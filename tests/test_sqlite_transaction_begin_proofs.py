"""Transaction start reuses an admitted identity."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_sqlite_transaction_source as fixture
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite import sqlite_inventory_enum_profile as profile


class Format16TransactionBeginProofTests(unittest.TestCase):
    setUp = fixture.TransactionSourceTests.setUp
    mutate = fixture.TransactionSourceTests.mutate

    def test_identity_reads_once_when_admitted_and_not_again_when_warm(self):
        connect = self.backend._connect
        actual = self.backend.database_id, self.backend.configuration_generation
        for writer, expected in ((False, 1), (False, 0), (True, 1), (False, 1)):
            with self.subTest(writer=writer, source_reads=expected):
                trace = []
                handle = self.backend._read_handle
                if handle is not None:
                    handle.connection.set_trace_callback(trace.append)

                def observe(*args, **kwargs):
                    connection = connect(*args, **kwargs)
                    connection.set_trace_callback(trace.append)
                    return connection

                with patch.object(self.backend, '_connect', side_effect=observe), \
                     patch.object(profile, 'read_source', wraps=profile.read_source) as source:
                    view = self.backend.begin_write(uuid4()) if writer else self.backend.begin_read()
                    with closing(view):
                        self.assertEqual((view.database_id, view.configuration_generation), actual)
                        self.assertIsNot(view.database_id, self.backend.database_id)
                    self.assertEqual(source.call_count, expected)
                if self.backend._read_handle is not None:
                    self.backend._read_handle.connection.set_trace_callback(None)
                self.assertEqual(sum('FROM database_info' in sql for sql in trace), expected)
                probes = [sql for sql in trace if '_receipt WHERE operation_id=' in sql]
                self.assertFalse(probes, probes)
                if writer:
                    self.assertIn('BEGIN IMMEDIATE', trace)

    def test_external_identity_edit_invalidates_read_proof_and_denies_write(self):
        for field, changed, original, error in (
                ('database_uuid', str(uuid4()), str(self.backend.database_id), 'schema_changed'),
                ('generation', 2, 1, 'integrity')):
            with self.subTest(field=field):
                for _ in range(2):
                    with closing(self.backend.begin_read()): pass
                self.mutate(f'UPDATE database_info SET {field}=? WHERE singleton=1', (changed,))
                try:
                    for begin in (self.backend.begin_read, lambda: self.backend.begin_write(uuid4())):
                        with self.assertRaisesRegex(BackendError, error):
                            begin()
                        self.assertIsNone(self.backend._active)
                finally:
                    self.mutate(f'UPDATE database_info SET {field}=? WHERE singleton=1', (original,))
                with closing(self.backend.begin_read()) as view:
                    self.assertEqual((view.database_id, view.configuration_generation),
                                     (self.backend.database_id, self.backend.configuration_generation))

    def test_warm_read_rejects_changed_backend_generation(self):
        with closing(self.backend.begin_read()): pass
        with patch.object(self.backend, 'configuration_generation', 2):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                self.backend.begin_read()
        self.assertIsNone(self.backend._active)
        with closing(self.backend.begin_read()): pass
