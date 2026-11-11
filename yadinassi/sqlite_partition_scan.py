"""Bounded merge of two ordered cursors on one caller-owned read snapshot.

The caller checks declaration/FK and payload byte limits before opening these
cursors. This helper neither changes the transaction nor owns the connection.
"""
from uuid import UUID
from .catalog_backend import BackendError
from .document_backend import DocumentKey


def recorder_key(database_id, document, record):
    try:
        key = DocumentKey(database_id, UUID(document), UUID(record))
        if (type(document) is not str or type(record) is not str
                or not key.document_id.int or not key.record_id.int
                or (str(key.document_id), str(key.record_id)) != (document, record)):
            raise ValueError('noncanonical recorder identity')
        return key
    except (ValueError, TypeError, AttributeError):
        raise BackendError('integrity') from None


def ordered_partitions(metadata, movements, *, max_partitions, max_rows):
    """Yield each stored partition, including empties; reject unmatched rows.

    Payload buffering is at most one partition, already covered by the source's
    preflight byte limit. No per-partition SQL or IN-list construction occurs.
    The caller closes both cursors, including on decoder failure/interruption.
    """
    current = next(movements, None)
    partition_count = row_count = 0
    for document, record, revision in metadata:
        partition_count += 1
        if partition_count > max_partitions:
            raise BackendError('unsupported')
        rows = []
        while current is not None and current[:2] == (document, record):
            row_count += 1
            if row_count > max_rows:
                raise BackendError('unsupported')
            rows.append(current[2:])
            current = next(movements, None)
        yield document, record, revision, rows
    if current is not None:
        raise BackendError('integrity')
