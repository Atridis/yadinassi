"""Single aggregate preflight preserves malformed and aggregate bounds."""
import unittest
from uuid import uuid4
import test_source_document_sections as fixture

class SourceSectionPreflightTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store

    def populated(self):
        s=self.store();rid=uuid4()
        s.write_document_bundle('Invoice',rid,0,self.values(),{'lines':()})
        return s,rid

    def check(self,s):
        queries=[];s._connection.set_trace_callback(queries.append)
        try:s.verify_extra()
        finally:s._connection.set_trace_callback(None)
        return [q for q in queries if q.startswith('SELECT ') and 'FROM source_document_section' in q]

    def test_empty_one_scan(self):
        self.assertEqual(len(self.check(self.store())),1)

    def test_populated_one_scan(self):
        s,_=self.populated();self.assertEqual(len(self.check(s)),1)

    def test_each_identity_short(self):
        for column in ('document_identity','record_identity','section_identity'):
            with self.subTest(column=column):
                s,_=self.populated()
                s._connection.execute('PRAGMA foreign_keys=OFF')
                s._connection.execute('UPDATE source_document_section SET '+column+'=?',('short',))
                with self.assertRaisesRegex(ValueError,'section storage bounds'):s.verify_extra()
                s.close();self.path.unlink()

    def test_each_identity_blob(self):
        for column in ('document_identity','record_identity','section_identity'):
            with self.subTest(column=column):
                s,_=self.populated()
                s._connection.execute('PRAGMA foreign_keys=OFF')
                s._connection.execute('UPDATE source_document_section SET '+column+'=?',(b'x'*36,))
                with self.assertRaisesRegex(ValueError,'section storage bounds'):s.verify_extra()
                s.close();self.path.unlink()

    def test_identity_byte_length_not_characters(self):
        s,_=self.populated()
        s._connection.execute('UPDATE source_document_section SET section_identity=?',('é'*36,))
        with self.assertRaisesRegex(ValueError,'section storage bounds'):s.verify_extra()

    def test_blob_payload(self):
        s,_=self.populated();s._connection.execute('UPDATE source_document_section SET payload=?',(b'[]',))
        with self.assertRaisesRegex(ValueError,'section storage bounds'):s.verify_extra()

    def test_payload_byte_boundary(self):
        s,_=self.populated();s._connection.execute('UPDATE source_document_section SET payload=?',('é'*131072,))
        self.check(s)
        s._connection.execute('UPDATE source_document_section SET payload=?',('é'*131072+'x',))
        with self.assertRaisesRegex(ValueError,'section storage bounds'):s.verify_extra()

    def test_aggregate_byte_boundary(self):
        s,rid=self.populated();did=str(s.document('Invoice').identity)
        s._connection.execute('DELETE FROM source_document_section')
        rows=[(did,str(rid),str(uuid4()),'x'*262144) for _ in range(64)]
        s._connection.executemany('INSERT INTO source_document_section VALUES(?,?,?,?)',rows)
        self.check(s)
        s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',(did,str(rid),str(uuid4()),'x'))
        with self.assertRaisesRegex(ValueError,'section aggregate storage bound'):s.verify_extra()

    def test_count_limit_and_error_precedence(self):
        # Fake only this query's row, leaving superclass schema verification
        # real. This checks both boundary and priority without 160k fixture rows.
        from unittest.mock import Mock
        from yadinassi.source_document_store import SourceDocumentStore
        from unittest.mock import patch
        s=self.store();original=s._connection
        try:
            s._connection=Mock()
            with patch.object(SourceDocumentStore,'verify_extra'):
                for result,expected in (((0,160000,0),None),((0,160001,0),'aggregate'),((1,160001,16777217),'section storage bounds')):
                    s._connection.execute.return_value.fetchone.return_value=result
                    if expected:
                        with self.assertRaisesRegex(ValueError,expected):s.verify_extra()
                    else:s.verify_extra()
        finally:s._connection=original
