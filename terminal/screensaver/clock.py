"""Virtual clock helpers: wall time is now + t, read in LOCAL time; weekday 0 = Sunday (JS getDay)."""
import re
import time


def local_fields(epoch_ms):
    tm = time.localtime(epoch_ms // 1000)
    return {"year": tm.tm_year, "month": tm.tm_mon, "day": tm.tm_mday,
            "weekday": (tm.tm_wday + 1) % 7, "hour": tm.tm_hour, "minute": tm.tm_min}


def when_matches(when, f):
    if not when:
        return True
    if "months" in when and f["month"] not in when["months"]:
        return False
    if "days" in when and f["day"] not in when["days"]:
        return False
    if "weekdays" in when and f["weekday"] not in when["weekdays"]:
        return False
    if "hours" in when and not (when["hours"][0] <= f["hour"] < when["hours"][1]):
        return False
    return True


def date_key(f):
    return "%d-%d-%d" % (f["year"], f["month"], f["day"])


def hhmm(f):
    return "%02d:%02d" % (f["hour"], f["minute"])


_NOW = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$")


def parse_now(v):
    """"2026-12-24T23:30" (local time) or an int (epoch ms) -> epoch ms (int)."""
    if isinstance(v, int):
        return v
    m = _NOW.match(str(v))
    if not m:
        raise ValueError("bad --now %s (want YYYY-MM-DDTHH:MM)" % v)
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h, mi, s = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
    return int(time.mktime((y, mo, d, h, mi, s, 0, 0, -1))) * 1000
