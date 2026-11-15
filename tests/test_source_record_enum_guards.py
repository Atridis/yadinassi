"""Independent update, query-boundary and aggregate rollback checks."""
import unittest
from unittest.mock import patch
import test_source_record_enums as fixture
import test_source_document_records as records
from test_source_enums import xml, value, identity
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.source_document_section_store import SourceDocumentSectionStore
from yadinassi.errors import BSLError

class SourceRecordEnumGuardTests(unittest.TestCase):
    setUp=records.SourceDocumentRecordTests.setUp
    def test_query_refuses_before_reading_records(self):
        for where,table in [('catalog','Catalog.Items'),('document','Document.Invoice'),('section','Document.Invoice.Lines')]:
            path=self.path.with_name(where+'.sqlite')
            source=fixture.package('Q=New Query("SELECT Ref FROM '+table+'"); Q.Execute();',where)
            app=SourceApplication(source,scratch_database=path,source_document_sections=True);self.addCleanup(app.close)
            with patch.object(app.constant_store,'read_records',side_effect=AssertionError('read')),patch.object(app.constant_store,'read_documents',side_effect=AssertionError('read')):
                with self.assertRaisesRegex(BSLError,'enumeration field unsupported'):app.start()
    def test_enum_identity_update_keeps_original_bytes(self):
        source=fixture.package(fixture.CAT+'C.Choice=Enums.State.Active; C.Write();')
        app=SourceApplication(source,scratch_database=self.path,source_catalog_records=True);app.start();app.close();before=self.path.read_bytes()
        for changed in (xml('Enum','State',value('Inactive')),xml('Enum','State',value('Active',uid=identity('replacement'))+value('Inactive'))):
            files={f.path:f.content for f in source.files};files['Enums/State.xml']=changed
            with self.assertRaises(ValueError):SourceCatalogStore.update_source(self.path,import_source(files))
            self.assertEqual(self.path.read_bytes(),before)
    def test_compatible_source_update_rebinds(self):
        source=fixture.package(fixture.CAT+'C.Choice=Enums.State.Active; C.Write();');app=SourceApplication(source,scratch_database=self.path,source_catalog_records=True);app.start();old=app.enumerations.get_member('State')._values[0];app.close()
        files={f.path:f.content for f in source.files};files['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting(Names) EndProcedure';updated=import_source(files)
        SourceCatalogStore.update_source(self.path,updated)
        other=SourceApplication(updated,existing_scratch_database=self.path,source_catalog_records=True);self.addCleanup(other.close)
        ref=other.constant_store.read_records('Items')[0][2]['choice'];self.assertIs(ref,other.enumerations.get_member('State')._values[0]);self.assertEqual(ref.reference_uuid,old.reference_uuid)
    def test_section_failed_commit_preserves_previous_enum_and_revision(self):
        source=fixture.package(fixture.DOC+'R=D.Lines.Add(); R.Choice=Enums.State.Active; D.Write();','section')
        app=SourceApplication(source,scratch_database=self.path,source_document_sections=True);self.addCleanup(app.close);app.start();store=app.constant_store
        rid,rev,fields,sections=store.read_document_bundle('Invoice',store.read_documents('Invoice')[0][0]);sections['lines'][0]['choice']=app.enumerations.get_member('State')._values[1]
        with patch.object(store,'_sections',side_effect=ValueError('injected final validation')):
            with self.assertRaises(ValueError):store.write_document_bundle('Invoice',rid,rev,fields,sections)
        current=store.read_document_bundle('Invoice',rid);self.assertEqual(current[1],rev);self.assertIs(current[3]['lines'][0]['choice'],app.enumerations.get_member('State')._values[0])
    def test_legacy_unsupported_schema_not_silently_migrated(self):
        from yadinassi import source_catalog_definitions as definitions
        source=fixture.package();original=definitions.source_catalog_definitions
        def old(*args,**kwargs):
            supported,errors=original(*args,**kwargs);supported.pop('items');errors['items']='enum unsupported';return supported,errors
        with patch.object(definitions,'source_catalog_definitions',old):store=SourceCatalogStore.create(self.path,source);store.close()
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceCatalogStore.reopen(self.path,source)
        self.assertEqual(self.path.read_bytes(),before)
