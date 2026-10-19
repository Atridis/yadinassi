"""Readers for genuine legacy records and the pending compact probe schemas.

This module reads observations, never creates expected native output. Compact
escape decoding happens once, after schema detection; intrinsic CR/LF survive.
"""
import re

from yadinassi.serialization import _Reader
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray, BSLType, equal, to_string
from yadinassi.type_values import type_of
from yadinassi.serialization import value_to_string_internal as write


def _unescape(text):
    result = []
    index = 0
    escapes = {'\\': '\\', 'r': '\r', 'n': '\n', 't': '\t'}
    while index < len(text):
        char = text[index]
        index += 1
        if char == '\\':
            if index == len(text) or text[index] not in escapes:
                raise ValueError('Invalid compact escape')
            char = escapes[text[index]]
            index += 1
        result.append(char)
    return ''.join(result)


class _Compact:
    def __init__(self, text):
        self.text, self.pos = text, 0
        self.nodes = 0

    def skip(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def scalar(self):
        # Native grammar parses quoted delimiters/UTF-16 escapes correctly.
        reader = _Reader(self.text[self.pos:])
        result = reader.value(reader.token())
        self.pos += reader.position
        self.nodes += reader.nodes
        if self.nodes > 10000:
            raise ValueError("Observation aggregate scalar node limit")
        return result

    def value(self, depth=0):
        self.nodes += 1
        if depth > 64 or self.nodes > 10000:
            raise ValueError("Observation resource limit")
        self.skip()
        if self.text.startswith('{"', self.pos):
            return self.scalar()
        if self.pos >= len(self.text) or self.text[self.pos] not in '[{':
            raise ValueError('Expected compact value')
        structure = self.text[self.pos] == '{'
        closing = '}' if structure else ']'
        self.pos += 1
        result = BSLStructure() if structure else BSLArray()
        self.skip()
        if self.text.startswith(closing, self.pos):
            self.pos += 1
            return result
        while True:
            if structure:
                key = self.value(depth + 1)
                if type(key) is not str:
                    raise ValueError('Non-string compact structure key')
                self.skip()
                self.take('=')
                if result.property(key):
                    raise ValueError('Duplicate compact key')
                result.insert(key, self.value(depth + 1))
            else:
                result.add(self.value(depth + 1))
            self.skip()
            if self.text.startswith(closing, self.pos):
                self.pos += 1
                return result
            self.take(';')
            self.skip()

    def take(self, token):
        if not self.text.startswith(token, self.pos):
            raise ValueError('Expected ' + token)
        self.pos += len(token)

    def finish(self):
        self.skip()
        if self.pos != len(self.text):
            raise ValueError('Trailing observation data')


def _build_paths(entries, explicit):
    nodes = {}
    counts = {}
    for path, value, count in entries:
        if path in nodes:
            raise ValueError('Duplicate observation path')
        nodes[path] = value
        if len(nodes) > 10000:
            raise ValueError("Observation aggregate path limit")
        if count is not None:
            counts[path] = count
        if not explicit:
            parent = path[:-1]
            while parent and parent not in nodes:
                if len(nodes) >= 10000:
                    raise ValueError("Observation aggregate path limit")
                nodes[parent] = BSLStructure()
                parent = parent[:-1]
    if not explicit:
        nodes[()] = BSLStructure()
    child_counts = {}
    for path in sorted(nodes, key=len, reverse=True):
        if not path:
            continue
        if path[:-1] not in nodes:
            raise ValueError('Missing container marker')
        child_counts[path[:-1]] = child_counts.get(path[:-1], 0) + 1
        parent = nodes[path[:-1]]
        if type(parent) is BSLStructure:
            if parent.property(path[-1]):
                raise ValueError("Duplicate case-insensitive observation path")
            parent.insert(path[-1], nodes[path])
        elif type(parent) is BSLArray:
            if not re.fullmatch(r'0|[1-9][0-9]*', path[-1]):
                raise ValueError('Invalid array index')
            index = int(path[-1])
            if index >= counts[path[:-1]]:
                raise ValueError('Array index exceeds count')
            parent.items[index] = nodes[path]
        else:
            raise ValueError('Observation child of scalar')
    for path, count in counts.items():
        if child_counts.get(path, 0) != count:
            raise ValueError('Container count mismatch')
    return nodes[()]


def read_observation(payload, *, compact=False):
    """Read one bracket-stripped observation without altering scalar contents."""
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("Observation text limit")
    text = payload.lstrip()
    if text.startswith('value='):
        parser = _Compact(_unescape(text))
        entries = []
        declared_elements = 0
        while True:
            match = re.match(r'value((?:\.[\w]+)*)=', parser.text[parser.pos:])
            if not match:
                raise ValueError('Invalid values observation path')
            path = tuple(match[1][1:].split('.')) if match[1] else ()
            parser.pos += len(match[0])
            marker = re.match(r'(structure|array)\((0|[1-9][0-9]*)\)', parser.text[parser.pos:])
            if marker:
                count = int(marker[2])
                declared_elements += count + 1
                if declared_elements + parser.nodes > 10000:
                    raise ValueError('Observation aggregate container limit')
                value = BSLStructure() if marker[1] == 'structure' else BSLArray()
                if type(value) is BSLArray:
                    value.items = [None] * count
                parser.pos += len(marker[0])
            else:
                value, count = parser.value(), None
            if len(path) > 64 or len(entries) >= 10000:
                raise ValueError("Observation resource limit")
            if declared_elements + parser.nodes > 10000:
                raise ValueError("Observation aggregate node limit")
            entries.append((path, value, count))
            if parser.pos == len(parser.text):
                break
            parser.take(';')
        return _build_paths(entries, True)
    if re.match(r'[\w]+(?:\.[\w]+)*=', text):
        entries = []
        total_nodes = 0
        for line in payload.split('\n'):
            if not line.strip():
                continue
            key, separator, encoded = line.strip().partition('=')
            if not separator or not re.fullmatch(r'[\w]+(?:\.[\w]+)*', key):
                raise ValueError('Invalid table field path')
            if len(key.split(".")) > 64 or len(entries) >= 10000:
                raise ValueError("Observation resource limit")
            parser = _Compact(_unescape(encoded))
            entries.append((tuple(key.split('.')), parser.value(), None))
            parser.finish()
            total_nodes += parser.nodes
            if total_nodes > 10000:
                raise ValueError("Observation aggregate node limit")
        return _build_paths(entries, False)
    # Legacy native scalar/collection record, or compact inline table container.
    # Native records begin with {"; inline structures start {{" or {}.
    if text.startswith('{"'):
        parser = _Compact(_unescape(text) if compact else text)
        value = parser.scalar()
    else:
        parser = _Compact(_unescape(text))
        value = parser.value()
    parser.finish()
    return value


def inverse_stream(record, inverse='ReadWrite', original='Write'):
    """Resolve observed deduplication only; reject inconsistent/missing fields."""
    flag = inverse + 'Equal'
    has_raw = record.property(inverse)
    if record.property(flag):
        identical = record.get(flag)
        if type(identical) is not bool:
            raise AssertionError('Inverse comparison did not succeed')
        if identical:
            if has_raw:
                raise AssertionError('Equal compact inverse unexpectedly duplicated')
            return record.get(original)
        if not has_raw or record.get(inverse) == record.get(original):
            raise AssertionError('Differing inverse stream missing or inconsistent')
        return record.get(inverse)
    raw = record.get(inverse)
    return record.get(original) if raw == 'same-as-Write' else raw


def assert_type_inverse(case, record):
    actual = write(_read_stream(record.get('TypeWrite')))
    # TypeRead in the table schema independently records type/equality/stability.
    if record.property('TypeRead') and type(record.get('TypeRead')) is BSLStructure:
        observed = record.get('TypeRead')
        restored = _read_stream(record.get('TypeWrite'))
        case.assertEqual(set(observed._items), {'type', 'equal', 'stable'})
        case.assertIs(type(observed.get('Equal')), bool)
        case.assertIs(type(observed.get('Stable')), bool)
        case.assertIs(type_of(restored), observed.get('Type'))
        case.assertEqual(equal(restored, record.get('Type')), observed.get('Equal'))
        case.assertEqual(actual == record.get('TypeWrite'), observed.get('Stable'))
    else:
        case.assertEqual(actual, inverse_stream(record, 'TypeRead', 'TypeWrite'))


def _read_stream(text):
    # Local alias avoids changing the public runtime stream reader.
    from yadinassi.serialization import value_from_string_internal
    return value_from_string_internal(text)


def assert_nested(case, record, value):
    nested = record.get('Nested')
    array = BSLArray()
    array.add(value)
    payload = write(array)
    restored = _read_stream(payload)
    if type(nested) is str:
        case.assertEqual(write(restored), nested)
    else:
        case.assertEqual(set(nested._items), {'write', 'readtype', 'readview', 'readwrite'})
        case.assertEqual(payload, nested.get('Write'))
        case.assertIs(type_of(restored), nested.get('ReadType'))
        case.assertEqual(write(restored), inverse_stream(nested))
        assert_view(case, nested.get("ReadView"), restored)


def assert_snapshot(case, record, value, *, table=False):
    restored = _read_stream(write(value))
    case.assertIs(type(record.get('Equal')), bool)
    for key, expected in {'Type': type_of(value), 'Text': to_string(value),
                          'Write': write(value), 'TypeWrite': write(type_of(value)),
                          'ReadType': type_of(restored), 'Equal': equal(value, restored)}.items():
        case.assertEqual(record.get(key), expected, key)
    expected_fields = {'type', 'text', 'write', 'typewrite', 'readtype', 'equal', 'nested'}
    for inverse, original in [('ReadWrite', 'Write'), ('TypeRead', 'TypeWrite')]:
        if record.property(inverse + 'Equal'):
            expected_fields.add((inverse + 'Equal').lower())
            if record.get(inverse + 'Equal') is False:
                expected_fields.add(inverse.lower())
        else:
            expected_fields.add(inverse.lower())
    if table:
        expected_fields.update({'view', 'readview'})
    case.assertEqual(set(record._items), expected_fields)
    if table:
        for key, item in [('View', value), ('ReadView', restored)]:
            assert_view(case, record.get(key), item)
    assert_type_inverse(case, record)
    case.assertEqual(write(restored), inverse_stream(record))
    assert_nested(case, record, value)


def extract_payload(text, label):
    pattern = (r'^' + re.escape(label) +
               r': \[(.*?)\](?=\r?\n[a-zA-Z][a-zA-Z0-9.-]*:|\r?\n?\Z)')
    matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise ValueError('Missing or duplicate observation label: ' + label)
    return matches[0]


def assert_view(case, observed, value):
    """Check all table view fields in either the old Columns or new Names schema."""
    from decimal import Decimal
    from yadinassi.value_tables import (BSLValueTable, BSLValueTableRow,
        BSLValueTableColumn, BSLValueTableColumnCollection)
    if type(value) is BSLValueTable:
        case.assertIs(type(observed), BSLStructure)
        columns_field = 'Names' if observed.property('Names') else 'Columns'
        case.assertEqual(set(observed._items), {'count', columns_field.lower(), 'rows'})
        case.assertIs(type(observed.get('Count')), Decimal)
        case.assertEqual(observed.get('Count'), Decimal(len(value.rows)))
        items = [c.name for c in value.columns.items] if columns_field == 'Names' else value.columns.items
        columns = BSLArray(); columns.items = items
        assert_view(case, observed.get(columns_field), columns)
        rows = BSLArray(); rows.items = value.rows
        assert_view(case, observed.get('Rows'), rows)
    elif type(value) is BSLValueTableColumn:
        case.assertEqual(set(observed._items), {'name', 'title', 'width', 'valuetype'})
        for name, item in [('Name', value.name), ('Title', value.title),
                           ('Width', value.width), ('ValueType', value.value_type)]:
            case.assertEqual(write(observed.get(name)), write(item))
    elif type(value) in (BSLArray, BSLValueTableRow, BSLValueTableColumnCollection):
        items = (list(value) if type(value) is BSLValueTableRow else value.items)
        case.assertIs(type(observed), BSLArray)
        case.assertEqual(len(observed.items), len(items))
        for actual, item in zip(observed.items, items):
            assert_view(case, actual, item)
    else:
        case.assertEqual(write(observed), write(value))
