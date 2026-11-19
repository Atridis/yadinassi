"""Bounded host-lifetime owned-form results, not a callback wire codec."""
from dataclasses import dataclass
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.execution.invocation import _encode_scalar, _decode_scalar
from yadinassi.ui.protocol import encode_line, decode_line

MAX_RESULT_FIELDS = 32
MAX_RESULT_BYTES = 65536


def freeze_result(value):
    """Detach the result at Close(), before later BSL can mutate its source."""
    from .direct_form_parameters import structure_items
    fields = structure_items(value)
    if fields is not None:
        if len(fields) > MAX_RESULT_FIELDS:
            raise ValueError('owned form result field limit')
        items = []
        for key, item in fields:
            if type(key) is not str or not key.isidentifier() or len(key) > 128:
                raise ValueError('owned form result field name')
            items.append([key, _encode_scalar(item)])
        packet = {'kind': 'structure', 'items': items}
    else:
        packet = {'kind': 'scalar', 'value': _encode_scalar(value)}
    raw = encode_line(packet)
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError('owned form result byte limit')
    return raw


def result_value(raw, *, direct=False):
    if type(direct) is not bool:raise TypeError('direct result selection requires Boolean')
    packet = decode_line(raw)
    if packet['kind'] == 'scalar':
        return _decode_scalar(packet['value'])
    if direct:
        from yadinassi.execution.codegen.experimental_naked_structure import new_structure
        result = new_structure()
    else:
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

    def finish(self, state):
        """Keep only a tombstone after a known terminal outcome, never replay."""
        self.state = state
        self.callback = None
        self.enrollment = None
        self.result = None

