"""Scalar/section chooser integration through existing typed edit paths."""
import unittest
from unittest import mock
from uuid import UUID, uuid4
import test_catalog_editor as scalar
import test_catalog_section_editor as section
from yadinassi.catalog_backend import CatalogDraft, CatalogKey
from yadinassi.ui.protocol import UIError, CatalogRef


class ScalarChoiceTests(unittest.TestCase):
    setUp = scalar.CatalogEditorTests.setUp
    select = scalar.CatalogEditorTests.select
    open_existing = scalar.CatalogEditorTests.open_existing

    def start(self):
        field = next(f for f in self.app.editor.snapshot()['fields'] if f['name'] == 'Category')
        self.app.event('referenceChoice', action={'action':'begin','control':field['control'],'section':None,'row':None})
        return self.app.snapshot()['state']['referenceChoice'], field

    def test_large_target_lazy_choice_then_save(self):
        tx = self.context.backend.begin_write(uuid4())
        try:
            for i in range(70):
                tx.create(CatalogDraft(CatalogKey(tx.database_id, UUID(self.ids['category']),uuid4()),f'X{i:03}',f'Category {i}',False,()))
            tx.commit()
        finally: tx.close()
        self.open_existing()
        choice, field = self.start()
        self.assertTrue(field['lazyChoice'])
        self.assertLessEqual(len(field['choices']), 2)
        self.assertEqual(choice['navigation']['total'],71)
        self.app.event('referenceChoice',action={'action':'search','ticket':choice['ticket'],'query':'X069'})
        found = self.app.snapshot()['state']['referenceChoice']
        self.app.event('referenceChoice',action={'action':'apply','ticket':found['ticket'],'choice':found['rows'][0]['choice']})
        self.assertIsNone(self.app.snapshot()['state']['referenceChoice'])
        self.app.event('command', control='SaveButton')
        self.assertEqual(self.app.editor.save_state,'saved')

    def test_arbitrary_reference_not_admitted(self):
        self.open_existing(); _, field = self.start()
        with self.assertRaises(UIError):
            self.app.editor.change(field['control'], CatalogRef(self.ids['category'],str(uuid4())))

    def test_destination_change_and_pending_refresh_refuse(self):
        self.open_existing(); choice, field = self.start()
        self.app.editor.change(field['control'],CatalogRef(self.ids['category'],str(UUID(int=0))))
        with self.assertRaises(UIError):
            self.app.event('referenceChoice',action={'action':'apply','ticket':choice['ticket'],'choice':choice['rows'][0]['choice']})
        self.app.editor.pending_refresh=True
        with self.assertRaises(UIError): self.start()
        self.app.editor.pending_refresh=False

    def test_envelope_failure_keeps_old_choice(self):
        self.open_existing(); choice, _ = self.start()
        with mock.patch('yadinassi.ui.catalog_editor.encode_line',side_effect=UIError('message_limit')):
            with self.assertRaises(UIError):
                self.app.event('referenceChoice',action={'action':'search','ticket':choice['ticket'],'query':'missing'})
        self.assertEqual(self.app.snapshot()['state']['referenceChoice'],choice)

    def test_cancel_and_other_event_retire_ticket(self):
        self.open_existing(); choice, _ = self.start()
        self.app.event('referenceChoice',action={'action':'cancel','ticket':choice['ticket']})
        with self.assertRaises(UIError): self.app.event('referenceChoice',action={'action':'clear','ticket':choice['ticket']})
        choice, _ = self.start()
        self.app.event('command',control='SaveButton')
        self.assertIsNone(self.app.snapshot()['state']['referenceChoice'])


class SectionChoiceTests(unittest.TestCase):
    setUp = section.CatalogSectionEditorTests.setUp
    section = section.CatalogSectionEditorTests.section

    def test_section_apply_uses_row_identity_and_typed_event(self):
        row = self.section()['rows'][0]
        self.app.event('referenceChoice',action={'action':'begin','control':None,'section':'Склады','row':row['id']})
        choice = self.app.snapshot()['state']['referenceChoice']
        self.app.event('referenceChoice',action={'action':'apply','ticket':choice['ticket'],'choice':choice['rows'][0]['choice']})
        self.assertEqual(self.section()['rows'][0]['id'],row['id'])
        self.assertTrue(self.editor.snapshot()['dirty'])
