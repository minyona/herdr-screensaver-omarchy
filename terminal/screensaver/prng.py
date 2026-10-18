"""sfc32 PRNG, identical to web/src/prng.js: 32-bit masked ops, randint(n) = next() % n,
Fisher-Yates shuffle from the end. The director's trace depends on this being exact."""

M32 = 0xFFFFFFFF


class Rng(object):
    __slots__ = ("a", "b", "c", "d")

    def __init__(self, seed):
        self.a, self.b, self.c, self.d = 0x9E3779B9, 0x243F6A88, 0xB7E15162, seed & M32
        for _ in range(15):
            self.next()

    def next(self):
        a, b, c, d = self.a, self.b, self.c, self.d
        t = (a + b + d) & M32
        self.d = (d + 1) & M32
        self.a = b ^ (b >> 9)
        c2 = (c + (c << 3)) & M32
        self.b = c2
        c3 = ((c << 21) | (c >> 11)) & M32
        self.c = (c3 + t) & M32
        return t

    def randint(self, n):
        return self.next() % n

    def shuffle(self, arr):
        for i in range(len(arr) - 1, 0, -1):
            j = self.randint(i + 1)
            arr[i], arr[j] = arr[j], arr[i]
        return arr

    def float(self):
        """Cosmetic animation only (never used by the director)."""
        return self.next() / 4294967296.0

    def pick(self, arr):
        return arr[self.randint(len(arr))]


def hash32(s):
    """FNV-1a over UTF-16 code units (ASCII here), like hash32() in prng.js."""
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & M32
    return h


def js_seed(x):
    """JS `x | 0` on a seed (signed 32-bit), then the same bits as an unsigned value."""
    return x & M32
