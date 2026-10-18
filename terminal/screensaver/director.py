"""The director: a 1:1 port of web/src/director.js. One deterministic, integer-only event loop
over virtual ms; same seed + clock + found-set => byte-identical trace JSONL (tests/parity)."""
import heapq
import json
import math

from .prng import Rng
from .clock import local_fields, when_matches, date_key
from .layout import compute_layout
from .channels import CHANNELS_BY_PANE, PANE_OF, format_egg, fits, pane_fits, message_rows, wrap, fetch_text_width
from .found import Found
from .workspaces import choose_active, crew_step, type_lines
from .storylines import init_storylines, lane_start, beat, arc_end

TIERS = ["common", "rare", "legendary"]
DHH_IDS = ["F1", "F2", "F3"]
REVEAL_DELAY_MS = 400
REVEAL_MS_PER_CHAR = 30
TOAST_HOLD_MS = 4000
TOAST_QUEUE_MAX = 3
SIDE_HOLD_MS = 20000
TICKER_HOLD_MS = 15000
MESSAGE_HOLD_MS = 6000  # a message egg stays whole in the lead pane this long after it is typed
FLIP_MIN_MS = 120000
FLIP_SPAN_MS = 170000
FLIP_HINT_MS = 1500
CREW_START_SPAN_MS = 60000
WARMUP_MS = 180000
DHH_FIRST_MS, DHH_SPAN_MS = 60000, 540000
TRACE_KEYS = ("t", "kind", "ws", "id", "channel", "role", "status")


def reveal_ms(text):
    return REVEAL_DELAY_MS + REVEAL_MS_PER_CHAR * len(text)


def js_round(x):
    """Math.round for the non-negative dt values we get."""
    return int(math.floor(x + 0.5))


def trace_line(e):
    return json.dumps(dict(zip(TRACE_KEYS, e)), separators=(",", ":"), ensure_ascii=False)


class State(object):
    pass


class Engine(object):
    def __init__(self, content, cols=160, rows=50, seed=1, now=0, found=(), egg_rate=5, include=None,
                 trace=True, theme=None, animate=True):
        include = include or {}
        S = self.state = State()
        S.content, S.cols, S.rows, S.now, S.t, S.seq, S.queue = content, cols, rows, now, 0, 0, []
        S.rng = Rng(seed)
        S.crng = Rng(seed ^ 0x5BD1E995)
        S.arng = Rng(seed ^ 0x27D4EB2F)
        S.trace = [] if trace else None
        S.theme_name = theme or content["default_theme"]
        S.egg_rate = egg_rate
        S.animate = animate

        def emit(kind, ws=None, id=None, channel=None, role=None, status=None):
            if S.trace is not None:
                S.trace.append((S.t, kind, ws, id, channel, role, status))

        def schedule(at, typ, data):
            heapq.heappush(S.queue, [at, S.seq, typ, data])
            S.seq += 1

        S.emit, S.schedule = emit, schedule

        S.eggs = {e["id"]: e for e in content["eggs"]}
        S.found = Found(found, [e["id"] for e in content["eggs"]])
        S.when_eggs = [e for e in content["eggs"] if e.get("when")]
        S.boosted = set()
        S.toast, S.toast_queue, S.ticker, S.fetch_egg, S.btop_egg = None, [], None, None, None
        S.pane_busy_until, S.effect_until, S.last_found_at, S.flips = 0, 0, -10 ** 9, 0

        S.ws = choose_active(S, content["workspaces"], content["storylines"], include)
        S.focus = S.rng.randint(len(S.ws))
        S.flip_target = None
        _relayout(S)
        _refill(S)
        _warm_up(S)
        if egg_rate > 0:
            S.schedule(5000 + S.rng.randint(_slot_interval(S)), "slot", None)
        S.schedule(DHH_FIRST_MS + S.rng.randint(DHH_SPAN_MS + 1) , "dhh", None)
        S.schedule(FLIP_MIN_MS + S.rng.randint(FLIP_SPAN_MS + 1) - FLIP_HINT_MS, "flipPre", None)
        init_storylines(S, include)

        a = S.arng
        S.anim = {"cores": [5 + a.float() * 55 for _ in range(8)], "mem": 5 + a.float() * 4,
                  "procs": [0.5 + a.float() * 20 for _ in range(12)], "history": [], "acc": 0}

    # -- public, like createEngine() --------------------------------------------------------
    @property
    def trace(self):
        return self.state.trace

    def update(self, dt):
        _update(self.state, dt)

    def draw(self, grid):
        from .render import draw_frame
        S = self.state
        th = S.content["themes"].get(S.theme_name) or S.content["themes"][S.content["default_theme"]]
        draw_frame(S, grid, getattr(S, "theme_override", None) or th)

    def resize(self, c, r):
        self.state.cols, self.state.rows = c, r
        _relayout(self.state)

    def found_count(self):
        return self.state.found.count()

    def on_found(self, cb):
        self.state.found.on_found(cb)

    def info(self):
        S = self.state
        return {"cols": S.cols, "rows": S.rows, "theme": S.theme_name, "ws": S.ws[S.focus]["id"],
                "found": S.found.count(), "total": S.found.total, "t": S.t}


def _warm_up(S):
    for wi in range(len(S.ws)):
        S.schedule(S.rng.randint(CREW_START_SPAN_MS), "crew", wi)
    trace = S.trace
    S.trace = None
    _update(S, WARMUP_MS, no_anim=True)
    S.trace = trace
    for ev in S.queue:
        ev[0] -= WARMUP_MS
    for w in S.ws:
        for a in w["cast"]:
            for l in a["lines"]:
                l.t0 -= WARMUP_MS
    S.t = 0
    for w in S.ws:
        S.emit("badge", ws=w["id"], status=w["badge"])
        for a in w["cast"]:
            S.emit("status", ws=w["id"], id=a["name"], role=a["role"], status=a["status"])


def _relayout(S):
    S.layout = compute_layout(S.cols, S.rows, len(S.ws[S.focus]["oddballs"]))


def _slot_interval(S):
    return max(1, int(math.floor(60000 / S.egg_rate)))


def _update(S, dt, no_anim=False):
    target = S.t + max(0, js_round(dt))
    q = S.queue
    while q and q[0][0] <= target:
        ev = heapq.heappop(q)
        S.t = ev[0]
        _dispatch(S, ev[2], ev[3])
    S.t = target
    if not no_anim and S.animate:
        _animate(S, dt)


def _dispatch(S, typ, data):
    if typ == "slot":
        _egg_slot(S)
        iv = _slot_interval(S)
        S.schedule(S.t + (iv * 3) // 4 + S.rng.randint(iv // 2 + 1), "slot", None)
    elif typ == "dhh":
        _dhh_slot(S)
    elif typ == "reveal":
        S.emit("shown", id=data)
        if S.found.add(data):
            S.last_found_at = S.t
            S.emit("found", id=data)
    elif typ == "toastEnd":
        S.toast = None
        if S.toast_queue:
            _show_toast(S, S.toast_queue.pop(0))
    elif typ == "flipPre":
        k = len(S.ws)
        arcs = [i for i, w in enumerate(S.ws) if i != S.focus and w["arc"]]
        S.flip_target = arcs[S.rng.randint(len(arcs))] if arcs else (S.focus + 1 + S.rng.randint(k - 1)) % k
        S.schedule(S.t + FLIP_HINT_MS, "flip", None)
    elif typ == "flip":
        if S.t < S.pane_busy_until:
            S.schedule(S.pane_busy_until + 250, "flip", None)
            return
        S.focus = S.flip_target
        S.flip_target = None
        S.flips += 1
        _relayout(S)
        S.emit("flip", ws=S.ws[S.focus]["id"])
        S.schedule(S.t + FLIP_MIN_MS + S.rng.randint(FLIP_SPAN_MS + 1) - FLIP_HINT_MS, "flipPre", None)
    elif typ == "crew":
        crew_step(S, data)
    elif typ == "lane":
        lane_start(S, data)
    elif typ == "beat":
        beat(S, data)
    elif typ == "arcEnd":
        arc_end(S, data)
    else:
        raise ValueError("unknown event %s" % typ)


# ---- egg bags -----------------------------------------------------------------------------
def _refill(S):
    S.bags = {}
    for tier in TIERS:
        ids = [e["id"] for e in S.content["eggs"] if e["tier"] == tier]
        S.bags[tier] = S.rng.shuffle([i for i in ids if not S.found.has(i)]) + S.rng.shuffle([i for i in ids if S.found.has(i)])
    S.emit("refill")


def _take_eligible(S, tier, f):
    bag = S.bags[tier]
    for i, eid in enumerate(bag):
        if when_matches(S.eggs[eid].get("when"), f):
            del bag[i]
            return S.eggs[eid]
    return None


def _draw(S, tier, f):
    order = [tier] + [x for x in TIERS if x != tier]
    for pass_ in range(2):
        for tr in order:
            e = _take_eligible(S, tr, f)
            if e:
                return e
        if pass_ == 0:
            _refill(S)
    return None


def _boost_pick(S, f):
    for e in S.when_eggs:
        if S.found.has(e["id"]) or not when_matches(e["when"], f):
            continue
        key = "%s@%s" % (e["id"], date_key(f))
        if key in S.boosted:
            continue
        bag = S.bags[e["tier"]]
        if e["id"] not in bag:
            continue
        S.boosted.add(key)
        bag.remove(e["id"])
        return e
    return None


def _egg_slot(S):
    f = local_fields(S.now + S.t)
    egg = _boost_pick(S, f)
    if egg is None:
        roll = S.rng.randint(1000)
        egg = _draw(S, "legendary" if roll < 15 else "rare" if roll < 75 else "common", f)
    if egg:
        _place(S, egg, False)


def _dhh_slot(S):
    in_bag = [i for i in DHH_IDS if i in S.bags["legendary"]]
    if not in_bag:
        return
    unfound = [i for i in in_bag if not S.found.has(i)]
    cand = unfound or in_bag
    eid = cand[S.rng.randint(len(cand))]
    S.bags["legendary"].remove(eid)
    _place(S, S.eggs[eid], True)


# ---- placement ----------------------------------------------------------------------------
def choose_channel(S, egg):
    opts = CHANNELS_BY_PANE[egg["pane"]]
    ch = opts[S.rng.randint(len(opts))] if len(opts) > 1 else opts[0]
    text = format_egg(ch, egg)
    role = PANE_OF.get(ch) or (egg["pane"] if ch == "chatter" else None)
    if role:
        rect = S.layout["rects"].get(role)
        if ch == "message":
            ok = pane_fits(text, rect, message_rows(rect) if rect else 0)
        else:
            ok = pane_fits(text, rect)
    else:
        ok = fits(ch, text, S.layout, S.cols, S.found.total)
    if not ok:
        ch, text = "toast", egg["text"]
        if not fits("toast", text, S.layout, S.cols, S.found.total):
            ch = None
    return ch, text, (role if role and ok else None)


def _place(S, egg, front):
    ch, text, role = choose_channel(S, egg)
    if ch is None:
        S.emit("drop", id=egg["id"])
        return
    ws = S.ws[S.focus]
    reveal = reveal_ms(text)
    t0 = S.t + REVEAL_DELAY_MS
    if ch == "toast":
        if S.toast:
            if front:
                S.toast_queue.insert(0, egg)
            elif len(S.toast_queue) < TOAST_QUEUE_MAX:
                S.toast_queue.append(egg)
            else:
                S.emit("drop", id=egg["id"], channel=ch)
            return
        _show_toast(S, egg)
        return
    S.emit("egg", ws=ws["id"], id=egg["id"], channel=ch, role=role)
    if role:
        type_lines(ws["byRole"][role], [(text, "egg")], t0, 0, REVEAL_MS_PER_CHAR)
        busy = S.t + reveal + (MESSAGE_HOLD_MS if ch == "message" else 0)
        if ch == "message":
            ws["byRole"][role]["hold_until"] = busy
        S.pane_busy_until = max(S.pane_busy_until, busy)
    elif ch in ("ticker", "pr"):
        S.ticker = {"text": text, "t0": t0, "until": S.t + reveal + TICKER_HOLD_MS}
    elif ch == "fastfetch":
        S.fetch_egg = {"rows": wrap(text, fetch_text_width(S.layout["rects"]["fetch"])), "t0": t0, "until": S.t + reveal + SIDE_HOLD_MS}
    elif ch == "btop":
        S.btop_egg = {"text": text, "t0": t0, "until": S.t + reveal + SIDE_HOLD_MS}
    S.schedule(S.t + reveal, "reveal", egg["id"])


def _show_toast(S, egg):
    reveal = reveal_ms(egg["text"])
    S.toast = {"egg": egg, "text": egg["text"], "t0": S.t + REVEAL_DELAY_MS, "until": S.t + reveal + TOAST_HOLD_MS}
    S.emit("egg", ws=S.ws[S.focus]["id"], id=egg["id"], channel="toast")
    S.schedule(S.t + reveal, "reveal", egg["id"])
    S.schedule(S.toast["until"], "toastEnd", None)


# ---- cosmetic animation (floats; not in the trace) ----------------------------------------
def _animate(S, dt):
    a, r = S.anim, S.arng
    k = min(1, dt / 50.0)

    def walk(v, step, lo, hi):
        return min(hi, max(lo, v + (r.float() * 2 - 1) * step))

    a["cores"] = [walk(v, 12 * k, 1, 99) for v in a["cores"]]
    a["mem"] = walk(a["mem"], 0.15 * k, 3, 14)
    a["procs"] = [walk(v, 3 * k, 0.1, 60) for v in a["procs"]]
    a["acc"] += dt
    while a["acc"] >= 500:
        a["acc"] -= 500
        a["history"].append(sum(a["cores"]) / len(a["cores"]))
        if len(a["history"]) > 256:
            a["history"].pop(0)
