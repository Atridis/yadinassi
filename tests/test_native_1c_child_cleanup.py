"""Deterministic POSIX cleanup contracts, without real signals or shared fixtures."""
import errno
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from test_native_1c_full_host import full


class ChildCleanupTests(unittest.TestCase):
    def child(self):
        process = mock.MagicMock()
        process.pid = 123
        process.wait.return_value = 0
        return process

    def run_cleanup(self, process, signals):
        with mock.patch.object(full.os, "killpg", create=True, side_effect=signals) as kill, \
             mock.patch.object(full.signal, "SIGKILL", 9, create=True):
            full._finish_child(process)
        return kill

    def assert_wait_bounded(self, process):
        self.assertTrue(process.wait.call_args_list)
        for call in process.wait.call_args_list:
            self.assertEqual(call.args, ())
            self.assertGreater(call.kwargs["timeout"], 0)
            self.assertLessEqual(call.kwargs["timeout"], max(full.CASE_SECONDS, full.CHILD_CLEANUP_SECONDS))
        self.assertLessEqual(process.wait.call_args.kwargs["timeout"], full.CHILD_CLEANUP_SECONDS)
        process.__enter__.assert_not_called()
        process.__exit__.assert_not_called()

    def test_cleanup_deadline_rounding_never_exceeds_five_second_cap(self):
        # A Windows monotonic tick near a binary exponent boundary can round
        # (now + 5) - now upward, even when the clock has not advanced.
        self.assertGreater((255.1 + 5) - 255.1, 5)
        for readings, expected in (([255.1, 255.1], 5),
                                   ([100.0, 101.25], 3.75),
                                   ([100.0, 106.0], 0.001)):
            with self.subTest(readings=readings):
                process = self.child()
                with mock.patch.object(full.time, 'monotonic', side_effect=readings):
                    self.run_cleanup(process, [None])
                process.wait.assert_called_once_with(timeout=expected)
                self.assert_wait_bounded(process)

    def test_successful_group_kill_retains_termination_and_bounded_reap(self):
        process = self.child()
        kill = self.run_cleanup(process, [None])
        self.assertEqual(kill.call_args_list, [mock.call(123, 9)])
        self.assert_wait_bounded(process)

    def test_already_missing_group_still_reaps_child(self):
        process = self.child()
        self.run_cleanup(process, [ProcessLookupError(errno.ESRCH, "private")])
        process.wait.assert_called_once()
        self.assert_wait_bounded(process)

    def test_permission_denial_only_recovers_after_reap_and_absence(self):
        process = self.child()
        events = []
        def signal_group(pid, sig):
            events.append(("signal", pid, sig))
            if sig == 9:
                raise PermissionError(errno.EPERM, "private")
            raise ProcessLookupError(errno.ESRCH, "private")
        process.wait.side_effect = lambda **kw: events.append(("reaped",)) or 0
        self.run_cleanup(process, signal_group)
        self.assertEqual(events, [("signal", 123, 9), ("reaped",), ("signal", 123, 0)])
        self.assert_wait_bounded(process)

    def test_reaped_leader_does_not_prove_descendant_group_absent(self):
        process = self.child()
        with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
            self.run_cleanup(process, [PermissionError(errno.EPERM, "private"), None])
        self.assert_wait_bounded(process)

    def test_permission_denied_existence_probe_is_not_success(self):
        process = self.child()
        with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
            self.run_cleanup(process, [PermissionError(errno.EPERM, "private")]*2)
        self.assert_wait_bounded(process)

    def test_wait_timeout_never_runs_existence_probe_or_unbounded_wait(self):
        for first_signal in (None, PermissionError(errno.EPERM, "private"), ProcessLookupError()):
            with self.subTest(signal=type(first_signal).__name__):
                process = self.child()
                process.wait.side_effect = subprocess.TimeoutExpired("private", 5)
                with mock.patch.object(full.os, "killpg", create=True, side_effect=[first_signal]) as kill, \
                     mock.patch.object(full.signal, "SIGKILL", 9, create=True), \
                     self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
                    full._finish_child(process)
                kill.assert_called_once_with(123, 9)
                process.wait.assert_called_once()
                self.assert_wait_bounded(process)

    def test_other_signal_and_wait_errors_remain_finite_failures(self):
        process = self.child()
        with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
            self.run_cleanup(process, [OSError(errno.EINVAL, "private")])
        process.wait.side_effect = OSError(errno.ECHILD, "private")
        with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
            self.run_cleanup(process, [None])

    def bounded_call(self, process, signals, *, overflow=True, seconds=10):
        selector = mock.MagicMock()
        selector.__enter__.return_value = selector
        selector.get_map.return_value = {1: True} if overflow else {}
        key = mock.Mock(data="stdout")
        selector.select.return_value = [(key, 1)]
        with mock.patch.object(full.subprocess, "Popen", return_value=process), \
             mock.patch.object(full.selectors, "DefaultSelector", return_value=selector), \
             mock.patch.object(full.os, "read", return_value=b"x"*100), \
             mock.patch.object(full.os, "killpg", create=True, side_effect=signals), \
             mock.patch.object(full.signal, "SIGKILL", 9, create=True):
            return full.bounded_child(["unused"], Path("unused"), seconds=seconds, stdout_limit=64)

    def assert_closed_without_context(self, process):
        process.stdout.close.assert_called_once()
        process.stderr.close.assert_called_once()
        process.__enter__.assert_not_called()
        process.__exit__.assert_not_called()

    def test_original_overflow_survives_only_proven_permission_recovery(self):
        process = self.child()
        with self.assertRaisesRegex(full.FullError, "^interpreter_output_limit$"):
            self.bounded_call(process, [PermissionError(errno.EPERM, "private"), ProcessLookupError()])
        self.assert_closed_without_context(process)
        self.assert_wait_bounded(process)

    def test_overflow_does_not_hide_unresolved_cleanup(self):
        for probe in (None, PermissionError(errno.EPERM, "private")):
            with self.subTest(probe=type(probe).__name__):
                process = self.child()
                with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
                    self.bounded_call(process, [PermissionError(errno.EPERM, "private"), probe])
                self.assert_closed_without_context(process)
                self.assert_wait_bounded(process)

    def test_cleanup_timeout_is_not_misclassified_as_interpreter_timeout(self):
        process = self.child()
        process.wait.side_effect = subprocess.TimeoutExpired("private", 5)
        with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
            self.bounded_call(process, [None])
        self.assert_closed_without_context(process)
        self.assert_wait_bounded(process)

    def test_original_timeout_survives_proven_cleanup(self):
        process = self.child()
        with self.assertRaisesRegex(full.FullError, "^interpreter_timeout$"):
            self.bounded_call(process, [PermissionError(errno.EPERM, "private"), ProcessLookupError()], seconds=-1)
        self.assert_closed_without_context(process)
        self.assert_wait_bounded(process)

    def test_success_requires_cleanup_and_does_not_enter_popen_context(self):
        for probe, success in ((ProcessLookupError(), True), (None, False)):
            with self.subTest(success=success):
                process = self.child()
                if success:
                    result = self.bounded_call(process, [PermissionError(errno.EPERM, "private"), probe], overflow=False)
                    self.assertEqual(result, (0, b"", b""))
                else:
                    with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
                        self.bounded_call(process, [PermissionError(errno.EPERM, "private"), probe], overflow=False)
                self.assert_closed_without_context(process)
                self.assert_wait_bounded(process)

    def test_both_pipes_closed_even_if_first_close_fails(self):
        process = self.child()
        process.stdout.close.side_effect = OSError(errno.EBADF, "private")
        with self.assertRaisesRegex(full.FullError, "^interpreter_unavailable$"):
            self.bounded_call(process, [None], overflow=False)
        self.assert_closed_without_context(process)


class CleanupHistoricalInverseTests(unittest.TestCase):
    def source_and_contract(self):
        import json
        import test_native_async_fixture as history
        source = (history.REPOSITORY / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        source = history.without_tree_unload_measurement(source, host=True)
        contract = json.loads((history.REPOSITORY / 'tests/child_cleanup_source_inverse.json').read_text(encoding='utf-8'))
        return history, source, contract

    def test_inverse_restores_exact_public_host_before_existing_history(self):
        import hashlib
        history, source, contract = self.source_and_contract()
        restored = history.without_child_cleanup(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), contract['base_sha256'])
        self.assertEqual(contract['base_commit'], '6851ebbf177b2bde5655c074dbbbffd7e28185e3')
        self.assertNotIn('def _finish_child(', restored)
        self.assertNotIn('CHILD_CLEANUP_SECONDS =', restored)
        historical = history.without_tree_find_measurement(source, host=True)
        self.assertNotEqual(historical, restored)

    def test_inverse_rejects_drift_without_normalization(self):
        history, source, _ = self.source_and_contract()
        for changed in (source+'\n', source.replace('\n', '\r\n'),
                        source.replace('CHILD_CLEANUP_SECONDS = 5', 'CHILD_CLEANUP_SECONDS = 6')):
            with self.subTest(size=len(changed)), self.assertRaises(AssertionError):
                history.without_child_cleanup(changed)

    def test_outer_hash_change_cannot_hide_changed_block_or_suffix(self):
        import copy
        import hashlib
        history, source, contract = self.source_and_contract()
        for changed in (source+'\n', source.replace('CHILD_CLEANUP_SECONDS = 5', 'CHILD_CLEANUP_SECONDS = 6')):
            forged = copy.deepcopy(contract)
            forged['candidate_sha256'] = hashlib.sha256(changed.encode()).hexdigest()
            with mock.patch.object(history.json, 'loads', return_value=forged), self.assertRaises(AssertionError):
                history.without_child_cleanup(changed)


if __name__ == "__main__":
    unittest.main()
