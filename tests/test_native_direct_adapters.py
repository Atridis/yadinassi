"""Current replay routing, separate from historical engine evidence schemas."""
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import native_1c_full_host as full, native_1c_smoke as smoke
from scripts import native_async_comparison as async_adapter


class DirectReplayAdapterTests(unittest.TestCase):
    def test_retired_routes_reject_before_native_or_local_work(self):
        for backend in ('interpreter', 'hybrid', 'compiled-strict'):
            with self.subTest(backend=backend), patch.object(full, 'bounded_child', side_effect=AssertionError('child')):
                with self.assertRaises(full.FullError):
                    full.compare_outputs(Path('/unused'), Path('/unused'), {}, {}, execution_backend=backend)
                with self.assertRaises(full.FullError):
                    full.compare_async_runtime(Path('/unused'), Path('/unused'), {}, {}, execution_backend=backend)
                with self.assertRaises(smoke.SmokeError):
                    smoke.run_smoke(Path('/unused'), execution_backend=backend)
                with self.assertRaises(ValueError):
                    async_adapter.execute_actual([], execution_backend=backend)

    def test_async_current_failure_is_not_replaced_by_expected_rows(self):
        root = Path(__file__).resolve().parents[1]
        _, bodies = async_adapter.read_pinned_sources((root / 'scripts/native_1c_bootstrap/full_suite.py').read_bytes())
        from yadinassi import Interpreter
        with patch.object(Interpreter, 'execute', side_effect=RuntimeError('private failure')):
            rows = async_adapter.execute_actual(bodies)
        self.assertEqual(len(rows), 8)
        for trace, values, errors, lifecycle, failed in rows:
            self.assertEqual((trace, values, errors, lifecycle, failed), ([], [], [], False, True))
        self.assertNotIn('private failure', str(rows))
