"""Lazy declared search indexes. Unsupported key domains retain ordered scanning."""
from decimal import Decimal
from types import MappingProxyType
from dataclasses import dataclass

from yadinassi.types.values import NULL
from yadinassi.types.unique_identifiers import BSLUUID, _exact_uuid_text
from .plain_table_storage import mutable_array_kind

_UNSUPPORTED = object()
_ARRAY_IDENTITY = object()
_SCALAR_TYPES = (type(None), str, bool, int, Decimal, type(NULL))

def token(value, typed):
    kind = type(value)
    if not any(kind is allowed for allowed in _SCALAR_TYPES):
        if typed and kind is BSLUUID:
            text = _exact_uuid_text(value)
            if text is not None:
                return BSLUUID, text
        if typed and mutable_array_kind(kind):
            # Rows keep the referent alive for this data epoch; array payload
            # edits do not affect identity, while cell replacement invalidates it.
            return _ARRAY_IDENTITY, id(value)
        # Invalid/unknown domains keep the linear lane's reached-row errors.
        return _UNSUPPORTED
    if kind is Decimal and not value.is_finite():
        return _UNSUPPORTED
    return (Decimal if kind is int else kind, value) if typed else value

@dataclass(frozen=True, slots=True)
class _Entry:
    epoch: object
    buckets: object
    row_slots: int = 0


def _ordered_positions(rows, history):
    if not history:
        yield from range(len(rows))
        return
    # Walk the untouched rows in physical order, then only moved rows in
    # chronological order. No sort, keys, or retained references to rows.
    touched = {}
    for position, row in enumerate(rows):
        identity = id(row)
        if identity in history:
            touched[identity] = position
        else:
            yield position
    for identity in history:
        position = touched.get(identity)
        if position is not None:
            yield position


def _positions(rows, positions):
    if type(positions) is not tuple:
        raise ValueError('invalid index positions')
    for position in positions:
        if type(position) is not int or not 0 <= position < len(rows):
            raise ValueError('invalid index position')
        yield rows[position]


class SearchIndexes:
    __slots__ = ('declarations', 'cache', 'builds', '_active', '_columns', '_history')
    def __init__(self):
        self.declarations = set()
        self.cache = {}
        self.builds = 0

        self._active = self._columns = self._history = None

    def declare(self, names):
        # Bare table and its scalar cache keep their original physical order.
        signature = tuple(sorted(names))
        if not signature or len(set(signature)) != len(signature):
            raise ValueError('index requires distinct columns')
        self.declarations.add(signature)
        return signature

    def bind(self, pairs, *, reset=(), preserve_cache=False):
        """Publish current valid definitions in handle order; never inspect rows."""
        active, columns = {}, {}
        history = {} if self._history is None else self._history
        dropped = set(history)
        for signature, handle in pairs:
            if not signature:
                continue
            identity = id(handle)
            active.setdefault(signature, identity)
            for offset in signature:
                columns.setdefault(offset, []).append(identity)
            dropped.discard(identity)
        dropped.update(reset)
        if preserve_cache and self._active is not None:
            for signature in tuple(self.cache):
                previous = self._active.get(signature)
                current = active.get(signature)
                if current is None or (previous != current
                                        and (previous in history or current in history)):
                    del self.cache[signature]
        else:
            self.cache.clear()
        for identity in dropped:
            history.pop(identity, None)
        if active:
            # Offsets belong to the current ordered table schema. Store the
            # column-to-index links as immutable positional entries.
            links = [()] * (max(columns) + 1)
            for offset, identities in columns.items():
                links[offset] = tuple(identities)
            self._active, self._columns, self._history = active, tuple(links), history
            # Codecs retain this set while admitting individual wire entries.
            self.declarations.clear()
            self.declarations.update(active)
        else:
            self.clear()

    def touch(self, row, offset):
        columns = self._columns
        if 0 <= offset < len(columns) and columns[offset]:
            self._touch(row, columns[offset])

    def _touch(self, row, handles):
        identity = id(row)
        for handle in handles:
            history = self._history.setdefault(handle, {})
            history.pop(identity, None)
            history[identity] = None

    def touch_all(self, row):
        for handles in self._columns:
            if handles:
                self._touch(row, handles)

    def filled(self, offsets):
        columns = self._columns
        for offset in offsets:
            if 0 <= offset < len(columns):
                for handle in columns[offset]:
                    self._history.pop(handle, None)

    def deleted(self, row):
        identity = id(row)
        for history in self._history.values():
            history.pop(identity, None)

    def reordered(self):
        self._history.clear()

    def clear(self):
        self.declarations.clear()
        self.cache.clear()
        self._active = self._columns = self._history = None

    def candidates(self, rows, selected, epoch, typed):
        if not self.declarations:
            return rows
        signature = tuple(sorted(offset for offset, _ in selected))
        if signature not in self.declarations:
            return rows
        history = None if self._active is None else self._history.get(self._active.get(signature))
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
                return rows if not history else (rows[i] for i in _ordered_positions(rows, history))
            if (len(self.cache) >= 8 and signature not in self.cache) or sum(e.row_slots for key,e in self.cache.items() if key != signature) + len(rows) > 200_000:
                self.cache.clear()
            buckets = {}
            for position in _ordered_positions(rows, history):
                row = rows[position]
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
_DIRECT_BINDINGS=tuple((name,value) for name,value in tuple(globals().items()) if callable(value) or name in ('_UNSUPPORTED', '_ARRAY_IDENTITY', '_SCALAR_TYPES'))
_DIRECT_NAMES=frozenset((*globals(), '_DIRECT_NAMES'))
