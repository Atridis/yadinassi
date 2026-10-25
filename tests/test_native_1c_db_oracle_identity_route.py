"""Local identity route, exact staging and existing-redump binding; never 1C."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'), str(ROOT / 'yadinassi/storage'),
                str(ROOT / 'scripts'), str(ROOT / 'tests')]
import inputs
import dbnames_identity as policy
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_extraction as extraction
import test_native_1c_db_oracle_record_route as legacy
import test_native_1c_db_oracle_stage as stages

NONCE = 'a' * 32
host = legacy.host


def identity():
    result = stages.provenance()
    result['sources'] = {path: 'c' * 64 for path in inputs.IDENTITY_SOURCE_FILES}
    return result


class IdentityRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: legacy.writable(self.root))

    def test_exact_26_file_inventory_with_every_old_membership_unchanged(self):
        self.assertEqual(tuple(map(len, (inputs.LEGACY_V3_SOURCE_FILES, inputs.SOURCE_FILES,
            inputs.RECORD_SOURCE_FILES, inputs.ROW_SOURCE_FILES, inputs.PARAMS_SOURCE_FILES,
            inputs.EXTRACTION_SOURCE_FILES, inputs.IDENTITY_SOURCE_FILES))),
            (18, 20, 21, 23, 22, 24, 26))
        self.assertEqual(set(inputs.IDENTITY_SOURCE_FILES) - set(inputs.EXTRACTION_SOURCE_FILES),
            {'yadinassi/storage/filedb_dbnames.py', 'scripts/native_1c_db_oracle/dbnames_identity.py'})
        options = {'dbnames_identity': True}
        provenance = identity(); provenance['sources'] = inputs.source_hashes(ROOT, **options)
        target = self.root / 'stage'
        inputs.stage_inputs(ROOT, target, NONCE, provenance, **options)
        self.assertEqual(inputs.verify_inputs(target, NONCE, **options), provenance)
        invocation = json.loads((target / 'invocation.json').read_text(encoding='utf-8'))
        self.assertEqual((invocation['schema'], invocation['lane']), (6, policy.LANE))
        command = host.container_command(target, 'onec-db-oracle-' + 'b' * 32, NONCE, **options)
        self.assertEqual(command[-1], '--dbnames-identity-validation')
        self.assertIn('--network', command); self.assertEqual(command[command.index('--network') + 1], 'none')
        for wrong in ({}, {'record_metadata': True}, {'record_reader': True},
                      {'params_transport': True}, {'params_extraction': True}):
            with self.assertRaises(OracleError): inputs.verify_inputs(target, NONCE, **wrong)
        for name in ('record_metadata', 'record_reader', 'params_transport', 'params_extraction'):
            with self.assertRaises(OracleError): inputs.inventory(dbnames_identity=True, **{name: True})
        for bad in (0, 1, None, 'true'):
            with self.assertRaises(OracleError): inputs.inventory(dbnames_identity=bad)

    def test_host_cli_selects_only_explicit_new_flag(self):
        with mock.patch.object(host, 'ROOT', self.root), \
             mock.patch.object(host, 'run_oracle', return_value={'accepted': False}) as run, \
             mock.patch.object(host, 'export_report'), mock.patch.dict(os.environ, {}, clear=True), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            base = ['--execute-approved-image', '--file-db-oracle', '--dbnames-identity-validation']
            self.assertEqual(host.main(base), 1)
            self.assertEqual(run.call_args.kwargs, {'dbnames_identity': True})
            for flag in ('--params-dbnames-extraction', '--params-transport-observation',
                         '--record-reader-validation', '--record-metadata-observation'):
                with self.assertRaises(SystemExit): host.main(base + [flag])
            with self.assertRaises(SystemExit): host.main(base + ['--profile', 'arbitrary'])

    def test_container_main_selection_never_invokes_native_in_test(self):
        report = policy.empty_report(NONCE, identity()); report['status'] = 'failed'
        output = io.BytesIO()
        with mock.patch.object(sys, 'argv', ['run.py', '--invocation-nonce', NONCE, '--dbnames-identity-validation']), \
             mock.patch.object(inputs, 'verify_inputs', return_value=identity()) as verify, \
             mock.patch.object(stages.stage, 'Native') as native, \
             mock.patch.object(stages.stage, 'Controller', return_value=types.SimpleNamespace(run=lambda: report)), \
             mock.patch.object(policy, 'validate_report') as validate, \
             mock.patch.object(sys, 'stdout', types.SimpleNamespace(buffer=output)):
            self.assertEqual(stages.stage.main(), 1)
        self.assertEqual(native.call_args.kwargs, {'dbnames_identity': True})
        self.assertEqual(verify.call_args.kwargs, {'dbnames_identity': True})
        self.assertEqual(validate.call_count, 1)
        self.assertEqual(json.loads(output.getvalue())['lane'], policy.LANE)

    def native_shell(self):
        native = object.__new__(stages.stage.Native)
        native.root = self.root; native.counter = 0
        native.v1 = self.root / 'v1'; native.v2 = self.root / 'v2'
        native.nonce = NONCE; native.params_policy = policy
        native.identity_manifest = None; native.identity_baseline_verified = False
        native.stage = 'seed_v1'
        native.batch = mock.Mock(side_effect=lambda *a, **k: (self.root / 'redump-001').mkdir())
        return native

    def test_manifest_follows_existing_verified_redumps_without_extra_launches(self):
        native = self.native_shell(); manifest = {'schema': 1, 'owned': 'synthetic'}
        order = []
        with mock.patch.object(stages.stage, 'verify_redump', side_effect=lambda *a, **k: order.append('verified')), \
             mock.patch.object(policy, 'build_identity_manifest', side_effect=lambda *a, **k: order.append('manifest') or copy.deepcopy(manifest)):
            native.redump(self.root / 'seed', 1, user=None)
            self.assertEqual(native.identity_manifest, manifest)
            self.assertFalse(native.identity_baseline_verified)
            native.stage = 'baseline'; native.redump(self.root / 'observer', 1)
        self.assertEqual(order, ['verified', 'manifest', 'verified', 'manifest'])
        self.assertEqual(native.batch.call_count, 2)
        self.assertTrue(native.identity_baseline_verified)
        self.assertFalse((self.root / 'redump-001').exists())
        for call in native.batch.call_args_list:
            self.assertEqual(call.args[1][0], '/DumpConfigToFiles')

    def test_failed_redump_cannot_create_manifest_and_changed_manifest_fails(self):
        native = self.native_shell()
        with mock.patch.object(stages.stage, 'verify_redump', side_effect=ValueError('private')), \
             mock.patch.object(policy, 'build_identity_manifest') as build:
            with self.assertRaises(OracleError): native.redump(self.root / 'seed', 1)
        build.assert_not_called(); self.assertIsNone(native.identity_manifest)
        self.assertFalse((self.root / 'redump-001').exists())
        native.stage = 'baseline'; native.identity_manifest = {'value': 1}
        with mock.patch.object(stages.stage, 'verify_redump'), \
             mock.patch.object(policy, 'build_identity_manifest', return_value={'value': 2}):
            with self.assertRaises(OracleError): native.redump(self.root / 'observer', 1)
        self.assertFalse(native.identity_baseline_verified)
        self.assertFalse((self.root / 'redump-001').exists())

    def test_seed_manifest_failure_keeps_seed_diagnostic_not_baseline_capture(self):
        native = self.native_shell(); native.seed_pending = native.seed_launched = None
        def batch(*args, **kwargs):
            native.seed_launched = 'redump'
            (self.root / 'redump-001').mkdir()
        native.batch = batch
        with mock.patch.object(stages.stage, 'verify_redump'), \
             mock.patch.object(policy, 'build_identity_manifest',
                               side_effect=policy.ObservationFailure('identity_mismatch', 'xml_role_mismatch')):
            with self.assertRaises(stages.stage.SeedCommandError) as caught:
                with native.seed_command('redump'):
                    native.redump(self.root / 'seed', 1)
        self.assertEqual((caught.exception.operation, caught.exception.kind), ('redump', 'logical_mismatch'))
        self.assertIsNone(native.identity_manifest)
        self.assertFalse((self.root / 'redump-001').exists())

    def test_missing_manifest_blocks_auditor_before_native_or_reader_activity(self):
        native = self.native_shell(); native.stage = 'baseline'; native.observation = policy
        native.temporary_clone = mock.Mock(side_effect=AssertionError('unexpected clone'))
        with self.assertRaises(OracleError): native.observe_record_metadata('baseline')
        native.temporary_clone.assert_not_called()

    def test_other_modes_never_request_manifest(self):
        native = self.native_shell(); native.params_policy = extraction.policy
        with mock.patch.object(stages.stage, 'verify_redump'), \
             mock.patch.object(policy, 'build_identity_manifest') as build:
            native.redump(self.root / 'seed', 1)
        build.assert_not_called(); self.assertIsNone(native.identity_manifest)
        self.assertEqual(native.batch.call_count, 1)


if __name__ == '__main__':
    unittest.main()
