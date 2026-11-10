"""Bounded independent periodic register dates and logical edge selection.

Dimension filters apply before edge selection. Query WHERE applies afterwards.
This is an explicit local contract, not a native parity claim.
"""
from .dates import BSLDate, TICKS_PER_SECOND, _parts, _from_parts

PERIODICITIES = ('WithinSecond', 'Day', 'Month', 'Quarter', 'Year')


def period(value, periodicity):
    if type(value) is not BSLDate: raise TypeError('Period requires Date')
    value.require_known()
    if type(periodicity) is not str or periodicity not in PERIODICITIES:
        raise ValueError('unsupported register periodicity')
    if periodicity == 'WithinSecond':
        return BSLDate(value.ticks // TICKS_PER_SECOND * TICKS_PER_SECOND)
    dt = _parts(value)
    month = 1 if periodicity == 'Year' else ((dt.month-1)//3*3+1 if periodicity == 'Quarter' else dt.month)
    day = dt.day if periodicity == 'Day' else 1
    return _from_parts((dt.year, month, day, 0, 0, 0))


def moment(value):
    if type(value) is not BSLDate: raise TypeError('slice boundary requires Date')
    value.require_known()
    if value.ticks % TICKS_PER_SECOND: raise ValueError('slice bounds require whole seconds')
    return value


def storage_moment(value):
    from datetime import datetime
    if type(value) is not datetime or value.tzinfo is not None or value.microsecond:
        raise TypeError('register boundary requires naive whole-second datetime')
    return value


def storage_period(value, periodicity):
    value=storage_moment(value)
    from .dates import _EPOCH
    delta=value-_EPOCH
    normalized=period(BSLDate((delta.days*86400+delta.seconds)*TICKS_PER_SECOND),periodicity)
    return _parts(normalized)


def edge_records(records, schema, boundary, first=False):
    """Choose one record per exact typed dimension identity, inclusively."""
    from .sqlite_registers import _dimension
    storage_moment(boundary)
    if not schema.periodic or type(first) is not bool: raise ValueError('periodic register required')
    chosen = {}
    for row in records:
        when = row.key.dimensions[0]
        if (when < boundary if first else when > boundary): continue
        # Canonical scalar encoding preserves exact strings and reference scope.
        import json
        key = json.dumps([_dimension(v, f, row.key.database_id)
                          for f, v in zip(schema.dimensions, row.key.dimensions[1:])],
                         ensure_ascii=False, separators=(',', ':'))
        old = chosen.get(key)
        if old is None or (when < old.key.dimensions[0] if first
                           else when > old.key.dimensions[0]):
            chosen[key] = row
    return tuple(chosen[k] for k in sorted(chosen))
