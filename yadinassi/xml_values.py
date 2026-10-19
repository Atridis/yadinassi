"""A bounded XML lexical conversion pair, not an XML document parser."""

from decimal import Decimal
import re

from . import timezones
from .dates import (
    BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange, _from_parts,
    codec_text,
)
from .values import BSLType, NULL


# Implementation budgets, not inferred limits of native Number or XML values.
_MAX_NUMBER_DIGITS = 4096
_MAX_NUMBER_TEXT = 2 * _MAX_NUMBER_DIGITS + 16
_NUMBER = re.compile(
    r'(?P<mantissa>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))'
    r'(?P<suffix>[eE][+-]?[0-9]+|,[0-9]+)?'
)
_MAX_DATE_TEXT = 4096
_UNIX_EPOCH_SECONDS = 62135596800
_MAX_DATE_SECONDS = MAX_TICKS // TICKS_PER_SECOND
_DATE = re.compile(
    r'(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})'
    r'(?:T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})'
    r'(?:\.(?P<fraction>[0-9]+))?'
    r'(?P<zone>Z|[+-][0-9]{2}:[0-9]{2})?)?'
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


def _date_value(text: str) -> BSLDate:
    """Canonical calendar forms only; no permissive host ISO parser.

    Native XML reads round to whole seconds, including exact halves. This is
    distinct from Date arithmetic's 100-microsecond precision and from the XML
    writer, which discards fractional ticks. Zoned input denotes an instant;
    unzoned input remains a naive calendar date.
    """
    if len(text) > _MAX_DATE_TEXT:
        raise ValueError("XMLЗначение: превышен предел ресурсов Yadinassi (4096 символов даты)")
    match = _DATE.fullmatch(text)
    if match is None:
        raise ValueError("XMLЗначение: неверное или неподдерживаемое XML-представление Дата")
    parts = tuple(int(match[name] or '0') for name in
                  ('year', 'month', 'day', 'hour', 'minute', 'second'))
    try:
        seconds = _from_parts(parts).ticks // TICKS_PER_SECOND
    except ValueError:
        # Invalid Gregorian dates, 24:00:00 and leap seconds are not coerced.
        raise ValueError("XMLЗначение: неверное XML-представление Дата") from None
    fraction = match['fraction']
    if fraction is not None and fraction[0] >= '5':
        # Only the first decimal digit matters: no float, Decimal context,
        # enormous integer conversion or intermediate tick rounding.
        seconds += 1
    if not 0 <= seconds <= _MAX_DATE_SECONDS:
        raise UnsupportedDateRange("XMLЗначение: округление за диапазон даты пока не поддерживается")
    zone = match['zone']
    if zone is None:
        return BSLDate(seconds * TICKS_PER_SECOND)
    offset = 0
    if zone != 'Z':
        hours, minutes = int(zone[1:3]), int(zone[4:6])
        # This is a bounded canonical grammar, not a claim about all forms 1C
        # accepts. Offsets beyond ±14:00 and malformed minutes are excluded.
        if hours > 14 or minutes > 59 or (hours == 14 and minutes):
            raise ValueError("XMLЗначение: неподдерживаемое смещение часового пояса")
        offset = (hours * 60 + minutes) * 60
        if zone[0] == '-':
            offset = -offset
    seconds -= offset
    if not 0 <= seconds <= _MAX_DATE_SECONDS:
        raise UnsupportedDateRange("XMLЗначение: UTC-дата вне поддержанного диапазона")
    try:
        return _from_parts(timezones.local_parts(seconds - _UNIX_EPOCH_SECONDS))
    except timezones.TimezoneConfigurationError:
        raise
    except (OSError, OverflowError, ValueError):
        raise UnsupportedDateRange(
            "XMLЗначение: местную дату нельзя представить в поддержанном диапазоне") from None


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
        # The native .1234, .5 and .9999 witnesses all discard the fraction.
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
    if value_type is BSLType.DATE:
        return _date_value(text)
    if value_type is BSLType.NULL or value_type is BSLType.UNDEFINED:
        # Only empty representations have native evidence. Do not silently
        # discard unobserved nonempty input, including whitespace or markup.
        if text:
            raise ValueError("XMLЗначение: непустое XML-представление Null/Неопределено пока не поддерживается в Yadinassi")
        return NULL if value_type is BSLType.NULL else None
    raise TypeError("XMLЗначение: пока поддерживаются только Строка, Булево, Число, Дата, Null и Неопределено")


BUILTINS = (("XMLСтрока", xml_string, "XMLString"),
            ("XMLЗначение", xml_value, "XMLValue"))
