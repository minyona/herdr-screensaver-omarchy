"""Storylines in 2 lanes; identical to web/src/storylines.js."""
from .workspaces import REQUIRED_ARCS, agent_for, set_status, type_lines

LANES = 2
ARC_TAIL_MS = 30000
COUNTER_BUG_MS = 2000


def init_storylines(S, include):
    active = set(w["id"] for w in S.ws)
    S.arcs = [s for s in S.content["storylines"] if s["workspace"] in active]
    first = []
    for sid in list(include.get("storylines") or []) + REQUIRED_ARCS:
        s = next((a for a in S.arcs if a["id"] == sid), None)
        if s is not None and s not in first:
            first.append(s)
    S.arc_queue = first + S.rng.shuffle([a for a in S.arcs if a not in first])
    S.schedule(20000 + S.rng.randint(40001), "lane", 0)
    S.schedule(90000 + S.rng.randint(60001), "lane", 1)


def lane_start(S, li):
    if not S.arcs:
        return
    if not S.arc_queue:
        S.arc_queue = S.rng.shuffle(list(S.arcs))
    busy = set(w["id"] for w in S.ws if w["arc"])
    i = next((k for k, a in enumerate(S.arc_queue) if a["workspace"] not in busy), -1)
    if i < 0:
        S.schedule(S.t + 30000, "lane", li)
        return
    arc = S.arc_queue.pop(i)
    wi = next(k for k, w in enumerate(S.ws) if w["id"] == arc["workspace"])
    S.ws[wi]["arc"] = arc["id"]
    S.ws[wi]["arcStart"] = S.t
    S.emit("arc", ws=arc["workspace"], id=arc["id"], status="start")
    for bi, b in enumerate(arc["beats"]):
        S.schedule(S.t + b["at"] * 1000, "beat", (wi, arc, bi))
    S.schedule(S.t + arc["beats"][-1]["at"] * 1000 + ARC_TAIL_MS, "arcEnd", (li, wi, arc))


def beat(S, data):
    wi, arc, bi = data
    ws, b = S.ws[wi], arc["beats"][bi]
    agent = agent_for(ws, b["role"])
    S.emit("beat", ws=ws["id"], id="%s#%d" % (arc["id"], bi), role=agent["role"] if agent else None, status=b.get("status") or None)
    if agent is None:
        return
    if b.get("text"):
        type_lines(agent, [(b["text"], "beat")], S.t, 0, 35)
    if b.get("title_suffix"):
        agent["suffix"] = b["title_suffix"]
    if b.get("status"):
        set_status(S, ws, agent, b["status"])
    if b.get("effect") == "counter_off_by_one":
        S.effect_until = S.t + COUNTER_BUG_MS
        S.emit("effect", ws=ws["id"], id=b["effect"])


def arc_end(S, data):
    li, wi, arc = data
    ws = S.ws[wi]
    for a in ws["cast"]:
        a["suffix"] = ""
    for a in ws["oddballs"]:
        set_status(S, ws, a, "idle")
    ws["arc"] = None
    S.emit("arc", ws=ws["id"], id=arc["id"], status="end")
    S.schedule(S.t + 30000 + S.rng.randint(90001), "lane", li)
