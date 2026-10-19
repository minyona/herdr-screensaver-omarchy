#!/bin/bash
# Runs inside each per-monitor screensaver terminal (class org.omarchy.screensaver) that
# bin/herdr-screensaver-launch opens. Derived from Omarchy's omarchy-screensaver (MIT, (c) David Heinemeier
# Hansson; see THIRD_PARTY_NOTICES.md). Mirrors Omarchy's own omarchy-screensaver: hide/show the cursor (Lua config first,
# legacy keyword second), wait up to 2 s for the terminal to leave 80x24, run the screensaver, end on
# any key or mouse move (herdr itself) or when the window loses focus. Extra arguments go to the engine.
# Lock on wake (lock-on-wake.sh): every way out (key, mouse, focus loss, the window closing, a signal,
# the engine crashing or exiting non-zero) goes through on_exit, which asks Omarchy's lock to lock and waits
# until it is secure (status "secure":true) BEFORE the screensaver windows close (pkill, like Omarchy),
# unless lock on wake is off (state lock_on_wake=off). When Omarchy is already locking (isLocked, or a
# compositor lock) it asks for no second lock but still waits for secure. If the lock cannot be confirmed
# it says so in $DATA/lock.log and a critical notification, and the windows stay up (lock_failed_loop):
# "Lock failed" on screen, retries with growing waits (a key retries at once), then a wait for a key;
# they close only once a lock is secure (or Omarchy's own lock closes them).
# $DATA is ${HERDR_SS_DATA:-~/.local/share/herdr-screensaver-plugin} (the plugin's only data dir).
# Debug (HERDR_SS_DEBUG=1, or the file $DATA/debug): sizes and TERM go to $DATA/debug.log. While the file
# $DATA/print-size exists, the terminal shows its size and layout (--print-size) instead of the screensaver.
# A bash started with INT/QUIT ignored (an & job of a non-interactive script) cannot trap them, so
# kill -INT/-QUIT would end it without on_exit: start once more with their default handling.
if [ -z "${HERDR_SS_SIGRESET:-}" ] && [[ $(trap -p INT QUIT) == *"''"* ]] && command -v python3 >/dev/null 2>&1; then
  export HERDR_SS_SIGRESET=1
  exec python3 -B -I -c 'import os, signal, sys
for s in (signal.SIGINT, signal.SIGQUIT): signal.signal(s, signal.SIG_DFL)
os.execv(sys.argv[1], sys.argv[1:])' "$BASH" "${BASH_SOURCE[0]}" "$@"
fi
unset HERDR_SS_SIGRESET
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
APP=$(dirname "$HERE")
ENGINE="$APP/terminal/bin/herdr-screensaver"
DATA=${HERDR_SS_DATA:-$HOME/.local/share/herdr-screensaver-plugin}
export HERDR_SS_DATA="$DATA"   # the engine keeps its found eggs and debug log here too

# shellcheck source=lib/lock-on-wake.sh
if ! . "$HERE/lock-on-wake.sh"; then
  # Without it nothing can wait for a secure lock, so nothing here closes the windows (no
  # omarchy-system-lock: its pkill would close them before the lock is secure). Say so loudly, ask for the
  # lock, and stay up until Omarchy's own lock closes the window (or the user does).
  why="lock-on-wake.sh is missing or broken in $HERE; re-add the plugin"
  { mkdir -p "$DATA" && printf '%s pid %d lock-on-wake: FALLBACK: %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$$" "$why" >>"$DATA/lock.log"; } 2>/dev/null
  logger -t herdr-screensaver "lock on wake: FALLBACK: $why" >/dev/null 2>&1
  omarchy-notification-send -u critical "Screen did not lock" "herdr screensaver: $why" >/dev/null 2>&1 ||
    notify-send -u critical "Screen did not lock" "herdr screensaver: $why" >/dev/null 2>&1
  OMARCHY_SHELL_IPC_TIMEOUT=1 omarchy-shell lock lock >/dev/null 2>&1
  loginctl lock-session >/dev/null 2>&1
  printf '\033[2J\033[Hherdr screensaver: %s\n' "$why"
  exec sleep 2147483647   # still this pid, so closing the window (HUP) or a kill ends it
fi

debug=""
if { [ -n "${HERDR_SS_DEBUG:-}" ] && [ "$HERDR_SS_DEBUG" != 0 ]; } || [ -e "$DATA/debug" ]; then debug=1; fi
dlog() {
  [ -n "$debug" ] || return 0
  { mkdir -p "$DATA" && printf '%s session.sh pid %d %s\n' "$(date +%Y-%m-%dT%H:%M:%S)" "$$" "$*" >>"$DATA/debug.log"; } 2>/dev/null || true
}

cursor_invisible() {
  hyprctl eval "hl.config({ cursor = { invisible = $1 } })" &>/dev/null || hyprctl keyword cursor:invisible "$1" &>/dev/null || true
}

screensaver_in_focus() {
  hyprctl activewindow -j | jq -e '.class == "org.omarchy.screensaver"' >/dev/null 2>&1
}

# The plugin's only window kill. Refuses (and keeps the windows up in lock_failed_loop) unless this exit has
# a confirmed secure lock (LOW_SECURE, set only by low_wait_secure) or lock on wake is off (close_ok).
close_windows() {
  if [ "${LOW_SECURE:-}" != 1 ] && [ "$close_ok" != opt-out ]; then
    low_log "BUG: close without a secure lock refused"
    lock_failed_loop "internal: close without a secure lock"   # never returns
  fi
  cursor_invisible false
  pkill -f '[o]rg.omarchy.screensaver' 2>/dev/null
  low_log "windows closed"
}

# Test knobs (not user settings): retries per round (1..20) and the first retry's wait (100..60000 ms)
lock_retries=${HERDR_SS_LOCK_RETRIES:-5}
{ [[ $lock_retries =~ ^[1-9][0-9]?$ ]] && ((lock_retries <= 20)); } || lock_retries=5
lock_backoff=${HERDR_SS_LOCK_BACKOFF_MS:-2000}
{ [[ $lock_backoff =~ ^[1-9][0-9]{2,4}$ ]] && ((lock_backoff <= 60000)); } || lock_backoff=2000

ms_sleep() { sleep "$(printf '%d.%03d' $(($1 / 1000)) $(($1 % 1000)))"; }

# key_wait <ms>: wait for a key on the terminal (fd 3) for <ms> (0: no limit), in slices of 1 s at most;
# lock_failed_loop has put the tty in -icanon -echo -isig (Ctrl+C is a key there, not a signal, also between
# two waits). Returns 0 on a key, 1 when the time is up, 2 when the terminal is gone (stty fails, or reads
# come back empty at once three times in a row). The rest of an escape sequence (an arrow key) is read away
# with the key. Not bash's read -n (it turns isig back on), not dd.
key_wait() {
  local ms=$1 end t0 dt n quick=0 rc=1
  end=$(($(low_now_ms) + ms))
  while :; do
    dt=10
    if ((ms > 0)); then
      dt=$(((end - $(low_now_ms)) / 100))
      ((dt > 0)) || break
      ((dt <= 10)) || dt=10
    fi
    stty min 0 time "$dt" <&3 2>/dev/null || { rc=2; break; }
    t0=$(low_now_ms)
    n=$(head -c 1 <&3 2>/dev/null | wc -c)
    if ((n > 0)); then
      stty min 0 time 0 <&3 2>/dev/null && head -c 256 <&3 >/dev/null 2>&1
      rc=0; break
    fi
    if (($(low_now_ms) - t0 < 50)); then
      quick=$((quick + 1)); ((quick < 3)) || { rc=2; break; }
    else quick=0; fi
  done
  return "$rc"
}

fail_screen() {   # <first line> <why>
  printf '\033[2J\033[H%s\n\nherdr screensaver: the screen did not lock: %s\nLog: %s\n' "$1" "$2" "$DATA/lock.log" 2>/dev/null
}

# The lock failed ($1 says why) and the windows must stay up. A round: the alert (FALLBACK, critical
# notification, logind), then up to $lock_retries retries, the waits before them growing from $lock_backoff ms
# (low_backoff_ms; a key retries at once). After a round: wait for a key (no time limit), then a new round.
# Ends only with a secure lock (then Omarchy's lock steps and close_windows, as on success), or when the
# terminal is gone: the round ends on its timer, then it exits without closing anything.
lock_failed_loop() {
  local why=$1 r=0 i gap how t0 left tty=1 saved
  saved=$(stty -g <&3 2>/dev/null) && stty -icanon -echo -isig <&3 2>/dev/null
  while :; do
    r=$((r + 1))
    low_deadline 4500
    low_alert "$why"
    for ((i = 1; i <= lock_retries; i++)); do
      gap=$(low_backoff_ms "$i" "$lock_backoff")
      how=timer
      if [ -n "$tty" ]; then
        fail_screen "Lock failed, retrying in $(((gap + 999) / 1000))s (attempt $i/$lock_retries). Press a key to retry now." "$why"
        t0=$(low_now_ms)
        key_wait "$gap"
        case $? in
        0) how=key ;;
        2) tty=""; left=$((gap - ($(low_now_ms) - t0))); ((left <= 0)) || ms_sleep "$left" ;;
        esac
      else
        ms_sleep "$gap"
      fi
      low_log "retry $r.$i/$lock_retries ($how)"
      if low_attempt; then
        [ -z "$saved" ] || stty "$saved" <&3 2>/dev/null
        cursor_invisible false
        low_system_lock   # Omarchy's own lock steps; its pkill closes the windows
        close_windows
        exit 0
      fi
      why=$LOW_WHY
      low_log "retry $r.$i/$lock_retries failed: $why"
      if command -v loginctl >/dev/null 2>&1; then low_bounded 500 loginctl lock-session; fi
    done
    low_log "round $r: $lock_retries retries failed; windows stay up, waiting for a key"
    if [ -n "$tty" ]; then
      fail_screen "Lock failed. Press a key to retry." "$why"
      key_wait 0 && continue
    fi
    low_log "terminal gone after a failed lock: exiting, windows not closed"
    cursor_invisible false
    exit 0
  done
}

close_ok=""
child=""
stty_saved=""
watcher=""
exiting=""
# The one way out. Runs once and cannot be cut short: the dying terminal's SIGHUP (from our own pkill,
# or Omarchy's) is ignored from here on, and INT/TERM/QUIT/USR1 are caught and dropped. Caught, not
# ignored: an ignored signal stays ignored in every command started from here (Omarchy's
# "timeout 1s pidwait" could then never stop its pidwait); a caught one is back at its default there.
on_exit() {
  [ -z "$exiting" ] || return 0
  exiting=1
  trap '' HUP
  trap ':' INT TERM QUIT USR1
  trap - EXIT
  low_deadline 4500   # a secure lock closes the windows within 4.5 s of here (lock phase 3 s, then omarchy-system-lock); otherwise lock_failed_loop keeps them up
  [ -n "$watcher" ] && kill "$watcher" 2>/dev/null
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
    kill -TERM "$child" 2>/dev/null   # herdr restores the terminal on SIGTERM
    wait "$child" 2>/dev/null
  fi
  [ -z "$stty_saved" ] || stty "$stty_saved" <&3 2>/dev/null
  [ -z "$blank" ] || printf '\033[?1003l\033[?1006l\033[?25h' 2>/dev/null   # mouse reports off, cursor back
  low_log "exit reason=$1"
  if ! low_enabled "$DATA/state"; then
    low_log "off (opt-out)"
    close_ok=opt-out
  elif ! command -v omarchy-shell >/dev/null 2>&1; then
    lock_failed_loop "omarchy-shell not found"   # never returns to close_windows below
  elif low_already_locked; then
    # Omarchy's own lock (or the idle plugin's lockSystem) is requested, pending or held: no second request
    # yet, but isLocked / a compositor lock is no confirmation; not secure within 3 s -> the failed-lock loop
    low_log "already locked ($LOW_WHICH): not requesting a lock; waiting for secure"
    if low_wait_secure 3000; then low_log "secure after ${LOW_MS}ms"
    else lock_failed_loop "already locked ($LOW_WHICH) but not secure within 3s (status: ${LOW_STATUS:-no reply})"; fi   # never returns
  elif low_attempt; then
    cursor_invisible false
    low_system_lock   # Omarchy's own lock steps; its pkill closes the windows
  else
    lock_failed_loop "$LOW_WHY"   # never returns to close_windows below
  fi
  # only: lock on wake off, or secure (close_windows refuses anything else)
  close_windows
  exit 0
}
trap 'on_exit signal:INT' INT
trap 'on_exit signal:TERM' TERM
trap 'on_exit signal:HUP' HUP
trap 'on_exit signal:QUIT' QUIT
trap 'on_exit focus' USR1
trap 'on_exit shell-exit' EXIT

# Without python3 or the engine there is no herdr: a blank screen instead (never Omarchy's own saver,
# which would not lock on wake). Any key or mouse move still ends it through on_exit.
blank=""
if ! { command -v python3 >/dev/null 2>&1 && [ -x "$ENGINE" ]; }; then
  blank=1
  low_log "engine missing (python3 or $ENGINE): showing a blank screen; waking still locks"
  omarchy-notification-send "herdr screensaver" "The herdr engine or python3 is missing; showing a blank screen" >/dev/null 2>&1 || true
fi

cursor_invisible true

wait_for_terminal_resize() {
  local deadline=$((SECONDS + 2))
  while ((SECONDS < deadline)) && [[ $(stty size 2>/dev/null) == "24 80" ]]; do
    sleep 0.02
  done
}
dlog "start: stty size $(stty size 2>/dev/null || echo unavailable), TERM=${TERM:-unset}, TERM_PROGRAM=${TERM_PROGRAM:-unset}"
wait_for_terminal_resize
dlog "after the resize wait: stty size $(stty size 2>/dev/null || echo unavailable)"
# the real grid, next to font-size.sh's prediction in font.log (always on, capped like lock.log)
{
  mkdir -p "$DATA" && printf '%s session %s stty size %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$(tty 2>/dev/null || echo '?')" "$(stty size 2>/dev/null || echo unavailable)" >>"$DATA/font.log"
  if [ "$(wc -l <"$DATA/font.log")" -gt 250 ]; then tail -n 200 "$DATA/font.log" >"$DATA/font.log.tmp" && mv -f "$DATA/font.log.tmp" "$DATA/font.log"; fi
} 2>/dev/null || true

# Focus loss ends the screensaver, like Omarchy's (checked once a second); USR1 tells on_exit why.
(
  while sleep 1; do
    screensaver_in_focus || { kill -USR1 $$ 2>/dev/null; exit 0; }
  done
) &
watcher=$!

# herdr runs as a child (so the traps can fire while it runs) but keeps the terminal as stdin.
exec 3<&0
if [ -n "$blank" ]; then
  # Ctrl+C and Ctrl+\ become bytes that wake it (and lock), not signals the background reader ignores
  # (-isig; not bash's read -n, whose cbreak mode turns isig back on); on_exit restores the tty
  stty_saved=$(stty -g <&3 2>/dev/null) && stty -icanon -echo -isig min 1 time 0 <&3 2>/dev/null
  # black screen, mouse motion reported (so a mouse move wakes it), one key or mouse byte ends it. The reader
  # is head itself (child), so on_exit's kill ends it and no stale reader eats a key meant for lock_failed_loop;
  # on_exit turns the mouse reports off again.
  printf '\033[2J\033[H\033[?25l\033[?1003h\033[?1006h'
  head -c 1 <&3 >/dev/null &
else
  mode=()
  if [ -e "$DATA/print-size" ]; then
    mode=(--print-size)
    export HERDR_SS_DEBUG=1   # the engine also appends what it shows to debug.log
    debug=1
    dlog "print-size flag found: showing the size instead of the screensaver"
  fi
  "$ENGINE" --theme "${HERDR_SS_THEME:-omarchy}" ${mode[@]+"${mode[@]}"} "$@" <&3 &
fi
child=$!
wait "$child"
rc=$?
if [ "$rc" = 0 ]; then on_exit input; else on_exit "engine-exit:$rc"; fi
