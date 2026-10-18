"""Fix 3 F1: the font size per monitor (terminal/screensaver/fontsize.py). Run: python3 -m unittest discover -s tests/terminal
The metrics check needs the real TTF: HERDR_SS_TEST_FONT=/path/JetBrainsMonoNerdFont-Regular.ttf, or fc-match finds it."""
import io
import json
import math
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TERMINAL = os.path.join(ROOT, "terminal")
sys.path.insert(0, TERMINAL)

from screensaver import fontsize, layout  # noqa: E402
from screensaver.fontsize import FULL, PT_MAX, PT_MIN, PT_STEP, cells, font_pt  # noqa: E402

# plan-fix3.md 2.2: width, height, scale -> font_pt, worst-case cells at that size
TABLE = (
    (1920, 1200, 1.6, 9, (160, 46)),
    (2560, 1440, 1, 18, (170, 43)),
    (3840, 2160, 2, 15, (160, 40)),
    (3840, 2160, 1.5, 18, (174, 45)),
    (1920, 1080, 1, 15, (160, 40)),
    (2880, 1800, 2, 11.5, (151, 42)),
    (1366, 768, 1, 10, (170, 42)),
    (3440, 1440, 1, 18, (229, 43)),
    (1920, 1200, 1.25, 12, (160, 44)),
    (5120, 2880, 2, 18, (176, 45)),
    (1280, 800, 1.6, 8, (116, 33)),
)
FONT_SHA256 = "0ec29a68b539ece7078fc714cebff0c0accb2f4948f8f7963d9f5e86633b12d9"   # nerd-fonts v3.4.0
MONITORS = [   # the key set of a real `hyprctl monitors -j` entry that fontsize reads, plus neighbours
    {"id": 0, "name": "eDP-1", "width": 1920, "height": 1200, "refreshRate": 60.0, "x": 0, "y": 0, "scale": 1.6,
     "transform": 0, "focused": True, "disabled": False, "specialWorkspace": {"id": 0, "name": ""}, "solitaryBlockedBy": []},
    {"id": 1, "name": "HDMI-A-1", "width": 2560, "height": 1440, "refreshRate": 60.0, "x": 1200, "y": 0, "scale": 1.0,
     "transform": 0, "focused": False, "disabled": False, "specialWorkspace": {"id": 0, "name": ""}, "solitaryBlockedBy": []},
]


def full(c):
    return c[0] >= FULL[0] and c[1] >= FULL[1]


def cli(name, stdin):
    out, err = io.StringIO(), io.StringIO()
    rc = fontsize.main([name], io.StringIO(stdin), out, err)
    return rc, out.getvalue(), err.getvalue()


class FontPt(unittest.TestCase):
    def test_table(self):
        for w, h, s, pt, worst in TABLE:
            with self.subTest(monitor="%dx%d@%g" % (w, h, s)):
                self.assertEqual(font_pt(w, h, s), pt)
                self.assertEqual(cells(w, h, s, pt), worst)

    def test_brief_samples(self):
        self.assertEqual(font_pt(1920, 1200, 1.6), 9)      # the XPS 14, eDP-1
        self.assertEqual(font_pt(2560, 1440, 1), 18)
        self.assertEqual(font_pt(3840, 2160, 2), 15)
        self.assertEqual(font_pt(3840, 2160, 1.5), 18)
        self.assertEqual(font_pt(1920, 1080, 1), 15)
        self.assertEqual(font_pt(2880, 1800, 2), 11.5)

    def test_largest_full(self):
        for w, h, s, pt, _ in TABLE:
            if pt == PT_MIN:
                continue
            with self.subTest(monitor="%dx%d@%g" % (w, h, s)):
                self.assertTrue(full(cells(w, h, s, pt)))
                self.assertEqual(layout.size_class(*cells(w, h, s, pt)), "full")
                if pt < PT_MAX:
                    self.assertFalse(full(cells(w, h, s, pt + PT_STEP)))
                    # and no larger size anywhere up to 18 is full (the search is from the top)
                    for q in range(int((pt - PT_MIN) / PT_STEP) + 1, int((PT_MAX - PT_MIN) / PT_STEP) + 1):
                        self.assertFalse(full(cells(w, h, s, PT_MIN + q * PT_STEP)))

    def test_clamps(self):
        self.assertEqual(font_pt(7680, 4320, 1), PT_MAX)     # 8K at 1: 18, never more
        self.assertEqual(font_pt(800, 600, 1), PT_MIN)       # too small even at 8: 8
        self.assertEqual(font_pt(1280, 800, 1.6), PT_MIN)

    def test_transform_swaps(self):
        self.assertEqual(font_pt(1200, 1920, 1.6, 1), font_pt(1920, 1200, 1.6))
        self.assertEqual(font_pt(1200, 1920, 1.6, 3), font_pt(1920, 1200, 1.6))
        self.assertEqual(font_pt(1920, 1200, 1.6, 1), font_pt(1200, 1920, 1.6))
        self.assertEqual(font_pt(1920, 1200, 1.6, 2), font_pt(1920, 1200, 1.6))   # 180 deg: no swap
        self.assertNotEqual(font_pt(1920, 1080, 1, 1), font_pt(1920, 1080, 1))     # portrait FHD differs

    def test_invalid(self):
        for args in ((0, 1200, 1.6), (1920, -1, 1.6), (1920, 1200, 0), (math.nan, 1200, 1), (1920, math.inf, 1),
                     (1920, 1200, math.nan), (None, 1200, 1), ("1920", 1200, 1), (True, 1200, 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                font_pt(*args)
        with self.assertRaises(ValueError):
            font_pt(1920, 1200, 1, "0")

    def test_monotonic(self):
        # a bigger logical screen never gets a smaller size
        for s in (1, 1.25, 1.5, 1.6, 2):
            prev = None
            for w in range(1000, 4000, 120):
                pt = font_pt(w, round(w * 0.6), s)
                if prev is not None:
                    self.assertGreaterEqual(pt, prev, "%dx%d@%g" % (w, round(w * 0.6), s))
                prev = pt
            for h in range(600, 2400, 60):
                ptw = font_pt(3840, h, s)
                self.assertGreaterEqual(font_pt(3840, h + 60, s), ptw)

    def test_full_is_layout_full(self):
        self.assertIs(fontsize.FULL, layout.FULL)

    def test_cells_worst_case(self):
        # every cell dimension rounded up: never more cells than the unrounded (exact) grid
        for w, h, s, pt, _ in TABLE:
            p = pt * 4 / 3 * s
            c, r = cells(w, h, s, pt)
            self.assertLessEqual(c, w / (fontsize.ADV * p))
            self.assertLessEqual(r, h / ((fontsize.ASC + fontsize.DESC) * p))


class Cli(unittest.TestCase):
    def test_two_monitors(self):
        rc, out, err = cli("eDP-1", json.dumps(MONITORS))
        self.assertEqual((rc, out), (0, "9\n"))
        self.assertEqual(err, "eDP-1 1920x1200@1.6 -> 9 pt, at least 160x46 (full)\n")
        rc, out, err = cli("HDMI-A-1", json.dumps(MONITORS))
        self.assertEqual((rc, out), (0, "18\n"))
        self.assertIn("-> 18 pt, at least 170x43 (full)", err)

    def test_half_point(self):
        rc, out, _ = cli("X", json.dumps([{"name": "X", "width": 2880, "height": 1800, "scale": 2.0, "transform": 0}]))
        self.assertEqual((rc, out), (0, "11.5\n"))

    def test_errors(self):
        for name, stdin, why in (("DP-9", json.dumps(MONITORS), "not in hyprctl monitors"), ("eDP-1", "garbage", "bad hyprctl monitors JSON"),
                                 ("eDP-1", "{}", "not in hyprctl monitors"), ("X", json.dumps([{"name": "X", "width": 0, "height": 1, "scale": 1}]), "X:"),
                                 ("X", json.dumps([{"name": "X", "width": 1920, "height": 1080}]), "X:")):
            with self.subTest(stdin=stdin[:20], name=name):
                rc, out, err = cli(name, stdin)
                self.assertEqual((rc, out), (2, ""))
                self.assertIn(why, err)
        self.assertEqual(fontsize.main([], io.StringIO("[]"), io.StringIO(), io.StringIO()), 2)

    def test_module_cli(self):
        p = subprocess.run([sys.executable, "-m", "screensaver.fontsize", "eDP-1"], input=json.dumps(MONITORS), capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=TERMINAL))
        self.assertEqual((p.returncode, p.stdout), (0, "9\n"), p.stderr)
        p = subprocess.run([sys.executable, "-m", "screensaver.fontsize", "nope"], input="[]", capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=TERMINAL))
        self.assertEqual(p.returncode, 2)


def find_font():
    f = os.environ.get("HERDR_SS_TEST_FONT")
    if f:
        return f
    if shutil.which("fc-match"):
        f = subprocess.run(["fc-match", "-f", "%{file}", "JetBrainsMono Nerd Font"], capture_output=True, text=True).stdout
        if "JetBrainsMono" in f and os.path.exists(f):
            return f
    return None


class Metrics(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "tools", "font-metrics.py")),
                         "tools/font-metrics.py (the source app's measuring tool) is not part of the plugin")
    def test_constants_match_the_ttf(self):
        f = find_font()
        if not f:
            self.skipTest("JetBrainsMono Nerd Font not found (set HERDR_SS_TEST_FONT); constants were measured from sha256 " + FONT_SHA256)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("font_metrics", os.path.join(ROOT, "tools", "font-metrics.py"))
        fm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fm)
        m = fm.metrics(f)
        upem = m["unitsPerEm"]
        self.assertEqual(m["advance"], m["advanceWidthMax"])
        self.assertAlmostEqual(m["advance"] / upem, fontsize.ADV)
        self.assertAlmostEqual(m["hhea"][0] / upem, fontsize.ASC)
        self.assertAlmostEqual(-m["hhea"][1] / upem, fontsize.DESC)
        self.assertEqual(m["hhea"][2], 0)
        try:
            from PIL import ImageFont
        except ImportError:
            return
        font = ImageFont.truetype(f, 100)
        self.assertAlmostEqual(font.getlength("M"), 100 * fontsize.ADV, places=3)
        a, d = font.getmetrics()
        self.assertEqual(a + d, round(100 * (fontsize.ASC + fontsize.DESC)))


if __name__ == "__main__":
    unittest.main()
