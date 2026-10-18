"""Cell grid like web/src/grid.js: w*h cells of [ch, fg, bg, bold]."""

BOX_TL, BOX_TR, BOX_BL, BOX_BR, BOX_H, BOX_V = "╭", "╮", "╰", "╯", "─", "│"
ELL = "…"
BREAKS = " -/_"


def fit(text, w):
    """Text for w columns, readably (terminal classes below "full"), never cut inside a word and
    never shortened silently: the whole text, or its longest whole-word prefix (a space, - / or _
    ends a word) followed by "…". If not even the first word plus "…" fits: nothing (callers
    leave the label out)."""
    if len(text) <= w:
        return text
    if w <= 0:
        return ""
    best = ""
    for i, c in enumerate(text):
        if c not in BREAKS or i == 0:
            continue
        head = text[:i].rstrip(BREAKS)
        if not head:
            continue
        cand = head + ELL if len(head) + 1 <= w else ""
        if len(cand) > len(best):
            best = cand
    return best


def _pieces(word, width):
    """A word longer than the width: a rule line (one repeated symbol) is trimmed; otherwise it
    breaks after its own - / _ (snake_case, paths) onto the next row; only a word with no such
    break is cut, with "…"."""
    if len(set(word)) == 1 and not word[0].isalnum():
        return [word[:width]]
    out = []
    while len(word) > width:
        cut = max(word.rfind(c, 0, width) for c in "-/_")
        if cut <= 0:
            out.append(word[:width - 1] + ELL)
            return out
        out.append(word[:cut + 1])
        word = word[cut + 1:]
    return out + [word]


def wrap_readable(text, width):
    """Like channels.wrap, but a word longer than the width never splits mid-word (see _pieces):
    its pieces go on rows of their own, the first one after the row's last word if it fits."""
    if width <= 0:
        return [text]
    rows, cur = [], ""
    for word in text.split(" "):
        pieces = _pieces(word, width) if len(word) > width else [word]
        for i, piece in enumerate(pieces):
            if i == 0 and cur and len(cur) + 1 + len(piece) <= width:
                cur += " " + piece
            elif i == 0 and not cur:
                cur = piece
            else:
                rows.append(cur)
                cur = piece
    rows.append(cur)
    return rows


class Grid(object):
    def __init__(self, w, h, bg="#000000", fg="#ffffff"):
        self.w, self.h = w, h
        self.cells = [(" ", fg, bg, False)] * (w * h)

    def clear(self, bg, fg):
        self.cells = [(" ", fg, bg, False)] * (self.w * self.h)

    def put(self, x, y, text, fg, bg=None, bold=False):
        if y < 0 or y >= self.h or not text:
            return
        start, end = max(0, -x), min(len(text), self.w - x)
        base = y * self.w + x
        cells = self.cells
        for i in range(start, end):
            j = base + i
            cells[j] = (text[i], fg, cells[j][2] if bg is None else bg, bool(bold))

    def fill(self, r, ch, fg, bg):
        x0, x1 = max(0, r["x"]), min(self.w, r["x"] + r["w"])
        y0, y1 = max(0, r["y"]), min(self.h, r["y"] + r["h"])
        if x0 >= x1:
            return
        run = [(ch, fg, bg, False)] * (x1 - x0)
        for y in range(y0, y1):
            self.cells[y * self.w + x0:y * self.w + x1] = run

    def box(self, r, title, fg, title_fg, bold=False):
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        if w < 2 or h < 2:
            return
        self.put(x, y, BOX_TL + BOX_H * (w - 2) + BOX_TR, fg)
        self.put(x, y + h - 1, BOX_BL + BOX_H * (w - 2) + BOX_BR, fg)
        for yy in range(y + 1, y + h - 1):
            self.put(x, yy, BOX_V, fg)
            self.put(x + w - 1, yy, BOX_V, fg)
        if title and w > 6:
            t = title if len(title) <= w - 6 else title[:w - 7] + "…"
            self.put(x + 2, y, " " + t + " ", title_fg, None, bold)

    def plain(self):
        w = self.w
        return "".join("".join(c[0] for c in self.cells[y * w:(y + 1) * w]) + "\n" for y in range(self.h))


def inner(r):
    return {"x": r["x"] + 1, "y": r["y"] + 1, "w": max(0, r["w"] - 2), "h": max(0, r["h"] - 2)}
