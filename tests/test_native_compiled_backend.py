"""Current direct child security plus historical evidence validators; no native run."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_1c_smoke import smoke

ROOT=Path(__file__).resolve().parents[1]
full=smoke.FULL

class NativeCompiledBackendTests(unittest.TestCase):

    def test_direct_child_default_and_explicit_route_execute_real_routines(self):
        bodies = ('Function F() Return 42; EndFunction Message(F());',
                  'Function F() s=0;For i=1 To 2 Do s=s+21;EndDo;Return s;EndFunction Message(F());')
        # Read actual backend state after execution; output equality is not the
        # witness of backend selection.
        script = full.EXECUTE_SCRIPT + (
            "\nsys.stderr.buffer.write((interpreter.execution_backend + '\\n').encode('ascii'))\n")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.bsl'
            for body in bodies:
                source.write_text(body, encoding='utf-8')
                for arguments in ([], ['python-direct']):
                    with self.subTest(body=body, arguments=arguments):
                        result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                            str(ROOT), str(source), full.LINUX_TARGET, *arguments],
                            capture_output=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, b'42\n')
                        self.assertEqual(result.stderr, b'python-direct\n')

    def test_direct_child_backend_drift_fails_before_and_after_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.bsl'
            source.write_text('Message(42);', encoding='utf-8')
            for boundary in ('before', 'after'):
                marker = ('interpreter = Interpreter(output=emit, **options)' if boundary == 'before'
                          else 'interpreter.execute(source_text, str(source))')
                script = full.EXECUTE_SCRIPT.replace(marker, marker + "\ninterpreter._execution_backend = 'interpreter'")
                self.assertNotEqual(script, full.EXECUTE_SCRIPT)
                with self.subTest(boundary=boundary):
                    result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                        str(ROOT), str(source), full.LINUX_TARGET, 'python-direct'],
                        capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b'execution backend mismatch', result.stderr)
                    self.assertEqual(result.stdout, b'' if boundary == 'before' else b'42\n')

    def test_child_rejects_invalid_backend_protocol_before_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'case.bsl'; stats = Path(directory) / 'execution.json'
            source.write_text('Message(42);', encoding='utf-8')
            command = [sys.executable, '-I', '-B', '-c', full.EXECUTE_SCRIPT, str(ROOT), str(source), full.LINUX_TARGET]
            for args in (['interpreter'], ['hybrid'], ['garbage'], ['compiled-strict'], ['python-direct', str(stats)], ['compiled-strict', str(stats), 'extra']):
                with self.subTest(args=args):
                    result = subprocess.run(command + args, capture_output=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, b'')
                    self.assertFalse(stats.exists())

    def test_source_only_inverse_is_exact_and_rejects_mutation(self):
        from test_native_async_fixture import without_compiled_backend_harness
        import hashlib
        source=(ROOT/'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        contract=json.loads((ROOT/'tests/native_compiled_source_inverse.json').read_text(encoding='utf-8'))
        restored=without_compiled_backend_harness(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),contract['base_sha256'])
        changed=source+'# changed\n'
        self.assertEqual(without_compiled_backend_harness(changed),changed)

    def test_invalid_backend_rejected_before_native_work(self):
        with self.assertRaises(smoke.SmokeError):
            smoke.run_smoke(Path('/not-used'),execution_backend='compiled-strict')
        with self.assertRaises(smoke.SmokeError):
            smoke.run_smoke(Path('/not-used'),full_suite=True,execution_backend='garbage')

    def test_three_harness_inverses_are_exact_and_reject_unknown_changes(self):
        from test_native_async_fixture import historical_source_bytes, without_associative_order_harness
        import hashlib
        inventory=json.loads((ROOT/'tests/native_compiled_source_inverse.json').read_text(encoding='utf-8'))
        contracts={'scripts/native_1c_full_host.py':inventory,**inventory['additional_sources']}
        for path,contract in contracts.items():
            with self.subTest(path=path):
                if path == 'scripts/native_async_comparison.py':
                    raw = (ROOT / 'tests/fixtures/native_compiled_inverse/native_async_comparison.py.txt').read_bytes()
                else:
                    source = (ROOT / path).read_text(encoding='utf-8')
                    raw = without_associative_order_harness(source, path).encode('utf-8')
                self.assertEqual(hashlib.sha256(raw).hexdigest(),contract['candidate_sha256'])
                restored=historical_source_bytes(path,raw,contract['base_sha256'])
                self.assertEqual(hashlib.sha256(restored).hexdigest(),contract['base_sha256'])
                self.assertEqual(historical_source_bytes(path,restored,contract['base_sha256']),restored)
                self.assertEqual(historical_source_bytes(path,raw,contract['candidate_sha256']),raw)
                self.assertEqual(historical_source_bytes(path,raw,'0'*64),raw)
                with self.assertRaisesRegex(AssertionError,'outer identity'):
                    historical_source_bytes(path,raw+b'\n# changed',contract['base_sha256'])

if __name__=='__main__':unittest.main()
