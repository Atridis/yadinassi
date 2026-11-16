"""Bounded single-query section Read and post-write verification."""
import unittest
from uuid import uuid4
from unittest.mock import patch
import test_source_document_sections as fixture

class SourceSectionPointReadTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store

    def populated(self,source=None):
        s=self.store(source);rid=uuid4()
        sections={'lines':({'flag':True},)} if s.document('Invoice').sections else {}
        s.write_document_bundle('Invoice',rid,0,self.values(),sections)
        return s,rid

    def point_queries(self,s,action):
        sql=[];s._connection.set_trace_callback(sql.append)
        try:result=action()
        finally:s._connection.set_trace_callback(None)
        return result,[q for q in sql if q.startswith('SELECT ') and 'FROM source_document_section WHERE document_identity=' in q]

    def test_read_one_bounded_query(self):
        s,rid=self.populated();result,sql=self.point_queries(s,lambda:s.read_document_bundle('Invoice',rid))
        self.assertEqual(result[3],{'lines':({'flag':True},)})
        self.assertEqual(len(sql),1);self.assertTrue(sql[0].endswith('LIMIT 2'))

    def test_write_one_bounded_query(self):
        s,rid=self.populated()
        revision,sql=self.point_queries(s,lambda:s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':()}))
        self.assertEqual(revision,2);self.assertEqual(len(sql),1)

    def test_missing_inventory(self):
        s,rid=self.populated();s._connection.execute('DELETE FROM source_document_section')
        with self.assertRaisesRegex(ValueError,'inventory'):s.read_document_bundle('Invoice',rid)

    def test_extra_inventory(self):
        s,rid=self.populated()
        s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',
            (str(s.document('Invoice').identity),str(rid),str(uuid4()),'[]'))
        with self.assertRaisesRegex(ValueError,'inventory'):s.read_document_bundle('Invoice',rid)

    def test_unknown_inventory(self):
        s,rid=self.populated();s._connection.execute('UPDATE source_document_section SET section_identity=?',(str(uuid4()),))
        with self.assertRaisesRegex(ValueError,'inventory'):s.read_document_bundle('Invoice',rid)

    def test_noncanonical(self):
        s,rid=self.populated();s._connection.execute('UPDATE source_document_section SET payload=?',('[ [true] ]',))
        with self.assertRaises(ValueError):s.read_document_bundle('Invoice',rid)

    def test_aggregate_bytes(self):
        s,rid=self.populated()
        with patch('yadinassi.source_document_section_store._MAX_DOCUMENT_BYTES',1):
            with self.assertRaisesRegex(ValueError,'byte bound'):s.read_document_bundle('Invoice',rid)

    def test_row_bound(self):
        s,rid=self.populated()
        with patch('yadinassi.source_document_section_store._MAX_ROWS',0):
            with self.assertRaisesRegex(ValueError,'row bound'):s.read_document_bundle('Invoice',rid)

    def test_zero_sections(self):
        s,rid=self.populated(fixture.package(children=''))
        result,sql=self.point_queries(s,lambda:s.read_document_bundle('Invoice',rid))
        self.assertEqual(result[3],{});self.assertEqual(len(sql),1);self.assertTrue(sql[0].endswith('LIMIT 1'))

    def test_zero_sections_cannot_hide_payload(self):
        s,rid=self.populated(fixture.package(children=''))
        s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',
            (str(s.document('Invoice').identity),str(rid),str(uuid4()),'[]'))
        with self.assertRaisesRegex(ValueError,'inventory'):s.read_document_bundle('Invoice',rid)

    def test_failure_aborts_outer_transaction(self):
        s,rid=self.populated();s.begin_transaction()
        s._connection.execute('UPDATE source_document_section SET payload=?',('[[]]',))
        with self.assertRaises(ValueError):s.read_document_bundle('Invoice',rid)
        self.assertFalse(s.transaction_active)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],{'lines':({'flag':True},)})

    def test_success_preserves_outer_transaction(self):
        s,rid=self.populated();s.begin_transaction()
        s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':()})
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],{'lines':()})
        self.assertTrue(s.transaction_active);s.rollback_transaction()
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],{'lines':({'flag':True},)})
