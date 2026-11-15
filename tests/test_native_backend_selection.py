"""Native oracle selection must not drift with the application default."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_native_1c_smoke import smoke


class NativeBackendSelectionTests(unittest.TestCase):
    def test_real_child_oracle_and_strict_selection_are_explicit(self):
        full = smoke.FULL
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'case.bsl'
            source.write_text('r=0;For i=1 To 2 Do r=r+i;EndDo;', encoding='utf-8')
            for mode in ('interpreter', 'compiled-strict'):
                with self.subTest(mode=mode):
                    # Observe the actual constructed runtime after execution.
                    script = full.EXECUTE_SCRIPT + '\nprint(interpreter.execution_backend)\n'
                    args = [sys.executable, '-I', '-B', '-c', script,
                            str(smoke.ROOT), str(source), full.LINUX_TARGET]
                    evidence = root / 'execution.json'
                    if mode == 'compiled-strict':
                        args += [mode, str(evidence)]
                    result = subprocess.run(args, capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.decode().strip(), mode)
                    if mode == 'compiled-strict':
                        stats = json.loads(evidence.read_text())
                        self.assertGreater(stats['emitted_executions'] + stats['helper_executions']
                                           + stats['inline_blocks'] + stats['inline_fragments'], 0)
                        for name in ('interpreter_fallbacks', 'old_backend_executions', 'strict_rejections'):
                            self.assertEqual(stats[name], 0)

    def test_client_witness_selects_explicit_oracle(self):
        import ast
        tree = ast.parse(smoke.FULL.CLIENT_EXECUTE_SCRIPT)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'Interpreter']
        self.assertEqual(len(calls), 1)
        selections = [kw.value.value for kw in calls[0].keywords
                      if kw.arg == 'execution_backend' and isinstance(kw.value, ast.Constant)]
        self.assertEqual(selections, ['interpreter'])

    @unittest.skipIf(os.name == 'nt', 'owned witness uses POSIX process groups')
    def test_real_client_witness_retains_oracle_under_snapshot_default(self):
        full = smoke.FULL
        full.verify_client_interpreter(smoke.ROOT, smoke.ROOT / full.CLIENT_SOURCE,
                                       full.PREPROCESSOR_SOURCE_SHA256)

    def test_exact_inverse_preserves_historical_fixture_and_rejects_drift(self):
        import test_native_async_fixture as history
        source = (smoke.ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        restored = history.without_explicit_oracle_backend(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         '958376c98dca682b77b5e8cc07e1e913a6d8b9118d2bde67652e039ff1505e5b')
        for changed in (source + '# drift\n', source.replace('CASE_SECONDS = 10', 'CASE_SECONDS = 11')):
            with self.assertRaises(AssertionError):
                history.without_sqlite_host_context(changed)
