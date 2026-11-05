"""Bounded metadata assignment conversion, not a permissive storage decoder.

The half-up checkpoint is shared with TypeDescription/ValueTable observations;
CatalogObject assignment/Write still needs its own native measurement. These
resource limits and refusal of split UTF-16 surrogates are local safety rules.
"""
import sys
from decimal import Decimal

from .numeric.numbers import round_number

_MAX_TEXT_CHARS = 65536
_MAX_DECIMAL_BYTES = 2048


def _string_bytes(value, length):
    if type(value) is not str:
        raise TypeError('catalog String required')
    if type(length) is not int or not 0 <= length <= 65536:
        raise ValueError('unsupported catalog String qualifier')
    if len(value) > _MAX_TEXT_CHARS:
        raise ValueError('catalog String resource limit')
    # Strict encoding rejects even a surrogate in the discarded suffix. Never
    # repair, substitute, or silently discard malformed incoming Unicode.
    return value.encode('utf-16-le')


def normalize_string(value, length):
    encoded = _string_bytes(value, length)
    # Strict decode deliberately refuses an otherwise native split surrogate:
    # the result cannot be represented in our strict UTF-8 SQLite storage.
    return encoded[:length * 2].decode('utf-16-le')


def validate_string(value, length):
    """Strict read/codec boundary: no truncation of persisted data."""
    if len(_string_bytes(value, length)) > length * 2:
        raise ValueError('catalog String length')


def bound_number(value):
    if type(value) is not Decimal:
        raise TypeError('catalog Number required')
    if not value.is_finite():
        raise ValueError('finite catalog Number required')
    # as_tuple() allocates proportional to coefficient size. Refuse before it
    # is called, using the same explicit CPython boundary as backend scans.
    if sys.implementation.name != 'cpython' or Decimal.__sizeof__ is object.__sizeof__:
        raise ValueError('unsupported catalog Number resource accounting')
    if value.__sizeof__() > _MAX_DECIMAL_BYTES:
        raise ValueError('catalog Number resource limit')


def normalize_number(value, qualifiers):
    bound_number(value)
    if (type(qualifiers) is not tuple or len(qualifiers) != 3
            or type(qualifiers[0]) is not int or not 1 <= qualifiers[0] <= 38
            or type(qualifiers[1]) is not int or not 0 <= qualifiers[1] <= qualifiers[0]
            or type(qualifiers[2]) is not str or qualifiers[2] not in ('Any', 'Nonnegative')):
        raise ValueError('unsupported catalog Number qualifiers')
    digits, scale, sign = qualifiers
    if sign == 'Nonnegative' and value < 0:
        return Decimal(0)
    # Preserve the sign of already valid zero for historical canonical receipts.
    # Its exponent is bounded without expanding a tiny/huge exponent into text.
    if value.is_zero():
        return Decimal((value.as_tuple().sign, (0,), -scale))
    maximum = Decimal((0, (9,) * digits, -scale))
    if value.copy_abs() > maximum:
        return maximum.copy_negate() if value.is_signed() else maximum
    rounded = round_number(value, Decimal(scale))
    if rounded.copy_abs() > maximum:
        return maximum.copy_negate() if rounded.is_signed() else maximum
    return rounded


def normalize_field(value, field):
    if field.kind == 'string':
        if type(field.qualifiers) is not tuple or len(field.qualifiers) != 1:
            raise ValueError('unsupported catalog String qualifiers')
        return normalize_string(value, field.qualifiers[0])
    if field.kind == 'number':
        return normalize_number(value, field.qualifiers)
    # Dates/references/Booleans keep their existing exact-type validation.
    return value
