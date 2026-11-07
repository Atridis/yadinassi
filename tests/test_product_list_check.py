"""Original demo list checks only persisted data through one read snapshot."""
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_imported_product_editor as fixture
from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import _View
from yadinassi.ui.protocol import CatalogRef, UIError, encode_value, encode_line, decode_line
from yadinassi.ui.editor_protocol import CatalogEditorSession, PROTOCOL


class ProductListCheckTests(unittest.TestCase):
    setUp = fixture.ImportedProductEditorTests.setUp
    ref = staticmethod(fixture.ImportedProductEditorTests.ref)
    change = fixture.ImportedProductEditorTests.change
    row = fixture.ImportedProductEditorTests.row
    valid = fixture.ImportedProductEditorTests.valid
    save = fixture.ImportedProductEditorTests.save

    def saved(self):
        self.valid(); self.save()
        self.reference = self.ref(self.editor.object)
        self.app.event('closeCard')
        return self.reference

    def check(self, reference):
        self.app.event('checkCard', reference=reference)
        return self.app.snapshot()['state']['listCheck']['messages']

    def test_valid_original_success_without_write(self):
        ref = self.saved()
        with patch.object(self.app.backend, 'begin_write', side_effect=AssertionError('write')):
            messages = self.check(ref)
        self.assertEqual(len(messages), 1)
        self.assertIn('Карточка заполнена корректно', messages[0]['text'])

    def test_empty_selection_original_message(self):
        self.saved()
        self.assertEqual(self.check(None)[0]['text'], 'Выберите номенклатуру в списке.')

    def test_missing_saved_card_original_message(self):
        self.saved()
        self.assertIn('Карточка уже удалена', self.check(CatalogRef(self.catalog, str(uuid4())))[0]['text'])

    def test_deletion_mark_original_message(self):
        ref = self.saved()
        obj = self.editor.object
        obj.set_member('DeletionMark', True); obj.write()
        self.assertIn('Карточка помечена на удаление', self.check(ref)[0]['text'])

    def test_changed_kind_checked_fresh(self):
        ref = self.saved()
        self.kind.set_member('DeletionMark', True); self.kind.write()
        self.assertIn('вид номенклатуры помечен', self.check(ref)[0]['text'])

    def test_changed_warehouse_checked_fresh(self):
        ref = self.saved()
        self.warehouse.set_member('DeletionMark', True); self.warehouse.write()
        self.assertIn('Склад помечен на удаление', self.check(ref)[0]['text'])

    def test_open_editor_rejects_command_and_clears_messages(self):
        ref = self.saved(); self.check(ref); self.app.event('openCard', reference=ref)
        self.assertEqual(self.app.snapshot()['state']['listCheck']['messages'], [])
        with self.assertRaises(UIError): self.check(ref)
        self.assertIsNotNone(self.app.editor)

    def test_foreign_reference_rejected(self):
        self.saved()
        with self.assertRaises(UIError): self.check(self.ref(self.kind))

    def test_source_error_releases_read_snapshot_and_clears_message(self):
        ref = self.saved(); self.check(ref)
        with patch.object(_View, 'product_list_sources', side_effect=BackendError('schema_changed')):
            with self.assertRaises(BackendError): self.check(ref)
        self.assertIsNone(self.app.backend._active)
        self.assertEqual(self.app.list_messages, ())

    def test_protocol_null_and_saved_reference(self):
        ref = self.saved(); session = CatalogEditorSession(self.app)
        hello = {'jsonrpc':'2.0','id':1,'method':'editor.hello','params':{'protocol':PROTOCOL}}
        self.assertIn('result', decode_line(session.exchange(encode_line(hello))))
        for index, reference in enumerate((None, encode_value(ref)), 2):
            request = {'jsonrpc':'2.0','id':index,'method':'editor.event','params':{
                'event':'checkCard','baseRevision':index-2,'reference':reference}}
            result = decode_line(session.exchange(encode_line(request)))
            self.assertIn('result', result)
            self.assertEqual(len(result['result']['state']['listCheck']['messages']), 1)

    def test_all_record_reads_share_source_snapshot(self):
        ref = self.saved(); reads = []; sources = []
        read = _View.read_catalog; source = _View.product_list_sources
        def capture(view, key):
            reads.append(view); return read(view, key)
        def capture_source(view, catalog):
            sources.append(view); return source(view, catalog)
        with patch.object(_View, 'read_catalog', capture), patch.object(_View, 'product_list_sources', capture_source):
            self.check(ref)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(reads), 3)
        self.assertTrue(all(view is sources[0] for view in reads))
        self.assertIsNone(sources[0]._operation_id)

    def test_modified_source_is_not_executed(self):
        ref = self.saved(); original = _View.product_list_sources
        def changed(view, catalog):
            form, obj = original(view, catalog)
            return form + b'\n', obj
        with patch.object(_View, 'product_list_sources', changed):
            with self.assertRaises(BackendError): self.check(ref)
        self.assertEqual(self.app.list_messages, ())
        self.assertIsNone(self.app.backend._active)

    def test_repeated_check_does_not_normalize_saved_name_or_revision(self):
        from yadinassi.catalog_backend import CatalogDraft
        ref = self.saved(); key = self.editor.object._key
        view = self.app.backend.begin_read()
        try: card = view.read_catalog(key)
        finally: view.close()
        view = self.app.backend.begin_write(uuid4())
        try:
            view.update(CatalogDraft(key, card.code, '  Кабель USB-C  ', False,
                                     card.values), card.revision)
            view.commit()
        finally: view.close()
        view = self.app.backend.begin_read()
        try: before = view.read_catalog(key)
        finally: view.close()
        first = self.check(ref); self.assertEqual(self.check(ref), first)
        view = self.app.backend.begin_read()
        try: self.assertEqual(view.read_catalog(key), before)
        finally: view.close()

    def test_other_catalog_has_no_command(self):
        self.saved(); self.app.event('selectCatalog', catalog=str(self.kind._key.catalog_id))
        self.assertFalse(self.app.snapshot()['state']['listCheck']['available'])
        with self.assertRaises(UIError): self.check(self.ref(self.kind))

    def test_invalid_saved_card_emits_original_errors(self):
        from yadinassi.catalog_backend import CatalogDraft
        ref = self.saved(); key = self.editor.object._key
        view = self.app.backend.begin_read()
        try: card = view.read_catalog(key)
        finally: view.close()
        view = self.app.backend.begin_write(uuid4())
        try:
            view.update(CatalogDraft(key, card.code, 'x', False, card.values, ()), card.revision)
            view.commit()
        finally: view.close()
        messages = self.check(ref)
        self.assertEqual([m['field'] for m in messages], ['Наименование', 'Склады'])
        self.assertNotIn('корректно', ' '.join(m['text'] for m in messages))
