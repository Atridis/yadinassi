"""Fresh CLI stock query package; never migrates an existing demo database."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'examples/inventory_reference'


class ScopedStockExampleTests(unittest.TestCase):
    def test_fresh_cli_seed_and_readonly_three_report_package(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            database=Path(temp)/'stock.sqlite'
            def cli(*args):
                result=subprocess.run([sys.executable,*(['-O'] if sys.flags.optimize else []),'-m','yadinassi',*map(str,args)],cwd=ROOT,capture_output=True,text=True,
                               encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
                self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
                return result.stdout.splitlines()
            cli('--create-demo-db',database,'--import-xml',ROOT/'examples/demo')
            cli('--f',database,EXAMPLE/'period_seed.bsl')
            expected=['Balance: 10','Turnover 202401: 7','Turnover 202403: -2',
                      'Statement 202401: 5,10,3,12','Statement 202403: 12,0,2,10']
            self.assertEqual(cli('--f',database,EXAMPLE/'scoped_statement.bsl'),expected)
            self.assertEqual(cli('--f',database,EXAMPLE/'scoped_statement.bsl'),expected)
