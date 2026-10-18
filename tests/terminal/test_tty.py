"""Live mode in a real pty: a key or a mouse move exits within 1 s and the terminal is restored."""
import os
import fcntl
import pty
import select
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import BIN  # noqa: E402

LEAVE = b"\x1b[?1006l\x1b[?1003l\x1b[?25h\x1b[?1049l"


class TtyTest(unittest.TestCase):
    def _session(self, payload):
        tmp = tempfile.mkdtemp(prefix="herdr-tty-")
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
        before = termios.tcgetattr(slave)
        env = dict(os.environ, XDG_STATE_HOME=os.path.join(tmp, "state"), HOME=os.path.join(tmp, "home"), TERM="xterm-256color")
        p = subprocess.Popen([BIN, "--seed", "1"], stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
        out = b""
        try:
            deadline = time.monotonic() + 15
            while b"herdr" not in out and time.monotonic() < deadline:   # first frame painted
                r, _, _ = select.select([master], [], [], 0.2)
                if r:
                    out += os.read(master, 65536)
            time.sleep(0.5)  # past the start-up grace
            sent = time.monotonic()
            os.write(master, payload)
            while p.poll() is None and time.monotonic() - sent < 3:
                r, _, _ = select.select([master], [], [], 0.05)
                if r:
                    try:
                        out += os.read(master, 65536)
                    except OSError:
                        break
            took = time.monotonic() - sent
            try:
                while select.select([master], [], [], 0.2)[0]:
                    out += os.read(master, 65536)
            except OSError:
                pass
            after = termios.tcgetattr(slave)
        finally:
            if p.poll() is None:
                p.kill()
            os.close(master)
            os.close(slave)
            shutil.rmtree(tmp)
        return p.returncode, took, out, before, after

    def check(self, payload):
        code, took, out, before, after = self._session(payload)
        self.assertEqual(code, 0)
        self.assertLessEqual(took, 1.0, "exit took %.2fs" % took)
        self.assertTrue(out.rstrip(b"\r\n").endswith(LEAVE), out[-80:])
        # PENDIN (pending-input retype) is a transient kernel bit, not a mode we set or restore
        pend = getattr(termios, "PENDIN", 0)
        before[3] &= ~pend
        after[3] &= ~pend
        self.assertEqual(before, after, "tty attributes restored")
        self.assertIn(b"found ", out)

    def test_key_exits(self):
        self.check(b"q")

    def test_mouse_motion_exits(self):
        self.check(b"\x1b[<35;10;10M")  # SGR mouse report for a plain move (mode 1003)


if __name__ == "__main__":
    unittest.main()
