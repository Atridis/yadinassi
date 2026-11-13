"""Explicit synchronous constants-only transactions, not native DB parity."""
from contextlib import contextmanager
from contextvars import ContextVar
from .source_constants_runtime import SourceConstants

_current = ContextVar('source_transaction_application', default=None)


def forbid_source_transfer():
    app = _current.get()
    if app is not None and app.constant_store is not None and app.constant_store.transaction_active:
        raise ValueError('source transaction cannot cross an asynchronous or client/server boundary')


@contextmanager
def execution(application):
    previous = _current.get()
    if previous is application:
        yield
        return
    forbid_source_transfer()
    token = _current.set(application)
    try:
        try:
            yield
        except BaseException:
            store = application.constant_store
            if store is not None and store.transaction_active:
                store.rollback_transaction()
            raise
        else:
            store = application.constant_store
            if store is not None and store.transaction_active:
                store.rollback_transaction()
                raise ValueError('unfinished source transaction rolled back at execution boundary')
    finally:
        _current.reset(token)


class SourceTransactionCall:
    def __init__(self, application, operation):
        self.owner = SourceConstants(application)
        self.operation = operation

    def __call__(self, *args):
        raise ValueError('source transactions require an interpreter invocation')

    def invoke(self, caller, values):
        if values:
            raise TypeError('source transaction functions take no arguments; lock modes unsupported')
        store = self.owner._store(caller)
        app = self.owner._application()
        if (_current.get() is not app or caller._scheduler.pending
                or not getattr(caller, '_transaction_activation_allowed', True)):
            raise ValueError('source transactions require owning synchronous execution')
        from .database_transactions import require_admission
        require_admission()
        if self.operation == 'active':
            store._open()
            return store.transaction_active
        return getattr(store, self.operation + '_transaction')()
