"""Report-contract tests, not evidence of compiled language execution."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StrictRunnerReportTests(unittest.TestCase):
    def test_caught_preengine_rejection_is_a_gap_not_compiled_success(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'rejection_fixture.py').write_text('''import unittest
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
class Rejection(unittest.TestCase):
    def test_rejected_adapter(self):
        class Unknown(Interpreter): pass
        vm = Unknown()
        with self.assertRaises(CompiledUnsupported):
            vm.execute('changed=1;')
        self.assertNotIn('changed', vm.variables)
''', encoding='utf-8')
            report = folder / 'report.json'
            env = dict(os.environ)
            env['PYTHONPATH'] = os.pathsep.join((directory, str(root)))
            process = subprocess.run(
                [sys.executable, str(root / 'scripts' / 'run_compiled_tests.py'),
                 '--module', 'rejection_fixture', '--report', str(report)],
                env=env, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', timeout=30,
            )
            self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
            result = json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(result['test_assertions_passed'])
            self.assertEqual(result['tests_run'], 1)
            self.assertEqual(len(result['strict_coverage_gaps']), 1)
            case = result['cases'][0]
            self.assertFalse(case['compiled_execution_observed'])
            self.assertEqual(case['strict_rejections'], 1)
            self.assertEqual(case['emitted_executions'], 0)
            self.assertEqual(case['helper_executions'], 0)


    def test_optional_health_probe_does_not_claim_helper_as_compiled(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'health_fixture.py').write_text(
                'import time, unittest\nclass Health(unittest.TestCase):\n'
                ' def test_wait(self): time.sleep(.2)\n'
                ' def test_execution(self):\n'
                '  from yadinassi import Interpreter\n'
                '  Interpreter().execute("x=1;")\n', encoding='utf-8')
            report = folder / 'report.json'
            env = dict(os.environ)
            env['PYTHONPATH'] = os.pathsep.join((directory, str(root)))
            process = subprocess.run(
                [sys.executable, str(root / 'scripts' / 'run_compiled_tests.py'),
                 '--module', 'health_fixture', '--report', str(report),
                 '--diagnostic-heartbeat-seconds', '.01'], env=env, cwd=root,
                capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            result = json.loads(report.read_text(encoding='utf-8'))
            self.assertFalse(result['owned_snapshot_experiment'])
            self.assertTrue(result['origin_mutation_monitor'])
            waiting = next(row for row in result['cases'] if row['test'].endswith('test_wait'))
            executing = next(row for row in result['cases'] if row['test'].endswith('test_execution'))
            self.assertFalse(waiting['compiled_execution_observed'])
            self.assertEqual(waiting['observed_execution_contracts'], [])
            self.assertTrue(executing['compiled_execution_observed'])
            self.assertEqual(executing['observed_execution_contracts'], [{
                'owned_snapshot': True, 'origin_mutation_monitor': 'off',
                'active_ast_contract': 'snapshot'}])
            health = json.loads(report.with_suffix('.health.json').read_text(encoding='utf-8'))
            self.assertGreater(health['pid'], 0)
            self.assertGreaterEqual(health['process_cpu_seconds'], 0)
            # This is the latest sample, which may legitimately observe result
            # reporting after the wait. Do not assert thread scheduling timing.
            self.assertTrue(health['stack'])
            self.assertLessEqual(len(health['stack']), 80)
            self.assertTrue(all(len(row) == 3 and isinstance(row[0], str)
                                and isinstance(row[1], str) and isinstance(row[2], int)
                                for row in health['stack']))


    def test_metadata_entry_execution_is_distinct_from_admission_and_inline(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'metadata_fixture.py').write_text('''import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
class Metadata(unittest.TestCase):
    def admitted(self):
        vm=Interpreter(execution_backend='compiled-strict')
        call=parse('Unused();')[0].expression
        vm._compiled().prepare_node(call)
        return vm,call.arguments
    def test_admission_only(self):
        vm,arguments=self.admitted()
        self.assertEqual(vm.compiled_backend_stats['metadata_block_executions'],0)
    def test_empty_metadata_execution(self):
        vm,arguments=self.admitted()
        self.assertIsNone(vm._scheduler.run_inline(vm.block(arguments)))
        self.assertEqual(vm.compiled_backend_stats['metadata_block_executions'],1)
    def test_helper_only(self):
        self.assertEqual(1+1,2)
''', encoding='utf-8')
            report = folder / 'report.json'
            env = dict(os.environ, PYTHONPATH=os.pathsep.join((directory, str(root))))
            process = subprocess.run(
                [sys.executable, str(root / 'scripts' / 'run_compiled_tests.py'),
                 '--module', 'metadata_fixture', '--lowering', 'inline-fast', '--report', str(report)],
                env=env, cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            result = json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(result['test_assertions_passed'])
            self.assertEqual(result['tests_run'], 3)
            self.assertEqual(result['strict_coverage_gaps'], [])
            for case in result['cases']:
                executed = case['test'].endswith('test_empty_metadata_execution')
                self.assertEqual(case['metadata_block_executions'], int(executed))
                self.assertEqual(case['compiled_execution_observed'], executed)
                for key in ('inline_blocks','inline_fragments','emitted_executions','helper_executions'):
                    self.assertEqual(case[key], 0)
                self.assertEqual(case['observed_execution_contracts'], [{
                    'owned_snapshot': True, 'origin_mutation_monitor': 'off',
                    'active_ast_contract': 'snapshot'}] if executed else [])

    def test_context_early_return_legacy_visitors_remain_a_gap_with_compiled_execution(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'context_fixture.py').write_text('import unittest\nfrom yadinassi import Interpreter\nclass Context(unittest.TestCase):\n def test_mixed(self):\n  Interpreter(execution_backend="compiled-strict").execute("x=1;")\n  from types import SimpleNamespace\n  from yadinassi.source_constant_managers import _ValueInterpreter\n  from yadinassi.form_runtime import _FormInterpreter\n  from yadinassi.syntax.parser import parse\n  value_vm=object.__new__(_ValueInterpreter)\n  value_vm.manager=SimpleNamespace(value_read=lambda vm: 7)\n  if value_vm.visit_Name(parse(\'Value;\')[0].expression)!=7: raise AssertionError(\'Value result\')\n  form=SimpleNamespace(_check=lambda: None)\n  form_vm=object.__new__(_FormInterpreter)\n  Interpreter.__init__(form_vm, execution_backend="compiled-strict")\n  form_vm._form_session=SimpleNamespace(form=form)\n  if form_vm.visit_Name(parse(\'ThisObject;\')[0].expression) is not form: raise AssertionError(\'ThisObject identity\')\n',encoding='utf-8')
            report=folder/'report.json'
            env=dict(os.environ,PYTHONPATH=os.pathsep.join((directory,str(root))))
            process=subprocess.run([sys.executable,str(root/'scripts/run_compiled_tests.py'),
                '--module','context_fixture','--lowering','inline-fast','--report',str(report)],
                env=env,cwd=root,capture_output=True,text=True,timeout=30)
            self.assertEqual(process.returncode,2,process.stdout+process.stderr)
            result=json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(result['test_assertions_passed'])
            self.assertEqual(len(result['strict_coverage_gaps']),1)
            case=result['cases'][0]
            self.assertTrue(case['compiled_execution_observed'])
            self.assertEqual(case['legacy_visitor_calls'],2)
            self.assertEqual(case['strict_rejections'],0)


if __name__ == '__main__':
    unittest.main()
