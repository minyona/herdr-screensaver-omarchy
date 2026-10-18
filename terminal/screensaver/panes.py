"""Agent panes. Port of web/src/panes.js."""
from .grid import inner, wrap_readable
from .channels import wrap
from .chrome import pane_title, pane_title_fit, readable, STATUS_COLOR

STYLES = {
    "text": ("fg", False), "dim": ("muted", False), "cmd": ("accent2", False), "head": ("accent", True),
    "add": ("ok", False), "del": ("err", False), "hunk": ("info", False), "warn": ("warn", False),
    "pass": ("ok", True), "fail": ("err", True), "egg": ("fg", True), "beat": ("accent2", True),
}


def shown_chars(l, t):
    return max(0, min(len(l.text), (t - l.t0) // l.ms)) if l.ms else len(l.text)


def draw_agent_pane(S, g, r, agent, th):
    working = agent["status"] == "working"
    easy = readable(S)
    title = pane_title_fit(agent, r["w"] - 6) if easy else pane_title(agent)
    g.box(r, title, th["accent"] if working else th["border"], th.get(STATUS_COLOR.get(agent["status"]), th["accent"]), True)
    ir = inner(r)
    width = ir["w"] - 1
    if width < 1 or ir["h"] < 1:
        return
    t = S.t
    picked = []
    for l in reversed(agent["lines"]):
        if len(picked) >= ir["h"]:
            break
        if l.t0 <= t:
            picked.append(l)
    picked.reverse()
    rows, typing = [], False
    for l in picked:
        n = shown_chars(l, t)
        if n < len(l.text):
            typing = True
        key, bold = STYLES.get(l.style, ("fg", False))
        for row in (wrap_readable if easy else wrap)(l.text[:n], width):
            rows.append((row, th[key], bold))
    shown = rows[-ir["h"]:]
    for i, (text, fg, bold) in enumerate(shown):
        g.put(ir["x"] + 1, ir["y"] + i, text, fg, None, bold)
    if typing and shown:
        cx = ir["x"] + 1 + len(shown[-1][0])
        if cx < ir["x"] + ir["w"]:
            g.put(cx, ir["y"] + len(shown) - 1, " ", th["fg"], th["fg"])
