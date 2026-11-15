"""Independent v5 integration, update reservation and original-file guards."""
import contextlib
import io
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_source_document_records as fixture
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source, save_source_archive
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_store import SourceDocumentStore
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.cli import main
from yadinassi.errors import BSLError

CREATE='D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); '

class SourceDocumentIntegrationTests(unittest.TestCase):
    setUp=fixture.SourceDocumentRecordTests.setUp
    run_app=fixture.SourceDocumentRecordTests.run_app
    values=fixture.SourceDocumentRecordTests.values

    def test_cli_create_reopen_without_xml(self):
        archive=self.path.with_suffix('.zip');save_source_archive(archive,fixture.package())
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--configuration-source',str(archive),'--source-scratch-db',str(self.path),'--source-document-records','--run-startup']),0)
            self.assertEqual(main(['--open-source-scratch-db',str(self.path),'--source-document-records','--run-startup']),0)

    def test_cli_wrong_profile_preserves_bytes(self):
        store=SourceCatalogStore.create(self.path,fixture.package());store.close();before=self.path.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--open-source-scratch-db',str(self.path),'--source-document-records','--run-startup']),1)
        self.assertEqual(before,self.path.read_bytes())

    def test_cli_profile_requires_source(self):
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main(['--source-document-records'])

    def test_v5_catalog_queries_keep_actual_data(self):
        _,out=self.run_app('O=Catalogs.Items.CreateItem(); O.Code="A"; O.Description="real"; O.Write(); Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items; SELECT R FROM Saved"); S=Q.Execute().Select(); S.Next(); Message(S.R.Description);')
        self.assertEqual(out,['real'])

    def test_document_virtual_query_not_faked(self):
        with self.assertRaises(BSLError):self.run_app(CREATE+'D.Write(); Q=New Query("SELECT Ref FROM Document.Invoice.Lines"); Q.Execute();')

    def test_document_ref_readonly_assignment(self):
        body=CREATE+'D.Write(); R=D.Ref; Try R.Number="changed"; Except Message("readonly"); EndTry; Message(R.Number);'
        _,out=self.run_app(body);self.assertEqual(out,['readonly','A'])

    def test_catalog_and_document_shared_rollback(self):
        app,out=self.run_app('BeginTransaction(); O=Catalogs.Items.CreateItem(); O.Code="A"; O.Write(); '+CREATE+'D.Write(); RollbackTransaction(); Message(Catalogs.Items.Select().Next()); Message(Documents.Invoice.Select().Next());')
        self.assertEqual(out,['Нет','Нет']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])

    def test_catalog_handler_poison_cannot_write_document(self):
        files={f.path:f.content for f in configuration().files}
        files.update({f.path:f.content for f in fixture.package().files if f.path!='Configuration.xml'})
        files['Catalogs/Items/Ext/ObjectModule.bsl']=('Procedure BeforeWrite(Cancel) Try Constants.Date.Get(); Except EndTry; Try '+CREATE+'D.Write(); Except EndTry; EndProcedure').encode()
        files['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting(Names) O=Catalogs.Items.CreateItem(); O.Code="A"; Try O.Write(); Except EndTry; EndProcedure'
        app=SourceApplication(import_source(files),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close);app.start()
        self.assertEqual(app.constant_store.read_documents('Invoice'),[]);self.assertEqual(app.constant_store.read_records('Items'),[])

    def test_hook_under_write_reservation(self):
        source=fixture.package();store=SourceDocumentStore.create(self.path,source);store.close();calls=[]
        original=SourceDocumentStore.validate_source_update
        def check(store,newsource):
            calls.append(store._connection.in_transaction)
            return original(store,newsource)
        with patch.object(SourceDocumentStore,'validate_source_update',check):SourceDocumentStore.update_source(self.path,source)
        self.assertEqual(calls,[True])

    def test_reserved_schema_check_rejects_document_difference(self):
        store=SourceDocumentStore.create(self.path,fixture.package());self.addCleanup(store.close)
        store.begin_transaction()
        with self.assertRaises(ValueError):store.validate_source_update(fixture.package(props=fixture.BASE.replace('NumberLength>9','NumberLength>8')))
        store.rollback_transaction()

    def test_copy_preserves_catalog_record(self):
        source=fixture.package();store=SourceCatalogStore.create(self.path,source);identity=uuid4()
        store.write_record('Items',identity,0,{'code':'A','description':'keep','deletionmark':False});store.close();before=self.path.read_bytes()
        destination=self.path.with_name('copy.sqlite');SourceDocumentStore.upgrade_copy(self.path,destination)
        self.assertEqual(self.path.read_bytes(),before)
        new=SourceDocumentStore.reopen(destination,source);self.addCleanup(new.close)
        self.assertEqual(new.read_records('Items')[0][2]['description'],'keep')
        self.assertEqual(new.read_documents('Invoice'),[])

    def test_copy_same_path_not_overwritten(self):
        store=SourceCatalogStore.create(self.path,fixture.package());store.close();before=self.path.read_bytes()
        with self.assertRaises(FileExistsError):SourceDocumentStore.upgrade_copy(self.path,self.path)
        self.assertEqual(before,self.path.read_bytes())

    def test_document_reference_byref_is_readonly(self):
        module='Procedure Change(Value) Value="changed"; EndProcedure Procedure SessionParametersSetting(Names) '+CREATE+'D.Write(); R=D.Ref; Try Change(R.Number); Except Message("readonly"); EndTry; Message(R.Number); EndProcedure'
        out=[];app=SourceApplication(fixture.package(extra={'Ext/SessionModule.bsl':module.encode()}),scratch_database=self.path,source_document_records=True,output=out.append)
        self.addCleanup(app.close);app.start();self.assertEqual(out,['readonly','A'])

    def test_reopen_rejects_tampered_posted_true(self):
        import sqlite3
        import json
        source=fixture.package();store=SourceDocumentStore.create(self.path,source)
        store.write_document('Invoice',uuid4(),0,self.values());store.close()
        with contextlib.closing(sqlite3.connect(self.path)) as connection:
            payload=json.loads(connection.execute('SELECT payload FROM source_document_record').fetchone()[0])
            payload[3][1]=['boolean',True]
            connection.execute('UPDATE source_document_record SET payload=?',(json.dumps(payload,separators=(',',':')),));connection.commit()
        before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'posting unsupported'):SourceDocumentStore.reopen(self.path,source)
        self.assertEqual(before,self.path.read_bytes())
