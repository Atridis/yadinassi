"""Bounded ValueList sorting from owner checkpoint 3172627, Windows 8.3.27.

Value and Presentation do NOT share a comparison relation: values ignore case
and trailing ASCII spaces, while presentations retain both. The pinned UCA6
data fits the two observed string/Unicode datasets in both modes; that is not a
claim about the native algorithm or arbitrary locales/Unicode. Other string
comparison APIs are unchanged.

Supported families are scalars, empty Array/Structure, Type(String)/Type(Number),
and SortDirection. Cross-family ordering and other object/Type identities were
not observed and remain unsupported. Strings accept ASCII alphanumerics, space,
hyphen, Russian letters and á/Á, plus the observed Unicode special strings only
as standalone strings. Budgets and active-iteration guards are local policy.
"""

from decimal import Decimal
import unicodedata

from . import value_table_collation as collation
from .dates import BSLDate
from .sort_directions import BSLSortDirection
from .structures import BSLStructure
from .values import BSLArray, BSLType, NULL


_MAX_SORT_ITEMS = 100_000
_MAX_SORT_TEXT = 1_000_000
_MAX_KEY_WEIGHTS = 8_000_000
_MAX_NUMBER_DIGITS = 4096
_ALPHABET = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -áÁ"
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
_SPECIAL = frozenset(("😀", "😁", "\U00010000", "\ue000", "é", "e\u0301", "ß", "İ"))


def _unsupported(message):
    raise ValueError(f"Сортировка списка: {message} пока не поддерживается в Yadinassi")


def _budget(message):
    raise ValueError(f"Сортировка списка: превышен предел {message} Yadinassi")


def _string_key(value, budget, *, by_presentation):
    # Do not call host string coercion, comparison or normalization hooks.
    if type(value) is not str:
        _unsupported("этот тип строкового ключа")
    if len(value) > collation.MAX_STRING_LENGTH:
        _budget("длины строки")
    budget[0] += len(value)
    if budget[0] > _MAX_SORT_TEXT:
        _budget("текста")
    if value not in _SPECIAL and any(char not in _ALPHABET for char in value):
        _unsupported("строка вне подтвержденного набора сравнения")
    if not by_presentation:
        value = value.rstrip(" ")
    normalized = unicodedata.normalize("NFD", value)
    if len(normalized) > collation.MAX_NORMALIZED_LENGTH:
        _budget("нормализации")
    collator = collation._collator()
    key = collator.sort_key_from_collation_elements(collator.collation_elements(normalized))
    if not by_presentation:
        second_separator = key.index(0, key.index(0) + 1)
        key = key[:second_separator]
    budget[1] += len(key)
    if budget[1] > _MAX_KEY_WEIGHTS:
        _budget("ключей")
    return key


def _value_key(value, budget):
    """Return an observed comparison family and an inert, total-order key."""
    kind = type(value)
    if value is None:
        return "scalar", (0, 0)
    if value is NULL:
        return "scalar", (1, 0)
    if kind is bool:
        return "scalar", (2, value)
    if kind is Decimal:
        if not value.is_finite():
            raise ValueError("Сортировка списка: ожидается конечное число")
        if (len(value.as_tuple().digits) > _MAX_NUMBER_DIGITS
                or abs(value.adjusted()) > _MAX_NUMBER_DIGITS):
            _budget("числа")
        return "scalar", (3, value)
    if kind is str:
        return "scalar", (4, _string_key(value, budget, by_presentation=False))
    if kind is BSLDate:
        return "scalar", (5, value.require_known().ticks)
    # Opaque object comparison does not traverse contents, stringify objects,
    # compare identity addresses or invoke their equality/hash methods.
    if kind is BSLArray:
        if type(value.items) is not list or value.items:
            _unsupported("сортировка непустого массива")
        return "object", (0, 0)
    if kind is BSLStructure:
        if type(value._items) is not dict or value._items:
            _unsupported("сортировка непустой структуры")
        return "object", (1, 0)
    if kind is BSLType:
        if value is BSLType.STRING:
            return "type", (0, 0)
        if value is BSLType.NUMBER:
            return "type", (1, 0)
        _unsupported("порядок этого значения Тип")
    if kind is BSLSortDirection:
        return "sort-direction", (0 if value is BSLSortDirection.ASC else 1, 0)
    _unsupported("этот тип ключа")


def sort_list(owner, direction=None, *, by_presentation=False):
    """Validate every key, then commit a stable item-identity-preserving sort."""
    from .value_lists import BSLValueListItem

    if direction is not None and type(direction) is not BSLSortDirection:
        raise TypeError("Сортировка списка: ожидается НаправлениеСортировки")
    if len(owner.items) > _MAX_SORT_ITEMS:
        _budget("элементов")
    budget = [0, 0]
    family = None
    keyed = []
    for item in owner.items:
        if type(item) is not BSLValueListItem:
            _unsupported("этот тип элемента")
        if by_presentation:
            key = _string_key(item.presentation, budget, by_presentation=True)
        else:
            item_family, key = _value_key(item.value, budget)
            if family is not None and family != item_family:
                _unsupported("смешанный порядок семейств значений")
            family = item_family
        keyed.append((key, item))
    # reverse=True preserves equal-key order in both directions. Never reverse
    # the completed ascending result, which would reverse duplicate items.
    keyed.sort(key=lambda pair: pair[0], reverse=direction is BSLSortDirection.DESC)
    owner.items[:] = [item for _, item in keyed]
    owner._revision += 1
