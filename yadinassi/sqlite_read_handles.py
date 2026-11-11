"""Connection-local integrity proofs for short read leases, never snapshots by path.

The owning backend permits one active view/writer. A retained handle is readonly;
its transaction ends at every lease boundary. Proofs never move to a different
sqlite connection, even when paths, generations and data_version numbers match.
"""
from functools import wraps
from .catalog_backend import BackendError


def lifecycle(function):
    """Serialize only ownership transitions; never queue concurrent operations.

    Views themselves are not a thread-safe API. Reentrancy is needed for the
    existing nested cleanup paths; a foreign transition fails busy immediately.
    """
    @wraps(function)
    def call(owner, *args, **kwargs):
        backend = getattr(owner, '_backend', owner)
        lock = getattr(backend, '_owner_lock', None)
        if lock is None: return function(owner, *args, **kwargs)
        if not lock.acquire(blocking=False): raise BackendError('busy')
        try: return function(owner, *args, **kwargs)
        finally: lock.release()
    return call


def reserve_owner(backend, owner):
    """Atomically reserve, never queue SQL operations on an already owned handle."""
    with backend._owner_lock:
        if backend._closed: raise BackendError('closed')
        if backend._active is not None: raise BackendError('busy')
        try:
            backend._active = owner
        except BaseException:
            # This reservation has no connection yet. An interrupted attribute
            # publication must not strand an empty owner or touch another view.
            if backend._active is owner: backend._active = None
            raise

MAX_PROOFS = 2048
MAX_OWNER_IDENTITIES = 10000


def _bounded_proofs(proofs):
    """Retain only immutable validation facts, not rows, cursors or VM objects."""
    result = {}; owners = 0
    for key, value in proofs.items():
        if len(result) >= MAX_PROOFS:
            break
        if type(value) is frozenset:
            if any(type(item) is not str or len(item) > 36 for item in value):
                continue
            if owners + len(value) > MAX_OWNER_IDENTITIES:
                continue
            owners += len(value)
        elif not (type(value) is tuple and len(value) <= 4
                  and all(type(item) is int and item >= 0 for item in value)):
            continue
        result[key] = value
    return result


class ReadHandle:
    """One actual readonly connection and its successful validation facts.

    No BEGIN/COMMIT/CLOSE here: the existing connection owner remains responsible
    for releasing SQLite locks, including interrupted or uncertain cleanup.
    """
    def __init__(self, connection):
        self.connection = connection
        self.epoch = None
        self.proofs = {}
        self.failed = False

    def invalidate(self):
        self.epoch = None
        self.proofs.clear()
        self.failed = True

    def pin(self):
        """Called only after the owner pinned its real read snapshot."""
        connection = self.connection
        if not connection.in_transaction:
            raise BackendError('closed')
        if connection.execute('PRAGMA query_only').fetchone() != (1,):
            raise BackendError('unsupported')
        row = connection.execute('PRAGMA main.data_version').fetchone()
        if (type(row) is not tuple or len(row) != 1 or type(row[0]) is not int
                or row[0] < 0):
            raise BackendError('integrity')
        epoch = row[0]
        if epoch != self.epoch:
            self.proofs.clear()
        self.epoch = epoch
        self.failed = False
        # A view owns a distinct dictionary; closing it cannot mutate a proof
        # still retained by this handle, and old views never see a later lease.
        return dict(self.proofs)

    def complete(self, proofs):
        """Publish at the old pinned epoch, only after confirmed ROLLBACK.

        Never read data_version here: a foreign commit after ROLLBACK must not
        relabel old validation facts with the next snapshot's epoch.
        """
        if self.connection.in_transaction:
            raise BackendError('busy')
        retained = {} if self.failed else _bounded_proofs(proofs)
        self.proofs = retained
