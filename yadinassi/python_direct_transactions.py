"""Lazy execution-local standalone direct SQLite transactions."""
from contextlib import contextmanager
from types import MethodType
from threading import get_ident as _thread_id
from .experimental_naked_boundaries import BoundaryViolation
from .values import HostFunction
from . import database_transactions as tx

class _Owner:
    __slots__=('backend','token','scope','active','allowed','thread')
    def __init__(self,backend,allowed):
        self.backend=backend;self.token=None;self.scope=None;self.active=True;self.allowed=allowed;self.thread=_thread_id()
    def check(self,backend):
        if not self.active or backend is not self.backend or self.thread!=_thread_id():
            raise BoundaryViolation('direct transaction execution owner changed')
        if self.token is None:
            if tx._execution.get() is not None or tx._execution_backend.get() is not None:raise BoundaryViolation('foreign transaction execution owner')
        elif tx._execution.get() is not self.token or tx._execution_backend.get() is not self.backend:
            raise BoundaryViolation('direct transaction execution owner changed')
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
    owner=_Owner(database.backend,getattr(vm,'_transaction_activation_allowed',True) and tx._admission_allowed.get())
    # Admission is narrowed for the whole activation, but no global execution
    # token is installed until canonical BeginTransaction actually runs.
    with tx.admission(owner.allowed):
        try:
            yield owner
        except BaseException as error:
            owner.close(error);raise
        else:owner.close()
        finally:owner.active=False

def check(owner,database):
    if owner is None:
        if tx._execution.get() is not None or tx._execution_backend.get() is not None:raise BoundaryViolation('foreign transaction execution owner')
    elif type(owner) is not _Owner or database is None:
        raise BoundaryViolation('invalid direct transaction execution owner')
    else:owner.check(database.backend)

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
