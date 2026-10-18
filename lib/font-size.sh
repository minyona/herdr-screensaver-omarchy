#!/bin/bash
# The font size (pt) for one monitor's screensaver terminal; bin/herdr-screensaver-launch calls it once per monitor:
#   font-size.sh <monitor-name>   prints the size (9, 11.5) and always exits 0
# A fixed size (state font_size=N, 6..36, set with `herdr-screensaver-ctl set font_size N`) wins. Otherwise
# terminal/screensaver/fontsize.py picks, from `hyprctl monitors -j`, the largest size at which herdr gets its
# full layout (>= 150x40, the one the Mac shows) on that monitor. On any error: 12.
# Each call appends one line to $DATA/font.log (capped at about 200 lines);
# $DATA is ${HERDR_SS_DATA:-~/.local/share/herdr-screensaver-plugin}.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
APP=$(dirname "$HERE")
DATA=${HERDR_SS_DATA:-$HOME/.local/share/herdr-screensaver-plugin}
FALLBACK=12
m=${1:-}

flog() {
  local f="$DATA/font.log"
  {
    mkdir -p "$DATA" && printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$*" >>"$f"
    if [ "$(wc -l <"$f")" -gt 250 ]; then tail -n 200 "$f" >"$f.tmp" && mv -f "$f.tmp" "$f"; fi
  } 2>/dev/null || true
}
# a size the terminals take: 6..36, whole or .5
valid() { [[ $1 =~ ^([1-9][0-9]?)(\.5)?$ ]] && [ "${BASH_REMATCH[1]}" -ge 6 ] && { [ "${BASH_REMATCH[1]}" -lt 36 ] || [ "$1" = 36 ]; }; }
fallback() {
  flog "${m:-?} fallback $FALLBACK pt: $1"
  echo "$FALLBACK"
  exit 0
}

fixed=$( [ -f "$DATA/state" ] && sed -n 's/^font_size=//p' "$DATA/state" | head -n 1)
if [ -n "$fixed" ] && valid "$fixed"; then
  flog "${m:-?} fixed $fixed pt (state font_size)"
  echo "$fixed"
  exit 0
fi
[ -n "$m" ] || fallback "no monitor name given"
command -v hyprctl >/dev/null 2>&1 || fallback "hyprctl not found"
command -v python3 >/dev/null 2>&1 || fallback "python3 not found"
mons=$(hyprctl monitors -j 2>/dev/null) || fallback "hyprctl monitors -j failed"
err=$(mktemp "${TMPDIR:-/tmp}/herdr-font.XXXXXX" 2>/dev/null) || fallback "mktemp failed"
pt=$(printf '%s' "$mons" | PYTHONPATH="$APP/terminal" python3 -B -m screensaver.fontsize "$m" 2>"$err")
rc=$?
why=$(head -n 1 "$err" 2>/dev/null)
rm -f "$err"
[ "$rc" = 0 ] || fallback "${why:-screensaver.fontsize exited $rc}"
valid "$pt" || fallback "not a size: '$pt'"
flog "$why"
echo "$pt"
