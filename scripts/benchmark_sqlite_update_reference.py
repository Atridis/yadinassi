"""Independent stdlib reference for the Склады db.update benchmark fixture.

This is a read/modify/write reference, not a catalog backend. It assumes the
admitted fixture has no custom fields, sections, hierarchy or write hooks.
Schema/source admission and operation recovery are deliberately not reproduced.
Each iteration reads a detached scalar record, then commits an optimistic update
and the same receipt format as the catalog writer. No batching or durability
shortcut is used. Setup and verify() belong outside the measured interval.
"""
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


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
        with closing(self._connect(True)) as connection:
            if connection.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                raise ValueError('reference requires DELETE journal mode')
            row = connection.execute(
                'SELECT physical_name FROM catalog_storage_map WHERE catalog_id=?',
                (self.catalog_id,)).fetchone()
            if row is None or type(row[0]) is not str:
                raise ValueError('catalog mapping missing')
            self.table = '"' + row[0].replace('"', '""') + '"'
        self.read_record()  # Setup verifies that the requested record exists.
        self._first = None
        self._last_receipt = None

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

    def read_record(self):
        with closing(self._connect(True)) as connection:
            connection.execute('BEGIN')
            row = connection.execute(
                f'SELECT record_id,revision,code,description,deletion_mark FROM {self.table} '
                'WHERE record_id=?', (self.record_id,)).fetchone()
            connection.commit()
        if row is None:
            raise ValueError('record missing')
        return Record(*row)

    def update_record(self, record, description):
        if type(description) is not str or len(description) > 100:
            raise ValueError('fixture Description must be a string of at most 100 characters')
        if record.record_id != self.record_id:
            raise ValueError('wrong record')
        revision = record.revision + 1
        outcomes = [[self.catalog_id, self.record_id, str(revision), record.code]]
        intent = [self.catalog_id, self.record_id, record.code, description,
                  bool(record.deletion_mark), '[]', revision]
        digest = hashlib.sha256(_json(['write_outcomes_v1', [intent], outcomes]).encode('utf-8')).hexdigest()
        receipt = (str(uuid4()), digest, _json(outcomes))
        with closing(self._connect()) as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                changed = connection.execute(
                    f'UPDATE {self.table} SET revision=revision+1,code=?,description=?,deletion_mark=? '
                    'WHERE record_id=? AND revision=?',
                    (record.code, description, record.deletion_mark,
                     self.record_id, record.revision)).rowcount
                if changed != 1:
                    raise StaleRevisionError('stale revision')
                connection.execute('INSERT INTO commit_receipt VALUES(?,?,?)', receipt)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return receipt

    def __call__(self):
        self._first = None
        self._last_receipt = None
        total = Decimal(0)
        for i in range(1, self.n + 1):
            record = self.read_record()
            if self._first is None:
                self._first = record
            self._last_receipt = self.update_record(record, str(i))
            total += 1
        return total

    def verify(self):
        """Verify persisted result independently, outside timing; raise on mismatch."""
        if self.n == 0:
            return
        if self._first is None or self._last_receipt is None:
            raise AssertionError('reference has not completed')
        actual = self.read_record()
        expected = Record(self.record_id, self._first.revision + self.n,
                          self._first.code, str(self.n), self._first.deletion_mark)
        if actual != expected:
            raise AssertionError((actual, expected))
        with closing(self._connect(True)) as connection:
            receipt = connection.execute(
                'SELECT operation_id,request_hash,revisions_json FROM commit_receipt WHERE operation_id=?',
                (self._last_receipt[0],)).fetchone()
        if receipt != self._last_receipt:
            raise AssertionError('receipt mismatch')


def make_update_reference(path, catalog_id, rid, n):
    return SQLiteUpdateReference(path, catalog_id, rid, n)
