"""Finite, exact Total observation grammar; no assumed native answers.

Unknown values and observer failures are diagnostic failures, never parity.
Numeric spellings below are exact decimal values, not locale-formatted output.
"""
BASE_RECORDS = 1022
CASE_COUNT = 32
PAYLOAD_SIZE = 1 + CASE_COUNT
MAX_MESSAGE_UNITS = 6 + PAYLOAD_SIZE
NUMBER_VALUES = ('0', '1', '2', '3', '5', '6', '7', '11', '12', '16', '18', '23', '28')
CASE_NUMBERS = {
    9: ('0', '1.25', '2.5', '3.75'),
    29: ('10000000000000000000000000000', '10000000000000000000000000001', '1', '0'),
    30: ('0', '1', '10000000000000000000000000001'),
    31: ('0', '0.1', '0.2', '0.3'),
}
ALPHABET = b'0123456789ABC'


class ObservationError(ValueError):
    pass


def _reject():
    raise ObservationError('tree_total_observation_invalid')


def validate_payload(payload):
    if type(payload) is not bytes or len(payload) != PAYLOAD_SIZE or payload[:1] != b'1':
        _reject()
    observations = []
    for case in range(1, CASE_COUNT + 1):
        code = payload[case]
        numbers = CASE_NUMBERS.get(case, NUMBER_VALUES)
        if code not in b'EUL' + ALPHABET[:len(numbers)]:
            _reject()
        if code in b'EUL':
            kind, value = {ord('E'): ('exception', None), ord('U'): ('undefined', None),
                           ord('L'): ('null', None)}[code]
        else:
            kind, value = 'number', numbers[ALPHABET.index(code)]
        observations.append((case, kind, value))
    return tuple(observations)


def validate_records(records):
    """Require exact count and sole final TT record; caller verifies prior1022."""
    if type(records) is not list or len(records) != BASE_RECORDS + 1:
        _reject()
    record = records[-1]
    if type(record) is not tuple or len(record) != 3:
        _reject()
    label, framed, payload = record
    if label != 'TT' or type(framed) is not bytes or type(payload) is not bytes:
        _reject()
    if framed != b'TT: [' + payload + b']\n':
        _reject()
    validate_payload(payload)
    if len(framed) - 1 != MAX_MESSAGE_UNITS:
        _reject()
    return {'records': 1, 'message_units': MAX_MESSAGE_UNITS}
