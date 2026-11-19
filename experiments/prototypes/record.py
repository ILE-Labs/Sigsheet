"""Record which fields of a decoded file a computation reads (for the CKB IDL boundary check, X2).

`wrap(doc, log)` returns a read-only view of a JSON-like document; every key or index the computation reads is
added to `log` as a path such as `transaction.inputs[0].previous_output.tx_hash`. `summarize(log)` collapses
indices (`[]`) and hash-like map keys (`{}`) so the paths can be compared across cases.
"""
import re
from collections.abc import Mapping, Sequence


class RDict(Mapping):
    def __init__(self, d, path, log, alias=None, child_alias=None):
        self._d, self._p, self._log, self._alias, self._ca = d, path, log, alias or {}, child_alias

    def _key(self, k):
        return self._alias.get(k, k)

    def __getitem__(self, k):
        real = self._key(k)
        p = f"{self._p}.{real}" if self._p else str(real)
        self._log.add(p)
        return wrap(self._d[real], p, self._log, self._ca)

    def get(self, k, default=None):
        real = self._key(k)
        p = f"{self._p}.{real}" if self._p else str(real)
        self._log.add(p)
        if real in self._d:
            return wrap(self._d[real], p, self._log, self._ca)
        return default

    def __contains__(self, k):
        real = self._key(k)
        self._log.add(f"{self._p}.{real}" if self._p else str(real))
        return real in self._d

    def __iter__(self):
        self._log.add(f"{self._p}.*keys")
        return iter(self._d)

    def __len__(self):
        self._log.add(f"{self._p}.*keys")
        return len(self._d)


class RList(Sequence):
    def __init__(self, lst, path, log):
        self._l, self._p, self._log = lst, path, log

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(len(self._l)))]
        p = f"{self._p}[{i}]"
        self._log.add(p)
        return wrap(self._l[i], p, self._log)

    def __len__(self):
        self._log.add(f"{self._p}[#]")
        return len(self._l)

    def __iter__(self):
        self._log.add(f"{self._p}[#]")
        for i in range(len(self._l)):
            yield self[i]


def wrap(v, path, log, alias=None, child_alias=None):
    if isinstance(v, dict):
        return RDict(v, path, log, alias, child_alias)
    if isinstance(v, list):
        return RList(v, path, log)
    return v


HASHKEY = re.compile(r"\.0x[0-9a-f]{40,64}")


def summarize(log):
    out = set()
    for p in log:
        p = HASHKEY.sub(".{}", p)
        p = re.sub(r"\[\d+\]", "[]", p)
        out.add(p)
    return sorted(out)
