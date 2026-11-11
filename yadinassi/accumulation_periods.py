"""Closed date binding and overflow-safe calendar indexing for stock statements.

This module does not choose native opening/closing endpoints, row retention or
period completion. Those policies belong to the independently observed virtual
source reducer. Calendar indexing alone never expands an interval into rows.
"""
from dataclasses import dataclass
from datetime import datetime

from .dates import BSLDate, TICKS_PER_SECOND, _parts


def bind_dates(arguments, parameters, count):
    """Validate every period argument before a database read lease is opened."""
    from .query_parser import Parameter
    if type(arguments) is not tuple or len(arguments) != count:
        raise ValueError('Invalid accumulation virtual source')
    result = []
    for parameter in arguments:
        if type(parameter) is not Parameter:
            raise ValueError('Accumulation source requires named Date parameters')
        key = parameter.name.casefold()
        if key not in parameters:
            raise ValueError('Missing accumulation period parameter')
        value = parameters[key]
        if type(value) is not BSLDate or value.ticks % TICKS_PER_SECOND:
            raise TypeError('Accumulation source requires exact second-resolution Date')
        value.require_known()
        result.append(_parts(value))
    if count == 2 and result[0] > result[1]:
        raise ValueError('Reversed accumulation interval is outside this profile')
    return tuple(result)


def _moment(value):
    if (type(value) is not datetime or value.tzinfo is not None
            or value.microsecond or value.fold):
        raise TypeError('Period calendar requires an exact second-resolution datetime')
    return value


def _ordinal(value, periodicity):
    if periodicity == 'day':
        return value.toordinal() - 1
    return (value.year - 1) * 12 + value.month - 1


@dataclass(frozen=True, slots=True)
class CalendarSpan:
    """Constant-space closed Day/Month index, with explicitly bounded expansion.

    A calendar label may precede the requested start inside a partial bucket.
    It is not a query endpoint or an instruction to include earlier movements.
    No successor of year 9999 is constructed, even for its last day/month.
    """
    start: datetime
    end: datetime
    periodicity: str

    def __post_init__(self):
        _moment(self.start)
        _moment(self.end)
        if type(self.periodicity) is not str or self.periodicity not in ('day', 'month'):
            raise ValueError('Unsupported accumulation periodicity')
        if self.start > self.end:
            raise ValueError('Reversed accumulation interval is outside this profile')

    @property
    def count(self):
        return _ordinal(self.end, self.periodicity) - _ordinal(self.start, self.periodicity) + 1

    def index(self, value):
        value = _moment(value)
        if not self.start <= value <= self.end:
            raise ValueError('Movement is outside the requested period interval')
        return _ordinal(value, self.periodicity) - _ordinal(self.start, self.periodicity)

    def label(self, index):
        if type(index) is not int or not 0 <= index < self.count:
            raise ValueError('Invalid accumulation period index')
        ordinal = _ordinal(self.start, self.periodicity) + index
        if self.periodicity == 'day':
            return datetime.fromordinal(ordinal + 1)
        year, month = divmod(ordinal, 12)
        return datetime(year + 1, month + 1, 1)

    def bounded_indices(self, limit):
        if type(limit) is not int or limit < 0 or self.count > limit:
            raise ValueError('Query period expansion limit exceeded')
        return range(self.count)
