"""Trusted bridge between one form's private reference scope and owned storage.

Only explicitly enrolled snapshots of the same open database may normalize into
this coordinator's catalog managers. Browser capabilities never name records.
"""
from contextlib import contextmanager
from uuid import UUID
from weakref import WeakSet

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalog_types import BSLCatalogReference, BSLCatalogType
from yadinassi.forms.form_references import FormReferenceBinding, FormReferenceScope, active_reference_read


def admitted_reference_view(backend, lease):
    from yadinassi.db.sqlite.sqlite_catalog import _View
    from yadinassi.db.sqlite.sqlite_documents import DocumentView

    base = lease._view if type(lease) is DocumentView else lease
    if (type(base) is not _View or base._backend is not backend
            or backend._active is not base or base._operation_id is not None
            or base._query_language or base._catalog_data is not None
            or base._connection is None or not base._connection.in_transaction):
        raise BackendError('unsupported')
    base._require()
    return base


@contextmanager
def _ordinary_reference_read(owned, *, document):
    from yadinassi.db.database_transactions import forbid_transfer

    backend = owned._backend
    lease = None
    try:
        try:
            if owned._stale or owned.context.backend is not backend:
                raise BackendError('schema_changed')
            owned.context.require_active(tabular_sections=True)
            if document and (backend.posting_configuration is not None
                             or backend.accumulation_configuration is not None):
                raise BackendError('unsupported')
            forbid_transfer(backend)
            lease = backend.begin_document_read() if document else backend.begin_read()
            base = admitted_reference_view(backend, lease)
            # Reuse the existing export validator, but on this same read view.
            if backend._export_configuration_snapshot(base._connection) != owned._sources:
                raise BackendError('schema_changed')
            schema = lease.document_schema(owned.schema.identity) if document else lease.catalog_schema(owned.schema.identity)
            identity = (lease.database_id, lease.configuration_generation)
            if schema != owned.schema or (owned._identity is not None and identity != owned._identity):
                raise BackendError('schema_changed')
        except BackendError as error:
            if error.code in ('schema_changed', 'integrity'):
                owned._stale = True
            raise
        yield base
        backend._check_file()
    finally:
        if lease is not None:
            lease.close()


def owned_reference_scope(owned, targets, enum_targets=()):
    catalogs = owned.manager._catalogs
    metadata = catalogs._metadata
    metadata._snapshot()
    enrolled = WeakSet((metadata,))
    managers = {}
    bindings = {}
    for target, identity, name in targets:
        manager = catalogs._manager_by_metadata_uuid(identity)
        if manager._schema.name != name:
            raise ValueError('reference target source mismatch')
        managers[target] = manager
        def normalize(value, manager=manager, target=target):
            batch = active_reference_read(scope)
            if batch is None:
                owned.verify_source()
            else:
                batch.view()
            if (type(value) is not BSLCatalogReference or type(value.value_type) is not BSLCatalogType
                    or type(value.reference_uuid) is not UUID or type(value.reference_uuid.int) is not int
                    or type(value.value_type.metadata_uuid) is not UUID
                    or value.value_type.snapshot not in enrolled
                    or value.value_type.metadata_uuid != manager._schema.identity):
                raise ValueError('reference from another database, target or activation')
            if batch is None:
                return manager._ref(value.reference_uuid)
            key = (target, value.reference_uuid.int)
            result = batch.normalized.get(key)
            if result is None:
                result = batch.normalized[key] = manager._ref(value.reference_uuid)
            return result

        def presentation(value, manager=manager, target=target):
            if value.is_empty():
                return ''
            batch = active_reference_read(scope)
            if batch is None:
                card = manager._read(value.reference_uuid)
                return '[Unavailable record]' if card is None or card.deletion_mark else card.description
            key = (target, value.reference_uuid.int)
            if key not in batch.presentations:
                view = batch.view()
                if target not in batch.checked_targets:
                    if (manager._backend is not view._backend
                            or manager._catalogs._metadata._database_id != view.database_id
                            or manager._catalogs._metadata._generation != view.configuration_generation
                            or view.catalog_schema(manager._schema.identity) != manager._schema):
                        raise BackendError('schema_changed')
                    batch.checked_targets.add(target)
                card = view.read_catalog(manager._key(value.reference_uuid))
                batch.presentations[key] = '[Unavailable record]' if card is None or card.deletion_mark else card.description
            return batch.presentations[key]
        bindings[target] = FormReferenceBinding(manager._value_type, manager.empty_ref(), normalize, presentation)
    if enum_targets:
        from .demos.inventory_enum_runtime import binding as enum_binding
        from yadinassi.forms.form_references import FormEnumBinding
        storage=enum_binding(metadata._root)
        for target,identity,enum_name in enum_targets:
            kind=storage.value_type(identity)
            if kind.name!=enum_name:raise ValueError('enum target source mismatch')
            bindings[target]=FormEnumBinding(storage,identity)
            managers[target]=storage._entry(identity)[2]
    scope = FormReferenceScope(bindings=bindings)
    if targets and not enum_targets:
        from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
        from .configuration_catalog import CatalogObjectSession
        from .configuration_document import DocumentObjectSession
        from .demos.inventory_application_sessions import InventoryDocumentSession
        from .demos.inventory_host_operations import InventoryRootOperations
        if type(owned.context.backend) is SQLiteCatalogBackend:
            if type(owned) is CatalogObjectSession or type(owned) is DocumentObjectSession:
                scope._batch_read = lambda: _ordinary_reference_read(owned, document=type(owned) is DocumentObjectSession)
            elif type(owned) is InventoryDocumentSession and type(owned.operations) is InventoryRootOperations:
                @contextmanager
                def inventory_read():
                    if owned.context.backend is not owned._backend or owned.operations.backend is not owned._backend:
                        raise BackendError('schema_changed')
                    with owned.operations._reference_read() as view:
                        yield view
                scope._batch_read = inventory_read
    def enroll(interpreter):
        other = interpreter._catalogs
        if other is None or other._context.backend is not owned.context.backend:
            raise ValueError('reference activation backend mismatch')
        snapshot = other._metadata
        snapshot._snapshot()
        if (snapshot._database_id != metadata._database_id or snapshot._generation != metadata._generation):
            raise ValueError('reference activation identity mismatch')
        for target, identity, name in targets:
            if other._manager_by_metadata_uuid(identity)._schema != managers[target]._schema:
                raise ValueError('reference activation schema mismatch')
        if enum_targets:
            source=enum_binding(snapshot._root)
            for target,identity,enum_name in enum_targets:
                if source.value_type(identity).name!=enum_name:raise ValueError('enum activation schema mismatch')
                previous=scope.targets[target]
                if source is not previous.storage and all(source is not b for b in previous.sources):
                    scope.targets[target]=FormEnumBinding(previous.storage,identity,(*previous.sources,source))
        enrolled.add(snapshot)
    return scope, managers, enroll
