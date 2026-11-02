"""Bounded HTTP family measurement wire grammar; no native expected semantic values."""
import re

SOURCE_SHA256 = '83ed3c4e5263580df0b30c2bd3b7f44d602e913ee79ee47eaa4cd623de6f3702'
CASE_COUNT = 40
MAX_STRING_UNITS = 40
MAX_OUTPUT_BYTES = 8192
CALIBRATION = b'HT-C1: [S0:]\nHT-C2: [S6:004100a0003b0022d83dde00]\n'
# Fixed ASCII label/framing + maximum two-digit length + four hex digits per unit.
MAX_RECORD_BYTES = len(b'HT-00: [ok|S40:') + MAX_STRING_UNITS * 4 + len(b']\n')
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES

class ObservationError(ValueError):
    pass

class AvailabilityError(ObservationError):
    pass


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationError('http_family_output_invalid')
    if not raw.startswith(CALIBRATION):
        raise ObservationError('http_family_calibration_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('http_family_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'HT-{case:02d}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('http_family_record_invalid')
        payload = line[len(prefix):-2]
        if payload in (b'action-error', b'observer-error'):
            records.append({'case': case, 'status': payload.decode('ascii'), 'units': None})
            continue
        match = re.fullmatch(rb'ok\|S(0|[1-9][0-9]?):([0-9a-f]*)', payload)
        if match is None:
            raise ObservationError('http_family_string_invalid')
        count = int(match[1])
        encoded = match[2]
        if count > MAX_STRING_UNITS or len(encoded) != count * 4:
            raise ObservationError('http_family_length_invalid')
        units = tuple(int(encoded[i:i+4], 16) for i in range(0, len(encoded), 4))
        records.append({'case': case, 'status': 'ok', 'units': units})
    return tuple(records)


def require_available(raw):
    records = validate_output(raw)
    if any(record['status'] != 'ok' for record in (records[index] for index in range(CASE_COUNT))):
        raise AvailabilityError('http_family_positive_controls_failed')
    if any(record['status'] == 'observer-error' for record in records):
        raise AvailabilityError('http_family_observer_failed')
    return records
