"""Finite immutable system namespaces for the direct backend."""
from types import MappingProxyType

from .chars import CHARS
from .search_directions import SEARCH_DIRECTIONS
from .sort_directions import SORT_DIRECTIONS
from .numeric.round_modes import ROUND_MODES
from .type_qualifiers import ALLOWED_SIGNS, ALLOWED_LENGTHS, DATE_FRACTIONS
from .error_info import ERROR_CATEGORIES
from .json_processing import JSON_LINE_BREAKS, JSON_VALUE_TYPES

NAMES = MappingProxyType({
    alias: value
    for aliases, value in (
        (("chars", "символы"), CHARS),
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
