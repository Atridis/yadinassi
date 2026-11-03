"""Temporary, closed ValueStorage wire contract, not a native semantic oracle."""
import re

CASE_COUNT = 27
MESSAGE_COUNT = 28
CALIBRATION = b'VS-C1: [wire-v1]\n'
MAX_RECORD_BYTES = len(b'VS-00: [mutate-original-error]\n')
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES
MAX_OUTPUT_BYTES = MAX_ENCODED_BYTES

class ObservationError(ValueError):
    pass

class AvailabilityError(ObservationError):
    pass

# Case-specific, finite output forms, not expected native answers.
_PAYLOADS = {
    **dict.fromkeys((1, 2, 3, 4, 7, 25, 26, 27), rb'(?:[01]|type)'),
    **dict.fromkeys((5, 6), rb'(?:type-ok|type)'),
    8: rb'(?:[01]{2}|type)',
    **dict.fromkeys((9, 10, 11, 17), rb'(?:[ABCXT]{4}|type)'),
    **dict.fromkeys((12, 13), rb'(?:[ABCXT]{5}|type)'),
    **dict.fromkeys((14, 15, 16, 24), rb'(?:[ABCXT]|type)'),
    **dict.fromkeys((18, 19, 21, 23), rb'[ABCXT]'),
    **dict.fromkeys((20, 22), rb'[01]'),
}
_BASE = frozenset((b'setup', b'construct', b'get1', b'inspect', b'observer'))
_ACTION = frozenset((b'construct', b'get1', b'get2'))
_BAD = frozenset((b'setup', b'mutate-original', b'mutate-get1', b'inspect', b'observer'))

def _phases(case):
    phases = _BASE
    if case in (9, 10, 11, 12, 13, 17):
        phases = phases | {b'mutate-original', b'mutate-get1', b'get2'}
    if case == 24:
        phases = phases | {b'get2'}
    return phases

def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationError('value_storage_output_invalid')
    if not raw.startswith(CALIBRATION):
        raise ObservationError('value_storage_calibration_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('value_storage_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'VS-{case:02d}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('value_storage_record_invalid')
        payload = line[len(prefix):-2]
        if payload.startswith(b'ok|'):
            data = payload[3:]
            if re.fullmatch(_PAYLOADS[case], data) is None:
                raise ObservationError('value_storage_payload_invalid')
            records.append({'case': case, 'status': 'ok', 'value': data.decode('ascii')})
            continue
        if not payload.endswith(b'-error'):
            raise ObservationError('value_storage_status_invalid')
        phase = payload[:-6]
        if phase not in _phases(case):
            raise ObservationError('value_storage_phase_invalid')
        records.append({'case': case, 'status': 'action-error' if phase in _ACTION else 'observer-error',
                        'phase': phase.decode('ascii'), 'value': None})
    return tuple(records)

def require_available(raw):
    records = validate_output(raw)
    if any(record['status'] == 'observer-error' for record in records):
        raise AvailabilityError('value_storage_observer_failed')
    # Syntax controls include a positive Eval of both constructor and method.
    if (any(records[i]['status'] != 'ok' or records[i]['value'] != '1' for i in (0, 1, 2, 3))
            or records[22]['status'] != 'ok' or records[22]['value'] != 'A'):
        raise AvailabilityError('value_storage_positive_controls_failed')
    return records
