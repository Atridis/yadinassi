"""Independent transaction and source ownership regression checks."""
from pathlib import Path
import tempfile
import unittest
from test_source_catalog_records import package
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

class SourceCatalogModuleGuardTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'guard.sqlite'

    def app(self,body,module):
        files={f.path:f.content for f in configuration().files}
        files.update({f.path:f.content for f in package().files if f.path!='Configuration.xml'})
        files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
        files['Catalogs/Items/Ext/ObjectModule.bsl']=module.encode()
        out=[]
        app=SourceApplication(import_source(files),scratch_database=self.path,source_catalog_records=True,output=out.append)
        self.addCleanup(app.close)
        return app,out

    def test_after_failure_restores_constant_and_record(self):
        app,out=self.app('Constants.Flag.Set(False); O=Catalogs.Items.CreateItem(); O.Code="A"; Try O.Write(); Except Message("failed"); EndTry; Message(Constants.Flag.Get()); Message(O.IsNew());',
            'Procedure OnWrite(Cancel) Constants.Flag.Set(True); Raise "abort"; EndProcedure')
        app.start();self.assertEqual(out,['failed','Нет','Да'])
        self.assertEqual(app.constant_store.read_records('Items'),[])

    def test_caught_handler_storage_error_cannot_restart_write(self):
        app,out=self.app('O=Catalogs.Items.CreateItem(); O.Code="A"; Try O.Write(); Except Message("failed"); EndTry;',
            'Procedure BeforeWrite(Cancel) Try Constants.Flag.Set("wrong"); Except EndTry; Description="after"; EndProcedure')
        app.start();self.assertEqual(out,['failed']);self.assertEqual(app.constant_store.read_records('Items'),[])

    def test_explicit_transaction_failure_rolls_prior_write(self):
        app,out=self.app('Constants.Flag.Set(False); BeginTransaction(); Constants.Flag.Set(True); O=Catalogs.Items.CreateItem(); O.Code="A"; Try O.Write(); Except Message("failed"); EndTry; Message(TransactionActive()); Message(Constants.Flag.Get());',
            'Procedure OnWrite(Cancel) Cancel=True; EndProcedure')
        app.start();self.assertEqual(out,['failed','Нет','Нет']);self.assertEqual(app.constant_store.read_records('Items'),[])

    def test_safe_mode_blocks_handler_external_write(self):
        app,out=self.app('O=Catalogs.Items.CreateItem(); O.Code="A"; Try O.Write(); Except Message("failed"); EndTry;',
            'Procedure OnWrite(Cancel) SetSafeMode(True); Constants.Flag.Set(True); EndProcedure')
        app.start();self.assertEqual(out,['failed']);self.assertEqual(app.constant_store.read_records('Items'),[])

    def test_initializer_unsupported_signature_has_no_side_effect(self):
        app,out=self.app('Constants.Flag.Set(False); Try O=Catalogs.Items.CreateItem(); Except Message("unsupported"); EndTry; Message(Constants.Flag.Get());',
            'Procedure OnWrite(Val Cancel) EndProcedure Constants.Flag.Set(True);')
        app.start();self.assertEqual(out,['unsupported','Нет'])

    def test_moduleless_schema_record_keeps_three_items(self):
        from yadinassi.source_catalog_definitions import source_catalog_definitions, catalog_definition_record
        definitions,errors=source_catalog_definitions(package())
        self.assertEqual(errors,{})
        self.assertEqual(len(catalog_definition_record(definitions['items'])),3)

    def test_add_module_update_refuses_without_touching_original(self):
        from yadinassi.source_catalog_store import SourceCatalogStore
        source=package();store=SourceCatalogStore.create(self.path,source)
        store.close();before=self.path.read_bytes()
        files={f.path:f.content for f in source.files}
        files['Catalogs/Items/Ext/ObjectModule.bsl']=b'Procedure BeforeWrite(Cancel) EndProcedure'
        changed=import_source(files)
        with self.assertRaises(ValueError):SourceCatalogStore.update_source(self.path,changed)
        self.assertEqual(self.path.read_bytes(),before)
