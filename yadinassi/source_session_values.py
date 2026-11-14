"""Bounded immutable source session values, without object-reference grants."""
from decimal import Decimal
from .dates import BSLDate
from .maps import BSLFixedMap
from .structures import BSLFixedStructure
from .values import BSLFixedArray, BSLType
from .unique_identifiers import BSLUUID
from .value_storage import BSLValueStorage
from .type_descriptions import BSLTypeDescription

MAX_NODES = 10000
MAX_DEPTH = 32
MAX_UNITS = 16 * 1024 * 1024


def validate_session_value(value):
    pending = [(value, 0, False)]; active = set(); count = units = 0
    while pending:
        item, depth, leaving = pending.pop()
        if leaving:
            active.remove(id(item)); continue
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError('source session value structural limit')
        kind = type(item)
        if item is None or kind in (bool, BSLUUID):
            units += 64
        elif kind is str:
            units += 4 * len(item)
        elif kind is Decimal:
            if not item.is_finite():
                raise TypeError('source session value must be finite')
            units += item.__sizeof__()
        elif kind is BSLDate:
            item.require_known(); units += 64
        elif kind is BSLTypeDescription:
            if any(type(t) is not BSLType for t in item.types):
                raise TypeError('source session reference type descriptions are not supported')
            units += 512
        elif kind is BSLValueStorage:
            # Its constructor owns a bounded immutable snapshot; Get creates
            # separate values rather than publishing mutable session storage.
            storage_units, storage_nodes = _storage_size(item, MAX_UNITS - units, MAX_NODES - count)
            units += storage_units; count += storage_nodes
        elif kind in (BSLFixedArray, BSLFixedMap, BSLFixedStructure):
            if id(item) in active:
                raise ValueError('source session value cycle')
            active.add(id(item)); pending.append((item, depth, True))
            if kind is BSLFixedArray:
                children = item.items
            else:
                if len(item._items) * 2 > MAX_NODES:
                    raise ValueError('source session value structural limit')
                children = tuple(x for pair in item._items.values() for x in pair)
            if count + len(children) + len(pending) > MAX_NODES:
                raise ValueError('source session value structural limit')
            pending.extend((child, depth + 1, False) for child in children)
            units += 64
        else:
            raise TypeError('mutable or unsupported value in source session parameter')
        if units > MAX_UNITS:
            raise ValueError('source session value resource limit')


def _storage_size(storage, unit_budget, node_budget):
    from .value_storage import Snapshot
    snapshot = object.__getattribute__(storage, '_snapshot')
    if type(snapshot) is not Snapshot:
        raise TypeError('invalid source session ValueStorage snapshot')
    pending=[(object.__getattribute__(snapshot, '_root'),0)]
    nodes=0; units=0
    while pending:
        item, depth=pending.pop();nodes+=1
        if nodes>node_budget or depth>256:
            raise ValueError('source session snapshot structural limit')
        kind=type(item)
        if kind is tuple:
            if len(item)+nodes+len(pending)>node_budget:
                raise ValueError('source session snapshot structural limit')
            pending.extend((child,depth+1) for child in item)
            units+=64+8*len(item)
        elif kind is str:
            units+=64+4*len(item)
        elif kind is bytes:
            units+=64+len(item)
        elif kind is Decimal:
            if not item.is_finite():
                raise TypeError('invalid source session snapshot number')
            units+=item.__sizeof__()
        elif item is None or kind in (bool,int):
            units+=64+(item.__sizeof__() if kind is int else 0)
        else:
            raise TypeError('invalid source session snapshot payload')
        if units>unit_budget:
            raise ValueError('source session value resource limit')
    return units,nodes
