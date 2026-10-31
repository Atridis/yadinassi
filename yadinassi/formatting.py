"""Bounded numeric and numeric-mask Date Format; native witnesses are documented.

No host locale, binary float, Decimal context, or host Decimal formatting is
used. This is not the complete native date/Boolean/numeric format language.
"""
from decimal import Decimal

from .dates import BSLDate, _parts as date_parts
from .values import NULL, to_string

_MAX_TEXT = 4096
_MAX_DIGITS = 4096
_MAX_FRACTION = 324
_ALIASES = {"NFD": "NFD", "ЧДЦ": "NFD", "NDS": "NDS", "ЧРД": "NDS",
            "NG": "NG", "ЧГ": "NG", "NGS": "NGS", "ЧРГ": "NGS",
            "NZ": "NZ", "ЧН": "NZ", "L": "L", "Л": "L"}

# Recognized native families outside this bounded slice must not become no-ops.
_UNIMPLEMENTED = frozenset(("ND", "ЧЦ", "NS", "ЧС", "NLZ", "ЧВН", "NN", "ЧО", "NF", "ЧФ",
                            "DLF", "ДЛФ",
                            "BF", "БЛ", "BT", "БИ"))

def _unsupported():
    raise ValueError("Формат: формат вне поддержанного подмножества Yadinassi")


def _bound(text):
    if len(text) > _MAX_TEXT or len(text) + sum(ord(c) > 0xffff for c in text) > _MAX_TEXT:
        raise ValueError("Формат: превышен предел текста Yadinassi")


def _parameters(text):
    """Whole-input scanner with separate numeric and Date selection rules."""
    _bound(text)
    result = {}
    date_entries = {}
    i = 0
    while i < len(text):
        if text[i] in " ;\t":
            i += 1
            continue
        start = i
        while i < len(text) and text[i] not in "=;":
            i += 1
        if i == len(text) or text[i] != "=":
            _unsupported()
        raw_name = text[start:i].strip(" \t")
        if (not raw_name or any(not ("A" <= c <= "Z" or "a" <= c <= "z"
                                     or "А" <= c <= "Я" or "а" <= c <= "я"
                                     or c in "Ёё") for c in raw_name)):
            _unsupported()
        folded = raw_name.upper()
        if folded in _UNIMPLEMENTED:
            _unsupported()
        # Numeric/locale names are exact-case; Date aliases are case-insensitive.
        date_key = folded if folded in {"DF", "ДФ", "DE", "ДП"} else None
        key = _ALIASES.get(raw_name)
        i += 1
        while i < len(text) and text[i] in " \t":
            i += 1
        quote = text[i] if i < len(text) and text[i] in "'\"" else None
        if quote is not None:
            i += 1
            parts = []
            while i < len(text):
                if text[i] != quote:
                    parts.append(text[i])
                    i += 1
                elif i + 1 < len(text) and text[i + 1] == quote:
                    parts.append(quote)
                    i += 2
                else:
                    i += 1
                    break
            else:
                _unsupported()
            value = "".join(parts)
            while i < len(text) and text[i] in " \t":
                i += 1
            if i < len(text) and text[i] != ";":
                _unsupported()
        else:
            start = i
            while i < len(text) and text[i] != ";":
                if text[i] in "'\"":
                    _unsupported()
                i += 1
            value = text[start:i].strip(" \t")
        # Validate every entry, even one later overwritten: unsupported syntax
        # cannot hide behind a valid final duplicate.
        if key == "NFD":
            if (not value or len(value) > 3 or not value.isascii()
                    or not value.isdigit() or int(value) > _MAX_FRACTION):
                _unsupported()
        elif key == "NG":
            _grouping(value)
        elif key == "L" and value != "ru":
            _unsupported()
        elif key == "NDS" and not value:
            _unsupported()
        if date_key is not None:
            if date_key in {"DF", "ДФ"}:
                if not value:
                    _unsupported()
                tokens = _date_tokens(value)
                # Native bare multiword Date masks fall back to the default.
                value = None if quote is None and any(c in " \t" for c in value) else tokens
            date_entries.setdefault(date_key, value)
        elif key is not None:
            result[key] = value
        if i < len(text):
            i += 1
    # First duplicate within an alias; Russian alias precedes English alias.
    for canonical, russian in (("DF", "ДФ"), ("DE", "ДП")):
        if russian in date_entries:
            result[canonical] = date_entries[russian]
        elif canonical in date_entries:
            result[canonical] = date_entries[canonical]
    return result


def _date_tokens(mask):
    """Bounded numeric date tokens and quoted literals; not strftime grammar."""
    tokens = []
    allowed = {"d", "dd", "M", "MM", "yy", "yyyy", "H", "HH", "m", "mm", "s", "ss"}
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
            token = mask[i:end]
            if token not in allowed:
                _unsupported()
            tokens.append((True, token))
            i = end
        else:
            tokens.append((False, mask[i]))
            i += 1
    return tuple(tokens)


def _format_date(value, parameters):
    parts = date_parts(value)  # Validates known state, including empty-date boundary.
    if value.ticks == 0:
        if "DE" not in parameters:
            return ""
        if parameters["DE"]:
            return parameters["DE"]
    tokens = parameters.get("DF")
    if tokens is None:
        return str(value)
    components = {"d": parts.day, "M": parts.month, "y": parts.year,
                  "H": parts.hour, "m": parts.minute, "s": parts.second}
    output = []
    size = 0
    for numeric, token in tokens:
        if numeric:
            number = components[token[0]]
            if token == "yy":
                number %= 100
            text = str(number).zfill(len(token))
        else:
            text = token
        size += len(text) + sum(ord(c) > 0xffff for c in text)
        if size > _MAX_TEXT:
            raise ValueError("Формат: превышен предел текста Yadinassi")
        output.append(text)
    return "".join(output)


def _grouping(value):
    # One or two widths; primary 1C regional settings documentation describes
    # single A and A,B (B=0 repeats A). This subset rejects further fields.
    parts = value.split(",")
    if not 1 <= len(parts) <= 2:
        _unsupported()
    for part in parts:
        if not part or len(part) > 2 or not part.isascii() or not part.isdigit() or int(part) > 32:
            _unsupported()
    widths = tuple(int(part) for part in parts)
    if widths[0] == 0 and len(widths) != 1:
        _unsupported()
    return widths


def _decimal_parts(value, places):
    if not value.is_finite():
        _unsupported()
    sign, digits, exponent = value.as_tuple()
    # Bound before expanding exponents; these are local allocation budgets.
    if (len(digits) > _MAX_DIGITS or exponent < -_MAX_FRACTION
            or len(digits) + max(exponent, 0) > _MAX_DIGITS):
        raise ValueError("Формат: превышен предел десятичных разрядов Yadinassi")
    text = "".join(chr(48 + digit) for digit in digits)
    point = len(text) + exponent
    if point <= 0:
        integer, fraction = "0", "0" * -point + text
    elif point >= len(text):
        integer, fraction = text + "0" * (point - len(text)), ""
    else:
        integer, fraction = text[:point], text[point:]
    if places is None:
        fraction = fraction.rstrip("0")
    else:
        kept = integer + fraction[:places].ljust(places, "0")
        if len(fraction) > places and fraction[places] >= "5":
            # Round magnitude half away from zero, without a context-sensitive
            # Decimal operation or a host integer-to-string digit limit.
            chars = list(kept)
            i = len(chars) - 1
            while i >= 0 and chars[i] == "9":
                chars[i] = "0"
                i -= 1
            if i >= 0:
                chars[i] = chr(ord(chars[i]) + 1)
            else:
                chars.insert(0, "1")
            kept = "".join(chars)
        integer = kept[:-places] if places else kept
        fraction = kept[-places:] if places else ""
    integer = integer.lstrip("0") or "0"
    negative = bool(sign and any(c != "0" for c in integer + fraction))
    return negative, integer, fraction


def format_value(value, specification=""):
    """Format supported exact scalars; unsupported masks fail explicitly."""
    kind = type(value)
    if (value is not None and value is not NULL and kind is not Decimal
            and kind is not str and kind is not bool and kind is not BSLDate):
        raise TypeError("Формат: неподдержанный тип значения")
    if type(specification) is Decimal:
        # The numeric second-argument witness is a no-directive format. The
        # broader finite-Number behavior is an explicit local scalar policy.
        _decimal_parts(specification, None)
        parameters = {}
    elif type(specification) is str:
        parameters = _parameters(specification)
    else:
        raise TypeError("Формат: формат должен быть строкой или числом")
    if kind is not Decimal:
        result = _format_date(value, parameters) if kind is BSLDate else to_string(value)
        _bound(result)
        return result
    places = int(parameters["NFD"]) if "NFD" in parameters else None
    negative, integer, fraction = _decimal_parts(value, places)
    # NZ tests the original numeric zero, NOT the rounded magnitude.
    if value.is_zero() and parameters.get("NZ") != "":
        return parameters.get("NZ", "")
    separator = parameters.get("NGS") or "\u00a0"
    widths = _grouping(parameters["NG"]) if "NG" in parameters else (3, 0)
    first = widths[0]
    # Preflight the output bound before join can multiply a long separator.
    separators = 0
    if first and len(integer) > first:
        separators = 1
        if len(widths) == 2:
            repeat = widths[1] or first
            separators += (len(integer) - first - 1) // repeat
    estimated = (len(integer) + len(fraction) + bool(negative)
                 + separators * len(separator)
                 + (len(parameters.get("NDS", ",")) if fraction else 0))
    if estimated > _MAX_TEXT:
        raise ValueError("Формат: превышен предел текста Yadinassi")
    if first and len(integer) > first:
        leading, last = integer[:-first], integer[-first:]
        if len(widths) == 2:
            repeat = widths[1] or first
            groups = [leading[max(0, end - repeat):end]
                      for end in range(len(leading), 0, -repeat)]
            leading = separator.join(reversed(groups))
        integer = leading + separator + last
    result = ("-" if negative else "") + integer
    if fraction:
        result += parameters.get("NDS", ",") + fraction
    _bound(result)
    return result


BUILTINS = (("Формат", format_value, "Format"),)
