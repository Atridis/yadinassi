"""Bounded synchronous BSL transactions over the explicit v11 host journal.

Pending Write is staging, not persistence. Native transaction parity is not claimed.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from uuid import uuid4
from .catalog_backend import BackendError
from .transaction_backend import TransactionRequest

_execution = ContextVar('database_execution', default=None)
_execution_backend = ContextVar('database_execution_backend', default=None)


def _registered(backend):
    # Logical/mock backends may synthesize arbitrary attributes in __getattr__.
    # Only an explicitly stored, exact coordinator bound to this backend owns
    # a transaction; merely asking for a missing attribute must have no effect.
    if backend is None: return None
    try: fields = object.__getattribute__(backend, '__dict__')
    except AttributeError: return None
    transaction = fields.get('_bsl_transaction')
    if transaction is not None and (type(transaction) is not Transaction or transaction.backend is not backend):
        raise BackendError('unsupported')
    return transaction


def current(backend):
    transaction = _registered(backend)
    if transaction is not None and transaction.owner is not _execution.get():
        raise BackendError('unsupported')
    return transaction


def forbid_transfer(backend):
    if backend is not None and current(backend) is not None:
        raise BackendError('unsupported')


@contextmanager
def execution(backend):
    """Imports share the synchronous token; a later root execution never does."""
    if _execution.get() is not None:
        if backend is not _execution_backend.get():
            # Standalone object preparation uses a bounded no-DB interpreter.
            # Preserve that path unless either execution owns an explicit tx.
            if current(_execution_backend.get()) is not None or current(backend) is not None:
                raise BackendError('unsupported')
        yield
        return
    if backend is None:
        yield
        return
    token = _execution.set(object())
    backend_token = _execution_backend.set(backend)
    try:
        try:
            yield
        except BaseException as error:
            transaction = _registered(backend)
            if transaction is not None and transaction.owner is _execution.get():
                try:
                    if transaction.unit.state in ('uncertain', 'committed'):
                        transaction.commit()
                    else: transaction.rollback()
                except BaseException as cleanup:
                    if (not isinstance(cleanup, Exception) or isinstance(cleanup, MemoryError)) and isinstance(error, Exception) and not isinstance(error, MemoryError):
                        raise
            raise
        else:
            transaction = current(backend)
            if transaction is not None: transaction.finish_execution()
    finally:
        _execution_backend.reset(backend_token)
        _execution.reset(token)


def begin(backend):
    from .sqlite_catalog import SQLiteCatalogBackend
    if type(backend) is not SQLiteCatalogBackend or _execution.get() is None or backend is not _execution_backend.get():
        raise BackendError('unsupported')
    if current(backend) is not None: raise BackendError('unsupported')
    # Reserve the owner slot before acquiring a write connection.
    backend._bsl_transaction = None
    transaction = Transaction(backend, _execution.get())
    try: backend._bsl_transaction = transaction
    except BaseException:
        transaction.unit.rollback()
        raise


def commit(backend):
    if backend is not _execution_backend.get(): raise BackendError('unsupported')
    transaction = _registered(backend) if backend is not None else None
    if transaction is None: raise BackendError('unsupported')
    if transaction.owner is not _execution.get():
        if _execution.get() is None or transaction.unit.state not in ('uncertain', 'committed'):
            raise BackendError('unsupported')
        transaction.owner = _execution.get()
    transaction.commit()


def rollback(backend):
    transaction = current(backend) if backend is not None else None
    if transaction is None: raise BackendError('unsupported')
    transaction.rollback()


class Transaction:
    def __init__(self, backend, owner):
        self.backend, self.owner = backend, owner
        self.unit = None
        self.participants = ()
        self.prepared = None
        self.leases = 0
        self.unit = backend.begin_unit_of_work(uuid4())

    def _open(self):
        if self.unit.state != 'open': raise BackendError('uncertain_commit')
        if self.leases: raise BackendError('unsupported')

    def stage(self, participant, kind, draft, expected, pending):
        self._open()
        if any(item[0] is participant for item in self.participants):
            raise BackendError('unsupported')
        attr = '_pending_write' if hasattr(participant, '_pending_write') else '_pending'
        if getattr(participant, attr) is not None: raise BackendError('uncertain_commit')
        # Allocate registration before any SQL, then freeze before stage. If SQL
        # fails the host savepoint restores it and the edit buffer stays usable.
        participants = (*self.participants, (participant, attr))
        setattr(participant, attr, pending)
        try: self.unit.stage(TransactionRequest(kind, draft, expected))
        except BaseException:
            setattr(participant, attr, None)
            raise
        self.participants = participants

    def _prepare(self):
        """Validate and allocate all acceptance images BEFORE the durable commit."""
        prepared = []
        for (participant, attr), outcome in zip(self.participants, self.unit._results):
            shadow = object.__new__(type(participant))
            shadow.__dict__ = participant.__dict__.copy()
            sections = tuple(getattr(participant, '_sections', {}).values())
            if sections:
                copies = {}
                for name, section in participant._sections.items():
                    clone = object.__new__(type(section)); clone.__dict__ = section.__dict__.copy()
                    copies[name] = clone
                shadow._sections = copies
            if attr == '_pending_write' and hasattr(participant, '_accept_outcome'):
                shadow._accept_outcome(outcome.result)
            else: shadow._accept(outcome.result)
            if sections: shadow._sections = participant._sections
            prepared.append((participant, shadow.__dict__, sections))
        return tuple(prepared)

    def _install(self):
        # All dictionaries, refs, UUIDs and section lists already exist. Keep
        # prepared images until installation ends so retry is idempotent.
        for participant, values, sections in self.prepared:
            participant.__dict__ = values
            for section in sections: section._dirty = False
        self.backend._bsl_transaction = None

    def commit(self):
        if self.leases: raise BackendError('unsupported')
        if self.unit.state == 'uncertain':
            self.backend._bsl_transaction = None
            try:
                results = self.backend.resolve_unit_of_work(self.unit.operation_id, self.unit.requests)
            finally:
                self.backend._bsl_transaction = self
            if results is None:
                self._unlock(); self.backend._bsl_transaction = None
                raise BackendError('conflict')
            if results != self.unit._results: raise BackendError('uncertain_commit')
            self.unit.state = 'committed'
        elif self.unit.state == 'open':
            if not self.participants:
                self.unit.rollback(); self.backend._bsl_transaction = None
                return
            self.prepared = self._prepare()
            self.unit.commit()
        elif self.unit.state != 'committed': raise BackendError('closed')
        self._install()

    def _unlock(self):
        for participant, attr in self.participants: setattr(participant, attr, None)

    def rollback(self):
        if self.leases: raise BackendError('unsupported')
        if self.unit.state in ('uncertain', 'committed'):
            # Never describe an already committed transaction as rolled back.
            self.commit()
            raise BackendError('conflict')
        self.unit.rollback(); self._unlock(); self.backend._bsl_transaction = None

    def finish_execution(self):
        if self.unit.state in ('uncertain', 'committed'):
            # Resolve while still owning the token; no replay. On failed
            # resolution retain the locked buffers and pending journal.
            self.commit()
        else:
            self.rollback()
            raise BackendError('unsupported')

    def read_lease(self):
        from .sqlite_catalog import _View, _close_document_scan
        transaction = self
        class Lease(_View):
            def _cache_validation_allowed(self): return False
            def close(self):
                if not self._closed:
                    self._scan_cursor = None
                    _close_document_scan(self)
                    self._validated_sources.clear()
                    self._closed = True
                    transaction.leases -= 1
            def _require(self, write=False, mutate=False):
                if write or mutate: raise BackendError('unsupported')
                return super()._require()
        if self.unit.state != 'open': raise BackendError('uncertain_commit')
        lease = Lease(self.backend, self.unit._view._connection, None)
        self.leases += 1
        return lease


def query_view(manager):
    """Query-only borrowed port; detached object reads remain fail-closed."""
    if current(manager._backend) is None:
        return manager._view()
    view = manager._backend.begin_query_read()
    try:
        if hasattr(manager, '_check_view'):
            manager._check_view(view)
        else:
            metadata = manager._catalogs._metadata
            if (view.database_id != metadata._database_id
                    or view.configuration_generation != metadata._generation
                    or view.catalog_schema(manager._schema.identity) != manager._schema):
                raise BackendError('schema_changed')
        return view
    except BaseException:
        view.close()
        raise
