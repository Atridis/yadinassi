import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4
from test_source_catalog_definitions import config, attribute, BASE
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.errors import BSLError


def package(body='', **kwargs):
    source=config(**kwargs);files={e.path:e.content for e in source.files}
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    return import_source(files)

class SourceCatalogRecordTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'v4.sqlite'
    def store(self,source=None):
        store=SourceCatalogStore.create(self.path,source or package());self.addCleanup(store.close);return store
    def values(self,code='A',**extra):return {'code':code,'description':'One','deletionmark':False,**extra}
    def run_app(self,body,**kwargs):
        output=[];app=SourceApplication(package(body,**kwargs),scratch_database=self.path,source_catalog_records=True,output=output.append);self.addCleanup(app.close);app.start();return app,output
    def test_create_read_select_reopen(self):
        source=package();store=self.store(source);identity=uuid4();self.assertEqual(store.write_record('Items',identity,0,self.values()),1)
        self.assertEqual(store.read_records('Items',identity)[0][2],self.values());store.close()
        reopened=SourceCatalogStore.reopen(self.path,source);self.addCleanup(reopened.close);self.assertEqual(len(reopened.read_records('Items')),1)
    def test_revision(self):
        store=self.store();identity=uuid4();store.write_record('Items',identity,0,self.values());store.write_record('Items',identity,1,self.values(description='New'))
        with self.assertRaisesRegex(ValueError,'stale'):store.write_record('Items',identity,1,self.values())
        self.assertEqual(store.read_records('Items',identity)[0][2]['description'],'New')
    def test_duplicate_code(self):
        store=self.store();store.write_record('Items',uuid4(),0,self.values())
        with self.assertRaises(ValueError):store.write_record('Items',uuid4(),0,self.values())
        self.assertEqual(len(store.read_records('Items')),1)
    def test_explicit_transaction_rollback(self):
        store=self.store();store.begin_transaction();store.write_record('Items',uuid4(),0,self.values());self.assertTrue(store.transaction_active);store.rollback_transaction();self.assertEqual(store.read_records('Items'),[])
    def test_failed_write_rolls_transaction(self):
        store=self.store();store.begin_transaction();store.write_record('Items',uuid4(),0,self.values())
        with self.assertRaises(ValueError):store.write_record('Items',uuid4(),0,self.values())
        self.assertFalse(store.transaction_active);self.assertEqual(store.read_records('Items'),[])
    def test_unassigned_attribute(self):
        store=self.store(package(children=attribute()))
        with self.assertRaises(ValueError):store.write_record('Items',uuid4(),0,self.values())
        self.assertEqual(store.read_records('Items'),[])
    def test_wrong_field_type(self):
        store=self.store()
        with self.assertRaises(TypeError):store.write_record('Items',uuid4(),0,self.values(deletionmark='false'))
    def test_object_module_refused(self):
        store=self.store(package(extra={'Catalogs/Items/Ext/ObjectModule.bsl':b'broken'}))
        with self.assertRaisesRegex(ValueError,'unsupported'):store.write_record('Items',uuid4(),0,self.values())
    def test_bsl_full_cycle(self):
        _,out=self.run_app('O=Catalogs.Items.CreateItem(); Message(O.IsNew()); O.Code="A"; O.Description="Hello"; O.Write(); Message(O.IsNew()); R=O.Ref; P=R.GetObject(); Message(P.Description); P.Description="Changed"; P.Write(); S=Catalogs.Items.Select(); While S.Next() Do Message(S.Description); EndDo;')
        self.assertEqual(out,['Да','Нет','Hello','Changed'])
    def test_bsl_attribute(self):
        _,out=self.run_app('O=Catalogs.Items.CreateItem(); O.Code="A"; O.Flag=True; O.Write(); Message(O.Ref.GetObject().Flag);',children=attribute())
        self.assertEqual(out,['Да'])
    def test_bsl_safe_mode(self):
        with self.assertRaises(BSLError):self.run_app('SetSafeMode(True); O=Catalogs.Items.CreateItem();')
    def test_bsl_rollback_stale_buffer(self):
        _,out=self.run_app('BeginTransaction(); O=Catalogs.Items.CreateItem(); O.Code="A"; O.Write(); RollbackTransaction(); Try O.Write(); Except Message("stale"); EndTry; S=Catalogs.Items.Select(); Message(S.Next());')
        self.assertEqual(out,['stale','Нет'])
    def test_v3_cannot_open_v4(self):
        source=package();store=self.store(source);store.close()
        with self.assertRaises(ValueError):SourceConstantStore.reopen(self.path,source)
    def test_upgrade_copy_preserves_original(self):
        old=self.path.with_name('old.sqlite');source=package();store=SourceConstantStore.create(old,source);store.close();before=old.read_bytes()
        SourceCatalogStore.upgrade_copy(old,self.path);self.assertEqual(old.read_bytes(),before)
        store=SourceCatalogStore.reopen(self.path,source);self.addCleanup(store.close);store.write_record('Items',uuid4(),0,self.values())
    def test_upgrade_never_overwrites(self):
        old=self.path.with_name('old.sqlite');store=SourceConstantStore.create(old,package());store.close();self.path.write_bytes(b'owner')
        with self.assertRaises(FileExistsError):SourceCatalogStore.upgrade_copy(old,self.path)
        self.assertEqual(self.path.read_bytes(),b'owner')
    def test_source_schema_change_refused(self):
        source=package();store=self.store(source);store.write_record('Items',uuid4(),0,self.values());store.close();before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceCatalogStore.update_source(self.path,package(props=BASE.replace('<CodeLength>9','<CodeLength>10')))
        self.assertEqual(self.path.read_bytes(),before)
    def test_tampered_record_rejected(self):
        source=package();store=self.store(source);store.write_record('Items',uuid4(),0,self.values());store.close()
        # A Connection context commits/rolls back, but does not close the handle.
        # Close it before reopen and TemporaryDirectory cleanup (Windows locks).
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute('UPDATE source_catalog_record SET record_identity=?',('x'*10000,))
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')
        with self.assertRaisesRegex(ValueError,'bounds'):SourceCatalogStore.reopen(self.path,source)
    def test_no_missing_record_fabrication(self):
        store=self.store()
        with self.assertRaisesRegex(ValueError,'not found'):store.read_records('Items',uuid4())
    def test_constants_and_catalog_share_rollback(self):
        from test_source_constant_store import configuration
        files={e.path:e.content for e in configuration().files};files.update({e.path:e.content for e in package().files if e.path!='Configuration.xml'})
        store=self.store(import_source(files));store.set('Flag',False);store.begin_transaction();store.set('Flag',True);store.write_record('Items',uuid4(),0,self.values());store.rollback_transaction()
        self.assertFalse(store.get('Flag'));self.assertEqual(store.read_records('Items'),[])
    def test_upgrade_preserves_constant_values(self):
        from test_source_constant_store import configuration
        old=self.path.with_name('v3.sqlite');source=configuration();store=SourceConstantStore.create(old,source);store.set('Flag',True);store.close();before=old.read_bytes()
        SourceCatalogStore.upgrade_copy(old,self.path);self.assertEqual(old.read_bytes(),before)
        store=SourceCatalogStore.reopen(self.path,source);self.addCleanup(store.close);self.assertTrue(store.get('Flag'))
    def test_bsl_property_byref(self):
        source=package();files={e.path:e.content for e in source.files};files['Ext/SessionModule.bsl']=b'Procedure Change(V) V="updated"; EndProcedure Procedure SessionParametersSetting(Names) O=Catalogs.Items.CreateItem(); O.Code="A"; Change(O.Description); O.Write(); Message(O.Ref.GetObject().Description); EndProcedure'
        out=[];app=SourceApplication(import_source(files),scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['updated'])
    def test_bsl_saved_manager_method(self):
        _,out=self.run_app('F=Catalogs.Items.CreateItem; O=F(); O.Code="A"; O.Write(); Message(O.IsNew());')
        self.assertEqual(out,['Нет'])
    def test_cli_open_v4_without_xml(self):
        import io
        from contextlib import redirect_stdout,redirect_stderr
        from yadinassi.cli import main
        source=package('S=Catalogs.Items.Select(); Message(S.Next());');store=self.store(source);store.write_record('Items',uuid4(),0,self.values());store.close()
        out=io.StringIO()
        with redirect_stdout(out),redirect_stderr(io.StringIO()):
            result=main(['--open-source-scratch-db',str(self.path),'--source-catalog-records','--run-startup'])
        self.assertEqual(result,0);self.assertIn('Да',out.getvalue())
    def test_aggregate_payload_budget_rolls_back(self):
        from unittest.mock import patch
        store=self.store()
        with patch('yadinassi.source_catalog_store._MAX_RECORD_BYTES',1):
            with self.assertRaisesRegex(ValueError,'bounds'):store.write_record('Items',uuid4(),0,self.values())
        self.assertEqual(store.read_records('Items'),[])
