"""Section atomicity and physical cleanup after SQLite write failures."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from catalog_sections_fixture import configuration_files_with_sections
from test_catalog_commit_cleanup_recovery import FaultConnection
from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.catalog.catalog_sections import BSLCatalogSection
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import _View


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
        # Keep the row fixture independent of future qualifier-casting support.
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
        self.assertTrue(obj._uncertain_write)
        self.assertIsNone(obj._pending_write)
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
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('no replay')):
            with self.assertRaisesRegex(BackendError, '^uncertain_commit$'):
                obj.write()

    def assert_persisted(self, obj, expected_sections, revision):
        card = self.read(obj)
        self.assertEqual(card.tabular_sections, expected_sections)
        self.assertEqual(card.revision.token, revision)
        self.assertEqual(card.code, obj.get_member('Code'))
        self.assertEqual(card.description, obj.get_member('Description'))
        self.assertEqual(self.context.backend.export_configuration(), self.files)
        return card

    def test_known_commit_close_failures_keep_exact_rows_and_accepted_revision(self):
        for close_fault in ('before', 'after'):
            with self.subTest(close_fault=close_fault):
                obj = self.new_object()
                expected = obj._section_draft()
                instrument, views = self.injected_write(close_fault=close_fault, close_count=1)
                with instrument, self.assertRaisesRegex(BackendError, '^storage_error$'):
                    obj.write()
                self.assertEqual(obj._revision.token, '1')
                self.assertFalse(obj._uncertain_write)
                self.assertTrue(all(not section._dirty for section in obj._sections.values()))
                self.assertIsNone(self.context.backend._active)
                self.assertIsNone(views[0]._connection)
                self.assert_persisted(obj, expected, '1')

    def test_after_commit_error_and_interruptions_keep_exact_persisted_sections(self):
        for fault, error in (('after', BackendError), ('interrupt', KeyboardInterrupt), ('memory', MemoryError)):
            with self.subTest(fault=fault):
                obj = self.new_object()
                expected = obj._section_draft()
                instrument, _ = self.injected_write(commit_fault=fault)
                with instrument, self.assertRaises(error): obj.write()
                self.assert_locked(obj)
                self.assertTrue(obj.is_new())
                self.assert_persisted(obj, expected, '1')

    def test_before_commit_failure_leaves_no_record_and_cannot_replay(self):
        obj = self.new_object()
        instrument, _ = self.injected_write(commit_fault='before')
        with instrument, self.assertRaisesRegex(BackendError, '^uncertain_commit$'): obj.write()
        self.assert_locked(obj)
        self.assertIsNone(self.read(obj))
        self.assertIsNone(self.context.backend._active)

    def test_update_lost_reply_keeps_replacement_order_identity_and_revision(self):
        obj = self.new_object()
        obj.write()
        previous = obj._revision
        section = obj.get_member('Lines')
        section.delete(Decimal(0))
        section.add().set_member('Text', 'replacement')
        obj.get_member('Notes').get(Decimal(0)).set_member('Text', 'updated note')
        obj.set_member('DeletionMark', True)
        expected = tuple(section._stored_rows() for section in obj._sections.values())
        instrument, _ = self.injected_write(commit_fault='after')
        with instrument, self.assertRaisesRegex(BackendError, '^uncertain_commit$'): obj.write()
        self.assertEqual(obj._revision, previous)
        self.assert_locked(obj)
        self.assertTrue(self.assert_persisted(obj, expected, '2').deletion_mark)

    def test_persistent_close_failure_does_not_release_physical_owner_early(self):
        obj = self.new_object()
        expected = obj._section_draft()
        instrument, views = self.injected_write(close_fault='before', close_count=100)
        try:
            with instrument, self.assertRaisesRegex(BackendError, '^storage_error$'): obj.write()
            view = views[0]
            self.assertEqual(obj._revision.token, '1')
            self.assertIs(self.context.backend._active, view)
            with self.assertRaisesRegex(BackendError, '^closed$'): view.commit()
            with self.assertRaisesRegex(BackendError, '^busy$'): self.read(obj)
        finally:
            if views and views[0]._connection is not None:
                views[0]._connection.close_count = 0
                views[0].close()
        self.assert_persisted(obj, expected, '1')

    def test_interrupted_dirty_reset_leaves_buffer_frozen_without_replay(self):
        for error_type in (MemoryError, KeyboardInterrupt):
            with self.subTest(error=error_type):
                obj = self.new_object()
                expected = obj._section_draft()
                notes = obj.get_member('Notes')
                def setter(section, name, value):
                    if name == '_dirty' and value is False and section is notes:
                        self.assertTrue(obj._uncertain_write)
                        raise error_type('dirty reset interrupted')
                    object.__setattr__(section, name, value)
                with patch.object(BSLCatalogSection, '__setattr__', setter, create=True):
                    with self.assertRaises(error_type): obj.write()
                self.assertFalse(obj.get_member('Lines')._dirty)
                self.assertTrue(notes._dirty)
                self.assertEqual(obj._revision.token, '1')
                self.assert_locked(obj)
                self.assert_persisted(obj, expected, '1')

    def test_owner_only_lost_reply_keeps_unchanged_sections(self):
        obj = self.new_object()
        obj.write()
        expected = self.read(obj).tabular_sections
        obj.set_member('Description', 'owner only')
        self.assertIsNone(obj._section_draft())
        instrument, _ = self.injected_write(commit_fault='after')
        with instrument, self.assertRaisesRegex(BackendError, '^uncertain_commit$'): obj.write()
        self.assert_locked(obj)
        self.assert_persisted(obj, expected, '2')

    def test_multi_record_lost_commit_reply_keeps_owner_rows_atomic(self):
        first, second = self.new_object(), self.new_object()
        drafts = (first._write_draft(), second._write_draft())
        tx = self.context.backend.begin_write(uuid4())
        for draft in drafts: tx.create(draft)
        tx._connection = FaultConnection(tx._connection, commit_fault='after')
        with self.assertRaisesRegex(BackendError, '^uncertain_commit$'): tx.commit()
        self.assertIsNone(self.context.backend._active)
        for obj, draft in zip((first, second), drafts):
            self.assert_persisted(obj, draft.tabular_sections, '1')
