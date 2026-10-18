"""found N of M, like web/src/found.js."""


class Found(object):
    def __init__(self, initial, pool_ids):
        self.pool = set(pool_ids)
        self.set = set(i for i in initial if i in self.pool)
        self.total = len(self.pool)
        self._cbs = []

    def has(self, eid):
        return eid in self.set

    def count(self):
        return len(self.set)

    def on_found(self, cb):
        self._cbs.append(cb)

    def add(self, eid):
        if eid not in self.pool or eid in self.set:
            return False
        self.set.add(eid)
        for cb in self._cbs:
            cb(eid)
        return True


def found_label(n, total, bump=0):
    shown = n + bump
    if n >= total and total > 0 and not bump:
        return "found %d of %d · all of them. go outside." % (total, total)
    return "found %d of %d" % (shown, total)
