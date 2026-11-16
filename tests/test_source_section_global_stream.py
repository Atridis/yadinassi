"""Whole-store section integrity is streamed across all document families."""
import unittest
from uuid import uuid4
import test_source_document_sections as fixture
from yadinassi.configuration_source import import_source

class SectionGlobalStreamTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store
    def populated(self,count=8):
        files={f.path:f.content for f in fixture.package().files}
        base=files.pop('Documents/Invoice.xml');ids={}
        for n in range(count):
            name='Document'+str(n)
            files['Documents/'+name+'.xml']=base.replace(b'Invoice',name.encode()).replace(b'000000000003',('%012d'%(100+n)).encode()).replace(b'000000000099',('%012d'%(200+n)).encode())
        source=import_source(files);s=self.store(source)
        for n in range(count):
            name='Document'+str(n);rid=uuid4();ids[name]=rid
            s.write_document_bundle(name,rid,0,self.values(),{'lines':({'flag':True},)})
        return s,ids
    def test_eight_families_one_query(self):
        s,_=self.populated();queries=[];s._connection.set_trace_callback(queries.append)
        try:s.validate_records()
        finally:s._connection.set_trace_callback(None)
        reads=[q for q in queries if 'FROM source_document_section' in q]
        self.assertEqual(len(reads),1);self.assertTrue(reads[0].endswith('LIMIT 160001'))
    def test_missing_middle_family(self):
        s,ids=self.populated();s._connection.execute('DELETE FROM source_document_section WHERE record_identity=?',(str(ids['Document4']),))
        with self.assertRaisesRegex(ValueError,'inventory'):s.validate_records()
    def test_later_family_corrupt(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET payload=? WHERE record_identity=?',('[[]]',str(ids['Document7'])))
        with self.assertRaises(ValueError):s.validate_records()
    def test_unknown_family(self):
        s,_=self.populated();s._connection.execute('PRAGMA foreign_keys=OFF')
        s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',(str(uuid4()),str(uuid4()),str(uuid4()),'[]'))
        with self.assertRaisesRegex(ValueError,'foreign record'):s.validate_records()
    def test_foreign_record_in_existing_family(self):
        s,_=self.populated();s._connection.execute('PRAGMA foreign_keys=OFF')
        s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',(str(s.document('Document4').identity),str(uuid4()),str(uuid4()),'[]'))
        with self.assertRaisesRegex(ValueError,'foreign record'):s.validate_records()
    def test_later_family_missing_section(self):
        s,ids=self.populated();s._connection.execute('UPDATE source_document_section SET section_identity=? WHERE record_identity=?',(str(uuid4()),str(ids['Document7'])))
        with self.assertRaisesRegex(ValueError,'inventory'):s.validate_records()
    def test_global_limit_not_reset_per_family(self):
        from unittest.mock import Mock,patch
        from collections import deque
        from yadinassi.source_document_store import SourceDocumentStore
        s,ids=self.populated(2);original=s._connection
        first=str(s.document('Document0').identity);second=str(s.document('Document1').identity)
        def row_stream(count):
            for i in range(count):
                yield (first if i<80000 else second,'rid','sid','[]')
        def consume(definition,identities,payloads):deque(payloads,maxlen=0)
        for count in (160000,160001):
            connection=Mock()
            def execute(sql,args=()):
                if 'FROM source_document_record' in sql:return iter([(first,'rid'),(second,'rid')])
                if 'FROM source_document_section' in sql:
                    result=Mock();result.__iter__=Mock(return_value=row_stream(count));return result
                result=Mock();result.fetchone.return_value=None;return result
            connection.execute.side_effect=execute;s._connection=connection
            try:
                with patch.object(SourceDocumentStore,'validate_records'),patch.object(s,'_validate_section_payloads',side_effect=consume):
                    if count==160000:s.validate_records()
                    else:
                        with self.assertRaisesRegex(ValueError,'aggregate storage bound'):s.validate_records()
            finally:s._connection=original
