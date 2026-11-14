"""Frozen smoke speaks the public writer protocol, never bypassing the host guard."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import ui_frozen_smoke as smoke
from yadinassi.ui.browser_session import AttachmentError, BrowserSession

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = 'a' * 43


class FrozenUIAttachmentSmokeTests(unittest.TestCase):
    def test_unified_launch_requires_exact_loopback_attachment_profile(self):
        self.assertEqual(smoke._launch_identity('http://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1'), (1234, BOOTSTRAP))
        for url in ('http://127.0.0.1:1234/#session='+BOOTSTRAP,
                    'http://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=0',
                    'http://localhost:1234/#session='+BOOTSTRAP+'&attachment=1',
                    'https://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1',
                    'http://user@127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1',
                    'http://127.0.0.1:1234/?other=1#session='+BOOTSTRAP+'&attachment=1',
                    'http://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1&extra=',
                    'http://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1&session=',
                    'http://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1&session='+BOOTSTRAP):
            with self.subTest(url=url), self.assertRaises(AssertionError): smoke._launch_identity(url)

    def test_real_attach_exchanges_bootstrap_for_current_writer_headers(self):
        host = BrowserSession(BOOTSTRAP)
        calls = []
        def request(method, path, data, headers):
            calls.append((method, path))
            self.assertEqual((method, path), ('POST', '/attachment'))
            self.assertEqual(headers, {'Host':'127.0.0.1:1234','Origin':'http://127.0.0.1:1234',
                'Content-Type':'application/x-ndjson','X-Yadinassi-Session':BOOTSTRAP})
            packet = json.loads(data)
            self.assertEqual(set(packet), {'action','instance'})
            self.assertEqual(packet['action'], 'attach')
            return json.dumps(host.attach(BOOTSTRAP, packet['instance'])).encode()
        headers = smoke._writer_headers(request, '127.0.0.1:1234', 'http://127.0.0.1:1234', BOOTSTRAP)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(headers['X-Yadinassi-Session'], BOOTSTRAP)
        with host.dispatch(headers['X-Yadinassi-Session'], headers['X-Yadinassi-Attachment'], int(headers['X-Yadinassi-Generation'])):
            pass
        with self.assertRaises(AttachmentError):
            with host.dispatch(BOOTSTRAP, headers['X-Yadinassi-Attachment'], int(headers['X-Yadinassi-Generation'])):
                self.fail('bootstrap was allowed to bypass attachment')

    def test_observer_closed_recovery_and_malformed_status_never_dispatch(self):
        value = BrowserSession(BOOTSTRAP).attach(BOOTSTRAP, '0'*32)
        mutations = [('role','observer'), ('closed',True), ('recovery',True), ('protocol','other'),
                     ('generation',True), ('generation',0), ('generation','1'), ('generation',2**53),
                     ('leaseSeconds',False), ('graceSeconds',0), ('attachment','other'),
                     ('credential',BOOTSTRAP), ('resume',value['credential']), ('credential','bad')]
        for name, bad in mutations:
            changed = dict(value, **{name:bad})
            request = mock.Mock(return_value=json.dumps(changed).encode())
            with self.subTest(name=name,bad=bad), self.assertRaises(AssertionError):
                smoke._writer_headers(request,'127.0.0.1:1','http://127.0.0.1:1',BOOTSTRAP)
            request.assert_called_once()

    def test_unknown_missing_and_error_reply_do_not_fallback_or_retry(self):
        value = BrowserSession(BOOTSTRAP).attach(BOOTSTRAP, '0'*32)
        missing = copy.deepcopy(value); del missing['resume']
        for changed in (missing, dict(value, extra=True), {'error':'busy'}, [], None):
            request = mock.Mock(return_value=json.dumps(changed).encode())
            with self.subTest(value=changed), self.assertRaises(AssertionError):
                smoke._writer_headers(request,'127.0.0.1:1','http://127.0.0.1:1',BOOTSTRAP)
            request.assert_called_once()

    def test_http_refusal_is_not_retried_or_relabelled(self):
        request = mock.Mock(side_effect=AssertionError('frozen UI HTTP 403'))
        with self.assertRaisesRegex(AssertionError, 'HTTP 403'):
            smoke._writer_headers(request,'127.0.0.1:1','http://127.0.0.1:1',BOOTSTRAP)
        request.assert_called_once()

    def test_same_smoke_runs_against_real_unified_source_launcher(self):
        # The same smoke function/process/HTTP/child-runtime/save/reopen path is
        # exercised here. This is source-launch regression, not a frozen-binary claim.
        real_popen = subprocess.Popen
        launches = []
        def source_launch(arguments, **kwargs):
            if arguments[0] != 'source-launch-probe':
                return real_popen(arguments, **kwargs)
            self.assertEqual(arguments[1:3], ['--ui', '--f'])
            self.assertEqual(kwargs['start_new_session'], not smoke.WINDOWS)
            self.assertNotEqual(kwargs['stdout'], subprocess.PIPE)
            launches.append(arguments)
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + ['-m','yadinassi',*arguments[1:]]
            return real_popen(command, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            # Match the packaged smoke entrypoint, including macOS /var aliases.
            directory = str(Path(directory).resolve())
            env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
                       PYTHONIOENCODING='utf-8', TMPDIR=directory)
            output = io.StringIO()
            with mock.patch.object(smoke.subprocess, 'Popen', side_effect=source_launch), \
                    mock.patch.object(smoke, '_stop_owned_tree', wraps=smoke._stop_owned_tree) as stop, \
                    contextlib.redirect_stdout(output):
                smoke.check_ui('source-launch-probe', directory, env)
            stop.assert_not_called()
            self.assertEqual(len(launches), 1)
            self.assertIn('Frozen UI smoke passed:', output.getvalue())

    def test_startup_capture_has_bounded_size_deadline_and_three_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'private.log'
            url = 'http://127.0.0.1:1234/#session='+BOOTSTRAP+'&attachment=1'
            capture.write_bytes(('one\ntwo\n'+url+'\nlater output\n').encode())
            process = mock.Mock(); process.poll.return_value = None
            self.assertEqual(smoke._read_launch(capture, process), url)
            process.poll.assert_not_called()
            for content, message in ((b'x'*4097+b'\n', 'exceeds limit'),
                                     (b'a\nb\nc\n', 'URL missing'),
                                     (b'one\npartial', 'exited before')):
                capture.write_bytes(content); process.poll.return_value = 0
                with self.subTest(message=message), self.assertRaisesRegex(AssertionError, message):
                    smoke._read_launch(capture, process)
            capture.write_bytes(b'one\npartial'); process.poll.return_value = None
            clock = SimpleNamespace(monotonic=mock.Mock(side_effect=[0,45]), sleep=mock.Mock())
            with mock.patch.object(smoke, 'time', clock), self.assertRaisesRegex(AssertionError, 'timed out'):
                smoke._read_launch(capture, process)
            clock.sleep.assert_not_called()
            with mock.patch.object(smoke.subprocess, 'Popen', side_effect=OSError('spawn refused')), \
                    self.assertRaisesRegex(OSError, 'spawn refused'):
                smoke.check_ui('source-launch-probe', directory, dict(os.environ))
            self.assertFalse((Path(directory)/'ui smoke база'/'private-launch-output.log').exists())

    def test_posix_failure_targets_only_created_group_with_bounded_escalation(self):
        process = mock.Mock(pid=246810); process.poll.return_value = None
        process.wait.return_value = 0
        def signal_group(pid, number):
            if number == 0: raise ProcessLookupError
        # Same clock tick can round (tick + 25) - tick slightly above 25.
        # Reproduce it deterministically instead of depending on OS clock granularity.
        tick = 65527.597865678625
        self.assertGreater((tick + 25) - tick, 25)
        with mock.patch.object(smoke, 'WINDOWS', False), \
                mock.patch.object(smoke.time, 'monotonic', return_value=tick), \
                mock.patch.object(smoke, 'signal', SimpleNamespace(SIGTERM=15, SIGKILL=9)), \
                mock.patch.object(smoke.time, 'sleep'), \
                mock.patch.object(smoke.os, 'killpg', side_effect=signal_group, create=True) as killpg:
            self.assertTrue(smoke._stop_owned_tree(process))
        process.poll.assert_called_once()
        self.assertEqual(killpg.call_args_list, [mock.call(246810,15), mock.call(246810,9), mock.call(246810,0)])
        self.assertTrue(all(0 < c.kwargs['timeout'] <= 25 for c in process.wait.call_args_list))
        process.kill.assert_not_called(); process.terminate.assert_not_called()
        process.poll.return_value = 0
        with mock.patch.object(smoke, 'WINDOWS', False), \
                mock.patch.object(smoke.os, 'killpg', create=True) as probe:
            self.assertFalse(smoke._stop_owned_tree(process))
        probe.assert_called_once_with(246810, 0)  # surviving group, no signal

    def test_windows_tree_cleanup_is_absolute_owned_pid_and_fallback_is_unverified(self):
        for failure in (None, 1, subprocess.TimeoutExpired('owned taskkill', 10)):
            process = mock.Mock(pid=246810); process.poll.return_value = None
            def wait(**kwargs):
                process.poll.return_value = 0
                return 0
            process.wait.side_effect = wait
            calls = []
            def run(args, **kwargs):
                calls.append('tree'); self.assertEqual(args[1:], ['/PID','246810','/T','/F'])
                self.assertEqual(args[0], str(PureWindowsPath(os.environ.get('SystemRoot', r'C:\Windows'))/'System32'/'taskkill.exe'))
                self.assertTrue(0 < kwargs['timeout'] <= 10)
                if isinstance(failure, Exception): raise failure
                return SimpleNamespace(returncode=failure or 0)
            process.terminate.side_effect = lambda: calls.append('parent')
            with self.subTest(failure=failure), mock.patch.object(smoke, 'WINDOWS', True), \
                    mock.patch.object(smoke.subprocess, 'run', side_effect=run):
                self.assertEqual(smoke._stop_owned_tree(process), failure is None)
            self.assertEqual(calls[0], 'tree')
            if failure == 1: self.assertEqual(calls, ['tree','parent'])
        process.poll.return_value = 0
        with mock.patch.object(smoke, 'WINDOWS', True), mock.patch.object(smoke.subprocess, 'run') as run:
            self.assertFalse(smoke._stop_owned_tree(process))
        run.assert_not_called()
        process.poll.return_value = None
        with mock.patch.object(smoke, 'WINDOWS', True), \
                mock.patch.dict(os.environ, {'SystemRoot':'relative'}), \
                mock.patch.object(smoke.subprocess, 'run') as run:
            self.assertFalse(smoke._stop_owned_tree(process))
        run.assert_not_called()

    def test_real_source_refusal_preserves_error_even_if_cleanup_is_unverified(self):
        real_popen = subprocess.Popen; launches = []
        def source_launch(arguments, **kwargs):
            if arguments[0] != 'source-launch-probe': return real_popen(arguments, **kwargs)
            command = [sys.executable] + (['-O'] if sys.flags.optimize else []) + ['-m','yadinassi',*arguments[1:]]
            process = real_popen(command, **kwargs); launches.append(process)
            return process
        with tempfile.TemporaryDirectory() as directory:
            directory = str(Path(directory).resolve())
            env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
                       PYTHONIOENCODING='utf-8', TMPDIR=directory)
            real_stop = smoke._stop_owned_tree
            def report_uncertain(process):
                real_stop(process)
                return False  # Verify primary error preservation, not false success.
            diagnostics = io.StringIO()
            with mock.patch.object(smoke.subprocess, 'Popen', side_effect=source_launch), \
                    mock.patch.object(smoke, '_writer_headers', side_effect=AssertionError('injected HTTP 403')), \
                    mock.patch.object(smoke, '_stop_owned_tree', side_effect=report_uncertain), \
                    contextlib.redirect_stderr(diagnostics), \
                    self.assertRaisesRegex(AssertionError, 'injected HTTP 403'):
                smoke.check_ui('source-launch-probe', directory, env)
            self.assertEqual(len(launches),1)
            self.assertIsNotNone(launches[0].poll())
            self.assertFalse((Path(directory)/'ui smoke база'/'private-launch-output.log').exists())
            self.assertEqual(diagnostics.getvalue(), 'Frozen UI owned process-tree cleanup unverified.\n')


if __name__ == '__main__': unittest.main()
