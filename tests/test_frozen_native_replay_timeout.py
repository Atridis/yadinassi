"""Keep every frozen launch bounded without weakening native replay checks."""
import ast
import inspect
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts import smoke_test


class FrozenNativeReplayTimeoutTests(unittest.TestCase):
    def invoke(self, run):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(smoke_test.subprocess, 'run', side_effect=run):
                smoke_test.check_saved_native_outputs('frozen', directory=Path(temporary)/'replay', env={})

    def output(self, argv, **kwargs):
        name = Path(argv[1]).stem.removesuffix('-historical')
        expected = (smoke_test.ROOT/'tests/fixtures/native_windows'/f'{name}.out').read_text(encoding='utf-8')
        return subprocess.CompletedProcess(argv, 0, expected, '')

    def test_all_authenticated_replays_receive_common_bound(self):
        calls = []
        def run(argv, **kwargs):
            calls.append((Path(argv[1]).stem, kwargs['timeout']))
            return self.output(argv, **kwargs)
        self.invoke(run)
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(timeout == 120 for name, timeout in calls))

    def test_reconstruction_rejection_prevents_collection_launch(self):
        calls = []
        def run(argv, **kwargs):
            calls.append(Path(argv[1]).stem)
            return self.output(argv, **kwargs)
        with patch.object(smoke_test, 'historical_collections_source', side_effect=ValueError('source binding changed')):
            with self.assertRaisesRegex(ValueError, 'source binding changed'):
                self.invoke(run)
        self.assertEqual(calls, ['functions-historical', 'strings'])

    def test_output_mismatch_still_fails(self):
        def run(argv, **kwargs):
            result = self.output(argv, **kwargs)
            if Path(argv[1]).stem == 'collections-historical': result.stdout += 'unexpected\n'
            return result
        with self.assertRaisesRegex(AssertionError, 'Frozen native output mismatch: collections'):
            self.invoke(run)

    def test_collection_timeout_is_not_swallowed(self):
        def run(argv, **kwargs):
            if Path(argv[1]).stem == 'collections-historical':
                self.assertEqual(kwargs['timeout'], 120)
                raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
            return self.output(argv, **kwargs)
        with self.assertRaises(subprocess.TimeoutExpired): self.invoke(run)

    def test_every_frozen_subprocess_has_the_same_finite_bound(self):
        self.assertEqual(smoke_test.FROZEN_PROCESS_TIMEOUT_SECONDS, 120)
        tree = ast.parse(inspect.getsource(smoke_test))
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == 'subprocess' and node.func.attr == 'run']
        self.assertGreater(len(calls), 70)
        for call in calls:
            with self.subTest(line=call.lineno):
                timeout = next((arg.value for arg in call.keywords if arg.arg == 'timeout'), None)
                self.assertIsInstance(timeout, ast.Name)
                self.assertEqual(timeout.id, 'FROZEN_PROCESS_TIMEOUT_SECONDS')
