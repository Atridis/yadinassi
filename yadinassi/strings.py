"""String builtins, with positions measured in UTF-16 code units.

The public Python API still uses str. A temporary code-unit string keeps searches
aligned and lets slicing preserve individual surrogate halves without depending
on the host platform's wchar_t width. See features.md for compatibility limits.
"""

from decimal import Decimal

from .values import BSLArray, boolean, number, to_string


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
    if not isinstance(values, BSLArray):
        raise TypeError("СтрСоединить ожидает массив")
    delimiter = to_string(separator)
    return _text(delimiter.join(to_string(value) for value in values))


BUILTINS = (
    ("СтрДлина", string_length, "StrLen"),
    ("Лев", left, "Left"),
    ("Прав", right, "Right"),
    ("Сред", mid, "Mid"),
    ("Найти", find, "Find"),
    ("СтрЗаменить", replace, "StrReplace"),
    ("СокрЛ", trim_left, "TrimL"),
    ("СокрП", trim_right, "TrimR"),
    ("СокрЛП", trim_all, "TrimAll"),
    ("ПустаяСтрока", is_blank, "IsBlankString"),
    ("ВРег", upper, "Upper"),
    ("НРег", lower, "Lower"),
    ("СтрРазделить", split, "StrSplit"),
    ("СтрСоединить", join, "StrConcat"),
)
