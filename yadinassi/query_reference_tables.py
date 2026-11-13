"""Owned, detached catalog/document report columns; no default or transport grant.

A binding identifies the original canonical manager, not a read lease. Unload and cell assignment check the detached owner without a lease. Query
re-use validates all reference domains under one owned read view, including
external-only packages. No existence read occurs.
"""
from dataclasses import dataclass, replace
from types import MethodType
from uuid import UUID

from .catalog_types import BSLCatalogReference
from .document_types import BSLDocumentReference
from .values import NULL, BSLType


@dataclass(frozen=True, slots=True, eq=False)
class _Binding:
    kind: str
    issuer: object
    collection: object
    context: object
    backend: object
    value_type: object
    identity: tuple

    def require_context(self, catalogs, documents):
        collection = catalogs if self.kind == 'catalog_ref' else documents
        if collection is not self.collection:
            raise TypeError('Reference report belongs to another interpreter snapshot')
        self.require_owner()

    def require_owner(self):
        from .catalogs import BSLCatalogManager, BSLCatalogs
        if type(self.identity) is not tuple or len(self.identity) != 2 or type(self.identity[1]) is not UUID:
            raise TypeError('Malformed reference report identity')
        from .documents import BSLDocumentManager, BSLDocuments
        if type(self.kind) is not str or self.kind not in ('catalog_ref', 'document_ref'):
            raise TypeError('Unsupported reference report domain')
        expected, collection_type = ((BSLCatalogManager, BSLCatalogs) if self.kind == 'catalog_ref'
                                    else (BSLDocumentManager, BSLDocuments))
        if (type(self.issuer) is not expected or type(self.collection) is not collection_type
                or self.collection._context is not self.context
                or self.context.backend is not self.backend
                or self.collection._managers.get(self.issuer._schema.name.casefold()) is not self.issuer
                or self.issuer._value_type is not self.value_type
                or self.value_type.snapshot is not self.identity[0]
                or self.value_type.metadata_uuid != self.identity[1]
                or self.collection._metadata is not self.identity[0]):
            raise TypeError('Reference report requires its canonical issuer')
        # Cached owner state only: do not silently open a connection for a
        # detached external-only report. A persistent query rechecks its view.
        from .sqlite_catalog import SQLiteCatalogBackend
        if type(self.backend) is SQLiteCatalogBackend:
            from .catalog_backend import BackendError
            if self.backend._closed:
                raise BackendError('closed')
            if (self.backend.database_id != self.collection._metadata._database_id
                    or self.backend.configuration_generation != self.collection._metadata._generation):
                raise BackendError('schema_changed')

    def value(self, value):
        self.require_owner()
        expected = BSLCatalogReference if self.kind == 'catalog_ref' else BSLDocumentReference
        if (type(value) is not expected or value.value_type is not self.value_type
                or type(value.reference_uuid) is not UUID
                or value.metadata is not self.issuer._metadata):
            raise TypeError('Reference report cell requires exact owned reference; defaults and casts are closed')
        for callback, function in ((value.read_member, type(self.issuer)._read_member),
                                   (value.get_object, type(self.issuer)._get_object)):
            if (type(callback) is not MethodType or callback.__self__ is not self.issuer
                    or callback.__func__ is not function):
                raise TypeError('Reference report cell requires canonical owner callbacks')
        return value


def bind_column(column, catalogs, documents):
    """Resolve declared metadata, never a row UUID or existence lookup."""
    if column.reference_binding is not None:
        if type(column.reference_binding) is not _Binding:
            raise TypeError('Invalid reference report binding')
        column.reference_binding.require_context(catalogs, documents)
        return column
    identity = column.reference_identity
    collection = catalogs if column.kind == 'catalog_ref' else documents
    if collection is None or identity[0] is not collection._metadata:
        raise TypeError('Reference report requires the current metadata snapshot')
    # Planning may initialize a declared target manager, exactly as existing
    # reference field binding does. It never obtains a row or dereferences it.
    if column.kind == 'catalog_ref':
        issuer = collection._manager_by_metadata_uuid(identity[1])
    else:
        matches = [m for m in collection._metadata._snapshot().values()
                   if m._schema.identity == identity[1]]
        if len(matches) != 1:
            raise TypeError('Unknown document reference report domain')
        issuer = collection.get_index(matches[0]._name)
    binding = _Binding(column.kind, issuer, collection, collection._context,
                       collection._context.backend, issuer._value_type, identity)
    binding.require_owner()
    return replace(column, reference_binding=binding)


def description_binding(description):
    from .type_descriptions import BSLTypeDescription
    if type(description) is not BSLTypeDescription:
        raise TypeError('Invalid reference query column description')
    binding = description._query_reference
    from .query_enum_tables import _EnumBinding
    if (type(binding) not in (_Binding, _EnumBinding)
            or type(description.types) is not tuple or len(description.types) != 2
            or description.types[0] is not binding.value_type or description.types[1] is not BSLType.NULL
            or description._query_scalar is not None):
        raise TypeError('Invalid reference query column description')
    # Re-use the existing exact qualifier checks without letting the private
    # nullable marker weaken ordinary reference descriptor validation.
    from .type_descriptions import _reference_description_kind
    singleton = object.__new__(BSLTypeDescription)
    for name in ('number_qualifiers', 'string_qualifiers', 'date_qualifiers', 'binary_data_qualifiers'):
        object.__setattr__(singleton, name, getattr(description, name))
    object.__setattr__(singleton, 'types', (binding.value_type,))
    _reference_description_kind(singleton)
    binding.require_owner()
    return binding


def _description(binding):
    from .type_descriptions import _reference_description
    binding.require_owner()
    description = _reference_description(binding.value_type)
    object.__setattr__(description, 'types', (binding.value_type, BSLType.NULL))
    object.__setattr__(description, '_query_reference', binding)
    return description


def unload(columns, rows):
    """Build a fully validated report without invoking or inventing defaults."""
    from .queries import _description as scalar_description
    from .type_descriptions import _query_nullable_description
    from .value_tables import BSLValueTable, BSLValueTableColumn, BSLValueTableRow
    from decimal import Decimal
    descriptions = tuple(_description(c.reference_binding) if c.reference_binding is not None
                         else _query_nullable_description(scalar_description(c)) for c in columns)
    for values in rows:
        if len(values) != len(columns):
            raise TypeError('Invalid query result shape')
        for column, value in zip(columns, values):
            if value is not NULL and column.reference_binding is not None:
                column.reference_binding.value(value)
    table = BSLValueTable()
    table._budget(len(rows), len(columns))
    for column, description in zip(columns, descriptions):
        table.columns._validate_name(column.name)
        table.columns.items.append(BSLValueTableColumn(table, column.name, description, '', Decimal(0)))
    for values in rows:
        row = object.__new__(BSLValueTableRow)
        row.table, row._deleted = table, False
        row.cells = dict(zip(table.columns.items, values))
        table.rows.append(row)
    return table


def input_bindings(tables, catalogs, documents):
    """Validate every reference column and cell, even unused and empty inputs."""
    result, seen = [], set()
    for table in tables:
        for index, column in enumerate(table.columns):
            binding = column.reference_binding
            if binding is None:
                if column.kind in ('catalog_ref', 'document_ref'):
                    raise TypeError('Temporary reference column lacks an owned binding')
                continue
            from .query_enum_tables import _EnumBinding
            if type(binding) not in (_Binding, _EnumBinding):
                raise TypeError('Invalid temporary reference binding')
            binding.require_context(catalogs, documents)
            if id(binding) not in seen:
                result.append(binding); seen.add(id(binding))
            for row in table.rows:
                if row[index] is not NULL: binding.value(row[index])
    return tuple(result)


def validate_view(bindings, view):
    from .catalog_backend import BackendError
    for binding in bindings:
        binding.require_owner()
        from .query_enum_tables import _EnumBinding
        if type(binding) is _EnumBinding:
            binding.storage._live()
            continue
        metadata = binding.collection._metadata
        if (view.database_id != metadata._database_id
                or view.configuration_generation != metadata._generation):
            raise BackendError('schema_changed')
        schema = (view.catalog_schema(binding.identity[1]) if binding.kind == 'catalog_ref'
                  else view.document_schema(binding.identity[1]))
        if schema != binding.issuer._schema:
            raise BackendError('schema_changed')
