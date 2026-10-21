"""Offline stage-three plumbing tests; fake bytes are not native 1C evidence."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

REPOSITORY = Path(__file__).resolve().parents[1]
HELPERS = REPOSITORY / 'scripts/native_1c_bootstrap'
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))
import full_suite as suite

NONCE = '0123456789abcdef0123456789abcdef'
MESSAGES = ['first\r\nline', '', ' Привет\rworld ', '\\n\\r']


def load_launcher(path):
    spec = importlib.util.spec_from_file_location('native_full_test_launcher', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def portable_fixture_bytes(path: Path, limit: int, *, allow_empty: bool = False) -> bytes:
    """Read trusted offline fixtures, not native-container security evidence.

    Windows host files do not promise the Linux descriptor/path metadata
    equivalence required by secure_bytes. Keep that production gate unchanged;
    Windows orchestration tests use this explicit bounded fixture adapter. Real
    no-follow descriptor behavior remains covered by SecureEvidenceTests on
    POSIX, including links, special files, hard links and concurrent mutation.
    """
    try:
        if any(item.is_symlink() for item in (path, *path.parents)):
            raise suite.FullError('artifact_missing')
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not (0 if allow_empty else 1) <= before.st_size <= limit):
            raise suite.FullError('artifact_missing')
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
        after = path.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode,
                                  value.st_nlink, value.st_size,
                                  value.st_mtime_ns, value.st_ctime_ns)
        if (identity(before) != identity(after) or len(data) != before.st_size
                or len(data) > limit):
            raise suite.FullError('artifact_missing')
        return data
    except (OSError, ValueError, OverflowError):
        raise suite.FullError('artifact_missing') from None


class StrictResultTests(unittest.TestCase):
    def test_complete_result_matches_unchanged_launcher_serialization(self):
        data = json.dumps({'messages': MESSAGES, 'error': ''}).encode()
        self.assertEqual(suite.parse_native_result(data), (MESSAGES, ''))
        self.assertEqual(suite.serialize_messages(MESSAGES), b'first\nline\n\n \xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82\nworld \n\\n\\r\n')
        launcher = load_launcher(REPOSITORY / 'integrational_tests/test_launcher.py')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'sample.out'
            launcher.write_output(output, MESSAGES)
            self.assertEqual(output.read_bytes(), suite.serialize_messages(MESSAGES))

    def test_strict_invalid_results(self):
        invalid = [
            b'{"messages":[],"messages":[],"error":""}',
            b'{"messages":[],"error":"","other":0}',
            b'{"messages":[],"error":"native private details"}',
            b'{"messages":[],"error":false}', b'{"messages":[],"error":0}',
            b'{"messages":null,"error":""}', b'{"messages":[1],"error":""}',
            b'{"messages":[true],"error":""}', b'{"messages":[[]],"error":""}',
            b'{"messages":[NaN],"error":""}', b'{"messages":[Infinity],"error":""}',
            b'{"messages":[1.5],"error":""}', b'{"messages":[1234567890123],"error":""}',
            b'{"messages":["\\ud800"],"error":""}', b'{"messages":["\xff"],"error":""}',
            b'{"messages":[],"error":""} trailing', b'{"messages":[],"error":""',
            b'[]', b'null', b'[' * 1000 + b']' * 1000,
        ]
        for raw in invalid:
            with self.subTest(raw=raw[:70]), self.assertRaises(suite.FullError) as caught:
                suite.parse_native_result(raw)
            self.assertEqual(str(caught.exception), 'invalid_result')

    def test_size_message_count_and_aggregate_limits(self):
        for value in ({'messages': [''] * (suite.MAX_MESSAGES + 1), 'error': ''},
                      {'messages': ['x' * suite.MAX_OUTPUT], 'error': ''},
                      {'messages': ['я' * suite.MAX_OUTPUT], 'error': ''}):
            with self.assertRaises(suite.FullError):
                suite.parse_native_result(json.dumps(value, ensure_ascii=False).encode('utf-8'))
        with self.assertRaises(suite.FullError):
            suite.parse_native_result(b' ' * (suite.MAX_RESULT + 1))
        self.assertEqual(suite.parse_native_result(b'{"messages":[],"error":""}'), ([], ''))

    def test_module_matches_actual_launcher_utf8_bom_and_universal_newlines(self):
        for raw in (b'first\r\nsecond\rthird\n', b'\xef\xbb\xbfline\r\n', 'Сообщить(1);\n'.encode()):
            with tempfile.TemporaryDirectory() as directory:
                source, generated = Path(directory) / 'source', Path(directory) / 'module'
                source.write_bytes(raw)
                generated.write_text(source.read_text(encoding='utf-8-sig'), encoding='utf-8-sig', newline='\n')
                self.assertEqual(generated.read_bytes(), suite.generated_module(raw))
        with self.assertRaises(suite.FullError):
            suite.generated_module(b'\xff')


class SecureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.file = self.root / 'data'
        self.file.write_bytes(b'abc')

    def test_finite_regular_file_empty_and_size(self):
        self.assertEqual(suite.secure_bytes(self.file, 3), b'abc')
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(self.file, 2)
        self.file.write_bytes(b'')
        self.assertEqual(suite.secure_bytes(self.file, 3, allow_empty=True), b'')
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(self.file, 3)
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(self.root, 3)

    @unittest.skipUnless(os.name == 'posix', 'Linux no-follow descriptor boundary')
    def test_links_parent_links_fifo_and_hardlinks_rejected(self):
        link = self.root / 'link'
        link.symlink_to(self.file)
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(link, 3)
        parent = self.root / 'parent'
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(parent / 'data', 3)
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(fifo, 3)
        os.link(self.file, self.root / 'hard')
        with self.assertRaises(suite.FullError):
            suite.secure_bytes(self.file, 3)

    def test_mutation_during_descriptor_read_is_rejected(self):
        original = os.read
        def read(descriptor, count):
            data = original(descriptor, count)
            self.file.write_bytes(b'changed')
            return data
        with mock.patch.object(suite.os, 'read', side_effect=read), self.assertRaises(suite.FullError):
            suite.secure_bytes(self.file, 100)

    def test_absent_rejects_preexisting_empty_file(self):
        self.file.write_bytes(b'')
        with self.assertRaises(suite.FullError):
            suite.absent(self.file)


class FullSuiteHarness(unittest.TestCase):
    use_fixture_reader = os.name == 'nt'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.inputs = self.root / 'inputs'
        if self.use_fixture_reader:
            reader_patcher = mock.patch.object(suite, 'secure_bytes', new=portable_fixture_bytes)
            reader_patcher.start()
            self.addCleanup(reader_patcher.stop)
        for source, target in suite.INPUT_FILES.items():
            path = self.inputs / target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPOSITORY / source, path)
        # Production runs Linux only. Exercise its exact file newline behavior
        # even when these process-free tests run in the Windows Python matrix.
        original_write = Path.write_text
        def linux_module_write(path, text, *args, **kwargs):
            if kwargs.get('encoding') == 'utf-8-sig':
                kwargs['newline'] = '\n'
            return original_write(path, text, *args, **kwargs)
        newline_patcher = mock.patch.object(Path, 'write_text', new=linux_module_write)
        newline_patcher.start()
        self.addCleanup(newline_patcher.stop)
        self.launcher = load_launcher(self.inputs / 'launcher/test_launcher.py')
        self.platform = self.launcher.Platform(Path('/approved/1cv8t'), self.root / 'db', 120, 'NativeSmoke')
        self.epf = self.root / 'Launcher.epf'
        self.epf.write_bytes(b'offline fake compiled launcher')
        self.work = self.root / ('stage3-' + NONCE)
        self.events = []
        self.failure = None
        self.result_overrides = {}
        self.output_override = None
        self.native_hook = None
        patcher = mock.patch.object(suite, 'run_process', side_effect=self.native)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('Never launch native processes in offline tests'))
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def argument(command, flag):
        return command[command.index(flag) + 1]

    def native(self, command, directory, log, timeout):
        name = directory.name.removesuffix('-case')
        mode = 'build' if '/DumpResult' in command else 'enterprise'
        self.events.append((name, mode))
        self.assertIn(name, suite.SCENARIOS)
        self.assertEqual(timeout, 120)
        self.assertEqual(self.argument(command, '/N'), 'NativeSmoke')
        self.assertNotIn('/P', command)
        self.assertFalse(log.exists())
        log.write_bytes(b'private fake console')
        if self.failure == (name, mode):
            raise suite.FullError('process_failed')
        if mode == 'build':
            Path(self.argument(command, '/DumpResult')).write_bytes(b'0\n')
            index = command.index('/LoadExternalDataProcessorOrReportFromFiles')
            Path(command[index + 2]).write_bytes(b'fake native EPF')
        else:
            self.assertEqual(self.argument(command, '/VL'), 'ru_RU')
            self.assertIn('/RunModeManagedApplication', command)
            request = json.loads(Path(self.argument(command, '/C')).read_text(encoding='utf-8'))
            raw = self.result_overrides.get(name, json.dumps({'messages': MESSAGES, 'error': ''}).encode())
            Path(request['result']).write_bytes(raw)
        if self.native_hook:
            self.native_hook(name, mode, directory)

    def run_suite(self):
        return suite.run_suite(self.launcher, self.platform, self.epf, self.work, self.inputs, NONCE)

    def test_six_actual_launcher_cases_complete_identity_and_exact_input_hashes(self):
        original_reader, original_process, original_build = self.launcher.read_result, self.launcher.run_process, self.launcher.build_epf
        result = self.run_suite()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['failure_kind'], 'none')
        self.assertIsNone(result['failed_case'])
        self.assertEqual(result['nonce'], NONCE)
        self.assertEqual(len(result['input_sha256']), 23)
        self.assertEqual(self.events, [(name, mode) for name in suite.SCENARIOS for mode in ('build', 'enterprise')])
        for case in result['cases']:
            name = case['name']
            source = (self.inputs / f'scenarios/{name}.bsl').read_bytes()
            self.assertEqual(case, {'name': name, 'status': 'ok', 'source_sha256': suite.digest(source),
                                  'module_sha256': suite.digest(suite.generated_module(source)),
                                  'output_sha256': suite.digest(suite.serialize_messages(MESSAGES)),
                                  'output_size': len(suite.serialize_messages(MESSAGES)), 'message_count': len(MESSAGES)})
            self.assertEqual((self.work / (name + '.out')).read_bytes(), suite.serialize_messages(MESSAGES))
        self.assertIs(self.launcher.read_result, original_reader)
        self.assertIs(self.launcher.run_process, original_process)
        self.assertIs(self.launcher.build_epf, original_build)
        self.assertLess(len(json.dumps(result)), suite.MAX_STAGE_REPORT)

    def test_first_failure_stops_suffix_and_exports_no_partial_payload(self):
        self.failure = ('dates', 'enterprise')
        result = self.run_suite()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failed_case'], 'dates')
        self.assertEqual([case['status'] for case in result['cases']], ['ok', 'failed'] + ['not_started'] * 4)
        self.assertEqual(result['failure_kind'], 'process_failed')
        self.assertIsNone(result['cases'][1]['output_size'])
        report = {'status': 'stage3_failed', 'native_tests_completed': False, 'stage3': result}
        raw = suite.build_envelope(report, NONCE, self.work, quiet=True)
        self.assertEqual(json.loads(raw)['outputs'], [])
        self.assertNotIn(b'private fake', raw)
        self.assertNotIn(base64.b64encode(suite.serialize_messages(MESSAGES)), raw)

    def test_duplicate_keys_rejected_before_launcher_writes_output(self):
        self.result_overrides['collections'] = b'{"messages":[],"messages":["secret"],"error":""}'
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'invalid_result')
        self.assertFalse((self.work / 'collections.out').exists())
        self.assertEqual(self.events, [('collections', 'build'), ('collections', 'enterprise')])

    def test_error_and_extra_fields_rejected_before_output(self):
        for raw in (b'{"messages":["secret"],"error":"secret"}',
                    b'{"messages":["secret"],"error":"","other":"secret"}'):
            with self.subTest(raw=raw):
                self.result_overrides['collections'] = raw
                result = self.run_suite()
                self.assertEqual(result['failure_kind'], 'invalid_result')
                self.assertFalse((self.work / 'collections.out').exists())
                shutil.rmtree(self.work)

    def test_stale_root_and_missing_input_fail_before_any_case(self):
        self.work.mkdir()
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'stale_evidence')
        self.assertEqual(self.events, [])
        self.work.rmdir()
        (self.inputs / 'scenarios/dates.bsl').unlink()
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'artifact_missing')
        self.assertEqual(result['input_sha256'], {})
        self.assertEqual(self.events, [])

    def test_module_changed_after_compile_fails_identity(self):
        def change(name, mode, directory):
            if mode == 'build':
                (directory / 'src/TestModule/Ext/ObjectModule.bsl').write_bytes(b'changed')
        self.native_hook = change
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'module_mismatch')
        self.assertIsNone(result['cases'][0]['output_sha256'])

    def test_wrong_output_bytes_never_pass_even_when_result_is_valid(self):
        original = self.launcher.write_output
        def changed(path, messages):
            original(path, messages)
            path.write_bytes(path.read_bytes() + b' ')
        self.launcher.write_output = changed
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'output_mismatch')
        self.assertIsNone(result['cases'][0]['output_sha256'])

    def test_error_file_causes_failure_without_exporting_its_text(self):
        def error_file(name, mode, directory):
            if mode == 'enterprise':
                (self.work / (name + '.err')).write_text('secret diagnostics')
        self.native_hook = error_file
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'stale_evidence')
        self.assertNotIn('secret', json.dumps(result))

    def test_total_output_limit_fails_before_accepting_overflow_case(self):
        self.result_overrides = {name: json.dumps({'messages': ['x' * 400_000], 'error': ''}).encode() for name in suite.SCENARIOS}
        result = self.run_suite()
        self.assertEqual(result['failure_kind'], 'output_limit')
        self.assertEqual(result['failed_case'], 'values')
        self.assertIsNone(result['cases'][-1]['output_size'])

    def test_invalid_platform_never_runs(self):
        self.platform = self.launcher.Platform(Path('/approved'), self.root / 'db', 121, 'NativeSmoke')
        self.assertEqual(self.run_suite()['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_live_envelope_contains_only_exact_six_saved_outputs(self):
        result = self.run_suite()
        report = {'status': 'ok', 'native_tests_completed': True, 'stage3': result}
        raw = suite.build_envelope(report, NONCE, self.work, quiet=True)
        envelope = json.loads(raw)
        self.assertEqual(set(envelope), {'schema', 'nonce', 'report', 'outputs'})
        self.assertEqual(envelope['schema'], 'native-1c-full-v1')
        self.assertEqual([entry['name'] for entry in envelope['outputs']], [name + '.out' for name in suite.SCENARIOS])
        for entry in envelope['outputs']:
            data = (self.work / entry['name']).read_bytes()
            self.assertEqual(entry, {'name': entry['name'], 'size': len(data), 'sha256': suite.digest(data),
                                    'data_b64': base64.b64encode(data).decode('ascii')})
        self.assertLess(len(raw), suite.MAX_TRANSPORT)
        self.assertNotIn(b'private fake console', raw)

    def test_output_changes_or_live_native_process_suppress_entire_payload(self):
        for change in ('changed', 'quiet'):
            with self.subTest(change=change):
                result = self.run_suite()
                if change == 'changed':
                    (self.work / 'dates.out').write_bytes(b'tampered')
                report = {'status': 'ok', 'native_tests_completed': True, 'stage3': result}
                envelope = json.loads(suite.build_envelope(report, NONCE, self.work, quiet=change != 'quiet'))
                self.assertEqual(envelope['outputs'], [])
                self.assertEqual(envelope['report']['stage3']['failure_kind'], 'export_failed')
                self.assertFalse(envelope['report']['native_tests_completed'])
                shutil.rmtree(self.work)

    def test_real_producer_and_host_validator_agree_success_and_export_failure(self):
        from tests.test_native_1c_smoke import smoke, bootstrap_report
        result = self.run_suite()
        modules = {name: suite.digest(suite.generated_module(
            (self.inputs / f'scenarios/{name}.bsl').read_bytes())) for name in suite.SCENARIOS}
        self.assertEqual(suite.INPUT_FILES, smoke.FULL_STAGED_FILES)
        for quiet in (True, False):
            report = bootstrap_report()
            report.update(stage3=result, native_tests_completed=True)
            raw = suite.build_envelope(report, NONCE, self.work, quiet=quiet)
            verified, outputs = smoke.FULL.validate_envelope(
                raw, NONCE, result['input_sha256'], modules, smoke.validate_report)
            self.assertEqual(bool(outputs), quiet)
            self.assertEqual(verified['native_tests_completed'], quiet)

    def test_stage_report_is_exclusive_and_finite(self):
        result = self.run_suite()
        path = self.root / 'report.json'
        suite.write_report(path, result)
        self.assertEqual(json.loads(path.read_bytes()), result)
        with self.assertRaises(FileExistsError):
            suite.write_report(path, result)
        with self.assertRaises(suite.FullError):
            suite.write_report(self.root / 'too-large.json', {'large': 'x' * suite.MAX_STAGE_REPORT})


class PortableFixtureFullSuiteHarness(FullSuiteHarness):
    """Exercise the Windows test adapter in every CI OS, without native calls."""
    use_fixture_reader = True


class PortableFixtureReaderTests(SecureEvidenceTests):
    """Run the same finite-file/link contracts against the test-only adapter."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(suite, 'secure_bytes', new=portable_fixture_bytes)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mutation_during_descriptor_read_is_rejected(self):
        # The adapter intentionally uses a portable Python file reader, while
        # the inherited original test exercises os.read in the Linux gate.
        original = Path.open
        path = self.file
        class MutatingReader:
            def __enter__(self):
                self.stream = original(path, 'rb')
                return self
            def read(self, count):
                data = self.stream.read(count)
                with original(path, 'wb') as target:
                    target.write(b'changed')
                return data
            def __exit__(self, *args):
                self.stream.close()
        with mock.patch.object(Path, 'open', return_value=MutatingReader()), self.assertRaises(suite.FullError):
            suite.secure_bytes(self.file, 100)


class FixtureBoundaryIsolationTests(unittest.TestCase):
    def test_production_still_rejects_descriptor_path_metadata_disagreement(self):
        # Simulate an OS-specific descriptor/path disagreement explicitly. This
        # is a contract test, not a claim about a particular Windows stat field.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'fixture'
            path.write_bytes(b'bounded fixture')
            original = os.fstat
            fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size',
                      'st_mtime_ns', 'st_ctime_ns')
            def descriptor_view(fd):
                value = original(fd)
                values = {name: getattr(value, name) for name in fields}
                values['st_mode'] ^= stat.S_IXUSR
                return SimpleNamespace(**values)
            with mock.patch.object(suite.os, 'fstat', side_effect=descriptor_view):
                with self.assertRaises(suite.FullError):
                    suite.secure_bytes(path, 100)
                self.assertEqual(portable_fixture_bytes(path, 100), b'bounded fixture')


class Stage3IntegrationTests(unittest.TestCase):
    def test_full_arguments_are_fixed_and_nonce_is_strict(self):
        spec = importlib.util.spec_from_file_location('native_full_stage_controller', HELPERS / 'run_stage.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        for args in (['--full-suite'], ['--full-suite', '--invocation-nonce', '../x'],
                     ['--full-suite', '--invocation-nonce', 'A' * 32],
                     ['--full-suite', '--invocation-nonce', NONCE, '--other']):
            with self.subTest(args=args), mock.patch.object(controller, 'run') as run:
                self.assertEqual(controller.main(args), 2)
                run.assert_not_called()

    def test_probe_keeps_legacy_branch_and_emits_payload_before_exit_not_docker_cp(self):
        text = (REPOSITORY / 'scripts/native_1c_smoke_probe.sh').read_text()
        self.assertIn('"$1" = --bootstrap-simple-epf', text)
        self.assertIn('"$1" = --full-suite', text)
        self.assertIn('full_suite.build_envelope(', text)
        self.assertIn('full_suite.native_processes_quiet(', text)
        self.assertIn('sys.stdout.buffer.write(raw)', text)
        self.assertNotIn('docker cp', text)
        self.assertNotIn('tee ', text)


@unittest.skipUnless(os.name == 'posix', 'Linux native process groups')
class ProcessBoundaryTests(unittest.TestCase):
    def test_process_waits_at_120_seconds_and_reaps_group_after_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = mock.MagicMock()
            child.pid = 456
            child.wait.return_value = 0
            child.__enter__.return_value = child
            with mock.patch.object(suite.subprocess, 'Popen', return_value=child) as popen, \
                 mock.patch.object(suite.os, 'killpg', side_effect=[None, ProcessLookupError()]):
                suite.run_process(['native'], root, root / 'console', 120)
            child.wait.assert_any_call(timeout=120)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertGreaterEqual(child.wait.call_count, 2)

    def test_timeout_terminates_group_and_never_exposes_exception_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = mock.MagicMock()
            child.pid = 456
            child.wait.side_effect = [subprocess.TimeoutExpired('secret', 120), 0]
            child.__enter__.return_value = child
            with mock.patch.object(suite.subprocess, 'Popen', return_value=child), \
                 mock.patch.object(suite.os, 'killpg', side_effect=[None, ProcessLookupError()]), \
                 self.assertRaises(suite.FullError) as caught:
                suite.run_process(['native'], root, root / 'console', 120)
            self.assertEqual(str(caught.exception), 'timeout')
            self.assertEqual(child.wait.call_count, 2)

    def test_group_disappearance_wait_is_bounded(self):
        child = mock.MagicMock()
        child.pid = 456
        with mock.patch.object(suite.os, 'killpg'), \
             mock.patch.object(suite.time, 'monotonic', side_effect=[1, 7]), \
             self.assertRaises(suite.FullError) as caught:
            suite._stop_group(child)
        self.assertEqual(str(caught.exception), 'process_failed')
        child.wait.assert_called_once()

    def test_native_quiescence_rejects_live_unreadable_and_unreaped_pids(self):
        executable = Path(__file__).resolve()
        process = mock.MagicMock()
        process.name = '123'
        proc_root = mock.MagicMock()
        proc_root.iterdir.return_value = [process]
        link = process.__truediv__.return_value
        with mock.patch.object(suite, 'Path', return_value=proc_root):
            link.readlink.return_value = executable
            self.assertFalse(suite.native_processes_quiet(executable))
            link.readlink.side_effect = PermissionError()
            process.stat.return_value.st_uid = os.geteuid()
            self.assertFalse(suite.native_processes_quiet(executable))
            link.readlink.side_effect = FileNotFoundError()
            process.exists.return_value = True
            self.assertFalse(suite.native_processes_quiet(executable))
            process.exists.return_value = False
            self.assertTrue(suite.native_processes_quiet(executable))

    def test_keyboard_interrupt_still_stops_and_reaps_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = mock.MagicMock()
            child.pid = 456
            child.wait.side_effect = [KeyboardInterrupt(), 0]
            child.__enter__.return_value = child
            with mock.patch.object(suite.subprocess, 'Popen', return_value=child), \
                 mock.patch.object(suite.os, 'killpg', side_effect=[None, ProcessLookupError()]), \
                 self.assertRaises(KeyboardInterrupt):
                suite.run_process(['native'], root, root / 'console', 120)
            self.assertEqual(child.wait.call_count, 2)


from tests.test_native_1c_stage2 import Stage2Harness


class FullStageGateTests(Stage2Harness):
    def test_full_suite_starts_only_after_all_existing_gates(self):
        completed = suite.empty_report(NONCE)
        completed.update(status='ok', failure_kind='none')
        with mock.patch.object(suite, 'run_suite', return_value=completed) as run:
            report = self.module.run(full_nonce=NONCE)
        self.assertEqual(report['status'], 'ok')
        run.assert_called_once()
        launcher, platform, epf, root, inputs, nonce = run.call_args.args
        self.assertEqual(platform.timeout, 120)
        self.assertEqual(platform.user, 'NativeSmoke')
        self.assertIsNone(platform.password)
        self.assertEqual(epf, self.evidence / 'Launcher.epf')
        self.assertEqual(root, self.root / ('stage3-' + NONCE))
        self.assertEqual(inputs, self.inputs)
        self.assertEqual(nonce, NONCE)
        self.assertTrue(report['simple_epf_passed'])
        self.assertFalse((self.evidence / 'control.json').exists())
        self.assertEqual(json.loads((self.root / 'stage3-report.json').read_bytes()), completed)

    def test_failed_fresh_security_gate_never_starts_full_suite(self):
        self.failures['verify'] = 'process_failed'
        with mock.patch.object(suite, 'run_suite') as run:
            report = self.module.run(full_nonce=NONCE)
        self.assertEqual(report['status'], 'failed')
        run.assert_not_called()
        self.assertEqual(json.loads((self.root / 'stage3-report.json').read_bytes()), suite.empty_report(NONCE))

    def test_failed_simple_epf_never_starts_full_suite(self):
        self.simple_result = {'messages': ['wrong'], 'error': ''}
        with mock.patch.object(suite, 'run_suite') as run:
            report = self.module.run(full_nonce=NONCE)
        self.assertEqual(report['failed_stage'], 'simple_epf')
        run.assert_not_called()
        self.assertEqual(json.loads((self.root / 'stage3-report.json').read_bytes()), suite.empty_report(NONCE))

    def test_stage_three_failure_does_not_relabel_successful_security_gates(self):
        failed = suite.empty_report(NONCE)
        failed.update(status='failed', failure_kind='timeout', failed_case='collections')
        with mock.patch.object(suite, 'run_suite', return_value=failed):
            code = self.module.main(['--full-suite', '--invocation-nonce', NONCE])
        self.assertEqual(code, 1)
        stage2 = json.loads((self.root / 'stage2-report.json').read_bytes())
        self.assertEqual(stage2['status'], 'ok')
        self.assertEqual(stage2['security_settings_state'], 'verified')
        self.assertEqual(json.loads((self.root / 'stage3-report.json').read_bytes()), failed)


if __name__ == '__main__':
    unittest.main()
