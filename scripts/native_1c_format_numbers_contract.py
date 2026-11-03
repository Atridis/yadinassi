"""Bounded Format measurement wire grammar; no native expected semantic values."""
import re

CASE_COUNT = 48
MAX_STRING_UNITS = 32
MAX_OUTPUT_BYTES = 8192
CALIBRATION = b'FM-C1: [S0:]\nFM-C2: [S6:004100a0003b0022d83dde00]\n'
# Fixed ASCII label/framing + maximum two-digit length + four hex digits per unit.
MAX_RECORD_BYTES = len(b'FM-00: [ok|S32:') + MAX_STRING_UNITS * 4 + len(b']\n')
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES

class ObservationError(ValueError):
    pass

class AvailabilityError(ObservationError):
    pass


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationError('format_numbers_output_invalid')
    if not raw.startswith(CALIBRATION):
        raise ObservationError('format_numbers_calibration_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('format_numbers_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'FM-{case:02d}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('format_numbers_record_invalid')
        payload = line[len(prefix):-2]
        if payload in (b'action-error', b'observer-error'):
            records.append({'case': case, 'status': payload.decode('ascii'), 'units': None})
            continue
        match = re.fullmatch(rb'ok\|S(0|[1-9][0-9]?):([0-9a-f]*)', payload)
        if match is None:
            raise ObservationError('format_numbers_string_invalid')
        count = int(match[1])
        encoded = match[2]
        if count > MAX_STRING_UNITS or len(encoded) != count * 4:
            raise ObservationError('format_numbers_length_invalid')
        units = tuple(int(encoded[i:i+4], 16) for i in range(0, len(encoded), 4))
        records.append({'case': case, 'status': 'ok', 'units': units})
    return tuple(records)


def require_available(raw):
    records = validate_output(raw)
    if any(record['status'] != 'ok' for record in records[:4]):
        raise AvailabilityError('format_numbers_positive_controls_failed')
    if any(record['status'] == 'observer-error' for record in records):
        raise AvailabilityError('format_numbers_observer_failed')
    return records
