#!/usr/bin/env bash
# README accuracy: every command, repo path and data path the README names must exist.
#   - omarchy-shell herdr-screensaver <fn>: <fn> is a function of the IpcHandler in Service.qml
#   - herdr-screensaver-ctl subcommands named in the README exist in bin/herdr-screensaver-ctl
#   - repo paths (bin/ lib/ terminal/ tests/, root files) are tracked by git
#   - data files named under ~/.local/share/herdr-screensaver-plugin are ones the code writes
#   - the plugin id and the install URL match manifest.json / the planned repo
#   - install and removal sections both exist; the scanner-safe negation line is there verbatim
set -u
cd "$(dirname "$0")/.." || exit 2
R=README.md
fail=0
bad() { echo "readme_check: FAIL: $*"; fail=1; }
ok() { echo "readme_check: ok: $*"; }
tracked=$(git ls-files)
has() { grep -qxF -- "$1" <<<"$tracked"; }

# IPC functions
ipc=$(awk '/IpcHandler \{/,0' Service.qml | sed -n 's/^ *function \([A-Za-z]*\)(.*/\1/p' | sort -u)
for fn in $(grep -o 'omarchy-shell herdr-screensaver [A-Za-z]*' "$R" | awk '{print $3}' | sort -u); do
  if grep -qx "$fn" <<<"$ipc"; then ok "ipc $fn"; else bad "ipc function '$fn' not in Service.qml"; fi
done
# arguments shown with the IPC calls are ones the code accepts
for pair in "takeover on" "takeover off" "lockOnWake off" "fontSize 11.5" "fontSize auto"; do
  grep -qF "omarchy-shell herdr-screensaver $pair" "$R" || continue
  # shellcheck disable=SC2086
  set -- $pair
  case $1 in
  takeover | lockOnWake) [[ $2 == on || $2 == off || $2 == status ]] || bad "bad arg $pair" ;;
  fontSize) bash bin/herdr-screensaver-ctl get font_size >/dev/null && [[ $2 == auto || $2 =~ ^[0-9]+(\.5)?$ ]] || bad "bad arg $pair" ;;
  esac
  ok "ipc args $pair"
done

# ctl subcommands
for sub in get set status paths; do
  if grep -q "\`$sub" "$R"; then grep -qE "^ *$sub\)" bin/herdr-screensaver-ctl && ok "ctl $sub" || bad "ctl $sub missing"; fi
done

# repo paths in backticks or links
for p in $( { grep -oE '`(bin|lib|terminal|tests)/[A-Za-z0-9_./-]+`' "$R" | tr -d '`'; grep -oE '\]\([A-Za-z_.-]+\.(md|png)\)|\]\(LICENSE\)' "$R" | sed 's/^](//; s/)$//'; grep -oE '`(Service\.qml|Model\.js|manifest\.json|content\.json)`' "$R" | tr -d '`'; } | sort -u); do
  if has "$p"; then ok "file $p"; else bad "file $p not tracked"; fi
done

# data files: each named one is written by the code
# shellcheck disable=SC2088  # a label for the output, not a path
D='~/.local/share/herdr-screensaver-plugin'
for f in state found lock.log font.log debug.log debug; do
  grep -q "$f" "$R" || continue
  case $f in
  state) grep -q 'STATE="$DATA/state"' bin/herdr-screensaver-ctl ;;
  found) grep -q 'os.path.join(data_dir(), "found")' terminal/screensaver/cli.py ;;
  lock.log) grep -q 'f="$DATA/lock.log"' lib/lock-on-wake.sh ;;
  font.log) grep -q 'f="$DATA/font.log"' lib/font-size.sh ;;
  debug.log) grep -q '"debug.log"' terminal/screensaver/cli.py && grep -q '$DATA/debug.log' lib/session.sh ;;
  debug) grep -q '\[ -e "$DATA/debug" \]' lib/session.sh ;;
  esac && ok "data $D/$f" || bad "data file $f not written by the code"
done
grep -q 'DATA=${HERDR_SS_DATA:-$HOME/.local/share/herdr-screensaver-plugin}' bin/herdr-screensaver-ctl lib/session.sh lib/font-size.sh || bad "data dir"
for f in bin/herdr-screensaver-ctl lib/session.sh lib/font-size.sh; do
  grep -qF 'DATA=${HERDR_SS_DATA:-$HOME/.local/share/herdr-screensaver-plugin}' "$f" || bad "$f: data dir differs"
done

# id, install, removal
id=$(python3 -I -c 'import json; print(json.load(open("manifest.json"))["id"])')
grep -qF "omarchy plugin remove $id" "$R" && ok "removal command uses $id" || bad "removal command"
grep -qF "omarchy plugin add https://github.com/minyona/herdr-screensaver-omarchy.git --enable" "$R" && ok "install command" || bad "install command"
grep -q '^## Install' "$R" && grep -q '^## Removal' "$R" && ok "install + removal sections" || bad "sections"
grep -qxF -- "- No sudo or pkexec is required." "$R" && ok "negation line" || bad "negation line"
grep -qF '](preview.png)' "$R" && ok "screenshot" || bad "screenshot"
# the egg count matches content.json
n=$(python3 -I -c 'import json; print(len(json.load(open("content.json"))["eggs"]))')
if grep -o '[0-9]\+ easter eggs\|^[0-9]\+ eggs' "$R" | grep -qv "^$n "; then bad "egg count differs from $n"; else ok "egg count $n"; fi
# the lead time and defaults match Model.js
grep -q 'var LEAD_SECONDS = 2 ' Model.js && grep -q '2 seconds before' "$R" && ok "lead time 2 s" || bad "lead time"
grep -q 'DEFAULT_SCREENSAVER = 150' Model.js && grep -q '150 s by default, so 148 s' "$R" && ok "150/148" || bad "150/148"

[ "$fail" = 0 ] && echo "readme_check: PASS" || echo "readme_check: FAILED"
exit "$fail"
