"""Immediate zero-argument structural reads of native detached collections.

Selection is value-sensitive, not a cache: each operation reads the current
storage in the owning activation. Explicit host extensions retain ordinary
bind/invoke checks. No fetched method or caller-supplied actual is admitted here.
"""
from decimal import Decimal
from yadinassi.types.values import BSLObject
from . import python_direct_value_tree as tree, python_direct_plain_tables as table

_TREE_TARGETS = {
    (id(tree._TREE), 'rows'), (id(tree._TREE), 'columns'),
    (id(tree._ROW), 'rows'), (id(tree._ROWS), None), (id(tree._COLUMNS), None),
}
_TABLE_TARGETS = {
    (id(table._TABLE), None), (id(table._TABLE), 'columns'), (id(table._TABLE), 'indexes'),
    (id(table._COLUMNS), None), (id(table._INDEXES), None),
}
_TARGETS = _TREE_TARGETS | _TABLE_TARGETS
TARGET_IDS = {name: frozenset(kind for kind, prop in _TARGETS if prop == name)
              for name in (None, 'rows', 'columns', 'indexes')}
_TABLE_FIELDS = {
    table._TABLE: frozenset(('rows', 'columns', 'indexes', '_bounded_slice_read')),
    table._COLUMNS: frozenset(('table', '_items')),
    table._INDEXES: frozenset(('table', '_handles')),
}
# This bridge is imported lazily by the emitter. Do not snapshot a host edit
# made after the collection model was defined but before that first import.
_TABLE_METHOD_CODES = {fn: code for fn, code, _, _ in table.runtime._DIRECT_FUNCTIONS}
_TABLE_HOOKS = {}
for cls, mro, fields in table.runtime._DIRECT_CLASSES:
    if cls in (table._TABLE, table._COLUMNS, table._INDEXES):
        _TABLE_HOOKS[cls] = (mro, tuple((name, fn, _TABLE_METHOD_CODES[fn]) for name, fn in fields
                                        if name in ('get_member', 'get_method', 'count')))


def _plain_class(kind):
    mro, checks = _TABLE_HOOKS[kind]
    current = vars(kind)
    return (kind.__mro__ is mro and all('__getattribute__' not in vars(base) and '__getattr__' not in vars(base)
                                        and _TABLE_FIELDS[kind].isdisjoint(vars(base))
                                        for base in (kind, BSLObject))
            and all(current.get(name) is fn and fn.__code__ is code for name, fn, code in checks))


def selects(context, value, projection):
    kind = type(value)
    key = (id(kind), projection)
    # A plain SQLite attachment is not database authority for these exact
    # detached receivers. The operation still checks its owning activation.
    if (key not in _TARGETS or not context._known_method_local
            or context._verify_context or context.policy is not None):
        return False
    if key in _TREE_TARGETS:
        return True
    # Existing table embedding dispatch honors application-specific methods.
    # Let the original path handle these; never bless a replacement as native.
    if not _plain_class(kind):return False
    if projection is not None:
        expected = table._COLUMNS if projection == 'columns' else table._INDEXES
        if not _plain_class(expected):return False
    data = table.raw(value)
    if any(type(name) is not str for name in data):table.fail()
    if 'get_member' in data or 'get_method' in data or 'count' in data:return False
    if projection is not None:
        child = data.get(projection)
        if type(child) is expected:
            child_data = table.raw(child)
            if any(type(name) is not str for name in child_data):table.fail()
            if 'get_method' in child_data or 'count' in child_data:return False
    return True


def _plain_table_count(value, projection):
    data = table.raw(value)
    if any(type(key) is not str for key in data):table.fail()
    kind = type(value)
    if projection is not None:
        child = data.get(projection)
        if type(child) is not (table._COLUMNS if projection == 'columns' else table._INDEXES):table.fail()
        child_data = table.raw(child)
        if any(type(key) is not str for key in child_data) or child_data.get('table') is not value:table.fail()
        data, kind = child_data, type(child)
    if kind is table._TABLE:
        items = data.get('rows')
    else:
        owner = data.get('table')
        if type(owner) is not table._TABLE:table.fail()
        if kind is table._INDEXES:
            owner_data = table.raw(owner)
            if any(type(key) is not str for key in owner_data):table.fail()
            bounded = owner_data.get('_bounded_slice_read')
            if type(bounded) is not bool:table.fail()
            if bounded:
                raise tree.BoundaryViolation('bounded slice index receiver is not connected')
            items = data.get('_handles')
            if type(items) is not list:raise ValueError('invalid index handles')
        else:
            items = data.get('_items')
    if type(items) is not list:table.fail()
    return Decimal(len(items))


def count(context, value, projection, spelling):
    # Generated publication (if any) precedes this check. This read neither
    # invokes a user callback nor mutates/publishes externally visible state.
    context._check_effect()
    key = (id(type(value)), projection)
    if (not context._known_method_local or context._verify_context or context.policy is not None):
        raise tree.BoundaryViolation('structural read context changed')
    if key in _TREE_TARGETS:
        return tree.structural_count(context, value, projection, spelling)
    if key in _TABLE_TARGETS:
        return _plain_table_count(value, projection)
    raise tree.BoundaryViolation('structural read receiver changed')
