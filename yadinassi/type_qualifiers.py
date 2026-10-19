"""Standalone qualifiers backed by the owner's native values checkpoint.

The observed constructors truncate positive fractions, clamp negative integral
Digits/Length to zero, and normalize zero-length Fixed to Variable. Negative
fractional counts and negative FractionDigits are not established and remain
explicitly unsupported. Boolean/Null and arbitrary host coercions are likewise
excluded. Numeric strings use the existing Number conversion policy.

The budgets below are local Yadinassi resource guards, not native upper bounds.
In particular, the native checkpoint accepts NumberQualifiers(39). Namespace
iteration has not been measured and is deliberately not implemented here.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import Enum

from .values import BSLObject, number


class BSLAllowedSign(Enum):
    """Opaque identities; the native stream ordinals are not Number values."""

    ANY = 0
    NONNEGATIVE = 1

    def __str__(self) -> str:
        return "Любой" if self is BSLAllowedSign.ANY else "Неотрицательный"


class BSLAllowedLength(Enum):
    FIXED = 0
    VARIABLE = 1

    def __str__(self) -> str:
        return "Фиксированная" if self is BSLAllowedLength.FIXED else "Переменная"


class BSLDateFractions(Enum):
    DATE = 1
    TIME = 2
    DATE_TIME = 3
    DATETIME = DATE_TIME  # Python spelling alias, not an additional BSL member.

    def __str__(self) -> str:
        return {BSLDateFractions.DATE: "Дата", BSLDateFractions.TIME: "Время",
                BSLDateFractions.DATE_TIME: "Дата и время"}[self]


@dataclass(frozen=True, eq=False)
class BSLAllowedSigns(BSLObject):
    def __str__(self) -> str:
        return "ПеречислениеДопустимыйЗнак"

    def get_member(self, name: str) -> object:
        members = {"any": BSLAllowedSign.ANY, "любой": BSLAllowedSign.ANY,
                   "nonnegative": BSLAllowedSign.NONNEGATIVE,
                   "неотрицательный": BSLAllowedSign.NONNEGATIVE}
        member = members.get(name.casefold())
        return super().get_member(name) if member is None else member


@dataclass(frozen=True, eq=False)
class BSLAllowedLengths(BSLObject):
    def __str__(self) -> str:
        return "ПеречислениеДопустимаяДлина"

    def get_member(self, name: str) -> object:
        members = {"fixed": BSLAllowedLength.FIXED,
                   "фиксированная": BSLAllowedLength.FIXED,
                   "variable": BSLAllowedLength.VARIABLE,
                   "переменная": BSLAllowedLength.VARIABLE}
        member = members.get(name.casefold())
        return super().get_member(name) if member is None else member


@dataclass(frozen=True, eq=False)
class BSLDateFractionsNamespace(BSLObject):
    def __str__(self) -> str:
        return "ПеречислениеЧастиДаты"

    def get_member(self, name: str) -> object:
        members = {"date": BSLDateFractions.DATE, "дата": BSLDateFractions.DATE,
                   "time": BSLDateFractions.TIME, "время": BSLDateFractions.TIME,
                   "datetime": BSLDateFractions.DATE_TIME,
                   "датавремя": BSLDateFractions.DATE_TIME}
        member = members.get(name.casefold())
        return super().get_member(name) if member is None else member


ALLOWED_SIGNS = BSLAllowedSigns()
ALLOWED_LENGTHS = BSLAllowedLengths()
DATE_FRACTIONS = BSLDateFractionsNamespace()


# Resource budgets protect later qualified adjustment as well as construction.
# They do not claim anything about the maximum values accepted by native 1C.
_MAX_NUMBER_DIGITS = 4096
_MAX_LENGTH_UNITS = 1_000_000
_MAX_ARGUMENT_DIGITS = 4096


def _count(value: object, *, name: str, limit: int,
           negative_to_zero: bool = True) -> Decimal:
    # Tuple membership compares classes with == and can invoke an untrusted
    # host metaclass. The BSL boundary admits only these exact identities.
    if not any(type(value) is kind for kind in (Decimal, int, str)):
        raise TypeError(f"{name}: поддерживаются числовые и строковые аргументы")
    if ((type(value) is str and len(value) > _MAX_ARGUMENT_DIGITS)
            or (type(value) is int and value.bit_length() > 4 * _MAX_ARGUMENT_DIGITS)):
        raise ValueError(f"{name}: превышен предел ресурсов Yadinassi")
    try:
        value = number(value)
    except (ValueError, InvalidOperation):
        raise ValueError(f"{name}: ожидается конечное число") from None
    if len(value.as_tuple().digits) > _MAX_ARGUMENT_DIGITS:
        raise ValueError(f"{name}: превышен предел ресурсов Yadinassi")
    # Unlike int(value), this neither expands a huge positive exponent nor
    # rounds through the caller's Decimal precision/traps/flags.
    integral = value.to_integral_value(rounding=ROUND_DOWN)
    if value < 0:
        if value != integral or not negative_to_zero:
            raise ValueError(f"{name}: отрицательное значение пока не поддерживается в Yadinassi")
        return Decimal(0)
    if integral > limit:
        raise ValueError(f"{name}: превышен предел ресурсов Yadinassi ({limit})")
    # Only a proven bounded integer is materialized; properties are Numbers.
    return Decimal(int(integral))


@dataclass(frozen=True, eq=False, init=False)
class BSLNumberQualifiers(BSLObject):
    digits: Decimal
    fraction_digits: Decimal
    allowed_sign: BSLAllowedSign

    def __init__(self, digits: object = Decimal(0),
                 fraction_digits: object = Decimal(0),
                 allowed_sign: object = BSLAllowedSign.ANY):
        if type(allowed_sign) is not BSLAllowedSign:
            raise TypeError("КвалификаторыЧисла: ожидается значение ДопустимыйЗнак")
        digits = _count(digits, name="Разрядность", limit=_MAX_NUMBER_DIGITS)
        fraction_digits = _count(fraction_digits, name="РазрядностьДробнойЧасти",
                                 limit=_MAX_NUMBER_DIGITS, negative_to_zero=False)
        object.__setattr__(self, "digits", digits)
        object.__setattr__(self, "fraction_digits", min(digits, fraction_digits))
        object.__setattr__(self, "allowed_sign", allowed_sign)

    def __str__(self) -> str:
        return "КвалификаторыЧисла"

    def get_member(self, name: str) -> object:
        members = {"digits": self.digits, "разрядность": self.digits,
                   "fractiondigits": self.fraction_digits,
                   "разрядностьдробнойчасти": self.fraction_digits,
                   "allowedsign": self.allowed_sign,
                   "допустимыйзнак": self.allowed_sign}
        member = members.get(name.casefold())
        return super().get_member(name) if member is None else member


@dataclass(frozen=True, eq=False, init=False)
class _LengthQualifiers(BSLObject):
    length: Decimal
    allowed_length: BSLAllowedLength

    def __init__(self, length: object = Decimal(0),
                 allowed_length: object = BSLAllowedLength.VARIABLE):
        if type(allowed_length) is not BSLAllowedLength:
            raise TypeError("Квалификаторы длины: ожидается значение ДопустимаяДлина")
        length = _count(length, name="Длина", limit=_MAX_LENGTH_UNITS)
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "allowed_length",
                           allowed_length if length else BSLAllowedLength.VARIABLE)

    def get_member(self, name: str) -> object:
        members = {"length": self.length, "длина": self.length,
                   "allowedlength": self.allowed_length,
                   "допустимаядлина": self.allowed_length}
        member = members.get(name.casefold())
        return super().get_member(name) if member is None else member


@dataclass(frozen=True, eq=False, init=False)
class BSLStringQualifiers(_LengthQualifiers):
    def __str__(self) -> str:
        return "КвалификаторыСтроки"


@dataclass(frozen=True, eq=False, init=False)
class BSLBinaryDataQualifiers(_LengthQualifiers):
    """Standalone metadata only; this does not add BinaryData runtime values."""

    def __str__(self) -> str:
        return "КвалификаторыДвоичныхДанных"


@dataclass(frozen=True, eq=False, init=False)
class BSLDateQualifiers(BSLObject):
    date_fractions: BSLDateFractions

    def __init__(self, date_fractions: object = BSLDateFractions.DATE_TIME):
        if type(date_fractions) is not BSLDateFractions:
            raise TypeError("КвалификаторыДаты: ожидается значение ЧастиДаты")
        object.__setattr__(self, "date_fractions", date_fractions)

    def __str__(self) -> str:
        return "КвалификаторыДаты"

    def get_member(self, name: str) -> object:
        if name.casefold() in ("datefractions", "частидаты"):
            return self.date_fractions
        return super().get_member(name)


__all__ = ["BSLAllowedSign", "BSLAllowedLength", "BSLDateFractions",
           "BSLAllowedSigns", "BSLAllowedLengths", "BSLDateFractionsNamespace",
           "ALLOWED_SIGNS", "ALLOWED_LENGTHS", "DATE_FRACTIONS",
           "BSLNumberQualifiers", "BSLStringQualifiers", "BSLDateQualifiers",
           "BSLBinaryDataQualifiers"]
