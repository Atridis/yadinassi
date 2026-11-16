"""Only changed section payload rows are persisted; full aggregate guards remain."""
import unittest
from uuid import uuid4
from unittest.mock import patch
import test_source_document_sections as fixture

class DifferentialSectionWriteTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    values=fixture.SourceDocumentSectionTests.values
    store=fixture.SourceDocumentSectionTests.store
    def populated(self):
        s=self.store();rid=uuid4();data={'lines':({'flag':True},)}
        s.write_document_bundle('Invoice',rid,0,self.values(),data)
        return s,rid,data
    def test_same_payload_only_header_changes(self):
        s,rid,data=self.populated();before=s._connection.total_changes
        self.assertEqual(s.write_document_bundle('Invoice',rid,1,self.values(),data),2)
        self.assertEqual(s._connection.total_changes-before,1)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
    def test_changed_payload_one_update_not_delete_insert(self):
        s,rid,_=self.populated();before=s._connection.total_changes;data={'lines':({'flag':False},)}
        s.write_document_bundle('Invoice',rid,1,self.values(),data)
        self.assertEqual(s._connection.total_changes-before,2)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
    def test_missing_payload_is_reinserted(self):
        s,rid,data=self.populated();s._connection.execute('DELETE FROM source_document_section');before=s._connection.total_changes
        s.write_document_bundle('Invoice',rid,1,self.values(),data)
        self.assertEqual(s._connection.total_changes-before,2)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
    def test_unknown_payload_is_removed_as_before(self):
        s,rid,data=self.populated();s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',(str(s.document('Invoice').identity),str(rid),str(uuid4()),'[]'))
        s.write_document_bundle('Invoice',rid,1,self.values(),data)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
    def test_noncanonical_payload_is_replaced(self):
        s,rid,data=self.populated();s._connection.execute("UPDATE source_document_section SET payload='[ [true] ]'")
        s.write_document_bundle('Invoice',rid,1,self.values(),data)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
    def test_stale_revision_keeps_sections(self):
        s,rid,data=self.populated()
        with self.assertRaisesRegex(ValueError,'stale'):
            s.write_document_bundle('Invoice',rid,9,self.values(),{'lines':()})
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
    def test_outer_rollback_restores_header_and_sections(self):
        s,rid,data=self.populated();s.begin_transaction()
        s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':()})
        self.assertTrue(s.transaction_active);s.rollback_transaction()
        result=s.read_document_bundle('Invoice',rid);self.assertEqual(result[1],1);self.assertEqual(result[3],data)
    def test_postvalidation_failure_rolls_back(self):
        s,rid,data=self.populated()
        with patch.object(s,'_sections',side_effect=ValueError('post-validation failure')):
            with self.assertRaisesRegex(ValueError,'post-validation failure'):
                s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':()})
        result=s.read_document_bundle('Invoice',rid);self.assertEqual(result[1],1);self.assertEqual(result[3],data)
    def test_empty_definition_still_clears_payloads(self):
        s=self.store(fixture.package(children=''));rid=uuid4()
        s.write_document_bundle('Invoice',rid,0,self.values(),{})
        s._connection.execute('INSERT INTO source_document_section VALUES(?,?,?,?)',(str(s.document('Invoice').identity),str(rid),str(uuid4()),'[]'))
        s.write_document_bundle('Invoice',rid,1,self.values(),{})
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],{})
    def test_two_sections_only_changed_one_written(self):
        from uuid import uuid5,NAMESPACE_URL
        extra=fixture.SECTION.replace('000000000099','000000000098').replace('Lines','Extra').replace(str(uuid5(NAMESPACE_URL,'Flag')),str(uuid5(NAMESPACE_URL,'ExtraFlag')))
        s=self.store(fixture.package(children=fixture.SECTION+extra));rid=uuid4()
        data={'lines':({'flag':True},),'extra':({'flag':False},)}
        s.write_document_bundle('Invoice',rid,0,self.values(),data)
        before=s._connection.total_changes;data['lines']=()
        s.write_document_bundle('Invoice',rid,1,self.values(),data)
        self.assertEqual(s._connection.total_changes-before,2)
        self.assertEqual(s.read_document_bundle('Invoice',rid)[3],data)
