"""Host wall clocks, with an explicitly bounded standalone precision policy.

The documented contracts distinguish host-local Date, UTC Date and integer
milliseconds since 0001-01-01 UTC. Both Date functions deliberately return whole
seconds here; this is not a claim about native clock resolution. Date arithmetic
still retains its existing 100-microsecond ticks. Milliseconds are floored from
one integer nanosecond sample, without floating-point or Decimal arithmetic.
These are wall clocks: successive calls need not increase or share a sample.
"""

from datetime import date
from decimal import Decimal
import time

from .dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange, _from_parts


_NS_PER_SECOND = 1_000_000_000
_NS_PER_MILLISECOND = 1_000_000
_UNIX_EPOCH_SECONDS = (date(1970, 1, 1).toordinal() - 1) * 86400
_MAX_SECONDS = MAX_TICKS // TICKS_PER_SECOND


def _read_time_ns():
    # A private test seam, not an alternate public clock or timezone setting.
    try:
        value = time.time_ns()
    except (OSError, OverflowError, ValueError):
        raise ValueError("Текущее время: не удалось прочитать системные часы") from None
    if type(value) is not int:
        raise TypeError("Текущее время: системные часы должны возвращать целые наносекунды")
    return value


def current_date() -> BSLDate:
    seconds = _read_time_ns() // _NS_PER_SECOND
    try:
        # localtime applies the process host's timezone and DST for this exact
        # sample. Do not use today's UTC offset or cache a timezone snapshot.
        return _from_parts(time.localtime(seconds)[:6])
    except (OSError, OverflowError, ValueError):
        raise UnsupportedDateRange(
            "ТекущаяДата: системную дату нельзя представить в поддержанном диапазоне") from None


def current_universal_date() -> BSLDate:
    seconds = _read_time_ns() // _NS_PER_SECOND + _UNIX_EPOCH_SECONDS
    if not 0 <= seconds <= _MAX_SECONDS:
        raise UnsupportedDateRange("ТекущаяУниверсальнаяДата: дата вне поддержанного диапазона")
    # Integer epoch arithmetic avoids platform C gmtime()/timestamp limits.
    return BSLDate(seconds * TICKS_PER_SECOND)


def current_universal_date_in_milliseconds() -> Decimal:
    milliseconds = (_read_time_ns() // _NS_PER_MILLISECOND
                    + _UNIX_EPOCH_SECONDS * 1000)
    # The numeric clock includes the complete last second of year 9999. It is
    # independent of the second-resolution Date result, not its serialization.
    if not 0 <= milliseconds < (_MAX_SECONDS + 1) * 1000:
        raise UnsupportedDateRange(
            "ТекущаяУниверсальнаяДатаВМиллисекундах: дата вне поддержанного диапазона")
    return Decimal(milliseconds)


BUILTINS = (("ТекущаяДата", current_date, "CurrentDate"),
            ("ТекущаяУниверсальнаяДата", current_universal_date, "CurrentUniversalDate"),
            ("ТекущаяУниверсальнаяДатаВМиллисекундах",
             current_universal_date_in_milliseconds, "CurrentUniversalDateInMilliseconds"))
