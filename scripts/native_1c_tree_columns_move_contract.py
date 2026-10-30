"""CM-C1: bounded standalone Columns.Move observations, never assumed native answers.

Rows owner labels encode structure, not native Rows-wrapper identity. The shared
per-case registry records actual tree, columns, column and row identity across
both snapshots. Parsing a missing-method capture is not an availability pass.
"""
import re
from typing import NamedTuple

IDS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
CASE_COUNT = 28
MAX_OUTPUT_BYTES = 8192
MAX_COLUMNS = 3
NODE_LIMITS = tuple(0 if case == 17 else 5
                    for case in range(1, CASE_COUNT + 1))
CALIBRATION_RECORD = b'CM-C1: [-]\n'


class ObservationError(ValueError):
    pass


class AvailabilityError(ValueError):
    pass


class RowObservation(NamedTuple):
    row: int
    parent: int | None
    owner: int
    level: int
    children_owner: int
    child_count: int
    cells: tuple
    named_cells: tuple


def need(condition):
    if not condition:
        raise ObservationError('tree_columns_move_observation_invalid')


def snapshot_size(columns, nodes):
    return 5 + 13 * columns + nodes * (6 + 4 * columns)


def maximum_record_size(case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    return len(f'CM-{case}: [S/') + 2 * snapshot_size(MAX_COLUMNS, NODE_LIMITS[case - 1]) + 3


MAX_ENCODED_BYTES = len(CALIBRATION_RECORD) + sum(maximum_record_size(case)
                                                   for case in range(1, CASE_COUNT + 1))


def decode_snapshot(raw, case, registry):
    """Parse bounded observations; do not enforce a presumed Columns.Move result."""
    pos = 0

    def take(count):
        nonlocal pos
        need(pos + count <= len(raw))
        value = raw[pos:pos + count]
        pos += count
        return value

    def identity(kind, optional=False):
        value = take(1)
        if optional and value == '_':
            return None
        need(value in IDS)
        index = IDS.index(value)
        need(index <= len(registry))
        if index == len(registry):
            registry.append(kind)
        need(registry[index] == kind)
        return index

    def owner_label(expected):
        value = take(1)
        need(value in IDS and IDS.index(value) == expected)
        return expected

    def digit():
        value = take(1)
        need(value in '0123456789')
        return int(value)

    tree = identity('tree')
    rows_owner = owner_label(tree)
    columns = identity('columns')
    count = digit()
    need(count <= MAX_COLUMNS)
    schema = []
    for _ in range(count):
        column = identity('column')
        fields = take(12)
        need(re.fullmatch(r'[a-m]{2}[0-9][UNS][0-9]{2}[01][0-9][01][012][0-9][01]', fields) is not None)
        schema.append((column, fields))
    count_char = take(1)
    need(count_char in IDS)
    node_count = IDS.index(count_char)
    need(node_count <= NODE_LIMITS[case - 1])
    nodes = []
    for _ in range(node_count):
        row = identity('row')
        parent = identity('row', optional=True)
        owner = identity('tree')
        level = digit()
        children_owner = owner_label(row)
        child_count = digit()
        cells = []
        for _ in range(count):
            cell = take(2)
            need(re.fullmatch(r'(?:N[0-9]|S[a-r]|[UL]_|B[01])', cell) is not None)
            cells.append((cell[0], cell[1]))
        named_cells = []
        for _ in range(count):
            cell = take(2)
            need(re.fullmatch(r'(?:N[0-9]|S[a-r]|[UL]_|B[01])', cell) is not None)
            named_cells.append((cell[0], cell[1]))
        nodes.append(RowObservation(row, parent, owner, level, children_owner,
                                    child_count, tuple(cells), tuple(named_cells)))
    need(pos == len(raw))
    need(len({column for column, _ in schema}) == len(schema))
    need(len({node.row for node in nodes}) == len(nodes))
    # Each snapshot must describe a coherent preorder tree. This does not
    # constrain how identities, schema, cells or ordering change after Move.
    pending = []
    for node in nodes:
        while pending and pending[-1][1] == 0:
            pending.pop()
        need(node.owner == tree)
        if pending:
            parent, remaining = pending[-1]
            need(node.parent == parent.row and node.level == parent.level + 1)
            pending[-1] = (parent, remaining - 1)
        else:
            need(node.parent is None and node.level == 0)
        if node.child_count:
            pending.append((node, node.child_count))
    while pending and pending[-1][1] == 0:
        pending.pop()
    need(not pending)
    return {'tree': tree, 'rows_owner': rows_owner, 'columns': columns,
            'schema': tuple(schema), 'nodes': tuple(nodes)}


def validate_payload(payload, case):
    need(type(case) is int and 1 <= case <= CASE_COUNT and type(payload) is bytes)
    try:
        text = payload.decode('ascii')
    except UnicodeDecodeError:
        raise ObservationError('tree_columns_move_observation_invalid') from None
    parts = text.split('/')
    # XB/XO are finite observer failures, never action outcomes or valid evidence.
    need(len(parts) == 3 and (parts[0] in ('S', 'M', 'A', 'O')
                             or case == 23 and parts[0] == 'E'))
    registry = []
    snapshots = tuple(decode_snapshot(part, case, registry) for part in parts[1:])
    return {'case': case, 'status': parts[0], 'snapshots': snapshots,
            'identities': tuple(registry)}


def validate_output(raw):
    """Validate a capture, including calibration, without claiming availability."""
    need(type(raw) is bytes and len(raw) <= MAX_OUTPUT_BYTES)
    need(all(value == 10 or 32 <= value <= 126 for value in raw))
    lines = raw.splitlines(keepends=True)
    need(len(lines) == CASE_COUNT + 1 and lines[0] == CALIBRATION_RECORD)
    result = []
    for case, line in enumerate(lines[1:], 1):
        prefix = f'CM-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n')
             and len(line) <= maximum_record_size(case))
        result.append(validate_payload(line[len(prefix):-2], case))
    return tuple(result)


def require_available(raw):
    """Require successful English and Russian Columns.Move positive controls.

    Still not a native parity or completeness assertion: only a validated capture
    from the real platform can establish native answers to the remaining cases.
    """
    result = validate_output(raw)
    if any(result[index]['status'] != 'S' for index in (0, 1)):
        raise AvailabilityError('tree_columns_move_positive_controls_failed')
    return result
