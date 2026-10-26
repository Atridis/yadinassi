"""String builtins, with positions measured in UTF-16 code units.

The public Python API still uses str. A temporary code-unit string keeps searches
aligned and lets slicing preserve individual surrogate halves without depending
on the host platform's wchar_t width. See features.md for compatibility limits.
"""

from decimal import Decimal, ROUND_DOWN
import re

from .collation import caseless_string_key
from .search_directions import BSLSearchDirection
from .values import BSLArray, BSLFixedArray, NULL, boolean, number, to_string


# Unicode White_Space, explicitly listed instead of Python's wider isspace()
# predicate (which also accepts the C0 separators U+001C through U+001F).
_WHITESPACE = (" \t\n\v\f\r\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004"
               "\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000")
_OMITTED = object()

# Complete nonidentity simple-case alternatives where full casing expands,
# from UnicodeData 15.1 fields 12/13 (also unchanged in Unicode 16.0).
# https://www.unicode.org/Public/15.1.0/ucd/UnicodeData.txt
# Other expansions have no simple mapping and preserve the original character.
_SIMPLE_UPPER_ALTERNATIVES = {
    chr(code): chr(code + 8)
    for start in (0x1f80, 0x1f90, 0x1fa0)
    for code in range(start, start + 8)
}
_SIMPLE_UPPER_ALTERNATIVES.update({"\u1fb3": "\u1fbc", "\u1fc3": "\u1fcc", "\u1ff3": "\u1ffc"})
_SIMPLE_LOWER_ALTERNATIVES = {"\u0130": "\u0069"}


def _units(value: object) -> str:
    text = to_string(value)
    if all(ord(character) <= 0xffff for character in text):
        return text
    data = text.encode("utf-16-le", errors="surrogatepass")
    return "".join(chr(data[index] | data[index + 1] << 8)
                   for index in range(0, len(data), 2))


def _text(units: str) -> str:
    return units.encode("utf-16-le", errors="surrogatepass").decode(
        "utf-16-le", errors="surrogatepass")


def concatenate(left: str, right: str) -> str:
    """Rejoin surrogate halves as well as ordinary strings (also used by +)."""
    return _text(left + right)


def _index(value: object, minimum: int, maximum: int) -> int:
    value = number(value)
    # Clamp while still a Decimal: int(Decimal("1e1000000")) would allocate
    # an enormous integer for a position whose result is already determined.
    if value <= minimum:
        return minimum
    if value >= maximum:
        return maximum
    # Decimal -> int truncates toward zero, without a float round trip.
    return int(value)


def string_length(value: object) -> Decimal:
    return Decimal(len(to_string(value).encode("utf-16-le", errors="surrogatepass")) // 2)


# Unlike Python splitlines(), 1C's observed separators are CRLF, CR and LF.
_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def line_count(value: object) -> Decimal:
    text = to_string(value)
    count = sum(1 for _ in _LINE_BREAK.finditer(text))
    return Decimal(count if text.endswith(("\r", "\n")) else count + 1)


def get_line(value: object, position: object) -> str:
    text = to_string(value)
    # Bound before integer conversion: enormous Decimals cannot allocate huge ints.
    index = _index(position, 0, len(text) + 1)
    if index < 1:
        return ""
    start = 0
    for boundary in _LINE_BREAK.finditer(text):
        if index == 1:
            return _text(text[start:boundary.start()])
        start = boundary.end()
        index -= 1
    return _text(text[start:]) if index == 1 else ""


def character(value: object) -> str:
    # Truncate without host-context rounding or expanding enormous exponents.
    # Native Char returns an empty string outside the UTF-16 code-unit range.
    code = number(value).to_integral_value(rounding=ROUND_DOWN)
    if code < 0 or code > 0xffff:
        return ""
    return chr(int(code))


def character_code(value: object, position: object = Decimal(1)) -> Decimal:
    text = _units(value)
    index = _index(position, 0, len(text) + 1)
    if index < 1 or index > len(text):
        return Decimal(-1)
    return Decimal(ord(text[index - 1]))


def left(value: object, count: object) -> str:
    text = _units(value)
    return _text(text[:_index(count, 0, len(text))])


def right(value: object, count: object) -> str:
    text = _units(value)
    count = _index(count, 0, len(text))
    # A zero count must not become Python's [-0:] (the entire string).
    return _text(text[max(0, len(text) - count):])


def mid(value: object, start: object, count: object = _OMITTED) -> str:
    text = _units(value)
    offset = _index(start, 1, len(text) + 1) - 1
    length = -1 if count is _OMITTED else _index(count, -1, len(text))
    return _text(text[offset:] if length < 0 else text[offset:offset + length])


def find(value: object, needle: object) -> Decimal:
    return Decimal(_units(value).find(_units(needle)) + 1)



def str_find(value: object, needle: object, direction: object = _OMITTED,
             start: object = _OMITTED, occurrence: object = _OMITTED) -> Decimal:
    """Native PR53 search with UTF-16 positions and nonoverlapping matches.

    Empty matches use the owner-observed initial result of one. Subsequent
    zero-width matches retain the normalized start; this closed form avoids
    iterating an arbitrarily large occurrence count.
    """
    if direction is _OMITTED:
        direction = BSLSearchDirection.FROM_BEGIN
    if type(direction) is not BSLSearchDirection:
        raise TypeError("СтрНайти: ожидается НаправлениеПоиска")
    text, search = _units(value), _units(needle)
    backward = direction is BSLSearchDirection.FROM_END
    default_start = start is _OMITTED or start is None
    if default_start:
        position = max(1, len(text)) if backward else 1
    else:
        raw = number(start).to_integral_value(rounding=ROUND_DOWN)
        # Compare before integer conversion; enormous decimal exponents cannot
        # allocate integers whose position is already known to be out of range.
        if raw < 1 or raw > max(1, len(text)):
            raise ValueError("СтрНайти: неверная начальная позиция")
        position = int(raw)
    count = (Decimal(1) if occurrence is _OMITTED else
             number(occurrence).to_integral_value(rounding=ROUND_DOWN))
    if count.is_zero():
        raise ValueError("СтрНайти: номер вхождения не может быть равен нулю")
    if count < 0:
        return Decimal(0)
    if not search:
        # Native probes distinguish occurrence 1 from 2 and confirm that a
        # zero-width match does not advance at occurrence 3. The closed form
        # generalizes that recurrence; higher combinations are not new goldens.
        return Decimal(1 if count == 1 else position)
    # At most this many disjoint matches exist in the entire input. Comparing
    # as Decimal bounds both the conversion and loop independently of the
    # requested occurrence (including enormous positive exponents).
    width = len(search)
    if count > len(text) // width:
        return Decimal(0)
    if backward:
        # Native start is the latest allowed match START, not its final unit.
        stop = min(len(text), position + width - 1)
        for _ in range(int(count)):
            found = text.rfind(search, 0, stop)
            if found < 0:
                return Decimal(0)
            stop = found
    else:
        offset = position - 1
        for _ in range(int(count)):
            found = text.find(search, offset)
            if found < 0:
                return Decimal(0)
            offset = found + width
    return Decimal(found + 1)


def starts_with(value: object, needle: object) -> bool:
    text, search = _units(value), _units(needle)
    if not search:
        raise ValueError("СтрНачинаетсяС: строка поиска не должна быть пустой")
    return text.startswith(search)


def ends_with(value: object, needle: object) -> bool:
    text, search = _units(value), _units(needle)
    if not search:
        raise ValueError("СтрЗаканчиваетсяНа: строка поиска не должна быть пустой")
    return text.endswith(search)


def replace(value: object, needle: object, replacement: object) -> str:
    text, old, new = _units(value), _units(needle), _units(replacement)
    # An empty needle is a no-op, not Python's insertion at every boundary.
    return _text(text.replace(old, new) if old else text)


def trim_left(value: object) -> str:
    return to_string(value).lstrip(_WHITESPACE)


def trim_right(value: object) -> str:
    return to_string(value).rstrip(_WHITESPACE)


def trim_all(value: object) -> str:
    return to_string(value).strip(_WHITESPACE)


def is_blank(value: object) -> bool:
    return not trim_all(value)


def _simple_upper(character: str) -> str:
    mapped = character.upper()
    return mapped if len(mapped) == 1 else _SIMPLE_UPPER_ALTERNATIVES.get(character, character)


def _simple_lower(character: str) -> str:
    mapped = character.lower()
    return mapped if len(mapped) == 1 else _SIMPLE_LOWER_ALTERNATIVES.get(character, character)


def upper(value: object) -> str:
    # Native samples are consistent with simple, nonexpanding casing. Map each
    # character independently, without full or contextual string casing rules.
    return "".join(_simple_upper(character) for character in to_string(value))


def lower(value: object) -> str:
    return "".join(_simple_lower(character) for character in to_string(value))


def split(value: object, separators: object, include_empty: object = True) -> BSLArray:
    text, delimiters = _units(value), set(_units(separators))
    # Explicit Undefined is false in the native StrSplit result; omission still
    # uses the True default. Do not broaden global Boolean conversion here.
    include_empty = False if include_empty is None else boolean(include_empty)
    result = BSLArray()
    start = 0
    for index, character in enumerate(text):
        if character in delimiters:
            if include_empty or index > start:
                result.add(_text(text[start:index]))
            start = index + 1
    if include_empty or start < len(text):
        result.add(_text(text[start:]))
    return result


def join(values: object, separator: object = "") -> str:
    if not isinstance(values, (BSLArray, BSLFixedArray)):
        raise TypeError("СтрСоединить ожидает массив или фиксированный массив")
    delimiter = to_string(separator)
    return _text(delimiter.join(to_string(value) for value in values))


def occurrence_count(value: object, substring: object) -> Decimal:
    """Count non-overlapping UTF-16 matches; an empty needle has no matches."""
    text, needle = _units(value), _units(substring)
    return Decimal(text.count(needle) if needle else 0)


def template(value: object, *values: object) -> str:
    """Numbered substitution; inserted presentations are never parsed again."""
    if len(values) > 10:
        raise ValueError("СтрШаблон: очень много параметров")
    text = to_string(value)
    parts: list[str | int] = []
    required = 0
    position = 0
    while position < len(text):
        marker = text.find("%", position)
        if marker < 0:
            parts.append(text[position:])
            break
        parts.append(text[position:marker])
        position = marker + 1
        if position < len(text) and text[position] == "%":
            parts.append("%")
            position += 1
            continue
        parenthesized = position < len(text) and text[position] == "("
        if parenthesized:
            position += 1
        start = position
        while position < len(text) and "0" <= text[position] <= "9":
            position += 1
        # Check length before int(): malformed huge markers must not construct
        # giant integers or depend on Python's decimal-string conversion limit.
        digits = text[start:position]
        if (len(digits) not in (1, 2) or digits[0] == "0"
                or (len(digits) == 2 and digits != "10")
                or (parenthesized and (position == len(text) or text[position] != ")"))):
            raise ValueError("СтрШаблон: недопустимый формат маркера подстановки")
        if parenthesized:
            position += 1
        index = int(digits)
        required = max(required, index)
        parts.append(index)
    if len(values) > required:
        raise ValueError("СтрШаблон: очень много параметров")
    presentations: dict[int, str] = {}
    for part in parts:
        if isinstance(part, int) and part not in presentations:
            presentations[part] = to_string(values[part - 1]) if part <= len(values) else ""
    return _text("".join(presentations[part] if isinstance(part, int) else part
                         for part in parts))


def compare(first: object, second: object) -> Decimal:
    # Do not invent coercion rules for unprobed non-string arguments.
    if type(first) is not str or type(second) is not str:
        raise TypeError("СтрСравнить: аргументы должны иметь тип Строка")
    left, right = caseless_string_key(first), caseless_string_key(second)
    return Decimal((left > right) - (left < right))


# Deliberate standalone compatibility policy, not an observed configuration
# metadata value or a universal native default. No environment/locale lookup.
_NSTR_DEFAULT_LANGUAGE = "ru"
_NSTR_SPACE = " \t"
# Local resource limits, independent of the measurement observer's 64 units.
_NSTR_MAX_TEMPLATE_UNITS = 1_000_000
_NSTR_MAX_CODE_UNITS = 128


def _nstr_scalar(value: object) -> str:
    kind = type(value)
    # Class equality/membership can invoke a hostile metaclass __eq__. Identity
    # checks must precede every conversion, including primitive subclasses.
    if (value is not None and value is not NULL
            and kind is not str and kind is not Decimal and kind is not bool):
        raise TypeError("НСтр: поддержаны только Строка, Число, Булево, Неопределено и Null")
    # Never call arbitrary objects' __str__. Number presentation retains its
    # existing independent bounds; this is not a general native coercion claim.
    return to_string(value)


def _nstr_bound(text: str, maximum: int) -> None:
    if len(text) > maximum or len(text) + sum(ord(c) > 0xffff for c in text) > maximum:
        raise ValueError("НСтр: превышен предел текста или кода языка Yadinassi")


def _nstr_letter(character: str) -> bool:
    # Explicit bounded alphabet: no host Unicode identifier/casefold expansion.
    return ("a" <= character <= "z" or "A" <= character <= "Z"
            or "а" <= character <= "я" or "А" <= character <= "Я"
            or character in "ёЁ")


def nstr(value: object, language: object = _OMITTED) -> str:
    """Bounded multilingual selection; see docs/nstr-runtime.md for policy.

    Parse the whole input even after finding the first matching key. A malformed
    later entry invalidates the earlier selection. No template/output table,
    dynamic evaluation, recursive grammar or locale-dependent fallback is used.
    """
    text = _nstr_scalar(value)
    code = "" if language is _OMITTED else _nstr_scalar(language)
    _nstr_bound(text, _NSTR_MAX_TEMPLATE_UNITS)
    _nstr_bound(code, _NSTR_MAX_CODE_UNITS)
    if not code:
        code = _NSTR_DEFAULT_LANGUAGE
    # Numeric presentations are not language codes in this bounded grammar.
    # The native Number/String(Number) control was empty, not conversion proof.
    selected_code = code.lower() if all(_nstr_letter(c) for c in code) else None
    position, length = 0, len(text)
    selected = None
    while position < length:
        while position < length and text[position] in _NSTR_SPACE + ";":
            position += 1
        if position == length:
            break
        start = position
        while position < length and _nstr_letter(text[position]):
            position += 1
        if position == start:
            return ""
        if position - start > _NSTR_MAX_CODE_UNITS:
            raise ValueError("НСтр: превышен предел кода языка Yadinassi")
        capture = selected is None and text[start:position].lower() == selected_code
        while position < length and text[position] in _NSTR_SPACE:
            position += 1
        if position == length or text[position] != "=":
            return ""
        position += 1
        while position < length and text[position] in _NSTR_SPACE:
            position += 1
        if position < length and text[position] == "'":
            position += 1
            start = position
            parts = [] if capture else None
            while position < length:
                if text[position] != "'":
                    position += 1
                    continue
                if position + 1 < length and text[position + 1] == "'":
                    if parts is not None:
                        parts.extend((text[start:position], "'"))
                    position += 2
                    start = position
                    continue
                if parts is not None:
                    parts.append(text[start:position])
                position += 1
                break
            else:
                return ""  # No closing quote, including a final doubled quote.
            while position < length and text[position] in _NSTR_SPACE:
                position += 1
            if position < length and text[position] != ";":
                return ""
            if parts is not None:
                selected = "".join(parts)
        else:
            start = position
            while position < length and text[position] != ";":
                if text[position] == "'":
                    return ""
                position += 1
            if capture:
                selected = text[start:position].strip(_NSTR_SPACE)
        if position < length:
            position += 1  # The verified separator; every loop moves forward.
    return "" if selected is None else _text(selected)


BUILTINS = (
    ("НСтр", nstr, "NStr"),
    ("СтрСравнить", compare, "StrCompare"),
    ("СтрЧислоВхождений", occurrence_count, "StrOccurrenceCount"),
    ("СтрЧислоСтрок", line_count, "StrLineCount"),
    ("СтрПолучитьСтроку", get_line, "StrGetLine"),
    ("СтрШаблон", template, "StrTemplate"),
    ("СтрДлина", string_length, "StrLen"),
    ("Символ", character, "Char"),
    ("КодСимвола", character_code, "CharCode"),
    ("Лев", left, "Left"),
    ("Прав", right, "Right"),
    ("Сред", mid, "Mid"),
    ("Найти", find, "Find"),
    ("СтрНайти", str_find, "StrFind"),
    ("СтрЗаменить", replace, "StrReplace"),
    ("СтрНачинаетсяС", starts_with, "StrStartsWith"),
    ("СтрЗаканчиваетсяНа", ends_with, "StrEndsWith"),
    ("СокрЛ", trim_left, "TrimL"),
    ("СокрП", trim_right, "TrimR"),
    ("СокрЛП", trim_all, "TrimAll"),
    ("ПустаяСтрока", is_blank, "IsBlankString"),
    ("ВРег", upper, "Upper"),
    ("НРег", lower, "Lower"),
    ("СтрРазделить", split, "StrSplit"),
    ("СтрСоединить", join, "StrConcat"),
)
