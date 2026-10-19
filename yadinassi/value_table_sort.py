"""Bounded native-backed ValueTable.Sort (Windows 8.3.27.2342, ru_RU).

The 24 owner observations establish stable sorting, scalar type order and the
Array/Structure/Type object family. Other object codes and mixed scalar/object
order remain deferred. A separately pinned official UCA6 DUCET matches both
locale checkpoints; this is an empirical fit, not proof of the native algorithm.
The accepted alphabet remains bounded to ASCII alphanumerics, Russian letters,
á, ASCII space, ! and hyphen; trailing ASCII spaces are insignificant. Observed
😀, 😁, U+10000 and U+E000 are accepted as standalone strings only. Other scripts,
punctuation, controls, supplementary characters and special-character mixtures,
as well as CompareValues instances, remain deferred. Budgets are local limits.
"""
from decimal import Decimal

from .value_table_collation import caseless_string_key, MAX_STRING_LENGTH
from .dates import BSLDate
from .structures import BSLStructure
from .values import BSLArray, BSLType, NULL
from .value_tables import _text

_MAX_SORT_CELLS = 1_000_000
_MAX_SORT_TOKENS = 16_384
_MAX_SORT_TEXT = 1_000_000
_MAX_KEY_WEIGHTS = 8_000_000
_ALLOWED = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
                     '0123456789 !-áÁ'
                     'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'
                     'абвгдеёжзийклмнопрстуфхцчшщъыьэюя')

_SPECIAL = frozenset(('😀', '😁', '\U00010000', '\ue000'))

def _string_key(value, budget):
    if len(value) > MAX_STRING_LENGTH:
        raise ValueError('Сортировка: превышен предел длины строки Yadinassi')
    budget[0] += len(value)
    if budget[0] > _MAX_SORT_TEXT:
        raise ValueError('Сортировка: превышен предел текста Yadinassi')
    value = value.rstrip(' ')
    if value not in _SPECIAL and any(char not in _ALLOWED for char in value):
        raise ValueError('Сортировка: строка вне подтвержденного набора сравнения Yadinassi')
    result = caseless_string_key(value)
    budget[1] += len(result)
    if budget[1] > _MAX_KEY_WEIGHTS:
        raise ValueError('Сортировка: превышен предел ключей Yadinassi')
    return result


def _value_key(value, budget):
    kind = type(value)
    if value is None:
        return False, (0, 0)
    if value is NULL:
        return False, (1, 0)
    if kind is bool:
        return False, (2, value)
    if kind is Decimal:
        if not value.is_finite():
            raise ValueError('Сортировка: ожидается конечное число')
        if len(value.as_tuple().digits) > 4096 or abs(value.adjusted()) > 4096:
            raise ValueError('Сортировка: число вне ресурсных границ Yadinassi')
        return False, (3, value)
    if kind is str:
        return False, (4, _string_key(value, budget))
    if kind is BSLDate:
        return False, (5, value.require_known().ticks)
    if kind is BSLArray:
        return True, (0, 0)
    if kind is BSLStructure:
        return True, (1, 0)
    if kind is BSLType:
        return True, (2, _string_key(str(value), budget))
    raise ValueError('Сортировка: тип ключа пока не поддерживается в Yadinassi')


def sort_table(table, columns, comparator=None):
    """Validate all keys before committing a stable, identity-preserving order."""
    columns = _text(columns)
    if len(columns) > _MAX_SORT_TEXT:
        raise ValueError("Сортировка: превышен предел списка колонок Yadinassi")
    if comparator is not None:
        raise TypeError('Сортировка: объект сравнения пока не поддерживается в Yadinassi')
    # Resolve names once: repeated tokens must not rescan the whole schema.
    # The text cap bounds allocation; the token cap also bounds empty chunks.
    by_name = {column.name.casefold(): column for column in table.columns.items}
    specs = []
    seen = set()
    for token_index, chunk in enumerate(columns.split(',')):
        if token_index >= _MAX_SORT_TOKENS:
            raise ValueError('Сортировка: превышен предел элементов списка Yadinassi')
        parts = chunk.strip(' ').split(None, 2)
        if not parts:
            continue
        if len(parts) > 2:
            raise ValueError('Сортировка: неподдерживаемый формат порядка')
        name = parts[0].casefold()
        if name in seen:
            continue
        column = by_name.get(name)
        if column is None:
            raise ValueError(f'Колонка не найдена: {parts[0]}')
        specs.append((column, len(parts) == 2 and parts[1].casefold() in ('desc', 'убыв')))
        seen.add(name)
    if not specs:
        raise ValueError('Сортировка: не указаны колонки')
    if len(table.rows) * len(specs) > _MAX_SORT_CELLS:
        raise ValueError('Сортировка: превышен предел ячеек Yadinassi')
    budget = [0, 0]
    keys = []
    for column, descending in specs:
        family = None
        column_keys = {}
        for row in table.rows:
            object_family, key = _value_key(row.cells[column], budget)
            if family is not None and family != object_family:
                raise ValueError('Сортировка: смешанный порядок простых и объектных типов пока не поддерживается')
            family = object_family
            column_keys[row] = key
        keys.append((column_keys, descending))
    rows = list(table.rows)
    for column_keys, descending in reversed(keys):
        rows.sort(key=column_keys.__getitem__, reverse=descending)
    table.rows[:] = rows
