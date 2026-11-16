"""Record selections decode incrementally rather than retaining raw payload lists."""
import unittest
from uuid import uuid4
from unittest.mock import patch
import test_source_document_records as fixture

class IteratorOnlyCursor:
    def __init__(self,cursor,after=None):self.cursor=iter(cursor);self.after=after;self.count=0
    def __iter__(self):return self
    def __next__(self):
        row=next(self.cursor);self.count+=1
        if self.after:self.after(self.count)
        return row
    def fetchall(self):raise AssertionError('raw records must stream')
    def close(self):self.cursor.close()
class StreamingConnection:
    def __init__(self,connection,kind,after=None):self.connection=connection;self.kind=kind;self.after=after;self.selections=[]
    def __getattr__(self,name):return getattr(self.connection,name)
    def execute(self,sql,*args):
        cursor=self.connection.execute(sql,*args)
        if sql.startswith('SELECT record_identity,revision,payload,') and 'FROM source_'+self.kind+'_record' in sql:
            cursor=IteratorOnlyCursor(cursor,self.after);self.selections.append(cursor)
        return cursor

class SourceRecordStreamTests(unittest.TestCase):
    setUp=fixture.SourceDocumentRecordTests.setUp
    store=fixture.SourceDocumentRecordTests.store
    values=fixture.SourceDocumentRecordTests.values
    def populated(self,kind):
        s=self.store();ids=[uuid4() for _ in range(3)]
        for n,rid in enumerate(ids):
            if kind=='catalog':s.write_record('Items',rid,0,dict(code=str(n),description='One',deletionmark=False))
            else:s.write_document('Invoice',rid,0,self.values(str(n)))
        return s,ids
    def read(self,s,kind,rid=None):return s.read_records('Items',rid) if kind=='catalog' else s.read_documents('Invoice',rid)
    def test_selection_and_point_do_not_fetchall(self):
        for kind in ('catalog','document'):
            s,ids=self.populated(kind);wrapper=StreamingConnection(s._connection,kind);s._connection=wrapper
            self.assertEqual([r[0] for r in self.read(s,kind)],sorted(ids,key=str))
            self.assertEqual(self.read(s,kind,ids[1])[0][0],ids[1])
            self.assertEqual([c.count for c in wrapper.selections],[3,1])
            s.close();self.path.unlink()
    def test_decode_interleaves_fetch(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind);events=[];module=__import__('yadinassi.source_'+kind+'_store',fromlist=['decode_record']);real=module.decode_record
            s._connection=StreamingConnection(s._connection,kind,lambda n:events.append('fetch'))
            def decode(*args):events.append('decode');return real(*args)
            with patch.object(module,'decode_record',side_effect=decode):self.read(s,kind)
            self.assertEqual(events,['fetch','decode']*3)
            s.close();self.path.unlink()
    def test_late_corruption_aborts_outer(self):
        for kind in ('catalog','document'):
            s,ids=self.populated(kind);s.begin_transaction()
            s._connection.execute('UPDATE source_'+kind+'_record SET payload=? WHERE record_identity=?',('[]',str(max(ids,key=str))))
            with self.assertRaises(ValueError):self.read(s,kind)
            self.assertFalse(s.transaction_active);self.assertEqual(len(self.read(s,kind)),3)
            s.close();self.path.unlink()
    def test_iterator_failure_aborts(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind);s.begin_transaction()
            def fail(n):
                if n==3:raise ValueError('late cursor failure')
            original=s._connection;s._connection=StreamingConnection(original,kind,fail)
            with self.assertRaisesRegex(ValueError,'late cursor failure'):self.read(s,kind)
            self.assertFalse(s.transaction_active);s._connection=original
            self.assertEqual(len(self.read(s,kind)),3);s.close();self.path.unlink()
    def test_per_query_bound_even_without_preflight(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind)
            with patch.object(s,'_open'),patch('yadinassi.source_'+kind+'_store._MAX_RECORDS',2):
                with self.assertRaisesRegex(ValueError,'record bound'):self.read(s,kind)
            self.assertFalse(s.transaction_active);s.close();self.path.unlink()
    def test_point_missing(self):
        for kind in ('catalog','document'):
            s,_=self.populated(kind)
            with self.assertRaisesRegex(ValueError,'record not found'):self.read(s,kind,uuid4())
            self.assertFalse(s.transaction_active);s.close();self.path.unlink()

    def test_early_decode_error_releases_cursor_with_retained_traceback(self):
        import sqlite3
        for kind in ('catalog','document'):
            s,ids=self.populated(kind)
            s._connection.execute('UPDATE source_'+kind+'_record SET payload=? WHERE record_identity=?',('[]',str(min(ids,key=str))))
            retained=None
            try:self.read(s,kind)
            except ValueError as error:retained=error
            self.assertIsNotNone(retained);self.assertIsNotNone(retained.__traceback__)
            self.assertFalse(s.transaction_active)
            other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            try:
                other.execute('BEGIN IMMEDIATE')
                other.execute('UPDATE source_'+kind+'_record SET revision=revision')
                other.execute('COMMIT')
            finally:other.close()
            s.close();self.path.unlink()


import test_source_document_sections as sections
class SectionCursorRetirementTests(unittest.TestCase):
    setUp=sections.SourceDocumentSectionTests.setUp
    values=sections.SourceDocumentSectionTests.values
    store=sections.SourceDocumentSectionTests.store
    def test_section_errors_release_statement(self):
        import sqlite3
        for global_scan in (False,True):
            s=self.store();ids=[uuid4() for _ in range(3)]
            for n,rid in enumerate(ids):
                s.write_document_bundle('Invoice',rid,0,self.values(str(n)),{'lines':({'flag':True},)})
            s._connection.execute('UPDATE source_document_section SET payload=? WHERE record_identity=?',('[[]]',str(min(ids,key=str))))
            retained=None
            try:
                if global_scan:s.validate_records()
                else:s.read_documents('Invoice')
            except ValueError as error:retained=error
            self.assertIsNotNone(retained);self.assertIsNotNone(retained.__traceback__)
            other=sqlite3.connect(self.path,isolation_level=None,timeout=0)
            try:
                other.execute('BEGIN IMMEDIATE');other.execute('UPDATE source_document_section SET payload=payload');other.execute('COMMIT')
            finally:other.close()
            s.close();self.path.unlink()
