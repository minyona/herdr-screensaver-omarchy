"""Generic filler text the crew types (cosmetic rng only), like web/src/crew.js."""
import re

from .prng import hash32

PLAN_STEPS = [
    "add a small pure helper, keep the public api",
    "move the magic numbers into constants",
    "handle the empty and null cases first",
    "log once per failure, not per retry",
    "no new dependencies",
    "guard the slow path behind a flag",
    "write the test first, then argue with it",
    "keep the diff small enough to review",
]
EDGE_CASES = ["empty input", "timeout", "unicode", "huge payload", "duplicate keys", "clock skew", "leap day"]
FUNCS = ["load", "parse", "fetch", "render", "flush", "normalize", "retry", "apply"]
FINDINGS_OK = [
    "handles the empty input path",
    "tests cover the timeout branch",
    "no new dependencies",
    "names match the existing style",
    "error messages are readable",
    "no secrets or paths in logs",
]
FINDINGS_BUG = [
    "retry loop ignores the timeout",
    "off-by-one on the last page",
    "null slips through the guard",
    "exception swallowed in the catch block",
    "cache key misses the locale",
]
OLD = ["  for (const item of items) {", "    return handle(item);", "  } catch (e) {", "    // ignore", "  const timeout = 30;"]
NEW = [
    "  if (!items.length) return [];",
    "  for (let attempt = 0; attempt < retries; attempt++) {",
    "    const result = handle(items, { timeout: TIMEOUT });",
    "    if (result.ok) return result.value;",
    "    log.warn('retry %d', attempt);",
    "  }",
    "  throw new RetryError(retries);",
]


def sample(r, arr, k):
    return r.shuffle(list(arr))[:k]


def between(r, lo, hi):
    return lo + r.randint(hi - lo + 1)


def mod_name(ws):
    parts = [p for p in re.split(r"[^a-z0-9]+", ws["repo"], flags=re.I) if p]
    return parts[0] if parts else "app"


def hex7(s):
    return format(hash32(s) & 0xFFFFFFF, "07x")


def banner(agent):
    return [("agent %s ready (%s)" % (agent["name"], agent["kind"]), "head"), ("# %s" % agent["quirk"], "dim")]


def lead_prompt(target, n, verb, task=None):
    return [('herdr agent prompt %s "%s t%d%s"' % (target, verb, n, ": " + task if task else ""), "cmd")]


def lead_wake(role, n, verdict=None):
    return [("[%s] done: reports/%s-t%d.md%s" % (role, role, n, " (%s)" % verdict if verdict else ""), "text")]


def plan(r, ws, n, task):
    mod = mod_name(ws)
    edges = sample(r, EDGE_CASES, 2)
    out = [("Plan t%d: %s" % (n, task), "head"), ("- read src/%s.js and tests/%s.test.js" % (mod, mod), "text")]
    out += [("- " + s, "text") for s in sample(r, PLAN_STEPS, 3)]
    out += [("- edge cases: %s, %s" % (edges[0], edges[1]), "text"),
            ("- acceptance: %d checks, all green" % between(r, 3, 6), "text"),
            ("plan written: reports/plan-t%d.md" % n, "dim")]
    return out


def _diff(r, mod, func, adds, dels):
    line = between(r, 12, 180)
    out = [("diff --git a/src/%s.js b/src/%s.js" % (mod, mod), "dim"),
           ("@@ -%d,%d +%d,%d @@ function %s(" % (line, 4 + dels, line, 4 + adds, func), "hunk"),
           (" function %s(items, retries = 3) {" % func, "text")]
    out += [("-" + t, "del") for t in OLD[:dels]]
    out += [("+" + t, "add") for t in NEW[:adds]]
    out.append(("1 file changed, %d insertions(+), %d deletions(-)" % (adds, dels), "dim"))
    return out


def build(r, ws, n):
    mod, func = mod_name(ws), r.pick(FUNCS)
    out = [("$ edit src/%s.js" % mod, "cmd"), ("reading src/%s.js (%d lines)" % (mod, between(r, 80, 400)), "dim")]
    adds = between(r, 4, 7)
    out += _diff(r, mod, func, adds, between(r, 1, 4))
    out += [("$ edit tests/%s.test.js" % mod, "cmd"), ("+%d tests for %s" % (between(r, 2, 6), func), "add"),
            ("report: reports/builder-t%d.md" % n, "dim")]
    return out


def rework(r, ws, n):
    mod = mod_name(ws)
    out = [("fix: %s" % r.pick(FINDINGS_BUG), "head")]
    func = r.pick(FUNCS)
    adds = between(r, 2, 4)
    out += _diff(r, mod, func, adds, between(r, 1, 2))
    out.append(("report: reports/builder-t%d-fix.md" % n, "dim"))
    return out


def review(r, ws, n, fail):
    mod = mod_name(ws)
    out = [("reviewing src/%s.js against plan t%d" % (mod, n), "dim")]
    out += [("- [ok] " + f, "text") for f in sample(r, FINDINGS_OK, 3)]
    if fail:
        out += [("- [bug] %s (src/%s.js:%d)" % (r.pick(FINDINGS_BUG), mod, between(r, 12, 200)), "warn"), ("VERDICT: FAIL", "fail")]
    else:
        out.append(("VERDICT: PASS", "pass"))
    return out


def qa(r, ws, n, test_names):
    names = sample(r, test_names, between(r, 4, 7))
    out = [("$ npm test -- %s" % mod_name(ws), "cmd")]
    out += [("%s ... ok" % t, "text") for t in names]
    out += [("-" * 28, "dim"), ("%d passed in 0.%02ds" % (len(names), between(r, 5, 95)), "pass"), ("QA: PASS", "pass")]
    return out


def commit(r, ws, n, commits):
    return [("commit %s %s" % (hex7("%s:%d" % (ws["id"], n)), r.pick(commits)), "pass")]
