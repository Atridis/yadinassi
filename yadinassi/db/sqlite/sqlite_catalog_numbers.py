"""Exact catalog SQL operators over metadata-scaled numeric fields."""
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_typed_rows import encode_number, raw_number_coefficient


def _decimal(coefficient, scale):
    return Decimal((int(coefficient < 0), tuple(map(int, str(abs(coefficient)))), -scale))


def comparison(column, field, operator, operand):
    """Translate a validated Decimal predicate without rounding the operand."""
    precision, scale, sign = field.qualifiers
    maximum = 10**precision - 1
    minimum = 0 if sign == 'Nonnegative' else -maximum
    numerator, denominator = operand.as_integer_ratio()
    floor, fraction = divmod(numerator * 10**scale, denominator)
    if operator in ('eq', 'ne'):
        if fraction or not minimum <= floor <= maximum:
            return ('0' if operator == 'eq' else '1'), ()
        symbol = '=' if operator == 'eq' else '!='
        pivot = floor
    else:
        # Convert strict lower and inclusive upper comparisons to an integer
        # threshold; this preserves half steps and negative operands exactly.
        if operator in ('lt', 'le'):
            pivot = floor - (operator == 'lt' and not fraction)
            if pivot < minimum: return '0', ()
            if pivot >= maximum: return '1', ()
            symbol = '<='
        else:
            pivot = floor + (operator == 'gt' or bool(fraction))
            if pivot <= minimum: return '1', ()
            if pivot > maximum: return '0', ()
            symbol = '>='
    return f'({column} {symbol} ?)', (encode_number(_decimal(pivot, scale), field),)


class _SumCoefficients:
    """SQLite callbacks see only raw int/16-byte sortable signed coefficients."""
    def __init__(self):
        self.total = 0

    def step(self, raw):
        self.total += raw_number_coefficient(raw)

    def finalize(self):
        # More than 64 bits even for narrow fields; no SQLite REAL or TEXT
        # accumulator. 24 bytes covers Number(38) times the admitted row count.
        return self.total.to_bytes(24, 'big', signed=True)


def register_aggregates(connection):
    connection.create_aggregate('yadinassi_sum_coefficients_v1', 1, _SumCoefficients)


def aggregate_result(raw, count, operation, field):
    if not count:
        if raw is not None: raise BackendError('integrity')
        return None
    if type(raw) is not bytes or len(raw) != 24: raise BackendError('integrity')
    value = _decimal(int.from_bytes(raw, 'big', signed=True), field.qualifiers[1])
    if operation == 'avg':
        # Match relational AVG exactly: high precision division then a
        # single half-even quantization to the guest-visible ten places.
        context = Context(prec=80, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                          traps=[InvalidOperation])
        value = context.quantize(context.divide(value, Decimal(count)), Decimal('0.0000000001'))
    return value
