"""Whole-store section validation batches by family without dropping corruption."""
import unittest
import sqlite3
from unittest.mock import patch
from uuid import uuid4
import test_source_section_batch_read as fixture
import test_source_document_sections as sections
from yadinassi.source_document_section_store import SourceDocumentSectionStore

class SourceSectionOpenBatchTests(unittest.TestCase):
    setUp=fixture.SourceSectionBatchReadTests.setUp
    values=fixture.SourceSectionBatchReadTests.values
    store=fixture.SourceSectionBatchReadTests.store
    populated=fixture.SourceSectionBatchReadTests.populated
    def test_batch_whole_store_trace(self):
        s,ids=self.populated(32);q=[];s._connection.set_trace_callback(q.append)
        try:s.validate_records()
        finally:s._connection.set_trace_callback(None)
        payload=[sql for sql in q if sql.startswith('SELECT record_identity,section_identity,payload FROM source_document_section')]
        self.assertEqual(len(payload),1)
        self.assertFalse(any(sql.startswith('SELECT section_identity,payload') for sql in q))
        self.assertTrue(any(sql=='PRAGMA foreign_key_check' for sql in q))
    def test_reopen_no_per_record_path(self):
        s,_=self.populated();s.close()
        with patch.object(SourceDocumentSectionStore,'_sections',side_effect=AssertionError('N+1')):
            reopened=SourceDocumentSectionStore.reopen(self.path,sections.package());self.addCleanup(reopened.close)
            self.assertEqual(len(reopened.read_documents('Invoice')),3)
    def test_missing_section_on_reopen(self):
        s,ids=self.populated();s._connection.execute('DELETE FROM source_document_section WHERE record_identity=?',(str(ids[1]),));s.close()
        with self.assertRaises(ValueError):SourceDocumentSectionStore.reopen(self.path,sections.package())
    def test_unknown_section_on_reopen(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET section_identity=? WHERE record_identity=?',(str(uuid4()),str(ids[0])));s.close()
        with self.assertRaises(ValueError):SourceDocumentSectionStore.reopen(self.path,sections.package())
    def test_corrupt_later_payload(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET payload=? WHERE record_identity=?',('[[]]',str(max(ids,key=str))));s.close()
        with self.assertRaises(ValueError):SourceDocumentSectionStore.reopen(self.path,sections.package())
    def test_orphan_record_fk(self):
        s,ids=self.populated();s._connection.execute('PRAGMA foreign_keys=OFF');s._connection.execute('DELETE FROM source_document_record');s.close()
        with self.assertRaises(ValueError):SourceDocumentSectionStore.reopen(self.path,sections.package())
    def test_empty_store(self):
        s=self.store();s.validate_records();s.close();r=SourceDocumentSectionStore.reopen(self.path,sections.package());self.addCleanup(r.close)
    def test_no_sections(self):
        src=sections.package(children='');s=self.store(src);s.write_document('Invoice',uuid4(),0,self.values());s.close()
        r=SourceDocumentSectionStore.reopen(self.path,src);self.addCleanup(r.close);self.assertEqual(len(r.read_documents('Invoice')),1)
    def test_full_validation_inside_transaction(self):
        s,ids=self.populated();s.begin_transaction();s.write_document_bundle('Invoice',uuid4(),0,self.values('Z'),{'lines':()});s.validate_records();self.assertTrue(s.transaction_active);s.rollback_transaction();self.assertEqual(len(s.read_documents('Invoice')),3)
    def test_record_bound_not_just_query_limit(self):
        s,_=self.populated()
        with patch('yadinassi.source_catalog_store._MAX_RECORDS',2):
            with self.assertRaises(ValueError):s.validate_records()
    def test_two_families(self):
        from yadinassi.configuration_source import import_source
        files={f.path:f.content for f in sections.package().files}
        files['Documents/Receipt.xml']=files['Documents/Invoice.xml'].replace(b'Invoice',b'Receipt').replace(b'000000000003',b'000000000004').replace(b'000000000099',b'000000000098')
        src=import_source(files);s=self.store(src)
        for name in ('Invoice','Receipt'):s.write_document_bundle(name,uuid4(),0,self.values(),{'lines':({'flag':True},)})
        q=[];s._connection.set_trace_callback(q.append)
        try:s.validate_records()
        finally:s._connection.set_trace_callback(None)
        self.assertEqual(len([x for x in q if x.startswith('SELECT record_identity,section_identity,payload FROM source_document_section')]),2)
        s.close();r=SourceDocumentSectionStore.reopen(self.path,src);self.addCleanup(r.close)
        self.assertEqual(len(r.read_documents('Invoice')),1);self.assertEqual(len(r.read_documents('Receipt')),1)
