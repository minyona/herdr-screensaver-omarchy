"""The font size per monitor: the largest size at which herdr gets its full layout (layout.FULL, the one
the Mac shows) on that monitor. One pure function, font_pt(); bin/herdr-screensaver-launch calls the CLI
once per monitor (through lib/font-size.sh) and passes the size to foot, alacritty, ghostty or kitty.

Model (assumptions):
  - the screensaver terminals use JetBrainsMono Nerd Font (Omarchy's screensaver configs do); its metrics,
    measured from JetBrainsMonoNerdFont-Regular.ttf (nerd-fonts v3.4.0, sha256 0ec29a68b539ece7078fc714cebff0c0
    accb2f4948f8f7963d9f5e86633b12d9; tools/font-metrics.py): advance 600, ascender 1020, descender -300,
    lineGap 0, unitsPerEm 1000, so a cell is 0.6 em wide and 1.32 em tall;
  - not dpi-aware: 1 pt = 4/3 logical px, times the output scale = physical px;
  - fullscreen with zero padding (Omarchy's window rule and screensaver configs);
  - the terminal renders at the fractional scale and rounds each cell dimension to whole physical px, never
    by more than rounding up. cells() rounds everything up, so it is the worst case.
A terminal with extra line spacing (a user line-height / adjust-cell-height) gets fewer rows; the
screensaver configs set none (a fixed size, state font_size=N, overrides it).

CLI: hyprctl monitors -j | PYTHONPATH=<app>/terminal python3 -m screensaver.fontsize <monitor-name>
  stdout: the size (9, 11.5); stderr: one line, e.g. "eDP-1 1920x1200@1.6 -> 9 pt, at least 160x46 (full)".
  Exit 0; 2 (with the reason on stderr) for a missing monitor, bad JSON or invalid numbers.
"""
import json
import math
import sys

from .layout import FULL, size_class

ADV = 0.600                 # JetBrainsMono Nerd Font: advance 600 / unitsPerEm 1000
ASC, DESC = 1.020, 0.300    # hhea/typo ascender 1020, |descender| 300, lineGap 0
PT_MIN, PT_MAX, PT_STEP, PT_FALLBACK = 8.0, 18.0, 0.5, 12.0   # 18 = Omarchy's stock size, never exceeded


def cells(width, height, scale, pt):
    """Worst-case cols x rows a terminal shows at pt on a width x height (physical px) output with this scale.
    Each cell dimension is rounded UP to whole physical px (the pessimistic bound for foot/alacritty/ghostty/kitty)."""
    p = pt * 4 / 3 * scale
    return int(width // math.ceil(ADV * p)), int(height // (math.ceil(ASC * p) + math.ceil(DESC * p)))


def _valid(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def font_pt(width, height, scale, transform=0):
    """The largest size in PT_MIN..PT_MAX (0.5 pt steps) at which cells() >= layout.FULL (150x40): herdr's
    full layout, the one the Mac shows. PT_MIN when even that is too big. transform 1/3/5/7 (90/270 deg) swaps w/h.
    Raises ValueError on non-positive or non-finite input (the caller falls back to PT_FALLBACK)."""
    if not (_valid(width) and _valid(height) and _valid(scale)):
        raise ValueError("width, height and scale must be positive finite numbers: %r %r %r" % (width, height, scale))
    if isinstance(transform, bool) or not isinstance(transform, int):
        raise ValueError("transform must be an integer: %r" % (transform,))
    if transform % 2:
        width, height = height, width
    n = int(round((PT_MAX - PT_MIN) / PT_STEP))
    for i in range(n, -1, -1):   # from the top: cell rounding makes cells() not strictly monotonic in pt
        pt = PT_MIN + i * PT_STEP
        c, r = cells(width, height, scale, pt)
        if c >= FULL[0] and r >= FULL[1]:
            return pt
    return PT_MIN


def fmt(pt):
    """9.0 -> "9", 11.5 -> "11.5" (what the terminals get)."""
    return ("%g" % pt)


def explain(name, mon, pt):
    """One line for stderr / font.log: "eDP-1 1920x1200@1.6 -> 9 pt, at least 160x46 (full)"."""
    w, h = mon["width"], mon["height"]
    if mon.get("transform", 0) % 2:
        w, h = h, w
    c, r = cells(w, h, mon["scale"], pt)
    return "%s %dx%d@%g -> %s pt, at least %dx%d (%s)" % (name, mon["width"], mon["height"], mon["scale"], fmt(pt), c, r, size_class(c, r))


def main(argv=None, stdin=None, out=None, err=None):
    argv = sys.argv[1:] if argv is None else argv
    stdin, out, err = stdin or sys.stdin, out or sys.stdout, err or sys.stderr
    if len(argv) != 1:
        err.write("usage: hyprctl monitors -j | python3 -m screensaver.fontsize <monitor-name>\n")
        return 2
    name = argv[0]
    try:
        mons = json.load(stdin)
    except ValueError as e:
        err.write("bad hyprctl monitors JSON: %s\n" % e)
        return 2
    mon = next((m for m in mons if isinstance(m, dict) and m.get("name") == name), None) if isinstance(mons, list) else None
    if mon is None:
        err.write("monitor %s not in hyprctl monitors\n" % name)
        return 2
    try:
        pt = font_pt(mon.get("width"), mon.get("height"), mon.get("scale"), mon.get("transform", 0))
    except ValueError as e:
        err.write("monitor %s: %s\n" % (name, e))
        return 2
    out.write(fmt(pt) + "\n")
    err.write(explain(name, mon, pt) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
