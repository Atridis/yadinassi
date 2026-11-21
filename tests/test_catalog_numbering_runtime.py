"""Host-owned numbering runtime tests; no claim of native 1C behavior."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from catalog_sections_fixture import configuration_files_with_sections
from test_catalog_commit_cleanup_recovery import FaultConnection


class CatalogNumberingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.sqlite'
        self.files = configuration_files_with_sections()
        config = import_configuration(self.files)
        # Only the host changes the logical schema. XML remains explicit.
        config = replace(config, catalogs=tuple(
            replace(s, code_length=2, numbering='decimal_v1') if s.name == 'Products' else s
            for s in config.catalogs))
        self.context = SQLiteDBContext.create(self.path, config)
        self.addCleanup(lambda: self.context.close())
        self.vm = Interpreter(database_context=self.context)

    def new_object(self):
        self.vm.execute('''O=Catalogs.Products.CreateItem(); O.Description="owned";
R=O.Lines.Add(); R.Text="row"; N=O.Notes.Add(); N.Text="note";''')
        return self.vm.execute('O')

    def fault(self, **fault):
        begin = self.context.backend.begin_write
        def injected(operation):
            tx = begin(operation)
            tx._connection = FaultConnection(tx._connection, **fault)
            return tx
        return patch.object(self.context.backend, 'begin_write', side_effect=injected)

    def read(self, obj):
        view = self.context.backend.begin_read()
        try: return view.read_catalog(obj._key)
        finally: view.close()

    def counter(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute('SELECT next_value FROM catalog_sequence').fetchone()[0]

    def assert_frozen(self, obj):
        self.assertTrue(obj._uncertain_write)
        self.assertIsNone(obj._pending_write)
        self.assertEqual(obj.get_member('Code'), '')
        section = obj.get_member('Lines')
        row = section.get(Decimal(0))
        for mutate in (lambda: obj.set_member('Code', '77'),
                       lambda: obj.set_member('Description', 'changed'),
                       lambda: obj.set_new_object_ref(obj._manager._ref(uuid4())),
                       lambda: row.set_member('Text', 'changed'),
                       section.add, section.clear, lambda: section.delete(row),
                       obj.get_member('Notes').add):
            with self.subTest(mutate=mutate), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                mutate()
        self.assertTrue(obj._uncertain_write)
        self.assertIsNone(obj._pending_write)

    def test_new_object_and_abandoned_edit_allocate_nothing_until_write(self):
        abandoned = self.new_object()
        self.assertEqual(abandoned.get_member('Code'), '')
        self.assertTrue(abandoned.is_new())
        self.assertEqual(self.counter(), 1)
        self.assertIsNone(self.read(abandoned))
        obj = self.new_object()
        expected_sections = obj._section_draft()
        obj.write()
        self.assertEqual(obj.get_member('Code'), '01')
        self.assertFalse(obj.is_new())
        self.assertEqual(self.counter(), 2)
        self.assertIsNone(self.read(abandoned))
        self.assertEqual(abandoned.get_member('Code'), '')
        self.assertEqual(self.read(obj).tabular_sections, expected_sections)
        self.context.close()
        self.context = SQLiteDBContext(self.path)
        self.vm = Interpreter(database_context=self.context)
        self.vm.execute('O=Catalogs.Products.FindByCode("01").GetObject();')
        opened = self.vm.execute('O')
        self.assertEqual(opened.get_member('Code'), '01')
        self.assertEqual(opened.get_member('Lines').get(Decimal(0)).get_member('Text'), 'row')
        self.assertEqual(self.counter(), 2)
        self.assertEqual(self.context.backend.export_configuration(), self.files)

    def test_manual_code_and_updates_do_not_allocate_and_empty_update_is_rejected(self):
        obj = self.new_object()
        obj.set_member('Code', '80')
        obj.write()
        self.assertEqual(self.counter(), 1)
        obj.set_member('Description', 'edited')
        obj.write()
        self.assertEqual(obj.get_member('Code'), '80')
        self.assertEqual(self.counter(), 1)
        obj.set_member('Code', '')
        with self.assertRaisesRegex(BackendError, 'invalid_input'): obj.write()
        self.assertEqual(self.read(obj).code, '80')
        self.assertEqual(self.counter(), 1)
        next_obj = self.new_object()
        next_obj.write()
        self.assertEqual(next_obj.get_member('Code'), '01')

    def test_lost_commit_response_requires_fresh_read_of_number_and_sections(self):
        obj = self.new_object()
        expected = obj._section_draft()
        with self.fault(commit_fault='after'), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            obj.write()
        self.assert_frozen(obj)
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('must not replay')):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                obj.write()
        card = self.read(obj)
        self.assertEqual((card.code, card.tabular_sections), ('01', expected))
        self.assertEqual(self.counter(), 2)
        ref = obj._manager._ref(card.key.record_id)
        fresh = ref.get_object(ref)
        fresh.get_member('Lines').get(Decimal(0)).set_member('Text', 'fresh edit')
        fresh.write()
        self.assertEqual(self.counter(), 2)

    def test_before_commit_failure_retains_number_for_a_new_object(self):
        obj = self.new_object()
        with self.fault(commit_fault='before'), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            obj.write()
        self.assert_frozen(obj)
        self.assertIsNone(self.read(obj))
        self.assertEqual(self.counter(), 1)
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('must not replay')):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                obj.write()
        fresh = self.new_object()
        expected = fresh._section_draft()
        fresh.write()
        self.assertNotEqual(fresh._key, obj._key)
        self.assertEqual(fresh.get_member('Code'), '01')
        self.assertEqual(self.read(fresh).tabular_sections, expected)
        self.assertEqual(self.counter(), 2)

    def test_numbered_runtime_requires_outcome_capability_before_any_write(self):
        obj = self.new_object()
        caps = replace(self.context.backend.capabilities(), catalog_write_outcomes=False)
        with patch.object(self.context.backend, 'capabilities', return_value=caps), \
                patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('not admitted')):
            with self.assertRaisesRegex(BackendError, 'unsupported'): obj.write()
        self.assertEqual(obj.get_member('Code'), '')
        self.assertEqual(self.counter(), 1)
        self.assertIsNone(obj._pending_write)
