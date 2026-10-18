"""Raw-mode terminal session: alt screen, hidden cursor, mouse reporting, guaranteed restore."""
import os
import select
import signal
import termios
import tty

# Restore order matters: tests expect output to end with mouse-off, cursor-on, alt-screen-off.
ENTER = "\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[?1003h\x1b[?1006h\x1b[0m\x1b[2J\x1b[H"
LEAVE = "\x1b[0m\x1b[?7h\x1b[?1006l\x1b[?1003l\x1b[?25h\x1b[?1049l"


def measure(fd=1):
    """(cols, rows, source) of the terminal on fd; 80x24 with the reason when it cannot be known."""
    try:
        sz = os.get_terminal_size(fd)
    except OSError:
        return 80, 24, "fallback 80x24 because fd %d is not a terminal" % fd
    if sz.columns <= 0 or sz.lines <= 0:   # a fresh pty can report 0x0
        return 80, 24, "fallback 80x24 because the terminal reported %dx%d" % (sz.columns, sz.lines)
    return sz.columns, sz.lines, "terminal"


class Terminated(Exception):
    """Raised inside the main loop on SIGTERM/SIGHUP so the context manager can restore the tty."""


class Terminal:
    def __init__(self, infd=0, outfd=1):
        self.infd, self.outfd = infd, outfd
        self.resized = False
        self._saved_attrs = None
        self._saved_handlers = {}

    def __enter__(self):
        self._saved_attrs = termios.tcgetattr(self.infd)
        for sig in (signal.SIGTERM, signal.SIGHUP):
            self._saved_handlers[sig] = signal.signal(sig, self._on_term)
        self._saved_handlers[signal.SIGWINCH] = signal.signal(signal.SIGWINCH, self._on_winch)
        tty.setraw(self.infd, termios.TCSANOW)
        self.write(ENTER)
        termios.tcflush(self.infd, termios.TCIFLUSH)
        return self

    def __exit__(self, exc_type, exc, tb):
        # Ignore further TERM/HUP while restoring, so cleanup cannot be cut short.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            self.write(LEAVE)
        except OSError:
            pass
        try:
            termios.tcsetattr(self.infd, termios.TCSADRAIN, self._saved_attrs)
        except termios.error:
            pass
        for sig, handler in self._saved_handlers.items():
            signal.signal(sig, handler)
        return False

    def _on_term(self, signum, frame):
        raise Terminated(signum)

    def _on_winch(self, signum, frame):
        self.resized = True

    def size(self):
        return measure(self.outfd)[:2]

    def write(self, text):
        data = text.encode("utf-8")
        while data:
            n = os.write(self.outfd, data)
            data = data[n:]

    def read(self, timeout):
        """Bytes typed within timeout seconds (b"" if none). Raises EOFError if the tty went away."""
        r, _, _ = select.select([self.infd], [], [], max(0.0, timeout))
        if not r:
            return b""
        try:
            data = os.read(self.infd, 4096)
        except OSError:
            raise EOFError
        if not data:
            raise EOFError
        return data
