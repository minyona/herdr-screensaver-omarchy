#!/bin/bash
# Runs inside each per-monitor screensaver terminal (class org.omarchy.screensaver) that
# bin/herdr-screensaver-launch opens. Derived from Omarchy's omarchy-screensaver (MIT, (c) David Heinemeier
# Hansson; see THIRD_PARTY_NOTICES.md). Mirrors Omarchy's own omarchy-screensaver: hide/show the cursor (Lua config first,
# legacy keyword second), wait up to 2 s for the terminal to leave 80x24, run the screensaver, end on
# any key or mouse move (herdr itself) or when the window loses focus. Extra arguments go to the engine.
# Lock on wake (lock-on-wake.sh): every way out (key, mouse, focus loss, the window closing, a signal,
# the engine crashing or exiting non-zero) goes through on_exit, which asks Omarchy's lock to lock and waits
# until it is secure BEFORE the screensaver windows close (pkill, like Omarchy), unless Omarchy is
# already locking, or lock on wake is off (state lock_on_wake=off). If the lock cannot be confirmed it
# says so in $DATA/lock.log and a critical notification.
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

close_windows() {
  cursor_invisible false
  pkill -f '[o]rg.omarchy.screensaver' 2>/dev/null
  low_log "windows closed"
}

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
  low_deadline 4500   # the windows close within 4.5 s of here (lock phase 3 s, then the fallback and omarchy-system-lock)
  [ -n "$watcher" ] && kill "$watcher" 2>/dev/null
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then
    kill -TERM "$child" 2>/dev/null   # herdr restores the terminal on SIGTERM
    wait "$child" 2>/dev/null
  fi
  [ -z "$stty_saved" ] || stty "$stty_saved" <&3 2>/dev/null
  low_log "exit reason=$1"
  if ! low_enabled "$DATA/state"; then
    low_log "off (opt-out)"
  elif ! command -v omarchy-shell >/dev/null 2>&1; then
    low_fallback "omarchy-shell not found"
  elif low_already_locked; then
    # Omarchy's own lock (or the idle plugin's lockSystem) is running: no second request
    low_log "already locked ($LOW_WHICH): not requesting a lock"
    if low_wait_secure 3000; then low_log "secure after ${LOW_MS}ms"
    else low_log "already locked but not secure after 3s (Omarchy's own lock is in progress)"; fi
  elif ! low_request; then
    low_fallback "lock refused: ${LOW_REPLY:-no reply}"
  else
    low_log "requested reply=ok"
    if low_wait_secure 3000 ask; then
      low_log "secure after ${LOW_MS}ms"
      cursor_invisible false
      low_system_lock   # Omarchy's own lock steps; its pkill closes the windows
    else
      low_fallback "lock requested but not secure within 3s (status: ${LOW_STATUS:-no reply})"
    fi
  fi
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
  # black screen, mouse motion reported (so a mouse move wakes it), one key or mouse byte ends it
  (printf '\033[2J\033[H\033[?25l\033[?1003h\033[?1006h'; head -c 1 <&3 >/dev/null; printf '\033[?1003l\033[?1006l\033[?25h') &
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
