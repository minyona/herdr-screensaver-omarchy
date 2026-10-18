import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))      # tests/terminal
ROOT = os.path.dirname(os.path.dirname(HERE))           # the plugin repo
TERMINAL = os.path.join(ROOT, "terminal")
BIN = os.path.join(TERMINAL, "bin", "herdr-screensaver")
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, TERMINAL)

from screensaver import content as content_mod  # noqa: E402


def content():
    return content_mod.load()


def run(args, env=None, timeout=120):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([BIN] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e, timeout=timeout)


def advance(eng, ms, step=1000):
    t = 0
    while t < ms:
        eng.update(min(step, ms - t))
        t += step
    return eng


def frames(eng, n, fps=20):
    dt, acc = 1000.0 / fps, 0.0
    for _ in range(n):
        acc += dt
        s = math.floor(acc)
        acc -= s
        eng.update(s)
    return eng
