"""Standalone synthetic Copy wire grammar, not native semantic expectations."""
import re

IDS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
MAX_OUTPUT_BYTES = 8192
# Maximum columns, nodes, successful snapshot count for each fixed case.
LIMITS = ((0, 0, 3), (3, 0, 3), (3, 4, 3), (3, 4, 7),
          (3, 5, 11), (4, 0, 15), (3, 4, 11), (3, 4, 3), (3, 4, 3))


class ObservationError(ValueError):
    pass


def need(condition):
    if not condition:
        raise ObservationError('tree_copy_observation_invalid')


def snapshot_size(columns, nodes):
    return 5 + 13 * columns + nodes * (6 + 6 * columns)


def maximum_record_size(case):
    cols, nodes, count = LIMITS[case - 1]
    return len(f'TC-{case}: [S/') + count * snapshot_size(cols, nodes) + count - 1 + 2


MAX_ENCODED_BYTES = len(b'TC-C: [-]\n') + sum(maximum_record_size(c) for c in range(1, 10))


def decode_snapshot(raw, case, registry):
    max_columns, max_nodes, _ = LIMITS[case - 1]
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

    def digit():
        value = take(1)
        need(value in '0123456789')
        return int(value)

    tree = identity('tree'); rows = identity('rows'); columns = identity('columns')
    count = digit(); need(count <= max_columns)
    schema = []
    for _ in range(count):
        column = identity('column'); fields = take(12)
        need(re.fullmatch(r'[a-m]{2}[0-9][UNS][0-9]{2}[01][0-9][01][012][0-9][01]', fields) is not None)
        schema.append((column, fields))
    n = digit(); need(n <= max_nodes)
    nodes = []
    for _ in range(n):
        node = identity('row'); parent = identity('row', optional=True)
        owner = identity('tree'); level = digit(); children = identity('rows'); child_count = digit()
        need(level <= 4 and child_count <= 5)
        cells = []
        for _ in range(count):
            kind = take(1)
            if kind == 'A':
                outer = identity('array'); inner = identity('array'); a = digit(); b = digit()
                need(take(1) == '_'); cells.append((kind, outer, inner, a, b))
            else:
                tail = take(5)
                need((kind in 'UL' and tail == '_____') or
                     (kind == 'B' and re.fullmatch('[01]____', tail) is not None) or
                     (kind == 'N' and re.fullmatch('[0-9]____', tail) is not None) or
                     (kind == 'S' and re.fullmatch('[a-m]____', tail) is not None))
                cells.append((kind, tail))
        nodes.append((node, parent, owner, level, children, child_count, tuple(cells)))
    need(pos == len(raw))
    # Do not require copied identities, owners, parents or values to equal an
    # assumed answer: their recorded values are the questions being measured.
    return {'tree': tree, 'rows': rows, 'columns': columns, 'schema': tuple(schema), 'nodes': tuple(nodes)}


def validate_payload(payload, case):
    need(type(case) is int and 1 <= case <= 9 and type(payload) is bytes)
    try:
        text = payload.decode('ascii')
    except UnicodeDecodeError:
        raise ObservationError('tree_copy_observation_invalid') from None
    parts = text.split('/')
    need(parts[0] in ('S', 'M', 'A', 'O'))
    status = parts.pop(0)
    count = LIMITS[case - 1][2] if status == 'S' else 3
    need(len(parts) == count)
    registry = []
    decoded = []
    for i, part in enumerate(parts):
        if status != 'S' and i == 2:
            need(part == '-'); decoded.append(None)
        else:
            decoded.append(decode_snapshot(part, case, registry))
    return {'case': case, 'status': status, 'snapshots': tuple(decoded), 'identities': tuple(registry)}


def validate_output(raw):
    need(type(raw) is bytes and len(raw) <= MAX_OUTPUT_BYTES)
    need(all(x == 10 or 32 <= x <= 126 for x in raw))
    lines = raw.splitlines(keepends=True)
    need(len(lines) == 10 and lines[0] == b'TC-C: [-]\n')
    result = []
    for case, line in enumerate(lines[1:], 1):
        prefix = f'TC-{case}: ['.encode('ascii')
        need(line.startswith(prefix) and line.endswith(b']\n') and len(line) <= maximum_record_size(case))
        result.append(validate_payload(line[len(prefix):-2], case))
    return tuple(result)
