"""Documented fixed-GMT Date conversions, with a deliberately bounded domain.

The platform documents GMT{+/-}h[h][:mm], hours 0..23 and minutes 0..59.
Fractional ticks are preserved, as observed in native run 39758795625.
Named/computer timezones and overflow behavior remain outside this bounded
subset; no choice among their possible behaviors is made implicitly.
"""

import re

from .dates import BSLDate, MAX_TICKS, TICKS_PER_SECOND, UnsupportedDateRange


_GMT_OFFSET = re.compile(r"GMT([+-])([0-9]{1,2})(?::([0-9]{2}))?\Z")
_MAX_OFFSET_LENGTH = len("GMT+23:59")


def _offset_seconds(zone: object) -> int:
    if zone is None:
        raise ValueError("Преобразование времени: часовой пояс компьютера пока не поддерживается; "
                         "укажите явное смещение GMT")
    if type(zone) is not str:
        raise TypeError("Преобразование времени: часовой пояс должен иметь тип Строка")
    # Check length before matching; reject rather than trim or case-fold names.
    # This is the documented fixed-offset grammar, not a native string limit.
    match = _GMT_OFFSET.fullmatch(zone) if len(zone) <= _MAX_OFFSET_LENGTH else None
    if match is None:
        raise ValueError("Преобразование времени: поддержано только явное смещение "
                         "GMT+ч[ч][:мм] или GMT-ч[ч][:мм]")
    sign, hours, minutes = match.groups()
    hours, minutes = int(hours), int(minutes or '0')
    if hours > 23 or minutes > 59:
        raise ValueError("Преобразование времени: часы GMT должны быть 0–23, минуты 0–59")
    seconds = (hours * 60 + minutes) * 60
    return -seconds if sign == '-' else seconds


def _convert(value: object, zone: object, *, to_local: bool) -> BSLDate:
    if type(value) is not BSLDate:
        raise TypeError("Преобразование времени: первый аргумент должен иметь тип Дата")
    value.require_known()
    offset = _offset_seconds(zone) * TICKS_PER_SECOND
    ticks = value.ticks + offset if to_local else value.ticks - offset
    if not 0 <= ticks <= MAX_TICKS:
        # Do not use shift_date's native-backed boundary-only witnesses: those
        # describe Date arithmetic, not these conversion methods.
        raise UnsupportedDateRange("Преобразование времени: результат вне поддержанного "
                                   "диапазона дат 0001–9999")
    return BSLDate(ticks)


def to_local_time(value: object, zone: object = None) -> BSLDate:
    return _convert(value, zone, to_local=True)


def to_universal_time(value: object, zone: object = None) -> BSLDate:
    return _convert(value, zone, to_local=False)


BUILTINS = (("МестноеВремя", to_local_time, "ToLocalTime"),
            ("УниверсальноеВремя", to_universal_time, "ToUniversalTime"))
