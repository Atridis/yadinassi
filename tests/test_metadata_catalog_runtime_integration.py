"""Synthetic envelope and acquisition controls; never launches Docker or 1C."""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import test_metadata_catalog_runner as baseline_tests
import test_metadata_catalog_runtime_replay as replay_tests
import metadata_catalog_runtime_acquisition as acquisition
import metadata_catalog_runtime_inputs as inputs
import metadata_catalog_runtime_report as policy
import metadata_catalog_runtime_readback as readback
import metadata_catalog_runtime_run as runner
import metadata_catalog_acquisition as measurement
import native_1c_metadata_catalog_runtime_oracle as host
import protocol
from snapshots import OracleError

ROOT = Path(__file__).resolve().parents[1]
NONCE = baseline_tests.stages.NONCE


def isolated_bootstrap_environment():
    # Windows may require these loader variables even with an absolute Python
    # executable. Do not propagate credentials or ambient Python search paths.
    result={key:value for key,value in os.environ.items()
            if key.upper() in ('SYSTEMROOT', 'WINDIR')}
    result['PATH']=''
    return result


def identity():
    value = baseline_tests.stages.provenance()
    value['sources'] = {name: 'a' * 64 for name in inputs.SOURCE_FILES}
    return value


def report():
    value = baseline_tests.report()
    value['lane'] = inputs.LANE
    value['lifecycle']['provenance'] = identity()
    value['lifecycle']['provenance']['actual_version'] = protocol.VERSION
    value['runtime_identity'] = inputs.runtime_identity(identity())
    value['runtime_readbacks'] = []
    captures = json.loads(replay_tests.CAPTURE.read_bytes())
    for state, capture in zip(value['states'], captures):
        state['wire'] = replay_tests.native_wire(capture['rows']).decode('ascii')
        state['comparison'] = measurement.compare(measurement.wire.validate_output(state['wire'].encode()), state['config'])
        rows = copy.deepcopy(capture['rows'])
        for row in rows[6:8]: row.update(status='action-error', kind=None, value=None)
        actual = replay_tests.native_wire(rows)
        value['runtime_readbacks'].append(dict(snapshot=state['snapshot'], context=state['context'],
            token=state['token'], postimage=copy.deepcopy(state['postimage']), probe_sha256=readback.PROBE_SHA256,
            wire=actual.decode('ascii'), comparison=readback.compare_readback(actual, state['wire'].encode('ascii'))))
    return value


class RuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            from test_metadata_catalog_runtime_inputs import static_bundle_bytes
            patcher = mock.patch.object(inputs, '_read', new=static_bundle_bytes)
            patcher.start()
            self.addCleanup(patcher.stop)

    def validate(self, value):
        return policy.validate_report(policy.encode_report(value), nonce=NONCE, provenance=identity())

    def test_separate_complete_runtime_envelope(self):
        value = self.validate(report())
        self.assertEqual(len(value['runtime_readbacks']), 6)
        self.assertTrue(all(row['comparison']['supported_match'] for row in value['runtime_readbacks']))
        self.assertTrue(all(row['comparison']['payload_matches'] for row in value['states']))

    def test_forged_missing_reordered_or_wrong_postimage_runtime_rejected(self):
        for mutate in (
            lambda v: v['runtime_readbacks'][0]['postimage'].update(sha256='e' * 64),
            lambda v: v['runtime_readbacks'][0].update(token='f' * 32),
            lambda v: v['runtime_readbacks'][0]['comparison'].update(supported_match=False),
            lambda v: v['runtime_readbacks'][0]['comparison'].update(supported_match=1),
            lambda v: v['runtime_readbacks'][0]['comparison']['matched_ids'].__setitem__(0,True),
            lambda v: v['runtime_readbacks'][0].update(probe_sha256='f' * 64),
            lambda v: v.update(runtime_readbacks=v['runtime_readbacks'][:-1]),
            lambda v: v.update(runtime_readbacks=v['runtime_readbacks'][::-1]),
            lambda v: v['runtime_identity']['dependencies'].update(pyuca='0'),
            lambda v: v['runtime_identity'].update(bundle_manifest_sha256='e' * 64),
        ):
            value = report(); mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises((OracleError, ValueError)):
                self.validate(value)

    def test_real_mismatch_with_honest_comparison_cannot_be_accepted(self):
        value = report(); row = value['runtime_readbacks'][0]
        row['wire'] = row['wire'].replace('MC-20: [ok|B1]', 'MC-20: [ok|B0]')
        row['comparison'] = readback.compare_readback(row['wire'].encode(), value['states'][0]['wire'].encode())
        self.assertEqual(row['comparison']['mismatched_ids'], [20])
        with self.assertRaises(OracleError): self.validate(value)

    def test_runtime_constructive_caps(self):
        value = report()
        self.assertLess(len(policy.encode_report(value)), policy.MAX_REPORT_BYTES)
        largest = measurement.wire.C1 + measurement.wire.C2 + b''.join(
            f'MC-{i:02}: [ok|S64:'.encode() + b'0061' * 64 + b']\n' for i in range(1,27))
        for row in value['runtime_readbacks']: row['wire'] = largest.decode('ascii')
        self.assertLess(len(policy.encode_report(value)), policy.MAX_REPORT_BYTES)
        for mutate in (lambda v: v['runtime_readbacks'][0].update(wire='x' * acquisition.MAX_READBACK_STATE_BYTES),
                       lambda v: v.update(runtime_readbacks=v['runtime_readbacks'] * 2),
                       lambda v: v['runtime_identity'].update(extra='x' * 2048)):
            value = report(); mutate(value)
            with self.assertRaises(OracleError): policy.encode_report(value)

    def test_host_closed_command_and_no_credentials_cleanup(self):
        ident = identity(); ident['sources'] = inputs.source_hashes(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            inputs.stage_inputs(ROOT, staged, NONCE, ident)
            command = host.container_command(staged, 'onec-db-oracle-' + 'd' * 32, NONCE)
            self.assertEqual(command[command.index('--network') + 1], 'none')
            self.assertEqual(command[command.index('--user') + 1], '1000:1000')
            self.assertEqual(command[-7:], ['python3','-I','-S','-B','/oracle/metadata_catalog_runtime_run.py',
                                            '--invocation-nonce',NONCE])
            self.assertEqual(command.count('--mount'), 1)
            for flag in ('--read-only','--cap-drop','--init','--tmpfs'):
                self.assertIn(flag, command)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(host,'provenance',return_value=ident), \
             mock.patch.dict(host.os.environ,{},clear=True), \
             mock.patch.object(host.smoke,'run_silent') as external:
            value = host.run_oracle(Path(directory).resolve())
            self.assertEqual(list(Path(directory).iterdir()), [])
        external.assert_not_called()
        self.assertEqual(value['lifecycle']['failure_kind'], 'registry_credentials_missing')
        self.assertTrue(all(value['lifecycle']['cleanup'].values()))
        self.assertEqual(value['runtime_readbacks'], [])
        self.assertFalse(value['lifecycle']['accepted'])

    def test_cold_environment_preserves_loader_variables_not_secrets_or_python_paths(self):
        with mock.patch.dict(os.environ, {'SystemRoot':'C:\\Windows', 'WINDIR':'C:\\Windows',
             'GHCR_TOKEN':'sentinel', 'PYTHONPATH':'ambient', 'PYTHONHOME':'ambient'}, clear=True):
            value=isolated_bootstrap_environment()
        self.assertEqual({key.upper():item for key,item in value.items()},
                         {'SYSTEMROOT':'C:\\Windows', 'WINDIR':'C:\\Windows', 'PATH':''})

    def test_actual_isolated_entrypoint_bootstrap_and_required_flags(self):
        import subprocess
        import sys
        ident = identity(); ident['sources'] = inputs.source_hashes(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            inputs.stage_inputs(ROOT,staged,NONCE,ident)
            script = staged / 'metadata_catalog_runtime_run.py'
            result = subprocess.run([sys.executable,'-I','-S','-B',str(script)],
                cwd=Path(tempfile.gettempdir()), env=isolated_bootstrap_environment(),
                capture_output=True, timeout=10)
        # Missing closed invocation args, not an import failure under isolation.
        self.assertEqual(result.returncode,2,result.stderr.decode())
        self.assertEqual(result.stdout,b'')
        self.assertEqual(result.stderr,b'')
        with mock.patch.object(runner.sys, 'argv', ['runtime','--invocation-nonce',NONCE]):
            self.assertEqual(runner.main(),2)

    def test_public_readback_same_envelope_and_failure_cleanup(self):
        image = baseline_tests.fixture.source()
        summary = dict(bytes=image.size, sha256='a' * 64)
        native = replay_tests.native_wire(json.loads(replay_tests.CAPTURE.read_bytes())[0]['rows'])
        events = []
        class Backend:
            stage = 'update'; nonce = NONCE; artifacts = Path('/synthetic-only')
            def remaining(self): pass
            def physical_summary(self, path): return dict(summary, header='unknown', page_analysis='unsupported')
            @contextmanager
            def temporary_clone(self, *args):
                try: yield self.artifacts / 'auditor'
                finally: events.append('clone-removed')
            @contextmanager
            def command_context(self, *args): yield
            def quiescent(self): return True
            def budgets(self, *args): pass
            def remove(self, path): events.append('frozen-removed')
        def launch(database, context, token):
            return json.dumps(dict(schema=1,nonce=NONCE,token=token,operation='metadata_catalog_'+context,
                                   status='ok',output=native.decode())).encode()
        def inspect(path, **kwargs):
            events.append('envelope')
            result = kwargs['read_catalog'](image.read_at, image.size, limits=kwargs['limits'])
            return summary.copy(), result
        actual = dict(probe_sha256=readback.PROBE_SHA256, wire=native.decode(),
                      comparison=readback.compare_readback(native,native))
        for error in (False, True):
            events.clear(); backend = Backend()
            with mock.patch.object(acquisition,'freeze_database',return_value=summary), \
                 mock.patch.object(acquisition,'inspect_frozen_catalog',side_effect=inspect), \
                 mock.patch.object(baseline_tests.runner.lifecycle,'absent'), \
                 mock.patch.object(readback,'readback',side_effect=ValueError('readback failed') if error else None,
                                   return_value=actual) as public:
                if error:
                    with self.assertRaises(ValueError): acquisition.acquire(backend,'updated',launch=launch)
                    self.assertEqual(backend.metadata_attempt['phase'], 'runtime')
                else:
                    states, rows = acquisition.acquire(backend,'updated',launch=launch)
                    self.assertEqual(len(rows),2)
                    self.assertEqual([row['postimage'] for row in rows], [summary,summary])
                    self.assertEqual(public.call_count,2)
                public.assert_called_with(backend.artifacts / 'auditor_frozen', native_wire=native)
            self.assertEqual(events[-2:], ['frozen-removed','clone-removed'])

if __name__ == '__main__': unittest.main()
