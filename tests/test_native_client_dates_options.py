"""Offline opt-in wiring only; no native execution or native evidence."""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from test_native_1c_smoke import smoke
from test_native_1c_stage2 import load_controller
from test_native_1c_full_stage import suite, NONCE


class ClientDatesOptionTests(unittest.TestCase):
    def test_api_prerequisites_fail_before_side_effects(self):
        for full, client in ((False, False), (True, False), (False, True)):
            with self.subTest(full=full, client=client):
                with self.assertRaisesRegex(smoke.SmokeError, 'client_dates_requires'):
                    smoke.run_smoke(Path('/does-not-exist'), full_suite=full,
                                    client_probe=client, client_dates=True)
                with self.assertRaisesRegex(smoke.SmokeError, 'client_dates_requires'):
                    smoke.container_command(Path('/does-not-exist'), 'test',
                        full_suite=full, client_probe=client, client_dates=True)

    def test_cli_prerequisites_fail_before_run(self):
        for flags in ([], ['--full-suite'], ['--client-probe']):
            with self.subTest(flags=flags), mock.patch.object(smoke, 'run_smoke') as run:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    smoke.main(['--execute-approved-image', '--client-dates-parity', *flags])
                self.assertEqual(caught.exception.code, 2)
                run.assert_not_called()

    def test_command_changes_only_explicit_option(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory) / 'inputs'
            hashes = smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            self.assertEqual(len(hashes), 24)
            for watchdog in (False, True):
                options = dict(full_suite=True, client_probe=True, watchdog_check=watchdog, nonce=NONCE)
                old = smoke.container_command(staged, 'test', **options)
                new = smoke.container_command(staged, 'test', client_dates=True, **options)
                self.assertEqual(new, old + ['--client-dates-parity'])
                self.assertNotIn('--client-dates-parity', old)

    def test_generated_hash_uses_staged_inputs_and_restores_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory) / 'inputs'
            smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            names = ('inject_modules', 'evidence_gates', 'full_suite')
            before = {name: sys.modules.get(name) for name in names}
            if os.name == 'nt':
                # Fixture-only normalization; production remains raw-SHA pinned.
                for name in ('scenarios/dates.bsl', suite.CLIENT_TARGET):
                    path = staged / name
                    path.chmod(0o600)
                    path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
                    path.chmod(0o444)
            expected = smoke.FULL.digest(suite.client_dates_module(
                (staged / 'scenarios/dates.bsl').read_bytes(),
                (staged / 'bootstrap/client_probe.bsl').read_bytes()))
            self.assertEqual(smoke.client_dates_module_hash(staged), expected)
            for name in names:
                self.assertIs(sys.modules.get(name), before[name])

    def test_imports_restored_after_invalid_staged_source(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory) / 'inputs'
            smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            path = staged / 'scenarios/dates.bsl'
            path.chmod(0o600)
            path.write_bytes(b'not the reviewed scenario')
            before = {name: sys.modules.get(name) for name in ('inject_modules', 'evidence_gates', 'full_suite')}
            with self.assertRaises(Exception):
                smoke.client_dates_module_hash(staged)
            for name, module in before.items():
                self.assertIs(sys.modules.get(name), module)

    def test_stage_accepts_dates_with_and_without_watchdog(self):
        for watchdog in (False, True):
            controller = load_controller()
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'stage3-report.json').write_text('{"status":"ok"}')
                report = controller.empty_report()
                report['status'] = 'ok'
                args = ['--full-suite', '--invocation-nonce', NONCE, '--client-probe']
                if watchdog:
                    args.append('--client-watchdog-check')
                args.append('--client-dates-parity')
                with mock.patch.object(controller, 'ROOT', root), mock.patch.object(controller, 'run', return_value=report) as run:
                    self.assertEqual(controller.main(args), 0)
                run.assert_called_once_with(full_nonce=NONCE, client_probe=True,
                                            watchdog_check=watchdog, client_dates=True)

    def test_stage_rejects_invalid_options_without_run(self):
        for args in (['--client-dates-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-dates-parity'],
                     ['--client-probe', '--client-dates-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-dates-parity', '--client-dates-parity']):
            controller = load_controller()
            with mock.patch.object(controller, 'run') as run:
                self.assertEqual(controller.main(args), 2)
                run.assert_not_called()

    @unittest.skipUnless(shutil.which('bash'), 'requires Bash for shell parser only')
    def test_shell_parser_keeps_flags_and_rejects_bad_shapes(self):
        # Execute only argument parsing, never the probe or any native command.
        prefix = smoke.PROBE.read_text().split('\nfinish() {', 1)[0]
        script = prefix + '\nprintf "%s\\n" "$full_suite" "$client_probe" "$watchdog_check" "$client_dates" "${client_args[@]}"\n'
        for watchdog in (False, True):
            flags = ['--client-probe'] + (['--client-watchdog-check'] if watchdog else []) + ['--client-dates-parity']
            result = subprocess.run(['bash', '-c', script, 'parser', '--full-suite', '--invocation-nonce', NONCE, *flags], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.splitlines(), ['true', 'true', str(watchdog).lower(), 'true', *flags])
        for flags in (['--client-dates-parity'], ['--full-suite', '--invocation-nonce', NONCE, '--client-dates-parity'], ['--client-probe', '--client-dates-parity']):
            result = subprocess.run(['bash', '-c', script, 'parser', *flags], capture_output=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
