"""The six thank-you lines to Alex Epstein in the terminal (Omarchy) saver: rendered whole at 80, 82 and
100 columns, the layout intact with one on screen, the footer line rare.
Run: python3 -m unittest discover -s tests/terminal"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_layout import C, TERMINAL, check_frame  # noqa: E402

from screensaver.channels import wrap, pane_text_width, message_rows  # noqa: E402
from screensaver.clock import parse_now  # noqa: E402
from screensaver.director import Engine, _place, reveal_ms, TICKER_HOLD_MS, MESSAGE_HOLD_MS  # noqa: E402
from screensaver.grid import Grid, wrap_readable  # noqa: E402

MESSAGES = ("T001", "T002", "T003", "T004", "T006")
FOOTER = "T005"
NAME = "Alex Epstein"
# Fix 2 P3: + 83x24 (what Michael saw), 150x44 (full, the planned XPS grid) and 160x46 (the XPS after Fix 3)
SIZES = ((80, 20), (80, 24), (82, 21), (83, 24), (100, 22), (150, 44), (160, 46))
NOW = "2026-10-16T13:00"
EGGS = {e["id"]: e for e in C["eggs"]}


def placed_frame(w, h, tid):
    """seed 7, 30 s in, then the egg placed and fully revealed; returns (state, grid, egg event)."""
    e = Engine(C, cols=w, rows=h, seed=7, now=parse_now(NOW), animate=True)
    for _ in range(30):
        e.update(1000)
    S = e.state
    n0 = len(S.trace)
    _place(S, S.eggs[tid], False)
    ev = [x for x in S.trace[n0:] if x[1] == "egg"]
    e.update(reveal_ms(S.eggs[tid]["text"]) + 100)
    g = Grid(w, h)
    e.draw(g)
    return S, g, ev


def check_bar(tc, S, g, where):
    """Michael's readability bar (check_frame) where it applies: the terminal-only classes. full is the
    Mac's layout and cuts text like the Mac (tests/parity: identical to the web renderer)."""
    if S.layout["cls"] != "full":
        check_frame(tc, S, g, where)


def name_shown(rows):
    """'Alex Epstein' readable in these rows: on one row, or wrapped at its own space ('… Alex' then
    'Epstein …'). The Mac wraps the same way (web wrap = wrap_readable, test_ep2): at its 81-col
    lead strip T004 puts 'Alex' and 'Epstein' on two rows too."""
    rows = [x.strip() for x in rows]
    if any(NAME in x for x in rows):
        return 1
    return int(any(a.endswith(" Alex") and b.startswith("Epstein") for a, b in zip(rows, rows[1:])))


def lead_rows(S, g):
    r = S.layout["rects"]["lead"]
    rows = g.plain().split("\n")
    return [rows[y][r["x"] + 1:r["x"] + r["w"] - 1] for y in range(r["y"] + 1, r["y"] + r["h"] - 1)]


class RenderInFull(unittest.TestCase):
    def test_ep1_messages_in_the_lead_pane_whole(self):
        for w, h in SIZES:
            for tid in MESSAGES:
                text = EGGS[tid]["text"]
                S, g, ev = placed_frame(w, h, tid)
                where = (w, h, tid)
                self.assertEqual([(x[3], x[4], x[5]) for x in ev], [(tid, "message", "lead")], where)
                inner = lead_rows(S, g)
                shown = [x.strip() for x in inner if x.strip()]
                # the message is the newest k rows (bottom of the strip); a 3-row strip may keep one context row above it
                k = len(wrap(text, pane_text_width(S.layout["rects"]["lead"])))
                self.assertLessEqual(k, message_rows(S.layout["rects"]["lead"]), where)
                self.assertEqual(" ".join(shown[-k:]), text, (where, shown))
                if S.layout["cls"] != "full":   # full keeps earlier lead lines above it, as on the Mac
                    self.assertLessEqual(len(shown), message_rows(S.layout["rects"]["lead"]), where)
                shown = shown[-k:]
                # same indent on every row: one pad column after the border
                self.assertTrue(all(x.startswith(" ") and not x.startswith("  ") for x in inner if x.strip()), (where, inner))
                self.assertTrue(all(len(x) <= w for x in g.plain().split("\n")[:h]), where)
                self.assertTrue(all(len(x.rstrip()) <= pane_text_width(S.layout["rects"]["lead"]) + 1 for x in inner), (where, inner))
                self.assertEqual(name_shown(shown), 1, (where, shown))
                check_bar(self, S, g, where)

    def test_ep1_footer_in_the_status_bar_whole(self):
        for w, h in SIZES:
            text = EGGS[FOOTER]["text"]
            S, g, ev = placed_frame(w, h, FOOTER)
            where = (w, h, FOOTER)
            self.assertEqual([(x[3], x[4]) for x in ev], [(FOOTER, "ticker")], where)
            status = g.plain().split("\n")[S.layout["rects"]["status"]["y"]]
            self.assertIn(text, status, where)
            self.assertIn(" found ", status, where)
            check_bar(self, S, g, where)

    def test_ep2_fit_check_wrap_equals_drawn_wrap(self):
        """The fit check uses channels.wrap; compact layouts draw with grid.wrap_readable. They must
        agree for these texts at every lead width, so what passed the check is what is drawn."""
        for tid in MESSAGES + (FOOTER,):
            text = EGGS[tid]["text"]
            for width in range(40, 201):
                self.assertEqual(wrap(text, width), wrap_readable(text, width), (tid, width))
                self.assertEqual(" ".join(wrap(text, width)), text, (tid, width))


def visible_ms(w, h, seed, tid, step=100, window_ms=30000):
    """With every other egg found, tid is the first draw. From its placement on, for window_ms: how
    long (ms) the whole text is on screen in the lead pane, and how long 'Alex Epstein' is."""
    e = Engine(C, cols=w, rows=h, seed=seed, now=parse_now(NOW), found=[x for x in EGGS if x != tid], animate=False)
    text = EGGS[tid]["text"]
    whole = name = 0
    start = None
    t = 0
    while start is None or t - start < window_ms:
        e.update(step)
        t += step
        if start is None:
            ev = [x for x in e.state.trace if x[1] == "egg" and x[3] == tid]
            if not ev:
                if t > 120000:
                    raise AssertionError((w, h, seed, tid, "not placed in 2 min"))
                continue
            assert ev[0][4] == "message", (w, h, seed, tid, ev)
            start = t
        g = Grid(w, h)
        e.draw(g)
        rows = [x.strip() for x in lead_rows(e.state, g)]
        whole += step if text in " ".join(rows) else 0
        name += step if name_shown(rows) else 0
    return whole, name


class MessageHold(unittest.TestCase):
    def test_ep5_message_whole_and_name_visible_at_least_4s(self):
        """A message egg holds the lead strip (3 inner rows in compact): crew lines wait until it is typed + MESSAGE_HOLD_MS."""
        worst = None
        for w, h in ((100, 22), (82, 21), (83, 24)):
            for seed in range(1, 13):
                for tid in MESSAGES:
                    whole, name = visible_ms(w, h, seed, tid)
                    self.assertGreaterEqual(whole, 4000, (w, h, seed, tid, whole))
                    self.assertGreaterEqual(name, 4000, (w, h, seed, tid, name))
                    worst = min(worst or (whole, name), (whole, name))
        print("\n# EP-5 worst over 120 runs: whole %d ms, name %d ms" % worst)

    def test_ep5b_hold_delays_crew_lines_not_eggs(self):
        e = Engine(C, cols=100, rows=22, seed=7, now=parse_now(NOW), animate=False)
        for _ in range(30):
            e.update(1000)
        S = e.state
        lead = S.ws[S.focus]["byRole"]["lead"]
        self.assertNotIn("hold_until", lead)
        t_place = S.t
        n_before = len(lead["lines"])
        _place(S, S.eggs["T003"], False)
        hold = t_place + reveal_ms(EGGS["T003"]["text"]) + MESSAGE_HOLD_MS
        self.assertEqual(lead["hold_until"], hold)
        self.assertGreaterEqual(S.pane_busy_until, hold)
        for _ in range(60):
            e.update(1000)
        new = lead["lines"][n_before:]
        self.assertEqual(new[0].style, "egg")
        self.assertEqual(new[0].t0, t_place + 400)
        crew = [l for l in new[1:] if l.style != "egg"]
        self.assertTrue(crew, "crew lines arrived within 60 s")
        self.assertTrue(all(l.t0 >= hold for l in crew), [(l.t0, l.text) for l in crew if l.t0 < hold])
        # no flip while the message is held
        self.assertFalse([x for x in S.trace if x[1] == "flip" and t_place <= x[0] < hold])


class FooterWhenAllFound(unittest.TestCase):
    def test_ep6_ticker_egg_keeps_its_room_when_everything_is_found(self):
        """With every egg found the counter reads 'found M of M · all of them. go outside.'; a ticker egg
        keeps the room its fit check counted on (the tail gives way), so T005 is never cut."""
        text = EGGS[FOOTER]["text"]
        for w, h in SIZES:
            e = Engine(C, cols=w, rows=h, seed=7, now=parse_now(NOW), found=list(EGGS), animate=True)
            for _ in range(30):
                e.update(1000)
            S = e.state
            sy = S.layout["rects"]["status"]["y"]
            g = Grid(w, h)
            e.draw(g)
            before = g.plain().split("\n")[sy]
            _place(S, S.eggs[FOOTER], False)
            e.update(reveal_ms(text) + 100)
            g = Grid(w, h)
            e.draw(g)
            row = g.plain().split("\n")[sy]
            self.assertIn(text, row, (w, h, row))
            self.assertIn("found %d of %d" % (len(EGGS), len(EGGS)), row, (w, h, row))
            check_bar(self, S, g, (w, h, "all found"))
            e.update(TICKER_HOLD_MS + 1000)
            g = Grid(w, h)
            e.draw(g)
            after = g.plain().split("\n")[sy]
            self.assertNotIn(text, after)
            # without a ticker egg the counter is drawn exactly as before the egg
            self.assertEqual(after[after.index(" found "):], before[before.index(" found "):], (w, h))


class Rare(unittest.TestCase):
    def test_ep3_footer_line_is_rare_over_12_hours(self):
        hours = 12
        run_ms = hours * 3600 * 1000
        visible_each = reveal_ms(EGGS[FOOTER]["text"]) + TICKER_HOLD_MS
        for seed in (1, 7, 42):
            e = Engine(C, cols=100, rows=22, seed=seed, now=parse_now(NOW), animate=False)
            for _ in range(hours * 3600):
                e.update(1000)
            ev = [x for x in e.state.trace if x[1] == "egg" and x[3] and x[3].startswith("T")]
            t5 = [x[0] for x in ev if x[3] == FOOTER]
            print("\n# seed %d: T005 shown %d times in %d h at minutes %s" % (seed, len(t5), hours, [t // 60000 for t in t5]))
            self.assertTrue(1 <= len(t5) <= 6, (seed, len(t5)))
            self.assertLessEqual(len(t5) * visible_each, run_ms // 100, (seed, "visible more than 1% of the time"))
            self.assertTrue(all(b - a >= 60000 for a, b in zip(t5, t5[1:])), (seed, t5))
            self.assertTrue(all(x[4] == "ticker" for x in ev if x[3] == FOOTER), seed)
            self.assertEqual({x[3] for x in ev}, set(MESSAGES + (FOOTER,)), seed)


class CliDump(unittest.TestCase):
    def test_ep4_cli_plain_dump_shows_t003_whole(self):
        """Same path the proof tool uses: with every other egg found, T003 is the first draw.
        Frame 270 (13.5 s) is right after it is fully typed (placed 9.4 s, typed 3.5 s)."""
        text = EGGS["T003"]["text"]
        for size in ("100x22", "82x21", "83x24", "150x44", "160x46"):
            w, h = map(int, size.split("x"))
            with tempfile.TemporaryDirectory() as d:
                found = os.path.join(d, "found")
                with open(found, "w") as f:
                    f.write("".join(e["id"] + "\n" for e in C["eggs"] if e["id"] != "T003"))
                env = dict(os.environ, XDG_STATE_HOME=os.path.join(d, "state"))
                out = subprocess.run([os.path.join(TERMINAL, "bin", "herdr-screensaver"), "--frames", "270", "--seed", "7", "--now", NOW,
                                      "--size", size, "--found-file", found, "--dump", "--plain"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=True).stdout.decode()
            lines = out.rstrip("\n").split("\n")
            self.assertEqual(len(lines), h, size)
            self.assertTrue(all(len(l) == w for l in lines), size)
            lead = [i for i, l in enumerate(lines) if re.search(r"╭─ (\S+ · )?lead · ", l)]
            self.assertEqual(len(lead), 1, size)
            top = lines[lead[0]]
            x0 = re.search(r"╭─ (\S+ · )?lead · ", top).start()
            x1 = top.index("╮", x0)
            bottom = next(i for i in range(lead[0] + 1, h) if lines[i][x0] == "╰")
            body = [l[x0 + 1:x1] for l in lines[lead[0] + 1:bottom]]
            body = [b.strip() for b in body if b.strip()]
            k = len(wrap(text, x1 - x0 + 1 - 3))   # the message's own rows, the newest at the bottom
            self.assertEqual(" ".join(body[-k:]), text, (size, body))
            self.assertIn("WORKSPACES", out)
            for role in ("lead", "planner", "builder", "reviewer", "qa"):
                self.assertRegex(out, r"╭─ (\S+ · )?%s · " % role, (size, role))
            self.assertIn("found 727 of 727", out)


if __name__ == "__main__":
    unittest.main()
