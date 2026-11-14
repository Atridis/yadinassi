"""Batch selection keeps every section integrity check and snapshot boundary."""
import unittest
from uuid import uuid4
from unittest.mock import patch
import test_source_document_sections as fixture
from yadinassi.source_document_section_store import SourceDocumentSectionStore

class SourceSectionBatchReadTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store
    def populated(self,count=3):
        s=self.store();ids=[]
        s.begin_transaction()
        for n in range(count):
            rid=uuid4();ids.append(rid)
            s.write_document_bundle('Invoice',rid,0,self.values(str(n)),{'lines':({'flag':bool(n%2)},)})
        s.commit_transaction();return s,ids
    def payload_reads(self,s,identity=None):
        sql=[];s._connection.set_trace_callback(sql.append)
        try:result=s.read_documents('Invoice',identity)
        finally:s._connection.set_trace_callback(None)
        return result,[q for q in sql if q.startswith('SELECT record_identity,section_identity,payload FROM source_document_section')]
    def test_one_payload_query_many(self):
        s,ids=self.populated(32);rows,queries=self.payload_reads(s)
        self.assertEqual([r[0] for r in rows],sorted(ids,key=str));self.assertEqual(len(queries),1)
    def test_one_payload_query_single(self):
        s,ids=self.populated();rows,queries=self.payload_reads(s,ids[1]);self.assertEqual(rows[0][0],ids[1]);self.assertEqual(len(queries),1)
    def test_empty(self):
        s=self.store();rows,queries=self.payload_reads(s);self.assertEqual(rows,[]);self.assertEqual(len(queries),1)
    def test_old_per_record_path_not_used(self):
        s,_=self.populated()
        with patch.object(s,'_sections',side_effect=AssertionError('N+1')):self.assertEqual(len(s.read_documents('Invoice')),3)
    def test_missing_section(self):
        s,ids=self.populated();s._connection.execute('DELETE FROM source_document_section WHERE record_identity=?',(str(ids[1]),))
        with self.assertRaisesRegex(ValueError,'inventory'):s.read_documents('Invoice')
    def test_invalid_last_payload(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET payload=? WHERE record_identity=?',('[[]]',str(max(ids,key=str))))
        with self.assertRaises(ValueError):s.read_documents('Invoice')
    def test_noncanonical(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET payload=? WHERE record_identity=?',('[ [ true ] ]',str(ids[0])))
        with self.assertRaises(ValueError):s.read_documents('Invoice')
    def test_unknown_section(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET section_identity=? WHERE record_identity=?',(str(uuid4()),str(ids[0])))
        with self.assertRaisesRegex(ValueError,'inventory'):s.read_documents('Invoice')
    def test_orphan_sections(self):
        s,ids=self.populated();s._connection.execute('PRAGMA foreign_keys=OFF');s._connection.execute('DELETE FROM source_document_record WHERE record_identity=?',(str(ids[0]),))
        with self.assertRaises(ValueError):s.read_documents('Invoice')
    def test_transaction_visibility_and_preservation(self):
        s,ids=self.populated();s.begin_transaction();s.write_document_bundle('Invoice',uuid4(),0,self.values('Z'),{'lines':()})
        self.assertEqual(len(s.read_documents('Invoice')),4);self.assertTrue(s.transaction_active);s.rollback_transaction();self.assertEqual(len(s.read_documents('Invoice')),3)
    def test_failure_aborts_transaction(self):
        s,ids=self.populated();s.begin_transaction();s._connection.execute('UPDATE source_document_section SET payload=? WHERE record_identity=?',('[[]]',str(ids[0])))
        with self.assertRaises(ValueError):s.read_documents('Invoice')
        self.assertFalse(s.transaction_active);self.assertEqual(len(s.read_documents('Invoice')),3)
    def test_row_bound(self):
        s,ids=self.populated()
        with patch('yadinassi.source_document_section_store._MAX_ROWS',0):
            with self.assertRaises(ValueError):s.read_documents('Invoice')
    def test_byte_bound(self):
        s,ids=self.populated()
        with patch('yadinassi.source_document_section_store._MAX_DOCUMENT_BYTES',1):
            with self.assertRaisesRegex(ValueError,'byte bound'):s.read_documents('Invoice')
    def test_no_section_schema(self):
        s=self.store(fixture.package(children=''));s.write_document('Invoice',uuid4(),0,self.values());self.assertEqual(len(s.read_documents('Invoice')),1)
