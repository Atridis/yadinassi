"""Lazy execution-local standalone direct SQLite transactions."""
from contextlib import contextmanager
from contextvars import ContextVar
from types import MethodType
from threading import get_ident as _thread_id
from .experimental_naked_boundaries import BoundaryViolation
from .catalog_backend import BackendError
from .values import HostFunction
from . import database_transactions as tx

_ROOT_OWNER=ContextVar('direct_transaction_root_owner',default=None)

class _Owner:
    __slots__=('backend','token','scope','active','allowed','thread','vm','origin_token','database','scheduler','family','generation','vm_generation','profile','context_stack','module_stack','catalogs','catalog_metadata','catalog_dict')
    def __init__(self,backend,allowed,vm):
        self.vm=vm;self.origin_token=None
        self.database=vm.database_context;self.scheduler=vm._scheduler
        self.family=vm._family_owner;self.generation=self.family._family_generation
        self.vm_generation=vm._family_generation;self.profile=vm.compilation_profile
        self.context_stack=vm._context_stack;self.module_stack=vm._module_context_stack
        from .catalogs import _DIRECT_CATALOG_FAMILY_ABI
        catalog_type,self.catalog_dict=_DIRECT_CATALOG_FAMILY_ABI
        candidate=vars(vm).get('_catalogs')
        self.catalogs=candidate if type(candidate) is catalog_type else None
        self.catalog_metadata=(None if self.catalogs is None else
            self.catalog_dict.__get__(self.catalogs,catalog_type).get('_metadata'))
        self.backend=backend;self.token=None;self.scope=None;self.active=True;self.allowed=allowed;self.thread=_thread_id()
    def check(self,backend):
        if not self.active or backend is not self.backend or self.thread!=_thread_id():
            raise BoundaryViolation('direct transaction execution owner changed')
        if self.token is None:
            if tx._execution.get() is not None or tx._execution_backend.get() is not None:raise BoundaryViolation('foreign transaction execution owner')
        elif tx._execution.get() is not self.token or tx._execution_backend.get() is not self.backend:
            raise BoundaryViolation('direct transaction execution owner changed')
    def check_origin(self):
        from . import safe_mode,source_transactions
        if (not self.active or _ROOT_OWNER.get() is not self or self.thread!=_thread_id()
                or self.vm._direct_active is not True or self.vm._family_closed is not False
                or self.vm.database_context is not self.database or self.database.backend is not self.backend
                or self.vm._scheduler is not self.scheduler or self.scheduler.is_active or self.scheduler.pending
                or self.vm._family_owner is not self.family or self.vm._family_released is not False or self.family._family_closed is not False
                or self.vm._family_generation is not self.vm_generation or self.family._family_generation is not self.generation
                or self.vm.compilation_profile is not self.profile or self.vm._configuration_runtime is not None
                or self.vm._context_stack is not self.context_stack or self.vm._module_context_stack is not self.module_stack
                or self.vm.locals is not None or self.vm._has_module_context is not True
                or type(self.vm.execution_context) is not str or self.vm.execution_context!='client'
                or safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None):
            raise BoundaryViolation('direct transaction root activation changed')
        try:_ROOT_OWNER.reset(self.origin_token)
        except (ValueError,RuntimeError):raise BoundaryViolation('direct transaction root context changed') from None
        self.origin_token=_ROOT_OWNER.set(self)
        self.check(self.backend)
    def check_catalog_family(self):
        if self.catalogs is None or vars(self.vm).get('_catalogs') is not self.catalogs:
            raise BoundaryViolation('direct transaction root catalog family changed')
        fields=self.catalog_dict.__get__(self.catalogs,type(self.catalogs))
        if fields.get('_metadata') is not self.catalog_metadata:
            raise BoundaryViolation('direct transaction root catalog metadata changed')
    def start(self):
        self.check(self.backend)
        if self.scope is None:
            scope=tx.execution(self.backend);scope.__enter__()
            self.scope=scope;self.token=tx._execution.get()
    def close(self,error=None):
        scope=self.scope
        if scope is None:
            if tx._execution.get() is not None or tx._execution_backend.get() is not None:
                tx._execution.set(None);tx._execution_backend.set(None)
                raise BoundaryViolation('foreign transaction execution owner')
            return
        changed=(tx._execution.get() is not self.token or tx._execution_backend.get() is not self.backend)
        if changed:
            tx._execution.set(self.token);tx._execution_backend.set(self.backend)
            error=BoundaryViolation('direct transaction execution owner changed')
        try:
            scope.__exit__(type(error) if error is not None else None,error,error.__traceback__ if error is not None else None)
        finally:self.scope=None;self.token=None
        if changed:raise error

@contextmanager
def execution(vm):
    database=vm.database_context
    if database is None:
        yield None;return
    owner=_Owner(database.backend,getattr(vm,'_transaction_activation_allowed',True) and tx._admission_allowed.get(),vm)
    owner.origin_token=_ROOT_OWNER.set(owner)
    # Admission is narrowed for the whole activation, but no global execution
    # token is installed until canonical BeginTransaction actually runs.
    with tx.admission(owner.allowed):
        try:
            yield owner
        except BaseException as error:
            owner.close(error);raise
        else:owner.close()
        finally:
            owner.active=False
            _ROOT_OWNER.reset(owner.origin_token)

def check(owner,database):
    if owner is None:
        if tx._execution.get() is not None or tx._execution_backend.get() is not None:raise BoundaryViolation('foreign transaction execution owner')
    elif type(owner) is not _Owner or database is None:
        raise BoundaryViolation('invalid direct transaction execution owner')
    else:owner.check(database.backend)

def check_current_root_if_present(backend):
    owner=_ROOT_OWNER.get()
    if owner is None:return None
    if type(owner) is not _Owner or owner.backend is not backend:
        raise BoundaryViolation('foreign direct transaction root')
    owner.check_origin()
    owner.check_catalog_family()
    return owner

def require_preparation_origin(backend,*,expected=None):
    owner=_ROOT_OWNER.get()
    if owner is None and expected is None:raise BackendError("unsupported")
    if expected is not None and owner is not expected:
        raise BoundaryViolation("catalog preparation root witness changed")
    if (type(owner) is not _Owner or owner.backend is not backend or not owner.allowed
            or not getattr(owner.vm,'_transaction_activation_allowed',True)):
        raise BoundaryViolation('catalog preparation requires an original direct root activation')
    owner.check_origin()
    owner.check_catalog_family()
    transaction=tx.current(backend)
    if transaction is None or owner.token is None or transaction.owner is not owner.token:
        raise BoundaryViolation('catalog preparation requires the owned direct transaction')
    return owner

def service(context,function):
    from .runtime import _DIRECT_TRANSACTION_ABI
    if type(function) is not HostFunction:return function
    owner=getattr(context,'_direct_transaction_owner',None)
    method=function.function
    if type(method) is not MethodType or method.__func__ not in _DIRECT_TRANSACTION_ABI:return function
    if method.__self__ is not getattr(context,'vm',None):
        raise BoundaryViolation('foreign canonical transaction service')
    if type(owner) is not _Owner:return function
    def invoke(*args):
        if function.function is not method:
            raise BoundaryViolation('transaction service changed during binding')
        if args:raise TypeError('Операция транзакции не принимает аргументов')
        if ((getattr(context,'_eval_depth',None) or [0])[0]
                and method.__func__ is not _DIRECT_TRANSACTION_ABI[3]):
            raise ValueError('Управление транзакцией из Вычислить пока не поддерживается')
        owner.check_origin()
        owner.check(context.vm.database_context.backend)
        # Do not acquire an owner or writer for a denied/pending caller.
        vm=context.vm
        if (not owner.allowed or not getattr(vm,'_transaction_activation_allowed',True)
                or vm._scheduler.is_active or vm._scheduler.pending):
            raise ValueError('Transactions require synchronous execution without pending tasks')
        owner.start()
        try:return method()
        finally:
            # Commit/rollback may leave an uncertain journal. Only the existing
            # coordinator may resolve it; never erase/replay it here.
            if owner.scope is not None and tx._registered(owner.backend) is None:
                owner.close()
    return HostFunction(function.name,invoke,reference_parameters=function.reference_parameters,returns_value=function.returns_value)
