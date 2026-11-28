"""A source tuple belongs to one active SQLite transaction, never a later one."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlite_test_templates import copy_main_demo

from test_main_demo_configuration import source
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.db.sqlite import sqlite_inventory_enum_profile as profile


class TransactionSourceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path = Path(folder.name)/'demo.sqlite'
        copy_main_demo(self.path)
        self.backend = SQLiteCatalogBackend(self.path); self.addCleanup(self.backend.close)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql, args); db.commit()

    def test_one_fresh_source_read_per_read_and_write_transaction(self):
        original = profile.read_source
        with patch.object(profile, 'read_source', wraps=original) as read:
            for writer in (False, True, False):
                view = self.backend.begin_write(uuid4()) if writer else self.backend.begin_read()
                with closing(view): self.assertTrue(view.catalogs())
                self.assertFalse(view._connection)
            self.assertEqual(read.call_count, 3)

    def test_standalone_admit_still_reads_source(self):
        with closing(self.backend.begin_read()) as view:
            with patch.object(profile, 'read_source', wraps=profile.read_source) as read:
                self.assertEqual(profile.admit(view._connection, self.backend.database_id,
                    self.backend._schemas, self.backend._document_schemas), self.backend.accumulation_configuration)
                self.assertEqual(read.call_count, 1)

    def test_reader_blocks_external_commit_and_next_begin_is_fresh(self):
        original = profile.read_source
        def read_then_commit(connection, **kwargs):
            result = original(connection, **kwargs)
            with closing(sqlite3.connect(self.path, timeout=0)) as writer:
                writer.execute("UPDATE configuration_file SET content=x'00' WHERE path='Configuration.xml'")
                with self.assertRaises(sqlite3.OperationalError): writer.commit()
                writer.rollback()
            return result
        with patch.object(profile, 'read_source', side_effect=read_then_commit):
            with closing(self.backend.begin_read()) as view:
                self.assertTrue(view.catalogs())
        self.mutate("UPDATE configuration_file SET content=x'00' WHERE path='Configuration.xml'")
        for begin in (self.backend.begin_read, lambda: self.backend.begin_write(uuid4())):
            with self.assertRaises(BackendError): begin()
            self.assertIsNone(self.backend._active)

    def test_rehashed_source_change_between_transactions_is_refused(self):
        with closing(self.backend.begin_read()): pass
        with closing(sqlite3.connect(self.path)) as db:
            raw = db.execute("SELECT content FROM configuration_file WHERE path='Configuration.xml'").fetchone()[0]+b'\n'
        self.mutate("UPDATE configuration_file SET content=?,sha256=? WHERE path='Configuration.xml'", (raw, sha256(raw).hexdigest()))
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_envelope_refuses_malformed_rows_before_reading_payload(self):
        with closing(sqlite3.connect(':memory:')) as db:
            from yadinassi.db.sqlite.sqlite_catalog import _APPLICATION_ID
            db.execute(f'PRAGMA application_id={_APPLICATION_ID}')
            db.execute('PRAGMA user_version=16')
            db.execute('CREATE TABLE migration_marker(unused)')
            db.execute('CREATE TABLE configuration_file(path,kind,content,sha256)')
            payload_sql = 'SELECT path,kind,content,sha256 FROM configuration_file'
            for label, rows, reason in (
                ('empty', (), 'unsupported'),
                ('path type', ((b'x', 'xml', b'', '0'*64),), 'integrity'),
                ('path length', (('x'*257, 'xml', b'', '0'*64),), 'integrity'),
                ('content type', (('x', 'xml', 'not a blob', '0'*64),), 'integrity'),
                ('digest type', (('x', 'xml', b'', b'0'*64),), 'integrity'),
                ('digest length', (('x', 'xml', b'', '0'*63),), 'integrity'),
                ('row count before shape', (('x', 'xml', b'', '0'),)*2049, 'unsupported'),
            ):
                with self.subTest(label=label):
                    db.set_trace_callback(None)
                    db.execute('DELETE FROM configuration_file')
                    db.executemany('INSERT INTO configuration_file VALUES(?,?,?,?)', rows)
                    trace = []
                    db.set_trace_callback(trace.append)
                    with self.assertRaisesRegex(BackendError, f'^{reason}$'):
                        profile.read_source(db)
                    self.assertNotIn(payload_sql, trace)
            for count, reason in ((1, 'integrity'), (8, 'unsupported')):
                with self.subTest(oversize_blob_rows=count):
                    db.set_trace_callback(None)
                    db.execute('DELETE FROM configuration_file')
                    db.executemany("INSERT INTO configuration_file VALUES('x','xml',zeroblob(1048577),?)",
                                   [('0'*64,)]*count)
                    trace = []
                    db.set_trace_callback(trace.append)
                    with self.assertRaisesRegex(BackendError, f'^{reason}$'):
                        profile.read_source(db)
                    self.assertNotIn(payload_sql, trace)

    def test_register_schema_validation_is_not_skipped(self):
        self.mutate('DELETE FROM accumulation_register_schema')
        with self.assertRaises(BackendError): self.backend.begin_write(uuid4())
        self.assertIsNone(self.backend._active)

    def test_ddl_change_is_not_hidden_by_previous_source(self):
        with closing(self.backend.begin_read()): pass
        self.mutate('CREATE TABLE unexpected (value TEXT)')
        with self.assertRaises(BackendError): self.backend.begin_read()
