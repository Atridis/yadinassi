"""Finite immutable system namespaces for the direct backend."""
from types import MappingProxyType
from yadinassi.formats.xml.dom_nodes import DOM_NODE_TYPES
from yadinassi.formats.xml.xml_processing import XML_STRING_PROCESSING
from yadinassi.formats.xml.xml_io import XML_NODE_TYPES, XML_SPACES, XML_VALIDATION_TYPES

from yadinassi.http.http_client import BYTE_ORDER_MARK_USE
from yadinassi.streams.binary_streams import POSITIONS_IN_STREAM, BYTE_ORDERS, FILE_OPEN_MODES, FILE_ACCESSES
from yadinassi.streams.file_io import TEXT_ENCODINGS
from yadinassi.streams.data_hashing import HASH_FUNCTIONS
from yadinassi.text.chars import CHARS
from yadinassi.collections.search_directions import BSLSearchDirection, SEARCH_DIRECTIONS
from yadinassi.collections.sort_directions import BSLSortDirection, SORT_DIRECTIONS
from yadinassi.numeric.round_modes import BSLRoundMode, ROUND_MODES
from yadinassi.types.type_qualifiers import ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS
from yadinassi.types.error_info import ERROR_CATEGORIES
from yadinassi.formats.json.json_dates import JSON_DATE_FORMATS, JSON_DATE_WRITING_VARIANTS
from yadinassi.formats.json.json_processing import JSON_LINE_BREAKS, JSON_VALUE_TYPES

XML_CLEANUP_ALIASES = ("xmlstringprocessing", "обработкастрокиxml")

NAMES = MappingProxyType({
    alias: value
    for aliases, value in (
        (("domnodetype", "типузлаdom"), DOM_NODE_TYPES),
        (("xmlnodetype", "типузлаxml"), XML_NODE_TYPES),
        (("xmlspace", "пробельныесимволыxml"), XML_SPACES),
        (XML_CLEANUP_ALIASES, XML_STRING_PROCESSING),
        (("xmlvalidationtype", "типпроверкиxml"), XML_VALIDATION_TYPES),
        (("chars", "символы"), CHARS),
        (("byteordermarkuse", "использованиеbyteordermark"), BYTE_ORDER_MARK_USE),
        (("positioninstream", "позициявпотоке"), POSITIONS_IN_STREAM),
        (("textencoding", "кодировкатекста"), TEXT_ENCODINGS),
        (("byteorder", "порядокбайтов"), BYTE_ORDERS),
        (("fileopenmode", "режимоткрытияфайла"), FILE_OPEN_MODES),
        (("fileaccess", "доступкфайлу"), FILE_ACCESSES),
        (("hashfunction", "хешфункция"), HASH_FUNCTIONS),
        (("searchdirection", "направлениепоиска"), SEARCH_DIRECTIONS),
        (("sortdirection", "направлениесортировки"), SORT_DIRECTIONS),
        (("roundmode", "режимокругления"), ROUND_MODES),
        (("allowedsign", "допустимыйзнак"), ALLOWED_SIGNS),
        (("allowedlength", "допустимаядлина"), ALLOWED_LENGTHS),
        (("datefractions", "частидаты"), DATE_FRACTIONS),
        (("errorcategory", "категорияошибки"), ERROR_CATEGORIES),
        (("jsonlinebreak", "переносстрокjson"), JSON_LINE_BREAKS),
        (("jsonvaluetype", "типзначенияjson"), JSON_VALUE_TYPES),
        (("jsondateformat", "форматдатыjson"), JSON_DATE_FORMATS),
        (("jsondatewritingvariant", "вариантзаписидатыjson"), JSON_DATE_WRITING_VARIANTS),
    )
    for alias in aliases
})
VALUES = tuple(NAMES.values())
# VALUES retains these immutable singletons, so their identities cannot be reused.
VALUE_IDS = frozenset(map(id, VALUES))
ITERABLES = (SEARCH_DIRECTIONS, SORT_DIRECTIONS, ROUND_MODES)

# Immutable namespace receivers and their actual scalar members. Keep the
# instances alive: types, equal payloads and freshly forged instances confer no
# authority (including authority to dispatch a Python protocol).
ITERABLE_IDS = frozenset(map(id, ITERABLES))
ITERATION_ENUM_VALUES = (*BSLSearchDirection, *BSLSortDirection, *BSLRoundMode)
ITERATION_ENUM_VALUE_IDS = frozenset(map(id, ITERATION_ENUM_VALUES))
