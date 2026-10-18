"""Fix 2 P2: draw-only fallbacks for what compact cannot show (reports/plan-fix2.md 2): the oddball's newest
line in the ticker when it has no pane, the agent names in the tab bar before the workspace name, and
toasts never over the sidebar. Run: python3 -m unittest discover -s tests/terminal"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_layout import C, SEEDS, check_frame, overlaps  # noqa: E402

from screensaver.channels import toast_layout  # noqa: E402
from screensaver.clock import parse_now  # noqa: E402
from screensaver.director import Engine, _place, reveal_ms  # noqa: E402
from screensaver.grid import Grid  # noqa: E402
from screensaver.layout import compute_layout  # noqa: E402

NOW = "2026-10-16T13:00"
EGGS = {e["id"]: e for e in C["eggs"]}


def frames(w, h, seed, now, seconds, step=1000):
    e = Engine(C, cols=w, rows=h, seed=seed, now=parse_now(now), animate=True)
    for _ in range(seconds * 1000 // step):
        e.update(step)
        g = Grid(w, h)
        e.draw(g)
        yield e.state, g, g.plain().split("\n")


class OddballTicker(unittest.TestCase):
    def test_83x24_oddball_speaks_in_the_ticker(self):
        """seed 2 focuses the-intern-has-root (oddball 'intern'); at 83x24 it has no pane."""
        seen = 0
        for S, g, rows in frames(83, 24, 2, NOW, 60):
            ws = S.ws[S.focus]
            self.assertEqual(ws["name"], "the-intern-has-root")
            self.assertEqual([a["name"] for a in ws["oddballs"]], ["intern"])
            self.assertNotIn("odd0", S.layout["rects"])
            if S.ticker and S.t < S.ticker["until"]:
                self.assertNotIn("intern> ", rows[23])   # an egg owns the ticker first
                continue
            newest = max((l for l in ws["oddballs"][0]["lines"] if l.t0 <= S.t), key=lambda l: l.t0)
            self.assertTrue(rows[23].startswith(" intern> "), rows[23])
            self.assertIn(("intern> " + newest.text)[:40], rows[23])
            check_frame(self, S, g, ("oddball ticker", S.t))
            seen += 1
        self.assertGreater(seen, 30)

    def test_shown_pane_means_no_ticker_line(self):
        for w, h in ((100, 22), (150, 44)):
            for S, g, rows in frames(w, h, 2, NOW, 20):
                self.assertIn("odd0", S.layout["rects"], (w, h))
                self.assertNotIn("intern> ", rows[h - 1], (w, h))

    def test_t005_still_whole_in_the_ticker(self):
        """The footer egg owns the ticker over the oddball fallback (seed 2 at 83x24)."""
        e = Engine(C, cols=83, rows=24, seed=2, now=parse_now(NOW), animate=True)
        for _ in range(10):
            e.update(1000)
        _place(e.state, e.state.eggs["T005"], False)
        e.update(len(EGGS["T005"]["text"]) * 30 + 2000)
        g = Grid(83, 24)
        e.draw(g)
        row = g.plain().split("\n")[23]
        self.assertIn(EGGS["T005"]["text"], row)
        self.assertNotIn("intern> ", row)


class TabBarNames(unittest.TestCase):
    def test_83x24_every_agent_name(self):
        named = 0
        for seed, now in SEEDS[:3] + ((2, NOW),):
            for S, g, rows in frames(83, 24, seed, now, 300, 3000):
                names = [a["name"] for a in S.ws[S.focus]["cast"]]
                tail = rows[0][rows[0].index(" 2 team ") + 8:]
                if 83 - sum(len(n) + 3 for n in names) - 1 > 8 + 18:   # the names fit once the ws name goes
                    self.assertEqual(tail.split(), sum((["●", n] for n in names), []), (seed, S.t, rows[0]))
                    named += 1
                else:   # e.g. + yak-shaver: 56 cols of names, 54 free even without the ws name: dots, ws name kept
                    self.assertEqual(tail.split(), ["●"] * len(names), (seed, S.t, rows[0]))
                    self.assertNotEqual(rows[0][8:].split("   ")[0].strip(), "1 lead", rows[0])
                check_frame(self, S, g, ("tab bar", seed, S.t))
        self.assertGreater(named, 300)

    def test_name_kept_when_there_is_room(self):
        for S, g, rows in frames(100, 22, 7, NOW, 30, 3000):
            ws = S.ws[S.focus]
            if not ws["oddballs"]:   # 100x22 has room for both: the workspace name stays
                self.assertTrue(rows[0][8:].split("   ")[0].strip().startswith(ws["name"].split("-")[0]), rows[0])


class ToastPlacement(unittest.TestCase):
    def test_never_over_the_sidebar(self):
        """Every egg's toast, at every compact size of the laptop map, lies right of the sidebar."""
        for w, h in ((83, 24), (80, 20), (90, 24), (100, 22), (120, 30), (149, 44)):
            for o in range(3):
                L = compute_layout(w, h, o)
                sb = L["rects"]["sidebar"]
                for egg in C["eggs"]:
                    T = toast_layout(egg["text"], L["rects"], w, h, L["cls"])
                    if T:
                        self.assertFalse(overlaps(T["rect"], sb), (w, h, o, egg["id"], T["rect"]))

    def test_full_keeps_the_shared_regions(self):
        """full (shared with web/src/channels.js): the same toast with or without the class."""
        for w, h in ((150, 40), (160, 50)):
            L = compute_layout(w, h, 1)
            for egg in C["eggs"][:200]:
                self.assertEqual(toast_layout(egg["text"], L["rects"], w, h, "full"), toast_layout(egg["text"], L["rects"], w, h))

    def test_drawn_toast_at_83x24(self):
        """A btop egg (no btop at 83x24, so a toast) drawn: the sidebar column stays whole."""
        egg = next(e for e in C["eggs"] if e.get("pane") == "btop")
        e = Engine(C, cols=83, rows=24, seed=7, now=parse_now(NOW), animate=True)
        for _ in range(30):
            e.update(1000)
        S = e.state
        _place(S, S.eggs[egg["id"]], False)
        self.assertTrue(S.toast, egg["id"])
        e.update(reveal_ms(egg["text"]) + 100)
        g = Grid(83, 24)
        e.draw(g)
        rows = g.plain().split("\n")
        sw = S.layout["rects"]["sidebar"]["w"]
        T = toast_layout(egg["text"], S.layout["rects"], 83, 24, S.layout["cls"])
        self.assertGreaterEqual(T["rect"]["x"], sw)
        for y in range(1, 23):
            self.assertEqual(rows[y][sw - 1], "│", y)
        check_frame(self, S, g, "toast 83x24")


if __name__ == "__main__":
    unittest.main()
