"""Bounded host-lifetime owned-form results, not a callback wire codec."""
from dataclasses import dataclass
from .structures import BSLStructure, BSLFixedStructure
from .invocation import _encode_scalar, _decode_scalar
from .ui.protocol import encode_line, decode_line

MAX_RESULT_FIELDS = 32
MAX_RESULT_BYTES = 65536


def freeze_result(value):
    """Detach the result at Close(), before later BSL can mutate its source."""
    if type(value) in (BSLStructure, BSLFixedStructure):
        if len(value._items) > MAX_RESULT_FIELDS:
            raise ValueError('owned form result field limit')
        items = []
        for pair in value:
            if type(pair.key) is not str or not pair.key.isidentifier() or len(pair.key) > 128:
                raise ValueError('owned form result field name')
            items.append([pair.key, _encode_scalar(pair.value)])
        packet = {'kind': 'structure', 'items': items}
    else:
        packet = {'kind': 'scalar', 'value': _encode_scalar(value)}
    raw = encode_line(packet)
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError('owned form result byte limit')
    return raw


def result_value(raw):
    packet = decode_line(raw)
    if packet['kind'] == 'scalar':
        return _decode_scalar(packet['value'])
    result = BSLStructure()
    for key, value in packet['items']:
        result.insert(key, _decode_scalar(value))
    return result


@dataclass(slots=True)
class OwnedFormResult:
    owner: str
    callback: object
    enrollment: object
    result: bytes
    child: str | None = None
    state: str = 'queued'

