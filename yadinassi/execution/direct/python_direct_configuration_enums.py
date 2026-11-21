"""Selected-only read access to enum objects issued by a client application."""
from types import MethodType
from uuid import UUID

from yadinassi.configuration.configuration_enumerations import EnumDefinition
from yadinassi.db.metadata.enum_types import BSLEnumReference, BSLEnumType
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.formats.storage.serialization import value_to_string_internal
from yadinassi.runtime import Interpreter
from yadinassi.types.type_values import type_of
from yadinassi.types.value_checks import value_is_filled
from yadinassi.types.values import HostFunction, to_string
from .source import python_direct_source_enums as bridge

NAMES = ('enums', 'перечисления')
TYPE = ('type', 'тип')
FIND_TYPE = ('findbytype', 'найтипотипу')
FIND_NAME = ('findbyfullname', 'найтипополномуимени')
_RECEIVER_IDS = frozenset(map(id, (*bridge._TYPES, bridge._DeclaredMetadataCollection)))
_PURE = {alias: implementation for aliases, implementation in (
    (('typeof', 'типзнч'), type_of), (('string', 'строка'), to_string),
    (('valueisfilled', 'значениезаполнено'), value_is_filled),
    (('valuetostringinternal', 'значениевстрокувнутр'), value_to_string_internal),
) for alias in aliases}
SERVICES = (*TYPE, *_PURE)
_TYPE_ABI = Interpreter._type_by_name
_RESOLVE_TYPE = bridge.BSLEnumerations.resolve_type


def _deny():
    raise BoundaryViolation('unregistered, changed or foreign configuration enumeration')


def transfer_value(value):
    return type(value) is BSLEnumReference or type(value) is BSLEnumType


def receiver_type(value):
    return id(type(value)) in _RECEIVER_IDS


class Enums:
    def __init__(self, scope):
        self.scope = scope
        self.definitions = scope.configuration.enumerations
        self.namespace = scope.app._command_enum_root
        self.collections = {}

    def bind(self, boundary):
        return _Binding(self, boundary.owner, boundary)

    def check_transfer(self, owner, value):
        # The enclosing scope already checks lifetime before its variables.
        _Binding(self, owner, None).check(value)


class _Binding:
    def __init__(self, enums, owner, boundary):
        self.enums, self.owner, self.boundary = enums, owner, boundary

    def root(self):
        enums = self.enums
        scope, root = enums.scope, enums.namespace
        if self.boundary is not None:
            self.boundary._check()
            if self.boundary._command_scope is not scope:
                _deny()
        if (not enums.definitions or scope.configuration.enumerations is not enums.definitions
                or scope.app._command_enum_root is not root or scope.root._metadata._enumerations is not root
                or self.owner._metadata._enumerations is not root
                or type(root) is not bridge.BSLEnumerations or type(root._managers) is not dict
                or type(root.metadata) is not bridge._DeclaredMetadataCollection
                or type(root.metadata._items) is not dict):
            _deny()
        return root

    @staticmethod
    def manager(root, name):
        if type(name) is not str:
            _deny()
        key = name.casefold()
        manager = root._managers.get(key)
        if (type(manager) is not bridge.BSLEnumManager or type(manager._metadata) is not bridge.EnumMetadata
                or root.metadata._items.get(key) is not manager._metadata
                or type(manager._metadata._name) is not str or manager._metadata._name != name
                or type(manager._value_type) is not BSLEnumType or manager._value_type.snapshot is not root.metadata):
            _deny()
        return manager

    def enum_type(self, root, value):
        manager = self.manager(root, value.name)
        definition = manager._metadata._definition
        family = 'ref' if value is manager._value_type else 'manager' if value is manager._manager_type else None
        if (family is not None and type(value.family) is str and value.family == family
                and value.snapshot is root.metadata and type(value.metadata_uuid) is UUID
                and type(definition) is EnumDefinition and type(definition.identity) is UUID
                and value.metadata_uuid == definition.identity):
            return manager
        _deny()

    def check(self, value):
        root = self.root()
        bridge._abi(value)
        kind = type(value)
        if value is root or value is root.metadata:
            return
        if kind is bridge.BSLEnumManager and type(value._metadata) is bridge.EnumMetadata:
            if self.manager(root, value._metadata._name) is value:
                return
        elif kind is BSLEnumType:
            return self.enum_type(root, value)
        elif kind is BSLEnumReference and type(value.value_type) is BSLEnumType:
            bridge._abi(value.value_type)
            manager = self.enum_type(root, value.value_type)
            if (value.value_type is manager._value_type and value.metadata is manager._metadata
                    and type(value.reference_uuid) is UUID
                    and (value.reference_uuid.int != 0 or value is manager._empty)):
                return
        elif kind is bridge.EnumMetadata or kind is bridge.EnumValueMetadata:
            meta = value if kind is bridge.EnumMetadata else value._owner
            if type(meta) is bridge.EnumMetadata and self.manager(root, meta._name)._metadata is meta:
                if value is meta or (type(meta._values) is bridge._DeclaredMetadataCollection
                        and type(meta._values._items) is dict and type(value._name) is str
                        and meta._values._items.get(value._name.casefold()) is value):
                    return
        elif kind is bridge._DeclaredMetadataCollection:
            entry = self.enums.collections.get(id(value))
            if entry is not None and entry[0] is value and entry[1]._values is value:
                self.check(entry[1])
                return
        _deny()

    def resolve_callable(self, value, **kwargs):
        # Only enum-created transient wrappers reach this call.
        return BoundaryContext.resolve_callable(self.boundary, value, **kwargs)

    def get(self, value, name):
        if type(value) is bridge.EnumMetadata and name.casefold() in ('enumvalues','значенияперечисления'):
            self.check(value)
            self.enums.collections[id(value._values)] = value._values, value
        return bridge.get(self, value, name, validate=_Binding.check)

    def method(self, value, name, **kwargs):
        if name in ('__setitem__','__iter__'):
            _deny()
        return bridge.resolve(self, value, name, validate=_Binding.check, **kwargs)

    def metadata_method(self, name):
        self.root()

        def invoke(value):
            root = self.root()
            if name in FIND_TYPE:
                if type(value) is not BSLEnumType:
                    raise TypeError('enumeration Type required')
                return self.check(value)._metadata
            if type(value) is not str:
                raise TypeError('FindByFullName requires String')
            kind, sep, item = value.partition('.')
            if not sep or kind.casefold() not in ('enum', 'перечисление') or '.' in item:
                return None
            self.check(root.metadata)
            result = root.metadata.find(item)
            if result is not None:
                self.check(result)
            return result
        invoke.returns_value = True
        return invoke

    def service(self, name, **kwargs):
        boundary = self.boundary
        function = boundary._services.get(name)

        def selected():
            if (type(function) is not HostFunction or boundary._services.get(name) is not function
                    or type(function.reference_parameters) is not frozenset or function.reference_parameters
                    or function.returns_value is not True):
                _deny()
            implementation = function.function
            if name in TYPE:
                if (type(implementation) is not MethodType or implementation.__func__ is not _TYPE_ABI
                        or implementation.__self__ is not self.owner):
                    _deny()
            elif implementation is not _PURE[name]:
                _deny()
            return implementation

        self.root()
        selected()

        def invoke(value):
            implementation = selected()
            if name in TYPE:
                if type(value) is not str:
                    raise TypeError('Type requires String')
                root = self.root()
                self.check(root)
                result = _RESOLVE_TYPE(root, value)
                if result is None:
                    raise ValueError('enumeration Type name required')
                self.check(result)
                return result
            kind = type(value)
            if kind is not BSLEnumReference and kind is not BSLEnumType and kind is not bridge.BSLEnumManager:
                raise TypeError('enumeration value required')
            self.check(value)
            return implementation(value)

        return self.resolve_callable(HostFunction(name, invoke), **kwargs)
