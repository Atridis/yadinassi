"""Bounded Date foundation grounded in the owner's Windows 8.3.27 checkpoint.

Dates retain 100-microsecond ticks. Construction, arithmetic and the lossy
internal stream are deliberately separate operations, not host datetime casts.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

TICKS_PER_SECOND = 10000
_EPOCH = datetime(1, 1, 1)
MAX_TICKS = ((datetime(9999, 12, 31, 23, 59, 59) - _EPOCH).days * 86400
             + 86399) * TICKS_PER_SECOND
_MAX_DIGITS = 4096


class UnsupportedDateRange(ValueError):
    """A native Date result is not established in this implementation envelope."""


@dataclass(frozen=True, slots=True, eq=False)
class BSLDate:
    ticks: int
    boundary: bool = False

    def __post_init__(self):
        if type(self.ticks) is not int or not 0 <= self.ticks <= MAX_TICKS:
            raise ValueError("Дата: значение вне поддержанного диапазона")
        if type(self.boundary) is not bool or (self.boundary and self.ticks not in (0, MAX_TICKS)):
            raise ValueError("Дата: недопустимое граничное состояние")

    def require_known(self):
        if self.boundary:
            raise UnsupportedDateRange(
                "Дата: после выхода за диапазон известно только скалярное "
                "внутреннее представление; дальнейшая операция пока не поддерживается")
        return self

    def __eq__(self, other):
        self.require_known()
        if type(other) is not BSLDate:
            return NotImplemented
        other.require_known()
        return self.ticks == other.ticks

    def __hash__(self):
        self.require_known()
        return hash(self.ticks)

    def __str__(self):
        value = _parts(self)
        return f"{value.day:02}.{value.month:02}.{value.year:04} {value.hour}:{value.minute:02}:{value.second:02}"


def _require_date(value):
    if type(value) is not BSLDate:
        raise TypeError("Ожидается дата")
    return value.require_known()


def _parts(value):
    value = _require_date(value)
    return _EPOCH + timedelta(seconds=value.ticks // TICKS_PER_SECOND)


def _from_parts(parts):
    value = datetime(*parts)
    delta = value - _EPOCH
    return BSLDate((delta.days * 86400 + delta.seconds) * TICKS_PER_SECOND)


def _canonical(text, lengths):
    if len(text) not in lengths or not text.isascii() or not text.isdigit():
        raise ValueError("Дата: ожидается каноническая запись даты")
    text = text.ljust(14, '0')
    return _from_parts((int(text[:4]), int(text[4:6]), int(text[6:8]),
                        int(text[8:10]), int(text[10:12]), int(text[12:14])))


def literal_date(text: str) -> BSLDate:
    if type(text) is not str:
        raise TypeError("Литерал даты должен быть строкой")
    if len(text) > _MAX_DIGITS:
        raise ValueError("Литерал даты: превышен предел ресурсов Yadinassi (4096 символов)")
    return _canonical(''.join(char for char in text if char in '0123456789'), (8, 12, 14))


def date(*args) -> BSLDate:
    if len(args) == 1 and type(args[0]) is str:
        # Locale-dependent formats and undocumented string lengths are excluded.
        return _canonical(args[0], (8, 14))
    if len(args) not in (3, 6):
        raise TypeError("Дата: ожидается строка или 3 либо 6 числовых компонентов")
    parts = []
    for index, value in enumerate(args):
        if type(value) is not Decimal or not value.is_finite():
            raise TypeError("Дата: компоненты должны быть конечными числами")
        if len(value.as_tuple().digits) > _MAX_DIGITS:
            raise ValueError("Дата: превышен предел ресурсов Yadinassi (4096 разрядов компонента)")
        low, high = ((1, 9999), (1, 12), (1, 31), (0, 23), (0, 59), (0, 60))[index]
        if value < low or (value >= high if index == 5 else value > high):
            raise ValueError("Дата: компонент вне диапазона")
        if index != 5 and value != value.to_integral_value():
            raise ValueError("Дата: дробные компоненты кроме секунды пока не поддерживаются")
        # The native Date(...,56.9) discards fractions; tick arithmetic does not.
        parts.append(int(value))
    return _from_parts(tuple(parts + [0] * (6 - len(parts))))


def _delta_ticks(value: Decimal) -> int:
    if type(value) is not Decimal or not value.is_finite():
        raise TypeError("Арифметика даты: ожидается конечное число секунд")
    if value.is_zero():
        return 0
    sign, digits, exponent = value.as_tuple()
    shift = exponent + 4
    if len(digits) > _MAX_DIGITS or len(digits) + max(shift, 0) > _MAX_DIGITS:
        raise ValueError("Арифметика даты: превышен предел ресурсов Yadinassi (4096 разрядов)")
    # Slice decimal digits before integer conversion. No context-dependent
    # Decimal arithmetic, huge negative powers or unbounded int strings.
    if shift >= 0:
        result = Decimal((0, digits, 0)).as_integer_ratio()[0] * 10 ** shift
    else:
        cut = len(digits) + shift
        kept = digits[:cut] if cut > 0 else (0,)
        result = Decimal((0, kept, 0)).as_integer_ratio()[0]
        first = digits[cut] if cut >= 0 else 0
        if first >= 5:
            result += 1
    return -result if sign else result


def shift_date(value: BSLDate, seconds: Decimal) -> BSLDate:
    value = _require_date(value)
    delta = _delta_ticks(seconds)
    ticks = value.ticks + delta
    if 0 <= ticks <= MAX_TICKS:
        return BSLDate(ticks)
    # Owner probes establish only the endpoint stream for whole-second range
    # crossings, not a saturated internal Date. Keep that uncertainty explicit.
    if (value.ticks % TICKS_PER_SECOND or delta % TICKS_PER_SECOND
            or seconds != seconds.to_integral_value()):
        raise UnsupportedDateRange("Дата: дробная арифметика у границы диапазона пока не поддерживается")
    if ticks < -TICKS_PER_SECOND or ticks > MAX_TICKS + TICKS_PER_SECOND:
        raise UnsupportedDateRange("Дата: выход более чем на одну секунду за границу пока не поддерживается")
    return BSLDate(0 if ticks < 0 else MAX_TICKS, boundary=True)


def date_difference(left: BSLDate, right: BSLDate) -> Decimal:
    difference = _require_date(left).ticks - _require_date(right).ticks
    return Decimal((int(difference < 0), Decimal(abs(difference)).as_tuple().digits, -4))


def component(value: BSLDate, name: str) -> Decimal:
    return Decimal(getattr(_parts(value), name))


def codec_text(value: BSLDate, *, nested=False) -> str:
    if type(value) is not BSLDate:
        raise TypeError("Ожидается дата")
    if nested:
        value.require_known()
    # Only scalar boundary records were observed. Fractional normal dates
    # intentionally lose subsecond ticks, exactly as the owner's stream does.
    part = _EPOCH + timedelta(seconds=value.ticks // TICKS_PER_SECOND)
    return f"{part.year:04}{part.month:02}{part.day:02}{part.hour:02}{part.minute:02}{part.second:02}"


def read_codec(text: str) -> BSLDate:
    return _canonical(text, (14,))


def _extractor(part):
    def extract(value):
        return component(value, part)
    return extract


BUILTINS = (("Дата", date, "Date"),) + tuple(
    (ru, _extractor(part), en)
    for ru, en, part in (("Год", "Year", "year"), ("Месяц", "Month", "month"),
                         ("День", "Day", "day"), ("Час", "Hour", "hour"),
                         ("Минута", "Minute", "minute"), ("Секунда", "Second", "second")))
