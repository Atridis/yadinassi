"""Bounded numeric Rows.Sort for the explicit Linux 8.3.27.1508 target.

The 21-case native Tree checkpoint establishes receiver/recursive ordering,
identity preservation, the measured errors and two 18-row unstable tie orders.
The shared introsort primitive reproduces those orders; this is an empirical
model, not a claim about native internals or unobserved sizes. Windows Tree
ordering, nonnumeric keys and CompareValues instances remain deferred.
Resource/graph validation and preflight guarantees below are local policy.
"""
from decimal import Context, Decimal, DecimalException, InvalidOperation, Overflow, Rounded

from .native_targets import LINUX_8_3_27_1508, current_native_target
from .native_target_sort import introsort

_MAX_SORT_ROWS = 100_000
_MAX_SORT_COLUMNS = 4096
_MAX_SORT_CELLS = 1_000_000
_MAX_SORT_TEXT = 1_000_000
_MAX_SORT_TOKENS = 4096
_MAX_SORT_WORK = 8_000_000
_MAX_SORT_NUMBER_DIGITS = 4096
_MAX_SORT_NUMBER_EXPONENT = 4096


def _invalid():
    raise ValueError('Сортировка дерева: неверная структура или превышен предел Yadinassi')


class _Budget:
    def __init__(self):
        self.remaining = _MAX_SORT_WORK

    def charge(self, units):
        if units > self.remaining:
            _invalid()
        self.remaining -= units


def _numeric(value, budget):
    # Exact types only: no conversion/equality/order hooks from host objects.
    if type(value) is not Decimal:
        raise TypeError('Сортировка дерева: поддерживаются только числовые ключи')
    if not value.is_finite() or abs(value.adjusted()) > _MAX_SORT_NUMBER_EXPONENT:
        raise ValueError('Сортировка дерева: число вне подтвержденных ресурсных границ')
    # Bound coefficient size before allocating its tuple, including huge zero
    # tails. Never use the caller's Decimal context or modify the actual key.
    budget.charge(_MAX_SORT_NUMBER_DIGITS)
    try:
        context = Context(prec=_MAX_SORT_NUMBER_DIGITS, traps=[Rounded, InvalidOperation, Overflow])
        context.scaleb(value, -value.adjusted())
    except DecimalException:
        raise ValueError('Сортировка дерева: превышен предел разрядов Yadinassi') from None
    digits = len(value.as_tuple().digits)
    budget.remaining += _MAX_SORT_NUMBER_DIGITS - digits
    return value, digits


def sort_rows(receiver, selector, recursive=False, comparison=None):
    from .value_trees import (BSLValueTree, BSLValueTreeRow, BSLValueTreeRowCollection,
                             BSLValueTreeColumn, BSLValueTreeColumnCollection, _MAX_DEPTH)
    if current_native_target() != LINUX_8_3_27_1508:
        raise ValueError('Сортировка дерева: Windows-цель пока не измерена')
    if type(selector) is not str:
        raise TypeError('Сортировка дерева: ожидается строка колонок')
    if type(recursive) is not bool:
        raise TypeError('Сортировка дерева: ожидается Булево рекурсии')
    if comparison is not None:
        raise TypeError('Сортировка дерева: объект сравнения пока не поддерживается')
    if len(selector) > _MAX_SORT_TEXT or selector.count(',') >= _MAX_SORT_TOKENS:
        _invalid()
    if type(receiver) is not BSLValueTreeRowCollection or type(receiver.tree) is not BSLValueTree:
        _invalid()
    tree = receiver.tree
    if (type(tree.columns) is not BSLValueTreeColumnCollection or tree.columns.table is not tree
            or type(tree.columns.items) is not list or type(tree._all_rows) is not dict
            or len(tree._all_rows) > _MAX_SORT_ROWS or len(tree.columns.items) > _MAX_SORT_COLUMNS
            or type(tree.rows) is not BSLValueTreeRowCollection or tree.rows.tree is not tree
            or tree.rows.parent is not None):
        _invalid()
    budget = _Budget()
    budget.charge(len(tree._all_rows))
    registered = set()
    for row in tree._all_rows:
        if type(row) is not BSLValueTreeRow:
            _invalid()
        registered.add(id(row))
    # Verify a child receiver's ancestry without recursive host calls.
    ancestor = receiver
    depth = 0
    ancestors = []
    while ancestor is not tree.rows:
        parent = ancestor.parent
        if (type(parent) is not BSLValueTreeRow or parent.tree is not tree or parent._deleted is not False
                or parent.rows is not ancestor or id(parent) not in registered
                or type(parent.collection) is not BSLValueTreeRowCollection
                or parent.collection.tree is not tree or parent.parent is not parent.collection.parent):
            _invalid()
        siblings = parent.collection.items
        if type(siblings) is not list or len(siblings) > _MAX_SORT_ROWS:
            _invalid()
        budget.charge(len(siblings))
        if not any(candidate is parent for candidate in siblings):
            _invalid()
        depth += 1
        if depth > _MAX_DEPTH or type(parent.depth) is not int or parent.depth < 0:
            _invalid()
        ancestors.append(parent)
        ancestor = parent.collection
    for expected, parent in enumerate(reversed(ancestors)):
        if parent.depth != expected:
            _invalid()
    receiver._live()
    budget.charge(len(selector))
    schema = {}
    text_size = len(selector)
    for column in tree.columns.items:
        if (type(column) is not BSLValueTreeColumn or column.table is not tree
                or column._deleted is not False or type(column.name) is not str):
            _invalid()
        text_size += len(column.name)
        if text_size > _MAX_SORT_TEXT:
            _invalid()
        budget.charge(len(column.name))
        name = column.name.casefold()
        budget.charge(len(name))
        if name in schema:
            _invalid()
        schema[name] = column
    specs = []
    names = set()
    for token in selector.split(','):
        parts = token.split()
        if not 1 <= len(parts) <= 2:
            raise ValueError('Сортировка дерева: неподдерживаемая строка порядка')
        name = parts[0].casefold()
        if name in names:
            raise ValueError('Сортировка дерева: повторная колонка пока не измерена')
        column = schema.get(name)
        if column is None:
            raise ValueError('Сортировка дерева: колонка не найдена')
        direction = parts[1].casefold() if len(parts) == 2 else 'asc'
        if direction not in ('asc', 'desc', 'возр', 'убыв'):
            raise ValueError('Сортировка дерева: направление пока не измерено')
        names.add(name)
        specs.append((column, direction in ('desc', 'убыв')))
    column_ids = {id(column) for column in tree.columns.items}
    plans = []
    pending = [(receiver, depth)]
    visited = set()
    total_cells = 0
    while pending:
        collection, expected_depth = pending.pop()
        if (type(collection) is not BSLValueTreeRowCollection or collection.tree is not tree
                or type(collection.items) is not list or len(collection.items) > _MAX_SORT_ROWS
                or expected_depth > _MAX_DEPTH):
            _invalid()
        rows = list(collection.items)
        keys = {}
        for row in rows:
            if (type(row) is not BSLValueTreeRow or row.tree is not tree or row.collection is not collection
                    or row.parent is not collection.parent or row._deleted is not False or id(row) not in registered
                    or type(row.depth) is not int or row.depth != expected_depth
                    or type(row.cells) is not dict or row in visited):
                _invalid()
            visited.add(row)
            total_cells += len(row.cells)
            if len(visited) > _MAX_SORT_ROWS or total_cells > _MAX_SORT_CELLS:
                _invalid()
            budget.charge(1 + len(row.cells))
            if len(row.cells) != len(column_ids):
                _invalid()
            # Inspect key types/identity before dict lookup: a foreign key with
            # a colliding hash must never run its equality hook.
            for column in row.cells:
                if type(column) is not BSLValueTreeColumn or id(column) not in column_ids:
                    _invalid()
            keys[row] = tuple(_numeric(row.cells[column], budget) for column, _ in specs)
            if recursive:
                if (type(row.rows) is not BSLValueTreeRowCollection or row.rows.parent is not row
                        or row.rows.tree is not tree or type(row.rows.items) is not list):
                    _invalid()
                if row.rows.items:
                    pending.append((row.rows, expected_depth + 1))
        plans.append((collection, rows, keys))
    # Compute complete private permutations before modifying any live receiver.
    for collection, rows, keys in plans:
        def less(left, right):
            for index, (_, descending) in enumerate(specs):
                (a, au), (b, bu) = keys[left][index], keys[right][index]
                budget.charge(max(au, bu))
                if a != b:
                    return a > b if descending else a < b
            return False
        introsort(rows, less)
    for collection, rows, _ in plans:
        collection.items[:] = rows
