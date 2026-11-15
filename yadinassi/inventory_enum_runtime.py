"""Exact database enum namespace, owned by one interpreter family/context.

Only an explicitly captured lexical point-read snapshot can be reused. This
never discovers transaction authority from a backend's active connection.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from .catalog_backend import BackendError
from .configuration_inventory_enums import InventoryEnumConfiguration, PROFILE
from .configuration_main_demo import MainDemoConfiguration, PROFILE as MAIN_DEMO_PROFILE
from .configuration_inventory_enum_application import InventoryEnumApplicationConfiguration, PROFILE as FORMS_PROFILE
from .database_context import SQLiteDBContext
from .enum_storage_binding import EnumStorageBinding
from .enumerations import BSLEnumerations
from .sqlite_catalog import SQLiteCatalogBackend, _View

_POINT_READ = ContextVar('inventory_enum_point_read', default=None)


class _EnumScope:
    def __init__(self, interpreter, metadata, context, backend, configuration, namespace):
        self.family=interpreter._family_owner
        self.generation=self.family._family_generation
        self.metadata,self.context,self.backend=metadata,context,backend
        self.configuration,self.namespace=configuration,namespace
        self.database_id=backend.database_id
        self.configuration_generation=backend.configuration_generation

    def _require_owner(self):
        if (self.family._family_closed or self.family._family_generation!=self.generation
                or self.family._schema_scopes.get(id(self.context)) is not self.metadata
                or self.metadata._enum_storage_scope is not self
                or self.metadata._enumerations is not self.namespace
                or self.context.backend is not self.backend or self.backend._closed
                or self.backend.format_version!=16
                or self.backend.accumulation_configuration is not self.configuration):
            raise BackendError('closed')

    def _require_snapshot(self, view):
        # Exact read-only view supplied by the getter, not selected from _active.
        if type(view) is _View:
            if (view._backend is not self.backend or view._operation_id is not None
                    or self.backend._active is not view):
                raise BackendError('unsupported')
            view._require()
        else:
            from .database_transactions import require_registered_query_lease
            require_registered_query_lease(self.backend, view)
        self._require_identity(view)

    def _require_identity(self, view):
        if (view.database_id!=self.database_id
                or view.configuration_generation!=self.configuration_generation):
            raise BackendError('schema_changed')

    def require_live(self):
        self._require_owner()
        captured=_POINT_READ.get()
        if captured is not None:
            owner,view=captured
            if owner is not self:raise BackendError('unsupported')
            self._require_snapshot(view)
            return
        # Current execution's authorized transaction supplies a non-owning
        # lease; foreign execution ownership remains rejected by begin_read.
        view=self.backend.begin_read()
        try:self._require_identity(view)
        finally:view.close()


@contextmanager
def read_snapshot(metadata, document_view):
    """Internal lexical witness for conversion inside one captured point read.

    Transaction leases still go through the existing owned borrow path. The
    witness never closes, commits or rolls back its caller's snapshot.
    """
    from .metadata import BSLMetadata
    from .sqlite_documents import DocumentView
    if type(metadata) is not BSLMetadata:raise BackendError('unsupported')
    scope=metadata._enum_storage_scope
    if scope is None:
        yield
        return
    if type(scope) is not _EnumScope:raise BackendError('unsupported')
    if type(document_view) is DocumentView:view=document_view._view
    elif type(document_view) is _View:view=document_view
    else:raise BackendError('unsupported')
    scope._require_owner()
    scope._require_snapshot(view)
    token=_POINT_READ.set((scope,view))
    try:yield
    finally:_POINT_READ.reset(token)


def bind(interpreter,metadata):
    context=interpreter.database_context
    if type(context) is not SQLiteDBContext:return
    backend=context.backend
    if type(backend) is not SQLiteCatalogBackend or backend.format_version!=16:return
    configuration=backend.accumulation_configuration
    if (type(configuration) not in (InventoryEnumConfiguration, InventoryEnumApplicationConfiguration, MainDemoConfiguration)
            or (type(configuration), configuration.profile) not in ((InventoryEnumConfiguration, PROFILE),
                (InventoryEnumApplicationConfiguration, FORMS_PROFILE),
                (MainDemoConfiguration, MAIN_DEMO_PROFILE))):
        raise BackendError('unsupported')
    namespace=BSLEnumerations(configuration.enumerations)
    metadata._enumerations=namespace
    metadata._enum_storage_scope=_EnumScope(interpreter,metadata,context,backend,configuration,namespace)
    # Namespace preparation grants no storage crossing. Construct the guarded
    # binder only after the normal family reopen sequence has completed.


def binding(metadata):
    from .metadata import BSLMetadata
    if type(metadata) is not BSLMetadata or type(metadata._enum_storage_scope) is not _EnumScope:
        raise BackendError('unsupported')
    scope=metadata._enum_storage_scope
    scope.require_live()
    if metadata._enum_storage is None:
        metadata._enum_storage=EnumStorageBinding(scope.backend._enum_domain,
            scope.configuration.enumerations,scope.namespace,require_live=scope.require_live)
    if type(metadata._enum_storage) is not EnumStorageBinding:raise BackendError('unsupported')
    return metadata._enum_storage


def query_binding(catalogs):
    """Optional exact format16 source, never inferred from a parameter's UUID."""
    from .catalogs import BSLCatalogs
    from .metadata import BSLMetadata
    if type(catalogs) is not BSLCatalogs:return None
    metadata=catalogs._metadata._root
    if type(metadata) is not BSLMetadata or metadata._enum_storage_scope is None:return None
    return binding(metadata)


def query_owner(catalogs):
    """No-I/O dispatch only; this never replaces a live binding check."""
    from .catalogs import BSLCatalogs
    from .metadata import BSLMetadata
    if type(catalogs) is not BSLCatalogs:
        return None
    metadata = catalogs._metadata._root
    if type(metadata) is not BSLMetadata or metadata._enum_storage_scope is None:
        return None
    scope = metadata._enum_storage_scope
    if (type(scope) is not _EnumScope or type(scope.context) is not SQLiteDBContext
            or type(scope.backend) is not SQLiteCatalogBackend
            or type(scope.configuration) not in (InventoryEnumConfiguration, InventoryEnumApplicationConfiguration, MainDemoConfiguration)
            or (type(scope.configuration), scope.configuration.profile) not in (
                (InventoryEnumConfiguration, PROFILE),
                (InventoryEnumApplicationConfiguration, FORMS_PROFILE),
                (MainDemoConfiguration, MAIN_DEMO_PROFILE))
            or scope.backend.format_version != 16):
        raise BackendError('unsupported')
    scope._require_owner()
    if scope.metadata is not metadata:
        raise BackendError('closed')
    return scope
