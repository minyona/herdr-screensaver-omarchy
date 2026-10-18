"""herdr chrome: tab bar, status bar, pane titles. Port of web/src/chrome.js."""
from .found import found_label
from .channels import ticker_width
from .clock import local_fields, hhmm
from .grid import fit

STATUS_COLOR = {"working": "warn", "idle": "muted", "blocked": "err", "done": "ok", "auto": "accent2"}
DOT = "●"
SEP = " · "
ELL = "…"


def pane_title(agent):
    parts = [agent["name"]]
    if agent["name"] != agent["role"] and agent["role"] != "oddball":
        parts.append(agent["role"])
    parts.append(agent["status"])
    if agent["suffix"]:
        parts.append(agent["suffix"])
    return SEP.join(parts)


def readable(S):
    """Terminal-only classes (below "full") cut text with fit(); "full" stays identical to the web."""
    return S.layout["cls"] != "full"


def pane_title_fit(agent, room):
    """A title for room columns that keeps the role word and the status: the suffix goes first,
    then the name is shortened, then dropped."""
    role = agent["role"] if agent["role"] != "oddball" else None
    name, status, suffix = agent["name"], agent["status"], agent["suffix"]
    keep = [p for p in (role if role != name else None, status) if p]
    for parts in ([name] + keep + ([suffix] if suffix else []), [name] + keep):
        t = SEP.join(parts)
        if len(t) <= room:
            return t
    tail = SEP.join(keep)
    left = room - len(SEP) - len(tail)
    short = fit(name, left) if (role is None or role != name) and left >= 1 else ""
    if short:  # an oddball's name stands in for its role word; a name that cannot keep a whole word is left out
        return short + SEP + tail
    return fit(tail, room)


def draw_tab_bar(S, g, r, th):
    ws = S.ws[S.focus]
    g.fill(r, " ", th["fg"], th["bg"])
    x = [r["x"]]

    def seg(text, fg, bg, bold):
        g.put(x[0], r["y"], text, fg, bg, bold)
        x[0] += len(text) + 1

    seg(" herdr ", th["bg"], th["accent"], True)
    name = ws["name"]
    wsk = " ws %d/%d " % (S.focus + 1, len(S.ws)) if S.layout["cls"] == "narrow" else ""
    agents = ws["cast"]
    named = sum(len(a["name"]) + 3 for a in agents)
    if readable(S):
        # " 1 lead  2 team " stay whole; the workspace name comes before the agent dots, and is left
        # out when not even its first word fits
        room = r["w"] - 8 - (len(wsk) + 1 if wsk else 0) - 18 - 2
        name = fit(name, room)
        # the agent names before the workspace name (the sidebar shows the focused workspace): the
        # name goes when keeping it would leave the agents as bare dots
        fixed = r["x"] + 8 + (len(wsk) + 1 if wsk else 0) + 18
        if name and r["x"] + r["w"] - named - 1 <= fixed + len(name) + 3 and r["x"] + r["w"] - named - 1 > fixed:
            name = ""
    if name:
        seg(" %s " % name, th["accent2"], th["bg"], True)
    if wsk:
        seg(wsk, th["muted"], th["bg"], False)
    seg(" 1 lead ", th["muted"], th["bg"], False)
    seg(" 2 team ", th["bg"], th["accent2"], True)
    with_names = r["x"] + r["w"] - named - 1 > x[0]
    dx = r["x"] + r["w"] - (named if with_names else 2 * len(agents)) - 1
    if dx <= x[0]:
        return
    for a in agents:
        g.put(dx, r["y"], DOT, th.get(STATUS_COLOR.get(a["status"]), th["muted"]))
        dx += 1
        if with_names:
            g.put(dx + 1, r["y"], a["name"], th["muted"])
            dx += len(a["name"]) + 2
        else:
            dx += 1


def ticker_text(S):
    t = S.t
    if S.ticker and t < S.ticker["until"]:
        n = max(0, (t - S.ticker["t0"]) // 30)
        return S.ticker["text"][:n], True
    ws = S.ws[S.focus]
    if "lead" not in S.layout["rects"]:
        lines = [l for l in ws["byRole"]["lead"]["lines"] if l.t0 <= t]
        if lines:
            return "lead> " + lines[-1].text, False
    # an oddball with no pane (no room for a third team column): its newest line, like "lead>" above
    said = [(l.t0, a["name"], l.text) for i, a in enumerate(ws["oddballs"]) if "odd%d" % i not in S.layout["rects"]
            for l in a["lines"] if l.t0 <= t]
    if said:
        _, who, text = max(said, key=lambda x: x[0])
        return "%s> %s" % (who, text), False
    return "%s%st%d%s" % (ws["repo"], SEP, ws["n"] or 1, ": " + ws["task"] if ws["task"] else ""), False


def fit_found_label(n, total, bump, room, whole_words=False):
    full = found_label(n, total, bump)
    if len(full) + 3 <= room:
        return full
    base = "found %d of %d" % (n + bump, total)
    if whole_words:
        return base
    tail = full[len(base):]
    left = room - 3 - len(base)
    return base + tail[:left - 1] + ELL if left > 1 else base


def draw_status_bar(S, g, r, th):
    g.fill(r, " ", th["fg"], th["bg"])
    clock = " %s " % hhmm(local_fields(S.now + S.t))
    right = r["x"] + r["w"] - len(clock)
    g.put(right, r["y"], clock, th["bg"], th["accent"], True)
    bump = 1 if S.t < S.effect_until else 0
    text, egg = ticker_text(S)
    # an egg in the ticker keeps the room its fit check counted on: the all-found tail gives way first
    keep = len(S.ticker["text"]) + 1 if egg else 0
    label = " %s " % fit_found_label(S.found.count(), S.found.total, bump, right - r["x"] - 1 - keep, readable(S))
    lx = right - len(label) - 1
    flash = S.t - S.last_found_at < 1500
    g.put(lx, r["y"], label, th["bg"] if flash else th["accent2"], th["accent2"] if flash else th["bg"], True)
    tw = min(ticker_width(S.cols, S.found.total), lx - r["x"] - 2)
    if tw > 0:
        shown = fit(text, tw) if readable(S) else text[:tw - 1] + ELL if len(text) > tw else text
        g.put(r["x"] + 1, r["y"], shown, th["warn"] if egg else th["muted"], None, egg)
