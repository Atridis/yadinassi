"""Finite ordinary property-transfer snapshots; never predicted native answers."""
import re

CASE_COUNT = 48
SNAPSHOT_SIZE = 43
MAX_OUTPUT_BYTES = 8192
CALIBRATION = b'PV-C1: [wire-v1]\nPV-C2: [N0S0U_L_B0B1]\n'
MAX_RECORD_BYTES = len(b'PV-00: [S///]\n') + 3 * SNAPSHOT_SIZE
MAX_ENCODED_BYTES = len(CALIBRATION) + CASE_COUNT * MAX_RECORD_BYTES
CELL = rb'(?:[ULME]_|B[01]|N[0-9A-E]|S[0-9A-D]|A[0-3]|R[0-3]|C[01])'
SHAPE = rb'(?:[SF][0-9]------|T[0-9]{2}-[0-9]{2}[01]{2}|R[0-9]{3}[01][0-9]00)'
SNAPSHOT = re.compile(rb'(?:' + CELL + rb'){10}(?:' + SHAPE + rb'){2}A[01][SE-](?:' + CELL + rb'){2}')


class ObservationError(ValueError):
    pass


class AvailabilityError(ObservationError):
    pass


def validate_snapshot(raw):
    if type(raw) is not bytes or len(raw) != SNAPSHOT_SIZE or SNAPSHOT.fullmatch(raw) is None:
        raise ObservationError('property_transfer_snapshot_invalid')
    return {'target': tuple(raw[i:i+2].decode('ascii') for i in range(0, 10, 2)),
            'source': tuple(raw[i:i+2].decode('ascii') for i in range(10, 20, 2)),
            'target_shape': raw[20:28].decode('ascii'), 'source_shape': raw[28:36].decode('ascii'),
            'shared': raw[36:38].decode('ascii'), 'setter_status': raw[38:39].decode('ascii'),
            'setter_values': (raw[39:41].decode('ascii'), raw[41:43].decode('ascii'))}


def validate_output(raw):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT_BYTES or not raw.startswith(CALIBRATION):
        raise ObservationError('property_transfer_output_invalid')
    lines = raw[len(CALIBRATION):].splitlines(keepends=True)
    if len(lines) != CASE_COUNT:
        raise ObservationError('property_transfer_count_invalid')
    records = []
    for case, line in enumerate(lines, 1):
        prefix = f'PV-{case:02}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n') or len(line) > MAX_RECORD_BYTES:
            raise ObservationError('property_transfer_record_invalid')
        payload = line[len(prefix):-2]
        if re.fullmatch(rb'X[0-3]', payload):
            records.append({'case': case, 'status': 'observer-error', 'stage': int(payload[1:]), 'snapshots': None})
            continue
        parts = payload.split(b'/')
        if len(parts) != 4 or parts[0] not in (b'S', b'E'):
            raise ObservationError('property_transfer_action_invalid')
        snapshots = tuple(validate_snapshot(part) for part in parts[1:])
        records.append({'case': case, 'status': 'ok' if parts[0] == b'S' else 'action-error',
                        'stage': None, 'snapshots': snapshots})
    return tuple(records)


def require_available(raw):
    records = validate_output(raw)
    if any(row['status'] == 'observer-error' for row in records):
        raise AvailabilityError('property_transfer_observer_failed')
    if any(row['status'] != 'ok' for row in records[:4]):
        raise AvailabilityError('property_transfer_positive_controls_failed')
    return records
