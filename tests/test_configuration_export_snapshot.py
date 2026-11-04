"""Configuration export pins resource checks to the bytes it exports."""
from contextlib import closing
from dataclasses import replace
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_sqlite_catalog_backend import configuration
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import ConfigurationFile
import yadinassi.sqlite_catalog as storage
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class InterleavingConnection:
    def __init__(self, wrapped, before_rows):
        self.wrapped, self.before_rows = wrapped, before_rows
    def __getattr__(self, name): return getattr(self.wrapped, name)
    def execute(self, sql, *args):
        if sql.startswith('SELECT path,content,sha256 FROM configuration_file'):
            self.before_rows()
        return self.wrapped.execute(sql, *args)


class ConfigurationExportSnapshotTests(unittest.TestCase):
    def make_database(self, directory, *, active=True):
        config = configuration()
        files = config.files + (ConfigurationFile('Ext/Тест.bsl', b'', 'module'),
                                ConfigurationFile('Extra.xml', b'\xef\xbb\xbf<x>\r\n</x>', 'xml'))
        config = replace(config, files=files,
                         activation_issues=() if active else ('unsupported fixture',))
        path = Path(directory)/'owned.sqlite'
        backend = SQLiteCatalogBackend.create(path, config, activate=active)
        return path, backend, {item.path:item.content for item in files}

    def test_preflight_and_rows_share_snapshot_against_real_writer(self):
        for limit_kind in ('files', 'bytes'):
            with self.subTest(limit=limit_kind), tempfile.TemporaryDirectory() as directory:
                path, backend, expected = self.make_database(directory)
                payload = b'additional'; name = 'Concurrent.xml'
                args = (name, 'xml', payload, hashlib.sha256(payload).hexdigest())
                limit_name = '_MAX_FILES' if limit_kind == 'files' else '_MAX_CONFIG_BYTES'
                limit = len(expected) if limit_kind == 'files' else sum(map(len, expected.values()))
                outcomes = []
                original_connect = backend._connect
                def writer_attempt():
                    with closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as db:
                        db.execute('BEGIN IMMEDIATE')
                        db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)', args)
                        try:
                            db.execute('COMMIT')
                            outcomes.append('committed')
                        except sqlite3.OperationalError:
                            outcomes.append('locked')
                            db.execute('ROLLBACK')
                def connect(): return InterleavingConnection(original_connect(), writer_attempt)
                try:
                    with patch.object(storage, limit_name, limit), patch.object(backend, '_connect', side_effect=connect):
                        exported = backend.export_configuration()
                    self.assertEqual(outcomes, ['locked'])
                    self.assertEqual(exported, expected)
                    with closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as db:
                        db.execute('BEGIN IMMEDIATE')
                        db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)', args)
                        db.execute('COMMIT')
                    with patch.object(storage, limit_name, limit):
                        with self.assertRaisesRegex(BackendError, 'integrity'):
                            backend.export_configuration()
                finally: backend.close()

    def test_exact_source_survives_active_inactive_and_readonly_exports(self):
        for active in (True, False):
            for readonly in (False, True):
                with self.subTest(active=active, readonly=readonly), tempfile.TemporaryDirectory() as directory:
                    path, backend, expected = self.make_database(directory, active=active)
                    backend.close()
                    before = path.read_bytes()
                    backend = SQLiteCatalogBackend(path, read_only=readonly)
                    try: self.assertEqual(backend.export_configuration(), expected)
                    finally: backend.close()
                    self.assertEqual(path.read_bytes(), before)

    def test_invalid_digest_closes_snapshot_and_releases_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path, backend, expected = self.make_database(directory)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("UPDATE configuration_file SET sha256='invalid' WHERE path='Configuration.xml'")
            try:
                with self.assertRaisesRegex(BackendError, 'integrity'): backend.export_configuration()
                with closing(sqlite3.connect(path, isolation_level=None, timeout=0)) as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('UPDATE configuration_file SET sha256=? WHERE path=?',
                               (hashlib.sha256(expected['Configuration.xml']).hexdigest(), 'Configuration.xml'))
                    db.execute('COMMIT')
                self.assertEqual(backend.export_configuration(), expected)
            finally: backend.close()

    def test_export_works_with_existing_read_or_write_view(self):
        for write in (False, True):
            with self.subTest(write=write), tempfile.TemporaryDirectory() as directory:
                _, backend, expected = self.make_database(directory)
                view = backend.begin_write(uuid4()) if write else backend.begin_read()
                try:
                    self.assertEqual(backend.export_configuration(), expected)
                    self.assertEqual(len(view.catalogs()), len(backend._schemas))
                finally:
                    view.close()
                    backend.close()
