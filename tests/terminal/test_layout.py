"""L1: terminal size classes and readability (Michael's 8:41 bar: at exactly 100x22 the sidebar and
all five agents are fully readable). Run: python3 -m unittest discover -s tests/terminal"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TERMINAL = os.path.join(ROOT, "terminal")
sys.path.insert(0, TERMINAL)

from screensaver import content as content_mod  # noqa: E402
from screensaver.channels import toast_layout  # noqa: E402
from screensaver.chrome import pane_title, pane_title_fit, SEP  # noqa: E402
from screensaver.clock import parse_now  # noqa: E402
from screensaver.director import Engine  # noqa: E402
from screensaver.grid import Grid, fit, wrap_readable, BREAKS, ELL  # noqa: E402
from screensaver.sidebar import draw_sidebar, NARROW_BADGES  # noqa: E402
from screensaver.layout import compute_layout, size_class, MIN_PANE_W, MIN_PANE_H, SIDEBAR_INDEX_W  # noqa: E402
from screensaver.workspaces import BADGES  # noqa: E402

C = content_mod.load()
AGENTS = ("lead", "planner", "builder", "reviewer", "qa")
TEAM = ("planner", "builder", "reviewer", "qa")
SEEDS = ((1, "2026-10-16T09:00"), (7, "2026-10-16T13:00"), (42, "2026-10-16T03:00"), (1337, "2026-10-16T17:30"), (2026, "2026-12-24T23:30"))


def overlaps(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


# Short forms a label may use instead of the strict rule, by source name. Intentionally empty:
# no initials, no hard cuts anywhere (d-n-a-w for definitely-not-a-wrapper is a failure).
INTENTIONAL_SHORT = {}


def whole_word_cut(shown, source):
    """shown is source, or a prefix of it that ends at a word boundary followed by "…", or an
    intentionally listed short form. A cut inside a word, initials, a shortened label without "…"
    (now-you-have for now-you-have-two-problems) and an empty label are failures."""
    if not shown:
        return False
    if shown == source or shown in INTENTIONAL_SHORT.get(source, ()):
        return True
    if not shown.endswith(ELL):
        return False
    head = shown[:-1]
    return bool(head) and source.startswith(head) and len(head) < len(source) and source[len(head)] in BREAKS and head[-1] not in BREAKS


def first_word(name):
    for i, c in enumerate(name):
        if c in BREAKS and i:
            return name[:i]
    return name


class Classes(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(size_class(100, 22), "compact")
        self.assertEqual(size_class(99, 22), "compact")
        self.assertEqual(size_class(100, 21), "compact")
        self.assertEqual(size_class(80, 20), "compact")
        self.assertEqual(size_class(79, 20), "narrow")
        self.assertEqual(size_class(80, 19), "narrow")
        self.assertEqual(size_class(60, 16), "narrow")
        self.assertEqual(size_class(59, 16), "small")
        self.assertEqual(size_class(40, 12), "small")
        self.assertEqual(size_class(39, 12), "tiny")
        self.assertEqual(size_class(150, 40), "full")

    def test_geometry_every_size(self):
        for w in range(20, 301):
            for h in range(8, 91):
                for o in range(3):
                    L = compute_layout(w, h, o)
                    cls, rs = L["cls"], L["rects"]
                    items = list(rs.items())
                    for k, r in items:
                        self.assertTrue(r["w"] >= 1 and r["h"] >= 1 and r["x"] >= 0 and r["y"] >= 0 and r["x"] + r["w"] <= w and r["y"] + r["h"] <= h, (w, h, o, k))
                    for i in range(len(items)):
                        for j in range(i + 1, len(items)):
                            self.assertFalse(overlaps(items[i][1], items[j][1]), (w, h, o, items[i][0], items[j][0]))
                    if cls in ("compact", "narrow"):
                        for k, r in items:
                            if k in TEAM or k.startswith("odd"):
                                self.assertTrue(r["w"] >= MIN_PANE_W and r["h"] >= MIN_PANE_H, (w, h, o, k, r))
                        self.assertGreaterEqual(rs["lead"]["h"], 4)
                    if w >= 80 and h >= 20:
                        for k in ("sidebar",) + AGENTS:
                            self.assertIn(k, rs, (w, h, o))
                        sw = rs["sidebar"]["w"]
                        if cls == "full":
                            self.assertEqual(sw, 24, (w, h, sw))
                        else:
                            # Fix 2 P1: the oddball pane first, then btop, then the sidebar grows (16..24)
                            self.assertTrue(16 <= sw <= 24, (w, h, o, sw))
                            right = [r["x"] + r["w"] for k, r in items if k not in ("tabs", "status", "sidebar")]
                            self.assertEqual(max(right), w, (w, h, o, "full width used"))
                            self.assertEqual(rs["lead"]["x"], sw, (w, h, o))
                            self.assertGreaterEqual(rs["lead"]["h"] - 2, 3, (w, h, o, "lead strip inner rows"))
                            if o and w - 16 >= 3 * MIN_PANE_W:
                                self.assertIn("odd0", rs, (w, h, o, "oddball pane when 16 + 3 x 26 fit"))
                            if o == 2 and "odd0" in rs:
                                self.assertIn("odd1", rs, (w, h, o))
                            if sw < 24:   # the sidebar only gives up columns to a pane or btop
                                self.assertEqual(sum(r["w"] for k, r in items if k in TEAM[:2] or k == "odd0") + rs.get("btop", {"w": 0})["w"] + sw, w, (w, h, o))
                                cols = 3 if "odd0" in rs else 2
                                self.assertEqual(w - sw - rs.get("btop", {"w": 0})["w"], cols * MIN_PANE_W, (w, h, o, "team at its minimum"))
                    elif w >= 60 and h >= 16:
                        self.assertEqual(cls, "narrow")
                        for k in AGENTS:
                            self.assertIn(k, rs, (w, h, o))
                        self.assertNotIn("sidebar", rs)
                    elif w >= 40 and h >= 12:
                        self.assertEqual(sorted(k for k in rs if k in AGENTS), ["builder", "planner"])  # team as tabs
                    else:
                        self.assertEqual(list(rs), ["lead"])

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "web")), "the web build (web/src/layout.js) is not part of the plugin")
    def test_full_is_identical_to_the_web_layout(self):
        sizes = [(w, h) for w in range(150, 301, 7) for h in range(40, 91, 5)] + [(150, 40), (160, 50), (300, 90)]
        js = subprocess.run(["node", "--input-type=module", "-e",
                             "import { computeLayout } from './web/src/layout.js';"
                             "const s = JSON.parse(process.argv[1]); const out = [];"
                             "for (const [w, h] of s) for (let o = 0; o <= 2; o++) out.push(computeLayout(w, h, o));"
                             "process.stdout.write(JSON.stringify(out));", json.dumps(sizes)],
                            cwd=ROOT, stdout=subprocess.PIPE, check=True).stdout
        py = [compute_layout(w, h, o) for w, h in sizes for o in range(3)]
        self.assertEqual(json.loads(js), json.loads(json.dumps(py)))


# X4 + Fix 2 P1: the sidebar map for laptop sizes; per (w, h): (class, sidebar width or 0, btop, fetch, oddball pane)
# for a workspace with 0 oddballs, then for one with 1 or 2 (the oddball pane first, then btop, then the sidebar)
_C, _N = "compact", "narrow"
SIDEBAR_MAP = {
    (120, 30): ((_C, 24, True, False, False), (_C, 16, True, False, True)),
    (100, 22): ((_C, 23, True, False, False), (_C, 22, False, False, True)),
    (96, 21): ((_C, 19, True, False, False), (_C, 18, False, False, True)),
    (93, 22): ((_C, 16, True, False, False), (_C, 16, True, False, False)),
    (92, 22): ((_C, 24, False, False, False),) * 2, (90, 24): ((_C, 24, False, False, False),) * 2,
    (90, 20): ((_C, 24, False, False, False),) * 2, (84, 24): ((_C, 24, False, False, False),) * 2,
    (83, 24): ((_C, 24, False, False, False),) * 2, (83, 23): ((_C, 24, False, False, False),) * 2,
    (80, 24): ((_C, 24, False, False, False),) * 2, (80, 23): ((_C, 24, False, False, False),) * 2,
    (80, 22): ((_C, 24, False, False, False),) * 2, (80, 20): ((_C, 24, False, False, False),) * 2,
    (79, 23): ((_N, 0, True, False, False),) * 2, (79, 20): ((_N, 0, True, False, False),) * 2,
    (80, 19): ((_N, 0, True, False, False),) * 2, (70, 20): ((_N, 0, False, False, False),) * 2,
}


class SidebarMap(unittest.TestCase):
    def test_every_size_in_the_map(self):
        for (w, h), expect in sorted(SIDEBAR_MAP.items()):
            for o in range(3):
                cls, sw, btop, fetch, odd = expect[min(o, 1)]
                L = compute_layout(w, h, o)
                rs = L["rects"]
                where = (w, h, o)
                self.assertEqual(L["cls"], cls, where)
                self.assertEqual(rs["sidebar"]["w"] if "sidebar" in rs else 0, sw, where)
                for k in AGENTS:
                    self.assertIn(k, rs, where)
                self.assertEqual("btop" in rs, btop, where)
                self.assertEqual("fetch" in rs, fetch, where)
                self.assertEqual("odd0" in rs, odd, where)
                self.assertEqual("odd1" in rs, odd and o == 2, where)
                items = list(rs.items())
                for k, r in items:
                    self.assertTrue(r["x"] >= 0 and r["y"] >= 0 and r["x"] + r["w"] <= w and r["y"] + r["h"] <= h, (where, k))
                    if k in TEAM or k.startswith("odd"):
                        self.assertTrue(r["w"] >= MIN_PANE_W and r["h"] >= MIN_PANE_H, (where, k, r))
                for i in range(len(items)):
                    for j in range(i + 1, len(items)):
                        self.assertFalse(overlaps(items[i][1], items[j][1]), (where, items[i][0], items[j][0]))

    def test_boundaries(self):
        self.assertEqual(size_class(80, 20), "compact")
        self.assertEqual(size_class(79, 20), "narrow")
        self.assertEqual(size_class(80, 19), "narrow")
        self.assertNotIn("btop", compute_layout(92, 22)["rects"])
        self.assertIn("btop", compute_layout(93, 22)["rects"])
        self.assertIn("sidebar", compute_layout(80, 20)["rects"])
        self.assertNotIn("sidebar", compute_layout(79, 20)["rects"])
        self.assertNotIn("sidebar", compute_layout(80, 19)["rects"])

    def test_compact_geometry(self):
        """Fix 2 P1 (reports/plan-fix2.md 2): exact rects at 100x22, 83x24 and 149x44 (x, y, w, h)."""
        def rects(w, h, o):
            return {k: (r["x"], r["y"], r["w"], r["h"]) for k, r in compute_layout(w, h, o)["rects"].items() if k not in ("tabs", "status")}
        self.assertEqual(rects(100, 22, 0), {   # btop 25, sidebar 23 (index numbers), lead 5 rows (3 inner)
            "sidebar": (0, 1, 23, 20), "planner": (23, 1, 26, 7), "builder": (49, 1, 26, 7), "reviewer": (23, 8, 26, 8),
            "qa": (49, 8, 26, 8), "lead": (23, 16, 52, 5), "btop": (75, 1, 25, 20)})
        self.assertEqual(rects(100, 22, 1), {   # the oddball pane instead of btop (6 cols would be left), sidebar 22
            "sidebar": (0, 1, 22, 20), "planner": (22, 1, 26, 7), "builder": (48, 1, 26, 7), "odd0": (74, 1, 26, 7),
            "reviewer": (22, 8, 39, 8), "qa": (61, 8, 39, 8), "lead": (22, 16, 78, 5)})
        at83 = {"sidebar": (0, 1, 24, 22), "planner": (24, 1, 29, 8), "builder": (53, 1, 30, 8), "reviewer": (24, 9, 29, 9),
                "qa": (53, 9, 30, 9), "lead": (24, 18, 59, 5)}   # no btop, fetch or oddball: 83 - 16 - 2 x 26 = 15 < 25
        for o in range(3):
            self.assertEqual(rects(83, 24, o), at83, o)
        self.assertEqual(rects(149, 44, 1), {   # one col short of full: oddball, fetch, btop and the 24-col sidebar
            "sidebar": (0, 1, 24, 42), "planner": (24, 1, 30, 16), "builder": (54, 1, 30, 16), "odd0": (84, 1, 32, 16),
            "reviewer": (24, 17, 46, 16), "qa": (70, 17, 46, 16), "lead": (24, 33, 92, 10), "fetch": (116, 1, 33, 11),
            "btop": (116, 12, 33, 31)})

    def test_readability_sweep_every_size(self):
        """Michael's bar (check_frame) on every frame of 200 frames x 2 seeds at every map size, plus the
        sidebar (>= 10 workspace rows) or the tab bar's ws k/n."""
        for (w, h), expect in sorted(SIDEBAR_MAP.items()):
            for seed, now in (SEEDS[1], SEEDS[3]):
                e = Engine(C, cols=w, rows=h, seed=seed, now=parse_now(now), animate=True)
                for f in range(200):
                    e.update(3000)
                    g = Grid(w, h)
                    e.draw(g)
                    rows = g.plain().split("\n")
                    self.assertTrue(all(len(r) == w for r in rows[:h]), (w, h))
                    check_frame(self, e.state, g, (w, h, seed, f))
                    if f % 50:
                        continue
                    rs = e.state.layout["rects"]
                    sw = rs["sidebar"]["w"] if "sidebar" in rs else 0   # per workspace: its oddballs move it
                    self.assertEqual(sw, expect[min(len(e.state.ws[e.state.focus]["oddballs"]), 1)][1], (w, h, f))
                    if sw:
                        self.assertEqual(rows[1][1:11], "WORKSPACES", (w, h, f))
                        names = [r[1:15].strip() for r in rows[3:h - 3] if r[sw - 1] == "│" and r[1:14].strip()]
                        self.assertGreaterEqual(len(names), min(10, len(e.state.ws)), (w, h, f, names))
                        self.assertNotRegex(rows[0], r" ws \d+/\d+ ")
                    else:
                        self.assertNotIn("WORKSPACES", g.plain())
                        self.assertRegex(rows[0], r" ws \d+/\d+ ", (w, h, f))


class Fit(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(fit("rewrite-it-in-rust (day 412)", 8), "rewrite…")
        self.assertEqual(fit("p(doom)-mitigation", 8), "p(doom)…")
        self.assertEqual(fit("majestic-monolith-support-group", 8), "")  # "majestic" fills the room: no room for "…"
        self.assertEqual(fit("majestic-monolith-support-group", 9), "majestic…")
        self.assertEqual(fit("now-you-have-two-problems", 12), "now-you…")  # never shortened without "…"
        self.assertEqual(fit("definitely-not-a-wrapper", 8), "")  # never cut inside a word, never initials
        self.assertEqual(fit("distributed-monolith", 12), "distributed…")
        self.assertEqual(fit("definitely-not-a-wrapper", 12), "definitely…")
        # the reviewers' labels are failures for the checker: mid-word cuts and initials
        for bad, source in (("majesti…", "majestic-monolith-support-group"), ("definit…", "definitely-not-a-wrapper"),
                            ("distrib…", "distributed-monolith"), ("heisenb…", "heisenbug-hunting-season"),
                            ("d-n-a-w", "definitely-not-a-wrapper"), ("d-m", "distributed-monolith"), ("ele…", "eleven-lines"),
                            ("now-you-have", "now-you-have-two-problems"), ("10x-engineer", "10x-engineer-0x-readers")):
            self.assertFalse(whole_word_cut(bad, source), bad)
        self.assertEqual(fit("its-always-dns", 8), "its…")
        self.assertEqual(fit("short", 8), "short")
        self.assertEqual(fit("abc", 1), "")  # no whole word fits: nothing, never "a…"
        self.assertEqual(fit("abc", 0), "")
        for name in [ws["name"] for ws in C["workspaces"]]:
            for room in range(1, 40):
                f = fit(name, room)
                self.assertLessEqual(len(f), room, (name, room))
                self.assertTrue(f == "" or whole_word_cut(f, name), (name, room, f))
                self.assertEqual(bool(f), room >= len(name) or room >= len(first_word(name)) + 1, (name, room, f))

    def test_sidebar_all_35_names_every_badge_every_width(self):
        """Every workspace name in the catalog with EVERY badge (auto included) in the compact sidebar:
        at its real width (16, the only width compact uses) the first word is whole on every row and
        the auto mark is explained in the footer; at 12-15 (never used) still no mid-word cut and no
        initials (a label that cannot keep its first word is left out)."""
        class St(object):
            pass
        th = C["themes"]["tokyonight"]
        for sw in range(12, 17):
            for badge in BADGES:
                S = St()
                S.ws = [{"name": w["name"], "badge": badge} for w in C["workspaces"]]
                S.focus, S.flip_target = 0, 3
                S.layout = {"cls": "compact", "rects": {}}
                g = Grid(sw, len(S.ws) + 4)
                draw_sidebar(S, g, {"x": 0, "y": 0, "w": sw, "h": len(S.ws) + 4}, th)
                rows = g.plain().split("\n")
                b = NARROW_BADGES[badge]
                self.assertEqual(len(b), 1, badge)
                for i, w in enumerate(S.ws):
                    row = rows[2 + i][:sw - 1]
                    self.assertTrue(row.endswith(b), (sw, badge, row))
                    name = row[1:len(row) - len(b)].strip()
                    if sw == 16:
                        self.assertTrue(whole_word_cut(name, w["name"]), (sw, badge, name, w["name"]))
                        self.assertTrue(name.startswith(first_word(w["name"])), (sw, badge, name, w["name"]))
                    else:
                        self.assertTrue(name == "" or whole_word_cut(name, w["name"]), (sw, badge, name, w["name"]))
                foot = rows[len(S.ws) + 3].strip()
                if badge == "auto" and sw == 16:
                    self.assertIn("»=auto", foot)

    def test_wrap_readable(self):
        self.assertEqual(wrap_readable("a reports/builder-t1.md b", 10), ["a reports/", "builder-", "t1.md b"])
        self.assertEqual(wrap_readable("test_regex_finishes_eventually ... ok", 27), ["test_regex_finishes_", "eventually ... ok"])
        self.assertEqual(wrap_readable("-" * 40, 27), ["-" * 27])  # a rule line is trimmed, no "…"
        self.assertEqual(wrap_readable("zzzzzzzzzzzzzzzzzzzzzzzzzzzzz end", 10), ["zzzzzzzzz…", "end"])  # no break: cut
        self.assertEqual(wrap_readable("plan written: here", 13), ["plan written:", "here"])
        self.assertEqual(wrap_readable("x - y - z", 3), ["x -", "y -", "z"])
        # every row of every pane line in the content: whole words, or a long word's pieces split
        # after its own - / _, or (no break in it) cut with "…"
        lines = [b["text"] for sl in C["storylines"] for b in sl["beats"] if "text" in b] + [str(d if isinstance(d, str) else d.get("text", "")) for k in ("commits", "pr_titles", "test_names") for d in C["details"][k]]
        for t in lines:
            for width in (17, 24, 27, 37):
                rows = wrap_readable(t, width)
                self.assertTrue(all(len(r) <= width for r in rows), (t, width))
                joined = " ".join(rows)
                for word in t.split(" "):
                    if len(word) <= width:
                        self.assertIn(word, joined.split(" "), (t, width, word))
        for t in ["Plan t1: validate an email", "x" * 50, "a " * 30]:
            for w in range(2, 30):
                self.assertTrue(all(len(r) <= w for r in wrap_readable(t, w)), (t, w))

    def test_titles_keep_role_and_status(self):
        for ws in C["workspaces"]:
            for a in ws["cast"]:
                for status in ("idle", "working", "blocked", "done", "auto"):
                    agent = {"name": a["name"], "role": a["role"], "status": status, "suffix": "(day 412)"}
                    for room in range(20, 60):
                        t = pane_title_fit(agent, room)
                        self.assertLessEqual(len(t), room, (agent, room))
                        self.assertIn(status, t.split(SEP), (agent, room, t))
                        if a["role"] != "oddball":
                            self.assertIn(a["role"], t.split(SEP) + [a["name"]], (agent, room, t))


def check_frame(tc, S, g, where):
    """Michael's bar on one rendered frame: borders, titles, sidebar rows, tab and status bar."""
    rows = [g.plain().split("\n")[y] for y in range(g.h)]
    rs = S.layout["rects"]
    ws = S.ws[S.focus]
    cover = None
    if S.toast:
        L = toast_layout(S.toast["text"], rs, g.w, g.h, S.layout["cls"])
        cover = L["rect"] if L else None

    def hidden(x, y):
        return cover is not None and cover["x"] <= x < cover["x"] + cover["w"] and cover["y"] <= y < cover["y"] + cover["h"]

    def cell(x, y):
        return rows[y][x]

    for key in AGENTS + ("odd0", "odd1"):
        if key not in rs:
            continue
        r = rs[key]
        agent = ws["byRole"][key] if key in AGENTS else ws["oddballs"][int(key[3])]
        x0, y0, x1, y1 = r["x"], r["y"], r["x"] + r["w"] - 1, r["y"] + r["h"] - 1
        for (x, y), ch in (((x0, y0), "╭"), ((x1, y0), "╮"), ((x0, y1), "╰"), ((x1, y1), "╯")):
            if not hidden(x, y):
                tc.assertEqual(cell(x, y), ch, (where, key, "corner"))
        for x in range(x0 + 1, x1):
            if not hidden(x, y1):
                tc.assertEqual(cell(x, y1), "─", (where, key, "bottom edge"))
        for y in range(y0 + 1, y1):
            for x in (x0, x1):
                if not hidden(x, y):
                    tc.assertEqual(cell(x, y), "│", (where, key, "side edge"))
        title = pane_title_fit(agent, r["w"] - 6)
        if not any(hidden(x, y0) for x in range(x0, x1 + 1)):
            tc.assertEqual(rows[y0][x0 + 2:x0 + 4 + len(title)], " %s " % title, (where, key, "title drawn whole"))
            tc.assertTrue(set(rows[y0][x0 + 4 + len(title):x1]) <= {"─"}, (where, key, "top edge"))
        parts = title.split(SEP)
        tc.assertIn(agent["status"], parts, (where, key, title))
        if agent["role"] != "oddball":
            tc.assertTrue(agent["role"] in parts or (agent["name"] == agent["role"] and parts[0] == agent["role"]), (where, key, title))
        full = pane_title(agent).split(SEP)
        tc.assertTrue(all(p in full or whole_word_cut(p, agent["name"]) for p in parts), (where, key, title))
    if "sidebar" in rs:
        r = rs["sidebar"]
        for y in range(r["y"], r["y"] + r["h"]):
            if not hidden(r["x"] + r["w"] - 1, y):
                tc.assertEqual(cell(r["x"] + r["w"] - 1, y), "│", (where, "sidebar border"))
        shown = 0
        for i, w_ in enumerate(S.ws):
            y = r["y"] + 2 + i
            if y >= r["y"] + r["h"] - 2 or any(hidden(x, y) for x in range(r["x"], r["x"] + r["w"])):
                continue
            row = rows[y][r["x"]:r["x"] + r["w"] - 1].rstrip()
            badge = NARROW_BADGES[w_["badge"]]
            tc.assertTrue(row.endswith(badge), (where, "sidebar badge", row))
            nx = 1
            if r["w"] >= SIDEBAR_INDEX_W:   # Fix 2 P1: the Mac's index numbers
                tc.assertEqual(row[1:4], "%2d " % (i + 1), (where, "sidebar index", row))
                nx = 4
            name = row[nx:len(row) - len(badge)].strip()
            tc.assertTrue(whole_word_cut(name, w_["name"]), (where, "sidebar name", name, w_["name"]))
            shown += 1
        tc.assertGreaterEqual(shown, min(8, len(S.ws)) if r["h"] >= 12 else 1, (where, "sidebar rows"))
    if "tabs" in rs and not any(hidden(x, 0) for x in range(g.w)):
        tc.assertTrue(rows[0].startswith(" herdr "), (where, rows[0]))
        tc.assertIn(" 1 lead ", rows[0])
        tc.assertIn(" 2 team ", rows[0])
        name = rows[0][8:].split("   ")[0].strip()
        if not (name.startswith("ws ") or name == "1 lead"):  # else: left out, its first word did not fit
            tc.assertTrue(whole_word_cut(name, ws["name"]), (where, "tab ws name", name))
    if "btop" in rs:
        check_btop_names(tc, S, rows, rs["btop"], hidden, where)
    if "status" in rs and not any(hidden(x, g.h - 1) for x in range(g.w)):
        tc.assertRegex(rows[-1], r" found \d+ of %d " % S.found.total, where)


def check_btop_names(tc, S, rows, r, hidden, where):
    """Every row of btop's process table shows its whole name, never blank, never cut (QA)."""
    ws = S.ws[S.focus]
    procs = [p if isinstance(p, str) else p["text"] for p in S.content["details"]["processes"]]
    names = [c["name"] for c in ws["cast"]] + procs
    head = next((y for y in range(r["y"] + 1, r["y"] + r["h"] - 1) if " NAME" in rows[y][r["x"]:r["x"] + r["w"]] or rows[y][r["x"] + 1:].startswith("NAME")), None)
    if head is None:
        return
    egg = S.btop_egg if S.btop_egg and S.t < S.btop_egg["until"] else None
    for i, y in enumerate(range(head + 1, r["y"] + r["h"] - 1)):
        if egg and i == 2 or any(hidden(x, y) for x in range(r["x"], r["x"] + r["w"])):
            continue
        tokens = [t for t in rows[y][r["x"] + 1:r["x"] + r["w"] - 1].split() if not t.replace(".", "").isdigit()]
        tc.assertTrue(tokens, (where, "btop row has no NAME", rows[y][r["x"]:r["x"] + r["w"]]))
        tc.assertEqual(tokens[0], names[i], (where, "btop NAME", rows[y][r["x"]:r["x"] + r["w"]]))


class Btop(unittest.TestCase):
    def test_every_cast_name_whole_at_every_btop_width(self):
        """All 35 workspaces' cast names (and the process pool) in btop's table at every btop width and
        height the terminal-only layouts produce (compact, narrow, small): whole, never blank."""
        sizes = {}
        for w in range(40, 301):
            for h in (12, 16, 22, 24, 30, 39):
                L = compute_layout(w, h, 0)
                if L["cls"] != "full" and "btop" in L["rects"]:
                    b = L["rects"]["btop"]
                    sizes.setdefault((b["w"], b["h"]), (w, h))
        self.assertIn((25, 20), sizes)  # 100x22
        ids = [w["id"] for w in C["workspaces"]]
        for (bw, bh), (w, h) in sorted(sizes.items()):
            e = Engine(C, cols=w, rows=h, seed=3, now=parse_now("2026-10-16T13:00"), animate=False, include={"workspaces": ids})
            e.update(1000)
            S = e.state
            self.assertEqual(len(S.ws), 35)
            S.btop_egg = None
            r = S.layout["rects"]["btop"]
            for i in range(len(S.ws)):
                S.focus = i
                g = Grid(w, h)
                from screensaver.widgets import draw_btop
                draw_btop(S, g, r, C["themes"]["tokyonight"])
                check_btop_names(self, S, g.plain().split("\n"), r, lambda x, y: False, (w, h, S.ws[i]["name"]))


class Readability(unittest.TestCase):
    def sweep(self, w, h, frames, step_ms, seeds):
        for seed, now in seeds:
            e = Engine(C, cols=w, rows=h, seed=seed, now=parse_now(now), animate=True)
            for f in range(frames):
                e.update(step_ms)
                g = Grid(w, h)
                e.draw(g)
                for line in g.plain().split("\n")[:h]:
                    self.assertEqual(len(line), w)
                check_frame(self, e.state, g, (w, h, seed, f))

    def test_100x22_five_seeds_1000_frames(self):
        self.sweep(100, 22, 1000, 1000, SEEDS)

    def test_100x22_sixty_seeds_and_times(self):
        """QA: many seeds and times at exactly 100x22; every frame: no blank or cut btop NAME, no
        unmarked shortened label (check_frame)."""
        hours = ["00:01", "03:00", "09:00", "12:00", "13:00", "17:30", "21:00", "23:59"]
        days = ["2026-10-16", "2026-12-31", "2026-12-24", "2024-02-29", "2026-07-04"]
        pairs = [(s, "%sT%s" % (days[s % len(days)], hours[s % len(hours)])) for s in range(60)]
        for seed, now in pairs:
            e = Engine(C, cols=100, rows=22, seed=seed, now=parse_now(now), animate=True)
            for f in range(30):
                e.update(20000)
                g = Grid(100, 22)
                e.draw(g)
                check_frame(self, e.state, g, (seed, now, f))

    def test_qa_repro_seed5_craftsperson(self):
        """QA repro: seed 5, 2026-12-31T23:59, 400 frames at 50 ms: row 1115 showed no NAME (a 25-col btop).
        That workspace has an oddball, which (Fix 2 P1) takes btop's columns at 100x22; 93x22 keeps the
        same 25-col btop (16 + 3 x 26 do not fit there)."""
        for w, h in ((100, 22), (93, 22)):
            e = Engine(C, cols=w, rows=h, seed=5, now=parse_now("2026-12-31T23:59"), animate=False)
            for _ in range(399):
                e.update(50)
            e.state.animate = True
            e.update(50)
            g = Grid(w, h)
            e.draw(g)
            rs = e.state.layout["rects"]
            if w == 100:
                self.assertIn("odd0", rs)
                self.assertNotIn("btop", rs)
            else:
                self.assertEqual(rs["btop"]["w"], 25)
                row = [l for l in g.plain().split("\n") if "1115" in l][0]
                self.assertIn("1115 craftsperson", row)
            check_frame(self, e.state, g, ("qa repro", w, h))

    def test_other_terminal_sizes(self):
        for w, h in ((80, 24), (60, 16), (120, 36), (150, 30), (190, 36), (100, 39)):
            self.sweep(w, h, 200, 3000, SEEDS[:2])


class LiveFrames(unittest.TestCase):
    def frame(self, w, h, seed, now, steps, include=None):
        e = Engine(C, cols=w, rows=h, seed=seed, now=parse_now(now), animate=True, include=include)
        for _ in range(steps):
            e.update(1000)
        g = Grid(w, h)
        e.draw(g)
        return e.state, g

    def test_wrapper_pivot_auto_badge_at_100x22(self):
        """Reviewer L1b: seed 7, 2026-10-16T13:00, wrapper-pivot, frame 341 (t 342 s) had
        '▌d-n-a-w   auto│'. Now: 'definitely…', the 1-column auto mark and its legend."""
        S, g = self.frame(100, 22, 7, "2026-10-16T13:00", 342, {"workspaces": ["definitely-not-a-wrapper"], "storylines": ["wrapper-pivot"]})
        rows = g.plain().split("\n")
        i = [w["name"] for w in S.ws].index("definitely-not-a-wrapper")
        self.assertEqual(S.ws[i]["badge"], "auto")
        r = S.layout["rects"]["sidebar"]
        self.assertEqual(r["w"], 22)   # an oddball workspace: the oddball pane, then a 22-col sidebar (no index)
        row = rows[r["y"] + 2 + i][:r["w"] - 1]
        self.assertEqual(row[1:].rstrip(), "definitely-not-a…  »", row)
        self.assertNotIn("d-n-a-w", g.plain())
        self.assertIn("»=auto", rows[S.layout["rects"]["sidebar"]["y"] + S.layout["rects"]["sidebar"]["h"] - 1])
        check_frame(self, S, g, "wrapper-pivot frame 341")

    def test_eleven_lines_builder_title_at_100x22(self):
        """Seed 2026, 2026-12-24T23:30, frame 125: the builder title once read 'ele… · builder · working'."""
        S, g = self.frame(100, 22, 2026, "2026-12-24T23:30", 126)
        r = S.layout["rects"]["builder"]
        title = g.plain().split("\n")[r["y"]][r["x"] + 3:r["x"] + r["w"] - 1].split(" ─")[0].strip()
        parts = title.split(SEP)
        self.assertIn("builder", parts, title)
        name = S.ws[S.focus]["byRole"]["builder"]["name"]
        self.assertTrue(parts[0] in ("builder",) or whole_word_cut(parts[0], name), (title, name))
        check_frame(self, S, g, "eleven-lines frame 125")


class Dumps(unittest.TestCase):
    # Layout-only dumps: --egg-rate 0, so a toast (placed by whatever the shuffle-bag holds at frame
    # 400) never covers a title here. Eggs over the layout are checked by Readability (check_frame
    # skips cells under a toast) and tests/terminal/test_epstein.py.
    def dump(self, size):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, XDG_STATE_HOME=os.path.join(d, "state"))
            open(os.path.join(d, "found"), "w").close()
            return subprocess.run([os.path.join(TERMINAL, "bin", "herdr-screensaver"), "--frames", "400", "--seed", "7", "--now", "2026-10-16T13:00",
                                   "--size", size, "--found-file", os.path.join(d, "found"), "--egg-rate", "0", "--dump", "--plain"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=True).stdout.decode()

    def test_plain_dumps(self):
        for size in ("100x22", "80x24"):
            w, h = map(int, size.split("x"))
            text = self.dump(size)
            lines = text.rstrip("\n").split("\n")
            self.assertEqual(len(lines), h)
            self.assertTrue(all(len(l) == w for l in lines), size)
            for role in ("lead", "planner", "builder", "reviewer", "qa"):
                self.assertRegex(text, r"╭─ (\S+ · )?%s · " % role, (size, role))
            if size == "100x22":
                self.assertIn("WORKSPACES", text)
                sw = lines[2].index("│") + 1   # 23 here (no oddball): index numbers, like the Mac
                self.assertEqual(sw, 23)
                badged = [l for l in lines if l[sw - 1:sw] == "│" and l[sw - 2:sw - 1] in "●○!✓" and l[4:sw - 2].strip()]
                self.assertGreaterEqual(len(badged), 8)
                names = {w["name"] for w in C["workspaces"]}
                for n, l in enumerate(badged):
                    self.assertRegex(l[1:4], r"^[ \d]\d $", l)
                    shown = l[4:sw - 2].strip()
                    self.assertTrue(any(whole_word_cut(shown, n) for n in names), shown)

    def test_plain_dumps_sidebar_map(self):
        """The CLI dump (what tools/sidebar-proof.sh renders) at every map size: WORKSPACES and the five
        role titles where the map says sidebar, ws k/n in the tab bar where it says tabs."""
        for (w, h), expect in sorted(SIDEBAR_MAP.items()):
            cls, sw, btop, _, _ = expect[0]   # seed 7 at frame 400: a workspace without an oddball
            text = self.dump("%dx%d" % (w, h))
            lines = text.rstrip("\n").split("\n")
            self.assertEqual((len(lines), {len(l) for l in lines}), (h, {w}), (w, h))
            for role in AGENTS:
                self.assertRegex(text, r"╭─ (\S+ · )?%s · " % role, (w, h, role))
            self.assertEqual("WORKSPACES" in text, bool(sw), (w, h))
            self.assertEqual(bool(re.search(r" ws \d+/\d+ ", lines[0])), not sw, (w, h))
            self.assertEqual("─ btop ─" in text, btop, (w, h))


if __name__ == "__main__":
    unittest.main()
