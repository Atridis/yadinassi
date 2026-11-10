"""Bounded ValueTable snapshots for the private in-process ValueStorage tree.

Typed scalar schemas, titles, widths and ordered index definitions are a local
snapshot policy, not a native table codec or an additional native parity claim.
Owner graphs are rebuilt; cached index buckets and host objects are never copied.
"""
from decimal import Decimal

from .dates import BSLDate
from .structures import _key
from .type_descriptions import BSLTypeDescription, _query_nullable_description
from .type_qualifiers import (BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
                              BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers,
                              BSLStringQualifiers)
from .value_tables import (BSLCollectionIndex, BSLCollectionIndexes, BSLValueTable,
                           BSLValueTableColumn, BSLValueTableColumnCollection,
                           BSLValueTableRow, _index_key_units, _index_token,
                           _MAX_INDEX_UNITS)
from .values import BSLArray, BSLType, NULL

MAX_COLUMNS = 64
MAX_ROWS = 1024
MAX_CELLS = 4096
MAX_NAME_UNITS = 128
MAX_TITLE_UNITS = 1_000_000
MAX_INDEXES = 64
MAX_INDEX_COLUMNS = 256
MAX_INDEX_CELLS = 16_384

# These are private tuple positions, not native stream ordinals. BinaryData,
# UUID, references and arbitrary object descriptors are deliberately excluded.
_SCALARS = (BSLType.BOOLEAN, BSLType.STRING, BSLType.DATE, BSLType.NUMBER, BSLType.NULL)
_SIGNS = (BSLAllowedSign.ANY, BSLAllowedSign.NONNEGATIVE)
_LENGTHS = (BSLAllowedLength.VARIABLE, BSLAllowedLength.FIXED)
_DATES = (BSLDateFractions.DATE_TIME, BSLDateFractions.DATE, BSLDateFractions.TIME)
_EMPTY_DESCRIPTION = ((), (0, 0, 0), (0, 0), 0, False)


class TableSnapshotError(ValueError):
    """Table shape, metadata or local budget is not supported."""


def _field(value, name):
    # Call only for an exact admitted runtime type. Do not use instance methods
    # or permit a substituted __getattr__, equality or conversion hook.
    return object.__getattribute__(value, name)


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise TableSnapshotError('invalid table metadata integer')
    return value


def _count(value, maximum):
    # Metadata constructors store canonical nonnegative integer Decimals.
    # Bound coefficient allocation before as_tuple(), including huge trailing
    # zero coefficients whose numeric magnitude would otherwise appear small.
    if (type(value) is not Decimal or not value.is_finite()
            or Decimal.__sizeof__ is object.__sizeof__
            or Decimal.__sizeof__(value) > 256 or not 0 <= value <= maximum):
        raise TableSnapshotError('invalid table metadata count')
    parts = value.as_tuple()
    if parts.sign or parts.exponent != 0:
        raise TableSnapshotError('noncanonical table metadata count')
    return int(value)


def _ordinal(value, members):
    for position, member in enumerate(members):
        if value is member:
            return position
    raise TableSnapshotError('invalid table metadata enum')


def _descriptor_fields(description):
    if type(description) is not BSLTypeDescription:
        raise TableSnapshotError('expected exact scalar type description')
    types = _field(description, 'types')
    if type(types) is not tuple or len(types) > len(_SCALARS):
        raise TableSnapshotError('invalid descriptor type list')
    kinds = tuple(_ordinal(kind, _SCALARS) for kind in types)
    n, s, d, b = (_field(description, name) for name in
                  ('number_qualifiers', 'string_qualifiers', 'date_qualifiers',
                   'binary_data_qualifiers'))
    if (type(n) is not BSLNumberQualifiers or type(s) is not BSLStringQualifiers
            or type(d) is not BSLDateQualifiers or type(b) is not BSLBinaryDataQualifiers):
        raise TableSnapshotError('invalid descriptor qualifier type')
    number = (_count(_field(n, 'digits'), 4096), _count(_field(n, 'fraction_digits'), 4096),
              _ordinal(_field(n, 'allowed_sign'), _SIGNS))
    string = (_count(_field(s, 'length'), 1_000_000),
              _ordinal(_field(s, 'allowed_length'), _LENGTHS))
    date = _ordinal(_field(d, 'date_fractions'), _DATES)
    if (_count(_field(b, 'length'), 1_000_000) != 0
            or _field(b, 'allowed_length') is not BSLAllowedLength.VARIABLE):
        raise TableSnapshotError('nondefault binary qualifiers are not supported')
    return kinds, number, string, date


def _description(payload):
    """Validate primitive framing, then use existing descriptor constructors."""
    if type(payload) is not tuple or len(payload) != 5:
        raise TableSnapshotError('invalid descriptor snapshot')
    kinds, number, string, date, nullable = payload
    if (type(kinds) is not tuple or len(kinds) > len(_SCALARS)
            or type(number) is not tuple or len(number) != 3
            or type(string) is not tuple or len(string) != 2
            or type(nullable) is not bool):
        raise TableSnapshotError('invalid descriptor snapshot fields')
    for kind in kinds:
        _integer(kind, len(_SCALARS) - 1)
    digits, fraction, sign = number
    length, allowed_length = string
    _integer(digits, 4096)
    _integer(fraction, digits)
    _integer(sign, len(_SIGNS) - 1)
    _integer(length, 1_000_000)
    _integer(allowed_length, len(_LENGTHS) - 1)
    _integer(date, len(_DATES) - 1)
    try:
        types = BSLArray()
        types.items = [_SCALARS[kind] for kind in kinds]
        scalar = BSLTypeDescription(types, BSLNumberQualifiers(digits, fraction, _SIGNS[sign]),
                                    BSLStringQualifiers(length, _LENGTHS[allowed_length]),
                                    BSLDateQualifiers(_DATES[date]))
        # Constructors normalize order, duplicates and zero-length Fixed. Do
        # not accept malformed state by silently normalizing its metadata.
        if _descriptor_fields(scalar) != payload[:4]:
            raise TableSnapshotError('noncanonical descriptor snapshot')
        return _query_nullable_description(scalar) if nullable else scalar
    except (TypeError, ValueError, ArithmeticError):
        raise TableSnapshotError('unsupported or invalid scalar descriptor') from None


def _take_description(description):
    fields = _descriptor_fields(description)
    scalar = _field(description, '_query_scalar')
    if scalar is None:
        payload = (*fields, False)
    else:
        # One factory-owned scalar marker only. Cycles and nested nullable
        # descriptors are rejected before following another marker.
        if (type(scalar) is not BSLTypeDescription or scalar is description
                or _field(scalar, '_query_scalar') is not None):
            raise TableSnapshotError('invalid nullable query descriptor')
        payload = (*_descriptor_fields(scalar), True)
    rebuilt = _description(payload)
    if _descriptor_fields(rebuilt) != fields:
        raise TableSnapshotError('inconsistent nullable query descriptor')
    return payload, rebuilt


def _dimensions(columns, rows):
    if (type(columns) is not tuple or type(rows) is not tuple or len(columns) > MAX_COLUMNS
            or len(rows) > MAX_ROWS or len(columns) * len(rows) > MAX_CELLS
            or (not columns and rows)):
        raise TableSnapshotError('invalid or oversized table shape')


def _name(name):
    if type(name) is not str or not name or len(name) > MAX_NAME_UNITS:
        raise TableSnapshotError('invalid table column name')
    if len(name) + sum(ord(c) > 0xffff for c in name) > MAX_NAME_UNITS:
        raise TableSnapshotError('table column name budget exceeded')
    try:
        return _key(name)
    except (TypeError, ValueError):
        raise TableSnapshotError('invalid table column name') from None


def _title(title):
    if type(title) is not str or len(title) > MAX_TITLE_UNITS:
        raise TableSnapshotError('invalid or oversized column title')
    if len(title) + sum(ord(c) > 0xffff for c in title) > MAX_TITLE_UNITS:
        raise TableSnapshotError('column title budget exceeded')
    return title


def _schema_extra(payload):
    # The column node is already reserved with the row/column framing. Charge
    # its fields, descriptor tuples and primitive members in the same global
    # node budget. Plain legacy columns still cost one name metadata node.
    return 14 + len(payload[0])


def _index_bounds(count, positions, rows):
    if (count > MAX_INDEXES or positions > MAX_INDEX_COLUMNS
            or rows * positions > MAX_INDEX_CELLS):
        raise TableSnapshotError('table index budget exceeded')


def _take_indexes(table, indexes, column_positions, row_count, reserve):
    _index_bounds(len(indexes), 0, row_count)
    definitions, seen, positions = [], set(), 0
    reserve(len(indexes))
    for index in indexes:
        if (type(index) is not BSLCollectionIndex or _field(index, 'table') is not table
                or _field(index, '_deleted') is not False
                or _field(index, '_cleared') is not False or id(index) in seen):
            raise TableSnapshotError('invalid table index owner')
        seen.add(id(index))
        columns = _field(index, 'columns')
        if type(columns) is not list:
            raise TableSnapshotError('invalid index column list')
        positions += max(1, len(columns))
        _index_bounds(len(indexes), positions, row_count)
        reserve(len(columns))
        definition = []
        for column in columns:
            if type(column) is not BSLValueTableColumn or id(column) not in column_positions:
                raise TableSnapshotError('invalid index column owner')
            definition.append(column_positions[id(column)])
        definitions.append(tuple(definition))
    # Cached buckets/keys/units are intentionally neither read nor copied.
    return tuple(definitions)


def _restore_indexes(indexes, columns, rows, reserve):
    if type(indexes) is not tuple:
        raise TableSnapshotError('invalid table indexes snapshot')
    _index_bounds(len(indexes), 0, rows)
    reserve(len(indexes))
    positions = 0
    for definition in indexes:
        if type(definition) is not tuple:
            raise TableSnapshotError('invalid index definition snapshot')
        positions += max(1, len(definition))
        _index_bounds(len(indexes), positions, rows)
        reserve(len(definition))
        for position in definition:
            _integer(position, columns - 1)


def _cell_matches(description, value):
    """Check already admitted values without introducing coercion semantics."""
    if not description.types:
        return True
    scalar = description._query_scalar
    if scalar is not None:
        if value is NULL:
            return True  # Query Unload can contain Null; later writes still cannot.
        description = scalar
    elif value is None:
        return len(description.types) > 1  # Existing composite default.
    if value is NULL:
        return description.types == (BSLType.NULL,)
    kind = type(value)
    value_type = next((bsl for python, bsl in ((bool, BSLType.BOOLEAN), (str, BSLType.STRING),
                      (Decimal, BSLType.NUMBER), (BSLDate, BSLType.DATE)) if kind is python), None)
    if value_type is None or value_type not in description.types:
        return False
    if kind is BSLDate:
        # Do not call methods that host access could shadow on the source date.
        value = BSLDate(_field(value, 'ticks'), _field(value, 'boundary'))
    try:
        adjusted = BSLTypeDescription.adjust_value(description, value)
        if type(adjusted) is not kind:
            return False
        if kind is BSLDate:
            return adjusted.ticks == value.ticks and adjusted.boundary is value.boundary
        return adjusted == value
    except (TypeError, ValueError, ArithmeticError):
        return False


def take_table(table, *, encode, charge_text, reserve):
    """Capture through one parent traversal and its shared budgets/cycle guard.

    encode validates/captures each cell at parent depth+1; reserve and
    charge_text charge the same global budgets as all other values. These
    callbacks are trusted. Metadata contains only immutable builtin tuples,
    strings, integers and booleans. No schema object is retained in a snapshot.
    """
    if type(table) is not BSLValueTable:
        raise TableSnapshotError('expected exact ValueTable')
    try:
        if _field(table, '_bounded_slice_read') is not False:
            raise TableSnapshotError('slice table is not admitted')
        columns, indexes, rows = (_field(table, name) for name in ('columns', 'indexes', 'rows'))
        if (type(columns) is not BSLValueTableColumnCollection or columns.table is not table
                or type(indexes) is not BSLCollectionIndexes or indexes.table is not table
                or type(columns.items) is not list or type(indexes.items) is not list
                or type(rows) is not list):
            raise TableSnapshotError('invalid table owner or indexes')
        col_items = columns.items
        if (len(col_items) > MAX_COLUMNS or len(rows) > MAX_ROWS
                or len(col_items) * len(rows) > MAX_CELLS or (not col_items and rows)):
            raise TableSnapshotError('invalid or oversized table shape')
        _index_bounds(len(indexes.items), 0, len(rows))
        reserve(len(col_items) + len(rows))
        schema, descriptions, seen_names, column_positions = [], [], set(), {}
        plain = not indexes.items
        for position, column in enumerate(col_items):
            if (type(column) is not BSLValueTableColumn or column.table is not table
                    or column._deleted is not False or id(column) in column_positions):
                raise TableSnapshotError('unsupported or invalid column')
            folded = _name(column.name)
            if folded in seen_names:
                raise TableSnapshotError('duplicate column name')
            seen_names.add(folded)
            column_positions[id(column)] = position
            title, width = _title(column.title), _count(column.width, 2 ** 32 - 1)
            payload, description = _take_description(column.value_type)
            charge_text(column.name)
            charge_text(title)
            plain = plain and payload == _EMPTY_DESCRIPTION and title == '' and width == 0
            schema.append((column.name, payload, title, width))
            descriptions.append(description)
        if not plain:
            reserve(sum(_schema_extra(column[1]) for column in schema))
        definitions = _take_indexes(table, indexes.items, column_positions, len(rows), reserve)
        weights = [0] * len(col_items)
        for definition in definitions:
            for position in definition:
                weights[position] += 1
        index_units = 0
        encoded_rows, row_ids = [], set()
        for row in rows:
            if (type(row) is not BSLValueTableRow or row.table is not table
                    or row._deleted is not False or id(row) in row_ids
                    or type(row.cells) is not dict or len(row.cells) != len(col_items)):
                raise TableSnapshotError('invalid table row')
            row_ids.add(id(row))
            values = {}
            for key, value in row.cells.items():
                if type(key) is not BSLValueTableColumn or id(key) not in column_positions:
                    raise TableSnapshotError('invalid table cell owner')
                values[id(key)] = value
            cells = []
            for position, (column, description) in enumerate(zip(col_items, descriptions)):
                value = values[id(column)]
                node = encode(value)  # Parent admission/bounds precede scalar adjustment.
                if not _cell_matches(description, value):
                    raise TableSnapshotError('cell does not match scalar schema')
                if weights[position]:
                    try:
                        index_units += weights[position] * _index_key_units((_index_token(value),))
                    except (TypeError, ValueError, ArithmeticError):
                        raise TableSnapshotError('unsupported table index key') from None
                    if index_units > _MAX_INDEX_UNITS:
                        raise TableSnapshotError('table index key budget exceeded')
                cells.append(node)
            encoded_rows.append(tuple(cells))
        if plain:
            return ('value_table', tuple(column[0] for column in schema), tuple(encoded_rows))
        return ('value_table', tuple(schema), tuple(encoded_rows), definitions)
    except (AttributeError, KeyError):
        raise TableSnapshotError('incomplete table state') from None


def restore_table(node, *, decode, charge_text, reserve):
    """Validate framing/schema before allocation and return only a complete graph.

    Plain three-field snapshots remain valid. Extended four-field snapshots
    carry column schemas and index positions. Rows are built untyped, validated
    without coercion, then given their reconstructed descriptors, just as query
    Unload publishes nullable metadata only after filling its scalar rows.
    """
    if (type(node) is not tuple or len(node) not in (3, 4) or type(node[0]) is not str
            or node[0] != 'value_table'):
        raise TableSnapshotError('invalid table snapshot')
    columns, rows = node[1], node[2]
    _dimensions(columns, rows)
    reserve(len(columns) + len(rows))
    extended = len(node) == 4
    schema, seen = [], set()
    for column in columns:
        if extended:
            if type(column) is not tuple or len(column) != 4:
                raise TableSnapshotError('invalid column snapshot')
            name, payload, title, width = column
            description = _description(payload)
            reserve(_schema_extra(payload))
            _title(title)
            _integer(width, 2 ** 32 - 1)
        else:
            name, title, width, description = column, '', 0, BSLTypeDescription()
        folded = _name(name)
        if folded in seen:
            raise TableSnapshotError('duplicate column name')
        seen.add(folded)
        charge_text(name)
        charge_text(title)
        schema.append((name, description, title, width))
    definitions = node[3] if extended else ()
    _restore_indexes(definitions, len(columns), len(rows), reserve)
    for row in rows:
        if type(row) is not tuple or len(row) != len(columns):
            raise TableSnapshotError('invalid table row snapshot')
    table = BSLValueTable()
    for name, _, title, width in schema:
        table.columns.add(name, None, title, Decimal(width))
    for cells in rows:
        row = table.add()
        for position, (cell, column) in enumerate(zip(cells, schema)):
            value = decode(cell)
            if not _cell_matches(column[1], value):
                raise TableSnapshotError('cell does not match scalar schema')
            row.set(Decimal(position), value)
    for column, (_, description, _, _) in zip(table.columns.items, schema):
        column.value_type = description
    try:
        for definition in definitions:
            table.indexes._add_columns([table.columns.items[position] for position in definition])
    except (TypeError, ValueError, ArithmeticError):
        raise TableSnapshotError('table index cannot be rebuilt within runtime limits') from None
    return table
