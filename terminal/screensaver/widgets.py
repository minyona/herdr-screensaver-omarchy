"""fastfetch- and btop-like panes plus the egg toast. Port of web/src/widgets.js."""
from .grid import inner, fit
from .channels import LOGO_W, BTOP_PID_W, toast_layout
from .chrome import readable

LOGO = (" _   _ ", "| | | |", "| |_| |", "|  _  |", "| | | |", "|_| |_|")
SWATCH = ("accent", "accent2", "ok", "warn", "err", "info", "fg", "muted")
SPARK = " .:-=+*#"


def _uptime(ms):
    s = ms // 1000
    return "%dh %02dm %02ds" % (s // 3600, (s // 60) % 60, s % 60)


def _key_value(g, x, y, w, text, th, n=None, easy=False):
    n = len(text) if n is None else n
    shown = fit(text, w)[:n] if easy else text[:min(n, w)]
    i = text.find(": ")
    if 0 < i < 18:
        g.put(x, y, shown[:i + 1], th["accent"], None, True)
        g.put(x + i + 1, y, shown[i + 1:], th["fg"])
    else:
        g.put(x, y, shown, th["fg"])


def draw_fetch(S, g, r, th):
    g.box(r, "fastfetch", th["border"], th["accent"], False)
    ir = inner(r)
    if ir["w"] < 4 or ir["h"] < 1:
        return
    ws = S.ws[S.focus]
    for i, l in enumerate(LOGO[:ir["h"]]):
        g.put(ir["x"], ir["y"] + i, l, th["accent"], None, True)
    x = ir["x"] + LOGO_W
    w = ir["x"] + ir["w"] - x
    if w < 4:
        return
    pool = S.content["details"]["fastfetch"]
    k = S.t // 30000
    d1, d2 = pool[(2 * k) % len(pool)], pool[(2 * k + 1) % len(pool)]
    working = sum(1 for a in ws["cast"] if a["status"] == "working")
    rows = ["Workspace: %s" % ws["name"], "Uptime: %s" % _uptime(S.t), "Agents: %d (%d working)" % (len(ws["cast"]), working),
            "Theme: %s" % th["name"], "%s: %s" % (d1["key"], d1["value"]), "%s: %s" % (d2["key"], d2["value"])]
    egg = S.fetch_egg if S.fetch_egg and S.t < S.fetch_egg["until"] else None
    y = ir["y"]
    end = ir["y"] + ir["h"]
    title = "crew@%s" % ws["repo"]
    easy = readable(S)
    g.put(x, y, fit(title, w) if easy else title[:w], th["accent2"], None, True)
    g.put(x, y + 1, "-" * min(w, len(title)), th["muted"])
    y += 2
    info = rows[:len(rows) - len(egg["rows"])] if egg else rows
    for row in info:
        if y >= end:
            return
        _key_value(g, x, y, w, row, th, None, easy)
        y += 1
    if egg:
        n = max(0, (S.t - egg["t0"]) // 30)
        for row in egg["rows"]:
            if y >= end:
                return
            _key_value(g, x, y, w, row, th, n)
            y += 1
            n = max(0, n - len(row) - 1)
    if y < end:
        for i, key in enumerate(SWATCH):
            if x + 3 * i + 3 <= ir["x"] + ir["w"]:
                g.put(x + 3 * i, y, "   ", th[key], th[key])


def _level(th, p):
    return th["ok"] if p < 50 else th["warn"] if p < 80 else th["err"]


def _bar(g, x, y, w, label, pct, th, suffix):
    g.put(x, y, label, th["accent"], None, True)
    bx, bw = x + len(label) + 1, w - len(label) - 3 - len(suffix) - 1
    if bw < 3:
        return
    n = int(round(bw * pct / 100.0))
    g.put(bx, y, "[", th["muted"])
    g.put(bx + 1, y, "|" * n, _level(th, pct))
    g.put(bx + 1 + bw, y, "]", th["muted"])
    g.put(bx + bw + 3, y, suffix, th["fg"])


def btop_columns(w, nw):
    """Readable btop table: which of pid/cpu/cmd fit next to a NAME column nw wide (always shown).
    PID 4, CPU% 4, CMD needs 6 or more; dropped in the order CMD, CPU%, PID."""
    if 4 + 1 + nw + 1 + 4 + 1 + 6 <= w:
        return ("pid", "cpu", "cmd")
    if 4 + 1 + nw + 1 + 4 <= w:
        return ("pid", "cpu")
    if 4 + 1 + nw <= w:
        return ("pid",)
    return ()


def draw_btop(S, g, r, th):
    g.box(r, "btop", th["border"], th["accent"], False)
    ir = inner(r)
    if ir["w"] < 12 or ir["h"] < 1:
        return
    a, x, w = S.anim, ir["x"], ir["w"]
    y, end = ir["y"], ir["y"] + ir["h"]
    cpu = sum(a["cores"]) / len(a["cores"])
    _bar(g, x, y, w, "CPU", cpu, th, "%3d%%" % round(cpu))
    y += 1
    cols = 2 if w >= 40 else 1
    cw = w // cols
    row = 0
    while row < -(-8 // cols) and y < end - 1:
        for c in range(cols):
            i = row * cols + c
            _bar(g, x + c * cw, y, cw - 1, "c%d" % i, a["cores"][i], th, "%3d%%" % round(a["cores"][i]))
        row += 1
        y += 1
    if y < end:
        line = "".join(SPARK[min(len(SPARK) - 1, int(v * len(SPARK) // 100))] for v in a["history"][-w:])
        g.put(x + w - len(line), y, line, th["info"])
        y += 1
    if y < end:
        _bar(g, x, y, w, "Mem", a["mem"] / 16 * 100, th, "%.1fG/16G" % a["mem"])
        y += 1
    y += 1
    if y >= end:
        return
    easy = readable(S)
    ws = S.ws[S.focus]
    procs = [p if isinstance(p, str) else p["text"] for p in S.content["details"]["processes"]]
    names = [c["name"] for c in ws["cast"]] + procs
    if easy:
        # readable: NAME is as wide as the longest name shown and is never cut; when the room runs out
        # the other columns go, in this order: CMD, CPU%, PID
        nw = max(len(n) for n in names[:max(0, end - y - 1)] or ["NAME"])
        nw = max(nw, 4)
        cols = btop_columns(w, nw)
        head = " ".join([c for c, on in (("PID ", "pid" in cols), ("NAME".ljust(nw), True), ("CPU%", "cpu" in cols), ("CMD", "cmd" in cols)) if on])
    else:
        nw = 12
        head = "  PID NAME         CPU% CMD"
    g.put(x, y, head[:w], th["muted"], None, True)
    y += 1
    egg = S.btop_egg if S.btop_egg and S.t < S.btop_egg["until"] else None
    for i, name in enumerate(names):
        if y >= end:
            break
        pid = "%5d" % (1101 + i * 7)
        if egg and i == 2:
            n = max(0, (S.t - egg["t0"]) // 30)
            g.put(x, y, pid, th["muted"])
            g.put(x + BTOP_PID_W, y, egg["text"][:min(n, w - BTOP_PID_W)], th["warn"], None, True)
            y += 1
            continue
        agent = ws["cast"][i] if i < len(ws["cast"]) else None
        cmd = "herdr agent %s %s" % ("run" if agent["status"] == "working" else "wait", agent["name"]) if agent else "%s --serve" % name
        cpu = "%5.1f" % a["procs"][i % len(a["procs"])]
        if easy:
            parts = (["%4d" % (1101 + i * 7)] if "pid" in cols else []) + [name.ljust(nw)] + (["%4.1f" % a["procs"][i % len(a["procs"])]] if "cpu" in cols else [])
            row_text = " ".join(parts)
            if "cmd" in cols:
                row_text += " " + fit(cmd, w - len(row_text) - 1)
        else:
            row_text = "%s %s %s %s" % (pid, name[:12].ljust(12), cpu, cmd)
        g.put(x, y, row_text if easy else row_text[:w], th["fg"] if agent and agent["status"] == "working" else th["muted"])
        y += 1


def draw_toast(S, g, th):
    T = S.toast
    if not T:
        return
    L = toast_layout(T["text"], S.layout["rects"], g.w, g.h, S.layout["cls"])
    if not L:
        return
    rect, lines, border, pad = L["rect"], L["lines"], L["border"], L["padX"]
    g.fill(rect, " ", th["fg"], th["bg"])
    if border:
        label = T["egg"]["category_label"]
        g.box(rect, fit(label, rect["w"] - 6) if readable(S) else label, th["accent2"], th["accent"], True)
    n = max(0, (S.t - T["t0"]) // 30)
    for i, l in enumerate(lines):
        g.put(rect["x"] + pad, rect["y"] + (1 if border else 0) + i, l[:n], th["warn"], None, True)
        n = max(0, n - len(l) - 1)
