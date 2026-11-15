"""Closed date binding and overflow-safe calendar indexing for stock statements.

Calendar indexing alone never expands an interval into rows. The separate
StatementReducer implements the observed stock vector and sparse period-boundary
policy without owning a connection, opening another snapshot or changing storage.
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


class StatementReducer:
    """One-scan exact stock vectors and sparse calendar boundary rows.

    Native groups 1–13 establish opening < Start, inclusive flow endpoints,
    clipped first labels and movements plus nonzero period-boundary balances,
    not dense gap filling. This reducer owns no connection or read lease.
    The caller validates/charges every source row, including excluded rows.
    """
    def __init__(self, schema, start, end, periodicity, *, combined, enum_domain=None):
        self.enum_domain=enum_domain
        self.schema = schema
        self.start, self.end = _moment(start), _moment(end)
        self.span = CalendarSpan(start, end, periodicity) if periodicity else None
        self.combined = combined
        self.groups = {}
        self.width = len(schema.resources)

    def _coefficients(self, resources):
        # Reuse the existing exact input normalization and its hostile-context
        # guards. A single normalized vector has precisely the declared scale,
        # so integer extraction needs neither Decimal math nor a large power.
        from .accumulation_movements import _sum_resource_vectors
        normalized = _sum_resource_vectors(self.schema, (resources,), (1,), enum_domain=self.enum_domain)
        result = []
        for value in normalized:
            sign, digits, _ = value.as_tuple()
            coefficient = 0
            for digit in digits:
                coefficient = coefficient * 10 + digit
            result.append(-coefficient if sign else coefficient)
        return result

    def add(self, dimensions, key, row):
        from .accumulation_movements import AccumulationDirection
        if row.period > self.end or (not self.combined and row.period < self.start):
            return
        coefficients = self._coefficients(row.resources)
        group = self.groups.setdefault(key, (dimensions, [0] * self.width, {}))
        sign = 1 if row.direction is AccumulationDirection.RECEIPT else -1
        if row.period < self.start:
            for i, value in enumerate(coefficients):
                group[1][i] += sign * value
            return
        index = self.span.index(row.period) if self.span else 0
        flows = group[2].setdefault(index, ([0] * self.width, [0] * self.width))
        selected = flows[0 if sign == 1 else 1]
        for i, value in enumerate(coefficients):
            selected[i] += value

    def _decimals(self, coefficients):
        from decimal import Decimal
        return tuple(Decimal((int(value < 0), Decimal(abs(value)).as_tuple().digits,
                              -field.qualifiers[1]))
                     for value, field in zip(coefficients, self.schema.resources))

    def rows(self, limit):
        candidates = 0
        plans = []
        last = self.span.count - 1 if self.span else 0
        for dimensions, opening, flows in self.groups.values():
            indices = set(flows)
            closing = list(opening)
            for receipt, expense in flows.values():
                for i in range(self.width):
                    closing[i] += receipt[i] - expense[i]
            if self.combined:
                if any(opening): indices.add(0)
                if any(closing): indices.add(last)
            candidates += len(indices)
            if candidates > limit:
                raise ValueError('Query period result row limit exceeded')
            plans.append((dimensions, opening, flows, sorted(indices)))
        for dimensions, opening, flows, indices in plans:
            balance = list(opening)
            for index in indices:
                receipt, expense = flows.get(index, ([0] * self.width, [0] * self.width))
                net = [r - e for r, e in zip(receipt, expense)]
                totals = {'turnover': net, 'receipt': receipt, 'expense': expense}
                if self.combined:
                    totals['openingbalance'] = tuple(balance)
                    for i, value in enumerate(net): balance[i] += value
                    totals['closingbalance'] = tuple(balance)
                if not any(value for vector in totals.values() for value in vector):
                    # Sparse period rows with no balance or flow do not poison
                    # unrelated groups/WHERE, as the shared native14 case10
                    # demonstrates after case6 created an all-zero occurrence.
                    continue
                period = max(self.start, self.span.label(index)) if self.span else None
                yield dimensions, period, {name: self._decimals(vector)
                                           for name, vector in totals.items()}
