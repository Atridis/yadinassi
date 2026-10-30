"""CT: fixed six-case tail probe using unchanged CM snapshot grammar.

The fixed sibling is an explicit staged dependency, not a dynamic source path.
No before/after behavior, conversion order or successful boundaries are assumed.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'tree_columns_move_tail_basis',
    Path(__file__).with_name('native_1c_tree_columns_move_contract.py'))
_basis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_basis)
ObservationError = _basis.ObservationError
AvailabilityError = _basis.AvailabilityError
CASE_COUNT = 6
MAX_OUTPUT_BYTES = 8192
CALIBRATION_RECORD = b'CT-C1: [-]\n'
snapshot_size = _basis.snapshot_size


def need(condition):
    if not condition:
        raise ObservationError('tree_columns_move_tail_observation_invalid')


def maximum_record_size(case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    return len(f'CT-{case}: [S/') + 2 * snapshot_size(3, 5) + 3


MAX_ENCODED_BYTES = len(CALIBRATION_RECORD) + sum(
    maximum_record_size(case) for case in range(1, CASE_COUNT + 1))


def validate_payload(payload, case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    # CM case1 is the shared three-column/five-row domain and excludes E.
    result = _basis.validate_payload(payload, 1)
    return {**result, 'case': case}


def validate_output(raw):
    need(type(raw) is bytes and len(raw) <= MAX_OUTPUT_BYTES)
    need(all(value == 10 or 32 <= value <= 126 for value in raw))
    lines = raw.splitlines(keepends=True)
    need(len(lines) == CASE_COUNT + 1 and lines[0] == CALIBRATION_RECORD)
    result = []
    for case, line in enumerate(lines[1:], 1):
        prefix = f'CT-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n')
             and len(line) <= maximum_record_size(case))
        result.append(validate_payload(line[len(prefix):-2], case))
    return tuple(result)


def require_available(raw):
    result = validate_output(raw)
    if any(result[index]['status'] != 'S' for index in (0, 1)):
        raise AvailabilityError('tree_columns_move_tail_positive_controls_failed')
    return result
