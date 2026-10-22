"""A bounded scalar TypeDescription, grounded in native checkpoint probes.

Supported types are Boolean, String, Date, Number and standalone Null. Binary
runtime values, arbitrary object types, mixed Null ordering and ambiguous union
fallbacks are intentionally excluded. Qualifiers and their internal value-stream
codec are separate concerns; this module does not manufacture codec evidence.

Explicit resource limits are Yadinassi budgets, not inferred native maxima.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

from .dates import BSLDate, TICKS_PER_SECOND, date
from .numbers import round_number
from .type_qualifiers import (
    BSLAllowedLength, BSLAllowedSign, BSLBinaryDataQualifiers,
    BSLDateFractions, BSLDateQualifiers, BSLNumberQualifiers,
    BSLStringQualifiers,
)
from .values import BSLArray, BSLObject, BSLType, HostFunction, NULL, number, to_string


_ORDER = (BSLType.BOOLEAN, BSLType.STRING, BSLType.DATE, BSLType.NUMBER,
          BSLType.NULL)
_NAMES = {name.casefold(): value_type
          for value_type, alias in ((BSLType.BOOLEAN, "Boolean"),
                                    (BSLType.STRING, "String"),
                                    (BSLType.DATE, "Date"),
                                    (BSLType.NUMBER, "Number"),
                                    (BSLType.NULL, "Null"),
                                    (BSLType.UNDEFINED, "Undefined"))
          for name in (value_type.value, alias)}
_QUALIFIERS = (("number_qualifiers", BSLNumberQualifiers),
               ("string_qualifiers", BSLStringQualifiers),
               ("date_qualifiers", BSLDateQualifiers),
               ("binary_data_qualifiers", BSLBinaryDataQualifiers))
_OMITTED = object()
_MAX_TYPE_ARGUMENT = 4096
_MAX_NUMBER_DIGITS = 4096
_MAX_STRING_UNITS = 1_000_000


def _unsupported(message):
    raise ValueError(f"ОписаниеТипов: {message} пока не поддерживается в Yadinassi")


def _type_set(value):
    if value is None or (type(value) is str and not value):
        return set()
    if type(value) is str:
        if len(value) > _MAX_TYPE_ARGUMENT:
            raise ValueError("ОписаниеТипов: превышен предел ресурсов Yadinassi (4096 символов)")
        kinds = []
        for token in value.split(","):
            kind = _NAMES.get(token.strip().casefold())
            if kind is None:
                raise ValueError(f"ОписаниеТипов: тип не поддерживается: {token.strip()}")
            kinds.append(kind)
    elif type(value) is BSLArray:
        if len(value.items) > _MAX_TYPE_ARGUMENT:
            raise ValueError("ОписаниеТипов: превышен предел ресурсов Yadinassi (4096 типов)")
        kinds = value.items
    else:
        raise TypeError("ОписаниеТипов: ожидается строка или Массив значений Тип")
    result = set()
    for kind in kinds:
        # Validate before hashing: host objects must never supply equality/hash.
        if type(kind) is not BSLType:
            raise TypeError("ОписаниеТипов: элементы массива должны иметь тип Тип")
        if kind is BSLType.UNDEFINED:
            continue  # Native Undefined and Undefined,Number have no U entry.
        if kind not in _ORDER:
            _unsupported(f"тип {kind}")
        result.add(kind)
    return result


def _canonical(kinds):
    if BSLType.NULL in kinds and len(kinds) > 1:
        _unsupported("сочетание Null с другими типами")
    return tuple(kind for kind in _ORDER if kind in kinds)


def _number_value(value):
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("ПривестиЗначение: ожидается конечное число")
        if len(value.as_tuple().digits) > _MAX_NUMBER_DIGITS:
            raise ValueError("ПривестиЗначение: превышен предел ресурсов Yadinassi (4096 разрядов)")
        return value
    if value is None:
        return Decimal(0)
    if type(value) is bool:
        return Decimal(int(value))
    if type(value) is str:
        if len(value) > _MAX_NUMBER_DIGITS:
            raise ValueError("ПривестиЗначение: превышен предел ресурсов Yadinassi (4096 символов числа)")
        # Invalid text is zero in the native checkpoint. Keep malformed text's
        # Decimal InvalidOperation flag out of the caller's ambient context.
        with localcontext():
            try:
                return number(value)
            except (InvalidOperation, ValueError):
                return Decimal(0)
    _unsupported("это преобразование в Число")


def _qualified_number(value, qualifiers):
    if qualifiers.allowed_sign is BSLAllowedSign.NONNEGATIVE and value < 0:
        return Decimal(0)
    digits = int(qualifiers.digits)
    if not digits:
        return value  # Unqualified Number preserves every stored digit.
    fraction = int(qualifiers.fraction_digits)
    maximum = Decimal((0, (9,) * digits, -fraction))
    # Comparisons and tuple construction are exact under arbitrary host contexts.
    if value.copy_abs() > maximum:
        return maximum.copy_negate() if value.is_signed() else maximum
    rounded = round_number(value, Decimal(fraction))
    if rounded.copy_abs() > maximum:
        return maximum.copy_negate() if rounded.is_signed() else maximum
    return rounded


def _qualified_string(value, qualifiers):
    if not any(type(value) is kind for kind in (str, bool, Decimal, BSLDate)) and value is not None:
        _unsupported("это преобразование в Строку")
    if type(value) is str and len(value) > _MAX_STRING_UNITS:
        raise ValueError("ПривестиЗначение: превышен предел ресурсов Yadinassi (1000000 символов)")
    text = to_string(value)
    length = int(qualifiers.length)
    if not length:
        return text
    # Native counts UTF-16 units. surrogatepass preserves a split high surrogate
    # instead of silently replacing it or counting an emoji as one unit.
    encoded = text.encode("utf-16-le", errors="surrogatepass")
    units = len(encoded) // 2
    text = encoded[:length * 2].decode("utf-16-le", errors="surrogatepass")
    if qualifiers.allowed_length is BSLAllowedLength.FIXED and units < length:
        text += " " * (length - units)
    return text


def _qualified_date(value, qualifiers):
    if type(value) is BSLDate:
        value.require_known()
    elif type(value) is str:
        # Only the existing documented compact-date grammar is supported. A
        # failed parse is not evidence for an unmeasured default fallback.
        value = date(value)
    elif type(value) is Decimal:
        _number_value(value)
        value = BSLDate(0)
    else:
        _unsupported("это преобразование в Дату")
    fraction = qualifiers.date_fractions
    if fraction is BSLDateFractions.DATE_TIME:
        return value
    day_ticks = 86400 * TICKS_PER_SECOND
    if fraction is BSLDateFractions.DATE:
        return BSLDate(value.ticks // day_ticks * day_ticks)
    return BSLDate(value.ticks % day_ticks // TICKS_PER_SECOND * TICKS_PER_SECOND)


def _boolean_value(value):
    if type(value) is bool:
        return value
    if type(value) is Decimal:
        return not _number_value(value).is_zero()
    if value is None:
        return False
    if type(value) is str and value == "True":
        return True
    _unsupported("это преобразование в Булево")


def _scalar_type(value):
    if value is None:
        return BSLType.UNDEFINED
    if value is NULL:
        return BSLType.NULL
    for python_type, kind in ((bool, BSLType.BOOLEAN), (str, BSLType.STRING),
                              (BSLDate, BSLType.DATE), (Decimal, BSLType.NUMBER)):
        if type(value) is python_type:
            return kind
    _unsupported("приведение нескалярного значения")


def _qualifier_key(description):
    n, s, d, b = (getattr(description, attr) for attr, _ in _QUALIFIERS)
    return (n.digits, n.fraction_digits, n.allowed_sign,
            s.length, s.allowed_length, d.date_fractions,
            b.length, b.allowed_length)


@dataclass(frozen=True, eq=False, init=False)
class BSLTypeDescription(BSLObject):
    """Immutable scalar schema with bilingual methods and qualifier properties."""

    types: tuple[BSLType, ...]
    number_qualifiers: BSLNumberQualifiers
    string_qualifiers: BSLStringQualifiers
    date_qualifiers: BSLDateQualifiers
    binary_data_qualifiers: BSLBinaryDataQualifiers

    def __init__(self, source=None, *args):
        if type(source) is BSLTypeDescription:
            if len(args) > 6:
                raise TypeError("ОписаниеТипов: ожидается не более 7 аргументов")
            added = _type_set(args[0]) if args else set()
            removed = _type_set(args[1]) if len(args) > 1 else set()
            if added & removed:
                _unsupported("одновременное добавление и удаление одного типа")
            types = _canonical((set(source.types) | added) - removed)
            qualifier_args = args[2:]
        else:
            if len(args) > 4:
                raise TypeError("ОписаниеТипов: ожидается не более 5 аргументов")
            types = _canonical(_type_set(source))
            qualifier_args = args
        object.__setattr__(self, "types", types)
        for index, (attribute, qualifier_type) in enumerate(_QUALIFIERS):
            supplied = qualifier_args[index] if index < len(qualifier_args) else None
            if supplied is None:
                supplied = (getattr(source, attribute) if type(source) is BSLTypeDescription
                            else qualifier_type())
            elif type(supplied) is not qualifier_type:
                raise TypeError(f"ОписаниеТипов: недопустимый квалификатор {attribute}")
            # The native supplement supplies BinaryDataQualifiers(8, Fixed)
            # on scalar types and exposes (0, Variable). BinaryData itself is
            # out of scope, so no supported descriptor retains this setting.
            if qualifier_type is BSLBinaryDataQualifiers:
                supplied = BSLBinaryDataQualifiers()
            elif qualifier_type is BSLNumberQualifiers:
                if BSLType.NUMBER not in types and (supplied.digits or supplied.fraction_digits
                                                    or supplied.allowed_sign is not BSLAllowedSign.ANY):
                    _unsupported("квалификаторы Числа при отсутствии этого типа")
            elif qualifier_type is BSLStringQualifiers:
                if BSLType.STRING not in types and (supplied.length
                                                    or supplied.allowed_length is not BSLAllowedLength.VARIABLE):
                    _unsupported("квалификаторы Строки при отсутствии этого типа")
            elif BSLType.DATE not in types and supplied.date_fractions is not BSLDateFractions.DATE_TIME:
                _unsupported("квалификаторы Даты при отсутствии этого типа")
            object.__setattr__(self, attribute, supplied)

    def __str__(self):
        return ", ".join(str(kind) for kind in self.types)

    def __eq__(self, other):
        if type(other) is not BSLTypeDescription:
            return NotImplemented
        return self.types == other.types and _qualifier_key(self) == _qualifier_key(other)

    def __hash__(self):
        return hash((self.types, _qualifier_key(self)))

    def get_types(self):
        result = BSLArray()
        result.items = list(self.types)
        return result

    def contains_type(self, kind):
        if type(kind) is not BSLType:
            raise TypeError("СодержитТип: ожидается значение Тип")
        return kind in self.types

    def adjust_value(self, value=_OMITTED):
        if value is _OMITTED:
            if len(self.types) != 1:
                return None
            target = self.types[0]
            if target is BSLType.STRING:
                # Native PR82 measured omitted fixed-length String separately
                # from explicit Undefined/empty: all use the qualified default.
                return _qualified_string("", self.string_qualifiers)
            if target is BSLType.NUMBER:
                return Decimal(0)
            if target is BSLType.DATE:
                return BSLDate(0)
            if target is BSLType.BOOLEAN:
                return False
            return NULL
        kind = _scalar_type(value)
        if not self.types:
            # Native empty description accepts the scalar input unchanged.
            if kind is BSLType.DATE:
                value.require_known()
            if kind is BSLType.NUMBER:
                _number_value(value)
            return value
        if kind in self.types:
            target = kind
        elif len(self.types) == 1:
            target = self.types[0]
        elif self.types == (BSLType.STRING, BSLType.NUMBER) and kind is BSLType.BOOLEAN:
            target = BSLType.STRING
        elif self.types == (BSLType.DATE, BSLType.NUMBER) and kind is BSLType.STRING:
            target = BSLType.DATE
        else:
            _unsupported("выбор типа для несовпадающего значения составного описания")
        if target is BSLType.NUMBER:
            return _qualified_number(_number_value(value), self.number_qualifiers)
        if target is BSLType.STRING:
            return _qualified_string(value, self.string_qualifiers)
        if target is BSLType.DATE:
            return _qualified_date(value, self.date_qualifiers)
        if target is BSLType.BOOLEAN:
            return _boolean_value(value)
        return NULL

    def get_member(self, name):
        members = {"numberqualifiers": self.number_qualifiers,
                   "квалификаторычисла": self.number_qualifiers,
                   "stringqualifiers": self.string_qualifiers,
                   "квалификаторыстроки": self.string_qualifiers,
                   "datequalifiers": self.date_qualifiers,
                   "квалификаторыдаты": self.date_qualifiers,
                   "binarydataqualifiers": self.binary_data_qualifiers,
                   "квалификаторыдвоичныхданных": self.binary_data_qualifiers}
        key = name.casefold()
        if key in members:
            return members[key]
        methods = {"types": self.get_types, "типы": self.get_types,
                   "containstype": self.contains_type, "содержиттип": self.contains_type,
                   "adjustvalue": self.adjust_value, "привестизначение": self.adjust_value}
        method = methods.get(key)
        return super().get_member(name) if method is None else HostFunction(name, method)


__all__ = ["BSLTypeDescription"]
