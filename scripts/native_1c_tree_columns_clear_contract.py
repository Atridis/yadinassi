"""Strict CC lifetime observations, not assumed Columns.Clear behavior.

Active preorder/child counts describe reachability; reported Parent/Owner/Level
are independent observations. Retained collection handles have structural labels,
not wrapper identities. Access errors E_ differ from absent references A_ and from
unsupported observer values (which invalidate the entire capture).
"""
import re
from typing import NamedTuple

IDS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
CASE_COUNT = 12
MAX_COLUMNS = 3
MAX_ROWS = 5
MAX_OUTPUT_BYTES = 8192
CALIBRATION_RECORD = b'CC-C1: [-]\n'
QUERY_NAMES = tuple(f'{row}.{field}' for row in ('root', 'child')
                    for field in ('id', 'owner', 'parent', 'level', 'cell', 'named', 'children')) + (
    'column.id', 'column.name', 'column.title', 'column.width',
    'columns.count', 'columns.first', 'root_rows.count', 'root_rows.parent',
    'child_rows.count', 'child_rows.parent')
QUERY_TYPES = ('row', 'tree', 'row?', 'number', 'cell', 'cell', 'number') * 2 + (
    'column', 'word', 'word', 'number', 'number', 'column', 'number', 'row?', 'number', 'row?')


class ObservationError(ValueError):
    pass


class AvailabilityError(ValueError):
    pass


class RowObservation(NamedTuple):
    row: int
    parent: int | None
    owner: int | None
    level: int
    child_count: int
    cells: tuple
    named_cells: tuple


def need(condition):
    if not condition:
        raise ObservationError('tree_columns_clear_observation_invalid')


def snapshot_size(columns=MAX_COLUMNS, rows=MAX_ROWS):
    return 3 + 13 * columns + rows * (5 + 4 * columns) + 2 * len(QUERY_NAMES)


def maximum_record_size(case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    return len(f'CC-{case}: [') + 5 + 2 + 2 * snapshot_size() + 2


MAX_ENCODED_BYTES = len(CALIBRATION_RECORD) + sum(maximum_record_size(case) for case in range(1, CASE_COUNT + 1))


def signed(value):
    need(len(value) == 1 and value in '0123456789abcdefghi')
    return int(value) if value.isdigit() else -('abcdefghi'.index(value) + 1)


def scalar(token):
    need(len(token) == 2)
    if token in ('U_', 'L_', 'B0', 'B1'):
        return (token[0], token[1])
    if token[0] == 'N':
        return ('N', signed(token[1]))
    need(token[0] == 'S' and token[1] in 'abcdefghijklmnopqr')
    return ('S', token[1])


def decode_snapshot(raw, registry):
    pos = 0
    def take(count):
        nonlocal pos
        need(pos + count <= len(raw))
        value = raw[pos:pos + count]; pos += count
        return value
    def identity_token(value, kind, optional=False):
        if optional and value == '_': return None
        need(len(value) == 1 and value in IDS)
        index = IDS.index(value)
        need(index <= len(registry))
        if index == len(registry): registry.append(kind)
        need(registry[index] == kind)
        return index
    def identity(kind, optional=False):
        return identity_token(take(1), kind, optional)
    def count(limit):
        value = take(1); need(value in '0123456789' and int(value) <= limit)
        return int(value)
    tree = identity('tree')
    columns = count(MAX_COLUMNS); schema = []
    for _ in range(columns):
        column = identity('column'); fields = take(12)
        need(re.fullmatch(r'[a-n]{2}[0-9][UNS][0-9]{2}[01][0-9][01][012][0-9][01]', fields) is not None)
        schema.append((column, fields))
    need(len({c[0] for c in schema}) == columns)
    need(len({c[1][0] for c in schema}) == columns)
    node_count = count(MAX_ROWS); nodes = []
    # A stack checks only the serialized preorder child counts, never claims
    # that a retained/reported Parent, Owner, or Level must equal its position.
    remaining = []
    for _ in range(node_count):
        while remaining and remaining[-1] == 0: remaining.pop()
        if remaining: remaining[-1] -= 1
        row = identity('row'); parent = identity('row', True); owner = identity('tree', True)
        level = signed(take(1)); children = count(MAX_ROWS)
        cells = tuple(scalar(take(2)) for _ in range(columns))
        named = tuple(scalar(take(2)) for _ in range(columns))
        nodes.append(RowObservation(row, parent, owner, level, children, cells, named))
        remaining.append(children)
    need(not any(remaining))
    need(len({n.row for n in nodes}) == node_count)
    queries = []
    for kind in QUERY_TYPES:
        token = take(2)
        if token in ('E_', 'A_'):
            queries.append((token[0], None)); continue
        if kind in ('row', 'row?', 'tree', 'column'):
            need(token[0] == 'I')
            value = identity_token(token[1], kind.rstrip('?'), kind.endswith('?') or kind == 'tree')
        elif kind == 'word':
            need(token[0] == 'W' and token[1] in 'abcdefghijklmn'); value = token[1]
        elif kind == 'number':
            need(token[0] == 'N'); value = signed(token[1])
        else:
            value = scalar(token)
        queries.append((token[0], value))
    need(pos == len(raw))
    return {'tree': tree, 'schema': tuple(schema), 'nodes': tuple(nodes), 'queries': tuple(queries)}


def validate_payload(payload, case):
    need(type(case) is int and 1 <= case <= CASE_COUNT)
    need(type(payload) is bytes and len(payload) <= maximum_record_size(case))
    try: text = payload.decode('ascii')
    except UnicodeDecodeError: raise ObservationError('tree_columns_clear_observation_invalid') from None
    parts = text.split('/'); need(len(parts) == 3)
    header, before, after = parts
    need(len(header) == 5 and header[0] in 'SMAO' and header[1] in '-SMAO' and header[2] in '012345')
    status, follow, phase, expression = header[0], header[1], int(header[2]), header[3:]
    follows = case == 6 or case >= 9
    if status == 'S' and follows:
        need(follow != '-' and (phase in range(1, 6) if case == 12 else phase == 1))
        if case == 12 and follow == 'S': need(phase == 5)
    else: need(follow == '-' and phase == 0)
    if case == 8 and status == 'S': scalar(expression)
    else: need(expression == '--')
    registry = []
    snapshots = (decode_snapshot(before, registry), decode_snapshot(after, registry))
    return {'case': case, 'status': status, 'follow_status': follow, 'phase': phase,
            'expression': expression, 'snapshots': snapshots, 'identities': tuple(registry)}


def validate_output(raw):
    need(type(raw) is bytes and len(raw) <= MAX_OUTPUT_BYTES)
    need(all(value == 10 or 32 <= value <= 126 for value in raw))
    lines = raw.splitlines(keepends=True)
    need(len(lines) == CASE_COUNT + 1 and lines[0] == CALIBRATION_RECORD)
    result = []
    for case, line in enumerate(lines[1:], 1):
        prefix = f'CC-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n') and len(line) <= maximum_record_size(case))
        result.append(validate_payload(line[len(prefix):-2], case))
    return tuple(result)


def controls_valid(records):
    # Documented Clear effect only; retained-reference outcomes stay observations.
    return all(records[i]['status'] == 'S' and records[i]['snapshots'][0]['schema']
               and records[i]['snapshots'][0]['nodes'] and not records[i]['snapshots'][1]['schema']
               and not records[i]['snapshots'][1]['nodes'] for i in (0, 1))


def require_available(raw):
    records = validate_output(raw)
    if not controls_valid(records):
        raise AvailabilityError('tree_columns_clear_positive_controls_failed')
    return records
