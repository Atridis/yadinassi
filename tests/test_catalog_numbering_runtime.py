"""Host-owned numbering runtime tests; no claim of native 1C behavior."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
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
        with sqlite3.connect(self.path) as db:
            return db.execute('SELECT next_value FROM catalog_sequence').fetchone()[0]

    def assert_frozen(self, obj):
        pending = obj._pending_write
        self.assertIsNotNone(pending)
        self.assertTrue(pending[0].auto_number)
        self.assertEqual(pending[0].code, '')
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
        self.assertIs(obj._pending_write, pending)

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

    def test_lost_commit_response_keeps_code_and_sections_frozen_until_exact_resolution(self):
        for fault in ({'commit_fault': 'after'}, {'close_fault': 'after', 'close_count': 1}):
            with self.subTest(fault=fault):
                obj = self.new_object()
                expected = obj._section_draft()
                number = self.counter()
                with self.fault(**fault), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                    obj.write()
                self.assertTrue(obj.is_new())
                self.assert_frozen(obj)
                draft, previous, operation = obj._pending_write
                outcome = self.context.backend.resolve_write_outcome(operation, draft, previous)
                self.assertEqual(outcome.code, str(number).zfill(2))
                with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('must not replay')):
                    obj.write()
                self.assertEqual(obj.get_member('Code'), outcome.code)
                self.assertEqual(obj._revision, outcome.revision)
                self.assertIsNone(obj._pending_write)
                self.assertFalse(obj.is_new())
                self.assertEqual(self.read(obj).tabular_sections, expected)
                self.assertTrue(all(not s._dirty for s in obj._sections.values()))
                self.assertEqual(self.counter(), number + 1)
                obj.get_member('Lines').get(Decimal(0)).set_member('Text', 'editable again')
                obj.write()
                self.assertEqual(self.counter(), number + 1)
                self.assertEqual(self.context.backend.resolve_write_outcome(operation, draft, previous), outcome)

    def test_before_commit_failure_retries_frozen_intent_with_original_operation(self):
        obj = self.new_object()
        expected = obj._section_draft()
        with self.fault(commit_fault='before'), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            obj.write()
        self.assert_frozen(obj)
        draft, previous, operation = obj._pending_write
        self.assertIsNone(self.context.backend.resolve_write_outcome(operation, draft, previous))
        self.assertIsNone(self.read(obj))
        self.assertEqual(self.counter(), 1)
        obj._operation_id = uuid4()
        begin = self.context.backend.begin_write
        with patch.object(self.context.backend, 'begin_write', wraps=begin) as called:
            obj.write()
        called.assert_called_once_with(operation)
        self.assertEqual(obj.get_member('Code'), '01')
        self.assertEqual(self.read(obj).tabular_sections, expected)
        self.assertIsNone(obj._pending_write)
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
