"""Real temporary SQLite edit/save/reopen; no native UI parity claim."""
from decimal import Decimal
from unittest import mock
import unittest
from uuid import UUID, uuid4

from ui_catalog_fixture import repository
from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import _View
from yadinassi.ui.catalog_editor import CatalogEditorApplication, _reference_label
from yadinassi.ui.protocol import UIError, CatalogRef


class CatalogEditorTests(unittest.TestCase):
    def setUp(self):
        old, self.path, self.before, self.ids = repository(self)
        old.close()
        self.context = SQLiteDBContext(self.path)
        self.app = CatalogEditorApplication(self.context)
        self.addCleanup(self.app.close)

    def select(self, kind='product'):
        self.app.event('selectCatalog', catalog=self.ids[kind])

    def open_existing(self):
        self.select()
        self.reference = self.app.view.cards[0].reference
        self.app.event('openCard', reference=self.reference)

    def change(self, name, value):
        fields = self.app.editor.snapshot()['fields']
        control = next(field['control'] for field in fields if field['name'] == name)
        self.app.event('change', control=control, value=value)

    def save(self): self.app.event('command', control='SaveButton')

    def row(self, catalog, record):
        view = self.context.backend.begin_read()
        try: return view.read_catalog(CatalogKey(view.database_id, UUID(catalog), UUID(record)))
        finally: view.close()

    def test_create_save_close_reopen_actual_database(self):
        self.select('category'); self.app.event('create')
        self.change('Code', '20'); self.change('Description', 'Created through form')
        self.save()
        state = self.app.editor.snapshot()
        self.assertEqual(state['saveState'], 'saved'); self.assertFalse(state['dirty']); self.assertFalse(state['isNew'])
        record = state['reference']['record']
        self.app.event('closeCard'); self.app.close()
        context = SQLiteDBContext(self.path)
        try:
            view = context.backend.begin_read()
            try: card = view.read_catalog(CatalogKey(view.database_id, UUID(self.ids['category']), UUID(record)))
            finally: view.close()
            self.assertEqual(card.description, 'Created through form')
        finally: context.close()

    def test_edit_typed_scalars_preserves_reference(self):
        self.open_existing()
        references = self.app.editor.snapshot()['references']
        self.change('Text', 'edited'); self.change('Amount', '5.25')
        self.change('Active', False); self.change('Moment', '0001-01-01T00:00:00')
        self.save()
        state = self.app.editor.snapshot()
        self.assertEqual(state['references'], references)
        card = self.row(self.reference.catalog, self.reference.record)
        self.assertEqual(card.values[:3], ('edited', Decimal('5.25'), False))
        self.assertEqual(card.values[3].year, 1)

    def test_cancel_draft_and_edit_never_persist(self):
        self.select('category'); self.app.event('create'); self.change('Code', '20')
        self.app.event('command', control='CancelButton')
        self.assertIsNone(self.app.editor); self.assertEqual(len(self.app.view.cards), 1)
        self.open_existing(); self.change('Text', 'discard')
        self.app.event('command', control='CancelButton')
        self.assertEqual(self.row(self.reference.catalog, self.reference.record).values[0], 'typed text')
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_dirty_close_cancels_until_explicit_discard(self):
        self.open_existing(); self.change('Text', 'unsaved')
        revision = self.app.editor.form.revision
        self.app.event('closeCard')
        self.assertEqual(self.app.editor.form.revision, revision + 1)
        self.assertEqual(self.app.editor.snapshot()['state'], 'open')
        self.assertTrue(self.app.editor.snapshot()['dirty'])
        self.app.event('command', control='CancelButton')
        self.assertIsNone(self.app.editor)

    def test_repeated_save_does_not_write_or_increment_row_revision(self):
        self.open_existing(); self.change('Text', 'saved'); self.save()
        first = self.row(self.reference.catalog, self.reference.record)
        self.save()
        second = self.row(self.reference.catalog, self.reference.record)
        self.assertEqual(first.revision, second.revision)
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'unchanged')

    def test_duplicate_code_keeps_draft_then_corrected_save(self):
        self.select('category'); self.app.event('create'); self.change('Code', '10')
        self.save()
        state = self.app.editor.snapshot()
        self.assertEqual(state['error'], 'duplicate_code'); self.assertTrue(state['isNew']); self.assertTrue(state['dirty'])
        self.change('Code', '20'); self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'saved')
        self.app.event('closeCard'); self.assertEqual(len(self.app.view.cards), 2)

    def test_original_revision_conflict_is_not_reloaded_away(self):
        self.open_existing(); self.change('Text', 'stale edit')
        before = self.row(self.reference.catalog, self.reference.record)
        tx = self.context.backend.begin_write(uuid4())
        tx.update(CatalogDraft(before.key, before.code, before.description, False,
                               ('other writer',) + before.values[1:]), before.revision)
        tx.commit()
        self.save()
        self.assertEqual(self.app.editor.snapshot()['error'], 'conflict')
        self.assertTrue(self.app.editor.snapshot()['dirty'])
        self.assertEqual(self.row(self.reference.catalog, self.reference.record).values[0], 'other writer')

    def test_uncertain_committed_save_resolves_without_second_write(self):
        self.select('category'); self.app.event('create'); self.change('Code', '20')
        original = _View.commit
        def lose_reply(tx):
            original(tx); raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', lose_reply): self.save()
        self.assertTrue(self.app.editor.snapshot()['editingLocked'])
        with self.assertRaises(UIError): self.change('Description', 'cannot mutate intent')
        with self.assertRaises(UIError): self.app.event('command', control='CancelButton')
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('must not repeat')): self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'saved')
        self.app.event('closeCard'); self.assertEqual(len(self.app.view.cards), 2)

    def test_uncertain_uncommitted_save_reuses_intent_once(self):
        self.select('category'); self.app.event('create'); self.change('Code', '20')
        with mock.patch.object(_View, 'commit', side_effect=BackendError('uncertain_commit')): self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'uncertain')
        self.save(); self.app.event('closeCard')
        self.assertEqual(len(self.app.view.cards), 2)

    def test_committed_refresh_failure_is_not_reported_as_rollback_or_rewritten(self):
        self.open_existing(); self.change('Text', 'committed')
        with mock.patch.object(self.app.editor, '_refresh', side_effect=BackendError('storage_error')): self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'committed')
        self.assertEqual(self.app.editor.snapshot()['error'], 'refresh_required')
        self.assertEqual(self.row(self.reference.catalog, self.reference.record).values[0], 'committed')
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('must not recommit')): self.save()
        self.assertFalse(self.app.editor.snapshot()['dirty'])

    def test_reference_choices_reject_unlisted_and_wrong_target_without_mutation(self):
        self.open_existing()
        before = self.app.editor.snapshot()
        for value in (self.ids['category'], CatalogRef(self.ids['product'], str(UUID(int=0))),
                      CatalogRef(self.ids['category'], str(uuid4())), {'record': str(UUID(int=0))}):
            with self.assertRaises(UIError): self.change('Category', value)
            self.assertEqual(self.app.editor.snapshot(), before)
        self.assertTrue(self.app.snapshot()['capabilities']['referenceEditing'])
        label = _reference_label('x' * 1024, '😀' * 1024)
        self.assertLess(len(label.encode('utf-8')), 4096)
        self.assertTrue(label.endswith('…'))
        self.assertEqual(_reference_label('10', 'Category'), '10 · Category')

    def test_reference_clear_save_and_reopen_is_durable(self):
        self.open_existing()
        empty = CatalogRef(self.ids['category'], str(UUID(int=0)))
        self.change('Category', empty)
        self.assertTrue(self.app.editor.snapshot()['dirty'])
        self.save()
        self.assertFalse(self.app.editor.snapshot()['dirty'])
        self.assertEqual(self.row(self.reference.catalog, self.reference.record).values[-1].record_id, UUID(int=0))
        self.app.event('closeCard'); self.app.close()
        context = SQLiteDBContext(self.path)
        try:
            app = CatalogEditorApplication(context)
            app.select(self.ids['product']); app.open(self.reference)
            field = next(f for f in app.editor.snapshot()['fields'] if f['name'] == 'Category')
            self.assertEqual(field['value']['record'], empty.record)
        finally: context.close()

    def test_new_record_selects_existing_typed_reference(self):
        self.select(); self.app.event('create')
        field = next(f for f in self.app.editor.snapshot()['fields'] if f['name'] == 'Category')
        selected = field['choices'][1]['value']
        self.change('Code', '99')
        self.change('Category', CatalogRef(self.ids['category'], selected))
        self.save()
        record = self.app.editor.snapshot()['reference']['record']
        self.assertEqual(self.row(self.ids['product'], record).values[-1].record_id, UUID(selected))
        with mock.patch.object(self.app.editor.object, 'write', side_effect=AssertionError('repeat write')):
            self.save()
        self.assertEqual(self.app.editor.snapshot()['status'], 'No changes')

    def test_reference_discard_and_dirty_close_preserve_database(self):
        self.open_existing()
        original = self.row(self.reference.catalog, self.reference.record)
        self.change('Category', CatalogRef(self.ids['category'], str(UUID(int=0))))
        self.app.event('closeCard')
        self.assertIsNotNone(self.app.editor)
        self.app.event('command', control='CancelButton')
        self.assertIsNone(self.app.editor)
        self.assertEqual(self.row(self.reference.catalog, self.reference.record), original)

    def test_reference_selection_locked_until_pending_outcome_resolved(self):
        self.open_existing()
        for state in ('pending_commit', 'pending_refresh'):
            setattr(self.app.editor, state, True)
            with self.assertRaisesRegex(UIError, 'busy'):
                self.change('Category', CatalogRef(self.ids['category'], str(UUID(int=0))))
            setattr(self.app.editor, state, False)

    def test_oversized_reference_catalog_remains_explicitly_readonly(self):
        manager = self.app.catalogs.get_index('Categories')
        for index in range(64):
            obj = manager.create_item(); obj.set_member('Code', str(100 + index)); obj.write()
        self.open_existing()
        snapshot = self.app.editor.snapshot()
        self.assertFalse(any(f['name'] == 'Category' for f in snapshot['fields']))
        self.assertEqual(snapshot['references'][0]['reason'], 'reference-choice-limit')
        self.change('Description', 'Scalar still editable'); self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'saved')

    def test_reference_refresh_cannot_adopt_unlisted_key(self):
        self.open_existing(); self.change('Text', 'committed')
        editor = self.app.editor; baseline = editor.baseline; original = editor.object
        previous = self.row(self.reference.catalog, self.reference.record).values[-1]
        # A legitimate concurrent category created after choices were captured.
        category = self.app.catalogs.get_index('Categories').create_item()
        category.set_member('Code', '99'); category.write()
        new_reference = category.get_member('Ref')
        replacement = CatalogKey(previous.database_id, previous.catalog_id, new_reference.reference_uuid)
        def replace_reference(key):
            card = self.row(self.reference.catalog, self.reference.record)
            tx = self.context.backend.begin_write(uuid4())
            tx.update(CatalogDraft(card.key, card.code, card.description, False,
                                   card.values[:-1] + (key,)), card.revision)
            tx.commit()
        refresh = editor._refresh
        def concurrent_reference():
            replace_reference(replacement)
            return refresh()
        with mock.patch.object(editor, '_refresh', concurrent_reference): self.save()
        self.assertEqual(editor.snapshot()['saveState'], 'committed')
        self.assertEqual(editor.snapshot()['error'], 'refresh_required')
        self.assertTrue(editor.snapshot()['editingLocked'])
        self.assertIs(editor.object, original); self.assertEqual(editor.baseline, baseline)
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('no second write')): self.save()
        self.assertTrue(editor.snapshot()['editingLocked'])
        replace_reference(previous)
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('refresh only')): self.save()
        self.assertEqual(editor.snapshot()['saveState'], 'saved')
        self.assertFalse(editor.snapshot()['editingLocked'])

    def test_invalid_typed_input_refused_without_mutating_form(self):
        self.open_existing()
        before = self.app.editor.form.snapshot()
        for name, value in (('Amount', 'oops'), ('Amount', '1E+99999'), ('Moment', '2024-02-30T00:00:00'),
                            ('Moment', '2024-01-01T00:00:00Z'), ('Active', 'False'), ('Text', 1.0)):
            with self.subTest(name=name, value=value), self.assertRaises((UIError, ValueError)):
                self.change(name, value)
        self.assertEqual(self.app.editor.form.snapshot(), before)

    def test_data_is_not_generated_source_and_open_form_holds_no_read_transaction(self):
        self.open_existing()
        text = 'quote"; Raise "not code";'
        self.change('Text', text)
        view = self.context.backend.begin_read(); view.close()
        tx = self.context.backend.begin_write(uuid4()); tx.rollback()
        self.save()
        self.assertEqual(self.row(self.reference.catalog, self.reference.record).values[0], text)

    def test_borrowed_read_repository_does_not_close_application_backend(self):
        self.select()
        self.select('category')
        self.app.event('create'); self.change('Code', '20'); self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'saved')

    def test_committed_refresh_patch_rejection_keeps_original_object_locked(self):
        self.open_existing(); self.change('Text', 'committed')
        editor = self.app.editor; original_object = editor.object; original_baseline = editor.baseline
        refresh = editor._refresh
        def concurrent_backend_valid_form_invalid_value():
            card = self.row(self.reference.catalog, self.reference.record)
            tx = self.context.backend.begin_write(uuid4())
            tx.update(CatalogDraft(card.key, card.code, card.description, False,
                                   ('outside\x00form',) + card.values[1:]), card.revision)
            tx.commit()
            return refresh()
        with mock.patch.object(editor, '_refresh', concurrent_backend_valid_form_invalid_value):
            with self.assertRaises(ValueError): self.save()
        snapshot = editor.snapshot()
        self.assertIs(editor.object, original_object); self.assertEqual(editor.baseline, original_baseline)
        self.assertEqual(snapshot['saveState'], 'committed'); self.assertTrue(snapshot['editingLocked'])
        self.assertTrue(snapshot['dirty'])
        with self.assertRaises(UIError): self.change('Text', 'must not overwrite')
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('refresh must never write')):
            with self.assertRaises(ValueError): self.save()
        self.assertEqual(self.row(self.reference.catalog, self.reference.record).values[0], 'outside\x00form')
        card = self.row(self.reference.catalog, self.reference.record)
        tx = self.context.backend.begin_write(uuid4())
        tx.update(CatalogDraft(card.key, card.code, card.description, False,
                               ('repaired externally',) + card.values[1:]), card.revision); tx.commit()
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('refresh only')): self.save()
        self.assertFalse(editor.snapshot()['editingLocked'])
        self.assertEqual(next(f['inputText'] for f in editor.snapshot()['fields'] if f['name'] == 'Text'), 'repaired externally')

    def test_transient_uncertain_resolution_error_cannot_unlock_or_replace_intent(self):
        self.select('category'); self.app.event('create'); self.change('Code', '20')
        commit = _View.commit
        def lost_reply(tx):
            commit(tx); raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', lost_reply): self.save()
        for code in ('busy', 'storage_error'):
            with mock.patch.object(self.context.backend, 'resolve_write', side_effect=BackendError(code)): self.save()
            self.assertTrue(self.app.editor.snapshot()['editingLocked'])
            self.assertEqual(self.app.editor.snapshot()['saveState'], 'uncertain')
            with self.assertRaises(UIError): self.change('Code', '30')
            with self.assertRaises(UIError): self.app.event('command', control='CancelButton')
        with mock.patch.object(_View, 'commit', side_effect=AssertionError('must not duplicate')): self.save()
        self.assertEqual(self.app.editor.snapshot()['saveState'], 'saved')
        self.app.event('closeCard'); self.assertEqual(len(self.app.view.cards), 2)
