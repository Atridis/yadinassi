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
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (
    BSLAllowedLength, BSLAllowedSign, BSLDateFractions, BSLDateQualifiers,
    BSLNumberQualifiers, BSLStringQualifiers,
)
from .value_tables import (BSLValueTable, BSLValueTableColumn,
                           BSLCollectionIndexes, BSLCollectionIndex)
from .value_lists import BSLValueList, BSLValueListItem
from .type_values import type_of
from .values import BSLArray, BSLFixedArray, BSLType, NULL, equal


_MAX_NUMBER_DIGITS = 4096
_MAX_TEXT = 1024 * 1024
_MAX_DEPTH = 64
_MAX_NODES = 10000
# Lexical tokens include metadata that is not a semantic value node. The
# supported layouts need at most 23 metadata tokens per charged node (a
# fully qualified table column plus its two column-map references); an empty
# table needs 18, a list header 14, and a list item 19 before its child value.
# Keep a separate bounded allowance, with headroom, so valid writer output
# does not exhaust the parser solely on default picture/pattern metadata.
_MAX_TOKENS_PER_NODE = 32
FORMAT_ERROR = "Ошибка преобразования: Ошибка формата потока"
# These are implementation resource budgets, not inferred native limits.
_TYPE_IDS = {
    BSLType.XML_STRING_PROCESSING_MANAGER: "8f646b4e-fc39-44c7-85a2-c2eb39cdf361",
    BSLType.NULL: "af40a278-63bc-478e-91a8-19e0d16b10b5",
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
    BSLType.NUMBER_QUALIFIERS: "f6f6ce00-392c-49ed-8c6e-4e0295fd4051",
    BSLType.STRING_QUALIFIERS: "a5e1773c-a947-455a-a2f7-c51736d3f2de",
    BSLType.DATE_QUALIFIERS: "e73e1337-53df-4b30-a78c-ee1e8cf30fc0",
    BSLType.BINARY_DATA_QUALIFIERS: "73315712-166d-400d-adaf-287bd8f41b8d",
    BSLType.ALLOWED_SIGN: "9c4a8801-ff83-40d7-96d7-cc2b85430fbe",
    BSLType.ALLOWED_SIGNS: "eb851bfe-cc2a-4d16-84a4-e480da76672d",
    BSLType.ALLOWED_LENGTH: "3e4a7ff2-82a0-40ee-9000-3e83a3191b71",
    BSLType.ALLOWED_LENGTHS: "2f7878c0-bc8a-4820-a3b9-6bf1111ae5b0",
    BSLType.DATE_FRACTIONS: "8089abb5-ff39-4414-8252-c0dcef1c3d6b",
    BSLType.DATE_FRACTIONS_NAMESPACE: "83f71799-efb3-4984-a19b-6ed4f3cbc691",
    BSLType.TYPE_DESCRIPTION: "f5c65050-3bbb-11d5-b988-0050bae0a95d",
    BSLType.VALUE_LIST: "4772b3b4-f4a3-49c0-a1a5-8cb5961511a3",
    BSLType.VALUE_LIST_ITEM: "c27d99e0-2f53-11d5-a3be-0050bae0a776",
    BSLType.VALUE_TABLE: "acf6192e-81ca-46ef-93a6-5a6968b78663",
    BSLType.VALUE_TABLE_COLUMN_COLLECTION: "0e2c7b45-ad6d-4ebe-8c9b-358d42ab5002",
    BSLType.VALUE_TABLE_COLUMN: "e162969e-36e8-44f4-a5fd-fa2bf170a4f5",
    BSLType.VALUE_TABLE_ROW: "ac6bbae9-9a0f-4ec9-be2a-d9b1caa4eb36",
    BSLType.COLLECTION_INDEXES: "3a461c5c-0a17-430a-ae05-90890129a7da",
    BSLType.COLLECTION_INDEX: "4523f487-9cd3-4779-89f5-92023e88037b",
}
_TYPES_BY_ID = {identifier: kind for kind, identifier in _TYPE_IDS.items()}
_ARRAYS = frozenset({BSLType.ARRAY, BSLType.FIXED_ARRAY})
_STRUCTURES = frozenset({BSLType.STRUCTURE, BSLType.FIXED_STRUCTURE})
_MAPS = frozenset({BSLType.MAP, BSLType.FIXED_MAP})
_ENUM_TYPES = {
    BSLType.ROUND_MODE: BSLRoundMode,
    BSLType.SEARCH_DIRECTION: BSLSearchDirection,
    BSLType.ALLOWED_SIGN: BSLAllowedSign,
    BSLType.ALLOWED_LENGTH: BSLAllowedLength,
    BSLType.DATE_FRACTIONS: BSLDateFractions,
}
_ENUM_MEMBERS = {kind: {str(member.value): member for member in enum_type}
                 for kind, enum_type in _ENUM_TYPES.items()}
# Native snapshots write these objects without a body and read them as
# Undefined, including configured qualifiers. Their Type records do roundtrip.
_OPAQUE_TYPES = frozenset({
    BSLType.ROUND_MODES, BSLType.SEARCH_DIRECTIONS,
    BSLType.XML_STRING_PROCESSING_MANAGER,
    BSLType.NUMBER_QUALIFIERS, BSLType.STRING_QUALIFIERS,
    BSLType.DATE_QUALIFIERS, BSLType.BINARY_DATA_QUALIFIERS,
    BSLType.ALLOWED_SIGNS, BSLType.ALLOWED_LENGTHS,
    BSLType.DATE_FRACTIONS_NAMESPACE,
    BSLType.VALUE_TABLE_COLUMN_COLLECTION, BSLType.VALUE_TABLE_COLUMN,
    BSLType.VALUE_TABLE_ROW,
    BSLType.COLLECTION_INDEXES, BSLType.COLLECTION_INDEX,
})
_OPAQUE_IDS = frozenset(_TYPE_IDS[kind] for kind in _OPAQUE_TYPES)
_CODECS = (frozenset({BSLType.NULL, BSLType.UNDEFINED, BSLType.BOOLEAN, BSLType.NUMBER,
                     BSLType.STRING, BSLType.DATE, BSLType.TYPE, BSLType.KEY_AND_VALUE,
                     BSLType.TYPE_DESCRIPTION, BSLType.VALUE_TABLE,
                     BSLType.VALUE_LIST, BSLType.VALUE_LIST_ITEM})
           | frozenset(_ENUM_TYPES) | _OPAQUE_TYPES | _ARRAYS | _STRUCTURES | _MAPS)
_PATTERN_TYPES = {'B': BSLType.BOOLEAN, 'S': BSLType.STRING, 'D': BSLType.DATE,
                 'N': BSLType.NUMBER, 'L': BSLType.NULL}
_PATTERN_TAGS = {kind: tag for tag, kind in _PATTERN_TYPES.items()}
_NUMBER = re.compile(r'[+-]?[0-9]+(?:\.[0-9]+)?')
_COUNT = re.compile(r'0|[1-9][0-9]*')
_LIST_ENTRY_ID = "1e512aab-1b41-4ef6-9375-f0137be9dd91"
_LIST_PICTURE = '{4,0,\n{0},"",-1,-1,0,0,""}'
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


def _require_representable_description(value: BSLTypeDescription) -> None:
    """Never silently erase settings for types absent from the Pattern."""
    n, s, d, b = (value.number_qualifiers, value.string_qualifiers,
                  value.date_qualifiers, value.binary_data_qualifiers)
    if ((BSLType.NUMBER not in value.types and
         (n.digits != 0 or n.fraction_digits != 0 or n.allowed_sign is not BSLAllowedSign.ANY))
            or (BSLType.STRING not in value.types and
                (s.length != 0 or s.allowed_length is not BSLAllowedLength.VARIABLE))
            or (BSLType.DATE not in value.types and d.date_fractions is not BSLDateFractions.DATE_TIME)
            or b.length != 0 or b.allowed_length is not BSLAllowedLength.VARIABLE):
        raise ValueError("ЗначениеВСтрокуВнутр: квалификаторы отсутствующего типа "
                         "пока не поддерживаются в Yadinassi до проверки на реальной 1С")


def _table_cell_matches(description, value):
    """Validate a snapshot without coercing its payload or erasing qualifiers."""
    if not description.types:
        return True
    if value is None:
        # Composite descriptions have Undefined as their observed default.
        return len(description.types) > 1
    if type_of(value) not in description.types:
        return False
    adjusted = description.adjust_value(value)
    return type_of(adjusted) is type_of(value) and equal(adjusted, value)


def _pattern_entry(kind: BSLType, value: BSLTypeDescription) -> str:
    entry = '{"' + _PATTERN_TAGS[kind] + '"'
    if kind is BSLType.NUMBER:
        n = value.number_qualifiers
        if n.digits != 0 or n.allowed_sign is not BSLAllowedSign.ANY:
            entry += (',' + str(int(n.digits)) + ',' + str(int(n.fraction_digits))
                      + ',' + str(n.allowed_sign.value))
    elif kind is BSLType.STRING:
        s = value.string_qualifiers
        if s.length != 0:
            entry += ',' + str(int(s.length)) + ',' + str(s.allowed_length.value)
    elif kind is BSLType.DATE:
        fraction = value.date_qualifiers.date_fractions
        if fraction is not BSLDateFractions.DATE_TIME:
            entry += ',"' + ('D' if fraction is BSLDateFractions.DATE else 'T') + '"'
    return entry + '}'


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
        elif kind is BSLType.NULL:
            self.emit('{"L"}')
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
        elif kind in _ENUM_TYPES:
            self.emit('{"#",' + _TYPE_IDS[kind] + ',' + str(value.value) + '}')
        elif kind in _OPAQUE_TYPES:
            self.emit('{"#",' + _TYPE_IDS[kind] + '}')
        elif kind is BSLType.TYPE_DESCRIPTION:
            _require_representable_description(value)
            self.emit('{"#",' + _TYPE_IDS[kind] + ',\n{"Pattern"')
            for entry in value.types:
                self.emit(',\n' + _pattern_entry(entry, value))
            self.emit('\n}' if value.types else '}')
            self.emit('\n}')
        else:
            identity = id(value)
            if identity in self.active:
                raise ValueError("ЗначениеВСтрокуВнутр: циклические значения пока не поддерживаются в Yadinassi")
            self.active.add(identity)
            try:
                self.emit('{"#",' + _TYPE_IDS[kind] + ',\n')
                if kind is BSLType.VALUE_LIST:
                    self.value_list(value, depth)
                elif kind is BSLType.VALUE_LIST_ITEM:
                    self.value_list_item(value, depth)
                elif kind is BSLType.VALUE_TABLE:
                    self.table(value, depth)
                elif kind is BSLType.KEY_AND_VALUE:
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
                            if kind in _MAPS and type(key) is BSLTypeDescription:
                                raise TypeError("ОписаниеТипов как ключ соответствия "
                                                "пока не поддерживается в Yadinassi")
                            self.emit(',\n')
                            self.pair(key, item, depth)
                    self.emit('\n}' if count else '}')
                self.emit('\n}')
            finally:
                self.active.remove(identity)

    def value_list(self, value, depth):
        description = value.value_type
        if type(description) is not BSLTypeDescription or description.types:
            raise ValueError("ЗначениеВСтрокуВнутр: поддерживается только пустой тип списка значений")
        _require_representable_description(description)
        if (type(value.items) is not list or type(value._by_id) is not dict
                or type(value._next_id) is not int or not 0 <= value._next_id <= 2 ** 32):
            raise ValueError("ЗначениеВСтрокуВнутр: недопустимое состояние списка значений")
        count = len(value.items)
        self.nodes += count
        if self.nodes > _MAX_NODES:
            raise _resource("ЗначениеВСтрокуВнутр")
        seen = set()
        for item in value.items:
            if (type(item) is not BSLValueListItem or type(item._id) is not int
                    or not 0 <= item._id < value._next_id or item._id in seen
                    or item._detached or item._owner_ref() is not value
                    or value._by_id.get(item._id) is not item):
                raise ValueError("ЗначениеВСтрокуВнутр: недопустимый элемент списка значений")
            seen.add(item._id)
        if len(value._by_id) != count:
            raise ValueError("ЗначениеВСтрокуВнутр: недопустимые идентификаторы списка значений")
        self.emit('{6,' + _LIST_ENTRY_ID + ',0,0,\n{' + str(count))
        for item in value.items:
            # Item identity participates in cycles even though list entries do
            # not carry the standalone item type wrapper.
            identity = id(item)
            if identity in self.active:
                raise ValueError("ЗначениеВСтрокуВнутр: циклические значения пока не поддерживаются в Yadinassi")
            self.active.add(identity)
            try:
                self.emit(',\n{' + _LIST_ENTRY_ID + ',\n')
                self.value_list_item(item, depth + 1)
                self.emit('\n}')
            finally:
                self.active.remove(identity)
        self.emit('\n}' if count else '}')
        self.emit(',\n{"Pattern"},0,' + str(value._next_id - 1) + '}')

    def value_list_item(self, item, depth):
        if (type(item.presentation) is not str or type(item.check) is not bool
                or type(item._id) is not int or not -1 <= item._id < 2 ** 32):
            raise ValueError("ЗначениеВСтрокуВнутр: недопустимое состояние элемента списка значений")
        if getattr(item, '_decoded_standalone', False):
            identifier = item._id
        else:
            owner = item._owner_ref()
            identifier = (item._id if not item._detached and owner is not None
                          and owner._by_id.get(item._id) is item else -1)
        self.emit('{')
        self.string(item.presentation)
        self.emit(',' + ('1' if item.check else '0') + ',\n')
        self.value(item.value, depth + 1)
        self.emit(',\n' + _LIST_PICTURE + ',' + str(identifier) + ',0,""}')

    def table(self, table, depth):
        # Canonical snapshot layout established by table.codec.empty/table.
        # The owner's table.indexes.codec.table adds ordered index definitions.
        # Historic column/row IDs and undocumented flags are not synthesized.
        columns, rows = table.columns.items, table.rows
        nc, nr = len(columns), len(rows)
        self.nodes += nc + nr
        if self.nodes > _MAX_NODES or nc * nr > _MAX_NODES:
            raise _resource("ЗначениеВСтрокуВнутр")
        self.emit('{9,\n{' + str(nc))
        for index, column in enumerate(columns):
            description = column.value_type
            if type(description) is not BSLTypeDescription:
                raise TypeError("ЗначениеВСтрокуВнутр: ожидается ОписаниеТипов колонки")
            width = column.width
            if (type(width) is not Decimal or not width.is_finite()
                    or not 0 <= width < 2 ** 32 or width != width.to_integral_value()):
                raise ValueError("ЗначениеВСтрокуВнутр: недопустимая ширина колонки")
            _require_representable_description(description)
            self.emit(',\n{' + str(index) + ',')
            self.string(column.name)
            self.emit(',\n{"Pattern"')
            for kind in description.types:
                self.emit(',\n' + _pattern_entry(kind, description))
            self.emit('\n}' if description.types else '}')
            self.emit(',')
            self.string(column.title)
            self.emit(',' + str(int(width)) + '}')
        self.emit('\n}' if nc else '}')
        self.emit(',\n{2,' + str(nc))
        for index in range(nc):
            self.emit(',' + str(index) + ',' + str(index))
        self.emit(',\n{1,' + str(nr))
        for index, row in enumerate(rows):
            self.emit(',\n{2,' + str(index) + ',' + str(nc))
            for column in columns:
                self.emit(',\n')
                cell = row.cells[column]
                if not _table_cell_matches(column.value_type, cell):
                    raise ValueError("ЗначениеВСтрокуВнутр: значение ячейки не соответствует типу колонки")
                self.value(cell, depth + 1)
            self.emit(',0}')
        self.emit('\n}' if nr else '}')
        self.emit(',' + str(nc - 1) + ',' + str(nr - 1) + '},\n')
        self.table_indexes(table)
        self.emit('\n}')

    def table_indexes(self, table):
        collection = table.indexes
        if (type(collection) is not BSLCollectionIndexes or collection.table is not table
                or type(collection.items) is not list):
            raise ValueError("ЗначениеВСтрокуВнутр: недопустимая коллекция индексов")
        count = len(collection.items)
        self.nodes += count
        if self.nodes > _MAX_NODES:
            raise _resource("ЗначениеВСтрокуВнутр")
        positions = {id(column): position for position, column in enumerate(table.columns.items)}
        self.emit('{0,' + str(count))
        for index in collection.items:
            if (type(index) is not BSLCollectionIndex or index.table is not table
                    or index._deleted or type(index.columns) is not list):
                raise ValueError("ЗначениеВСтрокуВнутр: недопустимый индекс таблицы")
            self.nodes += len(index.columns)
            if self.nodes > _MAX_NODES:
                raise _resource("ЗначениеВСтрокуВнутр")
            self.emit(',\n{0,' + str(len(index.columns)))
            for column in index.columns:
                if (type(column) is not BSLValueTableColumn or column.table is not table
                        or column._deleted or id(column) not in positions):
                    raise ValueError("ЗначениеВСтрокуВнутр: недопустимая колонка индекса")
                self.emit(',' + str(positions[id(column)]))
            self.emit('}')
        self.emit('\n}' if count else '}')

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
        if self.tokens > _MAX_NODES * _MAX_TOKENS_PER_NODE or depth > _MAX_DEPTH * 3 + 3:
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

    def qualifier_count(self, token):
        if type(token) is not _Atom or _COUNT.fullmatch(token.text) is None:
            self.fail()
        # Supported qualifier constructors cap counts at one million; reject
        # oversize spelling before integer/Decimal materialization.
        if len(token.text) > 7:
            raise _resource("ЗначениеИзСтрокиВнутр")
        return Decimal(token.text)

    def pattern(self, body):
        # Qualified N/S/D shapes come from the owner's receiver supplement.
        # Duplicate types, noncanonical order and binary entries are outside
        # this defensive inverse subset; these are not native rejection claims.
        if (not body or len(body) > 5 or type(body[0]) is not str
                or body[0] != 'Pattern'):
            self.fail()
        kinds = []
        n, s, d = BSLNumberQualifiers(), BSLStringQualifiers(), BSLDateQualifiers()
        for entry in body[1:]:
            if (type(entry) is not list or not entry or type(entry[0]) is not str
                    or entry[0] not in _PATTERN_TYPES):
                self.fail()
            kind = _PATTERN_TYPES[entry[0]]
            kinds.append(kind)
            if len(entry) == 1:
                continue
            if kind is BSLType.NUMBER and len(entry) == 4:
                digits, fraction = self.qualifier_count(entry[1]), self.qualifier_count(entry[2])
                if type(entry[3]) is not _Atom or entry[3].text not in ('0', '1'):
                    self.fail()
                sign = _ENUM_MEMBERS[BSLType.ALLOWED_SIGN][entry[3].text]
                try:
                    n = BSLNumberQualifiers(digits, fraction, sign)
                except (TypeError, ValueError):
                    self.fail()
                if (n.digits != digits or n.fraction_digits != fraction
                        or (not digits and sign is BSLAllowedSign.ANY)):
                    self.fail()
            elif kind is BSLType.STRING and len(entry) == 3:
                length = self.qualifier_count(entry[1])
                if type(entry[2]) is not _Atom or entry[2].text not in ('0', '1') or not length:
                    self.fail()
                allowed = _ENUM_MEMBERS[BSLType.ALLOWED_LENGTH][entry[2].text]
                try:
                    s = BSLStringQualifiers(length, allowed)
                except (TypeError, ValueError):
                    self.fail()
            elif kind is BSLType.DATE and len(entry) == 2:
                if type(entry[1]) is not str or entry[1] not in ('D', 'T'):
                    self.fail()
                d = BSLDateQualifiers(BSLDateFractions.DATE if entry[1] == 'D'
                                      else BSLDateFractions.TIME)
            else:
                self.fail()
        source = BSLArray()
        source.items = kinds
        try:
            result = BSLTypeDescription(source, n, s, d)
        except (TypeError, ValueError):
            self.fail()
        if result.types != tuple(kinds):
            self.fail()
        return result

    def table_count(self, token):
        if type(token) is not _Atom or _COUNT.fullmatch(token.text) is None:
            self.fail()
        if len(token.text) > 5 or int(token.text) > _MAX_NODES:
            raise _resource("ЗначениеИзСтрокиВнутр")
        return int(token.text)

    def list_identifier(self, token):
        if token == _Atom('-1'):
            return -1
        if type(token) is not _Atom or _COUNT.fullmatch(token.text) is None:
            self.fail()
        if len(token.text) > 10 or int(token.text) >= 2 ** 32:
            raise _resource("ЗначениеИзСтрокиВнутр")
        return int(token.text)

    def value_list_item(self, body, depth, owner=None):
        # Only the observed default picture block is supported. This is not a
        # public Picture codec and unknown flags are never silently discarded.
        picture = [_Atom('4'), _Atom('0'), [_Atom('0')], '',
                   _Atom('-1'), _Atom('-1'), _Atom('0'), _Atom('0'), '']
        if (len(body) != 7 or type(body[0]) is not str
                or body[1] not in (_Atom('0'), _Atom('1'))
                or body[3] != picture or body[5:] != [_Atom('0'), '']):
            self.fail()
        identifier = self.list_identifier(body[4])
        value = self.value(body[2], depth + 1)
        if owner is None:
            return BSLValueListItem._from_stream(identifier, value, body[0], body[1] == _Atom('1'))
        if identifier < 0 or identifier in owner._by_id or identifier >= owner._next_id:
            self.fail()
        item = BSLValueListItem(owner, identifier, value, body[0], body[1] == _Atom('1'))
        owner.items.append(item)
        owner._by_id[identifier] = item
        return item

    def value_list(self, body, depth):
        if (len(body) != 8 or body[:4] != [_Atom('6'), _Atom(_LIST_ENTRY_ID), _Atom('0'), _Atom('0')]
                or type(body[4]) is not list or not body[4]
                or body[5:7] != [['Pattern'], _Atom('0')]):
            self.fail()
        entries = body[4]
        count = self.table_count(entries[0])
        if len(entries) != count + 1:
            self.fail()
        self.nodes += count
        if self.nodes > _MAX_NODES:
            raise _resource("ЗначениеИзСтрокиВнутр")
        result = BSLValueList()
        result._next_id = self.list_identifier(body[7]) + 1
        for entry in entries[1:]:
            if (type(entry) is not list or len(entry) != 2
                    or entry[0] != _Atom(_LIST_ENTRY_ID) or type(entry[1]) is not list):
                self.fail()
            self.value_list_item(entry[1], depth + 1, result)
        return result

    def table(self, body, depth):
        # Deliberately strict inverse subset of the observed version-9 stream.
        # Unknown versions, noncanonical reference IDs and flags are not guessed.
        if (len(body) != 4 or body[0] != _Atom('9')
                or type(body[1]) is not list or not body[1]
                or type(body[2]) is not list or type(body[3]) is not list):
            self.fail()
        definitions, data = body[1], body[2]
        nc = self.table_count(definitions[0])
        if len(definitions) != nc + 1 or len(data) != 2 * nc + 5:
            self.fail()
        if data[:2] != [_Atom('2'), _Atom(str(nc))]:
            self.fail()
        for index in range(nc):
            if data[2 + index * 2:4 + index * 2] != [_Atom(str(index))] * 2:
                self.fail()
        rows = data[-3]
        if type(rows) is not list or len(rows) < 2 or rows[0] != _Atom('1'):
            self.fail()
        nr = self.table_count(rows[1])
        if len(rows) != nr + 2 or data[-2:] != [_Atom(str(nc - 1)), _Atom(str(nr - 1))]:
            self.fail()
        self.nodes += nc + nr
        if self.nodes > _MAX_NODES or nc * nr > _MAX_NODES:
            raise _resource("ЗначениеИзСтрокиВнутр")
        result = BSLValueTable()
        for index, entry in enumerate(definitions[1:]):
            if (type(entry) is not list or len(entry) != 5
                    or entry[0] != _Atom(str(index)) or type(entry[1]) is not str
                    or type(entry[2]) is not list or type(entry[3]) is not str):
                self.fail()
            description = self.pattern(entry[2])
            width = self.number(entry[4])
            if not 0 <= width < 2 ** 32 or width != width.to_integral_value():
                self.fail()
            try:
                column = result.columns.add(entry[1], description, entry[3], width)
            except (TypeError, ValueError):
                self.fail()
            if column.name != entry[1] or column.title != entry[3] or column.width != width:
                self.fail()
        for index, entry in enumerate(rows[2:]):
            if (type(entry) is not list or len(entry) != nc + 4
                    or entry[:3] != [_Atom('2'), _Atom(str(index)), _Atom(str(nc))]
                    or entry[-1] != _Atom('0')):
                self.fail()
            row = result.add()
            for column, cell in zip(result.columns.items, entry[3:-1]):
                value = self.value(cell, depth + 1)
                try:
                    matches = _table_cell_matches(column.value_type, value)
                except (TypeError, ValueError):
                    self.fail()
                if not matches:
                    self.fail()
                row.cells[column] = value
        self.table_indexes(result, body[3])
        return result

    def table_indexes(self, table, body):
        if len(body) < 2 or body[0] != _Atom('0'):
            self.fail()
        count = self.table_count(body[1])
        if len(body) != count + 2:
            self.fail()
        self.nodes += count
        if self.nodes > _MAX_NODES:
            raise _resource("ЗначениеИзСтрокиВнутр")
        columns = table.columns.items
        for entry in body[2:]:
            if type(entry) is not list or len(entry) < 2 or entry[0] != _Atom('0'):
                self.fail()
            size = self.table_count(entry[1])
            if len(entry) != size + 2:
                self.fail()
            self.nodes += size
            if self.nodes > _MAX_NODES:
                raise _resource("ЗначениеИзСтрокиВнутр")
            selected = []
            for token in entry[2:]:
                position = self.table_count(token)
                if position >= len(columns):
                    self.fail()
                selected.append(columns[position])
            try:
                table.indexes._add_columns(selected)
            except (TypeError, ValueError, IndexError):
                self.fail()

    def value(self, group, depth=0):
        self.nodes += 1
        if self.nodes > _MAX_NODES or depth > _MAX_DEPTH:
            raise _resource("ЗначениеИзСтрокиВнутр")
        if type(group) is not list or not group or type(group[0]) is not str:
            self.fail()
        tag = group[0]
        if tag == 'U' and len(group) == 1:
            return None
        if tag == 'L' and len(group) == 1:
            return NULL
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
                and group[1].text in _OPAQUE_IDS):
            return None
        if tag not in ('T', '#') or len(group) != (2 if tag == 'T' else 3):
            self.fail()
        if type(group[1]) is not _Atom or group[1].text not in _TYPES_BY_ID:
            self.fail()
        kind = _TYPES_BY_ID[group[1].text]
        if tag == 'T':
            return kind
        body = group[2]
        if kind in _ENUM_MEMBERS:
            if type(body) is not _Atom or body.text not in _ENUM_MEMBERS[kind]:
                self.fail()
            return _ENUM_MEMBERS[kind][body.text]
        if type(body) is not list:
            self.fail()
        if kind is BSLType.TYPE_DESCRIPTION:
            return self.pattern(body)
        if kind is BSLType.VALUE_LIST:
            return self.value_list(body, depth)
        if kind is BSLType.VALUE_LIST_ITEM:
            return self.value_list_item(body, depth)
        if kind is BSLType.VALUE_TABLE:
            return self.table(body, depth)
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
