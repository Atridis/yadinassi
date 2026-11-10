"""Closed ordinary property-transfer profile; all local receipts are synthetic."""
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
from test_native_property_transfer_measurement import SOURCE, SOURCE_SHA, configure, emit, noop, wire

host, tree, full, smoke = budget.host, budget.tree, budget.suite, budget.smoke
ROOT, NONCE = budget.ROOT, budget.NONCE
PROFILE = 'property-transfer-v1'


def spec():
    return tree.profiles.select(PROFILE)


def envelope(raw):
    selected = PROFILE
    s = spec()
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


class PropertyTransferProfileTests(unittest.TestCase):
    def test_closed_registry_staging_and_isolated_contract(self):
        s = spec()
        self.assertEqual((s.case, s.count, s.print_sites, s.artifact, s.source_sha256),
                         ('property_transfer', 50, 3, 'property-transfer', SOURCE_SHA))
        self.assertEqual(tree.input_files(profile=PROFILE), host.staged_files(smoke, profile=PROFILE))
        self.assertEqual(len(tree.input_files(profile=PROFILE)), 22)
        self.assertNotIn(s.source, tree.input_files(profile='tree-v1'))
        with tempfile.TemporaryDirectory(prefix='property-stage-') as tmp, budget.synthetic_inventory_reader():
            parent = Path(tmp).resolve(); checkout = parent/'checkout'; staged = parent/'staged'
            for name in tree.input_files(profile=PROFILE):
                path = checkout/name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT/name).read_text(encoding='utf-8').encode())
            hashes = host.stage_inputs(checkout, staged, smoke, profile=PROFILE)
            self.assertEqual(set(host.module_hashes(staged, hashes, smoke, profile=PROFILE)), {s.case, 'client_tree'})
            code = ('import sys;sys.path.insert(0,' + repr(str(staged/'bootstrap'))
                    + ');import native_1c_property_transfer_contract as c;c.require_available('
                    + repr(emit()) + ');print(c.MAX_ENCODED_BYTES)')
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True, timeout=30)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, ('6903'+os.linesep).encode(), b''))
            (staged/'bootstrap/native_1c_property_transfer_contract.py').unlink()
            with self.assertRaises(host.TreeError):
                host.module_hashes(staged, hashes, smoke, profile=PROFILE)

    def test_generated_client_matches_standalone_observer_and_source_pin(self):
        source = SOURCE.encode(); template = (ROOT/full.CLIENT_SOURCE).read_text(encoding='utf-8').encode()
        module = tree.client_module(source, template, profile=PROFILE)
        def failure(*args):
            raise ValueError('synthetic private action error')
        for action in (noop, failure):
            vm = Interpreter(native_target=LINUX_8_3_27_1508)
            configure(vm, action)
            vm.execute(module.decode('utf-8-sig')); vm.execute('Result = ВычислитьПробу();')
            self.assertEqual(('\n'.join(vm.variables['result'].items)+'\n').encode(), emit(action))
        for bad in (source+b'\n', source.replace(b'\n', b'\r\n')):
            with self.assertRaises(full.FullError):
                tree.client_module(bad, template, profile=PROFILE)

    def test_native_envelope_does_not_imply_interpreter_parity(self):
        raw = emit(); encoded, hashes, modules = envelope(raw)
        _, observed = host.validate_envelope(encoded, NONCE, hashes, modules, smoke.validate_report, profile=PROFILE)
        self.assertEqual(observed, raw)
        different = raw.replace(b'PV-05: [S/', b'PV-05: [E/', 1)
        with tempfile.TemporaryDirectory(prefix='property-compare-') as tmp, budget.synthetic_inventory_reader():
            root = Path(tmp).resolve(); path = root/spec().source; path.parent.mkdir(parents=True); path.write_bytes(SOURCE.encode())
            for actual, status in [(raw, 'matched'), (different, 'mismatched'), (b'invalid\n', 'invalid_interpreter_output')]:
                result = host.compare_output(root, root, raw, hashes, runner=lambda *args: (0, actual, b''), profile=PROFILE)
                self.assertTrue(result['native_property_transfer_available'])
                self.assertEqual(result['status'], status)
                self.assertEqual(result['acceptance_status'], 'accepted' if status == 'matched' else 'rejected')

    def test_strict_host_rejects_failed_controls_even_with_rehashed_receipt(self):
        raw = emit(); encoded, hashes, modules = envelope(raw)
        lines = raw.splitlines(keepends=True); lines[6] = b'PV-05: [X2]\n'
        for invalid in (raw.replace(b'PV-01: [S/', b'PV-01: [E/', 1), b''.join(lines)):
            forged = json.loads(encoded); stage = forged['report']['stage3']
            for record in (stage['cases'][0], stage['client_tree']):
                record.update(output_sha256=full.digest(invalid), output_size=len(invalid))
            forged['outputs'][0].update(size=len(invalid), sha256=full.digest(invalid), data_b64=base64.b64encode(invalid).decode())
            with self.assertRaises(host.TreeError):
                host.validate_envelope(budget.wire(forged), NONCE, hashes, modules, smoke.validate_report, profile=PROFILE)
            for site in ('server', 'client'):
                diagnostic = tree.observation_diagnostic(invalid, site, profile=PROFILE)
                self.assertEqual(diagnostic['category'], 'api_controls')
                tree.validate_diagnostic(diagnostic, profile=PROFILE); host.validate_diagnostic(diagnostic, profile=PROFILE)
                with self.assertRaises(tree.ObservationFailure):
                    tree.validate_observations(invalid, site, profile=PROFILE)

    def test_identity_and_client_lifecycle_tampering_is_rejected(self):
        encoded, hashes, modules = envelope(emit())
        for key in ('nonce', 'profile'):
            value = json.loads(encoded); value[key] = 'wrong'
            with self.assertRaises(host.TreeError):
                host.validate_envelope(budget.wire(value), NONCE, hashes, modules, smoke.validate_report, profile=PROFILE)
        value = json.loads(encoded); value['report']['stage3']['client_tree']['quiet'] = False
        with self.assertRaises(host.TreeError):
            host.validate_envelope(budget.wire(value), NONCE, hashes, modules, smoke.validate_report, profile=PROFILE)

    def test_emitter_and_bootstrap_dispatch_remain_closed(self):
        import test_native_tree_emitter_dispatch as emitter
        import run_stage
        finish = mock.Mock(return_value=b'fixed\n'); raw, error = emitter.execute(emitter.arguments('property-transfer'), finish)
        self.assertEqual((raw, error.code), (b'fixed\n', 0)); self.assertEqual(finish.call_args.kwargs['profile'], PROFILE)
        for lead in ('if tree_mode not in ', 'if tree_mode in '):
            line = next(line for line in emitter.EMITTER.splitlines() if line.startswith(lead)); member = ', "property-transfer"'
            self.assertEqual(line.count(member), 1); finish.reset_mock()
            emitter.execute(emitter.arguments('property-transfer'), finish, emitter.EMITTER.replace(line, line.replace(member, '')))
            finish.assert_not_called()
        with tempfile.TemporaryDirectory(prefix='property-dispatch-') as tmp, mock.patch.object(run_stage, 'ROOT', Path(tmp)), mock.patch.object(run_stage, 'run', return_value=run_stage.empty_report()) as run, contextlib.redirect_stdout(io.StringIO()):
            run_stage.main(['--property-transfer-suite', '--invocation-nonce', NONCE]); run.assert_called_once()
            self.assertTrue(run.call_args.kwargs['tree_suite']); self.assertEqual(run.call_args.kwargs['tree_profile'], PROFILE)
        with mock.patch.object(run_stage, 'run') as run:
            for extra in ('--property-transfer-suite', '--tree-suite', '--client-probe', 'source.bsl'):
                self.assertEqual(run_stage.main(['--property-transfer-suite', '--invocation-nonce', NONCE, extra]), 2)
            run.assert_not_called()

    def test_cli_requires_parity_and_has_no_acquisition_bypass(self):
        for acquired, parity in [(True, False), (True, True), (False, False)]:
            report = dict(native_measurement_accepted=acquired, runtime_parity_accepted=parity)
            with tempfile.TemporaryDirectory(prefix='property-cli-') as tmp, mock.patch.object(host, 'ROOT', Path(tmp)), mock.patch.object(host, 'run', return_value=report), mock.patch.object(sys, 'argv', ['host', '--execute-approved-image', '--profile', PROFILE]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(host.main(), 0 if parity else 1)
                saved = json.loads((Path(tmp)/'native-smoke/property-transfer-report.json').read_text())
                self.assertEqual(saved, report)
        for flags in (['--profile', 'property-transfer-v2'], ['--profile', PROFILE, '--profile', PROFILE], ['--acquisition-only']):
            with mock.patch.object(host, 'run') as run, mock.patch.object(sys, 'argv', ['host', '--execute-approved-image']+flags), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                host.main()
            self.assertEqual(error.exception.code, 2); run.assert_not_called()

    def test_complete_rectangular_budgets_and_exact_workflow_entry(self):
        s = spec(); stage = budget.stage_majorant()
        stage.update(schema=s.stage_schema, profile=PROFILE, failed_case=s.case, input_sha256=dict.fromkeys(tree.input_files(profile=PROFILE), budget.H))
        stage['cases'][0]['name'] = s.case
        native = budget.native_majorant(); native['stage3'] = stage
        report = budget.host_majorant(); report.update(profile=PROFILE, trusted_input_sha256=stage['input_sha256'], native_report=native)
        report['host_source_sha256']['scripts/native_1c_property_transfer_contract.py'] = budget.H
        report['comparison'].update(profile=PROFILE, native_property_transfer_available=False)
        report['observation_diagnostic'] = stage['observation_diagnostic']; report['status'] = 'failed'
        provenance = budget.wire(report)+b'\n'; report['native_artifact_sha256'] = dict.fromkeys((s.case+'.out', 'provenance.json'), budget.H)
        transport = dict(schema=s.schema, profile=PROFILE, nonce=NONCE, report=native, outputs=[dict(name=s.case+'.out', size=8192, sha256=budget.H, data_b64=base64.b64encode(b'x'*8192).decode())])
        bounds = {'stage': len(budget.wire(stage)), 'native': len(budget.wire(native)), 'transport': len(budget.wire(transport))+1, 'host': len(budget.wire(report))+1, 'provenance': len(provenance)}
        for key, cap in [('stage',8192), ('native',32768), ('transport',65536), ('host',32768), ('provenance',32768)]:
            self.assertLessEqual(bounds[key], cap, (key, bounds))
        workflow = (ROOT/'.github/workflows/native-1c-isolated-smoke.yml').read_text(encoding='utf-8')
        self.assertEqual(workflow.count('- profile: '+PROFILE), 1)
        self.assertIn('artifact: property-transfer\n            case: property_transfer', workflow)
        self.assertNotIn('--acquisition-only', workflow)


if __name__ == '__main__':
    unittest.main()
