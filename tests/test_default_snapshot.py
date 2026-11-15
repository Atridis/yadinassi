"""Default selection is exercised, not inferred from a successful return code."""
import subprocess
import sys
import unittest
from yadinassi import Interpreter
from yadinassi.execution_policy import current_backend, execution_backend_policy


class DefaultSnapshotTests(unittest.TestCase):
    def test_default_executes_compiled_blocks_without_fallback(self):
        self.assertEqual(current_backend(), 'compiled-strict')
        vm = Interpreter()
        vm.execute('r=0; For i=1 To 3 Do r=r+i; EndDo;')
        self.assertEqual(vm.variables['r'], 6)
        self.assertEqual(vm.execution_backend, 'compiled-strict')
        stats = vm.compiled_backend_stats
        self.assertGreater(stats['block_executions'], 0)
        self.assertEqual(stats['interpreter_fallbacks'], 0)
        self.assertEqual(vm.compiled_ast_contract, 'snapshot')

    def test_explicit_interpreter_is_not_replaced(self):
        with execution_backend_policy('interpreter'):
            vm = Interpreter()
            vm.execute('r=1;')
            self.assertEqual(vm.execution_backend, 'interpreter')
            self.assertIsNone(vm._compiled_engine)
        self.assertEqual(current_backend(), 'compiled-strict')

    def test_cli_default_and_explicit_rollback_have_actual_engine_witness(self):
        # Subprocess instrumentation observes selection/entry without replacing
        # visitor methods or changing production runtime semantics.
        code = """import sys
from yadinassi.compiled_backend import Engine
from yadinassi.cli import main
mode=sys.argv.pop()
original=Engine.run_block
seen=[]
def block(self,*a,**kw):
    seen.append(1)
    return (yield from original(self,*a,**kw))
Engine.run_block=block
args=['-c','r=2+3;']
if mode!='default':args=['--execution-backend',mode]+args
if main(args)!=0: raise RuntimeError('CLI failed')
if bool(seen)!=(mode=='default'): raise RuntimeError((mode,seen))
"""
        for mode in ('default', 'interpreter'):
            with self.subTest(mode=mode):
                subprocess.run([sys.executable, '-c', code, mode], check=True,
                               capture_output=True, timeout=20)
