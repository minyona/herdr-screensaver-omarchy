"""Workspaces: active set, crew state machine, badges. Identical to web/src/workspaces.js."""
from . import crew

BADGES = {"working": "●", "idle": "○", "blocked": "!", "done": "✓", "auto": "auto"}
REQUIRED_ARCS = ["reviewer-rejects-everything", "off-the-rails", "qa-finds-screensaver-bug"]
MAX_LINES = 80


class Line(object):
    __slots__ = ("text", "style", "t0", "ms")

    def __init__(self, text, style, t0, ms):
        self.text, self.style, self.t0, self.ms = text, style, t0, ms


def agent_for(ws, key):
    for a in ws["cast"]:
        if a["name"] == key:
            return a
    for a in ws["cast"]:
        if a["role"] == key:
            return a
    return None


def make_workspace(src):
    cast = [{"name": a["name"], "role": a["role"], "kind": a["kind"], "quirk": a["quirk"],
             "status": "idle", "suffix": "", "lines": []} for a in src["cast"]]
    ws = {"id": src["id"], "name": src["name"], "repo": src["repo"], "tone": src["tone"], "tasks": src["tasks"],
          "cast": cast, "phase": "start", "n": 0, "fails": 0, "reviewFail": False, "justCommitted": False,
          "badge": "idle", "arc": None, "task": None}
    ws["byRole"] = {a["role"]: a for a in cast if a["role"] != "oddball"}
    ws["oddballs"] = [a for a in cast if a["role"] == "oddball"]
    for a in cast:
        for text, style in crew.banner(a):
            a["lines"].append(Line(text, style, 0, 0))
    return ws


def choose_active(S, all_ws, storylines, include):
    by_id = {w["id"]: w for w in all_ws}
    forced = []
    want = list(include.get("workspaces") or [])
    for rid in REQUIRED_ARCS:
        s = next((s for s in storylines if s["id"] == rid), None)
        if s and s.get("workspace"):
            want.append(s["workspace"])
    for wid in want:
        if wid in by_id and wid not in forced:
            forced.append(wid)
    k = min(len(all_ws), max(len(forced), 12 + S.rng.randint(5)))
    rest = S.rng.shuffle([w["id"] for w in all_ws if w["id"] not in forced])
    ids = S.rng.shuffle((forced + rest)[:k])
    return [make_workspace(by_id[i]) for i in ids]


def compute_badge(ws):
    st = [a["status"] for a in ws["cast"]]
    if "blocked" in st:
        return "blocked"
    if "auto" in st:
        return "auto"
    if "working" in st:
        return "working"
    if ws["justCommitted"]:
        return "done"
    return "idle"


def set_status(S, ws, agent, status):
    if agent is None or agent["status"] == status:
        return
    agent["status"] = status
    S.emit("status", ws=ws["id"], id=agent["name"], role=agent["role"], status=status)
    update_badge(S, ws)


def update_badge(S, ws):
    b = compute_badge(ws)
    if b != ws["badge"]:
        ws["badge"] = b
        S.emit("badge", ws=ws["id"], status=b)


def type_lines(agent, lines, t, dur, ms_per_char=0):
    n = len(lines)
    # a 'message' egg holds this pane (agent["hold_until"], set by the director): crew and beat lines
    # wait until it has been on screen a while, so they never scroll it out. Egg lines are never delayed.
    hold = max(0, agent.get("hold_until", 0) - t)
    for i, (text, style) in enumerate(lines):
        t0 = t + (i * dur) // (n + 1) + (0 if style == "egg" else hold)
        slot = max(200, dur // (n + 1))
        ms = ms_per_char or max(4, min(40, int((slot * 0.7) // max(1, len(text)))))
        agent["lines"].append(Line(text, style, t0, ms))
    if len(agent["lines"]) > MAX_LINES:
        del agent["lines"][:len(agent["lines"]) - MAX_LINES]


def _between(S, lo, hi):
    return lo + S.rng.randint(hi - lo + 1)


def _texts(pool):
    return [x if isinstance(x, str) else x["text"] for x in pool]


def crew_step(S, wi):
    ws = S.ws[wi]
    br = ws["byRole"]
    lead, planner, builder, reviewer, qa = br["lead"], br["planner"], br["builder"], br["reviewer"], br["qa"]
    t, c, d = S.t, S.crng, S.content["details"]

    def nxt(phase, dt):
        ws["phase"] = phase
        S.schedule(t + dt, "crew", wi)

    def dispatch():
        return _between(S, 3000, 8000)

    def work(agent, lo, hi, lines, phase):
        dur = _between(S, lo, hi)
        set_status(S, ws, lead, "idle")
        set_status(S, ws, agent, "working")
        type_lines(agent, lines, t, dur)
        nxt(phase, dur)

    ph = ws["phase"]
    if ph == "start":
        ws["n"] += 1
        ws["fails"] = 0
        ws["justCommitted"] = False
        ws["task"] = ws["tasks"][(ws["n"] - 1) % len(ws["tasks"])]
        dur = dispatch()
        set_status(S, ws, lead, "working")
        update_badge(S, ws)
        type_lines(lead, crew.lead_prompt(planner["name"], ws["n"], "plan", ws["task"]), t, dur)
        nxt("plan", dur)
    elif ph == "plan":
        work(planner, 20000, 60000, crew.plan(c, ws, ws["n"], ws["task"]), "planDone")
    elif ph == "planDone":
        set_status(S, ws, planner, "done")
        dur = dispatch()
        set_status(S, ws, lead, "working")
        type_lines(lead, crew.lead_wake(planner["name"], ws["n"]) + crew.lead_prompt(builder["name"], ws["n"], "implement"), t, dur)
        nxt("build", dur)
    elif ph == "build":
        work(builder, 30000, 90000, crew.build(c, ws, ws["n"]), "buildDone")
    elif ph == "rework":
        work(builder, 15000, 45000, crew.rework(c, ws, ws["n"]), "buildDone")
    elif ph == "buildDone":
        set_status(S, ws, builder, "done")
        dur = dispatch()
        set_status(S, ws, lead, "working")
        type_lines(lead, crew.lead_wake(builder["name"], ws["n"]) + crew.lead_prompt(reviewer["name"], ws["n"], "review"), t, dur)
        nxt("review", dur)
    elif ph == "review":
        # short-circuit exactly like JS: no draw once two FAILs happened
        ws["reviewFail"] = ws["fails"] < 2 and S.rng.randint(100) < 25
        work(reviewer, 15000, 40000, crew.review(c, ws, ws["n"], ws["reviewFail"]), "reviewDone")
    elif ph == "reviewDone":
        dur = dispatch()
        if ws["reviewFail"]:
            ws["fails"] += 1
            set_status(S, ws, reviewer, "blocked")
            set_status(S, ws, lead, "working")
            type_lines(lead, crew.lead_wake(reviewer["name"], ws["n"], "VERDICT: FAIL")
                       + crew.lead_prompt(builder["name"], ws["n"], "fix review findings for"), t, dur)
            nxt("rework", dur)
        else:
            set_status(S, ws, reviewer, "done")
            set_status(S, ws, lead, "working")
            type_lines(lead, crew.lead_wake(reviewer["name"], ws["n"], "VERDICT: PASS")
                       + crew.lead_prompt(qa["name"], ws["n"], "test"), t, dur)
            nxt("qa", dur)
    elif ph == "qa":
        work(qa, 15000, 40000, crew.qa(c, ws, ws["n"], _texts(d["test_names"])), "qaDone")
    elif ph == "qaDone":
        set_status(S, ws, qa, "done")
        dur = _between(S, 3000, 6000)
        set_status(S, ws, lead, "working")
        type_lines(lead, crew.lead_wake(qa["name"], ws["n"], "QA: PASS") + crew.commit(c, ws, ws["n"], _texts(d["commits"])), t, dur)
        nxt("commit", dur)
    elif ph == "commit":
        ws["justCommitted"] = True
        set_status(S, ws, lead, "done")
        for a in (planner, builder, reviewer, qa):
            set_status(S, ws, a, "idle")
        update_badge(S, ws)
        nxt("rest", _between(S, 20000, 90000))
    elif ph == "rest":
        if S.rng.randint(3) == 0:
            ws["justCommitted"] = False
            set_status(S, ws, lead, "idle")
            update_badge(S, ws)
            nxt("start", _between(S, 30000, 120000))
        else:
            nxt("start", 1000)
    else:
        raise ValueError("unknown crew phase %s" % ph)
