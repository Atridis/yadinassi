"""Finite immutable system namespaces for the direct backend."""
from types import MappingProxyType

from yadinassi.http.http_client import BYTE_ORDER_MARK_USE
from yadinassi.streams.binary_streams import POSITIONS_IN_STREAM
from yadinassi.text.chars import CHARS
from yadinassi.collections.search_directions import SEARCH_DIRECTIONS
from yadinassi.collections.sort_directions import SORT_DIRECTIONS
from yadinassi.numeric.round_modes import ROUND_MODES
from yadinassi.types.type_qualifiers import ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS
from yadinassi.types.error_info import ERROR_CATEGORIES
from yadinassi.formats.json.json_processing import JSON_LINE_BREAKS, JSON_VALUE_TYPES

NAMES = MappingProxyType({
    alias: value
    for aliases, value in (
        (("chars", "символы"), CHARS),
        (("byteordermarkuse", "использованиеbyteordermark"), BYTE_ORDER_MARK_USE),
        (("positioninstream", "позициявпотоке"), POSITIONS_IN_STREAM),
        (("searchdirection", "направлениепоиска"), SEARCH_DIRECTIONS),
        (("sortdirection", "направлениесортировки"), SORT_DIRECTIONS),
        (("roundmode", "режимокругления"), ROUND_MODES),
        (("allowedsign", "допустимыйзнак"), ALLOWED_SIGNS),
        (("allowedlength", "допустимаядлина"), ALLOWED_LENGTHS),
        (("datefractions", "частидаты"), DATE_FRACTIONS),
        (("errorcategory", "категорияошибки"), ERROR_CATEGORIES),
        (("jsonlinebreak", "переносстрокjson"), JSON_LINE_BREAKS),
        (("jsonvaluetype", "типзначенияjson"), JSON_VALUE_TYPES),
    )
    for alias in aliases
})
VALUES = tuple(NAMES.values())
# VALUES retains these immutable singletons, so their identities cannot be reused.
VALUE_IDS = frozenset(map(id, VALUES))
ITERABLES = (SEARCH_DIRECTIONS, SORT_DIRECTIONS, ROUND_MODES)
