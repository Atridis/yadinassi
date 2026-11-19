"""Bounded PeriodPresentation for measured Russian and English workflows.

The renderer uses calendar arithmetic, not host locale. Unmeasured locales,
partial tick boundaries and format options fail explicitly.
"""
from calendar import monthrange
from .dates import BSLDate, TICKS_PER_SECOND, _parts

_RU_MONTHS = ('', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь')
_RU_GENITIVE = ('', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')
_EN_MONTHS = ('', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
_EN_WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')


def _unsupported():
    raise ValueError('ПредставлениеПериода: формат вне поддержанного подмножества Yadinassi')


def _spec(value):
    if type(value) is not str:
        raise TypeError('ПредставлениеПериода: ожидается строка формата')
    if len(value) > 4096 or len(value) + sum(ord(c) > 0xffff for c in value) > 4096:
        raise ValueError('ПредставлениеПериода: превышен предел формата Yadinassi')
    locale, financial = 'ru', False
    seen = set()
    for part in value.split(';'):
        if not part.strip(): continue
        if part.count('=') != 1: _unsupported()
        key, item = (s.strip() for s in part.split('=', 1))
        key = key.upper()
        if key in ('L', 'Л'):
            if 'locale' in seen: _unsupported()
            seen.add('locale')
            if item.lower() in ('ru', 'ru_ru'): locale = 'ru'
            elif item.lower() in ('en', 'en_us'): locale = 'en'
            else: _unsupported()
        elif key in ('ФП', 'FP'):
            if 'financial' in seen: _unsupported()
            seen.add('financial')
            if item.casefold() in ('истина', 'true'): financial = True
            elif item.casefold() in ('ложь', 'false'): financial = False
            else: _unsupported()
        else:
            # !todo More native locale/options and duplicate precedence.
            _unsupported()
    return locale, financial


def _full_day_start(value):
    return (value.hour, value.minute, value.second) == (0, 0, 0)


def _full_day_end(value):
    return (value.hour, value.minute, value.second) == (23, 59, 59)


def _month_start(value): return value.day == 1 and _full_day_start(value)
def _month_end(value): return value.day == monthrange(value.year, value.month)[1] and _full_day_end(value)


def _day(value, locale):
    if locale == 'ru': return f'{value.day} {_RU_GENITIVE[value.month]} {value.year} г.'
    return f'{_EN_WEEKDAYS[value.weekday()]}, {_EN_MONTHS[value.month]} {value.day}, {value.year}'


def _month(value, locale):
    return f'{_RU_MONTHS[value.month]} {value.year} г.' if locale == 'ru' else f'{_EN_MONTHS[value.month]} {value.year}'


def _date(value, locale, with_time=False):
    if locale != 'ru':
        # !todo Native English partial range and time representations.
        _unsupported()
    base = f'{value.day:02}.{value.month:02}.{value.year:04}'
    return base + (f' {value.hour:02}:{value.minute:02}:{value.second:02}' if with_time else '')


def period_presentation(start, end, specification=''):
    if type(start) is not BSLDate or type(end) is not BSLDate:
        raise TypeError('ПредставлениеПериода: ожидаются две даты')
    start.require_known(); end.require_known()
    if start.ticks % TICKS_PER_SECOND or end.ticks % TICKS_PER_SECOND:
        # !todo Native fractional-second behavior.
        _unsupported()
    locale, financial = _spec(specification)
    if start.ticks > end.ticks:
        raise ValueError('ПредставлениеПериода: начало позже окончания')
    if start.ticks == 0 and end.ticks == 0:
        return ''
    if end.ticks == 0:
        # !todo One-sided open end; only empty start was observed.
        _unsupported()
    b = _parts(end)
    if start.ticks == 0:
        if financial or locale != 'ru' or not _full_day_end(b): _unsupported()
        return '... - ' + _day(b, locale)
    a = _parts(start)
    whole_days = _full_day_start(a) and _full_day_end(b)
    if financial:
        # !todo Other financial spans have no native witness.
        months = (b.year - a.year) * 12 + b.month - a.month + 1
        if not (whole_days and _month_start(a) and _month_end(b)
                and a.year == b.year and a.month == 1 and months in (6, 9)):
            _unsupported()
    if whole_days and a.date() == b.date():
        return _day(a, locale)
    if whole_days and _month_start(a) and _month_end(b):
        months = (b.year - a.year) * 12 + b.month - a.month + 1
        if a.year == b.year and a.month == 1 and months == 12:
            return f'{a.year} г.' if locale == 'ru' else f'{a.year} year'
        if financial and a.year == b.year and a.month == 1 and months == 6:
            return f'1 полугодие {a.year} г.' if locale == 'ru' else f'1-st half year of {a.year}'
        if financial and a.year == b.year and a.month == 1 and months == 9:
            if locale != 'ru': _unsupported()  # !todo English nine-month format.
            return f'9 месяцев {a.year} г.'
        if a.year == b.year and months == 3 and a.month in (1, 4, 7, 10):
            q = (a.month - 1) // 3 + 1
            return f'{q} квартал {a.year} г.' if locale == 'ru' else f'{q} quarter of {a.year}'
        if months == 1: return _month(a, locale)
        return _month(a, locale) + ' - ' + _month(b, locale)
    # Native observed whole-day partial ranges and non-whole-day time ranges.
    if locale != 'ru': _unsupported()
    return _date(a, locale, not whole_days) + ' - ' + _date(b, locale, not whole_days)


BUILTINS = (("ПредставлениеПериода", period_presentation, "PeriodPresentation"),)
