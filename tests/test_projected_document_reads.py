"""Document point/range projections preserve their integrity and snapshot scopes."""
from contextlib import closing
from datetime import datetime
import sqlite3
import unittest
from unittest.mock import patch

import test_document_query_port as fixtures
import test_document_posting_query_runtime as posting
from yadinassi.catalog_backend import BackendError
from yadinassi.document_backend import DocumentScanRequest, DocumentSelection
from yadinassi.sqlite_documents import DocumentView


class ProjectedDocumentReadTests(unittest.TestCase):
    setUp = fixtures.DocumentQueryPortTests.setUp
    tearDown = fixtures.DocumentQueryPortTests.tearDown
    object = fixtures.DocumentQueryPortTests.object
    sql = fixtures.DocumentQueryPortTests.sql
    seed = fixtures.DocumentQueryPortTests.seed
    view = fixtures.DocumentQueryPortTests.view

    def manager(self): return self.vm._documents.get_index('Orders')

    def test_cold_empty_range_validates_but_does_not_construct_full_cards(self):
        self.seed(30); view = self.view()
        with patch.object(view,'_card',side_effect=AssertionError('unselected card')), \
                patch.object(view,'_sections',wraps=view._sections) as sections:
            rows = view.select_documents(self.schema.identity,DocumentSelection(datetime(2027,1,1)))
        self.assertEqual(rows, ())
        self.assertEqual(sections.call_count,30)  # Cold integrity is not free.

    def test_warm_empty_range_across_leases_fetches_no_sections(self):
        self.seed(30); view = self.view(); view._validate_query_source(self.schema); view.close()
        view = self.view(); trace=[]; view._connection.set_trace_callback(trace.append)
        with patch.object(view,'_sections',side_effect=AssertionError('warm sections')):
            self.assertEqual(view.select_documents(self.schema.identity,
                DocumentSelection(datetime(2027,1,1))),())
        selected=[sql for sql in trace if sql.startswith('SELECT r.record_id')]
        self.assertEqual(len(selected),1)
        self.assertIn("r.date>='20270101000000'",selected[0])
        self.assertIn('LIMIT 1001',selected[0])

    def test_select_boundaries_inclusive_and_full_detached_cards_preserved(self):
        self.seed(3); view = self.view()
        moment=datetime(2026,11,9,12,30,5)
        rows=view.select_documents(self.schema.identity,DocumentSelection(moment,moment))
        self.assertEqual(len(rows),3)
        self.assertTrue(all(hasattr(row,'tabular_sections') for row in rows))
        view.close()
        self.sql("UPDATE document_record SET date='20270101000000'")
        self.assertTrue(all(row.date==moment for row in rows))

    def test_select_overflow_still_refuses_instead_of_truncating(self):
        self.seed(3); view=self.view()
        with self.assertRaisesRegex(BackendError,'unsupported'):
            view.select_documents(self.schema.identity,DocumentSelection(limit=2))
        with self.assertRaisesRegex(BackendError,'invalid_input'):
            view.select_documents(self.schema.identity,DocumentSelection(datetime(2027,1,1),datetime(2026,1,1)))

    def test_select_overflow_preserves_sorted_error_frontier(self):
        self.seed(3)
        self.sql("UPDATE document_record SET values_json='[]' WHERE number='000000003'")
        view=self.view()
        with self.assertRaisesRegex(BackendError,'unsupported'):
            view.select_documents(self.schema.identity,DocumentSelection(limit=1))
        with self.assertRaisesRegex(BackendError,'integrity'):
            view.select_documents(self.schema.identity,DocumentSelection(limit=3))

    def test_repeated_standard_ref_field_reads_fetch_neither_json_payload(self):
        self.seed(3); manager=self.manager(); ref=manager.find_by_number('000000001')
        self.assertEqual(manager._read_member(ref,'Number'),'000000001')
        trace=[]; self.context.backend._read_handle.connection.set_trace_callback(trace.append)
        with patch.object(DocumentView,'_sections',side_effect=AssertionError('sections')):
            for _ in range(10): self.assertEqual(manager._read_member(ref,'Number'),'000000001')
        reads=[sql for sql in trace if ' FROM document_record' in sql]
        self.assertEqual(len(reads),10)
        self.assertTrue(all('values_json' not in sql and 'sections_json' not in sql for sql in reads))

    def test_custom_ref_field_reads_only_header_json_after_selected_row_proof(self):
        self.seed(2); manager=self.manager(); ref=manager.find_by_number('000000001')
        field=self.schema.fields[0]
        trace=[]; self.context.backend._read_handle.connection.set_trace_callback(trace.append)
        with patch.object(DocumentView,'_sections',side_effect=AssertionError('sections')):
            manager._read_member(ref,field.name)
        reads=[sql for sql in trace if ' FROM document_record' in sql]
        self.assertEqual(len(reads),1)
        self.assertIn('values_json',reads[0]); self.assertNotIn('sections_json',reads[0])

    def test_same_generation_selected_section_tamper_is_not_hidden_by_number_getter(self):
        self.seed(2); manager=self.manager(); ref=manager.find_by_number('000000001')
        self.sql("UPDATE document_record SET sections_json='[]' WHERE number='000000001'")
        with self.assertRaisesRegex(BackendError,'integrity'): manager._read_member(ref,'Number')

    def test_point_scope_does_not_silently_become_full_unrelated_semantic_validation(self):
        self.seed(2); manager=self.manager()
        self.sql("UPDATE document_record SET values_json='[]' WHERE number='000000002'")
        ref=manager.find_by_number('000000001')
        self.assertEqual(manager._read_member(ref,'Number'),'000000001')
        with self.assertRaisesRegex(BackendError,'integrity'): manager.find_by_number('000000002')

    def test_unrelated_source_coarse_budget_tamper_still_refuses_point_read(self):
        self.seed(2); manager=self.manager(); ref=manager.find_by_number('000000001')
        self.sql('UPDATE document_record SET sections_json=? WHERE number=?',('x'*(1024*1024+1),'000000002'))
        with self.assertRaisesRegex(BackendError,'integrity'): manager._read_member(ref,'Number')

    def test_find_number_keeps_binary_exactness_and_no_warm_card_decode(self):
        self.seed(2)
        self.sql("UPDATE document_record SET number='Alpha' WHERE number='000000001'")
        manager=self.manager(); ref=manager.find_by_number('Alpha')
        self.assertFalse(ref.is_empty()); self.assertTrue(manager.find_by_number('alpha').is_empty())
        with patch.object(DocumentView,'_decode_record',side_effect=AssertionError('warm decode')):
            self.assertEqual(manager.find_by_number('Alpha'),ref)

    def test_get_object_keeps_full_payload_and_point_values_are_not_partial_cards(self):
        self.seed(2); manager=self.manager(); ref=manager.find_by_number('000000001')
        with closing(self.context.backend.begin_document_read()) as view:
            row=view.read_document_values(manager._key(ref.reference_uuid),('number',))
            self.assertEqual(row.values,('000000001',))
            self.assertFalse(hasattr(row,'tabular_sections'))
            card=view.read_document(manager._key(ref.reference_uuid))
            self.assertEqual(len(card.tabular_sections),len(self.schema.tabular_sections))


class BatchedPostedReadTests(unittest.TestCase):
    make=posting.PostingQueryRuntimeTests.make

    def test_cold_validation_and_projection_do_not_do_per_document_posted_reads(self):
        vm,context=self.make()
        vm.execute('For I=1 To 5 Do O=Documents.OwnedPostingDoc.CreateDocument();O.Number=String(I);O.Write();EndDo;')
        schema=context.backend._document_schemas[0]
        with closing(context.backend.begin_query_read()) as view:
            trace=[];view._connection.set_trace_callback(trace.append)
            with patch('yadinassi.sqlite_document_posting_state.read_posted',side_effect=AssertionError('per-row Posted')):
                page=view.scan_document_values(schema.identity,DocumentScanRequest(),('number','posted'))
            self.assertEqual(len(page.rows),5)
            self.assertTrue(all(row.values[1] is False for row in page.rows))
        joins=[sql for sql in trace if 'LEFT JOIN document_posting_state' in sql]
        self.assertEqual(len(joins),2)

    def test_hidden_corrupt_posted_state_still_refuses_nonposted_projection(self):
        vm,context=self.make()
        vm.execute('O=Documents.OwnedPostingDoc.CreateDocument();O.Number="1";O.Write();')
        schema=context.backend._document_schemas[0]
        with closing(context.backend.begin_query_read()) as view:
            view.scan_document_values(schema.identity,DocumentScanRequest(),('number',))
        with closing(sqlite3.connect(context.backend.path)) as connection,connection:
            connection.execute('UPDATE document_posting_state SET document_revision=document_revision+100')
        with closing(context.backend.begin_query_read()) as view:
            with self.assertRaisesRegex(BackendError,'integrity'):
                view.scan_document_values(schema.identity,DocumentScanRequest(),('number',))
