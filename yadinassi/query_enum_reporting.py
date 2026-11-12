"""Execute-local enum descriptors and one lexical read owner.

This is not a storage grant, persistent table owner or detached capability.
Only the exact inventory-enum namespace can issue descriptors; derived/UNION
columns must retain the very descriptor issued for this execution, not rebuild
one from UUIDs or arbitrary custom field metadata.
"""
from dataclasses import dataclass
from types import MethodType
from uuid import UUID

from . import query_parser as syntax
from .catalog_backend import BackendError
from .enum_storage_binding import EnumStorageBinding
from .enum_types import BSLEnumReference


@dataclass(frozen=True, slots=True, eq=False)
class _EnumDescriptor:
    _scope: object
    value_type: object


def require_direct_shape(statements, temporary_manager):
    """Admit one parsed direct tree, not a disguised persistent package."""
    if (type(statements) is not tuple or len(statements) != 1
            or type(statements[0]) not in (syntax.Select, syntax.Union)
            or temporary_manager is not None):
        raise ValueError('Enum inventory query packages are outside this profile')
    for node in syntax.walk_nodes(statements):
        if type(node) in (syntax.Select, syntax.Union) and node.into is not None:
            raise ValueError('Enum inventory temporary output is outside this profile')
        if type(node) in (syntax.Select, syntax.Source) and (node.temporary or node.external):
            raise ValueError('Enum inventory external and temporary sources are outside this profile')
        if type(node) is syntax.Hierarchy:
            raise ValueError('Enum reporting hierarchy queries are outside this profile')
        if (type(node) is syntax.Predicate and node.kind == 'not'
                and (type(node.terms) is not tuple or len(node.terms) != 1
                     or type(node.terms[0]) is not syntax.Membership)):
            raise ValueError('Direct enum reporting NOT is limited to membership')
    return statements[0]


class _EnumReportScope:
    """Current canonical issuer plus query-local immutable descriptor registry.

    The registry only retains identities; every crossing still uses the binder's
    live owner check. No configuration/source validation is replaced by this
    registry and no durable generation proof is exported with result rows.
    """
    __slots__ = ('catalogs', 'binding', '_descriptors', '_retired', 'condition_budget')

    def __init__(self, catalogs):
        from .inventory_enum_runtime import query_binding
        binding = query_binding(catalogs)
        if type(binding) is not EnumStorageBinding:
            raise BackendError('unsupported')
        self.catalogs, self.binding = catalogs, binding
        self._descriptors = {}
        self._retired = False
        self.condition_budget = [0, 0]

    def require_current(self):
        if self._retired:
            raise BackendError('closed')
        EnumStorageBinding._live(self.binding)

    def descriptor(self, enum_id):
        self.require_current()
        value_type = EnumStorageBinding.value_type(self.binding, enum_id)
        key = id(value_type)
        descriptor = self._descriptors.get(key)
        if descriptor is None:
            descriptor = _EnumDescriptor(self, value_type)
            self._descriptors[key] = descriptor
        return descriptor

    def require_descriptor(self, descriptor):
        # Exact class/identity checks precede attributes and any user equality.
        if (type(descriptor) is not _EnumDescriptor or descriptor._scope is not self
                or self._descriptors.get(id(descriptor.value_type)) is not descriptor):
            raise BackendError('invalid_input')
        self.require_current()
        canonical = EnumStorageBinding.value_type(self.binding, descriptor.value_type.metadata_uuid)
        if canonical is not descriptor.value_type:
            raise BackendError('closed')
        return descriptor

    def value_descriptor(self, value):
        self.require_current()
        if type(value) is not BSLEnumReference:
            raise BackendError('invalid_input')
        key = EnumStorageBinding.owned_key(self.binding, value)
        return self.descriptor(key.enum_id)

    def require_same(self, descriptors):
        if type(descriptors) is not tuple or not descriptors:
            raise BackendError('invalid_input')
        first = self.require_descriptor(descriptors[0])
        for descriptor in descriptors[1:]:
            if self.require_descriptor(descriptor) is not first:
                raise TypeError('Compound enum output requires one canonical enum domain')
        return first

    def snapshot_parameters(self, parameters):
        from .relational_queries import _ParameterList, snapshot_parameters
        from .catalog_types import BSLCatalogReference, BSLCatalogType
        from .catalogs import BSLCatalogManager
        from .document_types import BSLDocumentReference
        self.require_current()
        frozen = snapshot_parameters(parameters)
        for value in frozen.values():
            if type(value) is _ParameterList and len(value.values) > 256:
                raise ValueError('Direct enum reporting parameter member limit exceeded')
        # Check every member before any data lease or membership key creation,
        # including unused/mixed members and queries whose physical scan is empty.
        for value in frozen.values():
            members = value.values if type(value) is _ParameterList else (value,)
            for member in members:
                if type(member) is BSLEnumReference:
                    EnumStorageBinding.owned_key(self.binding, member)
                elif type(member) is BSLCatalogReference:
                    typ = member.value_type
                    if (type(typ) is not BSLCatalogType or type(typ.metadata_uuid) is not UUID
                            or type(member.reference_uuid) is not UUID
                            or typ.snapshot is not self.catalogs._metadata):
                        raise BackendError('invalid_input')
                    issuer = self.catalogs._manager_by_metadata_uuid(typ.metadata_uuid)
                    if (type(issuer) is not BSLCatalogManager or typ is not issuer._value_type
                            or member.metadata is not issuer._metadata):
                        raise BackendError('invalid_input')
                    for callback, function in ((member.read_member, BSLCatalogManager._read_member),
                                               (member.get_object, BSLCatalogManager._get_object)):
                        if (type(callback) is not MethodType or callback.__self__ is not issuer
                                or callback.__func__ is not function):
                            raise BackendError('invalid_input')
                elif type(value) is _ParameterList and type(member) is BSLDocumentReference:
                    raise TypeError('Document-reference lists are outside direct enum reporting')
        return frozen

    def execute(self, plan):
        from .inventory_enum_runtime import read_snapshot
        view = None
        try:
            self.require_current()
            view = self.catalogs._context.backend.begin_query_read()
            with read_snapshot(self.catalogs._metadata._root, view):
                # Covers zero rows and scalar-only projections after binding.
                self.require_current()
                result = plan.execute(view=view, budget=[0, 0, 0, 0])
                self.require_current()
                return result
        finally:
            try:
                if view is not None:
                    view.close()
            finally:
                self._retired = True


def execute_direct(statements, catalogs, parameters, temporary_manager,
                   documents, information_registers):
    from .relational_queries import _Plan
    from .query_sources import _UnionPlan
    query = require_direct_shape(statements, temporary_manager)
    scope = _EnumReportScope(catalogs)
    try:
        frozen = scope.snapshot_parameters(parameters)
        plan_type = _UnionPlan if type(query) is syntax.Union else _Plan
        plan = plan_type(query, catalogs, frozen, documents=documents,
                         information_registers=information_registers, enum_scope=scope)
        return scope.execute(plan)
    finally:
        scope._retired = True
