"""Original exact-demo product form projection and atomic durable UI writes."""
from pathlib import Path
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.ui.catalog_editor import CatalogEditorApplication
from yadinassi.ui.protocol import CatalogRef, UIError


class ImportedProductEditorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'demo.sqlite'
        root = Path(__file__).parent / 'fixtures/demo_cf/source'
        files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        SQLiteCatalogBackend.create_demo_products(self.path, files).close()
        self.app = CatalogEditorApplication(SQLiteDBContext(self.path)); self.addCleanup(self.app.close)
        self.kind = self.app.catalogs.get_member('ВидыНоменклатуры').create_item()
        self.kind.set_member('Description', 'Товары'); self.kind.write()
        self.warehouse = self.app.catalogs.get_member('Склады').create_item()
        self.warehouse.set_member('Description', 'Основной склад'); self.warehouse.write()
        product = self.app.catalogs.get_member('Номенклатура')
        self.catalog = str(product._schema.identity)
        self.app.select(self.catalog); self.app.open(); self.editor = self.app.editor

    @staticmethod
    def ref(obj):
        value = obj.get_member('Ref')
        return CatalogRef(str(value.value_type.metadata_uuid), str(value.reference_uuid))

    def change(self, field, value):
        control = next(f['control'] for f in self.editor.snapshot()['fields'] if f['name'] == field)
        return self.editor.change(control, value)

    def row(self, value=None):
        self.editor.row_event('addRow', 'Склады')
        row = self.editor.snapshot()['sections'][0]['rows'][-1]['id']
        if value is not None: self.editor.row_event('changeRow', 'Склады', row, value)
        return row

    def valid(self):
        self.change('Description', '  Кабель USB-C  ')
        self.change('ВидНоменклатуры', self.ref(self.kind))
        return self.row(self.ref(self.warehouse))

    def save(self): self.editor.command('SaveButton')

    def stored(self):
        view = self.app.backend.begin_read()
        try: return view.read_catalog(self.editor.object._key)
        finally: view.close()

    def test_original_description_change_normalizes_and_warns(self):
        self.change('Description', ' x ')
        snapshot = self.editor.snapshot()
        self.assertEqual(snapshot['fields'][1]['inputText'], 'x')
        self.assertEqual(snapshot['fieldMessages'][0]['field'], 'Объект.Наименование')
        self.assertTrue(snapshot['originalForm'])
        self.assertTrue(snapshot['fields'][0]['readOnly'])
        with self.assertRaises(UIError): self.change('Code', '001')

    def test_kind_change_runs_original_handler(self):
        empty = CatalogRef(str(self.kind._key.catalog_id), '00000000-0000-0000-0000-000000000000')
        self.change('ВидНоменклатуры', empty)
        self.assertEqual(self.editor.snapshot()['fieldMessages'][0]['field'], 'Объект.ВидНоменклатуры')
        self.change('ВидНоменклатуры', self.ref(self.kind))
        self.assertEqual(self.editor.snapshot()['fieldMessages'], [])

    def test_row_original_duplicate_and_empty_messages(self):
        self.row(self.ref(self.warehouse)); second = self.row(self.ref(self.warehouse))
        self.assertEqual(self.editor.snapshot()['fieldMessages'][0]['field'], 'Объект.Склады[1].Склад')
        empty = CatalogRef(str(self.warehouse._key.catalog_id), '00000000-0000-0000-0000-000000000000')
        self.editor.row_event('changeRow', 'Склады', second, empty)
        self.assertIn('пустую строку', self.editor.snapshot()['fieldMessages'][0]['text'])

    def test_server_refusal_keeps_buffer_and_never_writes(self):
        self.change('Description', ' x '); self.row()
        with patch.object(_View, 'create', side_effect=AssertionError('write')): self.save()
        self.assertEqual(self.editor.error, 'form_validation')
        self.assertIsNone(self.stored())
        self.assertTrue(self.editor.snapshot()['dirty'])
        self.assertEqual(len(self.editor.snapshot()['fieldMessages']), 3)

    def test_save_restart_and_reopen_preserves_reference_row(self):
        row = self.valid(); self.save()
        self.assertEqual(self.editor.save_state, 'saved')
        card = self.stored(); self.assertEqual(card.description, 'Кабель USB-C')
        self.assertEqual(card.code, '000000001')
        app = CatalogEditorApplication(SQLiteDBContext(self.path)); self.addCleanup(app.close)
        app.select(self.catalog); app.open(self.ref(self.editor.object))
        self.assertEqual(app.editor.snapshot()['sections'][0]['rows'][0]['id'], row)
        self.assertEqual(app.editor.snapshot()['sections'][0]['rows'][0]['field']['value']['record'], self.ref(self.warehouse).record)

    def test_duplicate_save_refused_then_delete_and_save(self):
        self.valid(); second = self.row(self.ref(self.warehouse)); self.save()
        self.assertEqual(self.editor.error, 'form_validation'); self.assertIsNone(self.stored())
        self.editor.row_event('deleteRow', 'Склады', second); self.save()
        self.assertEqual(self.editor.save_state, 'saved')

    def test_last_row_delete_refused_and_discard_preserves(self):
        row = self.valid(); self.save(); before = self.stored()
        self.editor.row_event('deleteRow', 'Склады', row); self.save()
        self.assertEqual(self.editor.error, 'form_validation'); self.assertEqual(self.stored(), before)
        self.editor.command('CancelButton'); self.assertTrue(self.editor.form.closed)

    def test_deleted_kind_after_form_validation_refused_in_writer(self):
        self.valid()
        original = self.editor._product_event
        def event(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[1] == 'BeforeWriteAtServer':
                self.kind.set_member('DeletionMark', True); self.kind.write()
            return result
        with patch.object(self.editor, '_product_event', event): self.save()
        self.assertEqual(self.editor.error, 'object_validation'); self.assertIsNone(self.stored())
        self.assertIn('помечен на удаление', self.editor.snapshot()['fieldMessages'][0]['text'])

    def test_source_drift_preserves_scalar_and_row_buffer(self):
        self.valid(); before = self.editor.snapshot()
        with patch.object(self.app.backend, 'read_form_source', side_effect=BackendError('schema_changed')):
            with self.assertRaises(BackendError): self.change('Description', 'Another')
        with self.assertRaises(BackendError): self.row()
        after = self.editor.snapshot()
        self.assertEqual(after['fields'], before['fields']); self.assertEqual(after['sections'], before['sections'])
        self.assertTrue(after['sourceStale'])

    def test_uncertain_committed_recovery_does_not_replay_form_or_object(self):
        self.valid(); commit = _View.commit
        def uncertain(view): commit(view); raise BackendError('uncertain_commit')
        with patch.object(_View, 'commit', uncertain): self.save()
        self.assertTrue(self.editor.pending_commit)
        with patch.object(self.editor, '_product_event', side_effect=AssertionError('form replay')), \
             patch.object(self.app.backend, 'catalog_write_preparation', side_effect=AssertionError('source replay')), \
             patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.save()
        self.assertEqual(self.editor.save_state, 'saved')

    def test_refresh_recovery_does_not_replay_form(self):
        self.valid()
        with patch.object(self.editor, '_refresh', side_effect=BackendError('storage_error')): self.save()
        self.assertTrue(self.editor.pending_refresh)
        with patch.object(self.editor, '_product_event', side_effect=AssertionError('form replay')), \
             patch.object(_View, 'commit', side_effect=AssertionError('write replay')): self.save()
        self.assertEqual(self.editor.save_state, 'saved')

    def test_conflicting_other_writer_does_not_overwrite(self):
        self.valid(); self.save()
        other = self.editor.object.get_member('Ref').get_object(self.editor.object.get_member('Ref'))
        other.set_member('Description', 'Other writer'); other.write()
        self.change('Description', 'My edit'); self.save()
        self.assertEqual(self.editor.error, 'conflict')
        self.assertEqual(self.stored().description, 'Other writer')

    def test_wire_budget_rejects_event_before_buffer_adoption(self):
        self.valid(); before = self.editor.snapshot()
        with patch('yadinassi.ui.catalog_editor.MAX_LINE_BYTES', 1):
            with self.assertRaises(UIError): self.change('Description', 'Different name')
        self.assertEqual(self.editor.snapshot(), before)

    def test_absent_receipt_revalidation_refusal_unlocks_editor(self):
        self.valid()
        with patch.object(_View, 'commit', side_effect=BackendError('uncertain_commit')):
            self.save()
        self.assertTrue(self.editor.pending_commit)
        self.kind.set_member('DeletionMark', True); self.kind.write()
        self.save()
        self.assertEqual(self.editor.error, 'object_validation')
        self.assertFalse(self.editor.pending_commit)
        self.assertIsNone(self.editor.object._pending_write)
        self.assertIsNone(self.stored())
        self.change('Description', 'Still editable')
        self.editor.command('CancelButton'); self.assertTrue(self.editor.form.closed)

    def mark(self, obj, value):
        app = CatalogEditorApplication(SQLiteDBContext(self.path))
        try:
            app.select(str(obj._key.catalog_id)); app.open(self.ref(obj))
            control = next(f['control'] for f in app.editor.snapshot()['fields'] if f['name'] == 'DeletionMark')
            app.event('change', control=control, value=value)
            app.event('command', control='SaveButton')
            self.assertIsNone(app.editor.error)
        finally:
            app.close()

    def deletion_field(self):
        return next(f for f in self.editor.snapshot()['fields'] if f['name'] == 'DeletionMark')

    def test_deletion_checkbox_is_draft_only_and_has_no_invented_handler(self):
        self.valid(); self.save(); before = self.stored()
        with patch.object(self.editor, '_product_event', side_effect=AssertionError('invented handler')):
            self.change('DeletionMark', True)
        self.assertTrue(self.deletion_field()['inputText'])
        self.assertTrue(self.editor.snapshot()['dirty'])
        self.assertEqual(self.stored(), before)
        self.assertFalse(self.editor.object.get_member('DeletionMark'))

    def test_deletion_checkbox_rejects_non_boolean_before_mutation(self):
        before = self.editor.snapshot()
        for value in (1, 0, 'true', None):
            with self.subTest(value=value), self.assertRaises(UIError):
                self.change('DeletionMark', value)
            self.assertEqual(self.editor.snapshot(), before)

    def test_deletion_checkbox_discard_preserves_saved_record(self):
        self.valid(); self.save(); before = self.stored()
        self.change('DeletionMark', True)
        self.editor.close(); self.assertFalse(self.editor.form.closed)
        self.editor.command('CancelButton')
        self.assertTrue(self.editor.form.closed)
        self.assertEqual(self.stored(), before)

    def test_marked_kind_refuses_product_save_without_changing_saved_rows(self):
        row = self.valid(); self.save(); before = self.stored()
        self.mark(self.kind, True); self.save()
        self.assertEqual(self.editor.error, 'form_validation')
        self.assertIn('вид номенклатуры помечен', self.editor.snapshot()['fieldMessages'][0]['text'])
        self.assertEqual(self.stored(), before)
        self.assertEqual(self.editor.snapshot()['sections'][0]['rows'][0]['id'], row)
        self.mark(self.kind, False); self.save()
        self.assertIsNone(self.editor.error)
        self.assertEqual(replace(self.stored(), revision=before.revision), before)

    def test_mark_product_with_marked_warehouse_then_refuse_unmark_until_fixed(self):
        row = self.valid(); self.save(); before = self.stored()
        self.mark(self.warehouse, True); self.save()
        self.assertEqual(self.editor.error, 'form_validation')
        self.assertIn('Склад помечен на удаление', self.editor.snapshot()['fieldMessages'][0]['text'])
        self.assertEqual(self.stored(), before)
        self.change('DeletionMark', True); self.save()
        marked = self.stored()
        self.assertTrue(marked.deletion_mark)
        self.assertEqual((marked.key, marked.code, marked.description, marked.values),
                         (before.key, before.code, before.description, before.values))
        self.assertEqual(self.editor.snapshot()['sections'][0]['rows'][0]['id'], row)
        self.change('DeletionMark', False); self.save()
        self.assertEqual(self.editor.error, 'form_validation')
        self.assertFalse(self.deletion_field()['inputText'])
        self.assertEqual(self.stored(), marked)
        self.mark(self.warehouse, False); self.save()
        self.assertFalse(self.stored().deletion_mark)
        self.assertEqual(self.editor.snapshot()['sections'][0]['rows'][0]['id'], row)

    def test_mark_incomplete_product_preserves_original_deletion_bypass(self):
        self.change('Description', 'x'); self.change('DeletionMark', True); self.save()
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertTrue(self.stored().deletion_mark)
        self.assertEqual(self.stored().description, 'x')
        before = self.stored()
        self.change('DeletionMark', False); self.save()
        self.assertEqual(self.editor.error, 'form_validation')
        self.assertEqual(len(self.editor.snapshot()['fieldMessages']), 3)
        self.assertEqual(self.stored(), before)

    def test_reopen_marked_product_preserves_unselectable_references_and_row(self):
        row = self.valid(); self.save(); reference = self.ref(self.editor.object)
        self.mark(self.warehouse, True); self.mark(self.kind, True)
        self.change('DeletionMark', True); self.save(); before = self.stored()
        self.app.event('closeCard'); self.app.open(reference); self.editor = self.app.editor
        self.assertTrue(self.deletion_field()['inputText'])
        self.assertTrue(self.editor.snapshot()['references'])
        self.assertTrue(self.editor.snapshot()['sections'][0]['rows'][0]['field']['readOnly'])
        self.assertEqual(self.editor.snapshot()['sections'][0]['rows'][0]['id'], row)
        self.change('DeletionMark', False); self.save()
        self.assertEqual(self.editor.error, 'form_validation'); self.assertEqual(self.stored(), before)
        self.change('DeletionMark', True); self.save()
        self.assertIsNone(self.editor.error)
        self.assertEqual(replace(self.stored(), revision=before.revision), before)

    def test_mark_repeated_save_revalidates_and_preserves_record_values(self):
        self.valid(); self.save(); self.change('DeletionMark', True); self.save()
        marked = self.stored()
        # Ordinary product Save retains its original mandatory object validation
        # and fresh revision, unlike receipt/refresh recovery (which cannot write).
        event = self.editor._product_event
        with patch.object(self.editor, '_product_event', wraps=event) as prepared:
            self.save()
        prepared.assert_called_once()
        self.assertNotEqual(self.stored().revision, marked.revision)
        self.assertEqual(replace(self.stored(), revision=marked.revision), marked)
        self.assertFalse(self.editor.snapshot()['dirty'])

    def test_mark_source_drift_preserves_draft_and_saved_record(self):
        self.valid(); self.save(); before = self.stored(); fields = self.editor.snapshot()['fields']
        with patch.object(self.app.backend, 'read_form_source', side_effect=BackendError('schema_changed')):
            with self.assertRaises(BackendError): self.change('DeletionMark', True)
        self.assertEqual(self.editor.snapshot()['fields'], fields)
        self.assertEqual(self.stored(), before)
        self.assertTrue(self.editor.snapshot()['sourceStale'])

    def test_mark_conflict_never_overwrites_other_writer(self):
        self.valid(); self.save()
        other = self.editor.object.get_member('Ref').get_object(self.editor.object.get_member('Ref'))
        other.set_member('Description', 'Other writer'); other.write(); before = self.stored()
        self.change('DeletionMark', True); self.save()
        self.assertEqual(self.editor.error, 'conflict')
        self.assertTrue(self.deletion_field()['inputText'])
        self.assertEqual(self.stored(), before)

    def test_mark_uncertain_commit_resolves_retained_boolean_without_replay(self):
        self.valid(); self.save(); self.change('DeletionMark', True)
        commit = _View.commit
        def uncertain(view): commit(view); raise BackendError('uncertain_commit')
        with patch.object(_View, 'commit', uncertain): self.save()
        self.assertTrue(self.editor.pending_commit)
        with self.assertRaises(UIError): self.change('DeletionMark', False)
        with self.assertRaises(UIError): self.editor.command('CancelButton')
        with patch.object(self.editor, '_product_event', side_effect=AssertionError('form replay')), \
             patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.save()
        self.assertFalse(self.editor.pending_commit)
        self.assertTrue(self.stored().deletion_mark)
        self.assertTrue(self.deletion_field()['inputText'])
        self.assertFalse(self.editor.snapshot()['dirty'])

    def test_unmark_absent_receipt_revalidation_refuses_and_keeps_mark(self):
        self.valid(); self.change('DeletionMark', True); self.save(); marked = self.stored()
        self.change('DeletionMark', False)
        with patch.object(_View, 'commit', side_effect=BackendError('uncertain_commit')): self.save()
        self.assertTrue(self.editor.pending_commit)
        self.mark(self.warehouse, True); self.save()
        self.assertEqual(self.editor.error, 'object_validation')
        self.assertFalse(self.editor.pending_commit)
        self.assertFalse(self.deletion_field()['inputText'])
        self.assertEqual(self.stored(), marked)
        self.change('DeletionMark', True); self.save()
        self.assertIsNone(self.editor.error)
        self.assertTrue(self.stored().deletion_mark)

    def test_mark_refresh_retry_adopts_checkbox_without_second_write(self):
        self.valid(); self.save(); self.change('DeletionMark', True)
        with patch.object(self.editor, '_refresh', side_effect=BackendError('storage_error')): self.save()
        self.assertTrue(self.editor.pending_refresh)
        with self.assertRaises(UIError): self.change('DeletionMark', False)
        with patch.object(self.editor, '_product_event', side_effect=AssertionError('form replay')), \
             patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.save()
        self.assertFalse(self.editor.pending_refresh)
        self.assertTrue(self.deletion_field()['inputText'])
        self.assertFalse(self.editor.snapshot()['dirty'])

    def test_mark_wire_budget_failure_does_not_adopt_checkbox(self):
        before = self.editor.snapshot()
        with patch('yadinassi.ui.catalog_editor.MAX_LINE_BYTES', 1), self.assertRaises(UIError):
            self.change('DeletionMark', True)
        self.assertEqual(self.editor.snapshot(), before)
