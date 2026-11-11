"""Read-only capacity classification; no form or interpreter construction."""
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import unittest

from yadinassi.catalog_backend import FieldSchema, TabularSectionSchema, TabularSectionRows, TabularRow, BackendError
from yadinassi.document_backend import DocumentSchema, DocumentKey, DocumentRevision, DocumentCard
from yadinassi.configuration_document import _OpenedDocument, _read_form_document, _FormCapacityError
from yadinassi.form_tables import FormTableSchema, FormTableColumn
from yadinassi.type_descriptions import BSLTypeDescription


class DocumentOpenPreflightTests(unittest.TestCase):
    def fixture(self, section_count=1, columns=3, rows=32):
        fields=tuple(FieldSchema(uuid4(),'Flag'+str(i),'boolean') for i in range(columns))
        sections=tuple(TabularSectionSchema(uuid4(),'Lines'+str(i),fields) for i in range(section_count))
        schema=DocumentSchema(uuid4(),'Receipt',9,tabular_sections=sections)
        backend=SimpleNamespace(database_id=uuid4(),configuration_generation=1)
        context=SimpleNamespace(backend=backend)
        key=DocumentKey(backend.database_id,schema.identity,uuid4())
        revision=DocumentRevision(key.database_id,1,key.document_id,key.record_id,'private-revision')
        card=DocumentCard(key,revision,'1',datetime(2026,1,1),False,(),tuple(
            TabularSectionRows(s.identity,tuple(TabularRow(uuid4(),(True,)*columns) for _ in range(rows))) for s in sections))
        tables=tuple(FormTableSchema(s.name,tuple(FormTableColumn(f.name,BSLTypeDescription('Boolean')) for f in fields)) for s in sections)
        definition=SimpleNamespace(document_schema=schema,tables=tables,object_sections=tuple((s.name,s.name) for s in sections))
        view=SimpleNamespace(document_schema=lambda identity:schema,read_document=lambda requested:card,close=Mock())
        backend.begin_document_read=lambda:view
        return context,definition,key,card,view

    def test_exact_row_and_aggregate_cell_limits_admitted(self):
        context,definition,key,card,view=self.fixture(section_count=2,columns=4)
        opened=_read_form_document(context,definition,key)
        self.assertIs(opened.take(context,definition.document_schema,key),card)
        self.assertEqual(sum(len(s.rows) for s in card.tabular_sections),64)
        view.close.assert_called_once_with()

    def test_one_extra_row_is_known_refusal_and_closes_lease(self):
        context,definition,key,card,view=self.fixture(rows=33)
        with self.assertRaises(_FormCapacityError):_read_form_document(context,definition,key)
        view.close.assert_called_once_with()
        self.assertEqual(len(card.tabular_sections[0].rows),33)

    def test_individually_valid_tables_cannot_exceed_aggregate_cells(self):
        context,definition,key,card,view=self.fixture(section_count=3,columns=3)
        with self.assertRaises(_FormCapacityError):_read_form_document(context,definition,key)
        view.close.assert_called_once_with()
        self.assertEqual(len(card.tabular_sections),3)

    def test_same_database_different_backend_is_not_same_open_owner(self):
        context,definition,key,card,view=self.fixture()
        opened=_read_form_document(context,definition,key)
        other=SimpleNamespace(backend=SimpleNamespace(database_id=key.database_id,configuration_generation=1))
        with self.assertRaises(BackendError):opened.take(other,definition.document_schema,key)

    def test_generation_and_record_rebinding_are_refused(self):
        context,definition,key,card,view=self.fixture()
        opened=_read_form_document(context,definition,key)
        with self.assertRaises(BackendError):opened.take(context,definition.document_schema,replace(key,record_id=uuid4()))
        context.backend.configuration_generation=2
        with self.assertRaises(BackendError):opened.take(context,definition.document_schema,key)

    def test_unknown_read_and_cleanup_errors_are_not_capacity_refusals(self):
        context,definition,key,card,view=self.fixture(rows=33)
        view.read_document=Mock(side_effect=BackendError('integrity'))
        with self.assertRaises(BackendError):_read_form_document(context,definition,key)
        view.close.assert_called_once_with()
        context,definition,key,card,view=self.fixture(rows=33)
        view.close.side_effect=RuntimeError('cleanup failed')
        with self.assertRaises(RuntimeError):_read_form_document(context,definition,key)
