"""Independent stdlib reference for the Склады db.update benchmark fixture.

This is a read/modify/write reference, not a catalog backend. It assumes the
admitted fixture has no custom fields, sections, hierarchy or write hooks.
Schema/source admission is deliberately not reproduced. Each iteration reads
a detached scalar record, then commits an optimistic update without a receipt.
Each UPDATE commits on its own in SQLite autocommit mode. Connection setup
and verify() are untimed.
"""
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import sqlite3
from uuid import UUID


@dataclass(frozen=True)
class Record:
    record_id: str
    revision: int
    code: str
    description: str
    deletion_mark: int


class StaleRevisionError(RuntimeError):
    """The detached record changed before its write transaction."""


class SQLiteUpdateReference:
    def __init__(self, path, catalog_id, rid, n):
        if type(n) is not int or n < 0:
            raise ValueError('iterations must be a nonnegative integer')
        self.path = Path(path).resolve()
        self.catalog_id = str(UUID(str(catalog_id)))
        self.record_id = str(UUID(str(rid)))
        self.n = n
        self._reader = self._connect(True)
        try:
            self._writer = self._connect()
            if self._reader.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                raise ValueError('reference requires DELETE journal mode')
            row = self._reader.execute(
                'SELECT physical_name FROM catalog_storage_map WHERE catalog_id=?',
                (self.catalog_id,)).fetchone()
            if row is None or type(row[0]) is not str:
                raise ValueError('catalog mapping missing')
            self.table = '"' + row[0].replace('"', '""') + '"'
            self.read_record()  # Setup verifies that the requested record exists.
        except BaseException:
            self.close()
            raise
        self._first = None

    def _connect(self, readonly=False):
        connection = sqlite3.connect(
            self.path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
            uri=True, isolation_level=None, timeout=.2)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA synchronous=FULL')
        except BaseException:
            connection.close()
            raise
        return connection

    def close(self):
        try:
            if hasattr(self, '_writer'):
                self._writer.close()
        finally:
            self._reader.close()

    def read_record(self):
        with closing(self._reader.execute(
                f'SELECT record_id,revision,code,description,deletion_mark FROM {self.table} '
                'WHERE record_id=?', (self.record_id,))) as cursor:
            row = cursor.fetchone()
        if row is None:
            raise ValueError('record missing')
        return Record(*row)

    def update_record(self, record, description):
        if type(description) is not str or len(description) > 100:
            raise ValueError('fixture Description must be a string of at most 100 characters')
        if record.record_id != self.record_id:
            raise ValueError('wrong record')
        with closing(self._writer.execute(
                f'UPDATE {self.table} SET revision=revision+1,code=?,description=?,deletion_mark=? '
                'WHERE record_id=? AND revision=?',
                (record.code, description, record.deletion_mark,
                 self.record_id, record.revision))) as cursor:
            if cursor.rowcount != 1:
                raise StaleRevisionError('stale revision')

    def __call__(self):
        self._first = None
        total = Decimal(0)
        for i in range(1, self.n + 1):
            record = self.read_record()
            if self._first is None:
                self._first = record
            self.update_record(record, str(i))
            total += 1
        return total

    def verify(self):
        """Verify persisted result independently, outside timing; raise on mismatch."""
        if self.n == 0:
            return
        if self._first is None:
            raise AssertionError('reference has not completed')
        actual = self.read_record()
        expected = Record(self.record_id, self._first.revision + self.n,
                          self._first.code, str(self.n), self._first.deletion_mark)
        if actual != expected:
            raise AssertionError((actual, expected))


def make_update_reference(path, catalog_id, rid, n):
    return SQLiteUpdateReference(path, catalog_id, rid, n)
