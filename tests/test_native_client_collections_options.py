"""Offline opt-in wiring only; no native execution or native evidence."""
from __future__ import annotations

import contextlib
import io
import itertools
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
from test_native_1c_full_stage import suite, NONCE, portable_fixture_bytes
from test_native_1c_full_host import read_synthetic_file


class ClientCollectionsOptionTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            # NTFS fixtures do not emulate Linux descriptor metadata equality.
            # Keep real native readers unchanged; reuse existing bounded fixtures.
            for patcher in (mock.patch.object(smoke.FULL, 'read_regular', new=read_synthetic_file),
                            mock.patch.object(suite, 'secure_bytes', new=portable_fixture_bytes)):
                patcher.start()
                self.addCleanup(patcher.stop)

    def test_api_prerequisites_fail_before_side_effects(self):
        for full, client in ((False, False), (True, False), (False, True)):
            with self.subTest(full=full, client=client):
                with self.assertRaisesRegex(smoke.SmokeError, 'client_collections_requires'):
                    smoke.run_smoke(Path('/does-not-exist'), full_suite=full,
                                    client_probe=client, client_collections=True)
                with self.assertRaisesRegex(smoke.SmokeError, 'client_collections_requires'):
                    smoke.container_command(Path('/does-not-exist'), 'test',
                        full_suite=full, client_probe=client, client_collections=True)
        for nonce, client in ((None, False), (None, True), (NONCE, False)):
            controller = load_controller()
            with mock.patch.object(controller, 'empty_report') as report:
                with self.assertRaisesRegex(controller.StageError, 'invalid_input'):
                    controller.run(full_nonce=nonce, client_probe=client, client_collections=True)
                report.assert_not_called()

    def test_cli_prerequisites_fail_before_run(self):
        for flags in ([], ['--full-suite'], ['--client-probe']):
            with self.subTest(flags=flags), mock.patch.object(smoke, 'run_smoke') as run:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    smoke.main(['--execute-approved-image', '--client-collections-parity', *flags])
                self.assertEqual(caught.exception.code, 2)
                run.assert_not_called()

    def test_command_changes_only_explicit_option(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            hashes = smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            self.assertEqual(len(hashes), 24)
            for watchdog, dates, values in itertools.product((False, True), repeat=3):
                options = dict(full_suite=True, client_probe=True, watchdog_check=watchdog,
                               client_dates=dates, client_values=values, nonce=NONCE)
                old = smoke.container_command(staged, 'test', **options)
                new = smoke.container_command(staged, 'test', client_collections=True, **options)
                self.assertEqual(new, old + ['--client-collections-parity'])
                self.assertNotIn('--client-collections-parity', old)

    def test_cli_forwards_all_selected_and_unselected_options(self):
        for watchdog, dates, values, collections in itertools.product((False, True), repeat=4):
            with tempfile.TemporaryDirectory() as directory:
                flags = (['--client-watchdog-check'] if watchdog else [])
                flags += ['--client-dates-parity'] if dates else []
                flags += ['--client-values-parity'] if values else []
                flags += ['--client-collections-parity'] if collections else []
                with mock.patch.object(smoke, 'run_smoke', side_effect=smoke.SmokeError('offline')) as run, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(smoke.main(['--execute-approved-image', '--full-suite',
                        '--client-probe', *flags, '--output', str(Path(directory).resolve() / 'report.json')]), 1)
                self.assertEqual(run.call_args.kwargs['client_collections'], collections)
                self.assertEqual(run.call_args.kwargs['client_dates'], dates)
                self.assertEqual(run.call_args.kwargs['client_values'], values)
                self.assertEqual(run.call_args.kwargs['watchdog_check'], watchdog)

    def test_generated_hash_uses_staged_inputs_and_restores_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            names = ('inject_modules', 'evidence_gates', 'full_suite')
            before = {name: sys.modules.get(name) for name in names}
            if os.name == 'nt':
                # Fixture-only normalization; production remains raw-SHA pinned.
                for name in ('scenarios/collections.bsl', suite.CLIENT_TARGET):
                    path = staged / name
                    path.chmod(0o600)
                    path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
                    path.chmod(0o444)
            expected = smoke.FULL.digest(suite.client_collections_module(
                (staged / 'scenarios/collections.bsl').read_bytes(),
                (staged / 'bootstrap/client_probe.bsl').read_bytes()))
            original = {path.relative_to(staged): path.read_bytes() for path in staged.rglob('*') if path.is_file()}
            with mock.patch.object(smoke.FULL, 'read_regular', wraps=smoke.FULL.read_regular) as reader:
                self.assertEqual(smoke.client_collections_module_hash(staged), expected)
            self.assertEqual([call.args[0].name for call in reader.call_args_list],
                             ['inject_modules.py', 'evidence_gates.py', 'full_suite.py', 'collections.bsl', 'client_probe.bsl'])
            self.assertEqual(original,
                {path.relative_to(staged): path.read_bytes() for path in staged.rglob('*') if path.is_file()})
            smoke.validate_input_tree(staged, full_suite=True, client_probe=True)
            self.assertFalse(list(staged.rglob('__pycache__')))
            command = smoke.container_command(staged, 'test', full_suite=True,
                client_probe=True, watchdog_check=True, client_collections=True, nonce=NONCE)
            self.assertEqual(command[-1], '--client-collections-parity')
            for name in names:
                self.assertIs(sys.modules.get(name), before[name])

            # Existing objects, explicit import blocks, and missing entries are
            # each restored exactly, without allowing ambient imports to win.
            for previous in ('missing', None, object()):
                with mock.patch.dict(sys.modules):
                    for name in names:
                        if previous == 'missing':
                            sys.modules.pop(name, None)
                        else:
                            sys.modules[name] = previous
                    self.assertEqual(smoke.client_collections_module_hash(staged), expected)
                    for name in names:
                        if previous == 'missing':
                            self.assertNotIn(name, sys.modules)
                        else:
                            self.assertIs(sys.modules[name], previous)
            self.assertFalse(list(staged.rglob('__pycache__')))

    def test_shell_decodes_stage_wire_before_named_census_and_transport(self):
        source = smoke.PROBE.read_text()
        decode = source.index('suite = full_suite.decode_stage_wire(')
        self.assertLess(decode, source.index('report["stage3"] = suite'))
        self.assertLess(decode, source.index('full_suite.final_client_process_census(nonce)'))
        self.assertLess(decode, source.index('full_suite.build_envelope('))
        self.assertIn('full_suite.secure_bytes(path, full_suite.MAX_STAGE_REPORT)', source)

    def test_adapter_selector_rejects_arbitrary_paths_before_reads(self):
        with mock.patch.object(smoke.FULL, 'read_regular') as read:
            for scenario in ('../collections', 'strings', 'client_collections', ''):
                with self.assertRaisesRegex(smoke.SmokeError, 'invalid_client_parity_scenario'):
                    smoke._client_parity_module_hash(Path('/does-not-exist'), scenario)
            read.assert_not_called()

    def test_imports_restored_after_invalid_staged_source(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            path = staged / 'scenarios/collections.bsl'
            path.chmod(0o600)
            path.write_bytes(b'not the reviewed scenario')
            before = {name: sys.modules.get(name) for name in ('inject_modules', 'evidence_gates', 'full_suite')}
            with self.assertRaises(Exception):
                smoke.client_collections_module_hash(staged)
            smoke.validate_input_tree(staged, full_suite=True, client_probe=True)
            self.assertFalse(list(staged.rglob('__pycache__')))
            for name, module in before.items():
                self.assertIs(sys.modules.get(name), module)

    def test_compile_failure_keeps_exact_tree_and_restores_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            smoke.stage_inputs(staged, full_suite=True, client_probe=True)
            (staged / 'bootstrap/full_suite.py').write_bytes(b'def broken(')
            before = {name: sys.modules.get(name) for name in ('inject_modules', 'evidence_gates', 'full_suite')}
            with self.assertRaises(SyntaxError):
                smoke.client_collections_module_hash(staged)
            smoke.validate_input_tree(staged, full_suite=True, client_probe=True)
            self.assertFalse(list(staged.rglob('__pycache__')))
            for name, module in before.items():
                self.assertIs(sys.modules.get(name), module)

    def test_stage_accepts_collections_with_and_without_dates_and_watchdog(self):
        for watchdog, dates, values in itertools.product((False, True), repeat=3):
            controller = load_controller()
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / 'stage3-report.json').write_text('{"status":"ok"}')
                report = controller.empty_report()
                report['status'] = 'ok'
                args = ['--full-suite', '--invocation-nonce', NONCE, '--client-probe']
                if watchdog:
                    args.append('--client-watchdog-check')
                if dates:
                    args.append('--client-dates-parity')
                if values:
                    args.append('--client-values-parity')
                args.append('--client-collections-parity')
                with mock.patch.object(controller, 'ROOT', root), mock.patch.object(controller, 'run', return_value=report) as run:
                    self.assertEqual(controller.main(args), 0)
                run.assert_called_once_with(full_nonce=NONCE, client_probe=True,
                                            watchdog_check=watchdog, client_dates=dates, client_collections=True,
                                            **({"client_values": True} if values else {}))

    def test_stage_rejects_invalid_options_without_run(self):
        for args in (['--client-collections-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-collections-parity'],
                     ['--client-probe', '--client-collections-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-collections-parity', '--client-collections-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-collections-parity', '--client-dates-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-collections-parity', '--client-values-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-collections-parity', '--client-probe'],
                     ['--full-suite', '--invocation-nonce', '0', '--client-probe', '--client-collections-parity']):
            controller = load_controller()
            with mock.patch.object(controller, 'run') as run:
                self.assertEqual(controller.main(args), 2)
                run.assert_not_called()

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'requires POSIX Bash, not Windows WSL launcher')
    def test_shell_parser_keeps_flags_and_rejects_bad_shapes(self):
        # Execute only argument parsing, never the probe or any native command.
        prefix = smoke.PROBE.read_text().split('\nfinish() {', 1)[0]
        script = prefix + '\nprintf "%s\\n" "$full_suite" "$client_probe" "$watchdog_check" "$client_dates" "$client_values" "$client_collections" "${client_args[@]}"\n'
        for watchdog, dates, values in itertools.product((False, True), repeat=3):
            flags = (['--client-probe'] + (['--client-watchdog-check'] if watchdog else [])
                     + (['--client-dates-parity'] if dates else [])
                     + (['--client-values-parity'] if values else []) + ['--client-collections-parity'])
            result = subprocess.run(['bash', '-c', script, 'parser', '--full-suite', '--invocation-nonce', NONCE, *flags], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.splitlines(),
                             ['true', 'true', str(watchdog).lower(), str(dates).lower(), str(values).lower(), 'true', *flags])
        for flags in (['--client-collections-parity'], ['--full-suite', '--invocation-nonce', NONCE, '--client-collections-parity'],
                      ['--client-probe', '--client-collections-parity'],
                      ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-collections-parity', '--client-collections-parity'],
                      ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-collections-parity', '--client-dates-parity'],
                     ['--full-suite', '--invocation-nonce', NONCE, '--client-probe', '--client-collections-parity', '--client-values-parity'],
                      ['--full-suite', '--invocation-nonce', '0', '--client-probe', '--client-collections-parity']):
            result = subprocess.run(['bash', '-c', script, 'parser', *flags], capture_output=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
