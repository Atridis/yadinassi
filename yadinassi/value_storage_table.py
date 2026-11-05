"""Bounded ValueTable snapshot hooks for in-process ValueStorage traversal.

No native table codec; no typed/qualified columns, indices or schema metadata.
The one native one-cell mutation witness does not establish the local limits or
multi-cell extension below. The hooks are used by the ValueStorage runtime.
"""
from decimal import Decimal

from .structures import _key
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
                              BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers,
                              BSLStringQualifiers)
from .value_tables import (BSLCollectionIndexes, BSLValueTable, BSLValueTableColumn,
                           BSLValueTableColumnCollection, BSLValueTableRow)

MAX_COLUMNS = 64
MAX_ROWS = 1024
MAX_CELLS = 4096
MAX_NAME_UNITS = 128


class TableSnapshotError(ValueError):
    """Table shape, metadata or local budget is not supported."""


def _zero(value):
    # Constructors normalize metadata to a canonical Decimal(0). Do not silently
    # erase malformed sign/exponent state injected through host access.
    if type(value) is not Decimal or not value.is_finite() or not value.is_zero():
        return False
    parts = value.as_tuple()
    return parts.sign == 0 and parts.digits == (0,) and parts.exponent == 0


def _untyped_default(description):
    # No arbitrary equality, conversion, stringification or arbitrary host hooks.
    if type(description) is not BSLTypeDescription:
        return False
    try:
        types = description.types
        n, s, d, b = (description.number_qualifiers, description.string_qualifiers,
                      description.date_qualifiers, description.binary_data_qualifiers)
        return (type(types) is tuple and not types and description._query_scalar is None
                and type(n) is BSLNumberQualifiers and _zero(n.digits)
                and _zero(n.fraction_digits) and n.allowed_sign is BSLAllowedSign.ANY
                and type(s) is BSLStringQualifiers and _zero(s.length)
                and s.allowed_length is BSLAllowedLength.VARIABLE
                and type(d) is BSLDateQualifiers and d.date_fractions is BSLDateFractions.DATE_TIME
                and type(b) is BSLBinaryDataQualifiers and _zero(b.length)
                and b.allowed_length is BSLAllowedLength.VARIABLE)
    except AttributeError:
        return False


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


def take_table(table, *, encode, charge_text, reserve):
    """Capture via one shared parent traversal, with no changes to source table.

    Parent callbacks: reserve(n) charges n metadata nodes against its global
    limit before copying; charge_text(str) charges UTF-16 units; encode(value)
    recursively captures a cell at parent depth+1 using the SAME global budgets
    and active-path cycle guard. Parent has already charged/entered this table
    and must exit the active path in finally. Callbacks must be trusted.
    """
    if type(table) is not BSLValueTable:
        raise TableSnapshotError('expected exact ValueTable')
    try:
        if table._bounded_slice_read is not False:
            raise TableSnapshotError('slice table is not admitted')
        columns, indexes, rows = table.columns, table.indexes, table.rows
        if (type(columns) is not BSLValueTableColumnCollection or columns.table is not table
                or type(indexes) is not BSLCollectionIndexes or indexes.table is not table
                or type(columns.items) is not list or type(indexes.items) is not list
                or indexes.items or type(rows) is not list):
            raise TableSnapshotError('invalid table owner or indexes')
        col_items = columns.items
        # Bounds before copying, iteration or callbacks.
        if (len(col_items) > MAX_COLUMNS or len(rows) > MAX_ROWS
                or len(col_items) * len(rows) > MAX_CELLS or (not col_items and rows)):
            raise TableSnapshotError('invalid or oversized table shape')
        reserve(len(col_items) + len(rows))
        names, seen_names, column_ids = [], set(), set()
        for column in col_items:
            if (type(column) is not BSLValueTableColumn or column.table is not table
                    or column._deleted is not False or id(column) in column_ids
                    or type(column.title) is not str or column.title != ''
                    or not _zero(column.width) or not _untyped_default(column.value_type)):
                raise TableSnapshotError('unsupported or invalid column')
            folded = _name(column.name)
            if folded in seen_names:
                raise TableSnapshotError('duplicate column name')
            seen_names.add(folded)
            column_ids.add(id(column))
            charge_text(column.name)
            names.append(column.name)
        encoded_rows, row_ids = [], set()
        for row in rows:
            if (type(row) is not BSLValueTableRow or row.table is not table
                    or row._deleted is not False or id(row) in row_ids
                    or type(row.cells) is not dict or len(row.cells) != len(col_items)):
                raise TableSnapshotError('invalid table row')
            row_ids.add(id(row))
            values = {}
            for key, value in row.cells.items():
                if type(key) is not BSLValueTableColumn or id(key) not in column_ids:
                    raise TableSnapshotError('invalid table cell owner')
                values[id(key)] = value
            # Build from ordered names/columns, never retain source dictionary keys.
            encoded_rows.append(tuple(encode(values[id(column)]) for column in col_items))
        return ('value_table', tuple(names), tuple(encoded_rows))
    except (AttributeError, KeyError):
        raise TableSnapshotError('incomplete table state') from None


def restore_table(node, *, decode, charge_text, reserve):
    """Restore a fresh owner graph; decode uses the parent's trusted node policy.

    This validates table framing before allocating a table. reserve and
    charge_text share the parent's restore budget; decode is the parent's
    depth+1 validating recursive decoder. On failure no table is returned.
    """
    if (type(node) is not tuple or len(node) != 3 or type(node[0]) is not str
            or node[0] != 'value_table'):
        raise TableSnapshotError('invalid table snapshot')
    names, rows = node[1], node[2]
    _dimensions(names, rows)
    reserve(len(names) + len(rows))
    seen = set()
    for name in names:
        folded = _name(name)
        if folded in seen:
            raise TableSnapshotError('duplicate column name')
        seen.add(folded)
        charge_text(name)
    for row in rows:
        if type(row) is not tuple or len(row) != len(names):
            raise TableSnapshotError('invalid table row snapshot')
    # Use constructors and public mutation, not copied owner/key internals.
    table = BSLValueTable()
    for name in names:
        table.columns.add(name)
    for cells in rows:
        row = table.add()
        for index, cell in enumerate(cells):
            row.set(Decimal(index), decode(cell))
    return table
