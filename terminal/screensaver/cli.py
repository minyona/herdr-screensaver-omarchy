"""Command line: headless runs (dump/trace, used by tests and parity) and the live terminal loop."""
import argparse
import math
import os
import random
import re
import subprocess
import sys
import time

from . import content as content_mod
from . import themes
from .clock import parse_now
from .director import Engine, trace_line
from .grid import Grid
from .layout import COMPACT, FULL, NARROW, SMALL, compute_layout
from .screen import Encoder, to_ansi

PROG = "herdr-screensaver"
GRACE = 0.3        # seconds after start-up during which input does not exit
MAX_DT = 250       # ms clamp for long stalls (suspended terminal)
MAX_SIZE = 1000
ANIM_TAIL_MS = 128000  # headless: animate btop only for the last 128 virtual s (cosmetic)
HEADLESS_SIZE = (160, 50)
DEBUG_CAP = 256 * 1024  # debug.log is cut to its newest half when it grows past this


def _int_in(lo, hi, what):
    def parse(s):
        try:
            v = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError("%s must be an integer %d-%d, got %r" % (what, lo, hi, s))
        if not lo <= v <= hi:
            raise argparse.ArgumentTypeError("%s must be %d-%d, got %d" % (what, lo, hi, v))
        return v
    return parse


def _egg_rate(s):
    try:
        v = float(s)
    except ValueError:
        v = float("nan")
    if not (math.isfinite(v) and 0 <= v <= 600):
        raise argparse.ArgumentTypeError("egg rate must be a number 0-600 (eggs per minute), got %r" % s)
    return int(v) if v == int(v) else v


def _frames(s):
    try:
        v = int(s)
    except ValueError:
        v = -1
    if v < 0:
        raise argparse.ArgumentTypeError("frames must be a non-negative integer, got %r" % s)
    return v


def _size(s):
    m = re.match(r"\A(\d+)x(\d+)\Z", s)
    if not m or not (1 <= int(m.group(1)) <= MAX_SIZE and 1 <= int(m.group(2)) <= MAX_SIZE):
        raise argparse.ArgumentTypeError("size must be WxH with W and H in 1-%d, got %r" % (MAX_SIZE, s))
    return int(m.group(1)), int(m.group(2))


def _now(s):
    try:
        return parse_now(s)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def build_parser():
    p = argparse.ArgumentParser(prog=PROG, description="A screensaver that pretends to be a Herdr session: everything on screen is "
                                "fake but looks real, generated live (the agents aren't real, no coding, no network; it never touches your "
                                "files, except its own found-eggs list). Hidden easter eggs. Any key or mouse move exits.")
    p.add_argument("--theme", default="tokyonight", metavar="NAME", help="tokyonight, catppuccin, gruvbox, or omarchy (follows the current Omarchy theme)")
    p.add_argument("--list-themes", action="store_true", help="print the bundled theme names and exit")
    p.add_argument("--fps", type=_int_in(1, 60, "fps"), default=20, metavar="N", help="frames per second, 1-60 (default 20)")
    p.add_argument("--egg-rate", type=_egg_rate, default=5, metavar="N", help="easter eggs per minute, 0-600 (default 5)")
    p.add_argument("--seed", type=int, default=None, metavar="N", help="random seed (default: random)")
    p.add_argument("--now", type=_now, default=None, metavar="YYYY-MM-DDTHH:MM", help="pretend the local time is this (default: now)")
    p.add_argument("--color", choices=("auto", "truecolor", "256"), default="auto", help="auto = truecolor if COLORTERM says so, else 256")
    p.add_argument("--found-file", default=None, metavar="PATH",
                   help="where found eggs are kept (default: ${HERDR_SS_DATA:-~/.local/share/herdr-screensaver-plugin}/found)")
    p.add_argument("--content", default=None, metavar="PATH", help="content.json to use (default: next to the engine)")
    p.add_argument("--frames", type=_frames, default=None, metavar="N", help="headless: run N frames on a virtual clock (no terminal)")
    p.add_argument("--size", type=_size, default=None, metavar="WxH",
                   help="headless: the frame size (default 160x50); live: draw exactly WxH at the top left and ignore resizes "
                   "(exits 2 if the terminal is smaller)")
    p.add_argument("--print-size", action="store_true",
                   help="print the terminal size (and stty/tput/$COLUMNS), the layout it gets and why, then wait for a key (on a terminal)")
    p.add_argument("--dump", action="store_true", help="with --frames: print the final frame (ANSI)")
    p.add_argument("--plain", action="store_true", help="with --dump: plain text, no escapes")
    p.add_argument("--trace", default=None, metavar="PATH", help="with --frames: write the director trace as JSONL")
    p.add_argument("--egg-log", default=None, metavar="PATH", help="with --frames: write t<TAB>id<TAB>channel<TAB>text per egg shown")
    return p


def _fail(msg):
    sys.stderr.write("%s: error: %s\n" % (PROG, msg))
    return 2


def _write_stdout(text):
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def data_dir():
    """The plugin's data dir: $HERDR_SS_DATA (tests; session.sh exports it), else
    ~/.local/share/herdr-screensaver-plugin."""
    return os.environ.get("HERDR_SS_DATA") or os.path.join(os.path.expanduser("~"), ".local", "share", "herdr-screensaver-plugin")


def debug_enabled():
    """HERDR_SS_DEBUG=1 (or any value but 0), or the file <data dir>/debug (which also
    reaches a saver started by Hyprland or the idle timer, where no env var can be passed)."""
    v = os.environ.get("HERDR_SS_DEBUG", "")
    return (v != "" and v != "0") or os.path.exists(os.path.join(data_dir(), "debug"))


class DebugLog(object):
    """Appends timestamped lines to <data dir>/debug.log when debug is on. Never
    writes to the terminal (live, stderr is the screen) and never fails the screensaver."""

    def __init__(self, on):
        self.path = os.path.join(data_dir(), "debug.log") if on else None

    def __call__(self, msg):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.exists(self.path) and os.path.getsize(self.path) > DEBUG_CAP:
                with open(self.path, "rb") as f:
                    f.seek(-DEBUG_CAP // 2, os.SEEK_END)
                    tail = f.read()
                tail = tail[tail.find(b"\n") + 1:]
                with open(self.path, "wb") as f:
                    f.write(tail)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write("%s pid %d %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), os.getpid(), msg))
        except OSError:
            pass


def layout_report(w, h):
    """(class, "layout: ..." line, "why: ..." line) for a WxH screen. The layout depends on the focused
    workspace's oddballs too: when one changes it, the line adds "with an oddball: ..." (layout of 1)."""
    def desc(r):
        panes = " ".join(k for k in ("lead", "planner", "builder", "reviewer", "qa") if k in r)
        panes += " oddball" if "odd0" in r else ""
        panes += "".join("; " + k for k in ("btop", "fetch") if k in r)
        return "sidebar %s; panes: %s" % (r["sidebar"]["w"] if "sidebar" in r else "none", panes)
    L = compute_layout(w, h)
    cls, plain, odd = L["cls"], desc(L["rects"]), desc(compute_layout(w, h, 1)["rects"])
    line = "layout: %s (%s)" % (cls, plain) + ("; with an oddball: (%s)" % odd if odd != plain else "")
    if cls == "full":
        why = "full needs >= %dx%d; this is %dx%d" % (FULL[0], FULL[1], w, h)
    elif cls == "compact":
        why = "compact needs >= %dx%d; this is %dx%d" % (COMPACT[0], COMPACT[1], w, h)
    elif cls == "narrow":
        short = "%d cols < %d" % (w, COMPACT[0]) if w < COMPACT[0] else "%d rows < %d" % (h, COMPACT[1])
        why = "narrow: %s, so tabs instead of a sidebar (the sidebar needs >= %dx%d)" % (short, COMPACT[0], COMPACT[1])
    elif cls == "small":
        why = "small: %dx%d is under %dx%d, so the team shows as tabs" % (w, h, NARROW[0], NARROW[1])
    else:
        why = "tiny: %dx%d is under %dx%d, so only the lead pane" % (w, h, SMALL[0], SMALL[1])
    return cls, line, "why: " + why


def _probe(cmd, stderr=None):
    """stdout of cmd, or "unavailable". stdin (stty) and stderr (tput) stay on the terminal so they see its size."""
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=stderr, timeout=5).stdout.decode().strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return out or "unavailable"


def print_size(args, log):
    from .term import measure

    if args.size:
        (w, h), source = args.size, "--size"
    else:
        w, h, source = measure(sys.stdout.fileno())
    cls, line, why = layout_report(w, h)
    lines = ["size: %dx%d (%s)" % (w, h, source),
             "COLUMNS x LINES: %s x %s" % (os.environ.get("COLUMNS", "unset"), os.environ.get("LINES", "unset")),
             "stty size: %s" % _probe(["stty", "size"], subprocess.DEVNULL),
             "tput: %s x %s" % (_probe(["tput", "cols"]), _probe(["tput", "lines"])),
             line, why]
    log("print-size: " + " | ".join(lines) + " | TERM=%s" % os.environ.get("TERM", "unset"))
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    _write_stdout("\n".join(lines) + "\n" + ("press any key to close\n" if interactive else ""))
    if interactive:
        import termios
        import tty
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd, termios.TCSANOW)
            os.read(fd, 1)
        except (OSError, KeyboardInterrupt):
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    return 0


def color_mode(choice):
    if choice != "auto":
        return choice
    return "truecolor" if os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") else "256"


def default_found_file():
    return os.path.join(data_dir(), "found")


class FoundStore(object):
    """Append-only file of found egg ids, de-duplicated on load."""

    def __init__(self, path):
        self.path = path
        self.ids = []
        if os.path.isfile(path):
            seen = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    i = line.strip()
                    if i and i not in seen:
                        seen.add(i)
                        self.ids.append(i)
        self._f = None

    def append(self, eid):
        if self._f is None:
            d = os.path.dirname(self.path)
            if d:
                os.makedirs(d, exist_ok=True)
            self._f = open(self.path, "a", encoding="utf-8")
        self._f.write(eid + "\n")
        self._f.flush()

    def close(self):
        if self._f:
            self._f.close()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        content = content_mod.load(args.content)
    except content_mod.ContentError as e:
        return _fail(str(e))
    if args.list_themes:
        _write_stdout(" ".join(themes.bundled(content)) + "\n")
        return 0
    try:
        theme = themes.resolve(args.theme, content)
    except themes.ThemeError as e:
        return _fail(str(e))
    if args.frames is None and (args.dump or args.trace or args.egg_log):
        return _fail("--dump, --trace and --egg-log need --frames N")
    if args.plain and not args.dump:
        return _fail("--plain needs --dump")
    try:
        store = FoundStore(args.found_file or default_found_file())
    except OSError as e:
        return _fail("cannot read the found file: %s" % e)
    seed = args.seed if args.seed is not None else random.randrange(2 ** 31)
    now = args.now if args.now is not None else int(time.time() * 1000)
    mode = color_mode(args.color)
    log = DebugLog(debug_enabled())
    try:
        if args.print_size:
            return print_size(args, log)
        if args.frames is not None:
            return headless(args, content, theme, store, seed, now, mode)
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return _fail("needs an interactive terminal (use --frames N for headless output)")
        return live(args, content, theme, store, seed, now, mode, log)
    finally:
        store.close()


def make_engine(args, content, theme, store, seed, now, w, h, animate=True):
    eng = Engine(content, w, h, seed=seed, now=now, found=store.ids, egg_rate=args.egg_rate,
                 theme=theme["name"] if theme["name"] in content["themes"] else None, animate=animate)
    if theme["name"] not in content["themes"]:
        eng.state.theme_override = theme
        eng.state.theme_name = theme["name"]
    eng.on_found(store.append)
    return eng


def headless(args, content, theme, store, seed, now, mode):
    w, h = args.size or HEADLESS_SIZE
    eng = make_engine(args, content, theme, store, seed, now, w, h, animate=False)
    total = eng.state.found.total
    sys.stderr.write("%s: start found %d of %d\n" % (PROG, eng.found_count(), total))
    dt = 1000.0 / args.fps
    acc = 0.0
    anim_from = args.frames - int(ANIM_TAIL_MS / dt)
    for f in range(args.frames):
        if f >= anim_from:
            eng.state.animate = True
        acc += dt
        step = math.floor(acc)
        acc -= step
        eng.update(step)
    if args.trace:
        with open(args.trace, "w", encoding="utf-8") as fh:
            fh.write("".join(trace_line(e) + "\n" for e in eng.trace))
    if args.egg_log:
        S = eng.state
        with open(args.egg_log, "w", encoding="utf-8") as fh:
            fh.write("".join("%d\t%s\t%s\t%s\n" % (e[0], e[3], e[4], S.eggs[e[3]]["text"]) for e in eng.trace if e[1] == "egg"))
    if args.dump:
        g = Grid(w, h)
        eng.draw(g)
        _write_stdout(g.plain() if args.plain else to_ansi(g, mode) + "\n")
    i = eng.info()
    sys.stderr.write("%s: %dx%d t=%dms ws=%s end found %d of %d\n" % (PROG, i["cols"], i["rows"], i["t"], i["ws"], i["found"], i["total"]))
    return 0


def live(args, content, theme, store, seed, now, mode, log):
    from .term import Terminal, Terminated, measure

    tw, th, source = measure(sys.stdout.fileno())
    log("start: terminal %dx%d (%s), TERM=%s, --size %s" % (tw, th, source, os.environ.get("TERM", "unset"),
                                                              "%dx%d" % args.size if args.size else "unset"))
    if args.size and (tw < args.size[0] or th < args.size[1]):
        log("refused: terminal smaller than --size")
        return _fail("this terminal is %dx%d, smaller than --size %dx%d; enlarge it or lower the font size" % (tw, th, args.size[0], args.size[1]))

    def chosen(w, h, what):
        cls, line, why = layout_report(w, h)
        log("%s: %dx%d %s | %s" % (what, w, h, line, why))

    try:
        with Terminal() as term:
            w, h = args.size or term.size()
            chosen(w, h, "size")
            eng = make_engine(args, content, theme, store, seed, now, w, h)
            enc = Encoder(mode)
            frame_ms = 1000.0 / args.fps
            start = last = time.monotonic()
            prev = None
            while True:
                tick = time.monotonic()
                if term.resized:
                    term.resized = False
                    if args.size:   # fixed size: keep drawing WxH at the top left
                        log("resize to %dx%d ignored (--size)" % term.size())
                        term.write("\x1b[0m\x1b[2J")   # the area outside WxH stays blank
                    else:
                        w, h = term.size()
                        chosen(w, h, "resize")
                        eng.resize(w, h)
                    prev = None
                eng.update(min((tick - last) * 1000.0, MAX_DT))
                last = tick
                g = Grid(w, h)
                eng.draw(g)
                term.write(enc.diff(prev, g))
                prev = g
                data = term.read(frame_ms / 1000.0 - (time.monotonic() - tick))
                if data and time.monotonic() - start >= GRACE:
                    break
    except (Terminated, EOFError, KeyboardInterrupt):
        pass
    return 0
