"""Finds and loads content.json (the single source of truth shared with the web/Mac build)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TERMINAL = os.path.dirname(HERE)


class ContentError(Exception):
    pass


def candidates():
    env = os.environ.get("HERDR_CONTENT")
    if env:
        yield env
    yield os.path.join(os.path.dirname(TERMINAL), "content.json")            # packaged: <root>/content.json
    yield os.path.join(os.path.dirname(TERMINAL), "build", "content.json")   # repo: build/content.json


def load(path=None):
    paths = [path] if path else list(candidates())
    for p in paths:
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    c = json.load(f)
            except (OSError, ValueError) as e:
                raise ContentError("cannot read %s: %s" % (p, e))
            if c.get("include_pending"):
                raise ContentError("%s was built with HERDR_INCLUDE_PENDING=1; refusing to run it" % p)
            return c
    raise ContentError("content.json not found (run `node tools/build-content.mjs`, or set HERDR_CONTENT)")
