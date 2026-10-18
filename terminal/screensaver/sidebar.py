"""Workspace sidebar with herdr-style badges. Port of web/src/sidebar.js."""
from .workspaces import BADGES

# compact (readable) sidebar: every badge is 1 column, so a name always gets 12 of the 15 columns;
# "auto" becomes » and the footer explains it (the full sidebar, shared with the web, keeps "auto")
NARROW_BADGES = dict(BADGES, auto="»")
from .chrome import STATUS_COLOR, readable
from .grid import fit
from .layout import SIDEBAR_INDEX_W


def draw_sidebar(S, g, r, th):
    g.fill(r, " ", th["fg"], th["bg"])
    for y in range(r["y"], r["y"] + r["h"]):
        g.put(r["x"] + r["w"] - 1, y, "│", th["border"])
    w = r["w"] - 1
    g.put(r["x"] + 1, r["y"], "WORKSPACES", th["muted"], None, True)
    for i, ws in enumerate(S.ws):
        y = r["y"] + 2 + i
        if y >= r["y"] + r["h"] - 2:
            continue
        focused, target = i == S.focus, i == S.flip_target
        badge = (NARROW_BADGES if readable(S) else BADGES)[ws["badge"]]
        bg = th["border"] if focused else th["bg"]
        g.fill({"x": r["x"], "y": y, "w": w, "h": 1}, " ", th["fg"], bg)
        g.put(r["x"], y, "›" if target else "▌" if focused else " ", th["accent"], bg, True)
        if readable(S):
            # compact sidebar: marker, [index,] name, a gap, the badge against the border; names cut whole-word.
            # The index numbers (like the Mac's) from SIDEBAR_INDEX_W cols; below that every first word fits
            nx = 4 if r["w"] >= SIDEBAR_INDEX_W else 1
            if nx > 1:
                g.put(r["x"] + 1, y, "%2d" % (i + 1), th["muted"], bg)
            name = fit(ws["name"], w - nx - 1 - len(badge))
            g.put(r["x"] + nx, y, name, th["fg"] if focused else th["muted"], bg, focused)
            g.put(r["x"] + w - len(badge), y, badge, th.get(STATUS_COLOR.get(ws["badge"]), th["muted"]), bg, True)
            continue
        idx = "%2d" % (i + 1)
        room = w - 4 - 1 - len(badge) - 1
        name = ws["name"][:room - 1] + "…" if len(ws["name"]) > room else ws["name"]
        g.put(r["x"] + 1, y, idx, th["muted"], bg)
        g.put(r["x"] + 4, y, name, th["fg"] if focused else th["muted"], bg, focused)
        g.put(r["x"] + w - len(badge) - 1, y, badge, th.get(STATUS_COLOR.get(ws["badge"]), th["muted"]), bg, True)
    blocked = sum(1 for x in S.ws if x["badge"] == "blocked")
    done = sum(1 for x in S.ws if x["badge"] == "done")
    foot = "%d spaces %d! %d✓" % (len(S.ws), blocked, done)
    if readable(S):
        # the shortest form that fits whole
        forms = (foot, "%d ws %d! %d✓" % (len(S.ws), blocked, done), "%d! %d✓" % (blocked, done))
        if any(x["badge"] == "auto" for x in S.ws):  # the legend for the 1-column auto mark
            forms = tuple(f + " »=auto" for f in forms) + ("»=auto %d! %d✓" % (blocked, done), "»=auto")
        for f in forms:
            if len(f) <= w - 1:
                foot = f
                break
        else:
            foot = ""
    g.put(r["x"] + 1, r["y"] + r["h"] - 1, foot[:w - 1], th["muted"])
