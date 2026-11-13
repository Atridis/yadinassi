"""Durable enum report domains, never Execute-local descriptors or read leases."""
from dataclasses import dataclass, replace
from uuid import UUID

from .catalog_backend import BackendError
from .enum_storage_binding import EnumStorageBinding
from .enum_types import BSLEnumReference, BSLEnumType


@dataclass(frozen=True, slots=True, eq=False)
class _EnumBinding:
    catalogs: object
    storage: object
    enum_id: UUID
    value_type: object
    identity: tuple
    kind: str = 'enum_ref'

    def require_owner(self):
        from .inventory_enum_runtime import query_owner
        owner = query_owner(self.catalogs)
        if (owner is None or type(self.storage) is not EnumStorageBinding
                or type(self.enum_id) is not UUID or type(self.kind) is not str or self.kind != 'enum_ref'
                or owner.metadata._enum_storage is not self.storage
                or self.storage._hook_owner is not owner):
            raise BackendError('closed')
        self.storage._require_detached()
        entry = self.storage._entry(self.enum_id)
        if (entry[5] is not self.value_type or type(self.identity) is not tuple
                or len(self.identity) != 2 or self.identity[0] is not self.value_type.snapshot
                or type(self.identity[1]) is not UUID or self.identity[1] != self.enum_id):
            raise BackendError('invalid_input')

    def require_context(self, catalogs, documents):
        if catalogs is not self.catalogs:
            raise BackendError('invalid_input')
        self.require_owner()

    def value(self, value):
        self.require_owner()
        if type(value) is not BSLEnumReference:
            raise TypeError('Enum report requires exact owned value; defaults/casts remain closed')
        if not any(value is ref for ref in self.storage._entry(self.enum_id)[7]):
            raise BackendError('invalid_input')
        return value

    def descriptor(self, scope):
        from .query_enum_reporting import _EnumReportScope
        if type(scope) is not _EnumReportScope:
            raise BackendError('invalid_input')
        self.require_context(scope.catalogs, None)
        scope.require_current()
        if scope.binding is not self.storage:
            raise BackendError('closed')
        descriptor = scope.descriptor(self.enum_id)
        if descriptor.value_type is not self.value_type:
            raise BackendError('closed')
        return descriptor


def binding(scope, descriptor):
    descriptor = scope.require_descriptor(descriptor)
    typ = descriptor.value_type
    result = _EnumBinding(scope.catalogs, scope.binding, typ.metadata_uuid, typ,
                          (typ.snapshot, typ.metadata_uuid))
    result.require_owner()
    return result


def prepare_tables(tables, scope):
    """Reissue descriptors even for unused/empty columns before any statement."""
    from .query_packages import _Table
    from .values import NULL
    result = {}
    for name, table in tables.items():
        columns = []
        for index, column in enumerate(table.columns):
            if column.kind == 'enum_ref':
                domain = column.reference_binding
                if type(domain) is not _EnumBinding:
                    raise BackendError('invalid_input')
                descriptor = domain.descriptor(scope)
                for row in table.rows:
                    if row[index] is not NULL:
                        domain.value(row[index])
                        scope.value_descriptor(row[index])
                column = replace(column, enum_descriptor=descriptor)
            columns.append(column)
        result[name] = _Table(tuple(columns), table.rows)
    return result


def detach_columns(columns):
    return tuple(replace(c, enum_descriptor=None) if c.kind == 'enum_ref' else c for c in columns)


def execute_report(statements, catalogs, parameters, manager, documents, information_registers):
    """One lexical lease, including cold metadata and external-only reports."""
    from . import query_parser as syntax
    from .inventory_enum_runtime import query_owner, read_snapshot
    from .metadata import _prepare_enum_query_metadata
    from .query_enum_reporting import _EnumReportScope
    from .query_packages import execute_package
    if type(statements) is not tuple or not statements:
        raise BackendError('invalid_input')
    for node in syntax.walk_nodes(statements):
        if type(node) in (syntax.Select, syntax.Source) and node.family == 'information_register':
            raise ValueError('Information-register sources remain outside the exact enum profile')
        if type(node) in (syntax.Select, syntax.Source) and node.virtual_condition is not None:
            _preflight_virtual_condition(node.virtual_condition)
        if type(node) is syntax.Hierarchy:
            raise ValueError('Enum report hierarchy queries remain outside this profile')
        if (type(node) is syntax.Predicate and node.kind == 'not'
                and (type(node.terms) is not tuple or len(node.terms) != 1
                     or type(node.terms[0]) is not syntax.Membership)):
            raise ValueError('Enum report NOT remains limited to membership')
    owner = query_owner(catalogs)
    if owner is None:
        raise BackendError('unsupported')
    parameters = _preflight_parameters(owner, catalogs, parameters)
    view, scope = owner.backend.begin_query_read(), None
    try:
        with read_snapshot(owner.metadata, view):
            _prepare_enum_query_metadata(owner.metadata, view)
            scope = _EnumReportScope(catalogs)
            return execute_package(statements, catalogs, parameters, manager, documents,
                                   information_registers, _enum_scope=scope, _owned_view=view)
    finally:
        try:
            if not view._view._closed:
                view.close()
        finally:
            if scope is not None: scope._retired = True


def _preflight_parameters(owner, catalogs, parameters):
    """Reject foreign parameter owners without acquiring a data lease.

    This is only a preliminary check. The complete binder is still freshly
    validated under the execution's lexical snapshot before any source scan.
    """
    from .relational_queries import snapshot_parameters, _ParameterList
    from .catalog_types import BSLCatalogReference
    from .catalogs import BSLCatalogManager
    from .document_types import BSLDocumentReference
    from .enumerations import BSLEnumerations, BSLEnumManager
    from types import MethodType
    frozen = snapshot_parameters(parameters)
    namespace = owner.namespace
    if type(namespace) is not BSLEnumerations or type(namespace._managers) is not dict:
        raise BackendError('invalid_input')
    for value in frozen.values():
        members = value.values if type(value) is _ParameterList else (value,)
        if type(value) is _ParameterList and len(members) > 256:
            raise ValueError('Enum report parameter member limit exceeded')
        for member in members:
            if type(member) is BSLEnumReference:
                if type(member.value_type) is not BSLEnumType or member.value_type.snapshot is not namespace.metadata:
                    raise BackendError('invalid_input')
                found = False
                for manager in namespace._managers.values():
                    if type(manager) is not BSLEnumManager or type(manager._values) is not tuple:
                        raise BackendError('invalid_input')
                    if member is manager._empty or any(member is ref for ref in manager._values):
                        found = True; break
                if not found: raise BackendError('invalid_input')
            elif type(member) is BSLCatalogReference:
                callback = member.read_member
                issuer = callback.__self__ if type(callback) is MethodType else None
                if (type(issuer) is not BSLCatalogManager or issuer._catalogs is not catalogs
                        or member.value_type is not issuer._value_type or member.metadata is not issuer._metadata
                        or callback.__func__ is not BSLCatalogManager._read_member
                        or type(member.get_object) is not MethodType or member.get_object.__self__ is not issuer
                        or member.get_object.__func__ is not BSLCatalogManager._get_object):
                    raise BackendError('invalid_input')
            elif type(value) is _ParameterList and type(member) is BSLDocumentReference:
                raise TypeError('Document-reference lists remain outside enum reports')
    return frozen


def _preflight_virtual_condition(node):
    """Cheap syntax/work bound only; field/domain checks use fresh metadata."""
    from . import query_parser as syntax
    from .accumulation_movements import MAX_DIMENSIONS
    pending, count = [(node, 0)], 0
    while pending:
        part, depth = pending.pop()
        if depth > 16:
            raise ValueError('Virtual dimension condition nesting limit exceeded')
        if type(part) is syntax.Predicate:
            if part.kind != 'and' or type(part.terms) is not tuple or not part.terms:
                raise ValueError('Virtual dimension conditions support only AND')
            pending.extend((child, depth + 1) for child in part.terms)
        else:
            count += 1
            if count > MAX_DIMENSIONS:
                raise ValueError('Virtual dimension condition term limit exceeded')
