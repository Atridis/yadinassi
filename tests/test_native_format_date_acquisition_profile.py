"""Closed date acquisition pipeline uses synthetic data, not a native oracle."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
import test_native_tree_profile_budget as budget
from test_native_tree_profile_host import synthetic_producer_reader
from test_native_1c_smoke import bootstrap_report
from test_native_format_date_acquisition_measurement import COUNTS, KINDS, emit, source, wire

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE


def profile(kind):
    return f'format-date-{kind}-v1'


def spec(kind):
    return tree.profiles.select(profile(kind))


def envelope(kind, raw):
    selected = profile(kind)
    s = spec(kind)
    hashes = dict.fromkeys(tree.input_files(profile=selected), 'a' * 64)
    hashes[s.source] = s.source_sha256
    modules = {s.case: 'b' * 64, 'client_tree': 'c' * 64}
    stage = tree.empty_report(NONCE, profile=selected)
    stage.update(status='ok', failure_kind='none', input_sha256=hashes)
    case = stage['cases'][0]
    case.update(status='ok', source_sha256=s.source_sha256, module_sha256=modules[s.case],
                output_sha256=full.digest(raw), output_size=len(raw), message_count=s.count)
    client = stage['client_tree']
    client.update(status='ok', failure_kind='none', source_sha256=s.source_sha256,
                  module_sha256=modules['client_tree'], roundtrip_sha256=modules['client_tree'],
                  **dict.fromkeys(host.FULL.CLIENT_FLAGS, True),
                  **{k: case[k] for k in host.FULL.CLIENT_OUTPUT_KEYS})
    client['process_diagnostics'].update(stage='after_exit', reason='none')
    with tempfile.TemporaryDirectory(prefix='date-acquisition-') as tmp, synthetic_producer_reader(tree.full), mock.patch.object(full, 'final_client_process_census'):
        parent = Path(tmp).resolve()
        capture = parent / 'capture'
        capture.mkdir()
        (capture / (s.case + '.out')).write_bytes(raw)
        tree.write_report(parent / 'stage3-report.json', stage, profile=selected)
        encoded = tree.finish_report(bootstrap_report(), NONCE, capture, quiet=True,
                                     bus_cleanup_failed=False, profile=selected)
    return encoded, hashes, modules


class DateAcquisitionProfileTests(unittest.TestCase):
    def test_closed_registry_exact_staging_and_isolated_contract_import(self):
        for kind in KINDS:
            selected, s = profile(kind), spec(kind)
            self.assertEqual((s.case, s.count, s.print_sites, s.artifact),
                             (f'format_date_{kind}', COUNTS[kind] + 2, 5, f'format-date-{kind}'))
            self.assertEqual(tree.input_files(profile=selected), host.staged_files(smoke, profile=selected))
            self.assertEqual(len(tree.input_files(profile=selected)), 22)
            self.assertNotIn(s.source, tree.input_files(profile='format-dates-v1'))
            with tempfile.TemporaryDirectory(prefix='date-stage-') as tmp, budget.synthetic_inventory_reader():
                parent = Path(tmp).resolve()
                checkout, staged = parent / 'checkout', parent / 'staged'
                for name in tree.input_files(profile=selected):
                    path = checkout / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((ROOT / name).read_text(encoding='utf-8').encode())
                hashes = host.stage_inputs(checkout, staged, smoke, profile=selected)
                self.assertEqual(set(host.module_hashes(staged, hashes, smoke, profile=selected)), {s.case, 'client_tree'})
                code = ('import sys;sys.path.insert(0,' + repr(str(staged / 'bootstrap'))
                        + f');import native_1c_format_date_{kind}_contract as c;c.require_available('
                        + repr(emit(kind, lambda *args: 'x' * 32)) + ');print(c.MAX_ENCODED_BYTES)')
                result = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True, timeout=30)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, (str(wire(kind).MAX_ENCODED_BYTES) + os.linesep).encode(), b''))
                (staged / f'bootstrap/native_1c_format_date_{kind}_contract.py').unlink()
                with self.assertRaises(host.TreeError):
                    host.module_hashes(staged, hashes, smoke, profile=selected)

    def test_generated_client_captures_helper_output_and_utf16(self):
        for kind in KINDS:
            raw_source = source(kind).encode()
            template = (ROOT / full.CLIENT_SOURCE).read_text(encoding='utf-8').encode()
            module = tree.client_module(raw_source, template, profile=profile(kind))
            for witness in (lambda *args: ' \u00a0\U0001f600', lambda *args: 'x' * 32, lambda *args: 42):
                vm = Interpreter(native_target=LINUX_8_3_27_1508)
                vm.register_function('Format', witness)
                vm.register_function('Формат', witness)
                vm.execute(module.decode('utf-8-sig'))
                vm.execute('Result = ВычислитьПробу();')
                self.assertEqual(('\n'.join(vm.variables['result'].items) + '\n').encode(), emit(kind, witness))
            for bad in (raw_source + b'\n', raw_source.replace(b'\n', b'\r\n')):
                with self.assertRaises(full.FullError):
                    tree.client_module(bad, template, profile=profile(kind))

    def test_native_envelope_is_source_bound_and_runtime_mismatch_stays_explicit(self):
        for kind in KINDS:
            raw = emit(kind, lambda *args: 'A')
            different = emit(kind, lambda *args: 'B')
            encoded, hashes, modules = envelope(kind, raw)
            _, observed = host.validate_envelope(encoded, NONCE, hashes, modules, smoke.validate_report, profile=profile(kind))
            self.assertEqual(observed, raw)
            with tempfile.TemporaryDirectory(prefix='date-compare-') as tmp, budget.synthetic_inventory_reader():
                root = Path(tmp).resolve()
                path = root / spec(kind).source
                path.parent.mkdir(parents=True)
                path.write_bytes(source(kind).encode())
                for actual, status in [(raw, 'matched'), (different, 'mismatched'), (b'invalid\n', 'invalid_interpreter_output')]:
                    result = host.compare_output(root, root, raw, hashes, runner=lambda *args: (0, actual, b''), profile=profile(kind))
                    self.assertTrue(result[f'native_format_date_{kind}_available'])
                    self.assertEqual(result['status'], status)
                    self.assertEqual(result['acceptance_status'], 'accepted' if status == 'matched' else 'rejected')

    def test_envelope_rejects_tampered_identity_and_unclean_client(self):
        for kind in KINDS:
            encoded, hashes, modules = envelope(kind, emit(kind, lambda *args: 'A'))
            for key in ('nonce', 'profile'):
                value = json.loads(encoded)
                value[key] = 'wrong'
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(budget.wire(value), NONCE, hashes, modules, smoke.validate_report, profile=profile(kind))
            value = json.loads(encoded)
            value['report']['stage3']['client_tree']['quiet'] = False
            with self.assertRaises(host.TreeError):
                host.validate_envelope(budget.wire(value), NONCE, hashes, modules, smoke.validate_report, profile=profile(kind))

    def test_acquisition_refuses_missing_controls_and_observer_failures(self):
        for kind in KINDS:
            encoded, hashes, modules = envelope(kind, emit(kind, lambda *args: 'A'))
            for raw in (emit(kind, missing=True), emit(kind, lambda *args: 42)):
                # A self-consistent transport receipt is insufficient when the
                # acquired observer or mandatory positive controls failed.
                forged = json.loads(encoded)
                stage = forged['report']['stage3']
                for record in (stage['cases'][0], stage['client_tree']):
                    record.update(output_sha256=full.digest(raw), output_size=len(raw))
                forged['outputs'][0].update(size=len(raw), sha256=full.digest(raw),
                                            data_b64=base64.b64encode(raw).decode())
                with self.assertRaises(host.TreeError):
                    host.validate_envelope(budget.wire(forged), NONCE, hashes, modules,
                                           smoke.validate_report, profile=profile(kind))
                for site in ('server', 'client'):
                    diagnostic = tree.observation_diagnostic(raw, site, profile=profile(kind))
                    self.assertEqual(diagnostic, {'site': site, 'case': None, 'category': 'api_controls', 'calibration': None})
                    tree.validate_diagnostic(diagnostic, profile=profile(kind))
                    host.validate_diagnostic(diagnostic, profile=profile(kind))
                    with self.assertRaises(tree.ObservationFailure):
                        tree.validate_observations(raw, site, profile=profile(kind))

    def test_emitter_dispatch_is_closed_at_both_admission_points(self):
        import test_native_tree_emitter_dispatch as emitter
        for kind in KINDS:
            mode = f'format-date-{kind}'
            finish = mock.Mock(return_value=b'fixed\n')
            raw, error = emitter.execute(emitter.arguments(mode), finish)
            self.assertEqual((raw, error.code), (b'fixed\n', 0))
            self.assertEqual(finish.call_args.kwargs['profile'], profile(kind))
            for lead in ('if tree_mode not in ', 'if tree_mode in '):
                line = next(line for line in emitter.EMITTER.splitlines() if line.startswith(lead))
                member = ', "' + mode + '"'
                self.assertEqual(line.count(member), 1)
                finish.reset_mock()
                emitter.execute(emitter.arguments(mode), finish, emitter.EMITTER.replace(line, line.replace(member, '')))
                finish.assert_not_called()

    def test_bootstrap_flags_are_exact_and_cannot_be_combined(self):
        import run_stage
        for kind in KINDS:
            flag = f'--format-date-{kind}-suite'
            with tempfile.TemporaryDirectory(prefix='date-dispatch-') as tmp, mock.patch.object(run_stage, 'ROOT', Path(tmp)), mock.patch.object(run_stage, 'run', return_value=run_stage.empty_report()) as run, contextlib.redirect_stdout(io.StringIO()):
                run_stage.main([flag, '--invocation-nonce', NONCE])
                run.assert_called_once()
                self.assertTrue(run.call_args.kwargs['tree_suite'])
                self.assertEqual(run.call_args.kwargs['tree_profile'], profile(kind))
                self.assertEqual(run.call_args.kwargs['full_nonce'], NONCE)
            with mock.patch.object(run_stage, 'run') as run:
                for extra in (flag, '--tree-suite', '--client-probe', 'source.bsl'):
                    self.assertEqual(run_stage.main([flag, '--invocation-nonce', NONCE, extra]), 2)
                run.assert_not_called()

    def test_unknown_or_duplicate_profiles_have_no_acquisition_bypass(self):
        for flags in (['--profile', 'format-date-names-v2'], ['--profile', profile('names'), '--profile', profile('names')], ['--acquisition-only']):
            with mock.patch.object(host, 'run') as run, mock.patch.object(sys, 'argv', ['host', '--execute-approved-image'] + flags), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                host.main()
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_fixed_date_lanes_require_runtime_parity_after_acquisition(self):
        selections = [(profile(kind), False) for kind in KINDS] + [('format-dates-v1', False), ('tree-v1', False)]
        for selected, acquisition in selections:
            for acquired, parity in [(True, False), (True, True), (False, False)]:
                report = {'native_measurement_accepted': acquired, 'runtime_parity_accepted': parity,
                          'comparison': {'status': 'matched' if parity else 'mismatched'}}
                with tempfile.TemporaryDirectory(prefix='date-cli-') as tmp, mock.patch.object(host, 'ROOT', Path(tmp)), mock.patch.object(host, 'run', return_value=report), mock.patch.object(sys, 'argv', ['host', '--execute-approved-image', '--profile', selected]), contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(host.main(), 0 if (acquired if acquisition else parity) else 1)
                    saved = json.loads((Path(tmp) / 'native-smoke' / (tree.profiles.select(selected).artifact + '-report.json')).read_text())
                    self.assertEqual(saved['runtime_parity_accepted'], parity)
                    if acquisition:
                        self.assertIn('runtime comparison: ' + report['comparison']['status'], output.getvalue())

    def test_rectangular_stage_transport_host_and_provenance_budgets_unchanged(self):
        for kind in KINDS:
            selected, s = profile(kind), spec(kind)
            stage = budget.stage_majorant()
            stage.update(schema=s.stage_schema, profile=selected, failed_case=s.case,
                         input_sha256=dict.fromkeys(tree.input_files(profile=selected), budget.H))
            stage['cases'][0]['name'] = s.case
            native = budget.native_majorant()
            native['stage3'] = stage
            report = budget.host_majorant()
            report.update(profile=selected, trusted_input_sha256=stage['input_sha256'], native_report=native)
            report['host_source_sha256'][f'scripts/native_1c_format_date_{kind}_contract.py'] = budget.H
            report['comparison'].update(profile=selected, **{f'native_format_date_{kind}_available': False})
            report['observation_diagnostic'] = stage['observation_diagnostic']
            report['status'] = 'failed'
            provenance = budget.wire(report) + b'\n'
            report['native_artifact_sha256'] = dict.fromkeys((s.case + '.out', 'provenance.json'), budget.H)
            transport = dict(schema=s.schema, profile=selected, nonce=NONCE, report=native,
                             outputs=[dict(name=s.case + '.out', size=8192, sha256=budget.H,
                                           data_b64=base64.b64encode(b'x' * 8192).decode())])
            bounds = {'stage': len(budget.wire(stage)), 'native': len(budget.wire(native)),
                      'transport': len(budget.wire(transport)) + 1,
                      'host': len(budget.wire(report)) + 1, 'provenance': len(provenance)}
            for key, cap in [('stage', 8192), ('native', 32768), ('transport', 65536),
                             ('host', 32768), ('provenance', 32768)]:
                self.assertLessEqual(bounds[key], cap, (key, bounds))

    def test_workflow_adds_exact_profiles_without_generic_flags(self):
        workflow = (ROOT / '.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        for kind in KINDS:
            self.assertEqual(workflow.count('- profile: ' + profile(kind)), 1)
            self.assertIn(f'artifact: format-date-{kind}\n            case: format_date_{kind}', workflow)
        self.assertNotIn('--acquisition-only', workflow)
        self.assertIn('profile: format-dates-v1\n            artifact: format-dates\n            case: format_dates', workflow)


if __name__ == '__main__':
    unittest.main()
