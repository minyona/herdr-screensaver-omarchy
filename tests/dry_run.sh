#!/usr/bin/env bash
# The plugin's life in a throw-away HOME, against Omarchy 4.0.0.alpha's real scripts (tests/omarchy/fixtures/v4-real,
# = the XPS): "add" (a git clone into ~/.config/omarchy/plugins/<id>, as `omarchy plugin add` does; nothing of ours
# runs), every command the service would run (the exact argv from Model.js: ctl status/set, the launcher with fakes,
# a headless engine run), then "remove" (rm -rf of the plugin dir) and the README's purge. After every step the whole
# HOME is snapshotted (each path's type and sha256); the checks:
#   1. nothing changes outside the plugin dir and ~/.local/share/herdr-screensaver-plugin, at any step
#   2. remove + purge -> HOME equals the snapshot before add (empty diff)
#   3. remove without purge -> the diff is only under ~/.local/share/herdr-screensaver-plugin
#   4. shell.json, .bashrc, ~/.config/hypr, the menu extension and ~/.local/state/omarchy are byte-identical throughout
#   5. the takeover gate: while the plugin's launcher runs (its argv from Model.launchArgv), Omarchy's real
#      omarchy-launch-screensaver exits 0 at its pgrep gate and opens nothing; without it, it opens its terminals
#   6. nothing is ever written inside the plugin dir (no __pycache__, no state)
# Stubs (outside HOME): omarchy-shell, hyprctl, pkill, socat, xdg-terminal-exec, omarchy-hyprland-monitor-focused,
# omarchy-cmd-missing, omarchy-notification-send. pgrep is the real one.
#   tests/dry_run.sh [repo]   (default: this checkout; it clones its committed HEAD)
# shellcheck disable=SC2015  # `check && ok "..." || bad "..."` is intended: ok/bad always return 0
set -u
cd "$(dirname "$0")/.." || exit 2
REPO=$(pwd -P)
SRC=${1:-$REPO}
ID=io.github.minyona.herdr-screensaver
FIX="$REPO/tests/omarchy/fixtures"
FAKES="$REPO/tests/omarchy/fakes"
BASH5=${BASH5:-$(command -v /opt/homebrew/bin/bash /usr/local/bin/bash bash 2>/dev/null | head -n 1)}
# shellcheck disable=SC2016
"$BASH5" -c '[ "${BASH_VERSINFO[0]}" -ge 4 ]' || { echo "need bash >= 4 (set BASH5)"; exit 2; }
WORK=$(mktemp -d "${TMPDIR:-/tmp}/herdr-dry-run.XXXXXX")
trap 'pkill -f "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT   # every process started here has $WORK in its argv
PASS=0; FAIL=0
ok() { echo "ok   $*"; PASS=$((PASS+1)); }
bad() { echo "FAIL $*"; FAIL=$((FAIL+1)); }

H="$WORK/home dir"   # a space, as a real HOME could have
S="$WORK/stubs"
O="$H/.local/share/omarchy"
P="$H/.config/omarchy/plugins/$ID"
DATA="$H/.local/share/herdr-screensaver-plugin"
LOG="$WORK/log"; EVENTS="$WORK/events"
mkdir -p "$H" "$S" "$O/bin" "$H/.config/omarchy/extensions" "$H/.config/hypr" "$H/.local/state/omarchy/toggles" "$H/.local/state/omarchy/current/theme"
: > "$LOG"; : > "$EVENTS"

# ---- the fixture HOME: Omarchy's real scripts and config, a user's own files ----
cp -R "$FIX/v4-real/shell" "$O/"
cp "$FIX/v4-real/version" "$O/"
for f in "$FIX"/v4-real/bin/*; do { echo '#!/usr/bin/env bash'; tail -n +2 "$f"; } > "$O/bin/$(basename "$f")"; done   # bash 5 on macOS
cp "$FIX/v4/bin/omarchy-toggle-enabled" "$O/bin/"
chmod 755 "$O/bin"/*
cp "$FIX/v4-real/config/omarchy/shell.json" "$H/.config/omarchy/shell.json"
cp "$FIX/v4/themes/tokyo-night/colors.toml" "$H/.local/state/omarchy/current/theme/"
printf '# my bashrc\nexport EDITOR=nvim\n' > "$H/.bashrc"
printf -- '-- my hyprland config\n' > "$H/.config/hypr/hyprland.lua"
printf '{\n  "personal": {"icon":"","label":"Personal"},\n}\n' > "$H/.config/omarchy/extensions/omarchy-menu.jsonc"
mkdir -p "$H/.config/omarchy/plugins"

# ---- stubs (outside HOME) ----
for f in omarchy-shell hyprctl pkill socat xdg-terminal-exec omarchy-hyprland-monitor-focused omarchy-notification-send; do cp "$FAKES/$f" "$S/"; done
printf '#!/usr/bin/env bash\nexit 1\n' > "$S/omarchy-cmd-missing"   # nothing missing (ttfx "is there")
ln -s "$BASH5" "$S/bash"
chmod 755 "$S"/*
ENV=(env -i "HOME=$H" "USER=tester" "PATH=$S:$O/bin:/usr/bin:/bin:/usr/sbin:/sbin" "OMARCHY_PATH=$O"
     "XDG_RUNTIME_DIR=$WORK/run" "HYPRLAND_INSTANCE_SIGNATURE=test" "FAKE_LOG=$LOG" "FAKE_EVENTS=$EVENTS"
     "FAKE_LOCK_DIR=$WORK/lockstate" "TERM=xterm-256color" "PYTHONDONTWRITEBYTECODE=1")

# every path under HOME: type and sha256 (files), sorted
snap() {
  (cd "$H" && find . | LC_ALL=C sort | while IFS= read -r p; do
    if [ -L "$p" ]; then echo "link $p -> $(readlink "$p")"
    elif [ -f "$p" ]; then echo "file $p $(shasum -a 256 < "$p" | cut -d' ' -f1)"
    elif [ -d "$p" ]; then echo "dir  $p"
    else echo "othr $p"; fi
  done)
}
# the paths that changed between two snapshots (added, removed or changed)
changed() { diff <(echo "$1") <(echo "$2") | sed -n 's/^[<>] [a-z]* *\(\.[^ ]*\).*/\1/p' | sort -u; }
ALLOWED='^\./\.config/omarchy/plugins(/io\.github\.minyona\.herdr-screensaver(/.*)?)?$|^\./\.local/share/herdr-screensaver-plugin(/.*)?$|^\./\.local/share$'
# the user's and Omarchy's own files: must never change
mine() { (cd "$H" && find .bashrc .config/omarchy/shell.json .config/hypr .config/omarchy/extensions .local/state/omarchy .local/share/omarchy -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256); }
MINE0=$(mine)
S0=$(snap)
PREV=$S0
STEPS=0
step() {   # step <name>: snapshot, check rules 1 and 4 against the previous snapshot
  local now c out
  now=$(snap); c=$(changed "$PREV" "$now")
  out=$(grep -Ev "$ALLOWED" <<<"$c" | grep -v '^$')
  STEPS=$((STEPS+1))
  if [ -z "$out" ] && [ "$(mine)" = "$MINE0" ]; then
    ok "step $STEPS ($1): $(grep -c . <<<"$c") paths changed, all under the plugin dir or the data dir; user/Omarchy files byte-identical"
  else
    bad "step $STEPS ($1): changed outside: ${out:-none}"; diff <(echo "$MINE0") <(mine)
  fi
  PREV=$now
}
# the exact argv Model.js gives Service.qml (dir = the plugin dir, as Qt.resolvedUrl(".") would give it)
argv() { node -e 'const fs=require("fs"),os=require("os"),path=require("path");const t=fs.mkdtempSync(path.join(os.tmpdir(),"m-"));fs.copyFileSync(process.argv[1],t+"/M.cjs");const M=require(t+"/M.cjs");fs.rmSync(t,{recursive:true});const a=process.argv.slice(3);const v=a[0]==="launch"?M.launchArgv(process.argv[2],a[1]):M.ctlArgv(process.argv[2],...a.slice(1));process.stdout.write(v.join("\0"))' "$P/Model.js" "file://$P/" "$@"; }
# run one argv (NUL-separated) in the fixture env; its output in $OUT. Through a file, not $(...): the launcher's
# fake socat (tail -f) outlives it and would hold a pipe open (the EXIT trap ends it)
# macOS only: a login shell (-l) runs /etc/profile, whose path_helper puts /bin (bash 3.2) before the stubs, so the
# launcher (bash >= 4, like Omarchy's own) runs with -c there; on Omarchy -l keeps bash 5. Everything else is exact.
run_argv() {
  local -a a; mapfile -d '' a < <(argv "$@")
  [ "$1" != launch ] || [ "$(uname)" != Darwin ] || [ "${a[1]}" != -lc ] || a[1]=-c
  "${ENV[@]}" "${a[@]}" >"$WORK/out" 2>&1; RC=$?; OUT=$(cat "$WORK/out")
}

echo "== add: git clone file://<repo> (as omarchy plugin add does; nothing of ours runs)"
git clone -q "file://$SRC" "$P" 2>&1; rc=$?
hooks=$(find "$P/.git/hooks" -type f ! -name '*.sample' | wc -l | tr -d ' ')
[ $rc = 0 ] && [ -f "$P/manifest.json" ] && [ "$hooks" = 0 ] && [ ! -e "$DATA" ] \
  && ok "add: cloned to ~/.config/omarchy/plugins/$ID at $(git -C "$P" rev-parse --short HEAD); no git hooks (only git's .sample files); no data dir yet" || bad "add (rc $rc, hooks $hooks)"
step "add"
PSNAP=$(cd "$P" && find . -path ./.git -prune -o -print | LC_ALL=C sort | while IFS= read -r p; do [ -f "$p" ] && echo "$p $(shasum -a 256 < "$p" | cut -d' ' -f1)" || echo "$p"; done)

echo "== the service's commands (exact argv from Model.js)"
run_argv ctl status
grep -qx "enabled: ON" <<<"$OUT" && grep -qx "takeover: OFF" <<<"$OUT" && grep -qx "lock on wake: ON" <<<"$OUT" && grep -qx "old one-liner install: none" <<<"$OUT" && [ ! -e "$DATA" ] \
  && ok "status (bash -lc ... ctl status): enabled ON, takeover OFF, lock on wake ON; reads only, no data dir" || { bad "status ($RC)"; echo "$OUT"; }
step "status"
run_argv ctl set takeover on
[ $RC = 0 ] && grep -qx 'takeover=on' "$DATA/state" && grep -q '^takeover_since=' "$DATA/state" && [ "$(stat -f %Lp "$DATA")" = 700 ] \
  && ok "takeover on: state takeover=on + takeover_since in the data dir (mode 700)" || { bad "takeover on ($RC)"; echo "$OUT"; }
step "takeover on"
run_argv launch force
nx=$(grep -c exec_cmd "$LOG")
[ $RC = 0 ] && [ "$nx" = 2 ] && grep -qF -- "-e $(printf '%q' "$(cd "$P" && pwd -P)/lib/session.sh")" "$LOG" && grep -q "exec_cmd(\[\[alacritty --class=org.omarchy.screensaver -o font.size=9 " "$LOG" \
  && ok "test (bash -lc ... herdr-screensaver-launch force org.omarchy.screensaver): 2 terminals, font 9 on DP-1, -e <plugin>/lib/session.sh (HOME with a space quoted)" || { bad "launch force ($RC, $nx execs)"; echo "$OUT"; cat "$LOG"; }
step "launch force"
: > "$LOG"
"${ENV[@]}" "$BASH5" "$P/terminal/bin/herdr-screensaver" --frames 3000 --egg-rate 600 --seed 3 --found-file /dev/null >/dev/null 2>&1   # no write anywhere
"${ENV[@]}" HERDR_SS_DATA="$DATA" "$BASH5" "$P/terminal/bin/herdr-screensaver" --frames 6000 --egg-rate 600 --seed 3 >/dev/null 2>"$WORK/eng.err"; rc=$?
[ $rc = 0 ] && [ -s "$DATA/found" ] && grep -q 'end found [1-9]' "$WORK/eng.err" \
  && ok "engine (headless, as session.sh runs it with HERDR_SS_DATA): found eggs kept in the data dir ($(wc -l < "$DATA/found" | tr -d ' ') ids)" || { bad "engine ($rc)"; cat "$WORK/eng.err"; }
step "engine"
for kv in "lock_on_wake off" "lock_on_wake on" "font_size 9" "font_size auto"; do
  # shellcheck disable=SC2086
  run_argv ctl set $kv
  [ $RC = 0 ] || bad "ctl set $kv ($RC)"
done
grep -qx 'lock_on_wake=on' "$DATA/state" && grep -qx 'font_size=auto' "$DATA/state" && ok "lockOnWake off/on, fontSize 9/auto: state updated" || { bad "lock/font state"; cat "$DATA/state"; }
step "lockOnWake + fontSize"
run_argv ctl set enabled off; run_argv ctl set enabled on
run_argv ctl set takeover off
grep -qx 'takeover=off' "$DATA/state" && grep -qx 'enabled=on' "$DATA/state" && ok "disable/enable, takeover off: state updated" || bad "takeover off"
step "takeover off"

echo "== the takeover gate (Omarchy's real launcher, real pgrep)"
GATE="$WORK/gate-log"; : > "$GATE"
# the plugin's launcher, held at its start by a slow monitor-focused stub, its argv from Model.launchArgv(idle)
printf '#!/usr/bin/env bash\nsleep 4\necho DP-1\n' > "$WORK/slow-focus"; chmod 755 "$WORK/slow-focus"
mkdir -p "$WORK/slow"; cp "$WORK/slow-focus" "$WORK/slow/omarchy-hyprland-monitor-focused"
mapfile -d '' LA < <(argv launch idle)
[ "$(uname)" != Darwin ] || LA[1]=-c   # as run_argv
env -i "HOME=$H" "PATH=$WORK/slow:$S:$O/bin:/usr/bin:/bin:/usr/sbin:/sbin" "OMARCHY_PATH=$O" "XDG_RUNTIME_DIR=$WORK/run" "HYPRLAND_INSTANCE_SIGNATURE=test" \
  "FAKE_LOG=$WORK/plugin-log" "FAKE_EVENTS=$EVENTS" "FAKE_LOCK_DIR=$WORK/lockstate" "${LA[@]}" >/dev/null 2>&1 &
lp=$!
sleep 1
marker=$(pgrep -f '[o]rg.omarchy.screensaver' | tr '\n' ' ')
"${ENV[@]}" FAKE_LOG="$GATE" "$O/bin/omarchy-launch-screensaver" >"$WORK/gate.out" 2>&1; g1=$?
# the launcher and its command-substitution subshells (same argv, so the same marker)
pkill -f "$P/bin/herdr-screensaver-launch" 2>/dev/null; wait "$lp" 2>/dev/null
[ -n "$marker" ] && [ $g1 = 0 ] && ! grep -q exec_cmd "$GATE" && [ ! -s "$GATE" ] \
  && ok "gate: with the plugin's launcher running (pids $marker), Omarchy's omarchy-launch-screensaver exits 0 at its pgrep gate and runs nothing (no hyprctl, no ttfx terminal)" || { bad "gate with marker ($g1, marker '$marker')"; cat "$GATE" "$WORK/gate.out"; }
sleep 1
pkill -f "tail -n +1 -f $WORK" 2>/dev/null
: > "$GATE"
if [ -z "$(pgrep -f '[o]rg.omarchy.screensaver')" ]; then
  wdp() { "$@" & local p=$! w; ( sleep 10; kill -9 $p 2>/dev/null ) & w=$!; wait $p; local r=$?; kill $w 2>/dev/null; wait $w 2>/dev/null; return $r; }
  wdp "${ENV[@]}" FAKE_LOG="$GATE" "$O/bin/omarchy-launch-screensaver" >/dev/null 2>&1; g2=$?
  [ $g2 = 0 ] && [ "$(grep -c 'exec_cmd(\[\[alacritty --class=org.omarchy.screensaver .*-e omarchy-screensaver' "$GATE")" = 2 ] \
    && ok "gate: without it, the same launcher goes on and opens Omarchy's own screensaver on both monitors" || { bad "gate without marker ($g2)"; cat "$GATE"; }
else
  bad "gate: another process with org.omarchy.screensaver in its argv is running on this machine; cannot check the no-marker case"
fi
step "takeover gate"

echo "== the plugin dir is never written"
PSNAP2=$(cd "$P" && find . -path ./.git -prune -o -print | LC_ALL=C sort | while IFS= read -r p; do [ -f "$p" ] && echo "$p $(shasum -a 256 < "$p" | cut -d' ' -f1)" || echo "$p"; done)
[ "$PSNAP" = "$PSNAP2" ] && [ -z "$(find "$P" -name __pycache__ -o -name '*.pyc')" ] && ok "plugin dir: byte-identical to the clone after every command (no __pycache__, no state)" || { bad "plugin dir written"; diff <(echo "$PSNAP") <(echo "$PSNAP2"); }

echo "== remove (rm -rf the plugin dir, as omarchy plugin remove does) and purge"
rm -rf "$P"
step "remove"
c=$(changed "$S0" "$(snap)")
rest=$(grep -v '^$' <<<"$c" | grep -Ev '^\./\.local/share/herdr-screensaver-plugin(/.*)?$|^\./\.local/share$')
[ -z "$rest" ] && ok "remove without purge: the only difference from before add is ~/.local/share/herdr-screensaver-plugin ($(grep -c . <<<"$c") paths)" || { bad "remove: other differences"; echo "$rest"; }
grep -q 'herdr\|minyona' <(cd "$H" && find . -path ./.local/share/herdr-screensaver-plugin -prune -o -print) && bad "remove: a herdr path is left outside the data dir" || ok "remove: no herdr path left outside the data dir"
rm -rf "$H/.local/share/herdr-screensaver-plugin"   # the README's purge
step "purge"
d=$(diff <(echo "$S0") <(snap))
[ -z "$d" ] && ok "remove + purge: HOME equals the snapshot before add (empty diff, $(grep -c . <<<"$S0") paths)" || { bad "remove + purge: diff"; echo "$d"; }
[ "$(mine)" = "$MINE0" ] && ok "shell.json, .bashrc, ~/.config/hypr, the menu extension, ~/.local/state/omarchy, \$OMARCHY_PATH: byte-identical throughout" || bad "user files changed"

echo "---- $PASS ok, $FAIL failed"
[ $FAIL = 0 ]
