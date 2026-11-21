"""Lazy declared search indexes. Unsupported key domains retain ordered scanning."""
from decimal import Decimal
from types import MappingProxyType
from dataclasses import dataclass

from yadinassi.types.values import NULL

_UNSUPPORTED = object()
_SCALAR_TYPES = (type(None), str, bool, int, Decimal, type(NULL))

def token(value, typed):
    kind = type(value)
    if not any(kind is allowed for allowed in _SCALAR_TYPES):
        return _UNSUPPORTED
    if kind is Decimal and not value.is_finite():
        return _UNSUPPORTED
    return (Decimal if kind is int else kind, value) if typed else value

@dataclass(frozen=True, slots=True)
class _Entry:
    epoch: object
    buckets: object
    row_slots: int = 0


def _positions(rows, positions):
    if type(positions) is not tuple:
        raise ValueError('invalid index positions')
    for position in positions:
        if type(position) is not int or not 0 <= position < len(rows):
            raise ValueError('invalid index position')
        yield rows[position]


class SearchIndexes:
    __slots__ = ('declarations', 'cache', 'builds')
    def __init__(self):
        self.declarations = set()
        self.cache = {}
        self.builds = 0

    def declare(self, names):
        signature = tuple(sorted(names))
        if not signature or len(set(signature)) != len(signature):
            raise ValueError('index requires distinct columns')
        self.declarations.add(signature)
        return signature

    def clear(self):
        self.declarations.clear()
        self.cache.clear()

    def candidates(self, rows, selected, epoch, typed):
        signature = tuple(sorted(offset for offset, _ in selected))
        if signature not in self.declarations:
            return rows
        values = dict(selected)
        wanted = tuple(token(values[offset], typed) for offset in signature)
        if any(value is _UNSUPPORTED for value in wanted):
            return rows
        entry = self.cache.get(signature)
        if entry is not None:
            if type(entry) is not _Entry:
                raise ValueError('invalid index entry')
            stamp=entry.epoch
            if not (type(stamp) is int or (type(stamp) is tuple and all(type(i) is int for i in stamp))):
                raise ValueError('invalid index epoch')
            if entry.buckets is not None and type(entry.buckets) is not MappingProxyType:
                raise ValueError('invalid index buckets')
        if entry is None or entry.epoch != epoch:
            # Bound retained row-position slots without work on each write.
            if len(rows) > 200_000:
                return rows
            if (len(self.cache) >= 8 and signature not in self.cache) or sum(e.row_slots for key,e in self.cache.items() if key != signature) + len(rows) > 200_000:
                self.cache.clear()
            buckets = {}
            for position, row in enumerate(rows):
                key = tuple(token(list.__getitem__(row, offset), typed) for offset in signature)
                if any(value is _UNSUPPORTED for value in key):
                    # Do not preempt linear short-circuit/error semantics.
                    buckets = None
                    break
                buckets.setdefault(key, []).append(position)
            if buckets is not None:
                buckets=MappingProxyType({key:tuple(positions) for key,positions in buckets.items()})
            self.cache[signature] = _Entry(epoch, buckets, len(rows) if buckets is not None else 0)
            self.builds += 1
        else:
            buckets = entry.buckets
        return rows if buckets is None else _positions(rows, buckets.get(wanted, ()))

# Same definition-time integrity contract as the table data kernel.
_DIRECT_CLASSES=tuple((cls,cls.__mro__,tuple(vars(cls).items())) for cls in (SearchIndexes,_Entry))
_DIRECT_FUNCTIONS=tuple((fn,fn.__code__,fn.__defaults__,tuple((fn.__kwdefaults__ or {}).items()))
    for fn in [token,_positions,*vars(SearchIndexes).values()] if type(fn) is type(token))
_DIRECT_BINDINGS=tuple((name,value) for name,value in tuple(globals().items()) if callable(value) or name in ('_UNSUPPORTED', '_SCALAR_TYPES'))
_DIRECT_NAMES=frozenset((*globals(), '_DIRECT_NAMES'))
