"""Versioned bounded JSON envelope for source scratch ValueStorage only.

Never a 1C codec, pickle, object loader, or executable deserializer. Private
snapshot primitives are converted through a closed tagged grammar, then the
existing full snapshot validator reconstructs an independent runtime value.
"""
import base64
from decimal import Decimal
from .value_storage import BSLValueStorage, Snapshot, restore

VERSION = 'yadinassi-source-storage-v1'
MAX_DEPTH = 160
MAX_NODES = 60000
MAX_WIRE_UNITS = 60000


class _Budget:
    def __init__(self):
        self.nodes = 0
        self.units = 0

    def node(self, depth):
        self.nodes += 1
        self.units += 8
        if depth > MAX_DEPTH or self.nodes > MAX_NODES or self.units > MAX_WIRE_UNITS:
            raise ValueError('source ValueStorage framing bound')

    def payload(self, length):
        self.units += length
        if self.units > MAX_WIRE_UNITS:
            raise ValueError('source ValueStorage payload bound')


def _pack(value, budget, depth=0):
    budget.node(depth)
    kind = type(value)
    if kind is tuple:
        if len(value) > MAX_NODES - budget.nodes:
            raise ValueError('source ValueStorage tuple bound')
        return ['t', [_pack(item, budget, depth + 1) for item in value]]
    if kind is str:
        budget.payload(len(value)); return ['s', value]
    if kind is bool:
        return ['b', value]
    if kind is int:
        if value.bit_length() > 128:
            raise ValueError('source ValueStorage integer bound')
        return ['i', str(value)]
    if kind is Decimal:
        if not value.is_finite() or value.__sizeof__() > 8192:
            raise ValueError('source ValueStorage number bound')
        text = str(value)
        budget.payload(len(text)); return ['n', text]
    if kind is bytes:
        budget.payload(2 * len(value))
        return ['x', base64.b64encode(value).decode('ascii')]
    raise TypeError('unsupported source ValueStorage snapshot primitive')


def _unpack(node, budget, depth=0):
    budget.node(depth)
    if type(node) is not list or len(node) != 2 or type(node[0]) is not str:
        raise ValueError('source ValueStorage framing integrity')
    tag, value = node
    if tag == 't' and type(value) is list:
        if len(value) > MAX_NODES - budget.nodes:
            raise ValueError('source ValueStorage tuple bound')
        return tuple(_unpack(item, budget, depth + 1) for item in value)
    if tag == 'b' and type(value) is bool:
        return value
    if type(value) is not str:
        raise ValueError('source ValueStorage primitive integrity')
    budget.payload(len(value))
    if tag == 's':
        return value
    if tag == 'i':
        if len(value) > 40:
            raise ValueError('source ValueStorage integer bound')
        result = int(value)
        if result.bit_length() > 128 or str(result) != value:
            raise ValueError('source ValueStorage integer integrity')
        return result
    if tag == 'n':
        if len(value) > 8192:
            raise ValueError('source ValueStorage number bound')
        result = Decimal(value)
        if not result.is_finite() or str(result) != value or result.__sizeof__() > 8192:
            raise ValueError('source ValueStorage number integrity')
        return result
    if tag == 'x':
        result = base64.b64decode(value, validate=True)
        if base64.b64encode(result).decode('ascii') != value:
            raise ValueError('source ValueStorage binary integrity')
        return result
    raise ValueError('source ValueStorage unknown primitive tag')


def encode_storage(value):
    if type(value) is not BSLValueStorage:
        raise TypeError('constant ValueStorage required')
    snapshot = object.__getattribute__(value, '_snapshot')
    if type(snapshot) is not Snapshot:
        raise ValueError('source ValueStorage snapshot integrity')
    wire = _pack(object.__getattribute__(snapshot, '_root'), _Budget())
    restore(snapshot)  # Full type/schema/compression/graph budgets, no callbacks.
    return [VERSION, wire]


def decode_storage(payload):
    if (type(payload) is not list or len(payload) != 2 or payload[0] != VERSION):
        raise ValueError('source ValueStorage version integrity')
    snapshot = Snapshot(_unpack(payload[1], _Budget()))
    restore(snapshot)
    return BSLValueStorage._from_snapshot(snapshot)
