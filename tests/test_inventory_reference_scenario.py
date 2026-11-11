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
from yadinassi.configuration_accumulation_references import PROFILE
from yadinassi.configuration_profile_import import prepare_directory, create_prepared
from yadinassi.database_context import SQLiteDBContext
from test_inventory_reference_profile import imported

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
    def test_candidate_native12_observer_executes_as_host_subset(self):
        context,vm,_=self.make(ASSETS/'runtime_source')
        observed=[];diagnostics=[]
        vm.register_function('ПодробноеПредставлениеОшибки',lambda info:info.get_member('Description'))
        vm.register_function('AccumulationEmit',lambda n,value:observed.append((int(n),value)),returns_value=False)
        vm.register_function('AccumulationDiagnostic',lambda n,stage,error:diagnostics.append((int(n),stage,error)),returns_value=False)
        vm.execute((ASSETS/'observe.bsl').read_text(),'candidate-inventory12-not-native-evidence')
        self.assertEqual([n for n,_ in observed],list(range(1,13)),repr(diagnostics))
        self.assertEqual(diagnostics,[])
        # Host target guard. Native wrong-target coercion may deliberately differ.
        self.assertEqual(observed[0][1],'1,1,1,1')
        self.assertEqual(observed[1][1],'1,1,0|1,1,0|1,1,0')
    def test_public_stock_example_atomic_refusal_and_reopen(self):
        context,vm,output=self.make(EXAMPLE/'source')
        vm.execute((EXAMPLE/'run.bsl').read_text(),'inventory-example')
        self.assertEqual(output,['After issue: Notebook, Main warehouse, 7',
            'After refused issue: 7','After unpost: 10','After repost: 8'])
        vm.close();context.close()
        with closing(SQLiteDBContext(self.path)) as reopened:
            lines=[]
            with closing(Interpreter(database_context=reopened,output=lines.append)) as fresh:
                fresh.execute((EXAMPLE/'reopen.bsl').read_text())
            self.assertEqual(lines,['P1, W1, 8','Turnovers: P1, W1, receipt 10, expense 2, net 8'])
    def test_cli_preflight_create_execute_and_reopen(self):
        def cli(*args):
            result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-m','yadinassi',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
            return result.stdout
        report=json.loads(cli('--check-xml',EXAMPLE/'source','--source-profile',PROFILE,'--report-json'))
        self.assertEqual(report['storage_format'],15);self.assertFalse(self.path.exists())
        cli('--create-db',self.path,'--import-xml',EXAMPLE/'source','--source-profile',PROFILE)
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
        context,vm,_=self.make(EXAMPLE/'source')
        other_path=Path(self.temp.name)/'other.sqlite'
        with closing(create_prepared(other_path,prepare_directory(EXAMPLE/'source',profile=PROFILE))) as other:
            with closing(Interpreter(database_context=other,output=lambda text:None)) as foreign:
                foreign.execute('P=Catalogs.Products.CreateItem();P.Code="X";P.Write();')
                value=foreign.execute('P.Ref')
                vm.register_function('ForeignRef',lambda:value)
                with self.assertRaises(BSLRuntimeError):vm.execute('D=Documents.Receipt.CreateDocument();L=D.Lines.Add();L.Product=ForeignRef();')
    def test_polymorphic_recorder_remains_refused(self):
        _,vm,_=self.make(EXAMPLE/'source')
        with self.assertRaises(BSLRuntimeError):
            vm.execute('Q=New Query("SELECT R.Recorder FROM AccumulationRegister.Stock AS R");Q.Execute();')
    def test_movement_target_invariant_rejects_orphan(self):
        context,vm,_=self.make(EXAMPLE/'source')
        vm.execute('P=Catalogs.Products.GetRef(New UUID("'+str(uuid4())+'"));'
            'D=Documents.Receipt.CreateDocument();D.Number="X";D.Date=Date(2024,1,1);'
            'L=D.Lines.Add();L.Product=P;L.Quantity=1;L.Amount=1;')
        with self.assertRaises(BSLRuntimeError):vm.execute('D.Write(DocumentWriteMode.Posting);')
