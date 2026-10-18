#!/usr/bin/env python3
"""An independent manifest checker, written from https://plugins.omarchy.org/develop.html and publish.html
(not from the marketplace code): JSON parses; schemaVersion 1; id, name, version, author, description present;
id lowercase, not omarchy.*, a reverse-domain style id; version <= 64 chars; kinds non-empty and known; one
entryPoints key per kind with its documented file; entry paths safe and relative; every entry file exists;
keepLoaded only with service; no symlink anywhere in the tracked tree; preview at most one root file.

  python3 -I tests/check_manifest.py [repo]      check the repo (its git-tracked files)
  python3 -I tests/check_manifest.py --self-test  also run the negative cases on mutated temp copies
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

KINDS = {  # kind -> (entryPoints key, documented file name)
    "bar-widget": ("barWidget", "BarWidget.qml"),
    "panel": ("panel", "Panel.qml"),
    "overlay": ("overlay", "Overlay.qml"),
    "menu": ("menu", "Menu.qml"),
    "service": ("service", "Service.qml"),
    "bar": ("bar", "Bar.qml"),
}
REQUIRED = ("schemaVersion", "id", "name", "version", "author", "description", "kinds", "entryPoints")
ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$")
PREVIEWS = ("preview.png", "preview.jpg", "preview.jpeg", "preview.webp", "preview.avif")


def tracked(root):
    """[(path, mode)] of the tracked files (git ls-files -s), or every file when root is not a git repo."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-s"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True).stdout.decode()
        return [(l.split("\t", 1)[1], l.split()[0]) for l in out.splitlines() if l]
    except (subprocess.CalledProcessError, OSError):
        res = []
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x != ".git"]
            for f in files + [x for x in dirs if os.path.islink(os.path.join(d, x))]:
                p = os.path.join(d, f)
                res.append((os.path.relpath(p, root), "120000" if os.path.islink(p) else "100644"))
        return res


def safe_rel(p):
    return isinstance(p, str) and p and not p.startswith("/") and "\\" not in p and ".." not in p.split("/") and not re.match(r"^[A-Za-z]:", p) and "\0" not in p


def check(root):
    errs = []
    try:
        with open(os.path.join(root, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as e:
        return ["manifest.json: %s" % e]
    if not isinstance(m, dict):
        return ["manifest.json is not an object"]
    for k in REQUIRED:
        if k not in m:
            errs.append("missing field: " + k)
    if m.get("schemaVersion") != 1:
        errs.append("schemaVersion must be 1")
    for k in ("id", "name", "version", "author", "description"):
        if k in m and (not isinstance(m[k], str) or not m[k].strip()):
            errs.append("%s must be a non-empty string" % k)
    pid = m.get("id", "")
    if isinstance(pid, str):
        if pid != pid.lower():
            errs.append("id must be lowercase")
        if pid.startswith("omarchy."):
            errs.append("id must not start with omarchy.")
        if not ID_RE.match(pid):
            errs.append("id is not a reverse-domain style id: %r" % pid)
    if isinstance(m.get("version"), str) and len(m["version"]) > 64:
        errs.append("version longer than 64 characters")
    kinds = m.get("kinds")
    eps = m.get("entryPoints")
    if not isinstance(kinds, list) or not kinds:
        errs.append("kinds must be a non-empty list")
        kinds = []
    if not isinstance(eps, dict):
        errs.append("entryPoints must be an object")
        eps = {}
    files = dict(tracked(root))
    for k in kinds:
        if k not in KINDS:
            errs.append("unknown kind: %r" % k)
            continue
        key, fname = KINDS[k]
        if key not in eps:
            errs.append("kind %s needs entryPoints.%s" % (k, key))
            continue
        p = eps[key]
        if not safe_rel(p):
            errs.append("entryPoints.%s is not a safe relative path: %r" % (key, p))
        elif p not in files:
            errs.append("entryPoints.%s: %s is not a tracked file" % (key, p))
        elif os.path.basename(p) != fname:
            errs.append("entryPoints.%s: expected a %s file, got %s" % (key, fname, p))
    for key in eps:
        if key not in [v[0] for k, v in KINDS.items() if k in kinds]:
            errs.append("entryPoints.%s has no matching kind" % key)
    if m.get("keepLoaded") and "service" not in kinds:
        errs.append("keepLoaded is for service plugins")
    links = [p for p, mode in files.items() if mode == "120000"]
    if links:
        errs.append("symlinks in the repo: %s" % ", ".join(links))
    previews = [p for p in PREVIEWS if p in files]
    if len(previews) > 1:
        errs.append("more than one root preview: %s" % previews)
    for p in previews:
        if os.path.getsize(os.path.join(root, p)) > 50 * 1024 * 1024:
            errs.append("%s is over 50 MB" % p)
    for doc in ("README.md", "LICENSE"):
        if doc not in files:
            errs.append("missing root " + doc)
    return errs


def self_test(root):
    """Each mutation on a temp copy must fail with the expected message."""
    cases = [
        ("bad json", lambda m: "{", "manifest.json"),
        ("no schemaVersion", lambda m: drop(m, "schemaVersion"), "missing field: schemaVersion"),
        ("schemaVersion 2", lambda m: put(m, "schemaVersion", 2), "schemaVersion must be 1"),
        ("no author", lambda m: drop(m, "author"), "missing field: author"),
        ("empty name", lambda m: put(m, "name", " "), "name must be a non-empty string"),
        ("omarchy id", lambda m: put(m, "id", "omarchy.herdr"), "must not start with omarchy."),
        ("uppercase id", lambda m: put(m, "id", "io.github.Minyona.x"), "id must be lowercase"),
        ("version 65", lambda m: put(m, "version", "1" * 65), "version longer than 64"),
        ("unknown kind", lambda m: put(m, "kinds", ["widget"]), "unknown kind"),
        ("kind without entry", lambda m: put(m, "kinds", ["service", "panel"]), "kind panel needs entryPoints.panel"),
        ("absolute entry", lambda m: put(m, "entryPoints", {"service": "/etc/Service.qml"}), "not a safe relative path"),
        ("dotdot entry", lambda m: put(m, "entryPoints", {"service": "../Service.qml"}), "not a safe relative path"),
        ("missing entry file", lambda m: put(m, "entryPoints", {"service": "Nope/Service.qml"}), "is not a tracked file"),
        ("wrong entry file", lambda m: put(m, "entryPoints", {"service": "Model.js"}), "expected a Service.qml file"),
        ("extra entry key", lambda m: put(m, "entryPoints", {"service": "Service.qml", "panel": "Service.qml"}), "entryPoints.panel has no matching kind"),
        ("keepLoaded without service", lambda m: put(put(m, "kinds", ["panel"]), "entryPoints", {"panel": "Service.qml"}), "keepLoaded is for service plugins"),
    ]
    fails = 0
    for name, mut, want in cases:
        errs = run_mutated(root, mut)
        hit = any(want in e for e in errs)
        print("%s  negative: %s -> %s" % ("ok  " if hit else "FAIL", name, errs[0] if errs else "no error"))
        fails += not hit
    # a symlink in the tree
    tmp = copy(root)
    try:
        os.symlink("README.md", os.path.join(tmp, "link.md"))
        subprocess.run(["git", "-C", tmp, "add", "link.md"], check=True)
        errs = check(tmp)
        hit = any("symlinks in the repo" in e for e in errs)
        print("%s  negative: a tracked symlink -> %s" % ("ok  " if hit else "FAIL", errs[0] if errs else "no error"))
        fails += not hit
        os.remove(os.path.join(tmp, "link.md"))
        subprocess.run(["git", "-C", tmp, "rm", "-q", "--cached", "link.md"], check=True)
        for f in ("LICENSE",):
            subprocess.run(["git", "-C", tmp, "rm", "-q", f], check=True)
        errs = check(tmp)
        hit = any("missing root LICENSE" in e for e in errs)
        print("%s  negative: no LICENSE -> %s" % ("ok  " if hit else "FAIL", errs[0] if errs else "no error"))
        fails += not hit
    finally:
        shutil.rmtree(tmp)
    return fails


def drop(m, k):
    m = dict(m)
    m.pop(k, None)
    return m


def put(m, k, v):
    m = dict(m)
    m[k] = v
    return m


def copy(root):
    tmp = tempfile.mkdtemp(prefix="herdr-manifest-")
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", root, os.path.join(tmp, "r")], check=True)
    # the working tree's manifest and entry files (they may be newer than HEAD)
    for f in ("manifest.json",):
        shutil.copy(os.path.join(root, f), os.path.join(tmp, "r", f))
    return os.path.join(tmp, "r")


def run_mutated(root, mut):
    tmp = copy(root)
    try:
        with open(os.path.join(tmp, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        new = mut(m)
        with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
            f.write(new if isinstance(new, str) else json.dumps(new))
        return check(tmp)
    finally:
        shutil.rmtree(os.path.dirname(tmp))


def main(argv):
    args = [a for a in argv[1:] if a != "--self-test"]
    root = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    errs = check(root)
    for e in errs:
        print("FAIL " + e)
    if not errs:
        m = json.load(open(os.path.join(root, "manifest.json"), encoding="utf-8"))
        print("ok   manifest: %s %s, kinds %s, entry %s; %d tracked files, no symlinks; README.md + LICENSE present"
              % (m["id"], m["version"], m["kinds"], m["entryPoints"], len(tracked(root))))
    fails = len(errs)
    if "--self-test" in argv:
        fails += self_test(root)
    print("check_manifest: %s" % ("PASS" if not fails else "FAILED (%d)" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
