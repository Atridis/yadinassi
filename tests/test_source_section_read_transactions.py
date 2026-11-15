"""Section reads reserve a snapshot, not SQLite's sole writer slot."""
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_source_document_sections as fixture

class SectionReadTransactionTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store
    def populated(self):
        s=self.store();rid=uuid4()
        s.write_document_bundle('Invoice',rid,0,self.values(),{'lines':({'flag':True},)})
        return s,rid
    def read(self,s,rid,bundle):
        return s.read_document_bundle('Invoice',rid) if bundle else s.read_documents('Invoice')
    def test_read_does_not_reserve_writer_slot(self):
        for bundle in (False,True):
            s,rid=self.populated();other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            self.addCleanup(other.close)
            name='_sections' if bundle else '_validate_selection_sections';original=getattr(s,name)
            observed=[]
            def probe(*args,**kwargs):
                self.assertTrue(s.transaction_active)
                other.execute('BEGIN IMMEDIATE');observed.append(True)
                other.execute('ROLLBACK')
                return original(*args,**kwargs)
            with patch.object(s,name,side_effect=probe):self.read(s,rid,bundle)
            self.assertEqual(observed,[True]);self.assertFalse(s.transaction_active)
            other.close();s.close();self.path.unlink()
    def test_read_works_while_other_writer_reserved(self):
        for bundle in (False,True):
            s,rid=self.populated();other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            self.addCleanup(other.close);other.execute('BEGIN IMMEDIATE')
            other.execute("UPDATE source_document_section SET payload='[]'")
            try:
                result=self.read(s,rid,bundle)
                if bundle:self.assertEqual(result[3],{'lines':({'flag':True},)})
            finally:other.execute('ROLLBACK')
            self.assertFalse(s.transaction_active)
            other.close();s.close();self.path.unlink()
    def test_owned_read_begin_and_rollback(self):
        for bundle in (False,True):
            s,rid=self.populated();queries=[];s._connection.set_trace_callback(queries.append)
            self.read(s,rid,bundle)
            self.assertEqual([q for q in queries if q.startswith('BEGIN')],['BEGIN'])
            self.assertEqual(queries.count('ROLLBACK'),1)
            s.close();self.path.unlink()
    def test_outer_write_transaction_preserved(self):
        for bundle in (False,True):
            s,rid=self.populated();s.begin_transaction()
            s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':()})
            self.read(s,rid,bundle);self.assertTrue(s.transaction_active)
            s.rollback_transaction()
            self.assertEqual(s.read_document_bundle('Invoice',rid)[3],{'lines':({'flag':True},)})
            s.close();self.path.unlink()
    def test_corruption_aborts_owned_and_outer(self):
        for bundle in (False,True):
            for outer in (False,True):
                s,rid=self.populated()
                if outer:s.begin_transaction()
                s._connection.execute('UPDATE source_document_section SET payload=?',('[[]]',))
                with self.assertRaises(ValueError):self.read(s,rid,bundle)
                self.assertFalse(s.transaction_active)
                s.close();self.path.unlink()

    def test_lifecycle_restart_guards(self):
        from yadinassi import source_catalog_runtime as catalog, source_document_runtime as document
        for context in (catalog._active_write,catalog._constructing,document._active_write,document._constructing):
            for bundle in (False,True):
                s,rid=self.populated();token=context.set(True)
                try:
                    with self.assertRaisesRegex(ValueError,'lifecycle transaction aborted; cannot restart'):
                        self.read(s,rid,bundle)
                    self.assertFalse(s.transaction_active)
                finally:context.reset(token)
                s.close();self.path.unlink()
    def test_lifecycle_existing_transaction_allowed(self):
        from yadinassi import source_catalog_runtime as catalog, source_document_runtime as document
        for context in (catalog._active_write,catalog._constructing,document._active_write,document._constructing):
            for bundle in (False,True):
                s,rid=self.populated();s.begin_transaction();token=context.set(True)
                try:
                    self.read(s,rid,bundle);self.assertTrue(s.transaction_active)
                finally:context.reset(token)
                s.rollback_transaction();s.close();self.path.unlink()
