"""Real authored package and public BSL flows; native12 evidence is separate."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.accumulation_movements import validate_schema
from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_types import BSLCatalogReference
from yadinassi.configuration_accumulation_references import PROFILE
from yadinassi.configuration_profile_import import prepare_directory, create_prepared
from yadinassi.database_context import SQLiteDBContext
from test_inventory_reference_profile import imported
from test_main_demo_configuration import source as main_demo_source
from yadinassi.configuration_main_demo import import_main_demo_configuration

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'scripts/inventory_reference_behavior'
EXAMPLE=ROOT/'examples/inventory_reference'


class InventoryScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'inventory.sqlite'
    def make(self,source):
        context=create_prepared(self.path,prepare_directory(source,profile=PROFILE));self.addCleanup(context.close)
        output=[];vm=Interpreter(database_context=context,output=output.append);self.addCleanup(vm.close)
        return context,vm,output
    def test_actual_owned_runtime_source_import_compile(self):
        p=prepare_directory(ASSETS/'runtime_source',profile=PROFILE)
        self.assertEqual((p.report()['catalogs'],p.report()['documents'],p.report()['registers']),(2,2,1))
        self.assertEqual(p.format_version,15)
    def test_measured_native12_replay(self):
        context,vm,_=self.make(ASSETS/'runtime_source')
        observed=[];diagnostics=[]
        vm.register_function('ПодробноеПредставлениеОшибки',lambda info:info.get_member('Description'))
        vm.register_function('AccumulationEmit',lambda n,value:observed.append((int(n),value)),returns_value=False)
        vm.register_function('AccumulationDiagnostic',lambda n,stage,error:diagnostics.append((int(n),stage,error)),returns_value=False)
        vm.execute((ASSETS/'observe.bsl').read_text(encoding='utf-8'),'measured-inventory12-host-replay')
        self.assertEqual([n for n,_ in observed],list(range(1,13)),repr(diagnostics))
        self.assertEqual(diagnostics,[])
        native=json.loads((ROOT/'tests/fixtures/native_inventory_reference/observations12.out').read_text(encoding='ascii'))
        self.assertEqual(native[1],'0,0,1|0,0,1|0,0,1')
        for index in range(12):
            with self.subTest(case=index+1):self.assertEqual(observed[index][1],native[index])
    def test_public_stock_example_atomic_refusal_and_reopen(self):
        context=SQLiteDBContext.create_main_demo(self.path,
            import_main_demo_configuration(main_demo_source(),profile='main-demo-v1'))
        self.addCleanup(context.close)
        output=[];vm=Interpreter(database_context=context,output=output.append);self.addCleanup(vm.close)
        vm.execute((EXAMPLE/'run.bsl').read_text(encoding='utf-8'),'inventory-example')
        self.assertEqual(output,['After issue: Notebook, Main warehouse, 7',
            'After refused issue: 7','After unpost: 10','After repost: 8'])
        vm.close();context.close()
        with closing(SQLiteDBContext(self.path)) as reopened:
            lines=[]
            with closing(Interpreter(database_context=reopened,output=lines.append)) as fresh:
                fresh.execute((EXAMPLE/'reopen.bsl').read_text(encoding='utf-8'))
            self.assertEqual(lines,['P1, W1, 8','Turnovers: P1, W1, receipt 10, expense 2, net 8'])
    def test_cli_preflight_create_execute_and_reopen(self):
        def cli(*args):
            result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-m','yadinassi',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            return result.stdout
        cli('--create-demo-db',self.path,'--import-xml',ROOT/'examples/demo')
        self.assertIn('After repost: 8',cli('--f',self.path,EXAMPLE/'run.bsl'))
        reopened=cli('--f',self.path,EXAMPLE/'reopen.bsl')
        self.assertIn('P1, W1, 8',reopened)
        self.assertIn('Turnovers: P1, W1, receipt 10, expense 2, net 8',reopened)
    def test_closed_schema_kind_rejects_str_subclass(self):
        class Foreign(str):pass
        r=imported().registers[0]
        with self.assertRaises(BackendError):
            validate_schema(replace(r,dimensions=(replace(r.dimensions[0],kind=Foreign('catalog_ref')),*r.dimensions[1:])))
    def test_cross_database_reference_assignment_refused(self):
        context,vm,_=self.make(ASSETS/'runtime_source')
        other_path=Path(self.temp.name)/'other.sqlite'
        with closing(create_prepared(other_path,prepare_directory(ASSETS/'runtime_source',profile=PROFILE))) as other:
            with closing(Interpreter(database_context=other,output=lambda text:None)) as foreign:
                foreign.execute('P=Catalogs.Products.CreateItem();P.Code="X";P.Write();')
                value=foreign.execute('P.Ref')
                vm.register_function('ForeignRef',lambda:value)
                with self.assertRaises(BSLRuntimeError):vm.execute('D=Documents.Receipt.CreateDocument();L=D.Lines.Add();L.Product=ForeignRef();')
    def test_same_database_different_family_is_not_coerced(self):
        context,vm,_=self.make(ASSETS/'runtime_source')
        vm.execute('D=Documents.Receipt.CreateDocument(); L=D.Lines.Add(); R=D.RegisterRecords.Stock.Add();')
        with closing(Interpreter(database_context=context,output=lambda text:None)) as other:
            for expression in ('Catalogs.Products.EmptyRef()','Catalogs.Warehouses.EmptyRef()'):
                value=other.execute(expression)
                vm.register_function('ForeignRef',lambda:value)
                for target in ('D.Warehouse','L.Product','R.Product'):
                    with self.subTest(expression=expression,target=target),self.assertRaises(BSLRuntimeError):
                        vm.execute(target+'=ForeignRef();')
    def test_forged_references_are_not_coerced(self):
        _,vm,_=self.make(ASSETS/'runtime_source')
        vm.execute('D=Documents.Receipt.CreateDocument(); L=D.Lines.Add(); R=D.RegisterRecords.Stock.Add();')
        valid=vm.execute('Catalogs.Products.EmptyRef()')
        candidates=(BSLCatalogReference(valid.value_type,valid.reference_uuid),
            replace(valid,value_type=replace(valid.value_type,metadata_uuid=uuid4())),
            replace(valid,metadata=object()),replace(valid,read_member=lambda ref,name:None),
            replace(valid,get_object=None))
        for value in candidates:
            vm.register_function('ForeignRef',lambda:value)
            for target in ('D.Warehouse','L.Product','R.Product'):
                with self.subTest(target=target),self.assertRaises(BSLRuntimeError):vm.execute(target+'=ForeignRef();')
    def test_wrong_empty_target_converts_but_other_value_types_do_not(self):
        _,vm,_=self.make(ASSETS/'runtime_source')
        vm.execute('D=Documents.Receipt.CreateDocument(); L=D.Lines.Add(); R=D.RegisterRecords.Stock.Add();'
            'D.Warehouse=Catalogs.Products.EmptyRef(); L.Product=Catalogs.Warehouses.EmptyRef(); R.Product=Catalogs.Warehouses.EmptyRef();')
        self.assertTrue(vm.execute('(D.Warehouse=Catalogs.Warehouses.EmptyRef() And L.Product=Catalogs.Products.EmptyRef() And R.Product=Catalogs.Products.EmptyRef())'))
        for value in ('Undefined','Null','0','""','Documents.Receipt.EmptyRef()','Catalogs.Products.CreateItem()'):
            for target in ('D.Warehouse','L.Product','R.Product'):
                with self.subTest(target=target,value=value),self.assertRaises(BSLRuntimeError):vm.execute(target+'='+value+';')
    def test_staged_reference_is_visible_without_early_acceptance(self):
        _,vm,_=self.make(ASSETS/'runtime_source')
        vm.execute('BeginTransaction(); C=Catalogs.Products.CreateItem(); C.Code="A"; C.Write();'
            'Before=C.Ref; Alias=C.Ссылка; WasNew=C.IsNew(); RollbackTransaction();')
        self.assertFalse(vm.execute('Before.IsEmpty()'))
        self.assertEqual(vm.execute('Before'),vm.execute('Alias'))
        self.assertTrue(vm.execute('WasNew'))
        self.assertTrue(vm.execute('C.Ref.IsEmpty()'))
        vm.execute('BeginTransaction(); C.Write(); Staged=C.Ref; CommitTransaction();')
        self.assertEqual(vm.execute('Staged'),vm.execute('C.Ref'))
        self.assertFalse(vm.execute('C.IsNew()'))
    def test_staged_reference_never_bypasses_owner_or_uncertain_state(self):
        context,vm,_=self.make(ASSETS/'runtime_source')
        from yadinassi import database_transactions as transactions
        def inspect():
            obj=vm.execute('C')
            transaction=transactions.current(context.backend)
            token=transactions._execution.set(object())
            try:
                with self.assertRaises(BackendError):obj.get_member('Ref')
            finally:transactions._execution.reset(token)
            transaction.unit.state='uncertain'
            try:
                with self.assertRaises(BackendError):obj.get_member('Ref')
            finally:transaction.unit.state='open'
            participants=transaction.participants
            transaction.participants=()
            try:
                with self.assertRaises(BackendError):obj.get_member('Ref')
            finally:transaction.participants=participants
        vm.register_function('InspectStaged',inspect,returns_value=False)
        vm.execute('BeginTransaction(); C=Catalogs.Products.CreateItem(); C.Code="A"; C.Write();'
            'InspectStaged(); RollbackTransaction();')
    def test_polymorphic_recorder_remains_refused(self):
        _,vm,_=self.make(ASSETS/'runtime_source')
        with self.assertRaises(BSLRuntimeError):
            vm.execute('Q=New Query("SELECT R.Recorder FROM AccumulationRegister.Stock AS R");Q.Execute();')
    def test_movement_target_invariant_rejects_orphan(self):
        context,vm,_=self.make(ASSETS/'runtime_source')
        vm.execute('P=Catalogs.Products.GetRef(New UUID("'+str(uuid4())+'"));'
            'D=Documents.Receipt.CreateDocument();D.Number="X";D.Date=Date(2024,1,1);'
            'L=D.Lines.Add();L.Product=P;L.Quantity=1;L.Amount=1;')
        with self.assertRaises(BSLRuntimeError):vm.execute('D.Write(DocumentWriteMode.Posting);')
