"""Detached list filters and post-save refresh, real logical/SQLite route."""
import unittest
import test_catalog_editor as support
from yadinassi.ui.protocol import UIError
from yadinassi.ui.editor_protocol import validate_request

class CatalogEditorSearchTests(unittest.TestCase):
    setUp = support.CatalogEditorTests.setUp
    select = support.CatalogEditorTests.select
    change = support.CatalogEditorTests.change
    save = support.CatalogEditorTests.save

    def test_search_snapshot_and_refresh_keep_query(self):
        self.select('category')
        original = self.app.view.cards[0]
        self.app.event('filterRecords', query=original.value('Code'), order='description')
        self.assertEqual(len(self.app.view.cards),1)
        self.app.event('refreshRecords')
        self.assertEqual(self.app.order,'description')
        self.assertEqual(self.app.query,original.value('Code'))
        self.assertEqual(self.app.view.cards[0].reference,original.reference)

    def test_saved_record_outside_filter_is_not_pending_write(self):
        self.select('category')
        reference = self.app.view.cards[0].reference
        self.app.event('filterRecords',query='not-yet-present',order='code')
        self.assertEqual(len(self.app.view.cards),0)
        self.app.event('openCard',reference=reference)
        self.change('Description','Saved but not matching')
        self.save()
        self.assertEqual(self.app.editor.save_state,'saved')
        self.assertFalse(self.app.editor.pending_refresh)
        self.assertEqual(len(self.app.view.cards),0)
        self.assertIn('outside',self.app.list_notice)
        self.app.event('closeCard')
        self.assertEqual(len(self.app.view.cards),0)

    def test_filter_rejects_during_editor_and_preserves_draft(self):
        self.select('category');self.app.event('create')
        editor=self.app.editor
        for event,values in [('filterRecords',{'query':'','order':'code'}),('refreshRecords',{})]:
            with self.assertRaises(UIError):self.app.event(event,**values)
        self.assertIs(self.app.editor,editor)

    def test_switch_catalog_resets_filter(self):
        self.select('category');self.app.event('filterRecords',query='absent',order='description')
        self.select('product')
        self.assertEqual((self.app.query,self.app.order),('','code'))
        self.assertGreater(len(self.app.view.cards),0)

    def test_protocol_is_closed_and_bounded(self):
        def request(**values):
            return {'jsonrpc':'2.0','id':1,'method':'editor.event','params':{'baseRevision':0,**values}}
        validate_request(request(event='filterRecords',query='x',order='code'))
        validate_request(request(event='refreshRecords'))
        for values in ({'query':'x'*129,'order':'code'}, {'query':'','order':'sql'}, {'query':False,'order':'code'}):
            with self.assertRaises(UIError):validate_request(request(event='filterRecords',**values))
        with self.assertRaises(UIError):validate_request(request(event='refreshRecords',extra=True))

    def test_failed_envelope_restores_entire_list_state(self):
        from unittest import mock
        self.select('category')
        before=self.app._list_state()
        for event,values in [('filterRecords',{'query':'absent','order':'description'}),('refreshRecords',{})]:
            with mock.patch.object(self.app,'_preflight_list',side_effect=UIError('message_limit')):
                with self.assertRaises(UIError):self.app.event(event,**values)
            self.assertEqual(self.app._list_state(),before)
            self.assertIs(self.app.summary,before[1])

    def test_missing_saved_record_is_not_misreported_as_filter(self):
        from unittest import mock
        from dataclasses import replace
        self.select('category');reference=self.app.view.cards[0].reference
        self.app.event('openCard',reference=reference);self.change('Description','Updated')
        load=self.app._load
        def concurrent_disappearance():
            load()
            self.app.summary=replace(self.app.summary,cards=())
            return self.app.summary.select(query=self.app.query,order=self.app.order)
        with mock.patch.object(self.app,'_load',side_effect=concurrent_disappearance):self.save()
        self.assertEqual(self.app.editor.save_state,'saved')
        self.assertFalse(self.app.editor.pending_refresh)
        self.assertEqual(self.app.list_notice,'Saved record is no longer available')
        with mock.patch.object(support._View,'commit',side_effect=AssertionError('must not repeat write')):
            self.save()

    def test_external_writer_visible_only_after_refresh(self):
        from uuid import uuid4
        from yadinassi.catalog_backend import CatalogDraft
        self.select('category');reference=self.app.view.cards[0].reference
        card=support.CatalogEditorTests.row(self,reference.catalog,reference.record)
        tx=self.context.backend.begin_write(uuid4())
        tx.update(CatalogDraft(card.key,card.code,'External new label',card.deletion_mark,card.values),card.revision)
        tx.commit()
        self.app.event('filterRecords',query='External new label',order='description')
        self.assertEqual(len(self.app.view.cards),0)
        self.app.event('refreshRecords')
        self.assertEqual(len(self.app.view.cards),1)
        self.assertEqual(self.app.view.cards[0].reference,reference)
