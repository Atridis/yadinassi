"""Finite failure-only observations. Synthetic fixtures never prove native semantics."""
from __future__ import annotations

import copy
import itertools
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import test_native_async_execution as execution
import test_native_async_protocol as protocol

suite, host = protocol.suite, protocol.full
NONCE = protocol.NONCE


def install_windows_offline_reader(test, *, windows=None):
    """Only trusted offline fixtures use the existing Windows read adapter."""
    if windows is None:
        windows = os.name == 'nt'
    if windows:
        reader = mock.patch.object(suite, 'secure_bytes',
            new=execution.probe.stage_fixture.portable_fixture_bytes)
        reader.start()
        test.addCleanup(reader.stop)


def failed_record(diagnostic=None):
    result = suite.empty_async_report()
    result.update(status='failed', failure_kind='timeout', template_sha256=protocol.H,
                  failure_diagnostics=diagnostic)
    result['cases'][0] = [0, 2, 10, protocol.MODULES[0], 0, [], [], []]
    return result


class AsyncFailureProtocolTests(unittest.TestCase):
    def accept(self, value):
        before = copy.deepcopy(value)
        self.assertEqual(suite.validate_async_report(value, protocol.H, protocol.MODULES), before)
        self.assertEqual(host.validate_client_async(value, protocol.H, protocol.MODULES), before)
        self.assertEqual(host.decode_async_wire(suite.encode_async_wire(value)), before)
        self.assertEqual(suite.decode_async_wire(host.encode_async_wire(value)), before)
        self.assertEqual(value, before)

    def reject(self, value):
        with self.assertRaises(suite.FullError):
            suite.validate_async_report(value, protocol.H, protocol.MODULES)
        with self.assertRaises(ValueError):
            host.validate_client_async(value, protocol.H, protocol.MODULES)

    def test_every_enum_combination_agrees_between_independent_validators(self):
        self.accept(failed_record())
        for stage, entered, completed, category in itertools.product(range(6), range(4), range(4), range(31)):
            valid = ((stage >= 3 or entered == completed == 0)
                     and (stage != 0 or category == 0)
                     and (category < 13 or stage >= 3)
                     and (completed != 3 or entered == 3))
            value = failed_record([stage, entered, completed, category])
            (self.accept if valid else self.reject)(value)

    def test_exact_types_lengths_bounds_missing_and_extra_keys(self):
        for malformed in ({}, (), (), '', True, 0, [], [3, 3, 3], [3, 3, 3, 3, 0]):
            self.reject(failed_record(malformed))
        for index, maximum in enumerate((5, 3, 3, 30)):
            for item in (True, False, None, '0', 0.0, -1, maximum + 1, [], {}):
                value = [3, 3, 3, 3]
                value[index] = item
                self.reject(failed_record(value))
        value = failed_record()
        del value['failure_diagnostics']
        self.reject(value)
        for codec in (suite.encode_async_wire, suite.decode_async_wire, host.encode_async_wire, host.decode_async_wire):
            with self.assertRaises((suite.FullError, ValueError)):
                codec(value)
        value = failed_record()
        value['raw_failure'] = 'PRIVATE'
        self.reject(value)

    def test_failure_applicability_never_adds_row_proof_or_success(self):
        value = suite.empty_async_report()
        value['failure_diagnostics'] = [0, 0, 0, 0]
        self.reject(value)
        value = protocol.record()
        value['failure_diagnostics'] = [3, 3, 3, 17]
        self.reject(value)
        for mutate in (lambda v: v['cases'][0].__setitem__(4, 63),
                       lambda v: v['cases'][0].__setitem__(5, [0]),
                       lambda v: v.update(continuity_sha256=protocol.H)):
            value = failed_record([3, 3, 3, 17])
            mutate(value)
            self.reject(value)
        value = failed_record([4, 3, 3, 3])
        value.update(status='inconclusive', failure_kind='unsupported_observation')
        value['cases'][0][1:3] = [3, 14]
        self.accept(value)

    def test_legacy_wire_schemas_cannot_gain_async_record(self):
        for schema in (1, 2, 3):
            value = suite.empty_report(NONCE)
            value.update(schema=schema, client_async=failed_record([3, 1, 1, 3]))
            with self.assertRaises(suite.FullError):
                suite.decode_stage_wire(value)


class AsyncFailureObservationTests(unittest.TestCase):
    def setUp(self):
        install_windows_offline_reader(self)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.request = self.root / 'request.json'
        self.request.write_bytes(b'{"schema":1}')
        self.request_snap = suite.async_file_snapshot(self.request, 2048)
        self.entered = self.root / 'entered.json'
        self.completed = self.root / 'completed.json'
        self.native_log = self.root / 'enterprise.log'
        self.console = self.root / 'enterprise-console.log'
        self.previous = {}

    def marker(self, phase):
        result = dict(schema=1, nonce=NONCE, case=0, phase=phase, witness='client')
        if phase == 'completed':
            result.update(status=2, failure=12, trace=[], values=[], errors=[])
        return result

    def write(self, phase, value=None):
        path = self.entered if phase == 'entered' else self.completed
        path.write_text(json.dumps(self.marker(phase) if value is None else value))
        return path

    def capture(self, *, stopped=True, stage=3):
        return suite.async_failure_observation(stage, 0, NONCE, stopped=stopped,
            marker_context=(self.entered, self.completed, self.request, self.request_snap, self.previous),
            log_context=((self.native_log, self.console), self.request, self.request_snap, 2048))

    def test_stop_gate_absence_validity_and_completed_dependency(self):
        with mock.patch.object(suite, 'async_diagnostic_snapshot', side_effect=AssertionError('read before stop')):
            self.assertEqual(self.capture(stopped=False), [3, 0, 0, 0])
        self.assertEqual(self.capture(), [3, 1, 1, 1])
        self.write('completed')
        self.assertEqual(self.capture()[1:3], [1, 2])
        self.write('entered')
        self.write('completed')
        self.assertEqual(self.capture(), [3, 3, 3, 1])

    def test_malformed_stale_nonce_case_witness_and_bom_are_never_valid(self):
        self.write('entered')
        good = json.dumps(self.marker('completed')).encode()
        bad = [b'', b'[]', b'null', b'\xff', good + b'PRIVATE', good[:-1], b'\xef\xbb\xbf' + good,
               good.replace(b'"schema": 1', b'"schema": 1, "schema": 1'),
               b' ' * (suite.ASYNC_MAX_MARKER + 1)]
        for key, item in (('nonce', 'b' * 32), ('case', 7), ('witness', 'server'),
                          ('phase', 'entered'), ('schema', True), ('extra', 'PRIVATE')):
            value = self.marker('completed')
            value[key] = item
            bad.append(json.dumps(value).encode())
        for raw in bad:
            self.completed.write_bytes(raw)
            self.assertEqual(self.capture()[2], 2, raw[:50])
        self.write('completed')
        os.utime(self.completed, ns=(1, 1))
        self.assertEqual(self.capture()[2], 2)

    @unittest.skipUnless(os.name == 'posix', 'POSIX secure files')
    def test_symlink_hardlink_fifo_directory_and_symlink_parent_invalid(self):
        self.write('entered')
        target = self.root / 'target'
        target.write_text(json.dumps(self.marker('completed')))
        self.completed.symlink_to(target)
        self.assertEqual(self.capture()[2], 2)
        self.completed.unlink()
        os.link(target, self.completed)
        self.assertEqual(self.capture()[2], 2)
        self.completed.unlink()
        os.mkfifo(self.completed)
        self.assertEqual(self.capture()[2], 2)
        self.completed.unlink()
        self.completed.mkdir()
        self.assertEqual(self.capture()[2], 2)
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(suite.FullError):
            suite.async_diagnostic_snapshot(alias / 'missing.json', 100)

    def test_previous_marker_and_request_snapshots_cannot_be_rebased(self):
        self.write('entered')
        self.write('completed')
        self.previous['entered'] = suite.async_file_snapshot(self.entered, suite.ASYNC_MAX_MARKER)
        swapped = self.root / 'swap'
        swapped.write_bytes(self.entered.read_bytes())
        swapped.replace(self.entered)
        self.assertEqual(self.capture()[1:3], [2, 2])
        self.previous.clear()
        swapped.write_bytes(self.request.read_bytes())
        swapped.replace(self.request)
        self.native_log.write_bytes(b'ASYNC-ENTRY-FAILURE:root')
        self.assertEqual(self.capture()[1:], [2, 2, 2])

    def test_anchor_replaced_during_classification_invalidates_markers_and_log(self):
        self.write('entered')
        self.write('completed')
        self.native_log.write_bytes(b'ASYNC-ENTRY-FAILURE:root')
        import diagnostics
        original = diagnostics.summarize_text
        def replace(text):
            swapped = self.root / 'swap'
            swapped.write_bytes(self.request.read_bytes())
            swapped.replace(self.request)
            return original(text)
        with mock.patch.object(diagnostics, 'summarize_text', side_effect=replace):
            self.assertEqual(self.capture()[1:], [2, 2, 2])

    def test_future_anchor_cannot_make_current_files_fresh(self):
        future = time.time_ns() + 60_000_000_000
        os.utime(self.request, ns=(future, future))
        self.request_snap = suite.async_file_snapshot(self.request, 2048)
        self.write('entered')
        self.write('completed')
        self.native_log.write_bytes(b'ASYNC-ENTRY-FAILURE:root')
        self.assertEqual(self.capture()[1:], [2, 2, 2])

    def test_marker_and_log_on_different_device_are_invalid(self):
        self.write('entered')
        self.write('completed')
        self.native_log.write_bytes(b'ASYNC-ENTRY-FAILURE:root')
        original = suite.async_diagnostic_snapshot
        def different_device(*args, **kwargs):
            value = original(*args, **kwargs)
            if value is None:
                return None
            signature, data = value
            return (signature[0] + 1, *signature[1:]), data
        with mock.patch.object(suite, 'async_diagnostic_snapshot', side_effect=different_device):
            self.assertEqual(self.capture()[1:], [2, 2, 2])

    def test_same_bytes_replacement_during_marker_validation_invalidates(self):
        self.write('entered')
        self.write('completed')
        original = suite.validate_async_marker
        def replace(value, nonce, case, phase):
            result = original(value, nonce, case, phase)
            if phase == 'entered':
                swapped = self.root / 'swap'
                swapped.write_bytes(self.entered.read_bytes())
                swapped.replace(self.entered)
            return result
        with mock.patch.object(suite, 'validate_async_marker', side_effect=replace):
            self.assertEqual(self.capture()[1:3], [2, 2])

    def test_absent_marker_created_during_log_classification_invalidates(self):
        self.native_log.write_bytes(b'unknown PRIVATE text')
        import diagnostics
        original = diagnostics.summarize_text
        def create(text):
            self.write('entered')
            return original(text)
        with mock.patch.object(diagnostics, 'summarize_text', side_effect=create):
            self.assertEqual(self.capture()[1], 2)

    def test_exact_entry_labels_finite_generic_categories_and_conflicts(self):
        for label, code in suite.ASYNC_ENTRY_LOG_MARKERS.items():
            self.native_log.write_bytes((label + '\n').encode())
            self.assertEqual(self.capture()[3], code)
        for text, code in (('syntax error SECRET /private', 4), ('runtime error', 5),
                           ('method object field not found', 6), ('permission denied', 7),
                           ('authentication failed', 8), ('license not found', 9),
                           ('training version limitation', 10), ('application startup error', 11),
                           ('unknown PRIVATE text', 3), ('syntax error\npermission denied', 12),
                           ('ASYNC-ENTRY-FAILURE:root\nASYNC-ENTRY-FAILURE:witness', 12),
                           ('ASYNC-ENTRY-FAILURE:root\nsyntax error', 12),
                           ('ASYNC-ENTRY-FAILURE:unknown', 2), ('prefix ASYNC-ENTRY-FAILURE:root', 2),
                           ('ASYNC-ENTRY-FAILURE:root suffix PRIVATE', 2)):
            self.native_log.write_bytes(text.encode())
            self.assertEqual(self.capture()[3], code, text)
            self.assertNotIn('PRIVATE', json.dumps(self.capture()))
        self.native_log.write_bytes(b'ASYNC-ENTRY-FAILURE:root')
        self.assertEqual(self.capture(stage=1)[3], 2)

    def test_log_late_same_bytes_replacement_invalidates_category(self):
        self.native_log.write_bytes(b'ASYNC-ENTRY-FAILURE:root')
        import diagnostics
        original = diagnostics.summarize_text
        def replace(text):
            swapped = self.root / 'swap'
            swapped.write_bytes(self.native_log.read_bytes())
            swapped.replace(self.native_log)
            return original(text)
        with mock.patch.object(diagnostics, 'summarize_text', side_effect=replace):
            self.assertEqual(self.capture()[3], 2)

    def test_final_emitter_preserves_historical_observation_without_rebasing(self):
        diagnostic = self.capture()
        self.write('entered')
        self.write('completed')
        stage = suite.empty_report(NONCE, client_probe=True, client_async=True)
        stage.update(status='failed', failure_kind='timeout', client_async=failed_record(diagnostic))
        report = {'status': 'stage3_failed', 'stage3': stage}
        with mock.patch.object(suite, 'async_diagnostic_snapshot', side_effect=AssertionError('late rebase')):
            raw = suite.build_envelope(report, NONCE, self.root, quiet=True)
        emitted = json.loads(raw)['report']['stage3']['client_async']
        self.assertEqual(emitted['failure_diagnostics'], [3, 1, 1, 1])
        self.assertEqual(emitted['cases'][0][4:], [0, [], [], []])
        self.assertIsNone(emitted['continuity_sha256'])


class AsyncFailureExecutionTests(execution.AsyncExecutionTests):
    def fake_async(self, *args, **kwargs):
        try:
            return super().fake_async(*args, **kwargs)
        except suite.FullError as error:
            # The offline fake has no child process; explicitly model completed stop.
            error.async_process_stopped = True
            raise

    def test_actual_host_operation_not_inferred_from_empty_row(self):
        def fail_build(mode, directory):
            if mode == 'build':
                raise suite.FullError('timeout')
        self.hook = fail_build
        self.assertEqual(self.run_async()['failure_diagnostics'], [1, 0, 0, 3])
        self.reset()
        def fail_dump(mode, directory):
            if mode == 'dump':
                raise suite.FullError('process_failed')
        self.hook = fail_dump
        self.assertEqual(self.run_async()['failure_diagnostics'], [2, 0, 0, 3])
        self.reset()
        self.hook = None
        self.only_entered = True
        self.failure = 'timeout'
        record = self.run_async()
        self.assertEqual(record['failure_diagnostics'], [3, 3, 1, 3])
        self.assertEqual(record['failure_kind'], 'timeout')
        self.assertEqual(record['cases'][0][4:], [0, [], [], []])
        self.assertIsNone(record['continuity_sha256'])
        self.reset()
        self.failure = None
        self.assertEqual(self.run_async()['failure_diagnostics'], [4, 3, 1, 3])
        self.reset()
        self.only_entered = False
        def mutate_source(mode, directory):
            if mode == 'enterprise' and directory.name == 'case-7':
                target = directory / 'src' / suite.CLIENT_MODULE
                target.write_bytes(target.read_bytes() + b'\n')
        self.hook = mutate_source
        record = self.run_async()
        self.assertEqual(record['failure_kind'], 'stale_evidence')
        self.assertEqual(record['failure_diagnostics'], [5, 3, 3, 3])

    def test_success_unreached_and_external_checkpoint_have_null_diagnostics(self):
        self.assertIsNone(suite.empty_async_report()['failure_diagnostics'])
        value = self.run_async()
        self.assertEqual(value['status'], 'ok')
        self.assertIsNone(value['failure_diagnostics'])
        suite.fail_async_process_checkpoint(value)
        self.assertIsNone(value['failure_diagnostics'])
        self.reset()
        self.work.mkdir()
        self.assertEqual(self.run_async()['failure_diagnostics'], [0, 0, 0, 0])

    def test_original_timeout_survives_failed_postexit_census(self):
        self.failure = 'timeout'
        with mock.patch.object(suite, 'client_process_snapshot', side_effect=suite.FullError('process_failed')):
            value = self.run_async()
        self.assertEqual(value['failure_kind'], 'timeout')
        self.assertEqual(value['failure_diagnostics'][0], 3)

    def test_unconfirmed_stop_never_reads_markers_or_log(self):
        def unconfirmed(*args, **kwargs):
            raise suite.FullError('timeout')
        with mock.patch.object(suite, 'run_async_process', side_effect=unconfirmed), \
             mock.patch.object(suite, 'async_diagnostic_snapshot', side_effect=AssertionError('unconfirmed stop read')):
            value = self.run_async()
        self.assertEqual(value['failure_diagnostics'], [1, 0, 0, 0])

    def test_roundtrip_directory_failure_does_not_reuse_build_log(self):
        original = Path.mkdir
        def fail_roundtrip(path, *args, **kwargs):
            if path.name == 'roundtrip':
                raise OSError('PRIVATE mkdir failure')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'mkdir', new=fail_roundtrip):
            value = self.run_async()
        self.assertEqual(self.events, ['build'])
        self.assertEqual(value['failure_kind'], 'artifact_missing')
        self.assertEqual(value['failure_diagnostics'], [2, 0, 0, 0])


class AsyncProcessFailureTests(unittest.TestCase):
    def test_timeout_preserves_original_kind_and_records_stop_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = mock.MagicMock()
            child.__enter__.return_value = child
            child.wait.side_effect = subprocess.TimeoutExpired(['native'], 1)
            for index, stop_failure in enumerate((False, True)):
                with mock.patch.object(suite.subprocess, 'Popen', return_value=child), \
                     mock.patch.object(suite, 'os', new=SimpleNamespace(name='posix')), \
                     mock.patch.object(suite, '_stop_group', side_effect=suite.FullError('process_failed') if stop_failure else None):
                    with self.assertRaises(suite.FullError) as caught:
                        suite.run_async_process(['native'], root, root / ('console-' + str(index)), 1, require_clean_tree=True)
                self.assertEqual(caught.exception.kind, 'timeout')
                self.assertIs(caught.exception.async_process_stopped, not stop_failure)


class AsyncOfflineAdapterTests(unittest.TestCase):
    def test_forced_windows_adapter_preserves_assertions_and_restores_reader(self):
        original = suite.secure_bytes
        fixture = AsyncFailureObservationTests('test_stop_gate_absence_validity_and_completed_dependency')
        install_windows_offline_reader(fixture, windows=True)
        try:
            fixture.setUp()
            self.assertIs(suite.secure_bytes, execution.probe.stage_fixture.portable_fixture_bytes)
            fixture.test_stop_gate_absence_validity_and_completed_dependency()
        finally:
            fixture.doCleanups()
        self.assertIs(suite.secure_bytes, original)

    def test_non_windows_setup_keeps_real_reader(self):
        original = suite.secure_bytes
        fixture = unittest.TestCase()
        install_windows_offline_reader(fixture, windows=False)
        try:
            self.assertIs(suite.secure_bytes, original)
        finally:
            fixture.doCleanups()
        self.assertIs(suite.secure_bytes, original)


class AsyncFilesystemClockTests(unittest.TestCase):
    def test_freshness_equality_each_timestamp_and_device_are_independent_gates(self):
        anchor = ((7, 1, 0, 1, 1, 100, 110), b'anchor')
        for device, mtime, ctime, expected in (
                (7, 110, 110, True), (7, 111, 112, True),
                (7, 109, 110, False), (7, 110, 109, False),
                (8, 110, 110, False)):
            observed = ((device, 2, 0, 1, 1, mtime, ctime), b'observed')
            self.assertIs(suite.async_diagnostic_after(observed, anchor), expected)
        future = ((7, 1, 0, 1, 1, 1000, 110), b'anchor')
        observed = ((7, 2, 0, 1, 1, 110, 110), b'observed')
        self.assertFalse(suite.async_diagnostic_after(observed, future))

    def test_coarse_filesystem_ticks_and_ahead_wall_clock_preserve_all_five_ci_cases(self):
        # Model coarse inode timestamps only AFTER the real secure reader has
        # checked type, identity, size and bytes; never substitute native proof.
        original = suite.async_file_snapshot
        real_time_ns = time.time_ns
        names = (
            (AsyncFailureExecutionTests, 'test_actual_host_operation_not_inferred_from_empty_row'),
            (AsyncFailureObservationTests, 'test_absent_marker_created_during_log_classification_invalidates'),
            (AsyncFailureObservationTests, 'test_exact_entry_labels_finite_generic_categories_and_conflicts'),
            (AsyncFailureObservationTests, 'test_stop_gate_absence_validity_and_completed_dependency'),
            (AsyncOfflineAdapterTests, 'test_forced_windows_adapter_preserves_assertions_and_restores_reader'),
            (AsyncFailureObservationTests, 'test_malformed_stale_nonce_case_witness_and_bom_are_never_valid'),
            (AsyncFailureObservationTests, 'test_previous_marker_and_request_snapshots_cannot_be_rebased'),
            (AsyncFailureObservationTests, 'test_same_bytes_replacement_during_marker_validation_invalidates'),
        )
        for quantum in (1, 10_000_000, 1_000_000_000):
            def coarse(*args, **kwargs):
                signature, data = original(*args, **kwargs)
                signature = (*signature[:5], *(value // quantum * quantum for value in signature[5:7]))
                return signature, data
            result = unittest.TestResult()
            tests = unittest.TestSuite(case(name) for case, name in names)
            with self.subTest(quantum=quantum), \
                 mock.patch.object(suite, 'async_file_snapshot', side_effect=coarse), \
                 mock.patch.object(suite.time, 'time_ns', side_effect=lambda: real_time_ns() + 10_000_000_000):
                tests.run(result)
                self.assertEqual(result.testsRun, len(names))
                self.assertEqual(result.failures, [])
                self.assertEqual(result.errors, [])


if __name__ == '__main__':
    unittest.main()
