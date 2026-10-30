"""Fixed CL6 checkpoints reuse CC's unchanged strict active/retained schema.

Held wrappers have structural labels only. No forwarding, identity preservation,
rollback or agreement between returned-row and held-wrapper parents is assumed.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location('tree_columns_clear_lifetime_basis',
    Path(__file__).with_name('native_1c_tree_columns_clear_contract.py'))
_basis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_basis)
ObservationError = _basis.ObservationError
AvailabilityError = _basis.AvailabilityError
CASE_COUNT = 6
MAX_OUTPUT_BYTES = 8192
CALIBRATION_RECORD = b'CL-C1: [-]\n'
ACTION_COUNTS = (1, 1, 4, 4, 3, 5)
EXTRA_TYPES = ('number', 'row?', 'row') * 4 + ('row', 'tree', 'row?', 'number')
QUERY_NAMES = tuple(f'{handle}.{field}' for handle in ('root_child_rows', 'child_rows', 'grandchild_rows', 'sibling_rows')
                    for field in ('count', 'parent', 'first')) + tuple('returned.' + field for field in ('id', 'owner', 'parent', 'level'))


def need(condition):
    if not condition:
        raise ObservationError('tree_columns_clear_lifetime_observation_invalid')


def snapshot_size():
    return _basis.snapshot_size() + 2 * len(EXTRA_TYPES)


def maximum_record_size(case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    checkpoints = ACTION_COUNTS[case - 1] + 1
    return len(f'CL-{case}: [') + checkpoints * (snapshot_size() + 4) + checkpoints - 1 + 2


MAX_ENCODED_BYTES = len(CALIBRATION_RECORD) + sum(maximum_record_size(case) for case in range(1, 7))


def decode_extra(raw, registry):
    need(len(raw) == 2 * len(EXTRA_TYPES))
    result = []
    for kind, token in zip(EXTRA_TYPES, (raw[i:i+2] for i in range(0, len(raw), 2))):
        if token in ('E_', 'A_'):
            result.append((token[0], None)); continue
        if kind == 'number':
            need(token[0] == 'N'); value = _basis.signed(token[1])
        else:
            need(token[0] == 'I')
            if token[1] == '_':
                need(kind in ('row?', 'tree')); value = None
            else:
                need(token[1] in _basis.IDS); value = _basis.IDS.index(token[1])
                need(value <= len(registry))
                if value == len(registry): registry.append(kind.rstrip('?'))
                need(registry[value] == kind.rstrip('?'))
        result.append((token[0], value))
    return tuple(result)


def validate_payload(payload, case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    need(type(payload) is bytes and len(payload) <= maximum_record_size(case))
    try: text = payload.decode('ascii')
    except UnicodeDecodeError: raise ObservationError('tree_columns_clear_lifetime_observation_invalid') from None
    pieces = text.split('/'); need(len(pieces) == ACTION_COUNTS[case - 1] + 1)
    registry = []; checkpoints = []; available = None
    for index, piece in enumerate(pieces):
        parts = piece.split('~'); need(len(parts) == 3)
        header, core, extra = parts
        need(len(header) == 2 and header[0] in '-SMAO' and header[1] in '0123')
        status, phase = header[0], int(header[1])
        if index == 0 or (index > 1 and not available):
            need(header == '-0')
        else:
            need(status != '-')
            if index == 2 and case in (4, 5, 6):
                need(phase in (1, 2, 3))
                if status == 'S': need(phase == 3)
            else: need(phase == 1)
        snapshot = _basis.decode_snapshot(core, registry)
        queries = decode_extra(extra, registry)
        checkpoints.append({'status': status, 'phase': phase, 'snapshot': snapshot, 'queries': queries})
        if index == 1: available = status == 'S'
    return {'case': case, 'checkpoints': tuple(checkpoints), 'identities': tuple(registry)}


def validate_output(raw):
    need(type(raw) is bytes and len(raw) <= MAX_OUTPUT_BYTES)
    need(all(c == 10 or 32 <= c <= 126 for c in raw))
    lines = raw.splitlines(keepends=True)
    need(len(lines) == CASE_COUNT + 1 and lines[0] == CALIBRATION_RECORD)
    records = []
    for case, line in enumerate(lines[1:], 1):
        prefix = f'CL-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n') and len(line) <= maximum_record_size(case))
        records.append(validate_payload(line[len(prefix):-2], case))
    return tuple(records)


def controls_valid(records):
    for record in records[:2]:
        before, after = record['checkpoints']
        if (after['status'] != 'S' or not before['snapshot']['schema'] or not before['snapshot']['nodes']
                or after['snapshot']['schema'] or after['snapshot']['nodes']): return False
    return True


def require_available(raw):
    records = validate_output(raw)
    if not controls_valid(records): raise AvailabilityError('tree_columns_clear_lifetime_positive_controls_failed')
    return records
