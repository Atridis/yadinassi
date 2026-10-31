"""Bounded file I/O family measurement wire grammar; no native expected semantic values."""
import re

CASE_COUNT = 33
MAX_STRING_UNITS = 56
MAX_OUTPUT_BYTES = 8192
CALIBRATION = b'FI-C1: [S0:]\nFI-C2: [S6:004100a0003b0022d83dde00]\n'
# Fixed ASCII label/framing + maximum two-digit length + four hex digits per unit.
MAX_RECORD_BYTES = len(b'FI-00: [ok|S56:') + MAX_STRING_UNITS * 4 + len(b']\n')
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES

class ObservationError(ValueError):
    pass

class AvailabilityError(ObservationError):
    pass


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationError('file_io_family_output_invalid')
    if not raw.startswith(CALIBRATION):
        raise ObservationError('file_io_family_calibration_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('file_io_family_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'FI-{case:02d}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('file_io_family_record_invalid')
        payload = line[len(prefix):-2]
        if payload in (b'action-error', b'observer-error'):
            records.append({'case': case, 'status': payload.decode('ascii'), 'units': None})
            continue
        match = re.fullmatch(rb'ok\|S(0|[1-9][0-9]?):([0-9a-f]*)', payload)
        if match is None:
            raise ObservationError('file_io_family_string_invalid')
        count = int(match[1])
        encoded = match[2]
        if count > MAX_STRING_UNITS or len(encoded) != count * 4:
            raise ObservationError('file_io_family_length_invalid')
        units = tuple(int(encoded[i:i+4], 16) for i in range(0, len(encoded), 4))
        records.append({'case': case, 'status': 'ok', 'units': units})
    return tuple(records)


def require_available(raw):
    records = validate_output(raw)
    if any(record['status'] != 'ok' for record in (records[index] for index in range(CASE_COUNT))):
        raise AvailabilityError('file_io_family_positive_controls_failed')
    if any(record['status'] == 'observer-error' for record in records):
        raise AvailabilityError('file_io_family_observer_failed')
    return records
