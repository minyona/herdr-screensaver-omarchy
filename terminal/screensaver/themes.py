"""Themes: the 3 bundled ones from content.json, plus `omarchy`, derived from the active Omarchy
theme's colors.toml (v4: $XDG_STATE_HOME/omarchy/current/theme, v3: ~/.config/omarchy/current/theme)."""
import os
import re
import sys

OMARCHY = "omarchy"
KEYS = ("bg", "fg", "muted", "border", "accent", "accent2", "ok", "warn", "err", "info")
# our key -> colors.toml keys, first one present wins
MAPPING = {
    "bg": ("background",), "fg": ("bright_foreground", "foreground"), "muted": ("muted", "dark_foreground"),
    "border": ("selection", "lighter_background"), "accent": ("accent", "blue"), "accent2": ("magenta", "bright_magenta"),
    "ok": ("green",), "warn": ("yellow",), "err": ("red",), "info": ("cyan",),
}
LINE = re.compile(r'^([a-z_]+) = "(#[0-9a-fA-F]{6})"$')


class ThemeError(Exception):
    pass


def bundled(content):
    return sorted(content["themes"])


def omarchy_paths():
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return [os.path.join(state, "omarchy", "current", "theme", "colors.toml"),
            os.path.join(os.path.expanduser("~"), ".config", "omarchy", "current", "theme", "colors.toml")]


def parse_colors_toml(text):
    """Strict flat parser: only `key = "#rrggbb"` lines count; anything else is ignored."""
    out = {}
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if m:
            out[m.group(1)] = m.group(2).lower()
    return out


def omarchy_theme(fallback, warn=None):
    warn = warn or (lambda msg: sys.stderr.write("herdr-screensaver: %s\n" % msg))
    paths = omarchy_paths()
    for p in paths:
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    colors = parse_colors_toml(f.read())
            except OSError:
                continue
            theme, missing = {"name": OMARCHY}, []
            for key in KEYS:
                v = next((colors[k] for k in MAPPING[key] if k in colors), None)
                if v is None:
                    missing.append(key)
                    v = fallback[key]
                theme[key] = v
            if missing:
                warn("omarchy theme: %s has no colour for %s; using %s for those" % (p.replace(os.path.expanduser("~"), "~"), ", ".join(missing), fallback["name"]))
            return theme
    warn("no Omarchy theme colors.toml found (looked in %s); using %s" % (" and ".join(p.replace(os.path.expanduser("~"), "~") for p in paths), fallback["name"]))
    return dict(fallback)


def resolve(name, content, warn=None):
    if name == OMARCHY:
        return omarchy_theme(content["themes"]["tokyonight"], warn)
    if name not in content["themes"]:
        raise ThemeError("unknown theme %r (have %s, %s)" % (name, " ".join(bundled(content)), OMARCHY))
    return content["themes"][name]
