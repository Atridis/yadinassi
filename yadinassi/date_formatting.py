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
# Short month and weekday spellings await independent native acquisition.
_ALIASES = {'д': 'd', 'М': 'M', 'г': 'y', 'к': 'q', 'ч': 'H', 'Ч': 'H',
            'м': 'm', 'с': 's'}
_ALLOWED = frozenset(('d', 'dd', 'M', 'MM', 'MMMM', 'y', 'yy', 'yyyy',
                      'q', 'H', 'HH', 'm', 'mm', 's', 'ss'))
_LOCAL = {
    'D': 'dd.MM.yyyy', 'Д': 'dd.MM.yyyy',
    'DD': "d MMMM yyyy 'г.'", 'ДД': "d MMMM yyyy 'г.'",
    'T': 'HH:mm:ss', 'В': 'HH:mm:ss',
    'DT': 'dd.MM.yyyy HH:mm:ss', 'ДВ': 'dd.MM.yyyy HH:mm:ss',
    'DDT': "d MMMM yyyy 'г.' HH:mm:ss", 'ДДВ': "d MMMM yyyy 'г.' HH:mm:ss",
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
                  'H': parts.hour, 'm': parts.minute, 's': parts.second,
                  'q': (parts.month - 1) // 3 + 1}
    output = []
    size = 0
    for kind, token in tokens:
        if not kind:
            text = token
        elif token == 'MMMM':
            text = (_MONTHS_GENITIVE if day_present else _MONTHS)[parts.month - 1]
        elif token == 'yyyy':
            text = str(parts.year).zfill(4)
        else:
            text = str(components[token[0]]).zfill(len(token))
        size += _units(text)
        if size > MAX_TEXT:
            raise ValueError('Формат: превышен предел текста Yadinassi')
        output.append(text)
    return ''.join(output)
