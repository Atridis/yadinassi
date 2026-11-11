"""Bounded synchronous BSL transactions over the explicit v11 host journal.

Pending Write is staging, not persistence. Native transaction parity is not claimed.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from uuid import UUID, uuid4
from dataclasses import dataclass
from .catalog_backend import BackendError
from .transaction_backend import TransactionRequest

_execution = ContextVar('database_execution', default=None)
_execution_backend = ContextVar('database_execution_backend', default=None)
_admission_allowed = ContextVar('database_transaction_admission', default=True)


@contextmanager
def admission(allowed):
    """A nested callee cannot widen its synchronous caller's admission.

    Bind this to the dynamic call boundary, not to the routine's persistent VM:
    configured common-module owners are reused on both allowed and denied paths.
    """
    token = _admission_allowed.set(_admission_allowed.get() and allowed)
    try:
        yield
    finally:
        _admission_allowed.reset(token)



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


def require_admission():
    if not _admission_allowed.get(): raise BackendError('unsupported')


def active(backend):
    """Inspect only this synchronous execution's journal; never open or clean up.

    Unavailable, foreign and uncertain owners are not reported as inactive.
    This status function grants no transaction or callback authority.
    """
    from .sqlite_catalog import SQLiteCatalogBackend
    if (not _admission_allowed.get() or type(backend) is not SQLiteCatalogBackend
            or _execution.get() is None or backend is not _execution_backend.get()
            or backend.format_version not in (11, 12, 13, 14, 15, 16)):
        raise BackendError('unsupported')
    if backend._closed: raise BackendError('closed')
    transaction = current(backend)
    if transaction is None: return False
    if transaction.unit.state != 'open': raise BackendError('uncertain_commit')
    return True


def begin(backend):
    from .sqlite_catalog import SQLiteCatalogBackend
    if (not _admission_allowed.get() or type(backend) is not SQLiteCatalogBackend
            or _execution.get() is None or backend is not _execution_backend.get()):
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
    if not _admission_allowed.get(): raise BackendError('unsupported')
    if backend is not _execution_backend.get(): raise BackendError('unsupported')
    transaction = _registered(backend) if backend is not None else None
    if transaction is None: raise BackendError('unsupported')
    if transaction.owner is not _execution.get():
        if _execution.get() is None or transaction.unit.state not in ('uncertain', 'committed'):
            raise BackendError('unsupported')
        transaction.owner = _execution.get()
    transaction.commit()


def rollback(backend):
    if not _admission_allowed.get(): raise BackendError('unsupported')
    transaction = current(backend) if backend is not None else None
    if transaction is None: raise BackendError('unsupported')
    transaction.rollback()


class Transaction:
    def __init__(self, backend, owner, *, operation_id=None):
        if operation_id is not None and (type(operation_id) is not UUID or not operation_id.int):
            raise BackendError("invalid_input")
        self.backend, self.owner = backend, owner
        self.unit = None
        self.participants = ()
        self.prepared = None
        self.leases = 0
        self.unit = backend.begin_unit_of_work(uuid4() if operation_id is None else operation_id)

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
        participants = (*self.participants, (participant, attr, len(self.unit.requests)))
        setattr(participant, attr, pending)
        try: self.unit.stage(TransactionRequest(kind, draft, expected))
        except BaseException:
            setattr(participant, attr, None)
            raise
        self.participants = participants

    @contextmanager
    def savepoint(self):
        """One document lifecycle may own several journal entries atomically."""
        self._open()
        before = self.participants
        try:
            with self.unit.savepoint():
                yield
        except BaseException:
            for participant, attr, _ in self.participants[len(before):]:
                if hasattr(participant, '_rollback_pending'): participant._rollback_pending()
                else: setattr(participant, attr, None)
            self.participants = before
            raise

    def _prepare(self):
        """Validate and allocate all acceptance images BEFORE the durable commit."""
        prepared = []
        for participant, attr, index in self.participants:
            outcome = self.unit._results[index]
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
        for participant, attr, _ in self.participants:
            if hasattr(participant, '_rollback_pending'): participant._rollback_pending()
            else: setattr(participant, attr, None)

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


@dataclass(frozen=True, slots=True)
class RootOperationReceipt:
    """Host-lifetime immutable journal envelope; not a durable restart token."""
    operation_id: UUID
    state: str
    requests: tuple = ()
    outcomes: tuple = ()
    accepted: bool = False
    error: str | None = None


def require_host_root(backend):
    """Only the exact v13 forms grant, outside every BSL activation.

    This host entry point is not an alternate root for scalar recorder or v14
    accumulation journals. BSL TransactionActive remains separately read-only.
    """
    from .sqlite_catalog import SQLiteCatalogBackend
    from .configuration_posting_application import PostingApplicationConfiguration, PROFILE, canonical
    require_admission()
    if (type(backend) is not SQLiteCatalogBackend or _execution.get() is not None
            or _execution_backend.get() is not None or _registered(backend) is not None
            or backend.format_version != 13
            or type(backend.posting_configuration) is not PostingApplicationConfiguration
            or backend.posting_configuration.profile != PROFILE):
        raise BackendError('unsupported')
    if backend._closed: raise BackendError('closed')
    configuration = canonical(backend.posting_configuration)
    if backend.export_configuration() != dict(configuration.files):
        raise BackendError('schema_changed')


class RootOperation:
    """Trusted host-only coordinator with preallocated durable outcome images.

    The callback runs once. Recovery releases retained resources and resolves
    the exact frozen journal, never a callback, form dispatch or posting handler.
    """
    def __init__(self, backend, operation_id):
        self._admit_root(backend)
        if type(operation_id) is not UUID or not operation_id.int:
            raise BackendError('invalid_input')
        self.backend = backend
        self.receipt = RootOperationReceipt(operation_id, 'prepared')
        self._rejected = RootOperationReceipt(operation_id, 'rejected', error='operation_failed')
        self._cleanup = RootOperationReceipt(operation_id, 'uncertain', error='cleanup_required')
        self._transaction = None
        self._images = None
        self._commit_attempted = False

    @staticmethod
    def _admit_root(backend):
        # Separate trusted host adapters may supply another exact source grant.
        # This public coordinator never broadens the original v13 admission.
        require_host_root(backend)

    @property
    def locked(self):
        transaction = self._transaction
        return (self.receipt.state in ('prepared', 'uncertain')
            or self.receipt.state == 'committed' and not self.receipt.accepted
            or transaction is not None and (transaction.leases
                or transaction.unit._view._connection is not None))

    def _enter(self):
        self._admit_root(self.backend)
        # Allocate the return container before installing either context. A
        # tuple built on return could fail after both tokens were acquired.
        tokens = [None, None]
        tokens[0] = _execution.set(object())
        try: tokens[1] = _execution_backend.set(self.backend)
        except BaseException:
            _execution.reset(tokens[0]); raise
        return tokens

    def _leave(self, tokens):
        transaction = self._transaction
        # Retain actual ownership when SQLite release failed. _closed alone
        # is insufficient: a failed connection.close can leave locks alive.
        if transaction is None or (not transaction.leases and transaction.unit._view._connection is None):
            self.backend._bsl_transaction = None
        _execution_backend.reset(tokens[1]); _execution.reset(tokens[0])

    def run(self, callback):
        if self.receipt.state != 'prepared' or not callable(callback):
            raise BackendError('conflict')
        tokens = None
        transaction = None
        try:
            tokens = self._enter()
            transaction = Transaction(self.backend, _execution.get(), operation_id=self.receipt.operation_id)
            self._transaction = transaction
            self.backend._bsl_transaction = transaction
            callback()
            if transaction.leases or not transaction.participants:
                raise BackendError('unsupported')
            requests, outcomes = transaction.unit.requests, transaction.unit._results
            # Every final immutable image exists before COMMIT; neither failure
            # handling nor successful installation needs a post-COMMIT allocation.
            self._images = (
                RootOperationReceipt(self.receipt.operation_id, 'uncertain', requests, outcomes, False, 'uncertain_commit'),
                RootOperationReceipt(self.receipt.operation_id, 'committed', requests, outcomes, False, 'acceptance_required'),
                RootOperationReceipt(self.receipt.operation_id, 'committed', requests, outcomes, True),
                RootOperationReceipt(self.receipt.operation_id, 'not_committed', requests, outcomes, False, 'conflict'))
            self.receipt = self._images[0]
            self._commit_attempted = True
            transaction.commit()
            self.receipt = self._images[2]
        except BaseException as error:
            if transaction is None:
                self.receipt = self._rejected
            elif transaction.unit.state in ('uncertain', 'committed'):
                # Publish certainty BEFORE fallible connection cleanup. The
                # pending participants and exact envelope stay reachable even
                # if close itself is interrupted or exhausts memory.
                self.receipt = self._images[1 if transaction.unit.state == 'committed' else 0]
                transaction.unit.close()
            else:
                self.receipt = self._cleanup
                transaction.rollback()
                self.receipt = self._rejected
            if not isinstance(error, Exception) or isinstance(error, MemoryError): raise
        finally:
            if tokens is not None: self._leave(tokens)
        return self.receipt

    def release_for_resolution(self):
        """Release only this operation's retained SQL resources, no replay."""
        require_admission()
        if _execution.get() is not None or _execution_backend.get() is not None:
            raise BackendError('unsupported')
        registered = _registered(self.backend)
        transaction = self._transaction
        if registered is not None and registered is not transaction:
            raise BackendError('unsupported')
        if transaction is not None:
            if transaction.leases: raise BackendError('unsupported')
            transaction.unit.close()
            if transaction.unit._view._connection is not None:
                raise BackendError('uncertain_commit')
            if not self._commit_attempted:
                transaction._unlock(); self.receipt = self._rejected
        if registered is transaction: self.backend._bsl_transaction = None

    def resolve(self):
        self.release_for_resolution()
        self._admit_root(self.backend)
        if self.receipt.state not in ('uncertain', 'committed') or self.receipt.accepted:
            return self.receipt
        transaction = self._transaction
        if transaction is None or transaction.leases:
            raise BackendError('unsupported')
        outcomes = self.backend.resolve_unit_of_work(self.receipt.operation_id, self.receipt.requests)
        if outcomes is None:
            if self.receipt.state == 'committed': raise BackendError('integrity')
            transaction._unlock()
            self.receipt = self._images[3]
            return self.receipt
        if outcomes != self.receipt.outcomes: raise BackendError('integrity')
        # Publish known committed before acceptance, which can still fail.
        self.receipt = self._images[1]
        transaction.unit.state = 'committed'
        transaction._install()
        self.receipt = self._images[2]
        return self.receipt
