"""Bounded implementation of the owner's observed 1C internal stream format.

Not JSON or a promised stable interchange format. GUIDs and layouts come from
the owner's committed native output; cycles and undocumented tags are not guessed.
New runtime types must be added explicitly to the codec policy and its completeness test.
"""

from dataclasses import dataclass

from .dates import codec_text, read_codec
from decimal import Decimal
import re

from .maps import BSLFixedMap, BSLMap
from .round_modes import BSLRoundMode
from .search_directions import BSLSearchDirection
from .structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from .type_values import type_of
from .values import BSLArray, BSLFixedArray, BSLType


_MAX_NUMBER_DIGITS = 4096
_MAX_TEXT = 1024 * 1024
_MAX_DEPTH = 64
_MAX_NODES = 10000
FORMAT_ERROR = "Ошибка преобразования: Ошибка формата потока"
# These are implementation resource budgets, not inferred native limits.
_TYPE_IDS = {
    BSLType.UNDEFINED: "ee8d3e7c-f930-4a76-8aad-4ff9083a6ea6",
    BSLType.BOOLEAN: "5d4125ad-f6e7-4313-be32-f71d0ab60915",
    BSLType.NUMBER: "b0be78f2-0ee6-4d31-a3bb-77dd32ba5bec",
    BSLType.STRING: "9b6abf8b-0173-48e5-b0a0-83b21fcf63c5",
    BSLType.DATE: "aae38c48-a877-411c-a6d3-fbaa1f83c4bd",
    BSLType.ARRAY: "51e7a0d2-530b-11d4-b98a-008048da3034",
    BSLType.STRUCTURE: "4238019d-7e49-4fc9-91db-b6b951d5cf8e",
    BSLType.MAP: "3d48feae-a9c6-4c5a-a099-9eb6477630c6",
    BSLType.FIXED_ARRAY: "4500381b-db30-4a10-9db4-990038032acf",
    BSLType.FIXED_STRUCTURE: "3ee983d7-ace7-40f9-bb7e-2e916fcddd56",
    BSLType.FIXED_MAP: "220455ea-6c85-4513-996f-bbe79ed07774",
    BSLType.KEY_AND_VALUE: "850afa6f-5244-482f-9729-d78ec65ff607",
    BSLType.TYPE: "d47d59f8-73f0-481c-8b5e-f6384c0a4804",
    BSLType.ROUND_MODE: "32c82ccd-fef3-4070-beb5-b9c52afc781d",
    BSLType.ROUND_MODES: "a47c4665-311c-405a-828e-0c5a3ca3bdda",
    BSLType.SEARCH_DIRECTION: "bee8fa9f-59d0-4e71-9f6e-599d83cb1960",
    BSLType.SEARCH_DIRECTIONS: "ca8683c7-a41c-4c82-b912-6afb606e8b01",
}
_TYPES_BY_ID = {identifier: kind for kind, identifier in _TYPE_IDS.items()}
_ARRAYS = frozenset({BSLType.ARRAY, BSLType.FIXED_ARRAY})
_STRUCTURES = frozenset({BSLType.STRUCTURE, BSLType.FIXED_STRUCTURE})
_MAPS = frozenset({BSLType.MAP, BSLType.FIXED_MAP})
_CODECS = frozenset({BSLType.UNDEFINED, BSLType.BOOLEAN, BSLType.NUMBER,
                    BSLType.STRING, BSLType.DATE, BSLType.TYPE, BSLType.KEY_AND_VALUE,
                    BSLType.ROUND_MODE, BSLType.ROUND_MODES,
                    BSLType.SEARCH_DIRECTION, BSLType.SEARCH_DIRECTIONS}) | _ARRAYS | _STRUCTURES | _MAPS
_NUMBER = re.compile(r'[+-]?[0-9]+(?:\.[0-9]+)?')
_COUNT = re.compile(r'0|[1-9][0-9]*')
_HEX = frozenset('0123456789abcdef')


def _resource(operation: str) -> ValueError:
    return ValueError(f"{operation}: превышен предел ресурсов Yadinassi")


def _number(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("ЗначениеВСтрокуВнутр: ожидается конечное число")
    if value.is_zero():
        return '{"N",0}'
    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
        exponent += 1
    digits = digits[:end]
    if max(len(digits) + max(exponent, 0), -exponent) > _MAX_NUMBER_DIGITS:
        raise _resource("ЗначениеВСтрокуВнутр")
    return '{"N",' + format(Decimal((sign, digits, exponent)), "f") + '}'


class _Writer:
    def __init__(self):
        self.parts = []
        self.size = 0
        self.nodes = 0
        self.active = set()

    def emit(self, text):
        self.size += len(text)
        if self.size > _MAX_TEXT:
            raise _resource("ЗначениеВСтрокуВнутр")
        self.parts.append(text)

    def string(self, value):
        if len(value) > _MAX_TEXT:
            raise _resource("ЗначениеВСтрокуВнутр")
        self.emit('"')
        for char in value:
            code = ord(char)
            if char == '"':
                self.emit('""')
            elif 0xD800 <= code <= 0xDFFF:
                self.emit('"\\' + format(code, '04x'))
            elif code > 0xFFFF:
                code -= 0x10000
                self.emit('"\\' + format(0xD800 + (code >> 10), '04x'))
                self.emit('"\\' + format(0xDC00 + (code & 0x3FF), '04x'))
            else:
                self.emit(char)
        self.emit('"')

    def value(self, value, depth=0):
        self.nodes += 1
        if self.nodes > _MAX_NODES or depth > _MAX_DEPTH:
            raise _resource("ЗначениеВСтрокуВнутр")
        try:
            kind = type_of(value)
        except TypeError:
            raise TypeError("ЗначениеВСтрокуВнутр: значение не относится к поддерживаемым типам BSL") from None
        if kind not in _CODECS:
            raise ValueError("ЗначениеВСтрокуВнутр: для типа не задана политика сериализации Yadinassi")
        if kind is BSLType.UNDEFINED:
            self.emit('{"U"}')
        elif kind is BSLType.BOOLEAN:
            self.emit('{"B",1}' if value else '{"B",0}')
        elif kind is BSLType.NUMBER:
            self.emit(_number(value))
        elif kind is BSLType.STRING:
            self.emit('{"S",')
            self.string(value)
            self.emit('}')
        elif kind is BSLType.DATE:
            self.emit('{"D",' + codec_text(value, nested=depth > 0) + '}')
        elif kind is BSLType.TYPE:
            self.emit('{"T",' + _TYPE_IDS[value] + '}')
        elif kind in (BSLType.ROUND_MODE, BSLType.SEARCH_DIRECTION):
            self.emit('{"#",' + _TYPE_IDS[kind] + ',' + str(value.value) + '}')
        elif kind in (BSLType.ROUND_MODES, BSLType.SEARCH_DIRECTIONS):
            self.emit('{"#",' + _TYPE_IDS[kind] + '}')
        else:
            identity = id(value)
            if identity in self.active:
                raise ValueError("ЗначениеВСтрокуВнутр: циклические значения пока не поддерживаются в Yadinassi")
            self.active.add(identity)
            try:
                self.emit('{"#",' + _TYPE_IDS[kind] + ',\n')
                if kind is BSLType.KEY_AND_VALUE:
                    self.pair(value.key, value.value, depth)
                else:
                    count = len(value.items) if kind in _ARRAYS else len(value._items)
                    if count > _MAX_NODES:
                        raise _resource("ЗначениеВСтрокуВнутр")
                    self.emit('{' + str(count))
                    if kind in _ARRAYS:
                        for item in value.items:
                            self.emit(',\n')
                            self.value(item, depth + 1)
                    else:
                        # Observed in both forward/reverse insertion probes and
                        # their readbacks. No general map order guarantee.
                        # A fixed snapshot's native payload follows its source
                        # insertion order, unlike the mutable-map payload.
                        entries = (reversed(value._items.values()) if kind is BSLType.MAP
                                   else value._items.values())
                        for key, item in entries:
                            self.emit(',\n')
                            self.pair(key, item, depth)
                    self.emit('\n}' if count else '}')
                self.emit('\n}')
            finally:
                self.active.remove(identity)

    def pair(self, key, value, depth):
        self.emit('{\n')
        self.value(key, depth + 1)
        self.emit(',\n')
        self.value(value, depth + 1)
        self.emit('\n}')


def value_to_string_internal(value: object) -> str:
    writer = _Writer()
    writer.value(value)
    return ''.join(writer.parts)


@dataclass(frozen=True)
class _Atom:
    text: str


class _Reader:
    """Small bounded stream grammar; only explicitly listed BSL types exist."""
    def __init__(self, text):
        self.text = text
        self.position = 0
        self.tokens = 0
        self.nodes = 0

    def fail(self):
        raise ValueError(FORMAT_ERROR)

    def whitespace(self):
        while self.position < len(self.text) and self.text[self.position] in ' \t\r\n':
            self.position += 1

    def string(self):
        self.position += 1
        parts = []
        while self.position < len(self.text):
            char = self.text[self.position]
            self.position += 1
            if char != '"':
                parts.append(char)
                continue
            if self.position < len(self.text) and self.text[self.position] == '"':
                parts.append('"')
                self.position += 1
            elif self.position < len(self.text) and self.text[self.position] == '\\':
                digits = self.text[self.position + 1:self.position + 5]
                if len(digits) != 4 or any(digit not in _HEX for digit in digits):
                    self.fail()
                code = int(digits, 16)
                # Native evidence establishes UTF-16 surrogate escapes, not
                # arbitrary quoted escapes for other character ranges.
                if not 0xD800 <= code <= 0xDFFF:
                    self.fail()
                parts.append(chr(code))
                self.position += 5
            else:
                return ''.join(parts).encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'surrogatepass')
        self.fail()

    def token(self, depth=0):
        self.tokens += 1
        if self.tokens > _MAX_NODES * 8 or depth > _MAX_DEPTH * 3 + 3:
            raise _resource("ЗначениеИзСтрокиВнутр")
        self.whitespace()
        if self.position >= len(self.text):
            self.fail()
        char = self.text[self.position]
        if char == '"':
            return self.string()
        if char != '{':
            start = self.position
            while self.position < len(self.text) and self.text[self.position] not in ',} \t\r\n':
                self.position += 1
            if self.position == start:
                self.fail()
            return _Atom(self.text[start:self.position])
        self.position += 1
        result = []
        self.whitespace()
        if self.position < len(self.text) and self.text[self.position] == '}':
            self.position += 1
            return result
        while True:
            result.append(self.token(depth + 1))
            self.whitespace()
            if self.position >= len(self.text):
                self.fail()
            char = self.text[self.position]
            self.position += 1
            if char == '}':
                return result
            if char != ',':
                self.fail()

    def number(self, token):
        if type(token) is not _Atom or _NUMBER.fullmatch(token.text) is None:
            self.fail()
        if len(token.text) > _MAX_NUMBER_DIGITS + 3:
            raise _resource("ЗначениеИзСтрокиВнутр")
        value = Decimal(token.text)
        try:
            _number(value)
        except ValueError:
            raise _resource("ЗначениеИзСтрокиВнутр") from None
        return value

    def value(self, group, depth=0):
        self.nodes += 1
        if self.nodes > _MAX_NODES or depth > _MAX_DEPTH:
            raise _resource("ЗначениеИзСтрокиВнутр")
        if type(group) is not list or not group or type(group[0]) is not str:
            self.fail()
        tag = group[0]
        if tag == 'U' and len(group) == 1:
            return None
        if tag == 'B' and len(group) == 2 and type(group[1]) is _Atom and group[1].text in ('0', '1'):
            return group[1].text == '1'
        if tag == 'S' and len(group) == 2 and type(group[1]) is str:
            return group[1]
        if tag == 'N' and len(group) in (2, 3):
            value = self.number(group[1])
            if len(group) == 3:
                self.number(group[2])  # Observed {"N",1,5} reads the first number.
            return value
        if tag == 'D' and len(group) == 2:
            if type(group[1]) is not _Atom:
                self.fail()
            try:
                return read_codec(group[1].text)
            except (ValueError, TypeError, OverflowError):
                self.fail()
        if tag == 'n' and len(group) == 2:
            self.number(group[1])
            return None  # Observed lowercase numeric tag; not arbitrary unknown tags.
        if (tag == '#' and len(group) == 2 and type(group[1]) is _Atom
                and group[1].text in (_TYPE_IDS[BSLType.ROUND_MODES],
                                      _TYPE_IDS[BSLType.SEARCH_DIRECTIONS])):
            # Native round/search namespace probes establish Undefined on
            # readback. Type records still restore the namespace identities.
            return None
        if tag not in ('T', '#') or len(group) != (2 if tag == 'T' else 3):
            self.fail()
        if type(group[1]) is not _Atom or group[1].text not in _TYPES_BY_ID:
            self.fail()
        kind = _TYPES_BY_ID[group[1].text]
        if tag == 'T':
            return kind
        body = group[2]
        if kind is BSLType.ROUND_MODE:
            if type(body) is not _Atom or body.text not in ('0', '1'):
                self.fail()
            return BSLRoundMode.ROUND15_AS10 if body.text == '0' else BSLRoundMode.ROUND15_AS20
        if kind is BSLType.SEARCH_DIRECTION:
            if type(body) is not _Atom or body.text not in ('0', '1'):
                self.fail()
            return BSLSearchDirection.FROM_BEGIN if body.text == '0' else BSLSearchDirection.FROM_END
        if type(body) is not list:
            self.fail()
        if kind is BSLType.KEY_AND_VALUE and len(body) == 2:
            return BSLKeyAndValue(self.value(body[0], depth + 1), self.value(body[1], depth + 1))
        if kind not in _ARRAYS | _STRUCTURES | _MAPS or not body or type(body[0]) is not _Atom:
            self.fail()
        count_text = body[0].text
        if _COUNT.fullmatch(count_text) is None:
            self.fail()
        if len(count_text) > 5 or int(count_text) > _MAX_NODES:
            raise _resource("ЗначениеИзСтрокиВнутр")
        count = int(count_text)
        if len(body) != count + 1:
            self.fail()
        if kind in _ARRAYS:
            items = [self.value(item, depth + 1) for item in body[1:]]
            if kind is BSLType.ARRAY:
                result = BSLArray()
                result.items = items
            else:
                # The stream already specifies each nested type. The public
                # snapshot constructor would recursively freeze direct arrays.
                result = object.__new__(BSLFixedArray)
                result.items = tuple(items)
            return result
        result = BSLStructure() if kind in _STRUCTURES else BSLMap()
        for pair in body[1:]:
            if type(pair) is not list or len(pair) != 2:
                self.fail()
            key, value = (self.value(item, depth + 1) for item in pair)
            if kind in _STRUCTURES and type(key) is not str:
                self.fail()
            try:
                result.insert(key, value)
            except (ValueError, TypeError):
                self.fail()
        if kind is BSLType.FIXED_STRUCTURE:
            return BSLFixedStructure(result)
        if kind is BSLType.FIXED_MAP:
            # Readback of the observed fixed snapshot reverses stream order.
            # Keep this codec-local; collection iteration has no order promise.
            result._items = dict(reversed(tuple(result._items.items())))
            return BSLFixedMap(result)
        return result


def value_from_string_internal(text: object) -> object:
    if type(text) is not str:
        raise TypeError("ЗначениеИзСтрокиВнутр: ожидается строка")
    if len(text) > _MAX_TEXT:
        raise _resource("ЗначениеИзСтрокиВнутр")
    reader = _Reader(text)
    # Native evidence accepts a complete first record followed by garbage.
    return reader.value(reader.token())
