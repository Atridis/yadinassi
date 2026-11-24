"""Bounded preparation reuse for one Eval or Execute activation."""


class FragmentUnitCache:
    """Keep FIFO units; a new unit may displace one after a repeated miss.

    One-off text (or a cyclic working set just larger than the unit limit)
    should not evict the entire hot set. Only bounded process-local hashes
    of successful overflow misses are remembered. A hash collision may affect
    admission, never the exact-key lookup of a compiled fragment.
    """

    __slots__ = ('units', '_source_chars', '_misses')
    _MAX_UNITS = 16

    def __init__(self):
        self.units = {}
        self._source_chars = 0
        self._misses = {}

    def remember(self, key, unit, source_limit):
        units, misses = self.units, self._misses
        size = len(key[0])
        # Double publication must not count identical source twice.
        if size > source_limit or key in units:
            return
        total = self._source_chars
        if len(units) >= self._MAX_UNITS or total + size > source_limit:
            fingerprint = hash(key)
            if fingerprint not in misses:
                misses[fingerprint] = None
                if len(misses) > self._MAX_UNITS:
                    del misses[next(iter(misses))]
                # A trusted host can lower the admission budget between calls.
                while units and total > source_limit:
                    victim = next(iter(units))
                    total -= len(victim[0])
                    del units[victim]
                self._source_chars = total
                return
            del misses[fingerprint]
            while units and (len(units) >= self._MAX_UNITS or total + size > source_limit):
                victim = next(iter(units))
                total -= len(victim[0])
                del units[victim]
        units[key] = unit
        self._source_chars = total + size
