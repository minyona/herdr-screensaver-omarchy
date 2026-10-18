#!/usr/bin/env bash
# The plugin's Omarchy-side checks, in throw-away HOMEs with a mocked Omarchy tree: Omarchy 4.0.0.alpha's
# real scripts from the XPS (fixtures/v4-real, SOURCES.md) + fakes (fakes/) for everything that needs a live
# Hyprland/omarchy-shell. Ported from the source app's tests/omarchy/run.sh at 39b6acc (the lock-on-wake and
# font sections; reports/builder-plugin.md maps every old check). Runs every script with bash 5.
#   tests/omarchy/run.sh            all checks (needs: bash 5, jq, python3, shellcheck)
# shellcheck disable=SC2015  # `check && ok "..." || bad "..."` is intended: ok/bad always return 0
set -u   # no pipefail: in `producer | grep -q` checks only grep's answer counts (a SIGPIPEd producer must not flip it)
cd "$(dirname "$0")/../.." || exit 2
REPO=$(pwd -P)
FIX="$REPO/tests/omarchy/fixtures"
FAKES="$REPO/tests/omarchy/fakes"
# the read-only XPS copy, when this machine has it (25q compares byte for byte)
REAL_FIX=${REAL_FIX:-$HOME/herdr/omarchy-lock-fonts/fixtures/omarchy-real}
BASH5=${BASH5:-$(command -v /opt/homebrew/bin/bash /usr/local/bin/bash bash 2>/dev/null | head -n 1)}
# shellcheck disable=SC2016  # expanded by the bash being tested, not here
"$BASH5" -c '[ "${BASH_VERSINFO[0]}" -ge 4 ]' || { echo "need bash >= 4 (set BASH5)"; exit 2; }
WORK=$(mktemp -d "${TMPDIR:-/tmp}/herdr-plugin-test.XXXXXX")
trap 'pkill -f "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT   # every process started here has $WORK in its argv
PASS=0; FAIL=0
ok() { echo "ok   $*"; PASS=$((PASS+1)); }
bad() { echo "FAIL $*"; FAIL=$((FAIL+1)); }
n=0
DATA_REL=.local/share/herdr-screensaver-plugin
LAUNCH="$REPO/bin/herdr-screensaver-launch"
CTL="$REPO/bin/herdr-screensaver-ctl"
FSH="$REPO/lib/font-size.sh"
FLOG_REL=$DATA_REL/font.log

# make_tree [v4|v4real] [home-dir-name] -> sets T, H (HOME), O (OMARCHY_PATH), PATH_T, ENV (env assignments)
# Like the real box: Omarchy's scripts in $O/bin, PATH $O/bin first. Omarchy's real lock scripts (fixtures/v4-real,
# = the XPS) are in $O/bin with their first line #!/usr/bin/env bash ($T/bin/bash = bash 5; 25 checks that is all)
REAL_LOCK_BINS="omarchy-system-lock omarchy-hyprland-session-locked omarchy-system-sleep-lock"
make_tree() {
  n=$((n+1)); T="$WORK/t$n"; H="$T/${2:-home}"
  mkdir -p "$H" "$T/bin"
  : > "$T/log"; : > "$T/events"
  cp "$FAKES"/* "$T/bin/"
  O="$H/.local/share/omarchy"
  mkdir -p "$O/bin" "$O/shell" "$H/.local/state/omarchy/current/theme" "$H/.config/omarchy"
  cp -R "$FIX/v4-real/shell/plugins" "$O/shell/"
  cp "$FIX/v4-real/config/omarchy/shell.json" "$H/.config/omarchy/"
  cp "$FIX/v4/bin/omarchy-toggle-enabled" "$O/bin/"
  cp "$FIX/v4/themes/tokyo-night/colors.toml" "$H/.local/state/omarchy/current/theme/"
  local f
  for f in $REAL_LOCK_BINS omarchy-launch-screensaver omarchy-screensaver; do
    { echo '#!/usr/bin/env bash'; tail -n +2 "$FIX/v4-real/bin/$f"; } > "$O/bin/$f"
  done
  chmod +x "$T/bin"/* "$O/bin"/*
  ln -sf "$BASH5" "$T/bin/bash"
  PATH_T="$O/bin:$T/bin:/usr/bin:/bin:/usr/sbin:/sbin:$H/.local/bin"
  ENV=(env -i "HOME=$H" "USER=tester" "PATH=$PATH_T" "OMARCHY_PATH=$O"
       "XDG_STATE_HOME=$H/.local/state" "XDG_RUNTIME_DIR=$T/run" "HYPRLAND_INSTANCE_SIGNATURE=test"
       "FAKE_LOG=$T/log" "FAKE_EVENTS=$T/events" "FAKE_ACTIVE=$T/active" "TERM=xterm-256color"
       "PYTHONDONTWRITEBYTECODE=1")  # macOS' CLT python3 otherwise caches stdlib bytecode under $HOME/Library
}
xps_tree() { make_tree v4real; }
ctl() { "${ENV[@]}" "$BASH5" "$CTL" "$@"; }
# entries and file contents
snapc() { (cd "$H" && find . -print0 | LC_ALL=C sort -z | xargs -0 stat -f '%N %HT' && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum) 2>/dev/null; }
# run "$@" with a 10 s watchdog (macOS has no timeout); returns its exit code, 137 when killed
wd() {
  "$@" & local p=$! w
  ( sleep 10; kill -9 $p 2>/dev/null ) & w=$!
  wait $p; local rc=$?
  kill $w 2>/dev/null; wait $w 2>/dev/null
  return $rc
}

echo "== 1. shellcheck"
# shellcheck disable=SC2046
out=$(shellcheck -x bin/herdr-screensaver-launch bin/herdr-screensaver-ctl lib/session.sh lib/lock-on-wake.sh lib/font-size.sh terminal/bin/herdr-screensaver tests/omarchy/run.sh tests/dry_run.sh tests/readme_check.sh 2>&1) \
  && ok "1. shellcheck: bin/, lib/, terminal/bin and the test scripts are clean" || { bad "1. shellcheck"; echo "$out"; }
s_ok=1; for f in bin/* lib/*.sh terminal/bin/herdr-screensaver; do "$BASH5" -n "$f" || s_ok=0; done
[ $s_ok = 1 ] && ok "1. bash -n on every shipped script" || bad "1. bash -n"

echo "== 7. the launcher with fakes (2 monitors, Alacritty)"
make_tree v4real
: > "$T/log"
wd "${ENV[@]}" "$BASH5" "$LAUNCH" idle org.omarchy.screensaver >/dev/null 2>&1; rc=$?
execs=$(grep -c "hl.dsp.exec_cmd" "$T/log")
m1=$(grep -c "hyprctl dispatch hl.dsp.exec_cmd(\[\[alacritty --class=org.omarchy.screensaver -o font.size=9 --config-file .*/default/alacritty/screensaver.toml --title=herdr-screensaver -e $REPO/lib/session.sh *\]\])" "$T/log")
m2=$(grep -c "hyprctl dispatch hl.dsp.exec_cmd(\[\[alacritty --class=org.omarchy.screensaver -o font.size=18 .* -e $REPO/lib/session.sh *\]\])" "$T/log")
[ $rc = 0 ] && [ "$execs" = 2 ] && [ "$m1" = 1 ] && [ "$m2" = 1 ] && ok "7. idle: 2 monitors -> 2 hl.dsp.exec_cmd ... alacritty --class=org.omarchy.screensaver -o font.size=9 (DP-1) / 18 (HDMI-A-1) ... --title=herdr-screensaver -e <abs>/lib/session.sh" || { bad "7. launcher execs ($rc $execs $m1 $m2)"; cat "$T/log"; }
grep -q "^hyprctl dispatch hl.dsp.focus({ monitor = \"DP-1\" })$" "$T/log" && [ "$(grep -c 'hl.dsp.focus' "$T/log")" = 3 ] && tail -n 1 "$T/log" | grep -q 'monitor = "DP-1"' \
  && ok "7. focus moves to each monitor, then back to the focused one (DP-1)" || { bad "7. focus"; cat "$T/log"; }
: > "$T/log"; touch "$T/running"
wd "${ENV[@]}" FAKE_RUNNING="$T/running" "$BASH5" "$LAUNCH" idle >/dev/null 2>&1; rc=$?
[ $rc = 0 ] && ! grep -q exec_cmd "$T/log" && grep -qF -- "pgrep -f -- [-]-(class|app-id)=org[.]omarchy[.]screensaver" "$T/log" \
  && ok "7. a screensaver terminal already running: exit 0, no exec" || { bad "7. running (rc $rc)"; cat "$T/log"; }
: > "$T/log"; mkdir -p "$H/.local/state/omarchy/toggles"; touch "$H/.local/state/omarchy/toggles/screensaver-off"
wd "${ENV[@]}" "$BASH5" "$LAUNCH" idle >/dev/null 2>&1; rc=$?
[ $rc = 1 ] && ! grep -q exec_cmd "$T/log" && ok "7. Omarchy's screensaver-off toggle: idle exits 1, no exec" || bad "7. off (rc $rc)"
: > "$T/log"; wd "${ENV[@]}" "$BASH5" "$LAUNCH" force org.omarchy.screensaver >/dev/null 2>&1; rc=$?
[ $rc = 0 ] && [ "$(grep -c exec_cmd "$T/log")" = 2 ] && ok "7. ... force (test) ignores it: 2 execs" || bad "7. force (rc $rc)"
rm -f "$H/.local/state/omarchy/toggles/screensaver-off"
r1=$("${ENV[@]}" "$BASH5" "$LAUNCH" 2>&1); c1=$?; r2=$("${ENV[@]}" "$BASH5" "$LAUNCH" now 2>&1); c2=$?; r3=$("${ENV[@]}" "$BASH5" "$LAUNCH" idle other.marker 2>&1); c3=$?
[ "$c1$c2$c3" = 222 ] && [[ $r1 == usage:* ]] && [[ $r3 == *"only marker"* ]] && ok "7. bad arguments: exit 2 (no mode, unknown mode, another marker)" || bad "7. args ($c1 $c2 $c3)"
: > "$T/log"; wd "${ENV[@]}" FAKE_TERMINAL=wezterm.desktop "$BASH5" "$LAUNCH" force >/dev/null 2>&1; rc=$?
[ $rc = 1 ] && ! grep -q exec_cmd "$T/log" && grep -q "^omarchy-notification-send -g ✋ Screensaver only runs in Alacritty, Foot, Ghostty, or Kitty$" "$T/log" \
  && ok "7. another terminal: Omarchy's notification, exit 1, no exec" || { bad "7. other terminal (rc $rc)"; cat "$T/log"; }
# the real pgrep: the launcher's own marker argument does not stop it (its gate looks for --class=/--app-id=)
make_tree v4real; rm -f "$T/bin/pgrep"
: > "$T/log"; wd "${ENV[@]}" "$BASH5" "$LAUNCH" idle org.omarchy.screensaver >/dev/null 2>&1; rc=$?
[ $rc = 0 ] && [ "$(grep -c exec_cmd "$T/log")" = 2 ] && ok "7. real pgrep: 'idle org.omarchy.screensaver' in its own argv does not stop it (2 execs)" || { bad "7. real pgrep self-gate (rc $rc)"; cat "$T/log"; }
# every flag of the stock lines is kept: take the added flags out and put '-e omarchy-screensaver' back -> the stock line
SF="$FIX/v4-real/bin/omarchy-launch-screensaver"
stock=$(grep -E '^ +hypr_exec (alacritty|ghostty|foot|kitty) ' "$SF" | sed 's/^ *//')
# shellcheck disable=SC2016  # literal text of the launcher
mine=$(grep -E '^ +hypr_exec (alacritty|ghostty|foot|kitty) ' "$LAUNCH" | sed -e 's/^ *//' \
  -e 's/ -o "font.size=$size"//' -e 's/ --font="$FOOT_FAMILY:size=$size"//' -e 's/--font-size="$size"/--font-size=18/' \
  -e 's/font_size="$size"/font_size=18/' -e 's/ --title=herdr-screensaver//' -e 's/-e "$SESSION"/-e omarchy-screensaver/')
[ -n "$stock" ] && [ "$mine" = "$stock" ] && ok "7. the 4 terminal lines are Omarchy's own plus only the font size, the title and -e lib/session.sh" || { bad "7. terminal lines vs stock"; diff <(echo "$stock") <(echo "$mine"); }

echo "== 8. session.sh in a pty"
for how in key focus; do
  make_tree v4
  res=$("${ENV[@]}" python3 "$REPO/tests/omarchy/pty_session.py" "$how" "$BASH5" "$REPO/lib/session.sh" "$T/active" "$H/$DATA_REL/found")
  limit=$([ $how = key ] && echo 1.0 || echo 2.0)
  took=$(echo "$res" | jq -r .took)
  if [ "$(echo "$res" | jq -r '.exit == 0 and .restored and .frame and .left_alt_screen and .found > 0')" = true ] && awk -v t="$took" -v l="$limit" 'BEGIN { exit !(t <= l) }'; then
    ok "8. $how: exit 0 in ${took}s (<= ${limit}s), tty restored, alt screen left, found file has $(echo "$res" | jq .found) ids"
  else bad "8. $how: $res"; fi
  # lock on wake (section 25 has every exit path): the lock is requested and secure before the cursor and the windows
  inv=$(grep -n "invisible = true" "$T/log" | head -n 1 | cut -d: -f1); vis=$(grep -n "invisible = false" "$T/log" | tail -n 1 | cut -d: -f1)
  req=$(grep -n "^omarchy-shell lock lock$" "$T/log" | head -n 1 | cut -d: -f1); sec=$(grep -n "secure=true$" "$T/log" | head -n 1 | cut -d: -f1)
  # the last window kill: session.sh's own, after the real omarchy-system-lock's (this tree has it in $O/bin)
  kil=$(grep -n "^pkill -f \[o\]rg.omarchy.screensaver$" "$T/log" | tail -n 1 | cut -d: -f1)
  [ -n "$inv" ] && [ -n "$req" ] && [ -n "$sec" ] && [ -n "$vis" ] && [ -n "$kil" ] && [ "$inv" -lt "$req" ] && [ "$req" -lt "$sec" ] && [ "$sec" -lt "$vis" ] && [ "$vis" -lt "$kil" ] \
    && ok "8. $how: log shows cursor invisible, then lock lock, then status secure=true, then cursor visible, then pkill -f [o]rg.omarchy.screensaver" || { bad "8. $how log"; cat "$T/log"; }
done

echo "== 25. lock on wake (real Omarchy v4.0.4 scripts + stub omarchy-shell)"
PTY="$REPO/tests/omarchy/pty_session.py"
LOCK_RE='^(omarchy-shell|hyprctl switchxkblayout|pgrep|pkill|timeout)'
lseq() { grep -E "$LOCK_RE" "$T/log"; }
# the full lock-on-wake sequence: session.sh asks (isLocked false), requests, polls to secure, runs the real
# omarchy-system-lock (its own request, layout, 1Password check, ttfx, its pkill), then its pkill backstop
LOCK_SEQ=$(printf '%s\n' "omarchy-shell lock isLocked" "omarchy-shell lock lock" "omarchy-shell lock status secure=false" "omarchy-shell lock status secure=true" \
  "omarchy-shell lock lock" "hyprctl switchxkblayout all 0" "pgrep -x 1password" "pkill -x ttfx" "timeout 1s pidwait -x ttfx" \
  "pkill -f [o]rg.omarchy.screensaver" "pkill -f [o]rg.omarchy.screensaver")
SYSLOCK_SEQ=$(printf '%s\n' "omarchy-shell lock lock" "hyprctl switchxkblayout all 0" "pgrep -x 1password" "pkill -x ttfx" "timeout 1s pidwait -x ttfx" "pkill -f [o]rg.omarchy.screensaver")
first() { grep -n -E -- "$2" "$1" | head -n 1 | cut -d: -f1; }
# order_ok <log> <re>...: the first match of each pattern on a strictly increasing line, and no window kill
# (pkill -f [o]rg.omarchy.screensaver) before the first secure=true
order_ok() {
  local log=$1 prev=0 l s k re; shift
  for re in "$@"; do l=$(first "$log" "$re"); [ -n "$l" ] && [ "$l" -gt "$prev" ] || return 1; prev=$l; done
  s=$(first "$log" 'secure=true$'); k=$(first "$log" '^pkill -f \[o\]rg\.omarchy\.screensaver$')
  [ -n "$s" ] && { [ -z "$k" ] || [ "$k" -gt "$s" ]; }
}
LL_REL=$DATA_REL/lock.log
SESS="$REPO/lib/session.sh"
LOPT=()
# lrun <how> [VAR=value...]: session.sh in the pty of this tree; sets res (JSON), lt (took), le (exit)
LR_BG=""
lrun() {
  local how=$1; shift
  # a run whose fallback or omarchy-system-lock was cut at the bound leaves them finishing on their own
  # (up to ~1.5 s, writing to the fake log): let them end before this run's log starts
  [ -z "$LR_BG" ] || sleep 2
  case " $* " in *" FAKE_TTFX=stubborn "* | *" FAKE_NOTIFY_SLEEP="*) LR_BG=1 ;; *) LR_BG="" ;; esac
  rm -rf "$T/log.lockstate"; : > "$T/log"; rm -f "$T/active" "$H/$LL_REL"
  res=$("${ENV[@]}" "$@" python3 "$PTY" "$how" "$BASH5" "$SESS" "$T/active" "$H/$DATA_REL/found" --settle 1 --limit 8 ${LOPT[@]+"${LOPT[@]}"})
  lt=$(echo "$res" | jq -r .took); le=$(echo "$res" | jq -r .exit)
}
le_s() { awk -v t="$lt" -v l="$1" 'BEGIN { exit !(t <= l) }'; }
llog() { grep -q -F -- "$1" "$H/$LL_REL" 2>/dev/null; }
mkdir -p "$WORK/proof"

# 25a: the real omarchy-system-lock alone
make_tree v4real
same=0; for f in $REAL_LOCK_BINS; do [ "$(diff "$FIX/v4-real/bin/$f" "$O/bin/$f" | grep -c '^[<>]')" = 2 ] && [ "$(diff "$FIX/v4-real/bin/$f" "$O/bin/$f" | head -n 1)" = 1c1 ] || same=1; done
[ $same = 0 ] && ok "25. the real lock scripts in \$O/bin differ from fixtures/v4-real only in line 1" || bad "25. real scripts changed beyond line 1"
"${ENV[@]}" "$O/bin/omarchy-system-lock"; rc=$?
cp "$T/log" "$WORK/proof/system-lock-sequence.txt"
[ $rc = 0 ] && [ "$(cat "$T/log")" = "$SYSLOCK_SEQ" ] \
  && ok "25a. real omarchy-system-lock against the stubs: exactly lock lock, switchxkblayout, pgrep 1password, pkill ttfx, timeout pidwait, pkill -f [o]rg.omarchy.screensaver" || { bad "25a. system-lock sequence (rc $rc)"; cat "$T/log"; }

# 25b: the real omarchy-hyprland-session-locked
"${ENV[@]}" "$O/bin/omarchy-hyprland-session-locked"; r1=$?
"${ENV[@]}" FAKE_SOLITARY_LOCK=1 "$O/bin/omarchy-hyprland-session-locked"; r2=$?
"${ENV[@]}" FAKE_HYPR_FAIL=1 "$O/bin/omarchy-hyprland-session-locked"; r3=$?
[ "$r1$r2$r3" = 102 ] && ok "25b. real omarchy-hyprland-session-locked: 1 unlocked, 0 with LOCK in solitaryBlockedBy, 2 when hyprctl fails" || bad "25b. session-locked exits $r1/$r2/$r3"

# 25c-25g: every way out locks first: lock requested -> secure -> windows closed
lock_case() {   # id, how, expected reason, [VAR=value...]
  local id=$1 how=$2 reason=$3; shift 3
  lrun "$how" "$@"
  if [ "$le" = 0 ] && [ "$(lseq)" = "$LOCK_SEQ" ] && order_ok "$T/log" '^omarchy-shell lock lock$' 'secure=true$' '^pkill -f \[o\]rg\.omarchy\.screensaver$' \
     && llog "exit reason=$reason" && llog "requested reply=ok" && llog "secure after " && llog "windows closed" && le_s 3 \
     && { [ "$how" = hupclose ] || [ "$(echo "$res" | jq -r .restored)" = true ]; }; then
    ok "$id. $how: lock lock -> status secure=true -> real omarchy-system-lock -> pkill -f, in that order (exact log); exit 0 in ${lt}s; reason=$reason"
  else bad "$id. $how: $res"; cat "$T/log"; cat "$H/$LL_REL" 2>/dev/null; fi
}
make_tree v4real
lock_case 25c key input
lock_case 25d mouse input
lock_case 25e focus focus
lock_case 25f term signal:TERM
lock_case 25g hup signal:HUP
lock_case 25g hupclose signal:HUP
cp "$T/log" "$WORK/proof/session-hupclose.log"
# 25r (fail-loop 1): kill -INT / -QUIT of the session while herdr runs, also when it starts with them ignored
lock_case 25r int signal:INT
lock_case 25r quit signal:QUIT
LOPT=(--ignore-intquit 1)
lock_case "25r (started with INT/QUIT ignored)" int signal:INT
lock_case "25r (started with INT/QUIT ignored)" quit signal:QUIT
LOPT=()

# 25h: the engine crashes / exits non-zero (a fake engine in a copy of the app; session.sh is unchanged)
make_tree v4real
mkdir -p "$T/app/lib" "$T/app/terminal/bin"
cp "$REPO/lib/session.sh" "$REPO/lib/lock-on-wake.sh" "$T/app/lib/"
# shellcheck disable=SC2016  # text of a script / a sed pattern, not expanded here
printf '#!/usr/bin/env bash\nprintf "herdr\\n"; sleep 1\n[ "$FAKE_ENGINE" = crash ] && kill -SEGV $$\nexit 3\n' > "$T/app/terminal/bin/herdr-screensaver"
chmod +x "$T/app/terminal/bin/herdr-screensaver"
SESS="$T/app/lib/session.sh"
lock_case 25h wait engine-exit:139 FAKE_ENGINE=crash
lock_case 25h wait engine-exit:3 FAKE_ENGINE=nonzero

# 25p: no engine: no exec of Omarchy's own saver (it would not lock), a blank screen, waking still locks
rm -rf "$T/app/terminal"
# shellcheck disable=SC2016  # text of a script / a sed pattern, not expanded here
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "omarchy-screensaver ran" >> "$FAKE_LOG"\n' > "$T/bin/omarchy-screensaver"; chmod +x "$T/bin/omarchy-screensaver"
LOPT=(--ready '\x1b[2J')
lock_case 25p key input
! grep -q '^omarchy-screensaver' "$T/log" && llog "engine missing" && ! grep -q 'exec omarchy-screensaver' "$REPO/lib/session.sh" \
  && ok "25p. engine missing: no omarchy-screensaver run (and no exec of it in session.sh); lock.log notes the missing engine" || { bad "25p. engine missing"; cat "$T/log" "$H/$LL_REL"; }
# 25t (fail-loop 1): on the blank screen Ctrl+C is a byte (stty -isig), so it wakes it and locks; tty restored
lock_case 25t ctrlc input
# 25u (fail-loop 1): lock-on-wake.sh missing: nothing closes the windows before a secure lock (no
# omarchy-system-lock, no pkill); FALLBACK logged, critical notification, the lock requested; the window stays
rm "$T/app/lib/lock-on-wake.sh"
LOPT=(--ready 'herdr screensaver:' --limit 2)
for v in "" "without omarchy-system-lock"; do
  [ -z "$v" ] || rm -f "$O/bin/omarchy-system-lock"
  lrun term
  [ "$le" = -15 ] && [ "$(lseq)" = "omarchy-shell lock lock" ] && ! grep -q -E '^(pkill|hyprctl switchxkblayout)' "$T/log" \
    && grep -q '^omarchy-notification-send -u critical Screen did not lock' "$T/log" && grep -q '^loginctl lock-session$' "$T/log" && grep -q '^logger -t herdr-screensaver' "$T/log" \
    && llog "FALLBACK: lock-on-wake.sh is missing" \
    && ok "25u. lock-on-wake.sh missing${v:+ ($v)}: lock requested, FALLBACK logged, critical notification, loginctl; no system-lock, no pkill; still up until killed" || { bad "25u. missing library $v: $res"; cat "$T/log"; }
done
LOPT=(); SESS="$REPO/lib/session.sh"

# 25i: already locked: no second request, no omarchy-system-lock; windows close after secure
make_tree v4real
for how in key focus term; do
  lrun "$how" FAKE_LOCKED=1
  [ "$le" = 0 ] && [ "$(lseq)" = "$(printf '%s\n' "omarchy-shell lock isLocked" "omarchy-shell lock status secure=true" "pkill -f [o]rg.omarchy.screensaver")" ] \
    && order_ok "$T/log" 'secure=true$' '^pkill -f' && llog "already locked (isLocked)" \
    && ok "25i. already locked (isLocked true), $how: no lock lock, no switchxkblayout, pkill -f after secure=true" || { bad "25i. $how: $res"; cat "$T/log"; }
done
lrun key FAKE_SOLITARY_LOCK=1
[ "$le" = 0 ] && [ "$(grep -c '^omarchy-shell lock lock$' "$T/log")" = 0 ] && ! grep -q switchxkblayout "$T/log" && llog "already locked (session-locked)" \
  && llog "already locked but not secure after 3s" && le_s 5 \
  && ok "25i. compositor lock (real omarchy-hyprland-session-locked: LOCK), isLocked false: no lock lock, no system-lock; logged; ${lt}s" || { bad "25i. solitary: $res"; cat "$T/log"; }

# 25j: the idle plugin's lockSystem (the real omarchy-system-lock) while herdr runs, then its pkill's SIGHUP
LOPT=(--before "$O/bin/omarchy-system-lock")
lrun hup
LOPT=()
[ "$le" = 0 ] && [ "$(grep -c '^omarchy-shell lock lock$' "$T/log")" = 1 ] && llog "already locked (isLocked)" && llog "exit reason=signal:HUP" \
  && ok "25j. idle plugin's lockSystem first, then SIGHUP: exactly one lock lock (system-lock's own); session.sh says already locked" || { bad "25j. $res"; cat "$T/log"; }

# 25k: fallbacks: logged, critical notification and loginctl lock-session BEFORE the windows close; bounded
fb_case() {   # name, why (in lock.log), limit, [VAR=value...]
  local name=$1 why=$2 lim=$3 nl ll kl; shift 3
  lrun key "$@"
  nl=$(first "$T/log" '^omarchy-notification-send -u critical Screen did not lock'); ll=$(first "$T/log" '^loginctl lock-session$'); kl=$(first "$T/log" '^pkill -f \[o\]rg')
  if [ "$le" = 0 ] && llog "FALLBACK: $why" && [ -n "$nl" ] && [ -n "$ll" ] && [ -n "$kl" ] && [ "$nl" -lt "$ll" ] && [ "$ll" -lt "$kl" ] && le_s "$lim" \
     && grep -q '^logger -t herdr-screensaver' "$T/log"; then
    ok "25k. fallback ($name): FALLBACK in lock.log, critical notification, then loginctl lock-session, then pkill; exit 0 in ${lt}s (<= ${lim}s)"
  else bad "25k. fallback $name: $res"; echo "notify line $nl, loginctl line $ll, window pkill line $kl, exit $le, took $lt"; cat "$T/log"; cat "$H/$LL_REL" 2>/dev/null; fi
}
make_tree v4real
rm "$T/bin/omarchy-shell"
fb_case "no omarchy-shell" "omarchy-shell not found" 2
make_tree v4real
fb_case "missing-pam" "lock refused: missing-pam" 2 FAKE_SHELL=missing-pam
fb_case "shell down" "lock refused: omarchy-shell: the shell is not running" 2 FAKE_SHELL=down
fb_case "hang" "lock refused: omarchy-shell: lock lock not responding" 5 FAKE_SHELL=hang
fb_case "never secure" "lock requested but not secure within 3s" 5 FAKE_SHELL=never-secure
# 25v (fail-loops 1 and 2): every lock call takes the full 1 s and status never says "requested":true, so it
# keeps asking again; and a ttfx that ignores SIGTERM, so the real omarchy-system-lock's "timeout 1s pidwait
# -x ttfx" runs its full second (the fake timeout really waits, and the fake pidwait only dies of its TERM:
# a TERM ignored by session.sh would leak into it and hang). One budget still bounds the request, the
# re-asks, their sleeps, the fallback and omarchy-system-lock: the process ends within 5 s of the key.
fired() { grep -q '^timeout fired after 1s: pidwait -x ttfx$' "$T/log"; }
syslock_cut() { llog "omarchy-system-lock still running after"; }
fb_case "1 s lock calls, never requested" "lock requested but not secure within 3s" 5 FAKE_SHELL=slow-unrequested
[ "$(grep -c '^omarchy-shell lock lock$' "$T/log")" -ge 3 ] && ok "25v. ... it did ask again ($(grep -c '^omarchy-shell lock lock$' "$T/log") lock calls incl. system-lock's) and still closed in ${lt}s" || { bad "25v. re-asks"; cat "$T/log"; }
fb_case "1 s lock calls, never requested, ttfx ignores SIGTERM" "lock requested but not secure within 3s" 5 FAKE_SHELL=slow-unrequested FAKE_TTFX=stubborn
{ fired || syslock_cut; } && grep -q '^timeout 1s pidwait -x ttfx$' "$T/log" && [ "$(grep -c '^omarchy-shell lock lock$' "$T/log")" -ge 3 ] && grep -qx "pkill -f \[o\]rg.omarchy.screensaver" "$T/log" \
  && ok "25v. ... re-asks + the real system-lock reaching its 1 s pidwait ($(fired && echo 'timeout fired' || echo 'cut at the bound, logged')), windows closed in ${lt}s (<= 5 s)" || { bad "25v. stubborn ttfx: $res"; cat "$T/log" "$H/$LL_REL"; }
fb_case "never secure, ttfx ignores SIGTERM" "lock requested but not secure within 3s" 5 FAKE_SHELL=never-secure FAKE_TTFX=stubborn
fired && ok "25v. never secure + ttfx ignores SIGTERM: pidwait waited 1 s, closed in ${lt}s (<= 5 s)" || { bad "25v. never-secure stubborn"; cat "$T/log"; }
fb_case "slow fallback (notification takes 2 s)" "lock requested but not secure within 3s" 5 FAKE_SHELL=slow-unrequested FAKE_TTFX=stubborn FAKE_NOTIFY_SLEEP=2
llog "omarchy-notification-send still running after" && syslock_cut \
  && ok "25v. a 2 s notification: not waited for past 0.5 s (logged), omarchy-system-lock cut at the bound (logged), windows closed in ${lt}s (<= 5 s)" || { bad "25v. slow fallback"; cat "$T/log" "$H/$LL_REL"; }
lrun key FAKE_TTFX=stubborn
[ "$le" = 0 ] && fired && order_ok "$T/log" '^omarchy-shell lock lock$' 'secure=true$' '^timeout 1s pidwait' '^pkill -f \[o\]rg\.omarchy\.screensaver$' && le_s 2.5 && llog "secure after " \
  && ok "25v. secure + ttfx ignores SIGTERM: lock -> secure -> system-lock (pidwait 1 s) -> pkill; ${lt}s" || { bad "25v. secure stubborn: $res"; cat "$T/log"; }


# 25l-25n: lock on wake is on by default and set with herdr-screensaver-ctl (the IPC lockOnWake calls it); fail closed
make_tree v4real
lrun key
[ ! -e "$H/$DATA_REL/state" ] && grep -q '^omarchy-shell lock lock$' "$T/log" && llog "requested reply=ok" && [ "$(ctl get lock_on_wake)" = on ] \
  && ok "25l. no state file (a fresh plugin): ctl says on, a key locks (fail closed)" || { bad "25l. default"; cat "$T/log"; }
st=$(ctl status)
echo "$st" | grep -qx "lock on wake: ON" && ok "25l. ctl status: lock on wake: ON" || { bad "25l. status"; echo "$st"; }
ctl set lock_on_wake off >/dev/null
st=$(ctl status)
lrun key
grep -qx 'lock_on_wake=off' "$H/$DATA_REL/state" && echo "$st" | grep -qx "lock on wake: OFF" && [ "$le" = 0 ] && ! grep -q '^omarchy-shell lock' "$T/log" \
  && grep -q '^pkill -f \[o\]rg.omarchy.screensaver$' "$T/log" && llog "off (opt-out)" \
  && ok "25m. ctl set lock_on_wake off: state off, status OFF; a key: no omarchy-shell lock call, windows closed, lock.log says off (opt-out)" || { bad "25m. off: $res"; echo "$st"; cat "$T/log"; }
ctl set lock_on_wake on >/dev/null
lrun key
grep -qx 'lock_on_wake=on' "$H/$DATA_REL/state" && grep -q '^omarchy-shell lock lock$' "$T/log" && ok "25m. ... set on again: a key locks" || { bad "25m. on again"; cat "$T/log"; }
sed -i '' '/^lock_on_wake=/d' "$H/$DATA_REL/state"
lrun key
grep -q '^omarchy-shell lock lock$' "$T/log" && llog "requested reply=ok" && ok "25n. a state without the key: a key locks" || { bad "25n. no key"; cat "$T/log"; }
printf 'lock_on_wake=off \n' >> "$H/$DATA_REL/state"
lrun key
grep -q '^omarchy-shell lock lock$' "$T/log" && ok "25n. only the exact line lock_on_wake=off turns it off (a trailing space does not)" || bad "25n. inexact off"
pre=$(cat "$H/$DATA_REL/state")
ctl set lock_on_wake maybe >/dev/null 2>&1; rc=$?
[ $rc = 2 ] && [ "$(cat "$H/$DATA_REL/state")" = "$pre" ] && ok "25n. ctl set lock_on_wake maybe: exit 2, state unchanged" || bad "25n. bad value (rc $rc)"

# 25q: fixture integrity
fx=0; nfx=0
# shellcheck disable=SC2016  # text of a script / a sed pattern, not expanded here
while read -r f h; do
  nfx=$((nfx+1)); [ "$(shasum -a 256 "$FIX/$f" | cut -d' ' -f1)" = "$h" ] || { fx=1; echo "sha256 mismatch: $f"; }
  if [ -d "$REAL_FIX" ]; then cmp -s "$FIX/$f" "$REAL_FIX/${f#v4-real/}" || { fx=1; echo "differs from fixtures/omarchy-real: $f"; }; fi
done < <(sed -n 's/^| `\(v4-real\/[^`]*\)` | `\([0-9a-f]\{64\}\)` |$/\1 \2/p' "$FIX/SOURCES.md")
[ $fx = 0 ] && [ "$nfx" = "$(find "$FIX/v4-real" -type f | wc -l | tr -d ' ')" ] && [ "$nfx" -gt 0 ] \
  && ok "25q. fixtures/v4-real: all $nfx files match their sha256 in SOURCES.md$([ -d "$REAL_FIX" ] && echo ' and cmp-equal fixtures/omarchy-real')" || bad "25q. fixture integrity ($nfx files)"

# S5: the README says it
RM="$REPO/README.md"
grep -qF "first asks Omarchy's lock to lock the screen and waits until it reports secure" "$RM" && grep -qF "omarchy-shell herdr-screensaver lockOnWake off" "$RM" \
  && grep -qF "lock.log" "$RM" && grep -qF "critical notification" "$RM" \
  && ok "S5. README: lock on wake (secure before the windows close), lockOnWake off, lock.log, the critical notification" || bad "S5. docs"

echo "== 26. font size per monitor (the plugin's launcher, Omarchy 4.0.0.alpha terminal lines)"
# run the launcher (force) with FAKE_TERMINAL=$1 and env $2...; X1/X2: the 1st/2nd exec, NX: execs
frun() {
  local t=$1; shift
  : > "$T/log"; : > "$T/events"
  wd "${ENV[@]}" "FAKE_TERMINAL=$t" "$@" "$BASH5" "$LAUNCH" force >/dev/null 2>&1; FRC=$?
  X1=$(grep exec_cmd "$T/log" | sed -n 1p); X2=$(grep exec_cmd "$T/log" | sed -n 2p); NX=$(grep -c exec_cmd "$T/log")
}
has() { printf '%s\n' "$1" | grep -q -F -- "$2"; }
ends_session() { has "$1" "-e $REPO/lib/session.sh ]])"; }
mon() { printf '{"name":"%s","width":%s,"height":%s,"scale":%s,"transform":0,"focused":true,"disabled":false,"specialWorkspace":{"name":""}}' "$@"; }

xps_tree
# 26a-d: each terminal, 2 monitors with different scales -> 9 and 18 in one launch
frun foot.desktop
[ $FRC = 0 ] && [ "$NX" = 2 ] && has "$X1" "foot --app-id=org.omarchy.screensaver --font=JetBrainsMono\\ Nerd\\ Font:size=9 --config=" && has "$X2" "--font=JetBrainsMono\\ Nerd\\ Font:size=18 --config=" \
  && ends_session "$X1" && ends_session "$X2" && [ "$(grep -o -- '--font=' <<<"$X1" | wc -l | tr -d ' ')" = 1 ] \
  && ok "26a. foot: --font=JetBrainsMono\\ Nerd\\ Font:size=9 (DP-1) / size=18 (HDMI-A-1), --config kept, -e session.sh" || { bad "26a. foot ($FRC $NX)"; cat "$T/log"; }
[ "$(grep -c "DP-1 1920x1200@1.6 -> 9 pt, at least 160x46 (full)" "$H/$FLOG_REL")" -ge 1 ] && grep -q "HDMI-A-1 2560x1440@1 -> 18 pt, at least 170x43 (full)" "$H/$FLOG_REL" \
  && ok "26a. font.log: one line per monitor with size, cells and class" || { bad "26a. font.log"; cat "$H/$FLOG_REL"; }
frun Alacritty.desktop
[ $FRC = 0 ] && [ "$NX" = 2 ] && has "$X1" "alacritty --class=org.omarchy.screensaver -o font.size=9 --config-file $O/default/alacritty/screensaver.toml --title=herdr-screensaver -e" && has "$X2" "-o font.size=18 --config-file" \
  && ends_session "$X1" && ends_session "$X2" \
  && ok "26b. alacritty: -o font.size=9 / 18, --config-file screensaver.toml kept" || { bad "26b. alacritty ($FRC $NX)"; cat "$T/log"; }
frun com.mitchellh.ghostty.desktop
[ $FRC = 0 ] && [ "$NX" = 2 ] && has "$X1" "--font-size=9 --title=herdr-screensaver -e" && has "$X2" "--font-size=18 --title=herdr-screensaver -e" && has "$X1" "--config-file=$O/default/ghostty/screensaver" \
  && [ "$(grep -o -- '--font-size' <<<"$X1" | wc -l | tr -d ' ')" = 1 ] && [ "$(grep -o -- '--font-size' <<<"$X2" | wc -l | tr -d ' ')" = 1 ] && ends_session "$X1" \
  && ok "26c. ghostty: --font-size=9 / 18, exactly one --font-size per exec" || { bad "26c. ghostty ($FRC $NX)"; cat "$T/log"; }
frun kitty.desktop
[ $FRC = 0 ] && [ "$NX" = 2 ] && has "$X1" "kitty --class=org.omarchy.screensaver --override font_size=9 --override window_padding_width=0 --title=herdr-screensaver -e" && has "$X2" "--override font_size=18 --override window_padding_width=0" \
  && ends_session "$X2" && ok "26d. kitty: --override font_size=9 / 18, window_padding_width=0 kept" || { bad "26d. kitty ($FRC $NX)"; cat "$T/log"; }

# 26e: the brief's 6 samples, one monitor each
e_ok=1; e_got=""
while read -r w h sc want; do
  frun foot.desktop "FAKE_MONITORS=[$(mon eDP-1 "$w" "$h" "$sc")]"
  e_got="$e_got ${w}x$h@$sc->$(sed -n 's/.*size=\([0-9.]*\) .*/\1/p' <<<"$X1")"
  [ "$NX" = 1 ] && has "$X1" "Nerd\\ Font:size=$want --config=" && tail -n 1 "$H/$FLOG_REL" | grep -q "eDP-1 ${w}x$h@$sc -> $want pt, at least [0-9]*x[0-9]* (full)$" || { e_ok=0; tail -n 1 "$H/$FLOG_REL"; }
done <<'S'
1920 1200 1.6 9
2560 1440 1 18
3840 2160 2 15
3840 2160 1.5 18
1920 1080 1 15
2880 1800 2 11.5
S
[ $e_ok = 1 ] && ok "26e. the brief's samples through the launcher:$e_got, each logged as full" || bad "26e. samples:$e_got"

# 26f: fallbacks -> 12 pt with the reason in font.log; the launcher still opens every terminal
frun foot.desktop "FAKE_MONITORS=[{\"name\":\"DP-1\",\"scale\":1.6},{\"name\":\"HDMI-A-1\",\"width\":0,\"height\":1440,\"scale\":1}]"
[ $FRC = 0 ] && [ "$NX" = 2 ] && has "$X1" "Nerd\\ Font:size=12 " && has "$X2" "Nerd\\ Font:size=12 " && ends_session "$X1" && ends_session "$X2" \
  && tail -n 2 "$H/$FLOG_REL" | grep -q "DP-1 fallback 12 pt: monitor DP-1: width, height and scale must be positive" \
  && tail -n 1 "$H/$FLOG_REL" | grep -q "HDMI-A-1 fallback 12 pt: monitor HDMI-A-1: width, height and scale must be positive" \
  && ok "26f. monitors without width / with width 0: 12 pt on both, reason in font.log, both terminals open, exit 0" || { bad "26f. bad monitor info ($FRC $NX)"; cat "$T/log"; tail -n 3 "$H/$FLOG_REL"; }
printf '#!/usr/bin/env bash\nexit 1\n' > "$T/bin/python3"; chmod 755 "$T/bin/python3"
frun kitty.desktop
rm -f "$T/bin/python3"
[ $FRC = 0 ] && [ "$NX" = 2 ] && has "$X1" "font_size=12 " && has "$X2" "font_size=12 " && ends_session "$X1" && tail -n 1 "$H/$FLOG_REL" | grep -q "HDMI-A-1 fallback 12 pt: screensaver.fontsize exited 1" \
  && ok "26f. python3 shadowed by a failing stub: 12 pt, logged, both terminals open" || { bad "26f. python3 stub ($FRC $NX)"; cat "$T/log"; tail -n 2 "$H/$FLOG_REL"; }
r1=$("${ENV[@]}" FAKE_MONITORS=garbage "$BASH5" "$FSH" DP-1 2>&1); l1=$(tail -n 1 "$H/$FLOG_REL")
r2=$("${ENV[@]}" "$BASH5" "$FSH" eDP-9 2>&1); l2=$(tail -n 1 "$H/$FLOG_REL")
r3=$(env -i "HOME=$H" PATH=/usr/bin:/bin "$BASH5" "$FSH" DP-1 2>&1); rc3=$?; l3=$(tail -n 1 "$H/$FLOG_REL")
r4=$("${ENV[@]}" "$BASH5" "$FSH" 2>&1); l4=$(tail -n 1 "$H/$FLOG_REL")
[ "$r1" = 12 ] && [[ $l1 == *"DP-1 fallback 12 pt: bad hyprctl monitors JSON"* ]] && [ "$r2" = 12 ] && [[ $l2 == *"eDP-9 fallback 12 pt: monitor eDP-9 not in hyprctl monitors" ]] \
  && [ "$r3" = 12 ] && [ $rc3 = 0 ] && [[ $l3 == *"DP-1 fallback 12 pt: hyprctl not found" ]] && [ "$r4" = 12 ] && [[ $l4 == *"? fallback 12 pt: no monitor name given" ]] \
  && ok "26f. font-size.sh alone: garbage JSON, unknown monitor, no hyprctl, no name -> prints 12, exit 0, the reason in font.log" || { bad "26f. font-size.sh fallbacks"; printf '%s|%s\n' "$r1" "$l1" "$r2" "$l2" "$r3" "$l3" "$r4" "$l4"; }
for i in $(seq 260); do echo "filler $i"; done >> "$H/$FLOG_REL"
"${ENV[@]}" "$BASH5" "$FSH" DP-1 >/dev/null 2>&1
[ "$(wc -l < "$H/$FLOG_REL" | tr -d ' ')" -le 250 ] && tail -n 1 "$H/$FLOG_REL" | grep -q "DP-1 1920x1200@1.6 -> 9 pt" && ok "26f. font.log is capped (<= 250 lines, newest kept)" || bad "26f. font.log cap"

# 26g: a fixed size (state font_size, set by ctl / the IPC fontSize) wins on every monitor; bad sizes are refused
xps_tree
ctl set font_size 11 >/dev/null
frun foot.desktop
[ "$NX" = 2 ] && has "$X1" "Nerd\\ Font:size=11 " && has "$X2" "Nerd\\ Font:size=11 " && grep -qx 'font_size=11' "$H/$DATA_REL/state" \
  && ctl status | grep -qx "font size: 11" && tail -n 1 "$H/$FLOG_REL" | grep -q "HDMI-A-1 fixed 11 pt (state font_size)" \
  && ok "26g. ctl set font_size 11: size=11 on every monitor; status: font size: 11; font.log says fixed" || { bad "26g. fixed 11"; cat "$T/log"; tail -n 2 "$H/$FLOG_REL"; }
g_ok=1
for v in abc 5 37 11.25 08 36.5 ''; do
  ctl set font_size "$v" >/dev/null 2>&1 && { g_ok=0; echo "'$v' taken"; }
done
grep -qx 'font_size=11' "$H/$DATA_REL/state" || g_ok=0
[ $g_ok = 1 ] && ok "26g. ctl set font_size abc|5|37|11.25|08|36.5|'': refused (exit 2), state keeps 11" || bad "26g. invalid sizes"
ctl set font_size 36 >/dev/null && frun kitty.desktop && has "$X1" "font_size=36 " && ctl set font_size 6.5 >/dev/null && frun kitty.desktop && has "$X2" "font_size=6.5 " \
  && ok "26g. the bounds: 36 and 6.5 are taken" || bad "26g. bounds"
printf 'font_size=99\n' > "$H/$DATA_REL/state"
frun foot.desktop
has "$X1" "Nerd\\ Font:size=9 " && has "$X2" "Nerd\\ Font:size=18 " && ok "26g. a hand-edited bad size in the state (99): ignored, per monitor (9 / 18)" || { bad "26g. bad state size"; cat "$T/log"; }
printf 'font_size=08\n' > "$H/$DATA_REL/state"
frun foot.desktop
has "$X1" "Nerd\\ Font:size=9 " && has "$X2" "Nerd\\ Font:size=18 " && ok "26g. a hand-edited 08 in the state: refused by font-size.sh like ctl and Model.js, per monitor (9 / 18)" || { bad "26g. 08 in state"; cat "$T/log"; }
ctl set font_size auto >/dev/null && frun foot.desktop && has "$X1" "Nerd\\ Font:size=9 " && ok "26g. ctl set font_size auto: per monitor again" || bad "26g. auto"

# F4: session.sh logs the real grid next to the prediction
make_tree v4
"${ENV[@]}" python3 "$REPO/tests/omarchy/pty_session.py" key "$BASH5" "$REPO/lib/session.sh" "$T/active" "$H/$DATA_REL/found" >/dev/null
grep -q " session /dev/[^ ]* stty size 50 160$" "$H/$FLOG_REL" && ok "F4. session.sh appends 'session <tty> stty size 50 160' to font.log (pty 160x50)" || { bad "F4. stty size line"; cat "$H/$FLOG_REL" 2>/dev/null; }

# F5: the README says it
# shellcheck disable=SC2016
grep -qF "Each monitor gets the largest font size (8 to 18 pt)" "$RM" && grep -qF "fontSize 11.5" "$RM" && grep -qF "font.log" "$RM" && grep -qF "9 pt" "$RM" \
  && ok "F5. README: font size per monitor, the XPS example (9 pt), fontSize, font.log" || bad "F5. docs"

echo "---- $PASS ok, $FAIL failed"
[ $FAIL = 0 ]
