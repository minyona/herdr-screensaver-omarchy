"""ANSI encoding of a Grid (from screensaver-v2 screen.py): truecolor or xterm-256, full or diff."""

RESET = "\x1b[0m"


def hex_to_rgb(s):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


_CUBE = (0, 95, 135, 175, 215, 255)


def _cube_index(v):
    if v < 48:
        return 0
    if v < 115:
        return 1
    return (v - 35) // 40


def rgb_to_256(r, g, b):
    """Nearest xterm-256 color: the 6x6x6 cube or the 24-step gray ramp."""
    ri, gi, bi = _cube_index(r), _cube_index(g), _cube_index(b)
    cr, cg, cb = _CUBE[ri], _CUBE[gi], _CUBE[bi]
    d_cube = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
    avg = (r + g + b) // 3
    gray = 23 if avg > 238 else max(0, (avg - 3) // 10)
    gv = 8 + 10 * gray
    d_gray = (r - gv) ** 2 + (g - gv) ** 2 + (b - gv) ** 2
    if d_gray < d_cube:
        return 232 + gray
    return 16 + 36 * ri + 6 * gi + bi


class Encoder:
    """Turns grids (cells of (ch, fg, bg, bold)) into escape sequences. mode is "truecolor" or "256"."""

    def __init__(self, mode="truecolor"):
        if mode not in ("truecolor", "256"):
            raise ValueError("color mode must be truecolor or 256, got %r" % (mode,))
        self.mode = mode
        self._sgr = {}

    def _color(self, base, hexs):
        r, g, b = hex_to_rgb(hexs)
        if self.mode == "truecolor":
            return "%d;2;%d;%d;%d" % (base, r, g, b)
        return "%d;5;%d" % (base, rgb_to_256(r, g, b))

    def sgr(self, key):
        """key = (fg_hex, bg_hex, bold) -> one SGR sequence (cached)."""
        s = self._sgr.get(key)
        if s is None:
            fg, bg, bold = key
            # Colors first so every sequence starts with ESC[38;... (bold/normal last).
            s = "\x1b[%s;%s;%sm" % (self._color(38, fg), self._color(48, bg), "1" if bold else "22")
            self._sgr[key] = s
        return s

    def full(self, canvas):
        out = [RESET]
        state = None
        w, cells = canvas.w, canvas.cells
        for y in range(canvas.h):
            out.append("\x1b[%d;1H" % (y + 1))
            for c in cells[y * w:(y + 1) * w]:
                key = c[1:]
                if key != state:
                    out.append(self.sgr(key))
                    state = key
                out.append(c[0])
        return "".join(out)

    def diff(self, prev, canvas):
        """Only the cells that changed since prev (falls back to full on size change)."""
        if prev is None or prev.w != canvas.w or prev.h != canvas.h:
            return self.full(canvas)
        out = []
        state = None
        w, pc, cc = canvas.w, prev.cells, canvas.cells
        for y in range(canvas.h):
            a = y * w
            if pc[a:a + w] == cc[a:a + w]:
                continue
            cur = -1
            for x in range(w):
                c = cc[a + x]
                if c == pc[a + x]:
                    continue
                if x != cur:
                    out.append("\x1b[%d;%dH" % (y + 1, x + 1))
                key = c[1:]
                if key != state:
                    out.append(self.sgr(key))
                    state = key
                out.append(c[0])
                cur = x + 1
        return "".join(out)


def to_ansi(canvas, mode):
    """Whole frame as SGR-colored text: one line per row, each row ends with a reset."""
    enc = Encoder(mode)
    w, cells = canvas.w, canvas.cells
    rows = []
    for y in range(canvas.h):
        out = []
        state = None
        for c in cells[y * w:(y + 1) * w]:
            key = c[1:]
            if key != state:
                out.append(enc.sgr(key))
                state = key
            out.append(c[0])
        out.append(RESET)
        rows.append("".join(out))
    return "\n".join(rows)


def to_plain(canvas):
    w, cells = canvas.w, canvas.cells
    return "\n".join("".join(c[0] for c in cells[y * w:(y + 1) * w]) for y in range(canvas.h))
