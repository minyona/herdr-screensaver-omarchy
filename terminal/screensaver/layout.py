"""Screen layout per size class.

Shared with web/src/layout.js (layout parity test): "full" (>= 150x40) and "tiny". The Mac saver
only ever renders "full" (cellSize() gives >= 150 cols), so the classes below it are terminal-only:
  compact (>= 80x20):  sidebar + lead strip + team; what gets the columns, in order: the oddball (6th agent)
                       pane as a third team column when the focused workspace has one and 16 + 3 x MIN_PANE_W
                       fit, then btop (BTOP_MIN_W..60 cols, fetch above it at >= 140 cols), then the sidebar
                       grows from 16 to 24 cols (index numbers from 23). Lead strip a quarter of the body, as
                       in full, and at least 5 rows (3 inner). Fix 3 sizes the Omarchy font for "full"; compact is what is left below it
  narrow  (>= 60x16):  no sidebar (tab bar says ws k/n) + lead strip + 2x2 team; btop when there is room
  small   (>= 40x12):  team as tabs: planner + builder, btop (as before)
  tiny:               lead only
Every team/oddball pane below "full" is at least MIN_PANE_W x MIN_PANE_H, so its title keeps the
role word and status badge; the lead strip is at least 2 lines tall.
"""

FULL = (150, 40)
COMPACT = (80, 20)
NARROW = (60, 16)
SMALL = (40, 12)
SIDEBAR_W = 24
FETCH_H = 11
MIN_PANE_W = 26   # "reviewer · blocked" (18) fits a box title (w - 6) with no cut
MIN_PANE_H = 4
BTOP_MIN_W = 25   # btop's PID + NAME (13, the longest cast/process name) + CPU% fit whole
LEAD_STRIP_H = 4  # border + 2 lines (more on taller terminals: a fifth of the body)
COMPACT_LEAD_H = 5   # compact: 3 inner rows, so a message egg (the Epstein lines) wraps to 3 rows when the strip is narrow
FETCH_MIN_COLS = 140


def size_class(w, h):
    if w >= FULL[0] and h >= FULL[1]:
        return "full"
    if w >= COMPACT[0] and h >= COMPACT[1]:
        return "compact"
    if w >= NARROW[0] and h >= NARROW[1]:
        return "narrow"
    if w >= SMALL[0] and h >= SMALL[1]:
        return "small"
    return "tiny"


SIDEBAR_MIN_W = 16   # marker, name, gap, 1-column badge: 12 cols for a name, so every first word is whole
SIDEBAR_INDEX_W = 23  # from here the sidebar rows carry the index numbers, like the Mac's


def sidebar_width(w, team_cols=2, rw=0):
    """compact only: what is left of w once team_cols x MIN_PANE_W and the right column (btop, rw) have
    their columns, between SIDEBAR_MIN_W and SIDEBAR_W (the Mac's 24)."""
    return max(SIDEBAR_MIN_W, min(SIDEBAR_W, w - team_cols * MIN_PANE_W - rw))


def R(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def _split(start, total, n):
    each = total // n
    return [(start + i * each, total - each * (n - 1) if i == n - 1 else each) for i in range(n)]


def _team_grid(rects, x0, cw, y0, gh, odd):
    """2x2 team (planner/builder over reviewer/qa), plus up to one oddball per row while every
    column keeps MIN_PANE_W."""
    odd = odd if cw // (2 + min(odd, 1)) >= MIN_PANE_W else 0
    top = ["planner", "builder"] + (["odd0"] if odd >= 1 else [])
    bot = ["reviewer", "qa"] + (["odd1"] if odd >= 2 else [])
    (ty, th), (my, mh) = _split(y0, gh, 2)
    for i, (x, ww) in enumerate(_split(x0, cw, len(top))):
        rects[top[i]] = R(x, ty, ww, th)
    for i, (x, ww) in enumerate(_split(x0, cw, len(bot))):
        rects[bot[i]] = R(x, my, ww, mh)


def _right_width(free, team_cols):
    """btop's width: a quarter of the free columns (BTOP_MIN_W..60) while the team keeps team_cols x
    MIN_PANE_W, else BTOP_MIN_W if that still leaves them, else 0 (no btop)."""
    rw = min(60, max(BTOP_MIN_W, free // 4))
    if free - rw < team_cols * MIN_PANE_W:
        rw = BTOP_MIN_W if free - BTOP_MIN_W >= team_cols * MIN_PANE_W else 0
    return rw


def _terminal_layout(cls, w, h, oddballs):
    rects = {"tabs": R(0, 0, w, 1), "status": R(0, h - 1, w, 1)}
    by, bh = 1, h - 2
    oddballs = max(0, min(2, oddballs))
    if cls == "compact":
        # the oddball pane first, then btop, then the sidebar's width (16..24)
        n = 3 if oddballs and w - SIDEBAR_MIN_W >= 3 * MIN_PANE_W else 2
        rw = _right_width(w - SIDEBAR_MIN_W, n)
        sx = sidebar_width(w, n, rw)
        rects["sidebar"] = R(0, by, sx, bh)
        lead_h = max(COMPACT_LEAD_H, bh // 4)
    else:
        # narrow: no sidebar; btop on the right while the team keeps 2 x MIN_PANE_W
        sx = 0
        rw = _right_width(w, 2)
        lead_h = max(LEAD_STRIP_H, bh // 5)
    cw = w - sx - rw
    _team_grid(rects, sx, cw, by, bh - lead_h, oddballs)
    rects["lead"] = R(sx, by + bh - lead_h, cw, lead_h)
    if rw:
        rx = w - rw
        if cls == "compact" and w >= FETCH_MIN_COLS and bh - FETCH_H >= 8:
            rects["fetch"] = R(rx, by, rw, FETCH_H)
            rects["btop"] = R(rx, by + FETCH_H, rw, bh - FETCH_H)
        else:
            rects["btop"] = R(rx, by, rw, bh)
    return {"cls": cls, "rects": rects, "rows": h}


def compute_layout(w, h, oddballs=0):
    cls = size_class(w, h)
    rects = {}
    if cls == "tiny":
        rects["lead"] = R(0, 0, w, h)
        return {"cls": cls, "rects": rects, "rows": h}
    if cls in ("compact", "narrow"):
        return _terminal_layout(cls, w, h, oddballs)
    rects["tabs"] = R(0, 0, w, 1)
    rects["status"] = R(0, h - 1, w, 1)
    by, bh = 1, h - 2
    if cls == "small":
        lw = (w * 3) // 5
        rects["btop"] = R(lw, by, w - lw, bh)
        (y1, h1), (y2, h2) = _split(by, bh, 2)
        rects["planner"] = R(0, y1, lw, h1)
        rects["builder"] = R(0, y2, lw, h2)
        return {"cls": cls, "rects": rects, "rows": h}
    # full: identical to web/src/layout.js
    sx = SIDEBAR_W
    rects["sidebar"] = R(0, by, SIDEBAR_W, bh)
    rw = min(60, max(42, (w - sx) // 3))
    rx = w - rw
    cw = rx - sx
    lead_h = max(6, bh // 4)
    grid_h = bh - lead_h
    (ty, th), (my, mh) = _split(by, grid_h, 2)
    odd = max(0, min(2, oddballs))
    top = ["planner", "builder"] + (["odd0"] if odd >= 1 else [])
    bot = ["reviewer", "qa"] + (["odd1"] if odd >= 2 else [])
    for i, (x, ww) in enumerate(_split(sx, cw, len(top))):
        rects[top[i]] = R(x, ty, ww, th)
    for i, (x, ww) in enumerate(_split(sx, cw, len(bot))):
        rects[bot[i]] = R(x, my, ww, mh)
    rects["lead"] = R(sx, by + grid_h, cw, lead_h)
    rects["fetch"] = R(rx, by, rw, FETCH_H)
    rects["btop"] = R(rx, by + FETCH_H, rw, bh - FETCH_H)
    return {"cls": cls, "rects": rects, "rows": h}
