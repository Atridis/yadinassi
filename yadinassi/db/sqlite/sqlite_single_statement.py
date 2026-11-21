"""Owned SQLite statements outside caller transactions."""
from contextlib import closing

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_read_handles import ReadHandle, lifecycle, reserve_owner


def fetch_one(connection, sql, parameters=()):
    with closing(connection.execute(sql, parameters)) as cursor:
        return cursor.fetchone()


def fetch_all(connection, sql, parameters=()):
    with closing(connection.execute(sql, parameters)) as cursor:
        return cursor.fetchall()


def execute_write(connection, sql, parameters=()):
    with closing(connection.execute(sql, parameters)) as cursor:
        return cursor.rowcount


@lifecycle
def run(backend, operation, *, write=False, authorizer=None):
    """Run one finalized statement on a private idle handle; never start a transaction."""
    from .sqlite_catalog import _PendingConnection, _interruption
    if write and (backend.read_only or authorizer is None):
        raise BackendError('unsupported')
    pending = _PendingConnection(backend)
    reserve_owner(backend, pending)
    try:
        backend._check_file()
        if write:
            if backend._read_handle is not None:
                backend._read_handle.invalidate()
            cached = backend._single_statement_writer
            if cached is None:
                connection = backend._connect(_owner=pending, _single_statement=True)
            else:
                connection, previous = cached
                pending._connection = connection
                backend._single_statement_writer = None
            if cached is None or previous is not authorizer:
                connection.set_authorizer(authorizer)
        else:
            handle = backend._read_handle
            if handle is None:
                connection = backend._connect(_owner=pending, _read_handle=True)
                handle = ReadHandle(connection)
                backend._read_handle = handle
            else:
                connection = handle.connection
                pending._connection = connection
            pending._read_handle = handle

        if connection.in_transaction:
            raise BackendError('busy')
        value = operation(connection)
        if write:
            backend._single_statement_writer = (connection, authorizer)
        backend._active = None
        return value
    except BaseException as error:
        try:
            if pending._connection is None:
                backend._active = None
            else:
                if write:
                    backend._single_statement_writer = None
                pending.close()
        except BaseException as cleanup_error:
            if _interruption(cleanup_error) and not _interruption(error):
                raise
        raise


def close_writer(backend):
    """Close the separately retained, idle autocommit writer."""
    cached = backend._single_statement_writer
    if cached is None:
        return
    from .sqlite_catalog import _PendingConnection
    pending = _PendingConnection(backend)
    reserve_owner(backend, pending)
    pending._connection = cached[0]
    backend._single_statement_writer = None
    pending.close()
