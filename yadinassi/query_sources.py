"""Typed external snapshots and UNION for the bounded host query contract.

No ValueTable codec, implicit casts or dynamic TypeDescription admission. Source
buffers never escape into results; every external cell is validated before reads.
"""
from dataclasses import replace
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN

from . import query_parser as syntax
from .catalog_qualifiers import bound_number
from .dates import BSLDate, TICKS_PER_SECOND
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import BSLAllowedLength, BSLAllowedSign, BSLDateFractions
from .value_tables import (BSLValueTable, BSLValueTableColumn,
                           BSLValueTableColumnCollection, BSLValueTableRow)
from .values import BSLType, NULL


def _external_column(column):
    from .queries import _Column
    description = column.value_type
    if type(description) is not BSLTypeDescription:
        raise TypeError('External query columns require TypeDescription')
    kinds = tuple(t for t in description.types if t is not BSLType.NULL)
    if len(kinds) != 1:
        raise TypeError('External query columns require one scalar type, optionally nullable')
    kind = kinds[0]
    if kind is BSLType.STRING:
        q = description.string_qualifiers
        length = int(q.length)
        if not 0 <= length <= 65536:
            raise ValueError('External query String qualifier limit exceeded')
        qualifiers = (length, 'Fixed') if q.allowed_length is BSLAllowedLength.FIXED else (length,)
        name = 'string'
    elif kind is BSLType.NUMBER:
        q = description.number_qualifiers
        digits, scale = int(q.digits), int(q.fraction_digits)
        if not 1 <= digits <= 38 or not 0 <= scale <= digits:
            raise ValueError('External query Number requires bounded precision 1..38')
        qualifiers = (digits, scale, 'Nonnegative' if q.allowed_sign is BSLAllowedSign.NONNEGATIVE else 'Any')
        name = 'number'
    elif kind is BSLType.DATE:
        qualifiers = ({BSLDateFractions.DATE: 'Date', BSLDateFractions.TIME: 'Time',
                       BSLDateFractions.DATE_TIME: 'DateTime'}[description.date_qualifiers.date_fractions],)
        name = 'datetime'
    elif kind is BSLType.BOOLEAN:
        name, qualifiers = 'boolean', ()
    else:
        raise TypeError('External query columns support only String, Number, Boolean and Date')
    return _Column(column.name, None, name, qualifiers, explicit_alias=True)


def _check_number(value, qualifiers):
    bound_number(value)
    digits, scale, sign = qualifiers
    context = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999,
                      Emax=999999, capitals=1, clamp=0, flags=[], traps=[InvalidOperation])
    if (abs(value.adjusted()) > 38 or len(value.as_tuple().digits) > 38
            or value.copy_abs() >= Decimal((0, (1,), digits - scale))
            or (sign == 'Nonnegative' and value < 0)
            or context.quantize(value, Decimal((0, (1,), -scale))) != value):
        raise ValueError('Query Number is outside output qualifiers')


def _external_value(value, column, nullable):
    if value is NULL:
        if not nullable: raise TypeError('External query NULL requires nullable column metadata')
        return value
    expected = {'string': str, 'number': Decimal, 'datetime': BSLDate, 'boolean': bool}[column.kind]
    if type(value) is not expected:
        raise TypeError('External query cell requires exact declared scalar type')
    if column.kind == 'number':
        _check_number(value, column.qualifiers)
    elif column.kind == 'string':
        if len(value) > 65536: raise ValueError('External query String resource limit exceeded')
        units = len(value.encode('utf-16-le')) // 2
        length = column.qualifiers[0]
        if length and (units > length or (column.qualifiers[1:] == ('Fixed',) and units != length)):
            raise ValueError('External query String is outside declared qualifiers')
    elif column.kind == 'datetime':
        value.require_known()
        day = 86400 * TICKS_PER_SECOND
        fraction = column.qualifiers[0]
        if ((fraction == 'Date' and value.ticks % day)
                or (fraction == 'Time' and (value.ticks >= day or value.ticks % TICKS_PER_SECOND))):
            raise ValueError('External query Date is outside declared qualifiers')
    return value


def _snapshot(value, budget):
    from .queries import _MAX_CELLS, _MAX_RESULT_TEXT
    from .query_packages import _Table
    if type(value) is not BSLValueTable:
        raise TypeError('External query source requires ValueTable')
    if value._bounded_slice_read:
        raise ValueError('Restricted slice tables are not external query sources')
    if (type(value.rows) is not list or type(value.columns) is not BSLValueTableColumnCollection
            or value.columns.table is not value or type(value.columns.items) is not list):
        raise TypeError('Malformed external query table')
    if not 1 <= len(value.columns.items) <= 128 or len(value.rows) > syntax.MAX_ROWS:
        raise ValueError('External query source size limit exceeded')
    budget[0] += len(value.columns.items) * len(value.rows)
    if budget[0] > _MAX_CELLS: raise ValueError('External query source cell limit exceeded')
    original, columns, nullables, names = tuple(value.columns.items), [], [], set()
    for column in original:
        if (type(column) is not BSLValueTableColumn or column.table is not value or column._deleted
                or not syntax.identifier(column.name)):
            raise ValueError('Invalid external query column')
        key = column.name.casefold()
        if key in names: raise ValueError('Duplicate external query column')
        names.add(key)
        columns.append(_external_column(column))
        nullables.append(any(t is BSLType.NULL for t in column.value_type.types))
    rows = []
    for row in value.rows:
        if (type(row) is not BSLValueTableRow or row.table is not value or row._deleted
                or type(row.cells) is not dict or len(row.cells) != len(original)
                or any(type(key) is not BSLValueTableColumn for key in row.cells)):
            raise TypeError('Malformed external query row')
        values = []
        for source, column, nullable in zip(original, columns, nullables):
            if source not in row.cells: raise ValueError('Missing external query cell')
            cell = _external_value(row.cells[source], column, nullable)
            budget[1] += len(cell) if type(cell) is str else 0
            if budget[1] > _MAX_RESULT_TEXT: raise ValueError('External query source text limit exceeded')
            values.append(cell)
        rows.append(tuple(values))
    return _Table(tuple(columns), tuple(rows))


def snapshot_sources(statements, parameters):
    """Capture each referenced parameter once, before any statement/database read."""
    result, budget = {}, [0, 0]
    for arm in syntax.selects(statements):
        names = ([arm.catalog] if arm.external else []) + [j.source.catalog for j in arm.joins if j.source.external]
        for name in names:
            key = name.casefold()
            if key in result: continue
            if key not in parameters: raise ValueError('External query parameter is not set')
            result[key] = _snapshot(parameters[key], budget)
    return result


def _union_column(columns, enum_scope=None):
    first = columns[0]
    typed = [c for c in columns if c.kind != 'null']
    if not typed: raise TypeError('UNION NULL column requires a typed arm')
    kind = typed[0].kind
    if any(c.kind != kind for c in typed): raise TypeError('UNION columns require the same type')
    qualifiers, identity = typed[0].qualifiers, typed[0].reference_identity
    if kind == 'number':
        scale = max(c.qualifiers[1] for c in typed)
        integer = max(c.qualifiers[0] - c.qualifiers[1] for c in typed)
        sign = 'Nonnegative' if all(c.qualifiers[2] == 'Nonnegative' for c in typed) else 'Any'
        # Metadata never exceeds 38 digits; exact values are checked, not rounded.
        qualifiers = (min(38, integer + scale), scale, sign)
    elif kind == 'string':
        lengths = [c.qualifiers[0] for c in typed]
        length = 0 if 0 in lengths else max(lengths)
        qualifiers = ((length, 'Fixed') if all(c.qualifiers == (length, 'Fixed') for c in typed) else (length,))
    elif kind == 'datetime':
        if any(c.qualifiers != qualifiers for c in typed): qualifiers = ('DateTime',)
    elif kind in ('catalog_ref', 'document_ref'):
        if any(c.reference_identity[0] is not identity[0] or c.reference_identity[1] != identity[1] for c in typed):
            raise TypeError('UNION references require same database and catalog')
    descriptor = None
    if kind == 'enum_ref':
        if enum_scope is None:
            raise ValueError('Enum UNION output is outside this profile')
        descriptor = enum_scope.require_same(tuple(c.enum_descriptor for c in typed))
        identity = (descriptor.value_type.snapshot, descriptor.value_type.metadata_uuid)
    return replace(first, kind=kind, qualifiers=qualifiers, custom=None,
                   reference_identity=identity, enum_descriptor=descriptor)


class _UnionPlan:
    def __init__(self, query, catalogs, parameters, temporary_tables=None, external_tables=None, *, documents=None, information_registers=None, enum_scope=None):
        from .relational_queries import _Plan
        self.query = query
        self.arms = tuple(_Plan(arm, catalogs, parameters, temporary_tables, external_tables, allow_null=True, documents=documents,
                                 information_registers=information_registers, enum_scope=enum_scope)
                          for arm in query.arms)
        width = len(self.arms[0].columns)
        if any(len(arm.columns) != width for arm in self.arms):
            raise ValueError('UNION column counts must match')
        self.columns = tuple(_union_column(columns, enum_scope) for columns in zip(*(arm.columns for arm in self.arms)))
        self.managers = tuple(manager for arm in self.arms for manager in arm.all_managers)
        self.all_managers = self.managers
        aliases = {p.alias.casefold(): i for i, p in enumerate(query.arms[0].projections)}
        aliases.update({c.name.casefold(): i for i, c in enumerate(self.columns)})
        self.orders = []
        for order in query.order:
            if (type(order.field) is not syntax.Field or len(order.field.parts) != 1
                    or order.field.parts[0].casefold() not in aliases):
                raise ValueError('UNION ORDER BY requires a first-arm output column')
            index = aliases[order.field.parts[0].casefold()]
            if self.columns[index].kind == 'enum_ref':
                raise ValueError('Enum UNION ordering is outside this profile')
            self.orders.append((index, order.descending))

    def execute(self, view=None, budget=None):
        from .queries import BSLQueryResult, _MAX_CELLS, _MAX_RESULT_TEXT
        from .relational_queries import _key
        if budget is None: budget = [0, 0]
        rows, cells, text = [], 0, 0
        for index, arm in enumerate(self.arms):
            output = arm.execute(view=view, budget=budget)
            cells += len(output._rows) * len(self.columns)
            text += sum(len(v) for row in output._rows for v in row if type(v) is str)
            if cells > _MAX_CELLS or text > _MAX_RESULT_TEXT:
                raise ValueError('UNION result resource limit exceeded')
            distinct = index > 0 and not self.query.all[index - 1]
            unique = {}
            if distinct:
                for row in rows: unique.setdefault(tuple(_key(v) for v in row), row)
                rows = list(unique.values())
            for row in output._rows:
                for column, value in zip(self.columns, row):
                    if column.kind == 'number' and value is not NULL: _check_number(value, column.qualifiers)
                if distinct:
                    key = tuple(_key(v) for v in row)
                    if key in unique: continue
                    unique[key] = row
                rows.append(row)
                if len(rows) > syntax.MAX_ROWS: raise ValueError('UNION row limit exceeded')
        for index, descending in reversed(self.orders):
            rows.sort(key=lambda row: (row[index] is not NULL, _key(row[index])), reverse=descending)
        return BSLQueryResult(self.columns, tuple(rows))
