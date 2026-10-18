"""Runs lib/session.sh in a 160x50 pty (as the screensaver terminal would) and ends it with:
  key      a key press                         mouse    an SGR mouse motion report
  focus    focus moves away (the fake hyprctl's $FAKE_ACTIVE file)
  term     kill -TERM <session>                 hup      kill -HUP <session>
  int      kill -INT <session>                  quit     kill -QUIT <session>
  ctrlc    a Ctrl+C byte typed (the tty's INTR character)
  hupclose the terminal goes away: the pty master is closed (the pty is the session's controlling tty)
  wait     nothing (the engine ends by itself: crash / non-zero exit)
Options: --limit S (wait after the action, default 5), --ready BYTES (seen once started, default herdr),
--settle S (run time before the action, default 8: the first egg slot is at ~5 s),
--before CMD (a command run, with this environment, just before the action; e.g. Omarchy's own lock),
--ignore-intquit 1 (start the session with SIGINT and SIGQUIT ignored, as an & job of a script would).
Prints one JSON line: {exit, took, restored, frame, left_alt_screen, found, pid}."""
import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time

how, bash, session, active_file, found_file = sys.argv[1:6]
opts = dict(zip(sys.argv[6::2], sys.argv[7::2]))
limit = float(opts.get("--limit", 5))
ready = opts.get("--ready", "herdr").encode().decode("unicode_escape").encode("latin-1")
settle = float(opts.get("--settle", 8))
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
before = termios.tcgetattr(master)  # macOS revokes the slave when the session ends; the master reflects it


def pre():
    if how in ("hupclose", "ctrlc"):
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    if opts.get("--ignore-intquit"):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGQUIT, signal.SIG_IGN)


p = subprocess.Popen([bash, session, "--seed", "1", "--egg-rate", "600"], stdin=slave, stdout=slave, stderr=slave, close_fds=True,
                     start_new_session=True, preexec_fn=pre)
out = b""
closed = False


def pump(t):
    global out
    if closed:
        time.sleep(t)
        return
    r, _, _ = select.select([master], [], [], t)
    if r:
        try:
            out += os.read(master, 65536)
        except OSError:
            pass


deadline = time.monotonic() + 20
while ready not in out and time.monotonic() < deadline:
    pump(0.2)
end = time.monotonic() + settle
while time.monotonic() < end:
    pump(0.1)
if "--before" in opts:
    subprocess.run(opts["--before"], shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
sent = time.monotonic()
if how == "key":
    os.write(master, b"q")
elif how == "mouse":
    os.write(master, b"\x1b[<35;10;10M")
elif how == "focus":
    with open(active_file, "w") as f:
        f.write("org.example.other-window")
elif how == "term":
    os.kill(p.pid, signal.SIGTERM)
elif how == "hup":
    os.kill(p.pid, signal.SIGHUP)
elif how == "int":
    os.kill(p.pid, signal.SIGINT)
elif how == "quit":
    os.kill(p.pid, signal.SIGQUIT)
elif how == "ctrlc":
    os.write(master, b"\x03")
elif how == "hupclose":
    os.close(slave)
    os.close(master)
    closed = True
while p.poll() is None and time.monotonic() - sent < limit:
    pump(0.05)
took = time.monotonic() - sent
for _ in range(10):
    pump(0.05)
if p.poll() is None:
    p.kill()
    p.wait()
restored = None
if not closed:
    after = termios.tcgetattr(master)
    pend = getattr(termios, "PENDIN", 0)
    before[3] &= ~pend
    after[3] &= ~pend
    restored = before == after
found = open(found_file).read().split() if os.path.exists(found_file) else []
print(json.dumps({"exit": p.returncode, "took": round(took, 2), "restored": restored,
                  "frame": b"found " in out, "left_alt_screen": out.rstrip(b"\r\n").endswith(b"\x1b[?1049l"), "found": len(found), "pid": p.pid}))
