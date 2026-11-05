"""Host-owned bounded scalar FormData building block, not native managed forms.

No constructor/global registration, interpreter integration, imported-source
execution, persistence, message binding or renderer procedure endpoint. Python
hosts are trusted; BSL sees only the closed scalar member surface.
"""
from dataclasses import dataclass
from uuid import UUID

from .catalog_backend import FieldSchema
from .catalog_qualifiers import normalize_field
from .values import BSLObject

MAX_FIELDS = 128
MAX_TEXT = 65536
MAX_TOTAL_TEXT = 262144


def _name(value):
    if type(value) is not str or not value or len(value) > 128 or not value.isidentifier():
        raise ValueError('FormData: invalid name')
    return value.casefold()


@dataclass(frozen=True, slots=True)
class ScalarFormField:
    schema: FieldSchema
    aliases: tuple = ()
    writable: bool = True


@dataclass(frozen=True, slots=True)
class ScalarFormBinding:
    """Host registration only; path is root.canonical-field, not an expression."""
    control: str
    data_path: str
    editable: bool = True


@dataclass(frozen=True, slots=True)
class ScalarFormSnapshot:
    revision: int
    values: tuple


def _value(field, value):
    kind = field.kind
    expected = {'string': str, 'boolean': bool}[kind]
    if type(value) is not expected:
        raise TypeError('FormData: exact scalar type required')
    if kind == 'string' and ('\x00' in value or len(value) > MAX_TEXT):
        raise ValueError('FormData: text limit or invalid text')
    return normalize_field(value, field)


class ScalarFormData(BSLObject):
    """Single-owner scalar buffer. Patches commit once after full validation.

    Failed individual setters retain earlier successful setters. Atomic patch
    semantics are local host policy, not handler rollback or native evidence.
    Snapshots contain immutable scalars only; there is no persisted baseline
    inside this object and no implicit adoption of detached save images.
    """
    def __init__(self, fields, values, *, root='Object', bindings=()):
        _name(root)
        if type(fields) is not tuple or not 1 <= len(fields) <= MAX_FIELDS:
            raise ValueError('FormData: bounded fields required')
        self._fields = fields
        self._root = root
        self._aliases = {}
        self._schemas = {}
        identities = set()
        for item in fields:
            if type(item) is not ScalarFormField or type(item.schema) is not FieldSchema:
                raise TypeError('FormData: field schema required')
            field = item.schema
            if (type(field.identity) is not UUID or field.identity in identities
                    or type(field.kind) is not str or field.kind not in ('string', 'boolean')
                    or field.target_catalog_id is not None or type(item.writable) is not bool
                    or type(item.aliases) is not tuple or len(item.aliases) > 8):
                raise ValueError('FormData: unsupported schema')
            identities.add(field.identity)
            key = _name(field.name)
            # Normalization validates exact immutable qualifier tuples eagerly.
            if field.kind == 'boolean' and (type(field.qualifiers) is not tuple or field.qualifiers):
                raise ValueError('FormData: unsupported Boolean qualifiers')
            _value(field, {'string': '', 'boolean': False}[field.kind])
            for alias in (field.name,) + item.aliases:
                alias = _name(alias)
                if alias in self._aliases:
                    raise ValueError('FormData: duplicate alias')
                self._aliases[alias] = key
            self._schemas[key] = item
        self._bindings = {}
        if type(bindings) is not tuple or len(bindings) > MAX_FIELDS:
            raise ValueError('FormData: bounded bindings required')
        for binding in bindings:
            if type(binding) is not ScalarFormBinding or type(binding.editable) is not bool:
                raise TypeError('FormData: host binding required')
            control = _name(binding.control)
            if type(binding.data_path) is not str or len(binding.data_path) > 257:
                raise ValueError('FormData: invalid path')
            parts = binding.data_path.split('.')
            if len(parts) != 2 or _name(parts[0]) != _name(root):
                raise ValueError('FormData: unknown root')
            key = _name(parts[1])
            if key not in self._schemas or control in self._bindings:
                raise ValueError('FormData: unknown field or duplicate control')
            self._bindings[control] = (key, binding)
        self._registration = bindings
        self._revision = 0
        self._values = self._validate_pairs(values, initial=True)
        if len(self._values) != len(fields):
            raise ValueError('FormData: complete initial image required')
        self._check_total(self._values)

    def _validate_pairs(self, pairs, *, initial=False):
        if type(pairs) is not tuple or len(pairs) > MAX_FIELDS:
            raise ValueError('FormData: bounded patch required')
        changes = {}
        for pair in pairs:
            if type(pair) is not tuple or len(pair) != 2:
                raise TypeError('FormData: field/value pair required')
            key = self._aliases.get(_name(pair[0]))
            if key is None or key in changes:
                raise ValueError('FormData: unknown or repeated field')
            field = self._schemas[key]
            if not initial and not field.writable:
                raise ValueError('FormData: read-only member')
            changes[key] = _value(field.schema, pair[1])
        return changes

    @staticmethod
    def _check_total(values):
        if sum(len(v) for v in values.values() if type(v) is str) > MAX_TOTAL_TEXT:
            raise ValueError('FormData: total text limit')

    def snapshot(self):
        return ScalarFormSnapshot(self._revision, tuple(
            (field.schema.name, self._values[field.schema.name.casefold()]) for field in self._fields))

    def patch(self, pairs, *, revision):
        if type(revision) is not int or revision != self._revision:
            raise ValueError('FormData: stale revision')
        changes = self._validate_pairs(pairs)
        candidate = self._values | changes
        self._check_total(candidate)
        self._values = candidate
        self._revision += 1
        return self.snapshot()

    def change_control(self, control, value, *, revision):
        entry = self._bindings.get(_name(control))
        if entry is None or not entry[1].editable:
            raise ValueError('FormData: unknown or read-only control')
        return self.patch(((self._schemas[entry[0]].schema.name, value),), revision=revision)

    def data_path(self, control):
        entry = self._bindings.get(_name(control))
        if entry is None:
            raise ValueError('FormData: unknown control')
        return entry[1].data_path

    def detached_save_image(self):
        """Independent candidate. Refusal/failure means discard, never auto-copyout."""
        return ScalarFormData(self._fields, self.snapshot().values,
                              root=self._root, bindings=self._registration)

    def get_member(self, member):
        key = self._aliases.get(_name(member))
        if key is None:
            raise ValueError('FormData: unknown member')
        return self._values[key]

    def set_member(self, member, value):
        self.patch(((member, value),), revision=self._revision)

    def get_method(self, name):
        raise ValueError('FormData: no methods')
