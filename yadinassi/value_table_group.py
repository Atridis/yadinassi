"""Bounded GroupBy backed by the genuine PR64 owner observations.

Single-type totals preserve singleton cells and qualify after each merge,
as established by the genuine owner supplement 6e8d31f. Unsupported composite
conversion targets and object grouping keys fail before mutation.
"""
from decimal import Decimal, localcontext

from .dates import BSLDate
from .type_descriptions import _number_value
from .values import BSLType, NULL
from .value_tables import _adjust, _text, _MAX_COLUMNS, _MAX_TOTAL_PRECISION


_MAX_GROUP_CELLS = 1_000_000
_MAX_GROUP_TEXT = 1_000_000


def _columns(table, specification):
    if specification is None:
        return []
    specification = _text(specification)
    # Check before split allocates a potentially huge list of empty names.
    if specification.count(',') + 1 > _MAX_COLUMNS:
        raise ValueError('Свернуть: превышен предел колонок Yadinassi')
    names = specification.split(',')
    result = []
    for name in names:
        name = name.strip()
        if name:
            column = table.columns.get_index(name)
            if column not in result:
                result.append(column)
    return result


def _scalar_key(value):
    if value is None or value is NULL:
        return (type(value), value)
    if type(value) in (str, bool):
        if type(value) is str:
            _text(value)
        return (type(value), value)
    if type(value) is Decimal:
        _number_value(value)
        if abs(value.adjusted()) > 4096:
            raise ValueError('Свернуть: превышен предел числа Yadinassi')
        return (Decimal, value)
    if type(value) is BSLDate:
        value.require_known()
        return (BSLDate, value.ticks)
    raise ValueError('Свернуть: группировка этого типа пока не подтверждена')


def _sum(values):
    if not values:
        return Decimal(0)
    for value in values:
        _number_value(value)
        if abs(value.adjusted()) > 4096:
            raise ValueError('Свернуть: превышен предел числа Yadinassi')
    precision = (max(v.adjusted() for v in values)
                 - min(v.as_tuple().exponent for v in values)
                 + 1 + len(str(len(values))))
    if precision > _MAX_TOTAL_PRECISION:
        raise ValueError('Свернуть: превышен предел точности Yadinassi')
    with localcontext() as ctx:
        ctx.prec = max(1, precision)
        ctx.Emax, ctx.Emin = 999999, -999999
        return sum(values[1:], values[0])


def _numeric(value):
    if type(value) in (Decimal, str, bool) or value is None:
        return _number_value(value)
    if type(value) is BSLDate:
        value.require_known()
        return Decimal(0)
    if value is NULL:
        return Decimal(0)
    raise ValueError('Свернуть: суммирование этого типа пока не подтверждено')


def _single_type_total(description, values):
    """Native retains the first cell, then converts/adds/qualifies per merge."""
    result = values[0]
    for value in values[1:]:
        result = _adjust(description, _sum([_numeric(result), _numeric(value)]))
    return result


def _total(column, rows):
    description = column.value_type
    kinds = description.types
    values = [row.cells[column] for row in rows]
    if len(kinds) == 1:
        return _single_type_total(description, values)
    if kinds and BSLType.NUMBER not in kinds:
        if set(kinds) == {BSLType.STRING, BSLType.BOOLEAN}:
            # Native assigns Number 0 through this composite column as String.
            from .type_descriptions import _qualified_string
            return _qualified_string(Decimal(0), description.string_qualifiers)
        raise ValueError('Свернуть: нулевая сумма этого составного типа пока не подтверждена')
    numeric = [v for v in values if type(v) is Decimal]
    result = _adjust(description, _sum(numeric))
    if kinds:
        # The supplement proves per-merge qualification for a single Number
        # type, not composite Number columns. Defer only distinguishable cases.
        folded = Decimal(0)
        for value in numeric:
            folded = _adjust(description, _sum([folded, value]))
        if folded != result:
            raise ValueError('Свернуть: порядок приведения составной суммы пока не подтвержден')
    return result


def group_by(table, grouping_columns, totaling_columns=None):
    groups = _columns(table, grouping_columns)
    totals = _columns(table, totaling_columns)
    if any(column in totals for column in groups):
        raise ValueError('Списки колонок группировки и суммирования пересекаются')
    retained = set(groups + totals)
    # Build every key and total before touching row values or schema.
    if len(table.rows) * len(retained) > _MAX_GROUP_CELLS:
        raise ValueError('Свернуть: превышен предел ячеек Yadinassi')
    text_budget = 0
    for row in table.rows:
        for column in retained:
            value = row.cells[column]
            if type(value) is str:
                text_budget += len(value)
                if text_budget > _MAX_GROUP_TEXT:
                    raise ValueError('Свернуть: превышен предел текста Yadinassi')
    buckets = {}
    if retained:
        for row in table.rows:
            key = tuple(_scalar_key(row.cells[column]) for column in groups)
            buckets.setdefault(key, []).append(row)
    calculated = [(rows, {column: _total(column, rows) for column in totals})
                  for rows in buckets.values()]
    survivors = [rows[0] for rows, _ in calculated]
    survivor_set = set(survivors)
    # All validation is complete. Native GroupBy discards definitions; do so
    # once before schema changes, avoiding a full index rebuild per column.
    table.indexes.clear()
    for rows, sums in calculated:
        rows[0].cells.update(sums)
    for row in table.rows:
        if row not in survivor_set:
            row._deleted = True
            row.cells.clear()
    table.rows[:] = survivors
    for column in list(table.columns.items):
        if column not in retained:
            table.columns.delete(column)
