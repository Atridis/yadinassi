"""Deterministic Russian date presentation, independent of host locale.

Only calendar components supplied by dates._parts are rendered. Parameter
selection and the empty-date policy stay in formatting.py. Textual names and
local formats use an explicit standalone Russian profile, not OS settings.
"""

MAX_TEXT = 4096
_MONTHS = ('Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
           'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь')
_MONTHS_GENITIVE = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
                    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')
# Exact Russian spellings measured on native 8.3.27.1508, names52/tokens56.
_MONTHS_SHORT = ('янв.', 'февр.', 'март', 'апр.', 'май', 'июнь',
                 'июль', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.')
_MONTHS_SHORT_GENITIVE = ('янв.', 'февр.', 'марта', 'апр.', 'мая', 'июня',
                         'июля', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.')
_WEEKDAYS = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')
_WEEKDAYS_SHORT = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')
_ALIASES = {'д': 'd', 'М': 'M', 'г': 'y', 'к': 'q', 'ч': 'h', 'Ч': 'H', 'в': 't',
            'м': 'm', 'с': 's'}
_ALLOWED = frozenset(('d', 'dd', 'ddd', 'dddd', 'M', 'MM', 'MMM', 'MMMM', 'y', 'yy', 'yyyy',
                      'q', 'h', 'hh', 'H', 'HH', 'tt', 'm', 'mm', 's', 'ss'))
_LOCAL = {
    'D': 'dd.MM.yyyy', 'Д': 'dd.MM.yyyy',
    'DD': "d MMMM yyyy\u00a0'г.'", 'ДД': "d MMMM yyyy\u00a0'г.'",
    'T': 'HH:mm:ss', 'В': 'HH:mm:ss',
    'DT': 'dd.MM.yyyy HH:mm:ss', 'ДВ': 'dd.MM.yyyy HH:mm:ss',
    'DDT': "d MMMM yyyy\u00a0'г.' HH:mm:ss", 'ДДВ': "d MMMM yyyy\u00a0'г.' HH:mm:ss",
}


def _unsupported():
    raise ValueError('Формат: формат вне поддержанного подмножества Yadinassi')


def _units(text):
    return len(text) + sum(ord(c) > 0xffff for c in text)


def date_tokens(mask):
    """Scan documented case-sensitive tokens and single-quoted literals."""
    if type(mask) is not str:
        raise TypeError('Формат: ожидается строка формата даты')
    if _units(mask) > MAX_TEXT:
        raise ValueError('Формат: превышен предел текста Yadinassi')
    tokens = []
    i = 0
    while i < len(mask):
        if mask[i] == "'":
            end = mask.find("'", i + 1)
            if end < 0:
                _unsupported()
            tokens.append((False, mask[i + 1:end]))
            i = end + 1
        elif mask[i].isalpha():
            end = i + 1
            while end < len(mask) and mask[end] == mask[i]:
                end += 1
            token = _ALIASES.get(mask[i], mask[i]) * (end - i)
            if token not in _ALLOWED:
                _unsupported()
            tokens.append((True, token))
            i = end
        else:
            tokens.append((False, mask[i]))
            i += 1
    return tuple(tokens)


def local_date_tokens(name):
    """Finite locale formats; their order is meaningful (DT, never TD)."""
    if type(name) is not str or name not in _LOCAL:
        _unsupported()
    return date_tokens(_LOCAL[name])


def render_date_tokens(parts, tokens):
    # The official compound example uses genitive while standalone MMMM is
    # witnessed as nominative. Literal letters never affect this selection.
    day_present = any(kind and token in ('d', 'dd') for kind, token in tokens)
    components = {'d': parts.day, 'M': parts.month, 'y': parts.year % 100,
                  'h': parts.hour % 12 or 12, 'H': parts.hour, 'm': parts.minute, 's': parts.second,
                  'q': (parts.month - 1) // 3 + 1}
    output = []
    size = 0
    for kind, token in tokens:
        if not kind:
            text = token
        elif token == 'MMMM':
            text = (_MONTHS_GENITIVE if day_present else _MONTHS)[parts.month - 1]
        elif token == 'MMM':
            text = (_MONTHS_SHORT_GENITIVE if day_present else _MONTHS_SHORT)[parts.month - 1]
        elif token in ('ddd', 'dddd'):
            text = (_WEEKDAYS_SHORT if token == 'ddd' else _WEEKDAYS)[parts.weekday()]
        elif token == 'tt':
            text = 'AM' if parts.hour < 12 else 'PM'
        elif token == 'yyyy':
            text = str(parts.year).zfill(4)
        else:
            text = str(components[token[0]]).zfill(len(token))
        size += _units(text)
        if size > MAX_TEXT:
            raise ValueError('Формат: превышен предел текста Yadinassi')
        output.append(text)
    return ''.join(output)
