"""Frame composition onto a Grid. Port of drawFrame() in web/src/render.js."""
from .chrome import draw_tab_bar, draw_status_bar
from .sidebar import draw_sidebar
from .panes import draw_agent_pane
from .widgets import draw_fetch, draw_btop, draw_toast


def draw_frame(S, g, th):
    g.clear(th["bg"], th["fg"])
    rects = S.layout["rects"]
    ws = S.ws[S.focus]
    if "tabs" in rects:
        draw_tab_bar(S, g, rects["tabs"], th)
    if "sidebar" in rects:
        draw_sidebar(S, g, rects["sidebar"], th)
    for role in ("planner", "builder", "reviewer", "qa", "lead"):
        if role in rects:
            draw_agent_pane(S, g, rects[role], ws["byRole"][role], th)
    for i, a in enumerate(ws["oddballs"]):
        if "odd%d" % i in rects:
            draw_agent_pane(S, g, rects["odd%d" % i], a, th)
    if "fetch" in rects:
        draw_fetch(S, g, rects["fetch"], th)
    if "btop" in rects:
        draw_btop(S, g, rects["btop"], th)
    if "status" in rects:
        draw_status_bar(S, g, rects["status"], th)
    if S.toast:
        draw_toast(S, g, th)
