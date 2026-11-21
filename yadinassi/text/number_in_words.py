"""Bounded Russian/English NumberInWords; finite native witnesses are documented.

The implementation does not consult host locale or Decimal context. It deliberately
rejects unmeasured grammars and excessive numeric/text inputs instead of guessing.
"""
from decimal import Decimal
import sys

_MAX_UNITS = 4096
_MAX_DIGITS = 9

_RU_ONES = ('', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять')
_RU_FEM = ('', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять')
_RU_TEENS = ('десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать', 'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать')
_RU_TENS = ('', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто')
_RU_HUNDREDS = ('', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот', 'шестьсот', 'семьсот', 'восемьсот', 'девятьсот')
_EN_ONES = ('', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine')
_EN_TEENS = ('ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen')
_EN_TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety')


def _unsupported():
    raise ValueError('ЧислоПрописью: формат вне поддержанного подмножества Yadinassi')


def _bounded(text):
    if type(text) is not str:
        raise TypeError('ЧислоПрописью: ожидается строка')
    if len(text) > _MAX_UNITS or len(text) + sum(ord(c) > 0xffff for c in text) > _MAX_UNITS:
        raise ValueError('ЧислоПрописью: превышен предел текста Yadinassi')
    return text


def _spec(value):
    if type(value) is Decimal and value.is_finite():
        # Native observed numeric second argument; broader finite values are a
        # bounded local generalization, not additional native evidence.
        value = ''
    value = _bounded(value)
    locale, fraction_words = 'ru', False
    seen = set()
    for part in value.split(';'):
        if not part.strip():
            continue
        if part.count('=') != 1:
            _unsupported()
        key, item = (v.strip() for v in part.split('=', 1))
        key = key.upper()
        if key in ('L', 'Л'):
            if 'locale' in seen: _unsupported()
            seen.add('locale')
            item = item.lower()
            if item in ('ru', 'ru_ru'): locale = 'ru'
            elif item in ('en', 'en_us'): locale = 'en'
            else: _unsupported()
        elif key == 'ДП':
            if 'fraction' in seen: _unsupported()
            seen.add('fraction')
            if item.casefold() not in ('истина', 'ложь'):
                _unsupported()
            fraction_words = item.casefold() == 'истина'
        else:
            # !todo Native format-language aliases/other flags need acquisition.
            _unsupported()
    return locale, fraction_words


def _subject(value, locale):
    value = _bounded(value)
    if not value:
        return (('', '', ''), 'м', ('', '', ''), 'ж', 2) if locale == 'ru' else (('', ''), ('', ''), 2)
    parts = [s.strip() for s in value.split(',')]
    if any(len(s) > 128 for s in parts):
        _unsupported()
    if locale == 'ru':
        if len(parts) not in (4, 9) or parts[3].casefold() not in ('м', 'ж'):
            _unsupported()
        if len(parts) == 4:
            parts += ['', '', '', 'ж', '2']
        if parts[7].casefold() not in ('м', 'ж') or parts[8] != '2':
            # !todo Other scales and grammatical genders need native evidence.
            _unsupported()
        return tuple(parts[:3]), parts[3].casefold(), tuple(parts[4:7]), parts[7].casefold(), 2
    if len(parts) != 5 or parts[4] != '2':
        _unsupported()
    return tuple(parts[:2]), tuple(parts[2:4]), 2


def _ru_form(number, forms):
    last = number % 100
    if 11 <= last <= 14: return forms[2]
    last %= 10
    return forms[0] if last == 1 else forms[1] if 2 <= last <= 4 else forms[2]


def _ru_group(number, feminine=False):
    words = []
    if number >= 100: words.append(_RU_HUNDREDS[number // 100])
    number %= 100
    if 10 <= number < 20: words.append(_RU_TEENS[number - 10])
    else:
        if number >= 20: words.append(_RU_TENS[number // 10])
        if number % 10: words.append((_RU_FEM if feminine else _RU_ONES)[number % 10])
    return ' '.join(words)


def _en_group(number):
    words = []
    if number >= 100: words.extend((_EN_ONES[number // 100], 'hundred'))
    number %= 100
    if 10 <= number < 20: words.append(_EN_TEENS[number - 10])
    else:
        if number >= 20: words.append(_EN_TENS[number // 10])
        if number % 10: words.append(_EN_ONES[number % 10])
    return ' '.join(words)


def _words(number, locale, feminine=False):
    if number == 0: return 'ноль' if locale == 'ru' else 'zero'
    groups = []
    for magnitude, scale in ((1000000, 'million'), (1000, 'thousand'), (1, '')):
        group, number = divmod(number, magnitude)
        if not group: continue
        if locale == 'ru':
            name = _ru_group(group, scale == 'thousand' or (not scale and feminine))
            if scale == 'million': name += ' ' + _ru_form(group, ('миллион', 'миллиона', 'миллионов'))
            elif scale == 'thousand': name += ' ' + _ru_form(group, ('тысяча', 'тысячи', 'тысяч'))
        else:
            name = _en_group(group)
            if scale: name += ' ' + scale
        groups.append(name)
    return ' '.join(groups)


def _parts(value):
    if type(value) is not Decimal or not value.is_finite():
        raise TypeError('ЧислоПрописью: ожидается конечное число')
    # Check the coefficient allocation before as_tuple can expand it.
    if (sys.implementation.name != 'cpython' or Decimal.__sizeof__ is object.__sizeof__
            or Decimal.__sizeof__(value) > 512):
        _unsupported()
    sign, digits, exponent = value.as_tuple()
    if len(digits) > _MAX_DIGITS + 2 or exponent < -2 or exponent > _MAX_DIGITS:
        # !todo Rounding and more than two fractional positions need witnesses.
        _unsupported()
    text = ''.join(str(d) for d in digits)
    point = len(text) + exponent
    if point > _MAX_DIGITS:
        _unsupported()
    if point <= 0:
        integer, fraction = '0', '0' * -point + text
    else:
        integer, fraction = (text[:point] + '0' * max(0, point - len(text)), text[point:])
    integer = integer.lstrip('0') or '0'
    if len(integer) > _MAX_DIGITS:
        _unsupported()
    fraction = (fraction + '00')[:2]
    return bool(sign and any(c != '0' for c in integer + fraction)), int(integer), int(fraction)


def number_in_words(value, specification='', subject=''):
    locale, fraction_words = _spec(specification)
    subject = _subject(subject, locale)
    negative, integer, fraction = _parts(value)
    if locale == 'ru':
        whole_forms, whole_gender, fraction_forms, fraction_gender, _ = subject
        noun = _ru_form(integer, whole_forms)
        fractional_noun = _ru_form(fraction, fraction_forms)
        words = _words(integer, locale, whole_gender == 'ж')
        minor = _words(fraction, locale, fraction_gender == 'ж') if fraction_words else f'{fraction:02d}'
    else:
        whole_forms, fraction_forms, _ = subject
        if fraction_words:
            # !todo English spelled fractions require a separate native witness.
            _unsupported()
        noun = whole_forms[0] if integer == 1 else whole_forms[1]
        fractional_noun = fraction_forms[0] if fraction == 1 else fraction_forms[1]
        words = _words(integer, locale)
        minor = f'{fraction:02d}'
    words = words[:1].upper() + words[1:]
    if negative: words = '-' + words
    # Observed zero/units without subjects preserve two spaces before minor;
    # exact scale words suppress the otherwise empty whole-unit slot.
    separator = ' ' if not noun and integer >= 1000 and integer % 1000 == 0 else ' ' + noun + ' '
    result = words + separator + minor + ' ' + fractional_noun
    return _bounded(result)


BUILTINS = (("ЧислоПрописью", number_in_words, "NumberInWords"),)
