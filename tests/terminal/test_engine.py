"""Engine behaviour (port of the S2 checks that matter for the terminal build)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import content, advance  # noqa: E402

from screensaver.director import Engine, choose_channel  # noqa: E402
from screensaver.channels import wrap, pane_text_width, message_rows  # noqa: E402
from screensaver.prng import Rng, hash32  # noqa: E402
from screensaver.layout import compute_layout, size_class  # noqa: E402
from screensaver.clock import parse_now  # noqa: E402

C = content()
M = C["counts"]["shipped"]
NOW = parse_now("2026-10-15T12:00")


def eggs(e):
    return [x for x in e.trace if x[1] == "egg"]


class PrngTest(unittest.TestCase):
    def test_sfc32_matches_js(self):
        # first outputs of createRng(1) / createRng(42) in web/src/prng.js
        r = Rng(1)
        self.assertEqual([r.next() for _ in range(4)], JS_SEED1)
        r = Rng(42)
        self.assertEqual([r.randint(1000) for _ in range(5)], JS_SEED42_RANDINT)
        self.assertEqual(hash32("F1"), JS_HASH_F1)


# values printed by node from web/src/prng.js
JS_SEED1 = [473542192, 3964317691, 2295682031, 2113742504]
JS_SEED42_RANDINT = [471, 353, 629, 217, 397]
JS_HASH_F1 = 332577688


class LayoutTest(unittest.TestCase):
    def test_classes_and_no_overlap(self):
        self.assertEqual(size_class(150, 40), "full")
        self.assertIn("sidebar", compute_layout(150, 40, 2)["rects"])
        self.assertIn("sidebar", compute_layout(120, 34)["rects"])   # compact (>= 80x20): narrow sidebar
        self.assertIn("sidebar", compute_layout(80, 20)["rects"])
        self.assertNotIn("sidebar", compute_layout(79, 34)["rects"])
        for w in range(20, 301, 7):
            for h in range(8, 91, 3):
                for o in range(3):
                    rs = list(compute_layout(w, h, o)["rects"].values())
                    for r in rs:
                        self.assertTrue(r["w"] >= 1 and r["h"] >= 1 and r["x"] + r["w"] <= w and r["y"] + r["h"] <= h)
                    for i in range(len(rs)):
                        for j in range(i + 1, len(rs)):
                            a, b = rs[i], rs[j]
                            self.assertFalse(a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


def _words(n):
    return " ".join("w%03d" % i for i in range(n))


def _text_of_rows(rows, w):
    n = 1
    while len(wrap(_words(n), w)) < rows:
        n += 1
    return _words(n)


class MessageChannelTest(unittest.TestCase):
    """pane 'message': an agent's message to the lead pane; it must fit the lead pane's inner rows."""

    def test_compact_three_row_lead_strip(self):
        # Fix 2 P1: the compact lead strip has 3 inner rows (5 rows), like full's message limit
        for cols, rows in [(100, 22), (82, 21), (93, 22), (83, 24), (80, 20)]:
            S = Engine(C, seed=1, now=NOW, cols=cols, rows=rows).state
            lead = S.layout["rects"]["lead"]
            w = pane_text_width(lead)
            self.assertEqual(message_rows(lead), 3, (cols, rows))
            for n in (1, 2, 3):
                t = _text_of_rows(n, w)
                self.assertEqual(choose_channel(S, {"id": "X1", "text": t, "pane": "message"}), ("message", t, "lead"), (cols, rows, n))
            t4 = _text_of_rows(4, w)
            self.assertEqual(choose_channel(S, {"id": "X1", "text": t4, "pane": "message"}), ("toast", t4, None), (cols, rows))

    def test_full_and_no_lead(self):
        S = Engine(C, seed=1, now=NOW, cols=160, rows=50).state
        lead = S.layout["rects"]["lead"]
        w = pane_text_width(lead)
        self.assertEqual(message_rows(lead), 3)
        self.assertEqual(choose_channel(S, {"id": "X1", "text": _text_of_rows(3, w), "pane": "message"})[0], "message")
        self.assertEqual(choose_channel(S, {"id": "X1", "text": _text_of_rows(4, w), "pane": "message"})[0], "toast")
        small = Engine(C, seed=1, now=NOW, cols=40, rows=12).state
        self.assertEqual(choose_channel(small, {"id": "X1", "text": "agent-3: hi", "pane": "message"})[0], "toast")


class DirectorTest(unittest.TestCase):
    def test_total_is_the_shipped_count(self):
        e = Engine(C, seed=1, now=NOW)
        self.assertEqual(e.info()["total"], M)
        self.assertEqual(M, C["counts"]["total"] - C["counts"]["pending"] - C["counts"].get("cut", 0))

    def test_no_repeats_in_120_minutes(self):
        for seed in (1, 2, 3):
            ids = [x[3] for x in eggs(advance(Engine(C, seed=seed, now=NOW, animate=False), 120 * 60000))]
            self.assertGreater(len(ids), 500)
            self.assertEqual(len(set(ids)), len(ids), "seed %d" % seed)

    def test_dhh_within_15_minutes(self):
        for seed in range(1, 21):
            ids = [x[3] for x in eggs(advance(Engine(C, seed=seed, now=NOW, animate=False), 15 * 60000))]
            self.assertTrue(set(ids) & {"F1", "F2", "F3"}, "seed %d" % seed)

    def test_pending_never_shown(self):
        ids = set(x[3] for x in eggs(advance(Engine(C, seed=9, now=NOW, egg_rate=600, animate=False), 20 * 60000)))
        for pid in ("P017", "P018", "P019", "P020", "P021", "P022", "P023", "P027"):
            self.assertNotIn(pid, ids)

    def test_found_count_only_by_reveal_and_once(self):
        fired = []
        e = Engine(C, seed=13, now=NOW, egg_rate=20, animate=False)
        e.on_found(fired.append)
        advance(e, 30 * 60000, 100)
        found = [x[3] for x in e.trace if x[1] == "found"]
        self.assertEqual(fired, found)
        self.assertEqual(len(set(fired)), len(fired))
        self.assertEqual(e.found_count(), len(fired))

    def test_deterministic_and_fps_independent(self):
        a = advance(Engine(C, seed=77, now=NOW, animate=False), 20 * 60000, 50).trace
        b = advance(Engine(C, seed=77, now=NOW, animate=False), 20 * 60000, 1000).trace
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
