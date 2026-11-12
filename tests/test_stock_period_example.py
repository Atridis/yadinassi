"""Fresh-only period example, read-only reopen and explicit reconciliation."""
from contextlib import closing
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.configuration_accumulation_references import PROFILE
from yadinassi.configuration_profile_import import prepare_directory, create_prepared
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'examples/inventory_reference'
HEADER='Month | Product | Warehouse | Opening | Receipt | Expense | Net | Closing'
INITIAL=[HEADER,
    '2024-01-01 | PS-CARRY | PS-W | 7 | 0 | 0 | 0 | 7',
    '2024-01-01 | PS-STOCK | PS-W | 5 | 10 | 3 | 7 | 12',
    '2024-02-01 | PS-ZERO | PS-W | 0 | 2 | 2 | 0 | 0',
    '2024-03-01 | PS-STOCK | PS-W | 12 | 0 | 2 | -2 | 10',
    '2024-04-01 | PS-CARRY | PS-W | 7 | 0 | 0 | 0 | 7',
    '2024-04-01 | PS-STOCK | PS-W | 10 | 0 | 0 | 0 | 10']
RECONCILED=[HEADER,
    '2024-01-01 | PS-CARRY | PS-W | 7 | 0 | 0 | 0 | 7',
    '2024-01-01 | PS-STOCK | PS-W | 5 | 10 | 4 | 6 | 11',
    '2024-02-01 | PS-ZERO | PS-W | 0 | 2 | 2 | 0 | 0',
    '2024-04-01 | PS-CARRY | PS-W | 7 | 0 | 0 | 0 | 7',
    '2024-04-01 | PS-STOCK | PS-W | 11 | 0 | 0 | 0 | 11']


class StockPeriodExampleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'period.sqlite'
    def create(self):
        from yadinassi.configuration_main_demo import import_main_demo_configuration
        from test_main_demo_configuration import source
        with closing(SQLiteDBContext.create_main_demo(self.path,import_main_demo_configuration(source(),profile='main-demo-v1'))):pass
    def run_script(self,name,*,read_only=False):
        output=[]
        # The public CLI context has no read_only argument. This test host
        # supplies the existing readonly backend, without adding a public API.
        if read_only:
            context=object.__new__(SQLiteDBContext)
            context._backend=SQLiteCatalogBackend(self.path,read_only=True)
            context.path=context._backend.path
        else:
            context=SQLiteDBContext(self.path)
        with closing(context):
            with closing(Interpreter(database_context=context,output=output.append)) as vm:
                vm.execute((EXAMPLE/name).read_text(encoding='utf-8'),name)
        return output
    def test_fresh_seed_and_readonly_reopen_are_usable(self):
        self.create()
        self.assertEqual(self.run_script('period_seed.bsl'),['Stock period example created.'])
        before=self.path.read_bytes()
        self.assertEqual(self.run_script('period_statement.bsl',read_only=True),INITIAL)
        self.assertEqual(self.path.read_bytes(),before)
    def test_repost_unpost_reconcile_after_independent_reopen(self):
        self.create();self.run_script('period_seed.bsl')
        self.run_script('period_reconcile.bsl')
        self.assertEqual(self.run_script('period_statement.bsl',read_only=True),RECONCILED)
    def test_readonly_report_does_not_depend_on_live_catalog_objects(self):
        self.create();self.run_script('period_seed.bsl')
        for _ in range(2):self.assertEqual(self.run_script('period_statement.bsl',read_only=True),INITIAL)
    def test_cli_create_seed_report_and_reconcile(self):
        def cli(*args):
            run=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-m','yadinassi',*map(str,args)],
                               cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr)
            return run.stdout.splitlines()
        cli('--create-demo-db',self.path,'--import-xml',ROOT/'examples/demo')
        self.assertEqual(cli('--f',self.path,EXAMPLE/'period_seed.bsl'),['Stock period example created.'])
        self.assertEqual(cli('--f',self.path,EXAMPLE/'period_statement.bsl'),INITIAL)
        cli('--f',self.path,EXAMPLE/'period_reconcile.bsl')
        self.assertEqual(cli('--f',self.path,EXAMPLE/'period_statement.bsl'),RECONCILED)
