"""Bounded Data hashing family measurement wire grammar; no native expected semantic values."""
import re

SOURCE_SHA256 = '237b2b7df6ec9a16c1e17956b4bfc57c3d8b3cf1826d695fecae1a9e288b6602'
CASE_COUNT = 40
MAX_STRING_UNITS = 40
MAX_OUTPUT_BYTES = 8192
CALIBRATION = b'HF-C1: [S0:]\nHF-C2: [S6:004100a0003b0022d83dde00]\n'
# Fixed ASCII label/framing + maximum two-digit length + four hex digits per unit.
MAX_RECORD_BYTES = len(b'HF-00: [ok|S40:') + MAX_STRING_UNITS * 4 + len(b']\n')
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES
SOURCE_LINE_COUNT = 89
MAX_FAILURE_DIAGNOSTIC_BYTES = 16384
RESULT_FAILURE_CATEGORIES = frozenset(('result_json', 'result_shape', 'result_error',
                                     'result_encoding', 'result_limit'))
RESULT_ERROR_KINDS = frozenset(('identifier', 'function', 'type', 'method',
                                'syntax', 'module', 'other'))

class ObservationError(ValueError):
    pass

class AvailabilityError(ObservationError):
    pass


def validate_failure_diagnostic(value):
    """Finite failed-only witness; case holds an owned source line, never text."""
    if value is None: return
    if (type(value) is not dict or set(value) != {'site', 'case', 'category', 'calibration'}
            or type(value['category']) is not str):
        raise ObservationError('data_hashing_diagnostic_invalid')
    kind = value['calibration']
    if kind is not None and (value['category'] != 'result_error'
            or type(kind) is not str or kind not in RESULT_ERROR_KINDS):
        raise ObservationError('data_hashing_diagnostic_invalid')
    if value['category'] == 'record_count':
        if type(value['site']) is str and value['site'] in ('server', 'client') and value['case'] is None: return
    elif value['category'] in RESULT_FAILURE_CATEGORIES and type(value['site']) is str and value['site'] == 'server':
        line = value['case']
        if line is None or (value['category'] == 'result_error' and type(line) is int and 1 <= line <= SOURCE_LINE_COUNT): return
    raise ObservationError('data_hashing_diagnostic_invalid')


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES:
        raise ObservationError('data_hashing_family_output_invalid')
    if not raw.startswith(CALIBRATION):
        raise ObservationError('data_hashing_family_calibration_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('data_hashing_family_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'HF-{case:02d}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('data_hashing_family_record_invalid')
        payload = line[len(prefix):-2]
        if payload in (b'action-error', b'observer-error'):
            records.append({'case': case, 'status': payload.decode('ascii'), 'units': None})
            continue
        match = re.fullmatch(rb'ok\|S(0|[1-9][0-9]?):([0-9a-f]*)', payload)
        if match is None:
            raise ObservationError('data_hashing_family_string_invalid')
        count = int(match[1])
        encoded = match[2]
        if count > MAX_STRING_UNITS or len(encoded) != count * 4:
            raise ObservationError('data_hashing_family_length_invalid')
        units = tuple(int(encoded[i:i+4], 16) for i in range(0, len(encoded), 4))
        records.append({'case': case, 'status': 'ok', 'units': units})
    return tuple(records)


def require_available(raw):
    records = validate_output(raw)
    if any(record['status'] != 'ok' for record in (records[index] for index in range(CASE_COUNT))):
        raise AvailabilityError('data_hashing_family_positive_controls_failed')
    if any(record['status'] == 'observer-error' for record in records):
        raise AvailabilityError('data_hashing_family_observer_failed')
    return records
