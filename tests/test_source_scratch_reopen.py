"""Explicit source-bound reopen is persistence, never ordinary DB activation."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from test_source_constant_store import configuration
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.configuration_source_runtime import SourceApplication


class ScratchReopenTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'source.sqlite'
        self.source = configuration()

    def create(self):
        with closing(SourceConstantStore.create(self.path, self.source)) as store:
            store.set('Text', 'persisted')

    def change(self, sql, params=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(sql, params)

    def test_reopen_retains_values_and_complete_source(self):
        self.create()
        with closing(SourceConstantStore.reopen(self.path, self.source)) as store:
            self.assertEqual(store.get('Text'), 'persisted')
            store.set('Flag', True)
        with closing(SourceConstantStore.reopen(self.path, self.source)) as store:
            self.assertIs(store.get('Flag'), True)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT path,content FROM source_file ORDER BY path').fetchall(),
                             sorted((f.path, f.content) for f in self.source.files))

    def test_missing_file_not_created(self):
        with self.assertRaises(OSError): SourceConstantStore.reopen(self.path, self.source)
        self.assertFalse(self.path.exists())

    def test_foreign_database_unchanged(self):
        self.change('CREATE TABLE owner_data(value TEXT)')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'schema'): SourceConstantStore.reopen(self.path, self.source)
        self.assertEqual(before, self.path.read_bytes())

    def test_changed_source_refused(self):
        self.create()
        with self.assertRaisesRegex(ValueError, 'binding'):
            SourceConstantStore.reopen(self.path, configuration({'Extra.txt': b'new'}))

    def test_stored_source_corruption_refused(self):
        self.create()
        self.change("UPDATE source_file SET content=x'00' WHERE path='Configuration.xml'")
        with self.assertRaisesRegex(ValueError, 'source integrity'): SourceConstantStore.reopen(self.path, self.source)

    def test_trigger_refused_before_write(self):
        self.create()
        self.change('CREATE TRIGGER injected AFTER INSERT ON constant_value BEGIN DELETE FROM constant_value; END')
        with self.assertRaisesRegex(ValueError, 'schema'): SourceConstantStore.reopen(self.path, self.source)

    def test_invalid_persisted_value_refused(self):
        self.create()
        self.change("UPDATE constant_value SET value_json='invalid'")
        with self.assertRaisesRegex(ValueError, 'storage integrity'): SourceConstantStore.reopen(self.path, self.source)

    def test_old_profile_not_migrated(self):
        self.create()
        self.change("UPDATE source_binding SET profile='source-scalar-constants-extensions-v2'")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'binding'): SourceConstantStore.reopen(self.path, self.source)
        self.assertEqual(before, self.path.read_bytes())

    def test_symlink_not_followed(self):
        self.create()
        link = self.path.with_name('link.sqlite')
        try: link.symlink_to(self.path)
        except OSError: self.skipTest('symlink unavailable')
        with self.assertRaisesRegex(ValueError, 'file integrity'): SourceConstantStore.reopen(link, self.source)

    def test_live_source_tamper_blocks_writes(self):
        self.create()
        with closing(SourceConstantStore.reopen(self.path, self.source)) as store:
            self.change("DELETE FROM source_file WHERE path='Configuration.xml'")
            with self.assertRaisesRegex(ValueError, 'source integrity'): store.set('Text', 'changed')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertIn('persisted', db.execute('SELECT value_json FROM constant_value').fetchone()[0])

    def test_application_explicit_reopen(self):
        self.create()
        with closing(SourceApplication(self.source, existing_scratch_database=self.path)) as app:
            self.assertEqual(app.constant_store.get('Text'), 'persisted')

    def test_application_create_reopen_exclusive(self):
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            SourceApplication(self.source, scratch_database=self.path, existing_scratch_database=self.path)
        self.assertFalse(self.path.exists())

    def test_cli_reopen_requires_source_and_startup(self):
        import contextlib
        import io
        from yadinassi.cli import main
        for arguments in [ ['--open-source-scratch-db', str(self.path)],
                           ['--configuration-source', 'unused', '--open-source-scratch-db', str(self.path)],
                           ['--configuration-source', 'unused', '--run-startup', '--open-source-scratch-db', str(self.path), '--source-scratch-db', 'new'] ]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(arguments)
            self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.path.exists())

    def test_cli_reopens_explicitly_without_recreating(self):
        import contextlib
        import io
        from yadinassi.cli import main
        from yadinassi.configuration_source import save_source_archive
        self.create()
        archive = self.path.with_suffix('.zip')
        save_source_archive(archive, self.source)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = main(['--configuration-source', str(archive), '--run-startup', '--open-source-scratch-db', str(self.path)])
        self.assertEqual(result, 0)
        with closing(SourceConstantStore.reopen(self.path, self.source)) as store:
            self.assertEqual(store.get('Text'), 'persisted')

    def test_unchanged_source_not_reread_for_each_constant(self):
        from unittest.mock import patch
        self.create()
        with closing(SourceConstantStore.reopen(self.path, self.source)) as store:
            with patch('yadinassi.source_constant_store._verify_source', side_effect=AssertionError('redundant full scan')):
                self.assertEqual(store.get('Text'), 'persisted')
                store.set('Text', 'new')
                self.assertEqual(store.get('Text'), 'new')
            self.change("UPDATE source_file SET content=x'00' WHERE path='Configuration.xml'")
            with self.assertRaisesRegex(ValueError, 'source integrity'): store.get('Text')
