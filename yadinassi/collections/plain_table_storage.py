"""Plain list-backed table storage; no BSL receiver or ownership capability.

Adapters retain their existing public row/column identities and authority checks.
This module owns data operations, not interpreter admission. ``validate`` is an
explicit boundary check: hot reads do not rescan a table and must not be used to
bless arbitrary host-mutated list subclasses. Defaults/metadata/payloads are
opaque references. There is no qualifier coercion, codec or index engine here.
"""
from decimal import Decimal

from yadinassi.temporal.dates import BSLDate, MAX_TICKS
from yadinassi.text.sort_keys import text_sort_key
from yadinassi.types.values import BSLArray, BSLType, NULL
from yadinassi.execution.direct.python_direct_plain_array import _DIRECT_PLAIN_ARRAY_TYPE
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
from .structures import BSLStructure

_SCALAR_TYPES = (type(None), str, bool, int, Decimal, type(NULL))
_SORT_DATE_TICKS = vars(BSLDate)["ticks"]
_SORT_DATE_BOUNDARY = vars(BSLDate)["boundary"]


class StorageError(ValueError):
    pass


def key(name):
    if type(name) is not str:
        raise TypeError('column name must be an exact string')
    return name.casefold()


class Schema:
    """Ordered schema and a reusable default row; no per-row schema objects."""
    __slots__ = ('_names', '_keys', '_offsets', '_metadata', '_defaults', 'version', 'data_epoch')

    def __init__(self):
        self._names = []
        self._keys = []
        self._offsets = {}
        self._metadata = []
        self._defaults = []
        self.version = 0
        self.data_epoch = 0

    @property
    def names(self):
        return self._names

    @property
    def keys(self):
        return self._keys

    @property
    def metadata(self):
        return self._metadata

    def resolve(self, name):
        normalized = key(name)
        if type(self._offsets) is not dict or any(type(k) is not str for k in self._offsets):
            raise StorageError('noncanonical schema lookup')
        if normalized not in self._offsets:
            raise StorageError('column not found: ' + name)
        return normalized

    def offset(self, name):
        result=self._offsets[self.resolve(name)]
        if type(result) is not int or type(self._keys) is not list or not 0<=result<len(self._keys):
            raise StorageError('noncanonical schema offset')
        return result

    def validate(self):
        if (type(self._names) is not list or type(self._keys) is not list
                or type(self._metadata) is not list or type(self._offsets) is not dict
                or type(self._defaults) is not list or type(self.version) is not int):
            raise StorageError('noncanonical schema storage')
        if (any(type(k) is not str for k in self._offsets)
                or any(type(n) is not str for n in self._names)
                or any(type(k) is not str for k in self._keys)):
            raise StorageError('noncanonical schema keys')
        keys = [n.casefold() for n in self._names]
        if (keys != self._keys or len(set(keys)) != len(keys)
                or len(self._metadata) != len(keys)
                or len(self._defaults) != len(keys)
                or len(self._offsets) != len(keys)):
            raise StorageError('inconsistent schema')
        for index, name in enumerate(keys):
            value = self._offsets.get(name)
            if type(value) is not int or value != index:
                raise StorageError('inconsistent column offset')

    def _publish(self, names, metadata, defaults):
        # Inputs are prepared internally before touching this schema.
        keys = [n.casefold() for n in names]
        offsets = {name: i for i, name in enumerate(keys)}
        self._names, self._keys = names, keys
        self._metadata, self._defaults, self._offsets = metadata, defaults, offsets
        self.version += 1


class RowStorage(list):
    """Private row data. Raw list methods are fast, not an admission check."""
    def __init__(self, owner, schema, values=None):
        if type(schema) is not Schema:
            raise TypeError('exact schema required')
        if values is not None:
            if type(values) is not list or len(values) != len(schema._keys):
                raise StorageError('initial row does not match schema')
        list.__init__(self, schema._defaults if values is None else values)
        self.schema, self._owner, self._deleted = schema, owner, False

    def get_value(self, name):
        if self._deleted:
            raise StorageError('row is detached')
        return list.__getitem__(self, self.schema.offset(name))

    def set_value(self, name, value):
        if self._deleted:
            raise StorageError('row is detached')
        offset = self.schema.offset(name)
        self.schema.data_epoch += 1
        list.__setitem__(self, offset, value)


def validate_row(row, schema, owner, *, active=True, row_type=RowStorage):
    if type(row) is not row_type:
        raise StorageError('noncanonical row storage')
    if row.schema is not schema or row._owner is not owner or type(row._deleted) is not bool:
        raise StorageError('foreign row storage')
    if active and row._deleted:
        raise StorageError('row is detached')
    if list.__len__(row) != len(schema._keys):
        raise StorageError('row does not match schema')


def scalar_equal(left, right):
    """Exact scalar comparison only; never call arbitrary payload equality."""
    left_kind, right_kind = type(left), type(right)
    if (not any(left_kind is kind for kind in _SCALAR_TYPES)
            or not any(right_kind is kind for kind in _SCALAR_TYPES)):
        raise NotImplementedError('comparison of opaque values is not supported')
    if left_kind is not right_kind and not (
            left_kind in (int, Decimal) and right_kind in (int, Decimal)):
        return False
    return left == right

def table_object_sort_rank(kind):
    """Observed table order of Array, Structure and reflected Type."""
    if kind is list or kind is _DIRECT_PLAIN_ARRAY_TYPE or kind is BSLArray:
        return 0
    if kind is _DirectStructure or kind is BSLStructure:
        return 1
    if kind is BSLType:
        return 2
    return None


def _sort_value(value):
    kind = type(value)
    if value is None:
        return 0, 0, 0
    if kind is bool:
        return 1, 0, value
    if kind is int:
        return 1, 1, value
    if kind is Decimal:
        if not value.is_finite():
            raise ValueError('nonfinite sort value')
        return 1, 1, value
    if kind is str:
        return 1, 2, text_sort_key(value)
    if value is NULL:
        return 0, 1, 0
    if kind is BSLDate:
        try:
            ticks = _SORT_DATE_TICKS.__get__(value, kind)
            boundary = _SORT_DATE_BOUNDARY.__get__(value, kind)
        except AttributeError:
            raise ValueError('invalid sort date payload') from None
        if type(ticks) is not int or not 0 <= ticks <= MAX_TICKS or type(boundary) is not bool:
            raise ValueError('invalid sort date payload')
        if boundary:
            raise NotImplementedError('sorting unknown dates is not supported')
        return 1, 3, ticks
    raise NotImplementedError('sorting opaque values is not supported')


def _sort_object_value(value):
    rank = table_object_sort_rank(type(value))
    if rank is None:
        raise NotImplementedError('sorting opaque values is not supported')
    # Objects of the same collection kind are ties, not payload comparisons.
    return rank, text_sort_key(str(value)) if rank == 2 else 0


class TableStorage:
    """General data kernel, usable under an existing BSL table facade.

    Index arguments here are exact Python ints. BSL argument conversion belongs
    in the facade and is deliberately not repeated inside this kernel.
    """
    __slots__ = ('owner', 'schema', 'rows', 'row_factory', 'epoch')

    def __init__(self, owner, row_factory=RowStorage):
        # This is an internal factory parameter, not runtime admission. The
        # facade must pin its exact row class before allowing interpreted code.
        if type(row_factory) is not type or not any(base is RowStorage for base in row_factory.__mro__):
            raise TypeError('row factory must be a RowStorage class')
        self.owner, self.schema, self.rows = owner, Schema(), []
        self.row_factory = row_factory
        self.epoch = 0

    def validate(self):
        if type(self.schema) is not Schema or type(self.rows) is not list:
            raise StorageError('noncanonical table storage')
        self.schema.validate()
        for row in self.rows:
            validate_row(row, self.schema, self.owner, row_type=self.row_factory)

    def _position(self, index, *, inserting=False):
        if type(index) is not int:
            raise TypeError('storage index must be exact int')
        if not 0 <= index < len(self.rows) + int(inserting):
            raise IndexError('row index out of range')
        return index

    def add(self):
        row = self.row_factory(self.owner, self.schema)
        self.epoch += 1
        self.rows.append(row)
        return row

    def insert(self, index):
        position = self._position(index, inserting=True)
        row = self.row_factory(self.owner, self.schema)
        self.epoch += 1
        self.rows.insert(position, row)
        return row

    def get(self, index):
        return self.rows[self._position(index)]

    def delete(self, index):
        self.epoch += 1
        row = self.rows.pop(self._position(index))
        row._deleted = True
        return row

    def move(self, index, offset):
        old = self._position(index)
        if type(offset) is not int:
            raise TypeError('storage offset must be exact int')
        new = self._position(old + offset)
        self.epoch += 1
        self.rows.insert(new, self.rows.pop(old))

    def clear(self):
        rows = self.rows[:]
        self.epoch += 1
        self.rows.clear()
        for row in rows:
            row._deleted = True

    def add_column(self, name, metadata=None, default=None):
        # The facade admits canonical storage once. No per-column rescan or
        # rebuilding of the existing schema: O(1) amortized plus active rows.
        normalized = key(name)
        schema = self.schema
        # Structural growth can also be reached through the public class API.
        # Reject callback-bearing raw storage before lookup/append, without
        # scanning payload cells or reconstructing the existing schema.
        if type(schema) is not Schema or type(self.rows) is not list:
            raise StorageError('noncanonical structural storage')
        if (type(schema._offsets) is not dict or type(schema._names) is not list
                or type(schema._keys) is not list or type(schema._metadata) is not list
                or type(schema._defaults) is not list or type(schema.version) is not int):
            raise StorageError('noncanonical schema storage')
        if any(type(k) is not str for k in schema._offsets) or any(type(k) is not str for k in schema._names) or any(type(k) is not str for k in schema._keys):
            raise StorageError('noncanonical schema keys')
        if any(type(i) is not int or not 0<=i<len(schema._names) for i in schema._offsets.values()):
            raise StorageError('noncanonical schema offsets')
        width=len(schema._names)
        if not (len(schema._keys)==len(schema._metadata)==len(schema._defaults)==len(schema._offsets)==width):
            raise StorageError('inconsistent schema width')
        for row in self.rows:
            if type(row) is not self.row_factory or row._owner is not self.owner or row.schema is not schema or row._deleted is not False or list.__len__(row)!=width:
                raise StorageError('foreign or malformed row storage')
        if normalized in schema._offsets:
            raise StorageError('duplicate column: ' + name)
        position = len(schema._names)
        self.epoch += 1
        schema._names.append(name)
        schema._keys.append(normalized)
        schema._metadata.append(metadata)
        schema._defaults.append(default)
        schema._offsets[normalized] = position
        for row in self.rows:
            list.append(row, default)
        schema.version += 1
        return position

    def insert_column(self, position, name, metadata=None, default=None):
        if type(position) is not int:
            raise TypeError('storage index must be exact int')
        self.validate()
        schema = self.schema
        if not 0 <= position <= len(schema._names):
            raise IndexError('column index out of range')
        if key(name) in schema._offsets:
            raise StorageError('duplicate column: ' + name)
        names, descriptors, defaults = schema._names[:], schema._metadata[:], schema._defaults[:]
        names.insert(position, name)
        descriptors.insert(position, metadata)
        defaults.insert(position, default)
        self.epoch += 1
        schema._publish(names, descriptors, defaults)
        for row in self.rows:
            list.insert(row, position, default)

    def move_column(self, old, new):
        if type(old) is not int or type(new) is not int:
            raise TypeError('storage column positions must be exact int')
        self.validate()
        schema = self.schema
        width = len(schema._names)
        if not (0 <= old < width and 0 <= new < width):
            raise IndexError('column index out of range')
        if old == new:
            return
        names, metadata, defaults = schema._names[:], schema._metadata[:], schema._defaults[:]
        for items in (names, metadata, defaults):
            items.insert(new, items.pop(old))
        schema._publish(names, metadata, defaults)
        for row in self.rows:
            # Existing cells move with the column; neither equality nor
            # assignment conversion belongs to this structural operation.
            list.insert(row, new, list.pop(row, old))
        self.epoch += 1

    def rename_column(self, old_name, new_name):
        schema = self.schema
        old = schema.resolve(old_name)
        new = key(new_name)
        if new != old and new in schema._offsets:
            raise StorageError('duplicate column: ' + new_name)
        position = schema._offsets[old]
        # Rows are positional and need no mutation or payload copying.
        self.epoch += 1
        schema._offsets[new] = position
        if new != old:
            del schema._offsets[old]
        schema._names[position] = new_name
        schema._keys[position] = new
        schema.version += 1

    def delete_column(self, name):
        schema = self.schema
        position = schema.offset(name)
        names = schema._names[:position] + schema._names[position + 1:]
        metadata = schema._metadata[:position] + schema._metadata[position + 1:]
        defaults = schema._defaults[:position] + schema._defaults[position + 1:]
        # Keep all removed references alive until schema and rows agree.
        previous = (schema._metadata, schema._defaults,
                    [list.__getitem__(row, position) for row in self.rows])
        self.epoch += 1
        schema._publish(names, metadata, defaults)
        for row in self.rows:
            list.__delitem__(row, position)
        if not names:
            self.clear()
        return None

    def find(self, value, name):
        normalized = self.schema.offset(name)
        return next((row for row in self.rows
                     if scalar_equal(list.__getitem__(row, normalized), value)), None)

    def fill(self, value, names=None):
        if names is None:
            selected = range(len(self.schema._keys))
        else:
            if type(names) is not tuple and type(names) is not list:
                raise TypeError('column selection must be exact list or tuple')
            selected = tuple(self.schema.offset(name) for name in names)
        self.epoch += 1
        previous = [[list.__getitem__(row, name) for name in selected] for row in self.rows]
        for row in self.rows:
            for name in selected:
                list.__setitem__(row, name, value)
        # previous retains replaced payloads through coherent publication.
        return None

    def copy(self, owner, names=None):
        if names is None:
            selected = range(len(self.schema._keys))
        else:
            if type(names) is not tuple and type(names) is not list:
                raise TypeError('column selection must be exact list or tuple')
            selected = tuple(self.schema.offset(name) for name in names)
            if len(set(selected)) != len(selected):
                raise StorageError('duplicate projected column')
        result = TableStorage(owner, self.row_factory)
        for pos in selected:
            result.add_column(self.schema._names[pos], self.schema._metadata[pos],
                              self.schema._defaults[pos])
        for row in self.rows:
            copied = result.add()
            for target, source in enumerate(selected):
                list.__setitem__(copied, target, list.__getitem__(row, source))
        return result

    def sort(self, order):
        if type(order) is not tuple and type(order) is not list:
            raise TypeError('sort order must be exact list or tuple')
        prepared = []
        for entry in order:
            if type(entry) is not tuple or len(entry) != 2 or type(entry[1]) is not bool:
                raise TypeError('sort entry must be (column_name, descending_bool)')
            position = self.schema.offset(entry[0])
            # A column may sort scalar or object keys, not both. Select the
            # projection once, without adding a per-row test to the scalar sort.
            object_column = self.rows and (
                table_object_sort_rank(type(list.__getitem__(self.rows[0], position))) is not None
            )
            prepared.append((position, entry[1], _sort_object_value if object_column else _sort_value))
        # Sort a copy so an invalid key never changes the physical row order.
        if len(prepared) == 1:
            position, descending, project = prepared[0]
            ordered = sorted(self.rows,
                             key=lambda row: project(list.__getitem__(row, position)),
                             reverse=descending)
        else:
            # Mixed directions need stable passes over the materialized keys.
            decorated = [(row, tuple(project(list.__getitem__(row, position))
                                     for position, _, project in prepared)) for row in self.rows]
            for index in range(len(prepared) - 1, -1, -1):
                decorated.sort(key=lambda entry: entry[1][index], reverse=prepared[index][1])
            ordered = [row for row, _ in decorated]
        self.epoch += 1
        self.rows[:] = ordered

# Definition-time code/data identity, consumed by the direct boundary before a
# callback-free operation group. These tuples do not grant receiver authority.
_DIRECT_CLASSES=tuple((cls,cls.__mro__,tuple(vars(cls).items())) for cls in (Schema,RowStorage,TableStorage))
_DIRECT_FUNCTIONS=tuple((fn,fn.__code__,fn.__defaults__,tuple((fn.__kwdefaults__ or {}).items()))
    for fn in [*globals().values(),*(fn for cls,_,fields in _DIRECT_CLASSES for _,v in fields
        for fn in ((v.fget,v.fset,v.fdel) if type(v) is property else (v,)) if fn is not None)]
    if type(fn) is type(lambda:None))
_DIRECT_BINDINGS=tuple((name,value) for name,value in tuple(globals().items()) if callable(value) or name=='_SCALAR_TYPES')

_DIRECT_NAMES=frozenset((*globals(), "_DIRECT_NAMES"))
