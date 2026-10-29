"""The shared burn-in model (screensaver/burnin.py), wired into the engine by director.py.
Includes the terminal-only classes (compact/narrow), which web/src/burnin.js never sees."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402,F401  (puts terminal/ on sys.path)

from screensaver.burnin import (  # noqa: E402
    MARGIN_X, MARGIN_Y, STEP_MS, ORBIT, margins, frame_at, variant_at, apply_variant)
from screensaver.layout import COMPACT, compute_layout, size_class  # noqa: E402

SIZES = [(w, h) for w in range(20, 301) for h in range(8, 91)]


def _shared(w, h):
    c = size_class(w, h)
    return c if c in ("full", "tiny") else "other"


CLASS_FNS = {
    "size_class": size_class,
    "shared": _shared,
    "stepW": lambda w, h: w // 3,
    "stepH": lambda w, h: h // 3,
    "one": lambda w, h: "x",
}


def overlap(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


class Orbit(unittest.TestCase):
    def test_orbit_loop(self):
        self.assertEqual(len(ORBIT), 25)
        self.assertEqual(len({tuple(p) for p in ORBIT}), 25)
        for i, (ax, ay) in enumerate(ORBIT):
            bx, by = ORBIT[(i + 1) % 25]
            self.assertTrue(abs(ax) <= 2 and abs(ay) <= 2)
            self.assertTrue(abs(ax - bx) <= 1 and abs(ay - by) <= 1, i)
        for v in range(-2, 3):
            self.assertEqual(sum(1 for p in ORBIT if p[0] == v), 5)
            self.assertEqual(sum(1 for p in ORBIT if p[1] == v), 5)
        self.assertEqual((MARGIN_X, MARGIN_Y, STEP_MS), (2, 2, 30000))

    def test_off(self):
        for w, h in ((20, 8), (160, 50), (300, 90)):
            for t in (0, 29999, 30000, 1700000000000):
                f = frame_at(w, h, t, size_class, False)
                self.assertEqual((f["mx"], f["my"], f["ox"], f["oy"], f["bw"], f["bh"]), (0, 0, 0, 0, w, h))

    def test_margins_keep_class(self):
        for name, cls in CLASS_FNS.items():
            for w, h in SIZES:
                m = margins(w, h, cls)
                mx, my = m["mx"], m["my"]
                at = "%s %dx%d" % (name, w, h)
                self.assertTrue(0 <= mx <= MARGIN_X and 0 <= my <= MARGIN_Y, at)
                self.assertTrue(w - 2 * mx >= 1 and h - 2 * my >= 1, at)
                self.assertEqual(cls(w - 2 * mx, h - 2 * my), cls(w, h), at)
                if mx < MARGIN_X:
                    self.assertNotEqual(cls(w - 2 * (mx + 1), h), cls(w, h), at)
                if my < MARGIN_Y:
                    self.assertNotEqual(cls(w - 2 * mx, h - 2 * (my + 1)), cls(w, h), at)
        # the compact threshold (layout.COMPACT, 80x20) keeps its class and so gets no drift; +4x+4 gets it all
        cw, ch = COMPACT
        self.assertEqual(margins(cw, ch, size_class), {"mx": 0, "my": 0})
        self.assertEqual(margins(cw + 4, ch + 4, size_class), {"mx": 2, "my": 2})

    def test_frame_at(self):
        self.assertEqual(frame_at(160, 50, 0, size_class),
                         {"mx": 2, "my": 2, "bw": 156, "bh": 46, "ox": 2, "oy": 2, "step": 0})
        for w, h in ((160, 50), (101, 23), (20, 8), (100, 22)):
            for s in range(60):
                t = 1760529600000 + s * STEP_MS
                f = frame_at(w, h, t, size_class)
                self.assertEqual(f["step"], (t // STEP_MS) % 25)
                self.assertTrue(0 <= f["ox"] <= 2 * f["mx"] and 0 <= f["oy"] <= 2 * f["my"])
                self.assertTrue(f["ox"] + f["bw"] <= w and f["oy"] + f["bh"] <= h)
                self.assertTrue(all(isinstance(v, int) and v >= 0 for v in f.values()))
                g = frame_at(w, h, t + STEP_MS, size_class)
                self.assertTrue(abs(g["ox"] - f["ox"]) <= 1 and abs(g["oy"] - f["oy"]) <= 1)
                self.assertEqual(frame_at(w, h, t + 25 * STEP_MS, size_class), f)
        seen = {(frame_at(160, 50, s * STEP_MS, size_class)["ox"], frame_at(160, 50, s * STEP_MS, size_class)["oy"])
                for s in range(25)}
        self.assertEqual(len(seen), 25)

    def test_variant_at(self):
        for m in range(10):
            for fl in range(10):
                v = variant_at(m * 60000 + 59999, fl)
                self.assertEqual(v, (m + fl) % 4)
                self.assertEqual(variant_at(m * 60000, fl + 1), (v + 1) % 4)


class Variants(unittest.TestCase):
    def test_every_size(self):
        moved = swapped = 0
        for w, h in SIZES:
            for o in range(3):
                L = compute_layout(w, h, o)
                before = json.dumps(L)
                for v in range(4):
                    V = apply_variant(L, v)
                    at = "%dx%d o=%d v=%d %s" % (w, h, o, v, L["cls"])
                    self.assertEqual(json.dumps(L), before, at)
                    self.assertEqual(list(V), list(L), at)
                    self.assertEqual(list(V["rects"]), list(L["rects"]), at)
                    self.assertEqual((V["cls"], V["rows"]), (L["cls"], L["rows"]))
                    if v == 0 or L["cls"] == "tiny":
                        self.assertEqual(V, L, at)
                    ks = list(V["rects"])
                    for k in ks:
                        r, r0 = V["rects"][k], L["rects"][k]
                        self.assertEqual((r["w"], r["h"]), (r0["w"], r0["h"]), at + " " + k)
                        self.assertTrue(r["x"] >= 0 and r["y"] >= 0 and r["x"] + r["w"] <= w and r["y"] + r["h"] <= h, at + " " + k)
                    for i in range(len(ks)):
                        for j in range(i + 1, len(ks)):
                            self.assertFalse(overlap(V["rects"][ks[i]], V["rects"][ks[j]]), "%s %s/%s" % (at, ks[i], ks[j]))
                    if v & 1 and L["cls"] != "tiny" and ("sidebar" in L["rects"] or "btop" in L["rects"]):
                        k = "sidebar" if "sidebar" in L["rects"] else "btop"
                        self.assertNotEqual(V["rects"][k]["x"], L["rects"][k]["x"], at)
                        moved += 1
                    if v & 2 and "lead" in L["rects"] and L["cls"] != "tiny":
                        self.assertLess(V["rects"]["lead"]["y"], V["rects"]["planner"]["y"], at)
                        swapped += 1
        self.assertTrue(moved and swapped)
        V = apply_variant(compute_layout(160, 50, 0), 3)["rects"]
        self.assertEqual(V["sidebar"], {"x": 136, "y": 1, "w": 24, "h": 48})
        self.assertEqual(V["lead"]["y"], 1)
        self.assertEqual(V["fetch"]["x"], 0)


if __name__ == "__main__":
    unittest.main()
