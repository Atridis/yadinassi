"""Read each proof once in a physical transaction, never across transactions."""
from contextlib import closing
from dataclasses import replace
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_sqlite_transaction_source as source_fixture
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogDraft, CatalogKey


class SameTransactionProofTests(unittest.TestCase):
    setUp = source_fixture.TransactionSourceTests.setUp
    mutate = source_fixture.TransactionSourceTests.mutate

    def test_writer_uses_fresh_header_and_one_complete_catalog_manifest(self):
        statements = []
        connect = self.backend._connect
        def trace_connection(**kwargs):
            connection = connect(**kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        with patch.object(self.backend, '_connect', side_effect=trace_connection):
            with closing(self.backend.begin_write(uuid4())):
                pass
        for name in ('application_id', 'user_version', 'schema_version'):
            self.assertEqual(statements.count('PRAGMA ' + name), 1)
        manifest_sql = [sql for sql in statements if 'FROM catalog_schema' in sql]
        self.assertEqual(len(manifest_sql), 1)
        self.assertTrue(manifest_sql[0].endswith('LIMIT 4'))  # three exact catalog entries

    def test_corrupt_manifest_even_in_other_catalog_invalidates_latest_admission(self):
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(len(view.catalogs()), 3)
        with closing(sqlite3.connect(self.path)) as connection:
            identity, original = connection.execute('SELECT identity,definition FROM catalog_schema LIMIT 1').fetchone()
            connection.execute('UPDATE catalog_schema SET definition=zeroblob(262145) WHERE identity=?', (identity,))
            connection.commit()
        for begin in (self.backend.begin_read, lambda: self.backend.begin_write(uuid4())):
            with self.assertRaises(BackendError) as err:
                begin()
            self.assertEqual(err.exception.code, 'schema_changed')
            self.assertIsNone(self.backend._active)
        self.mutate('UPDATE catalog_schema SET definition=? WHERE identity=?', (original, identity))
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(len(view.catalogs()), 3)

    def test_exact_schema_reused_for_update_and_receipt(self):
        schema = next(schema for schema in self.backend._schemas if schema.name == 'Склады')
        key = CatalogKey(self.backend.database_id, schema.identity, uuid4())
        draft = CatalogDraft(key, '1', 'before', False, ())
        with closing(self.backend.begin_write(uuid4())) as create:
            create.create(draft)
            previous, = create.commit_outcomes()
        update = replace(draft, description='after')
        operation = uuid4()
        with closing(self.backend.begin_write(operation)) as writer:
            statements = []
            writer._connection.set_trace_callback(statements.append)
            writer.update(update, previous.revision)
            result, = writer.commit_outcomes()
        reads = [sql for sql in statements if sql.startswith('SELECT definition FROM catalog_schema')]
        self.assertEqual(len(reads), 1)
        self.assertEqual(self.backend.resolve_write_outcome(operation, update, previous.revision), result)
        with closing(self.backend.begin_read()) as reader:
            saved = reader.read_catalog(key)
            self.assertEqual((saved.description, saved.revision), ('after', result.revision))
