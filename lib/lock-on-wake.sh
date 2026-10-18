# shellcheck shell=bash
# shellcheck disable=SC2034  # LOW_WHICH, LOW_REPLY, LOW_MS and LOW_STATUS are read by session.sh
# Lock on wake, sourced by session.sh (no side effects when sourced; needs $DATA).
# Waking herdr (key, mouse, focus loss, the window closing, a signal, the engine ending) must leave
# Omarchy's own lock screen up: request the lock through Omarchy's lock plugin (omarchy-shell lock ...,
# the IPC in shell/plugins/lock/Service.qml), wait until it reports "secure", and only then let the
# screensaver windows close (closing them makes the idle plugin cancel its own lock). When that cannot
# be confirmed, low_fallback logs it, sends a critical notification and still tries every other lock.
# Log: $DATA/lock.log, one line per event, always on (capped at about 200 lines).
# Time: one budget (low_deadline, set when the exit starts) ends at LOW_STOP, by which the windows are
# closed (< 5 s). The lock phase (every IPC call, the secure wait, the re-asks and their sleeps) ends
# LOW_SYSLOCK_MS earlier, at LOW_END, leaving room for the fallback's commands (0.5 s each at most) and
# omarchy-system-lock (a 0.3 s IPC limit plus its "timeout 1s pidwait -x ttfx", a full second while a ttfx
# ignores SIGTERM). Nothing is waited for past LOW_STOP: what still runs then finishes on its own.

low_log() {
  local f="$DATA/lock.log"
  {
    mkdir -p "$DATA" && printf '%s pid %d lock-on-wake: %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$$" "$*" >>"$f"
    if [ "$(wc -l <"$f")" -gt 250 ]; then tail -n 200 "$f" >"$f.tmp" && mv -f "$f.tmp" "$f"; fi
  } 2>/dev/null || true
}

# milliseconds since the epoch (EPOCHREALTIME may use the locale's decimal separator: keep digits only)
low_now_ms() {
  if [ -n "${EPOCHREALTIME:-}" ]; then echo $((10#${EPOCHREALTIME//[!0-9]/} / 1000)); else echo $((SECONDS * 1000)); fi
}

# low_deadline <ms>: the exit's budget, <ms> from now (LOW_STOP); the lock phase ends LOW_SYSLOCK_MS before it
# (LOW_END). low_left: ms left of the lock phase; low_left_total: ms left of the whole budget.
LOW_END=""
LOW_STOP=""
LOW_SYSLOCK_MS=1500   # after the lock phase: the fallback's commands, then omarchy-system-lock (0.3 s IPC + 1 s pidwait + the rest)
low_deadline() { LOW_STOP=$(($(low_now_ms) + $1)); LOW_END=$((LOW_STOP - LOW_SYSLOCK_MS)); }
low_left() { if [ -n "$LOW_END" ]; then echo $((LOW_END - $(low_now_ms))); else echo 999999; fi; }
low_left_total() { if [ -n "$LOW_STOP" ]; then echo $((LOW_STOP - $(low_now_ms))); else echo 999999; fi; }

# low_ipc <limit ms> <lock function>: one call to the lock plugin, limited to what is left of the deadline
# (like omarchy-system-sleep-lock's lock_ipc); omarchy-shell bounds it itself (connection, timeout and
# unknown-target errors exit 1; refusals come back on stdout with exit 0). Fails at once when no time is left.
low_ipc() {
  local limit=$1 left; shift
  left=$(low_left)
  ((left > 0)) || return 1
  ((limit < left)) || limit=$left
  OMARCHY_SHELL_IPC_TIMEOUT=$(printf '%d.%03d' $((limit / 1000)) $((limit % 1000))) omarchy-shell lock "$@"
}

# low_bounded <ms> <cmd...>: run it (the dying terminal's SIGHUP ignored, every other signal at its
# default), and wait for it at most <ms> and never past LOW_STOP; one that takes longer keeps running
# on its own (logged), so a hung notification daemon, logind or ttfx cannot hold the windows open.
low_bounded() {
  local limit=$1 pid start; shift
  start=$(low_now_ms)
  (trap '' HUP; exec "$@") >/dev/null 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if (($(low_now_ms) - start >= limit)) || (($(low_left_total) <= 0)); then
      low_log "$1 still running after $(($(low_now_ms) - start))ms: not waiting for it (it finishes on its own)"
      return 0
    fi
    sleep 0.05
  done
  wait "$pid" 2>/dev/null || true
}

# Omarchy's own lock steps (keyboard layout, 1Password, ttfx, then its pkill of the windows), with a short
# IPC limit for its own lock request; waited for until LOW_STOP at most.
low_system_lock() {
  command -v omarchy-system-lock >/dev/null 2>&1 || return 0
  OMARCHY_SHELL_IPC_TIMEOUT=0.3 low_bounded 999999 omarchy-system-lock
}

# low_enabled <statefile>: off only for the exact line lock_on_wake=off (missing file or key: on)
low_enabled() {
  ! grep -qx 'lock_on_wake=off' "$1" 2>/dev/null
}

# already locked by Omarchy (its own lock, or the idle plugin's lockSystem)? sets LOW_WHICH
low_already_locked() {
  LOW_WHICH=""
  if [ "$(low_ipc 500 isLocked 2>/dev/null)" = true ]; then LOW_WHICH=isLocked; return 0; fi
  if command -v omarchy-hyprland-session-locked >/dev/null 2>&1 && omarchy-hyprland-session-locked >/dev/null 2>&1; then
    LOW_WHICH=session-locked; return 0
  fi
  return 1
}

# request the lock; LOW_REPLY holds the reply (or the error); succeeds only on "ok"
low_request() {
  LOW_REPLY=$(low_ipc 1000 lock 2>&1 | head -n 1)
  [ "$LOW_REPLY" = ok ]
}

# low_wait_secure <ms> [ask]: poll status until "secure":true (compact JSON, a fixed-string match), for at
# most <ms> and never past the lock phase; with ask, request again while the plugin does not hold the
# request (like omarchy-system-sleep-lock). Returns as soon as the time is up: no re-ask and no 0.1 s sleep
# is started without room for it (a re-ask that used up the rest ends the wait).
# Sets LOW_MS (time to secure) and LOW_STATUS (the last reply).
low_wait_secure() {
  local limit=$1 ask=${2:-} start s
  start=$(low_now_ms); LOW_STATUS=""
  # time for one more step of <ms>: inside <limit> and inside the lock phase
  room() { (($(low_now_ms) - start + $1 <= limit)) && (($(low_left) >= $1)); }
  while :; do
    s=$(low_ipc 500 status 2>/dev/null)
    [ -z "$s" ] || LOW_STATUS=$s
    if [[ $s == *'"secure":true'* ]]; then LOW_MS=$(($(low_now_ms) - start)); return 0; fi
    if [ -n "$ask" ] && [[ $s != *'"requested":true'* ]]; then
      room 1 || return 1
      low_ipc 1000 lock >/dev/null 2>&1
    fi
    room 100 || return 1
    sleep 0.1
  done
}

# the lock could not be confirmed: never quiet. Log, notify (critical), then every other lock there is.
low_fallback() {
  local why=$1
  low_log "FALLBACK: $why"
  if command -v logger >/dev/null 2>&1; then low_bounded 500 logger -t herdr-screensaver "lock on wake: FALLBACK: $why"; fi
  if command -v omarchy-notification-send >/dev/null 2>&1; then
    low_bounded 500 omarchy-notification-send -u critical "Screen did not lock" "herdr screensaver: $why (see $DATA/lock.log)"
  elif command -v notify-send >/dev/null 2>&1; then
    low_bounded 500 notify-send -u critical "Screen did not lock" "herdr screensaver: $why (see $DATA/lock.log)"
  fi
  if command -v loginctl >/dev/null 2>&1; then
    low_bounded 500 loginctl lock-session
    low_log "loginctl lock-session sent (Omarchy 3: hypridle locks; Omarchy 4: nothing listens to it)"
  fi
  low_system_lock
}
