"""CLI: themes, dumps (S2 #3 structure), found persistence, errors."""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import run, content, FIXTURES  # noqa: E402

C = content()
M = C["counts"]["shipped"]
BADGES = ("●", "○", "!", "✓", "auto")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="herdr-cli-")
        self.env = {"XDG_STATE_HOME": os.path.join(self.tmp, "state"), "HOME": os.path.join(self.tmp, "home")}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_list_themes(self):
        r = run(["--list-themes"], self.env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.decode(), "catppuccin gruvbox tokyonight\n")

    def test_matrix_rejected(self):
        r = run(["--theme", "matrix", "--frames", "1"], self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown theme 'matrix'", r.stderr.decode())

    def test_dump_structure_160x50(self):
        r = run(["--frames", "2400", "--size", "160x50", "--seed", "3", "--now", "2026-10-15T12:00", "--dump", "--plain"], self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = r.stdout.decode("utf-8")
        rows = text.split("\n")[:-1]
        self.assertEqual(len(rows), 50)
        self.assertTrue(all(len(x) == 160 for x in rows))
        self.assertTrue(rows[0].startswith(" herdr "))
        side = [x[:23] for x in rows[1:-1]]
        ws_rows = [x for x in side if re.match(r"^.[ \d]\d \S", x)]
        self.assertGreaterEqual(len(ws_rows), 12)
        self.assertTrue(any(x.rstrip().endswith(b) for x in ws_rows for b in BADGES))
        for role in ("lead", "planner", "builder", "reviewer", "qa"):
            self.assertRegex(text, "(─ |· )%s ·" % role)
        self.assertIn("─ fastfetch ─", text)
        self.assertIn("─ btop ─", text)
        self.assertIn("PID NAME", text)
        self.assertRegex(rows[-1], r"found \d+ of %d" % M)
        self.assertIsNone(re.search(r"\brain\b", text, re.I))
        self.assertFalse(any(0xFF66 <= ord(c) <= 0xFF9D for c in text))

    def test_ansi_dump_and_sizes(self):
        for size in ("20x8", "60x20", "100x30", "130x36", "200x60"):
            r = run(["--frames", "100", "--size", size, "--seed", "1", "--dump", "--plain"], self.env)
            self.assertEqual(r.returncode, 0, r.stderr)
            w, h = map(int, size.split("x"))
            rows = r.stdout.decode().split("\n")[:-1]
            self.assertEqual((len(rows), set(len(x) for x in rows)), (h, {w}), size)
        r = run(["--frames", "10", "--seed", "1", "--dump", "--color", "truecolor"], self.env)
        self.assertIn("\x1b[38;2;", r.stdout.decode())

    def test_found_persistence_across_two_runs(self):
        args = ["--frames", "24000", "--seed", "4", "--egg-rate", "60", "--now", "2026-10-15T12:00"]
        r1 = run(args, self.env)
        end1 = int(re.search(r"end found (\d+) of", r1.stderr.decode()).group(1))
        r2 = run(["--frames", "20", "--seed", "5"], self.env)
        start2 = int(re.search(r"start found (\d+) of", r2.stderr.decode()).group(1))
        self.assertGreater(end1, 0)
        self.assertEqual(start2, end1)
        path = os.path.join(self.env["HOME"], ".local", "share", "herdr-screensaver-plugin", "found")
        lines = open(path).read().split()
        self.assertEqual(len(lines), len(set(lines)), "no duplicate lines")
        self.assertEqual(len(lines), end1)

    def test_found_file_dedup_on_load(self):
        p = os.path.join(self.tmp, "found")
        with open(p, "w") as f:
            f.write("A1\nA1\nN001\n\nNOPE\n")
        r = run(["--frames", "1", "--found-file", p], self.env)
        self.assertIn("start found 2 of %d" % M, r.stderr.decode())

    def test_argument_errors(self):
        self.assertEqual(run(["--dump"], self.env).returncode, 2)
        self.assertEqual(run(["--frames", "1", "--plain"], self.env).returncode, 2)
        self.assertEqual(run(["--frames", "1", "--content", os.path.join(self.tmp, "missing.json")], self.env).returncode, 2)

    def test_refuses_include_pending_content(self):
        import json
        p = os.path.join(self.tmp, "c.json")
        c = dict(C, include_pending=True)
        with open(p, "w") as f:
            json.dump(c, f)
        r = run(["--frames", "1", "--content", p], self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("HERDR_INCLUDE_PENDING", r.stderr.decode())


class OmarchyThemeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="herdr-omarchy-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _place(self, which, v4=True):
        base = os.path.join(self.tmp, "state", "omarchy") if v4 else os.path.join(self.tmp, "home", ".config", "omarchy")
        d = os.path.join(base, "current", "theme")
        os.makedirs(d)
        shutil.copy(os.path.join(FIXTURES, "omarchy", which, "colors.toml"), d)

    def _dump(self):
        env = {"XDG_STATE_HOME": os.path.join(self.tmp, "state"), "HOME": os.path.join(self.tmp, "home")}
        return run(["--frames", "20", "--theme", "omarchy", "--color", "truecolor", "--dump", "--found-file", os.path.join(self.tmp, "f")], env)

    def test_tokyo_night_v4(self):
        self._place("tokyo-night")
        r = self._dump()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("48;2;26;27;38", r.stdout.decode())
        self.assertEqual(r.stderr.decode().count("omarchy"), 0)

    def test_gruvbox_and_malformed_line_ignored(self):
        self._place("gruvbox")
        r = self._dump()
        self.assertIn("48;2;40;40;40", r.stdout.decode())
        err = r.stderr.decode()
        # gruvbox fixture has no `muted`/`dark_foreground`: one line naming it, tokyonight fallback
        self.assertEqual(len([l for l in err.splitlines() if "omarchy theme" in l]), 1)
        self.assertIn("muted", err)

    def test_v3_path(self):
        self._place("gruvbox", v4=False)
        self.assertIn("48;2;40;40;40", self._dump().stdout.decode())

    def test_missing_falls_back_with_one_line(self):
        r = self._dump()
        self.assertEqual(r.returncode, 0)
        self.assertIn("48;2;26;27;38", r.stdout.decode())  # tokyonight bg
        lines = [l for l in r.stderr.decode().splitlines() if "Omarchy" in l]
        self.assertEqual(len(lines), 1, r.stderr)
        self.assertIn("~/.config/omarchy/current/theme/colors.toml", lines[0])  # HOME shown as ~
        self.assertNotIn(os.path.join(self.tmp, "home"), lines[0])



def pty_run(args, cols, rows, env, keys=b"q", wait_for=b"found ", resize=None, timeout=15):
    """Run the engine in a cols x rows pty: wait for wait_for, optionally resize, send keys.
    Returns (exit code, output bytes, tty attrs restored?)."""
    import fcntl
    import pty
    import select
    import struct
    import subprocess
    import termios
    import time
    from helpers import BIN
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    before = termios.tcgetattr(master)  # macOS revokes the slave when the session ends; the master reflects it
    e = dict(os.environ, TERM="xterm-256color")
    e.pop("HERDR_SS_DEBUG", None)
    e.update(env)
    p = subprocess.Popen([BIN] + args, stdin=slave, stdout=slave, stderr=slave, env=e, close_fds=True, start_new_session=True)
    out = b""

    def pump(t):
        nonlocal out
        r, _, _ = select.select([master], [], [], t)
        if r:
            try:
                out += os.read(master, 65536)
            except OSError:
                pass
    try:
        deadline = time.monotonic() + timeout
        while wait_for not in out and p.poll() is None and time.monotonic() < deadline:
            pump(0.1)
        end = time.monotonic() + 0.6  # past the start-up grace
        while time.monotonic() < end and p.poll() is None:
            pump(0.05)
        if resize and p.poll() is None:
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", resize[1], resize[0], 0, 0))
            end = time.monotonic() + 0.6
            while time.monotonic() < end:
                pump(0.05)
        if keys and p.poll() is None:
            os.write(master, keys)
        deadline = time.monotonic() + 5
        while p.poll() is None and time.monotonic() < deadline:
            pump(0.05)
        for _ in range(4):
            pump(0.05)
        after = termios.tcgetattr(master)
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        os.close(master)
        os.close(slave)
    pend = getattr(termios, "PENDIN", 0)
    before[3] &= ~pend
    after[3] &= ~pend
    return p.returncode, out, before == after


class SizeFlagsTest(unittest.TestCase):
    """X3: --size in live mode, --print-size, the debug log (HERDR_SS_DEBUG / the debug flag file)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="herdr-size-")
        self.home = os.path.join(self.tmp, "home dir")
        self.env = {"XDG_STATE_HOME": os.path.join(self.tmp, "state"), "HOME": self.home}
        self.data = os.path.join(self.home, ".local", "share", "herdr-screensaver-plugin")
        self.log = os.path.join(self.data, "debug.log")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_live_size_draws_exactly_wxh_at_the_top_left(self):
        code, out, restored = pty_run(["--seed", "1", "--size", "100x22"], 120, 30, self.env)
        self.assertEqual(code, 0)
        self.assertTrue(restored)
        pos = [(int(y), int(x)) for y, x in re.findall(rb"\x1b\[(\d+);(\d+)H", out)]
        self.assertTrue(pos)
        self.assertLessEqual(max(y for y, _ in pos), 22)
        self.assertLessEqual(max(x for _, x in pos), 100)
        text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", out.decode("utf-8", "replace"))
        self.assertIn("WORKSPACES", text)
        for role in ("lead", "planner", "builder", "reviewer", "qa"):
            self.assertRegex(text, " (\\S+ · )?%s · " % role)

    def test_live_size_ignores_resizes(self):
        code, out, restored = pty_run(["--seed", "1", "--size", "100x22"], 120, 30, self.env, resize=(130, 40))
        self.assertEqual(code, 0)
        pos = [(int(y), int(x)) for y, x in re.findall(rb"\x1b\[(\d+);(\d+)H", out)]
        self.assertLessEqual(max(y for y, _ in pos), 22)
        self.assertLessEqual(max(x for _, x in pos), 100)

    def test_live_size_bigger_than_the_terminal_exits_2(self):
        code, out, restored = pty_run(["--seed", "1", "--size", "100x22"], 83, 23, self.env, keys=None, wait_for=b"error")
        self.assertEqual(code, 2)
        self.assertTrue(restored)
        self.assertIn(b"herdr-screensaver: error: this terminal is 83x23, smaller than --size 100x22; enlarge it or lower the font size", out)
        self.assertNotIn(b"\x1b[?1049h", out)  # refused before the alt screen

    def test_print_size_83x23_compact(self):
        code, out, restored = pty_run(["--print-size"], 83, 23, self.env, wait_for=b"press any key")
        self.assertEqual(code, 0)
        self.assertTrue(restored)
        text = out.decode().replace("\r\n", "\n")
        self.assertIn("size: 83x23 (terminal)\n", text)
        self.assertIn("COLUMNS x LINES: unset x unset\n", text)
        self.assertIn("stty size: 23 83\n", text)
        self.assertIn("tput: 83 x 23\n", text)
        self.assertIn("layout: compact (sidebar 24; panes: lead planner builder reviewer qa)\n", text)
        self.assertIn("why: compact needs >= 80x20; this is 83x23\n", text)
        self.assertIn("press any key to close", text)

    def test_print_size_79x23_narrow(self):
        code, out, _ = pty_run(["--print-size"], 79, 23, self.env, wait_for=b"press any key")
        self.assertEqual(code, 0)
        text = out.decode()
        self.assertIn("size: 79x23 (terminal)", text)
        self.assertIn("layout: narrow (sidebar none; panes: lead planner builder reviewer qa; btop)", text)
        self.assertIn("why: narrow: 79 cols < 80, so tabs instead of a sidebar (the sidebar needs >= 80x20)", text)

    def test_print_size_waits_for_a_key(self):
        code, out, _ = pty_run(["--print-size"], 83, 23, self.env, keys=None, wait_for=b"press any key", timeout=5)
        self.assertLess(code, 0)  # still waiting for a key: the helper had to kill it

    def test_print_size_without_a_tty_exits_at_once(self):
        r = run(["--print-size", "--size", "100x22"], self.env, timeout=10)
        self.assertEqual(r.returncode, 0)
        text = r.stdout.decode()
        self.assertIn("size: 100x22 (--size)", text)
        self.assertIn("layout: compact (sidebar 23; panes: lead planner builder reviewer qa; btop); with an oddball: (sidebar 22; panes: lead planner builder reviewer qa oddball)", text)
        self.assertNotIn("press any key", text)
        r = run(["--print-size"], self.env, timeout=10)
        self.assertIn("size: 80x24 (fallback 80x24 because fd 1 is not a terminal)", r.stdout.decode())
        self.assertFalse(os.path.exists(self.log))

    def test_debug_env_logs_size_class_and_resize_never_to_the_tty(self):
        code, out, _ = pty_run(["--seed", "1"], 83, 23, dict(self.env, HERDR_SS_DEBUG="1"), resize=(100, 22))
        self.assertEqual(code, 0)
        log = open(self.log).read()
        self.assertIn("start: terminal 83x23 (terminal)", log)
        self.assertIn("size: 83x23 layout: compact (sidebar 24;", log)
        self.assertIn("why: compact needs >= 80x20; this is 83x23", log)
        self.assertIn("resize: 100x22 layout: compact", log)
        for word in (b"start:", b"layout:", b"why:", b"resize:", b"debug"):
            self.assertNotIn(word, out)

    def test_debug_flag_file_and_off_by_default(self):
        code, _, _ = pty_run(["--seed", "1"], 83, 23, self.env)
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.log))  # no env, no flag file: no log
        os.makedirs(self.data)
        open(os.path.join(self.data, "debug"), "w").close()
        code, _, _ = pty_run(["--seed", "1"], 79, 23, self.env)
        self.assertEqual(code, 0)
        self.assertIn("why: narrow: 79 cols < 80, so tabs instead of a sidebar", open(self.log).read())

    def test_debug_log_is_capped(self):
        os.makedirs(self.data)
        with open(self.log, "w") as f:
            f.write("old line\n" * 40000)  # 360 KB
        r = run(["--print-size"], dict(self.env, HERDR_SS_DEBUG="1"), timeout=10)
        self.assertEqual(r.returncode, 0)
        size = os.path.getsize(self.log)
        self.assertLess(size, 256 * 1024)
        self.assertIn("print-size: size: 80x24", open(self.log).read().splitlines()[-1])

    def test_help_lists_size_and_print_size(self):
        text = run(["--help"], self.env).stdout.decode()
        self.assertIn("--size WxH", text)
        self.assertIn("live: draw", text)
        self.assertIn("--print-size", text)


if __name__ == "__main__":
    unittest.main()
