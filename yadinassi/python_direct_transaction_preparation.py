"""One policy-selected main_demo BeforeWrite inside its owning SQL savepoint."""
from contextvars import ContextVar
from threading import get_ident
from . import database_transactions as tx
from .catalog_backend import BackendError
from .experimental_naked_boundaries import BoundaryViolation

_SCOPE=ContextVar('direct_transaction_preparation',default=None)

class _Scope:
    def __init__(self,transaction,receiver,lease,origin):
        self.origin=origin
        self.transaction=transaction;self.backend=transaction.backend;self.receiver=receiver
        self.unit=transaction.unit;self.view=self.unit._view;self.connection=self.view._connection
        self.manager=receiver._manager;self.schema=self.manager._schema
        self.catalogs=self.manager._catalogs;self.metadata=self.catalogs._metadata
        self.key=receiver._key;self.revision=receiver._revision;self.operation=receiver._operation_id
        self.lease=lease;self.owner=tx._execution.get();self.thread=get_ident()
        self.token=None;self.active=False
    def owner_check(self):
        from .execution_policy import current_backend
        if current_backend()!="python-direct":raise BoundaryViolation("catalog preparation execution backend changed")
        from .python_direct_transactions import require_preparation_origin
        if require_preparation_origin(self.backend,expected=self.origin) is not self.origin:
            raise BoundaryViolation("catalog transaction preparation origin changed")
        if (get_ident()!=self.thread or tx._execution.get() is not self.owner
                or tx._execution_backend.get() is not self.backend
                or self.receiver._manager is not self.manager or self.manager._backend is not self.backend
                or self.transaction.unit is not self.unit or self.unit._view is not self.view
                or self.view._connection is not self.connection
                or self.manager._catalogs is not self.catalogs or self.catalogs._metadata is not self.metadata
                or self.manager._schema is not self.schema or self.receiver._key is not self.key
                or self.receiver._revision is not self.revision or self.receiver._operation_id is not self.operation):
            raise BoundaryViolation('catalog transaction preparation owner changed')
        try:
            if tx.current(self.backend) is not self.transaction:raise BackendError('unsupported')
            tx.require_registered_query_lease(self.backend,self.lease)
        except BackendError as error:raise BoundaryViolation('catalog transaction preparation lease changed') from error
    def check(self):
        if not self.active or _SCOPE.get() is not self:raise BoundaryViolation('catalog transaction preparation scope changed')
        try:_SCOPE.reset(self.token)
        except (ValueError,RuntimeError):raise BoundaryViolation('catalog transaction preparation context changed') from None
        self.token=_SCOPE.set(self)
        self.owner_check()
    def enter(self):
        if _SCOPE.get() is not None:raise BoundaryViolation('recursive catalog transaction preparation')
        self.owner_check();self.token=_SCOPE.set(self);self.active=True
    def leave(self):
        if self.active:
            _SCOPE.reset(self.token);self.active=False;self.token=None


def stage_selected_source(receiver,preparation,selected_source):
    from .execution_policy import current_backend
    from .sqlite_catalog import _TRANSACTION_PREPARATION_POLICY_ABI
    from .configuration_main_demo import MainDemoConfiguration,PROFILE
    from .catalog_object_preparation import _prepare_catalog_object,CatalogWriteRefused
    backend=receiver._manager._backend
    cls,policy=_TRANSACTION_PREPARATION_POLICY_ABI
    if (current_backend()!='python-direct' or type(backend) is not cls or backend.format_version!=16
            or type(backend.accumulation_configuration) is not MainDemoConfiguration
            or backend.accumulation_configuration.profile!=PROFILE
            or type(selected_source) is not str or not selected_source
            or type(preparation) is not tuple or len(preparation)!=2
            or preparation[0]!=selected_source or type(preparation[1]) is not bool):
        raise BackendError('unsupported')
    if _SCOPE.get() is not None:raise BoundaryViolation('recursive catalog transaction preparation')
    from .python_direct_transactions import require_preparation_origin
    tx.require_admission()
    origin=require_preparation_origin(backend)
    if receiver._manager._catalogs is not origin.catalogs:
        raise BoundaryViolation('catalog preparation requires the originating root catalog family')
    transaction=tx.current(backend)
    if transaction is None:raise BackendError('unsupported')
    with transaction.savepoint():
        lease=backend.begin_read()
        scope=None
        try:
            scope=_Scope(transaction,receiver,lease,origin)
            scope.enter()
            if policy(backend,scope.schema.identity)!=selected_source:raise BackendError('schema_changed')
            scope.check()
            with tx.admission(False):
                cancel,messages=_prepare_catalog_object(selected_source,receiver,
                    cancel=preparation[1],write_view=lease,_transaction_scope=scope)
            scope.check()
            if cancel:raise CatalogWriteRefused(messages)
            if policy(backend,scope.schema.identity)!=selected_source:raise BackendError('schema_changed')
            draft=receiver._write_draft(complete_sections=True)
            scope.check()
        finally:
            try:
                if scope is not None:scope.leave()
            finally:lease.close()
        if tx.current(backend) is not transaction or tx._execution.get() is not scope.owner:
            raise BoundaryViolation('catalog transaction preparation owner changed')
        expected=receiver._revision;operation=receiver._operation_id
        transaction.stage(receiver,'catalog_create' if expected is None else 'catalog_update',
                          draft,expected,(draft,expected,operation))
        return messages
