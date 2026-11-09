"""Documented JSON date formats and bounded serializer settings.

The 8.3.27 developer guide spells JavaScript dates ``new Date(milliseconds)``;
these are parsed as data, never evaluated. ISO local/offset/UTC and Microsoft
Unix-millisecond forms use the existing YADINASSI_TIMEZONE policy. Serializer
ISO/LocalDate/False defaults follow the guide's ordinary examples.

Only whole-second dates are supported until native fractional conversion is
measured. Ambiguous/nonexistent local times cannot be assigned an instant.
Configured IANA zones use the pinned database; an unset setting delegates to
host calendar conversion without changing TZ. All ranges and lexical limits
below are local implementation bounds, not claimed native limits.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
import math
import os
import re
import time

from .dates import (BSLDate, TICKS_PER_SECOND, UnsupportedDateRange,
                    _from_parts, _parts)
from . import timezones
from .values import BSLObject


class BSLJSONDateFormat(Enum):
    ISO = ('ISO', 'ISO')
    JAVASCRIPT = ('JavaScript', 'JavaScript')
    MICROSOFT = ('Microsoft', 'Microsoft')

    def __str__(self):
        return self.value[0]


class BSLJSONDateWritingVariant(Enum):
    LOCAL_DATE = ('ЛокальнаяДата', 'LocalDate')
    LOCAL_DATE_WITH_OFFSET = ('ЛокальнаяДатаСоСмещением', 'LocalDateWithOffset')
    UNIVERSAL_DATE = ('УниверсальнаяДата', 'UniversalDate')

    def __str__(self):
        return self.value[0]


class _EnumNamespace(BSLObject):
    def __init__(self, enum):
        self._enum = enum

    def get_member(self, name):
        key = name.casefold()
        for member in self._enum:
            if key in (alias.casefold() for alias in member.value):
                return member
        return super().get_member(name)


JSON_DATE_FORMATS = _EnumNamespace(BSLJSONDateFormat)
JSON_DATE_WRITING_VARIANTS = _EnumNamespace(BSLJSONDateWritingVariant)


class BSLJSONSerializerSettings(BSLObject):
    def __init__(self):
        self.date_writing_variant = BSLJSONDateWritingVariant.LOCAL_DATE
        self.serialize_arrays_as_objects = False
        self.date_serialization_format = BSLJSONDateFormat.ISO

    def __str__(self):
        return 'НастройкиСериализацииJSON'

    @staticmethod
    def _property(name):
        return {
            'вариантзаписидаты': ('date_writing_variant', BSLJSONDateWritingVariant),
            'datewritingvariant': ('date_writing_variant', BSLJSONDateWritingVariant),
            'сериализовыватьмассивыкакобъекты': ('serialize_arrays_as_objects', bool),
            'serializearraysasobjects': ('serialize_arrays_as_objects', bool),
            'форматсериализациидат': ('date_serialization_format', BSLJSONDateFormat),
            'dateserializationformat': ('date_serialization_format', BSLJSONDateFormat),
        }.get(name.casefold())

    def get_member(self, name):
        member = self._property(name)
        if member is not None:
            return getattr(self, member[0])
        return super().get_member(name)

    def set_member(self, name, value):
        member = self._property(name)
        if member is None:
            return super().set_member(name, value)
        if type(value) is not member[1]:
            raise TypeError('НастройкиСериализацииJSON: недопустимый тип свойства')
        setattr(self, member[0], value)


_ISO = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})T'
                  r'([0-9]{2}):([0-9]{2}):([0-9]{2})'
                  r'(Z|[+-][0-9]{2}:[0-9]{2})?\Z')
_MILLISECONDS = re.compile(r'-?[0-9]{1,15}\Z')
_EPOCH = datetime(1970, 1, 1)
_UTC_EPOCH = _EPOCH.replace(tzinfo=timezone.utc)
_MIN_SECONDS = -62135596800
_MAX_SECONDS = 253402300799
_MAX_TEXT = 64


def _seconds(value):
    difference = value - _EPOCH
    return difference.days * 86400 + difference.seconds


def _range(seconds):
    if not _MIN_SECONDS <= seconds <= _MAX_SECONDS:
        raise UnsupportedDateRange('JSON: дата UTC вне поддержанного диапазона 0001–9999')
    return seconds


def _from_unix(seconds):
    _range(seconds)
    try:
        return _from_parts(timezones.local_parts(seconds))
    except timezones.TimezoneConfigurationError:
        raise
    except (OverflowError, OSError, ValueError) as error:
        raise UnsupportedDateRange('JSON: местная дата вне поддержанного диапазона '
                                   'или недоступна на этой платформе') from error


def _configured_zone(name):
    name = timezones._validate_zone_name(name)
    if name not in timezones._zone_names():
        raise timezones.TimezoneConfigurationError(
            f'{timezones.TIMEZONE_ENV}: неизвестный часовой пояс IANA {name}')
    return timezones._load_zone(name)


def _configured_candidates(part, zone):
    candidates = set()
    for fold in (0, 1):
        try:
            utc = part.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
            restored = utc.astimezone(zone).replace(tzinfo=None)
        except (OverflowError, ValueError) as error:
            raise UnsupportedDateRange('JSON: преобразование часового пояса '
                                       'выходит за диапазон 0001–9999') from error
        if restored == part:
            difference = utc - _UTC_EPOCH
            candidates.add(difference.days * 86400 + difference.seconds)
    return candidates


def _host_candidates(part):
    fields = (part.year, part.month, part.day, part.hour, part.minute, part.second)
    candidates = set()
    probes = set()
    for is_dst in (-1, 0, 1):
        try:
            value = time.mktime(fields + (0, 0, is_dst))
        except (OverflowError, OSError, ValueError):
            continue
        if not math.isfinite(value) or value != math.trunc(value):
            continue
        value = int(value)
        if _MIN_SECONDS <= value <= _MAX_SECONDS:
            candidates.add(value)
            # Nearby offsets also detect ordinary non-DST political folds.
            probes.update((value - 172800, value, value + 172800))
    if not candidates:
        raise UnsupportedDateRange('JSON: местная дата недоступна на этой платформе; '
                                   'задайте YADINASSI_TIMEZONE')
    for probe in probes:
        if not _MIN_SECONDS <= probe <= _MAX_SECONDS:
            continue
        try:
            local = datetime(*time.localtime(probe)[:6])
        except (OverflowError, OSError, ValueError):
            continue
        candidates.add(_seconds(part) - (_seconds(local) - probe))
    result = set()
    for candidate in candidates:
        if not _MIN_SECONDS <= candidate <= _MAX_SECONDS:
            continue
        try:
            restored = tuple(time.localtime(candidate)[:6])
        except (OverflowError, OSError, ValueError):
            continue
        if restored == fields:
            result.add(candidate)
    return result


def _local_instant(part):
    name = os.environ.get(timezones.TIMEZONE_ENV)
    candidates = (_host_candidates(part) if name is None else
                  _configured_candidates(part, _configured_zone(name)))
    if len(candidates) != 1:
        raise ValueError('JSON: неоднозначное или несуществующее местное время '
                         'пока не поддерживается')
    return _range(next(iter(candidates)))


def _format(value):
    if type(value) is not BSLJSONDateFormat:
        raise TypeError('JSON: ожидается ФорматДатыJSON')
    return value


def read_json_date(text, format):
    """Convert documented whole-second date text to a local-calendar BSL Date."""
    if type(text) is not str:
        raise TypeError('ПрочитатьДатуJSON: ожидается Строка')
    format = _format(format)
    if len(text) > _MAX_TEXT:
        raise ValueError('ПрочитатьДатуJSON: превышен предел длины даты Yadinassi')
    if format is BSLJSONDateFormat.ISO:
        match = _ISO.fullmatch(text)
        if match is None:
            raise ValueError('ПрочитатьДатуJSON: ожидается дата ISO с целыми секундами')
        part = datetime(*(int(item) for item in match.groups()[:6]))
        suffix = match.group(7)
        if suffix is None:
            return _from_parts((part.year, part.month, part.day,
                                part.hour, part.minute, part.second))
        offset = 0
        if suffix != 'Z':
            hours, minutes = int(suffix[1:3]), int(suffix[4:6])
            if hours > 23 or minutes > 59:
                raise ValueError('ПрочитатьДатуJSON: недопустимое смещение UTC')
            offset = (hours * 60 + minutes) * 60
            if suffix[0] == '-':
                offset = -offset
        return _from_unix(_seconds(part) - offset)
    if format is BSLJSONDateFormat.JAVASCRIPT:
        number = text[9:-1] if text.startswith('new Date(') and text.endswith(')') else ''
    else:
        # Escaping is optional JSON syntax, not JavaScript execution.
        unescaped = text.replace('\\/', '/')
        number = unescaped[6:-2] if unescaped.startswith('/Date(') and unescaped.endswith(')/') else ''
    if _MILLISECONDS.fullmatch(number) is None:
        raise ValueError('ПрочитатьДатуJSON: недопустимая запись даты JavaScript/Microsoft')
    milliseconds = int(number)
    seconds, fraction = divmod(milliseconds, 1000)
    if fraction:
        raise ValueError('ПрочитатьДатуJSON: дробные секунды пока не поддерживаются')
    return _from_unix(seconds)


def _iso(part):
    return (f'{part.year:04}-{part.month:02}-{part.day:02}T'
            f'{part.hour:02}:{part.minute:02}:{part.second:02}')


def write_json_date(date, format, variant=BSLJSONDateWritingVariant.LOCAL_DATE):
    """Return a date representation without JSON string quoting."""
    if type(date) is not BSLDate:
        raise TypeError('ЗаписатьДатуJSON: ожидается Дата')
    date.require_known()
    format = _format(format)
    if variant is None:
        variant = BSLJSONDateWritingVariant.LOCAL_DATE
    if type(variant) is not BSLJSONDateWritingVariant:
        raise TypeError('ЗаписатьДатуJSON: ожидается ВариантЗаписиДатыJSON')
    if date.ticks % TICKS_PER_SECOND:
        raise ValueError('ЗаписатьДатуJSON: дробные секунды пока не поддерживаются')
    if format is not BSLJSONDateFormat.ISO and variant is not BSLJSONDateWritingVariant.UNIVERSAL_DATE:
        raise ValueError('ЗаписатьДатуJSON: JavaScript и Microsoft требуют УниверсальнаяДата')
    part = _parts(date)
    if variant is BSLJSONDateWritingVariant.LOCAL_DATE:
        return _iso(part)
    seconds = _local_instant(part)
    if format is BSLJSONDateFormat.JAVASCRIPT:
        return f'new Date({seconds * 1000})'
    if format is BSLJSONDateFormat.MICROSOFT:
        return f'/Date({seconds * 1000})/'
    if variant is BSLJSONDateWritingVariant.UNIVERSAL_DATE:
        return _iso(_EPOCH + timedelta(seconds=seconds)) + 'Z'
    offset = _seconds(part) - seconds
    if abs(offset) >= 86400:
        raise ValueError('ЗаписатьДатуJSON: смещение UTC вне поддержанного диапазона')
    # The documented rule omits offset seconds, rather than rounding minutes.
    hours, minutes = divmod(abs(offset) // 60, 60)
    return f'{_iso(part)}{"-" if offset < 0 else "+"}{hours:02}:{minutes:02}'
