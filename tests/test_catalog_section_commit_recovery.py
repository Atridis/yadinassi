"""Section-specific recovery on disposable SQLite, never native 1C evidence."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from catalog_sections_fixture import configuration_files_with_sections
from test_catalog_commit_cleanup_recovery import FaultConnection
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_sections import BSLCatalogSection
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import _View


class CatalogSectionCommitRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.sqlite'
        self.files = configuration_files_with_sections()
        self.context = SQLiteDBContext.create(self.path, import_configuration(self.files))
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)
        self.sequence = 0

    def new_object(self):
        self.sequence += 1
        self.vm.execute('''O=Catalogs.Products.CreateItem();
O.Code="%s"; O.Text="owner"; O.Description="description";
A=O.Lines.Add(); A.Text="first"; A.Amount=12.34; A.Active=True;
A.Stamp=Date(2024,2,29,12,34,56);
B=O.Lines.Add(); B.Text="second"; B.Amount=-2.25;
N=O.Notes.Add(); N.Text="note";''' % self.sequence)
        obj = self.vm.execute('O')
        # Keep the receipt test independent of future qualifier-casting support.
        obj.get_member('Lines').get(Decimal(0)).set_member('Text', 'a' * 32)
        return obj

    def injected_write(self, **fault):
        original = self.context.backend.begin_write
        views = []
        def begin(operation):
            view = original(operation)
            view._connection = FaultConnection(view._connection, **fault)
            views.append(view)
            return view
        return patch.object(self.context.backend, 'begin_write', side_effect=begin), views

    def read(self, obj):
        view = self.context.backend.begin_read()
        try: return view.read_catalog(obj._key)
        finally: view.close()

    def assert_locked(self, obj):
        pending = obj._pending_write
        self.assertIsNotNone(pending)
        self.assertEqual(len(pending), 3)
        section = obj.get_member('Lines')
        row = section.get(Decimal(0))
        actions = (
            lambda: obj.set_member('Description', 'changed'),
            lambda: obj.set_new_object_ref(obj._manager._ref(uuid4())),
            lambda: row.set_member('Text', 'changed'),
            section.add, section.clear, lambda: section.delete(row),
            lambda: section.set_index(Decimal(0), row),
            obj.get_member('Notes').add,
            lambda: obj.get_member('Notes').get(Decimal(0)).set_member('Text', 'changed'),
        )
        for action in actions:
            with self.subTest(action=action), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                action()
        self.assertIs(obj._pending_write, pending)

    def resolve_once(self, obj, expected_sections):
        self.assert_locked(obj)
        draft, previous, operation = obj._pending_write
        receipt = self.context.backend.committed_operation(operation)
        self.assertIsNotNone(receipt)
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('no replay')):
            obj.write()
        self.assertIsNone(obj._pending_write)
        self.assertTrue(all(not section._dirty for section in obj._sections.values()))
        self.assertNotEqual(obj._operation_id, operation)
        self.assertEqual(int(obj._revision.token), 1 if previous is None else int(previous.token) + 1)
        card = self.read(obj)
        self.assertEqual(card.tabular_sections, expected_sections)
        self.assertEqual((card.code, card.description, card.deletion_mark, card.values),
                         (draft.code, draft.description, draft.deletion_mark, draft.values))
        self.assertEqual(self.context.backend.committed_operation(operation), receipt)
        self.assertEqual(self.context.backend.resolve_write(operation, draft, previous), obj._revision)
        self.assertEqual(self.read(obj), card)
        self.assertEqual(self.context.backend.export_configuration(), self.files)
        return card

    def test_create_close_failures_keep_exact_rows_and_release_mutations_after_resolution(self):
        for close_fault in ('before', 'after'):
            with self.subTest(close_fault=close_fault):
                obj = self.new_object()
                expected = obj._section_draft()
                instrument, views = self.injected_write(close_fault=close_fault, close_count=1)
                with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                    obj.write()
                self.assertTrue(obj.is_new())
                self.assertTrue(all(section._dirty for section in obj._sections.values()))
                self.assertIsNone(self.context.backend._active)
                self.assertEqual(views[0]._connection, None)
                self.resolve_once(obj, expected)
                obj.get_member('Lines').get(Decimal(0)).set_member('Text', 'next')
                obj.write()
                self.assertEqual(obj._revision.token, '2')
                self.assertEqual(self.read(obj).tabular_sections[0].rows[0].values[0], 'next')
                self.assertEqual(self.read(obj).tabular_sections[1], expected[1])

    def test_after_commit_error_and_interruptions_resolve_full_section_receipt(self):
        for fault, error in (('after', BackendError), ('interrupt', KeyboardInterrupt), ('memory', MemoryError)):
            with self.subTest(fault=fault):
                obj = self.new_object()
                expected = obj._section_draft()
                instrument, _ = self.injected_write(commit_fault=fault)
                with instrument, self.assertRaises(error): obj.write()
                self.resolve_once(obj, expected)

    def test_before_commit_failure_retries_exact_rows_and_original_operation(self):
        obj = self.new_object()
        expected = obj._section_draft()
        instrument, _ = self.injected_write(commit_fault='before')
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'): obj.write()
        self.assert_locked(obj)
        draft, previous, operation = obj._pending_write
        self.assertIsNone(self.context.backend.committed_operation(operation))
        self.assertIsNone(self.read(obj))
        obj._operation_id = uuid4()  # Acceptance may already have changed this field.
        begin = self.context.backend.begin_write
        with patch.object(self.context.backend, 'begin_write', wraps=begin) as started:
            obj.write()
        started.assert_called_once_with(operation)
        self.assertEqual(obj._revision.token, '1')
        self.assertIsNone(obj._pending_write)
        self.assertEqual(self.read(obj).tabular_sections, expected)
        self.assertEqual(self.context.backend.resolve_write(operation, draft, previous), obj._revision)
        self.assertTrue(all(not section._dirty for section in obj._sections.values()))

    def test_update_recovery_preserves_replacement_row_identity_order_and_revision(self):
        for fault in ({'close_fault': 'after', 'close_count': 1}, {'commit_fault': 'after'}):
            with self.subTest(fault=fault):
                obj = self.new_object()
                obj.write()
                previous = obj._revision
                section = obj.get_member('Lines')
                section.delete(Decimal(0))
                section.add().set_member('Text', 'replacement')
                obj.get_member('Notes').get(Decimal(0)).set_member('Text', 'updated note')
                obj.set_member('DeletionMark', True)
                expected = obj._section_draft()
                instrument, _ = self.injected_write(**fault)
                with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'): obj.write()
                self.assertEqual(obj._revision, previous)
                self.assertEqual(obj._pending_write[1], previous)
                self.resolve_once(obj, expected)
                self.assertEqual(obj._revision.token, '2')

    def test_persistent_close_failure_keeps_sections_locked_until_connection_released(self):
        obj = self.new_object()
        expected = obj._section_draft()
        instrument, views = self.injected_write(close_fault='before', close_count=100)
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'): obj.write()
        view = views[0]
        try:
            self.assertIs(self.context.backend._active, view)
            self.assert_locked(obj)
            with self.assertRaisesRegex(BackendError, 'closed'): view.commit()
            with self.assertRaisesRegex(BackendError, 'busy'): obj.write()
            self.assert_locked(obj)
        finally:
            view._connection.close_count = 0
            view.close()
        self.resolve_once(obj, expected)

    def test_interrupted_dirty_reset_retains_pending_operation_and_mutation_lock(self):
        for error_type in (MemoryError, KeyboardInterrupt):
            with self.subTest(error=error_type):
                obj = self.new_object()
                expected = obj._section_draft()
                operation = obj._operation_id
                notes = obj.get_member('Notes')
                def setter(section, name, value):
                    if name == '_dirty' and value is False:
                        self.assertIsNotNone(obj._pending_write)
                        if section is notes: raise error_type('dirty reset interrupted')
                    object.__setattr__(section, name, value)
                with patch.object(BSLCatalogSection, '__setattr__', setter, create=True):
                    with self.assertRaises(error_type): obj.write()
                self.assertFalse(obj.get_member('Lines')._dirty)
                self.assertTrue(notes._dirty)
                self.assertEqual(obj._pending_write[2], operation)
                self.assertNotEqual(obj._operation_id, operation)
                self.resolve_once(obj, expected)

    def test_section_order_or_values_cannot_resolve_another_intent(self):
        obj = self.new_object()
        expected = obj._section_draft()
        instrument, _ = self.injected_write(commit_fault='after')
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'): obj.write()
        draft, previous, operation = obj._pending_write
        lines, notes = draft.tabular_sections
        first = lines.rows[0]
        changed_row = replace(first, values=('changed',) + first.values[1:])
        changed_parts = (replace(lines, rows=tuple(reversed(lines.rows))),
                         replace(lines, rows=(changed_row,) + lines.rows[1:]),
                         replace(lines, rows=(replace(first, identity=uuid4()),) + lines.rows[1:]))
        for changed in changed_parts:
            with self.subTest(changed=changed), self.assertRaisesRegex(BackendError, 'conflict'):
                self.context.backend.resolve_write(operation, replace(draft, tabular_sections=(changed, notes)), previous)
        self.resolve_once(obj, expected)

    def test_owner_only_recovery_keeps_unchanged_sections(self):
        obj = self.new_object()
        obj.write()
        expected = self.read(obj).tabular_sections
        obj.set_member('Description', 'owner only')
        instrument, _ = self.injected_write(close_fault='after', close_count=1)
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'): obj.write()
        self.assertIsNone(obj._pending_write[0].tabular_sections)
        self.resolve_once(obj, expected)

    def test_multi_record_commit_close_failure_keeps_owner_rows_and_receipt_atomic(self):
        first, second = self.new_object(), self.new_object()
        from yadinassi.catalog_backend import CatalogDraft
        def draft(obj):
            manager = obj._manager
            return CatalogDraft(obj._key, obj._values['code'], obj._values['description'], False,
                tuple(manager._stored(field, obj._values[field.name.casefold()]) for field in manager._schema.fields),
                obj._section_draft())
        drafts = (draft(first), draft(second))
        operation = uuid4()
        tx = self.context.backend.begin_write(operation)
        for item in drafts: tx.create(item)
        tx._connection = FaultConnection(tx._connection, close_fault='after', close_count=1)
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'): tx.commit()
        self.assertIsNone(self.context.backend._active)
        receipt = self.context.backend.committed_operation(operation)
        self.assertEqual(tuple(revision.record_id for revision in receipt[1]), tuple(item.key.record_id for item in drafts))
        for obj, item in zip((first, second), drafts):
            card = self.read(obj)
            self.assertEqual(card.tabular_sections, item.tabular_sections)
            self.assertEqual(card.revision.token, '1')
