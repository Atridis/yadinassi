"""Independent v6 integration and preservation of existing v5 files."""
import contextlib
import io
import unittest
import test_source_document_records as fixture
from yadinassi.configuration_source import save_source_archive
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_store import SourceDocumentStore
from yadinassi.cli import main

class SourceDocumentSectionIntegrationTests(unittest.TestCase):
    setUp=fixture.SourceDocumentRecordTests.setUp

    def test_cli_create_reopen_without_xml(self):
        archive=self.path.with_suffix('.zip');save_source_archive(archive,fixture.package())
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--configuration-source',str(archive),'--source-scratch-db',str(self.path),'--source-document-sections','--run-startup']),0)
            self.assertEqual(main(['--open-source-scratch-db',str(self.path),'--source-document-sections','--run-startup']),0)

    def test_cli_wrong_profile_preserves_v5_bytes(self):
        store=SourceDocumentStore.create(self.path,fixture.package());store.close();before=self.path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--open-source-scratch-db',str(self.path),'--source-document-sections','--run-startup']),1)
        self.assertEqual(before,self.path.read_bytes())

    def test_cli_profile_requires_source(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(['--source-document-sections'])

    def test_flag_exact_boolean(self):
        with self.assertRaises(TypeError):SourceApplication(fixture.package(),source_document_sections=1)

    def test_v6_catalog_and_document_queries(self):
        body='C=Catalogs.Items.CreateItem(); C.Code="A"; C.Write(); D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); D.Write(); Q=New Query("SELECT D.Ref AS R FROM Document.Invoice AS D INNER JOIN Catalog.Items AS C ON D.Number=C.Code"); T=Q.Execute().Unload(); Q.Text="SELECT R FROM &Input"; Q.SetParameter("Input",T); Message(Q.Execute().Unload().Count());'
        out=[];app=SourceApplication(fixture.package(body),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['1'])

    def test_v5_remains_closed_profile(self):
        from yadinassi.source_document_section_store import SourceDocumentSectionStore
        store=SourceDocumentSectionStore.create(self.path,fixture.package());store.close();before=self.path.read_bytes()
        with self.assertRaises((ValueError,TypeError)):SourceDocumentStore.reopen(self.path,fixture.package())
        self.assertEqual(before,self.path.read_bytes())

    def test_bundle_failure_after_scalar_write_rolls_back_all(self):
        from unittest.mock import patch
        from uuid import uuid4
        from yadinassi.source_document_section_store import SourceDocumentSectionStore
        import test_source_document_sections as sections
        source=sections.package();store=SourceDocumentSectionStore.create(self.path,source);self.addCleanup(store.close)
        rid=uuid4();values=fixture.SourceDocumentRecordTests.values(self)
        store.write_document_bundle('Invoice',rid,0,values,{'lines':({'flag':True},)})
        values=dict(values,number='B')
        with patch.object(store,'_sections',side_effect=ValueError('injected final validation')):
            with self.assertRaisesRegex(ValueError,'injected'):
                store.write_document_bundle('Invoice',rid,1,values,{'lines':({'flag':False},)})
        _,revision,saved,rows=store.read_document_bundle('Invoice',rid)
        self.assertEqual((revision,saved['number'],rows['lines'][0]['flag']),(1,'A',True))
        self.assertFalse(store.transaction_active)

    def test_foreign_row_cannot_be_deleted(self):
        import test_source_document_sections as sections
        out=[];body=sections.CREATE+'A=D.Lines.Add(); A.Flag=True; O=Documents.Invoice.CreateDocument(); Try O.Lines.Delete(A); Except Message("foreign"); EndTry; Message(D.Lines.Count());'
        app=SourceApplication(sections.package(body),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['foreign','1'])

    def test_upgrade_preserves_existing_scalar_document(self):
        from uuid import uuid4
        from yadinassi.source_document_section_store import SourceDocumentSectionStore
        old=self.path.with_name('old.sqlite');source=fixture.package();s=SourceDocumentStore.create(old,source);rid=uuid4()
        s.write_document('Invoice',rid,0,fixture.SourceDocumentRecordTests.values(self));s.close();before=old.read_bytes()
        SourceDocumentSectionStore.upgrade_copy(old,self.path)
        s=SourceDocumentSectionStore.reopen(self.path,source);self.addCleanup(s.close)
        self.assertEqual(s.read_documents('Invoice',rid)[0][2]['number'],'A');self.assertEqual(old.read_bytes(),before)

    def test_upgrade_existing_destination_never_overwrites(self):
        from yadinassi.source_document_section_store import SourceDocumentSectionStore
        old=self.path.with_name('old.sqlite');s=SourceDocumentStore.create(old,fixture.package());s.close()
        self.path.write_bytes(b'keep-me');before=old.read_bytes()
        with self.assertRaises(FileExistsError):SourceDocumentSectionStore.upgrade_copy(old,self.path)
        self.assertEqual(self.path.read_bytes(),b'keep-me');self.assertEqual(old.read_bytes(),before)

    def test_section_catalog_reference_keeps_identity_after_reopen(self):
        import test_source_document_sections as sections
        import test_source_catalog_definitions as catalog
        from yadinassi.configuration_source import import_source
        children=sections.SECTION.replace(catalog.attribute('Flag'),catalog.attribute('Item','<v8:Type>cfg:CatalogRef.Items</v8:Type>'))
        source=sections.package(children=children);files={f.path:f.content for f in source.files}
        files['Documents/Invoice.xml']=files['Documents/Invoice.xml'].replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')
        body='C=Catalogs.Items.CreateItem(); C.Code="C"; C.Write(); '+sections.CREATE+'R=D.Lines.Add(); R.Item=C.Ref; D.Write(); O=D.Ref.GetObject(); Message(O.Lines.Get(0).Item=C.Ref);'
        files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
        source=import_source(files);out=[];app=SourceApplication(source,scratch_database=self.path,source_document_sections=True,output=out.append);app.start();app.close();self.assertEqual(out,['Да'])
        app=SourceApplication(source,existing_scratch_database=self.path,source_document_sections=True);self.addCleanup(app.close)
        rows=app.constant_store.read_documents('Invoice');ref=app.constant_store.read_document_bundle('Invoice',rows[0][0])[3]['lines'][0]['item']
        self.assertIs(ref.value_type,app.references.definition('Catalog','Items')[1]);self.assertIs(ref.value_type.snapshot,app.references.snapshot)
