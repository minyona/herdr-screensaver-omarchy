"""Burn-in model. Pure integer functions, wired into the engine by director.py (orbit drift in
Engine.draw, flip reflow in _relayout); --burnin off turns both off. Terminal engine only: the web
engine has no burn-in in this lineage, so tests/parity/run.sh compares with --burnin off.
 - Orbit drift: the board is drawn into a grid smaller than the screen by a margin and copied in at
   an offset that walks ORBIT, one step every STEP_MS of wall time.
 - Flip reflow: at a workspace flip, apply_variant moves (never resizes) the layout's rects.
"""

MARGIN_X = 2
MARGIN_Y = 2
STEP_MS = 30000

# Closed loop over every [dx, dy] in -2..2 x -2..2; each step (and last -> first) moves at most
# 1 cell per axis, so every row and column offset gets 1/5 of the time.
ORBIT = [
    [0, 0], [1, 0], [2, 0], [2, 1], [2, 2], [1, 2], [0, 2], [-1, 2], [-2, 2], [-2, 1], [-2, 0], [-2, -1], [-2, -2],
    [-1, -2], [0, -2], [1, -2], [2, -2], [2, -1], [1, -1], [0, -1], [-1, -1], [-1, 0], [-1, 1], [0, 1], [1, 1],
]

TEAM = ["planner", "builder", "odd0", "reviewer", "qa", "odd1"]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def margins(cols, rows, class_of):
    """Largest margins <= MARGIN_X / MARGIN_Y (mx first, then my with mx fixed) that keep the size
    class of the board equal to the screen's and leave a board of at least 1x1."""
    cls = class_of(cols, rows)
    mx = MARGIN_X
    while mx > 0 and (cols - 2 * mx < 1 or class_of(cols - 2 * mx, rows) != cls):
        mx -= 1
    my = MARGIN_Y
    while my > 0 and (rows - 2 * my < 1 or class_of(cols - 2 * mx, rows - 2 * my) != cls):
        my -= 1
    return {"mx": mx, "my": my}


def frame_at(cols, rows, wall_ms, class_of, on=True):
    """Board geometry at wall time wall_ms: board size bw x bh, drawn at screen offset (ox, oy)."""
    m = margins(cols, rows, class_of) if on else {"mx": 0, "my": 0}
    mx, my = m["mx"], m["my"]
    step = int(wall_ms // STEP_MS) % len(ORBIT)
    dx, dy = ORBIT[step]
    return {"mx": mx, "my": my, "bw": cols - 2 * mx, "bh": rows - 2 * my,
            "ox": mx + _clamp(dx, -mx, mx), "oy": my + _clamp(dy, -my, my), "step": step}


def variant_at(now_ms, flips):
    """Layout variant for the flip that happens at now_ms: 0 normal, 1 mirrored, 2 lead strip on top, 3 both."""
    return (int(now_ms // 60000) + flips) % 4


def apply_variant(layout, v):
    """New layout with the rects moved for variant v; every rect keeps its w and h. Bit 1 mirrors
    left <-> right; bit 2 puts the lead strip above the team rows (only where the lead strip sits
    directly below the team, i.e. not small). Tiny is returned unchanged."""
    rects = {k: dict(r) for k, r in layout["rects"].items()}
    if layout["cls"] != "tiny":
        lead = rects.get("lead")
        team = [k for k in TEAM if k in rects]
        if v & 2 and lead and team:
            top = min(rects[k]["y"] for k in team)
            if max(rects[k]["y"] + rects[k]["h"] for k in team) == lead["y"]:
                for k in team:
                    rects[k]["y"] += lead["h"]
                lead["y"] = top
        if v & 1:
            W = max(r["x"] + r["w"] for r in rects.values())
            for r in rects.values():
                r["x"] = W - r["x"] - r["w"]
    return dict(layout, rects=rects)
