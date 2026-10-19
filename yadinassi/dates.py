"""Bounded Date foundation grounded in the owner's Windows 8.3.27 checkpoint.

Dates retain 100-microsecond ticks. Construction, arithmetic and the lossy
internal stream are deliberately separate operations, not host datetime casts.
"""
from calendar import monthrange
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


def add_month(value: BSLDate, months: Decimal) -> BSLDate:
    value = _require_date(value)
    if type(months) is not Decimal or not months.is_finite():
        raise TypeError("ДобавитьМесяц: ожидается конечное число месяцев")
    if len(months.as_tuple().digits) > _MAX_DIGITS:
        raise ValueError("ДобавитьМесяц: превышен предел ресурсов Yadinassi (4096 разрядов)")
    # Bound before int(): an enormous positive exponent must not allocate a
    # huge integer. No shift this large can yield a supported Gregorian date.
    if months < -120000 or months > 120000:
        raise UnsupportedDateRange("ДобавитьМесяц: сдвиг за пределы диапазона пока не поддерживается")
    count = int(months)  # Truncation toward zero, independent of Decimal context.
    part = _parts(value)
    target = (part.year - 1) * 12 + part.month - 1 + count
    if not 0 <= target < 9999 * 12:
        # The native probes expose only scalar D records, not hidden tick state.
        # Both exact endpoint shifts serialize as the minimum date; do not
        # infer saturation, wraparound, or ordinary Date semantics from that.
        if ((value.ticks == 0 and months == -1)
                or (value.ticks == MAX_TICKS and months == 1)):
            return BSLDate(0, boundary=True)
        raise UnsupportedDateRange("ДобавитьМесяц: непроверенный выход за диапазон даты")
    year, month = divmod(target, 12)
    year, month = year + 1, month + 1
    day = min(part.day, monthrange(year, month)[1])
    # Even a zero-month shift discards fractional ticks in the native result.
    return _from_parts((year, month, day, part.hour, part.minute, part.second))


def _period_start(part, unit):
    if unit == "minute":
        return part.replace(second=0)
    if unit == "hour":
        return part.replace(minute=0, second=0)
    day = part.replace(hour=0, minute=0, second=0)
    if unit == "day":
        return day
    if unit == "week":
        return day - timedelta(days=part.weekday())
    if unit == "month":
        return day.replace(day=1)
    if unit == "quarter":
        return day.replace(month=(part.month - 1) // 3 * 3 + 1, day=1)
    if unit == "year":
        return day.replace(month=1, day=1)
    raise ValueError("Неизвестный календарный период")


def _date_from_datetime(part):
    return _from_parts((part.year, part.month, part.day,
                        part.hour, part.minute, part.second))


def begin_period(value: BSLDate, unit: str) -> BSLDate:
    return _date_from_datetime(_period_start(_parts(value), unit))


def end_period(value: BSLDate, unit: str) -> BSLDate:
    part = _parts(value)
    if unit == "minute":
        end = part.replace(second=59)
    elif unit == "hour":
        end = part.replace(minute=59, second=59)
    elif unit == "day":
        end = part.replace(hour=23, minute=59, second=59)
    elif unit == "week":
        remaining = 6 - part.weekday()
        if part.toordinal() + remaining > datetime.max.toordinal():
            if value.ticks == MAX_TICKS:
                return BSLDate(MAX_TICKS, boundary=True)
            raise UnsupportedDateRange("КонецНедели: непроверенный выход за диапазон даты")
        end = (part + timedelta(days=remaining)).replace(hour=23, minute=59, second=59)
    elif unit in ("month", "quarter", "year"):
        month = (part.month if unit == "month" else
                 (part.month - 1) // 3 * 3 + 3 if unit == "quarter" else 12)
        end = part.replace(month=month, day=monthrange(part.year, month)[1],
                           hour=23, minute=59, second=59)
    else:
        raise ValueError("Неизвестный календарный период")
    return _date_from_datetime(end)


def day_of_year(value: BSLDate) -> Decimal:
    part = _parts(value)
    return Decimal(part.toordinal() - datetime(part.year, 1, 1).toordinal() + 1)


def week_day(value: BSLDate) -> Decimal:
    return Decimal(_parts(value).weekday() + 1)


def week_of_year(value: BSLDate) -> Decimal:
    part = _parts(value)
    first = datetime(part.year, 1, 1)
    # First partial week is week 1, and each Monday begins the next week.
    # This is deliberately not ISO week numbering (2016-01-04 is week 2).
    return Decimal((part.toordinal() - first.toordinal() + first.weekday()) // 7 + 1)


def _period_function(unit, end=False):
    def apply(value):
        return end_period(value, unit) if end else begin_period(value, unit)
    return apply


def _extractor(part):
    def extract(value):
        return component(value, part)
    return extract


BUILTINS = (("Дата", date, "Date"),) + tuple(
    (ru, _extractor(part), en)
    for ru, en, part in (("Год", "Year", "year"), ("Месяц", "Month", "month"),
                         ("День", "Day", "day"), ("Час", "Hour", "hour"),
                         ("Минута", "Minute", "minute"), ("Секунда", "Second", "second")))


BUILTINS += (("ДобавитьМесяц", add_month, "AddMonth"),
             ("ДеньГода", day_of_year, "DayOfYear"),
             ("ДеньНедели", week_day, "WeekDay"),
             ("НеделяГода", week_of_year, "WeekOfYear"))
BUILTINS += tuple(
    (russian + suffix, _period_function(unit, end), english + name)
    for unit, suffix, name in (("minute", "Минуты", "Minute"),
                               ("hour", "Часа", "Hour"), ("day", "Дня", "Day"),
                               ("week", "Недели", "Week"), ("month", "Месяца", "Month"),
                               ("quarter", "Квартала", "Quarter"), ("year", "Года", "Year"))
    for russian, english, end in (("Начало", "BegOf", False), ("Конец", "EndOf", True)))
