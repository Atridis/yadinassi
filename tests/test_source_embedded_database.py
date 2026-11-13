"""Opening a saved source package needs neither an external XML tree nor extraction."""
from contextlib import closing, redirect_stdout, redirect_stderr
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source, source_digest
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.cli import main


class EmbeddedSourceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'saved.sqlite'
        self.source = configuration({'Resources/data.bin': b'\x00\xff'})

    def create(self):
        with closing(SourceConstantStore.create(self.path, self.source)) as store:
            store.set('Text', 'persisted')

    def change(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(sql, args)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = main(list(args))
        return result, out.getvalue(), err.getvalue()

    def test_embedded_roundtrip_preserves_every_byte_and_does_not_write(self):
        self.create()
        before = self.path.read_bytes()
        restored = SourceConstantStore.load_source(self.path)
        self.assertEqual(restored, self.source)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ['saved.sqlite'])
        with closing(SourceConstantStore.reopen(self.path, restored)) as store:
            self.assertEqual(store.get('Text'), 'persisted')

    def test_cli_startup_without_external_source(self):
        self.create()
        result, out, err = self.cli('--open-source-scratch-db', str(self.path), '--run-startup')
        self.assertEqual(result, 0, err)
        self.assertIn('Обработчики запуска завершены', out)

    def test_read_does_not_execute_stored_bsl(self):
        files = {f.path: f.content for f in self.source.files}
        files['Ext/ManagedApplicationModule.bsl'] = b'not parseable bsl!'
        self.source = import_source(files)
        self.create()
        self.assertEqual(SourceConstantStore.load_source(self.path), self.source)

    def test_cli_requires_explicit_startup(self):
        self.create()
        before = self.path.read_bytes()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--open-source-scratch-db', str(self.path)])
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_not_created(self):
        with self.assertRaises(OSError): SourceConstantStore.load_source(self.path)
        self.assertFalse(self.path.exists())

    def test_foreign_only_readonly_and_unchanged(self):
        self.change('CREATE TABLE foreign_data(v TEXT)')
        before = self.path.read_bytes()
        original, calls = sqlite3.connect, []
        def connect(path, *args, **kwargs):
            calls.append(str(path))
            return original(path, *args, **kwargs)
        with patch('yadinassi.source_constant_store.sqlite3.connect', side_effect=connect):
            with self.assertRaisesRegex(ValueError, 'schema'): SourceConstantStore.load_source(self.path)
        self.assertTrue(any('mode=ro' in p for p in calls))
        self.assertFalse(any('mode=rw' in p for p in calls))
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_source_refused(self):
        self.create()
        self.change("UPDATE source_file SET content=x'00' WHERE path='Resources/data.bin'")
        with self.assertRaisesRegex(ValueError, 'digest'): SourceConstantStore.load_source(self.path)

    def test_wrong_profile_refused(self):
        self.create()
        self.change("UPDATE source_binding SET profile='v2'")
        with self.assertRaisesRegex(ValueError, 'binding'): SourceConstantStore.load_source(self.path)

    def test_wrong_config_identity_refused(self):
        self.create()
        self.change("UPDATE source_binding SET configuration_uuid='wrong'")
        with self.assertRaisesRegex(ValueError, 'binding bound'): SourceConstantStore.load_source(self.path)

    def test_text_instead_of_blob_refused(self):
        self.create()
        self.change("UPDATE source_file SET content='text' WHERE path='Resources/data.bin'")
        with self.assertRaisesRegex(ValueError, 'bound'): SourceConstantStore.load_source(self.path)

    def test_path_re_admission_even_with_updated_digest(self):
        self.create()
        self.change("UPDATE source_file SET path='../escape' WHERE path='Resources/data.bin'")
        with self.assertRaises(ValueError): SourceConstantStore.load_source(self.path)
        self.assertFalse((self.path.parent.parent / 'escape').exists())

    def test_sidecars_refused_untouched(self):
        self.create()
        before = self.path.read_bytes()
        journal = Path(str(self.path) + '-journal')
        journal.write_bytes(b'untouched')
        with self.assertRaisesRegex(ValueError, 'clean-close'): SourceConstantStore.load_source(self.path)
        self.assertEqual(journal.read_bytes(), b'untouched')
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_values_prevent_startup(self):
        self.create()
        self.change("UPDATE constant_value SET value_json='bad'")
        with patch('yadinassi.configuration_source_runtime.SourceApplication.start', side_effect=AssertionError('must not execute')):
            result, _, err = self.cli('--open-source-scratch-db', str(self.path), '--run-startup')
        self.assertEqual(result, 1)
        self.assertIn('integrity', err)

    def test_other_cli_modes_refused(self):
        self.create()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--open-source-scratch-db', str(self.path), '--run-startup', '-c', 'Message(1);'])

    def test_source_change_between_read_and_reopen_refused(self):
        self.create()
        loaded = SourceConstantStore.load_source(self.path)
        self.change("UPDATE source_file SET content=x'00' WHERE path='Resources/data.bin'")
        with self.assertRaisesRegex(ValueError, 'source integrity'): SourceConstantStore.reopen(self.path, loaded)

    def test_path_size_bounded_before_content_read(self):
        self.create()
        self.change("UPDATE source_file SET path=? WHERE path='Resources/data.bin'", ('x' * 1025,))
        with self.assertRaisesRegex(ValueError, 'bound'): SourceConstantStore.load_source(self.path)

    def test_binding_size_bounded_before_materialization(self):
        self.create()
        self.change("UPDATE source_binding SET source_sha256=?", ('x' * 10000,))
        with self.assertRaisesRegex(ValueError, 'binding bound'): SourceConstantStore.load_source(self.path)

    def test_nul_padded_paths_and_bindings_bounded_as_bytes(self):
        self.create()
        self.change("UPDATE source_file SET path=? WHERE path='Resources/data.bin'", ('x\0' + 'x' * 4096,))
        with self.assertRaisesRegex(ValueError, 'bound'): SourceConstantStore.load_source(self.path)
        self.change("UPDATE source_binding SET source_sha256=?", ('x' * 64 + '\0' + 'x' * 4096,))
        with self.assertRaisesRegex(ValueError, 'binding bound'): SourceConstantStore.load_source(self.path)
