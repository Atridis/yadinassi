"""A bounded XML lexical conversion pair, not an XML document parser."""

from decimal import Decimal
import re

from .dates import BSLDate, TICKS_PER_SECOND, UnsupportedDateRange, codec_text
from .values import BSLType, NULL


# Implementation budgets, not inferred limits of native Number or XML values.
_MAX_NUMBER_DIGITS = 4096
_MAX_NUMBER_TEXT = 2 * _MAX_NUMBER_DIGITS + 16
_NUMBER = re.compile(
    r'(?P<mantissa>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))'
    r'(?P<suffix>[eE][+-]?[0-9]+|,[0-9]+)?'
)


def _bounded_number(value: Decimal, operation: str) -> Decimal:
    """Normalize exactly and guard fixed-point expansion before allocating it."""
    if not value.is_finite():
        raise ValueError(f"{operation}: ожидается конечное число")
    if value.is_zero():
        return Decimal(0)
    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
        exponent += 1
    digits = digits[:end]
    if max(len(digits) + max(exponent, 0), -exponent) > _MAX_NUMBER_DIGITS:
        raise ValueError(f"{operation}: превышен предел ресурсов Yadinassi (4096 десятичных разрядов)")
    # Tuple construction is exact even under a hostile ambient Decimal context.
    return Decimal((sign, digits, exponent))


def _number_value(text: str) -> Decimal:
    if len(text) > _MAX_NUMBER_TEXT:
        raise ValueError("XMLЗначение: превышен предел ресурсов Yadinassi")
    # Native observations include space, tab and LF; the bounded XML whitespace
    # set also includes CR. Never strip arbitrary Unicode whitespace.
    match = _NUMBER.fullmatch(text.strip(' \t\r\n'))
    if match is None:
        raise ValueError("XMLЗначение: неверное или неподдерживаемое XML-представление Число")
    mantissa, suffix = match.group('mantissa', 'suffix')
    if suffix is not None and suffix.startswith(',') and '.' in mantissa:
        raise ValueError("XMLЗначение: неверное или неподдерживаемое XML-представление Число")
    # Native 1e3, 1E-3 and 1,5 all read as 1. Limit this prefix behavior to
    # complete exponent-shaped or decimal-comma spellings, never Python's
    # exponent parser or Number()'s localized comma conversion.
    return _bounded_number(Decimal(mantissa), "XMLЗначение")


def xml_string(value: object) -> str:
    # Exact types: no host hooks, implicit String(), escaping or entity parsing.
    if type(value) is str:
        return value
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is Decimal:
        return format(_bounded_number(value, "XMLСтрока"), "f")
    if type(value) is BSLDate:
        value.require_known()
        # The single native +0.1234 observation does not distinguish truncation
        # from nearest-second rounding. Defer fractional writing as a whole.
        if value.ticks % TICKS_PER_SECOND:
            raise UnsupportedDateRange("XMLСтрока: дробные секунды даты пока не поддерживаются в Yadinassi")
        text = codec_text(value)
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}T{text[8:10]}:{text[10:12]}:{text[12:14]}"
    if value is None or value is NULL:
        return ""
    raise TypeError("XMLСтрока: пока поддерживаются только Строка, Булево, Число, Дата, Null и Неопределено")


def xml_value(value_type: object, text: object) -> object:
    if type(value_type) is not BSLType:
        raise TypeError("XMLЗначение: первый аргумент должен иметь тип Тип")
    if type(text) is not str:
        raise TypeError("XMLЗначение: второй аргумент должен иметь тип Строка")
    if value_type is BSLType.STRING:
        return text
    if value_type is BSLType.BOOLEAN:
        # Native TRUE is accepted but the whitespace probe is rejected.
        # Generalize only ASCII letter case; never trim or Unicode-casefold.
        token = text.translate(str.maketrans("TRUEFALS", "truefals"))
        if token in ("true", "1"):
            return True
        if token in ("false", "0"):
            return False
        raise ValueError("XMLЗначение: неверное XML-представление Булево")
    if value_type is BSLType.NUMBER:
        return _number_value(text)
    if value_type is BSLType.NULL or value_type is BSLType.UNDEFINED:
        # Only empty representations have native evidence. Do not silently
        # discard unobserved nonempty input, including whitespace or markup.
        if text:
            raise ValueError("XMLЗначение: непустое XML-представление Null/Неопределено пока не поддерживается в Yadinassi")
        return NULL if value_type is BSLType.NULL else None
    raise TypeError("XMLЗначение: пока поддерживаются только Строка, Булево, Число, Null и Неопределено")


BUILTINS = (("XMLСтрока", xml_string, "XMLString"),
            ("XMLЗначение", xml_value, "XMLValue"))
