from contextlib import closing
import sqlite3
from pathlib import Path
import tempfile
import unittest
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source
from yadinassi.source_constant_store import SourceConstantStore


def configured(length, history=False):
    source = configuration()
    files = {f.path:f.content for f in source.files}
    text = files['Constants/Text.xml'].replace(b'<v8:Length>16</v8:Length>', ('<v8:Length>'+str(length)+'</v8:Length>').encode())
    if history: text = text.replace(b'<DataHistory>DontUse</DataHistory>', b'<DataHistory>Use</DataHistory>')
    files['Constants/Text.xml'] = text
    return import_source(files)


class SourceConstantDefaultTests(unittest.TestCase):
    def store(self, length, history=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        store = SourceConstantStore.create(Path(directory.name)/'fresh.sqlite', configured(length, history))
        self.addCleanup(store.close)
        return store

    def test_measured_string_default_is_real_sqlite_row(self):
        store = self.store(64)
        self.assertEqual(store.get('Text'), '')
        with closing(sqlite3.connect(store.path)) as db, db:
            self.assertEqual(db.execute('SELECT value_json FROM constant_value').fetchall(), [('["string",""]',)])
        store.set('Text','assigned')
        self.assertEqual(store.get('Text'), 'assigned')

    def test_unmeasured_length_is_not_assumed(self):
        with self.assertRaisesRegex(ValueError,'uninitialized'):
            self.store(16).get('Text')

    def test_other_types_remain_uninitialized(self):
        store = self.store(64)
        for name in ('Flag','Amount','Date'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'uninitialized'):
                store.get(name)

    def test_unsupported_policies_do_not_gain_default(self):
        with self.assertRaisesRegex(ValueError,'uninitialized'):
            self.store(64, history=True).get('Text')
