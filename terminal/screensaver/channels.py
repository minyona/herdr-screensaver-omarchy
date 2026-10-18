"""Egg channels, formats, fit checks and wrapping; identical to web/src/channels.js."""
import re

from .prng import hash32
from .crew import hex7

CHANNELS_BY_PANE = {
    "lead": ["commit", "pr"], "planner": ["plan"], "builder": ["diff", "chatter"], "reviewer": ["review"],
    "qa": ["test", "chatter"], "log": ["ticker"], "message": ["message"], "fastfetch": ["fastfetch"], "btop": ["btop"], "any": ["toast"],
}
PANE_OF = {"commit": "lead", "plan": "planner", "diff": "builder", "review": "reviewer", "test": "qa", "message": "lead"}
PANE_MAX_ROWS = 3
FETCH_MAX_ROWS = 2
BTOP_PID_W = 6
LOGO_W = 9
TOAST_MIN_W = 24


def snake(t):
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def format_egg(channel, egg):
    text = egg["text"]
    if channel == "commit":
        return "commit %s %s" % (hex7(egg["id"]), text)
    if channel == "pr":
        return "PR #%d %s" % (100 + hash32(egg["id"]) % 900, text)
    if channel == "plan":
        return "- " + text
    if channel == "diff":
        return "+ " + text if text.startswith("#") or text.startswith("//") else "+ # " + text
    if channel == "test":
        return "test_%s PASSED" % snake(text)
    return text


def wrap(text, width):
    """Greedy word wrap; words longer than width are hard-split. At least one row."""
    if width <= 0:
        return [text]
    rows, cur = [], ""
    for word in text.split(" "):
        while len(word) > width:
            if cur:
                rows.append(cur)
                cur = ""
            rows.append(word[:width])
            word = word[width:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += " " + word
        else:
            rows.append(cur)
            cur = word
    rows.append(cur)
    return rows


def pane_text_width(r):
    return max(0, r["w"] - 3)


def fetch_text_width(r):
    return max(0, r["w"] - 2 - LOGO_W)


def btop_text_width(r):
    return max(0, r["w"] - 2 - BTOP_PID_W)


def ticker_width(cols, total):
    return max(0, cols - (len("found %d of %d" % (total, total)) + 4) - 9)


def fits(channel, text, layout, cols, total):
    r = layout["rects"]
    if channel in PANE_OF or channel == "chatter":
        return True
    if channel in ("ticker", "pr"):
        return "status" in r and len(text) <= ticker_width(cols, total)
    if channel == "fastfetch":
        return "fetch" in r and len(wrap(text, fetch_text_width(r["fetch"]))) <= FETCH_MAX_ROWS
    if channel == "btop":
        return "btop" in r and len(text) <= btop_text_width(r["btop"])
    if channel == "toast":
        return toast_layout(text, r, cols, layout["rows"], layout["cls"]) is not None
    return True


def toast_layout(text, rects, cols, rows, cls=None):
    """Where a toast goes: the lower half of btop, else the whole screen (shared with web/src/channels.js).
    Terminal-only classes (cls below "full") with a sidebar use the screen right of the sidebar instead,
    so a toast never covers the workspace list."""
    regions = []
    b = rects.get("btop")
    if b:
        top = b["h"] // 2
        regions.append({"x": b["x"] + 1, "y": b["y"] + top, "w": b["w"] - 2, "h": b["h"] - top - 1})
    sb = rects.get("sidebar")
    if cls not in (None, "full") and sb:
        regions.append({"x": sb["x"] + sb["w"], "y": 0, "w": cols - sb["x"] - sb["w"], "h": rows})
    else:
        regions.append({"x": 0, "y": 0, "w": cols, "h": rows})
    for reg in regions:
        for side, border in ((2, True), (1, True), (0, False)):
            tw = reg["w"] - 2 * side
            if tw < 4:
                continue
            lines = wrap(text, tw)
            h = len(lines) + (2 if border else 0)
            if h > reg["h"]:
                continue
            longest = max(len(l) for l in lines)
            w = min(reg["w"], max(longest + 2 * side, TOAST_MIN_W if border and side == 2 else 0))
            rect = {"x": reg["x"] + (reg["w"] - w) // 2, "y": reg["y"] + (reg["h"] - h) // 2, "w": w, "h": h}
            return {"rect": rect, "lines": lines, "border": border, "padX": side}
    return None


def pane_fits(text, rect, max_rows=PANE_MAX_ROWS):
    return bool(rect) and pane_text_width(rect) > 0 and len(wrap(text, pane_text_width(rect))) <= max_rows


# A 'message' egg (an agent messaging the lead pane) must fit the lead pane's inner rows too,
# so its first row (the speaker) is never scrolled out of a short lead strip.
def message_rows(rect):
    return min(PANE_MAX_ROWS, rect["h"] - 2)
