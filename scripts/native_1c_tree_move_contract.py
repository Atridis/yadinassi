"""Finite Move observation grammar; contains no assumed native action answers."""
from itertools import permutations

BASE_RECORDS = 1021
CASE_COUNT = 32
PAYLOAD_SIZE = 1 + CASE_COUNT * 6
MAX_MESSAGE_UNITS = 6 + PAYLOAD_SIZE
ROOT_ORDERS = frozenset(b''.join(p) for p in permutations((b'A', b'B', b'C')))
CHILD_ORDERS = frozenset((b'DE', b'ED'))


class ObservationError(ValueError):
    pass


def _reject():
    raise ObservationError('tree_move_observation_invalid')


def validate_payload(payload):
    if type(payload) is not bytes or len(payload) != PAYLOAD_SIZE or payload[:1] != b'1':
        _reject()
    observations = []
    for case in range(1, CASE_COUNT + 1):
        part = payload[1 + (case - 1) * 6:1 + case * 6]
        outcome, order = part[:1], part[1:]
        if outcome not in ((b'0', b'2') if case == 32 else (b'0', b'1')):
            _reject()
        if case == 25:
            if order != b'-----':
                _reject()
        elif case == 26:
            if order != b'A----':
                _reject()
        elif order[:3] not in ROOT_ORDERS or order[3:] not in CHILD_ORDERS:
            _reject()
        observations.append((case, outcome, order))
    return tuple(observations)


def validate_records(records):
    """Require the exact whole record count and sole final TM framing.

    The caller independently validates the exact prior1021-record Load prefix.
    Case positions are fixed by the source-bound ordered32-case BSL loop.
    """
    if type(records) is not list or len(records) != BASE_RECORDS + 1:
        _reject()
    record = records[-1]
    if type(record) is not tuple or len(record) != 3:
        _reject()
    label, framed, payload = record
    if label != 'TM' or type(framed) is not bytes or type(payload) is not bytes:
        _reject()
    if framed != b'TM: [' + payload + b']\n':
        _reject()
    validate_payload(payload)
    units = len(framed) - 1
    if units != MAX_MESSAGE_UNITS:
        _reject()
    return {'records': 1, 'message_units': units}
