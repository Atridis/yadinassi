"""Independent source identity and old-schema refusal guards."""
import unittest
from unittest.mock import patch
from uuid import uuid4
from dataclasses import replace
import test_source_document_relations as fixture
import test_source_document_records as records
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_store import SourceDocumentStore
from yadinassi.source_document_section_store import SourceDocumentSectionStore

class SourceDocumentRelationGuardTests(unittest.TestCase):
    setUp=records.SourceDocumentRecordTests.setUp
    def test_foreign_and_callback_document_ref_refused_before_write(self):
        source=fixture.package();app=SourceApplication(source,scratch_database=self.path,source_document_sections=True);self.addCleanup(app.close)
        other=SourceApplication(source);self.addCleanup(other.close)
        own=app.references.ref('Document','Invoice',uuid4());foreign=other.references.ref('Document','Invoice',own.reference_uuid)
        for ref in (foreign,replace(own,read_member=lambda *a:'fake'),
                    replace(own,get_object=lambda *a:'fake'),replace(own,metadata=object()),
                    replace(own,value_type=replace(own.value_type)),
                    app.references.ref('Catalog','Items',uuid4())):
            values=dict(records.SourceDocumentRecordTests.values(self),link=ref)
            with self.assertRaises((TypeError,ValueError)):app.constant_store.write_document('Invoice',uuid4(),0,values)
        self.assertEqual(app.constant_store.read_documents('Invoice'),[])

    def test_changed_reference_type_update_preserves_bytes(self):
        source=fixture.package();s=SourceDocumentSectionStore.create(self.path,source);s.close();before=self.path.read_bytes()
        files={f.path:f.content for f in source.files};files['Documents/Invoice.xml']=files['Documents/Invoice.xml'].replace(b'cfg:DocumentRef.Invoice',b'cfg:CatalogRef.Items')
        with self.assertRaises(ValueError):SourceDocumentSectionStore.update_source(self.path,import_source(files))
        self.assertEqual(self.path.read_bytes(),before)

    def test_old_unsupported_schema_refuses_without_mutation(self):
        from yadinassi import source_document_definitions as definitions
        source=fixture.package();original=definitions.source_document_definitions
        def old_parser(*args,**kwargs):
            supported,errors=original(*args,**kwargs)
            supported.pop('invoice',None);errors['invoice']='document attribute requires scalar or CatalogRef type'
            return supported,errors
        with patch.object(definitions,'source_document_definitions',old_parser):
            store=SourceDocumentStore.create(self.path,source);store.close()
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceDocumentStore.reopen(self.path,source)
        self.assertEqual(self.path.read_bytes(),before)
