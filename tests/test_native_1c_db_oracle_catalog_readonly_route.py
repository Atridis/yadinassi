"""Closed opt-in attribute route. Offline stubs only; no native acceptance."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts/native_1c_db_oracle'),
               str(ROOT / 'yadinassi/storage'), str(ROOT / 'scripts'), str(ROOT / 'tests')]
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as stages
import test_native_1c_db_oracle_record_route as old
import test_native_1c_db_oracle_config_content_decode_policy as previous

FLAG = '--catalog-readonly-binding'
OPTION = {'catalog_readonly_binding': True}
NONCE = old.NONCE
host = old.host
OLD_OPTIONS = ('record_metadata', 'record_reader', 'params_transport', 'params_extraction',
    'dbnames_identity', 'config_transport', 'config_framing', 'config_marker_census',
    'config_zero_marker_filename', 'config_entry_reference', 'config_blob_chain',
    'config_content_decode', 'config_root_reference_projection', 'config_catalog_observation',
    'config_catalog_name_binding', 'config_catalog_standard_binding',
    'config_catalog_identity_binding', 'config_catalog_field_matrix', 'config_catalog_attribute_binding')


def identity():
    value = previous.identity()
    value['sources'] = inputs.source_hashes(ROOT, **OPTION)
    return value


class CatalogReadonlyRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: old.writable(self.root))


    def stage(self):
        staged = self.root / 'inputs'
        value = identity()
        inputs.stage_inputs(ROOT, staged, NONCE, value, **OPTION)
        return staged, value


    def test_closed_inventory_and_old_lanes_unchanged(self):
        current = inputs.inventory(**OPTION)
        expected = (set(inputs.CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES)
            | {'yadinassi/storage/filedb_named_file.py', 'yadinassi/storage/filedb_dbnames.py',
               'yadinassi/storage/filedb_records.py', 'yadinassi/storage/config_catalog_binding.py',
               'yadinassi/storage/config_catalog_records.py',
               'scripts/native_1c_db_oracle/catalog_binding_reader.py',
               'scripts/native_1c_db_oracle/catalog_readonly_binding.py'})
        self.assertEqual(set(current), expected)
        self.assertEqual(len(current), 35)
        self.assertEqual(len(current), len(set(current.values())))
        self.assertEqual(len(inputs.CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES), 28)
        for name in OLD_OPTIONS:
            old_files = inputs.inventory(**{name: True})
            self.assertNotIn('yadinassi/storage/config_catalog_binding.py', old_files)
            self.assertNotIn('scripts/native_1c_db_oracle/catalog_readonly_binding.py', old_files)
            with self.assertRaises(OracleError): inputs.inventory(**OPTION, **{name: True})
        for bad in (1, None, 'true', (), []):
            with self.assertRaises(OracleError): inputs.inventory(catalog_readonly_binding=bad)

    def test_invocation_twenty_three_exact_closed_stage_and_container_command(self):
        staged, value = self.stage()
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)
        invocation = json.loads((staged / 'invocation.json').read_bytes())
        self.assertEqual(invocation['schema'], 23)
        self.assertEqual(invocation['lane'], inputs.CATALOG_BINDING_LANE)
        self.assertTrue((staged / 'config_root_projection.py').is_file())
        self.assertFalse((staged / 'config_content_decode.py').exists())
        self.assertFalse((staged / 'config_root_reference.py').exists())
        self.assertFalse((staged / 'config_root_diagnostic.py').exists())
        command = host.container_command(staged, 'onec-db-oracle-' + 'a' * 32, NONCE, **OPTION)
        self.assertEqual(command[-1], FLAG)
        self.assertEqual(command[command.index('--network') + 1], 'none')
        self.assertIn('--read-only', command)
        self.assertIn('no-new-privileges:true', command)
        for name in OLD_OPTIONS:
            with self.assertRaises(OracleError):
                inputs.verify_inputs(staged, NONCE, **{name: True})


    def test_invocation_stale_schemas_and_tampering_rejected(self):
        staged, value = self.stage()
        old.writable(staged)
        path = staged / 'invocation.json'
        original = json.loads(path.read_bytes())
        changes = [lambda v, n=n: v.update(schema=n) for n in (True, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22)]
        changes += [lambda v: v.update(lane=inputs.CONFIG_CONTENT_DECODE_LANE),
            lambda v: v.update(extra='PRIVATE'), lambda v: v.pop('lane'),
            lambda v: v['provenance']['sources'].pop('yadinassi/storage/config_catalog_references.py'),
            lambda v: v['provenance']['sources'].update({'foreign.py': 'f' * 64})]
        for change in changes:
            modified = copy.deepcopy(original)
            change(modified)
            path.write_bytes(protocol.encode(modified))
            with self.assertRaises(OracleError):
                inputs.verify_inputs(staged, NONCE, **OPTION)
        path.write_bytes(protocol.encode(original))
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)


    def test_missing_changed_or_extra_projector_rejected(self):
        staged, value = self.stage()
        old.writable(staged)
        path = staged / 'config_catalog_binding.py'
        original = path.read_bytes()
        for mode in ('changed', 'missing', 'foreign'):
            if mode == 'changed': path.write_bytes(original + b'\n')
            elif mode == 'missing': path.unlink()
            else: (staged / 'foreign.py').write_bytes(b'not admitted')
            with self.subTest(mode=mode), self.assertRaises(OracleError):
                inputs.verify_inputs(staged, NONCE, **OPTION)
            path.write_bytes(original)
            if mode == 'foreign': (staged / 'foreign.py').unlink()
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)


    def test_cold_staged_policy_import_requires_no_interpreter(self):
        staged, _ = self.stage()
        code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'import catalog_readonly_binding as p;import catalog_binding_reader as r;'
            'modules=r._load_storage();'
            'assert set(modules)=={"filedb_named_file","filedb_dbnames","filedb_records","config_catalog_binding","config_catalog_records"};'
            'assert p.SCHEMA==37 and p.CAPTURE_SCHEMA==38;'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print("closed")')
        env = {key: value for key, value in os.environ.items()
               if key.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(staged)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertIn(result.stdout, (b'closed\n', b'closed\r\n'))


    def test_host_cli_is_explicit_and_mutually_exclusive(self):
        with mock.patch.object(host, 'ROOT', self.root), \
             mock.patch.object(host, 'run_oracle', return_value={'accepted': False}) as run, \
             mock.patch.object(host, 'export_report'), mock.patch.dict(os.environ, {}, clear=True), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(host.main(['--execute-approved-image', '--file-db-oracle', FLAG]), 1)
            self.assertEqual(run.call_args.kwargs, OPTION)
            for other in ('--config-catalog-attribute-binding', '--config-content-decode-observation', '--config-blob-chain-observation',
                          '--config-entry-reference-observation', '--record-metadata-observation'):
                run.reset_mock()
                with self.assertRaises(SystemExit):
                    host.main(['--execute-approved-image', '--file-db-oracle', FLAG, other])
                run.assert_not_called()
            for flags in ([FLAG], ['--execute-approved-image', FLAG],
                          ['--execute-approved-image', '--file-db-oracle', FLAG + '=1']):
                run.reset_mock()
                with self.assertRaises(SystemExit): host.main(flags)
                run.assert_not_called()


    def test_host_failure_discards_only_new_policy_capture(self):
        policy = types.SimpleNamespace(discard_capture=mock.Mock())
        value = previous.identity()
        report = protocol.empty_report(NONCE, value)
        report['schema'] = 37
        with mock.patch.dict(sys.modules, {'catalog_readonly_binding': policy}):
            host.fail_report(report, 'invalid_input')
        policy.discard_capture.assert_called_once_with(report, final=True)
        self.assertEqual(report['failure_kind'], 'invalid_input')

    def test_native_and_controller_select_only_new_record_policy(self):
        import catalog_readonly_binding as policy
        import catalog_binding_reader as reader
        value = identity()
        native = stages.stage.Native(NONCE, value, **OPTION)
        self.assertTrue(native.catalog_binding)
        self.assertTrue(native.catalog_field_matrix)
        self.assertIs(native.record_policy, policy)
        self.assertIs(native.record_module, reader)
        self.assertIsNone(native.params_policy)
        report = policy.empty_report(NONCE, value)
        controller = stages.stage.Controller(mock.Mock(), report)
        self.assertIs(controller.record_policy, policy)
        self.assertIsNone(controller.params_policy)

    def test_native_new_option_rejects_other_lanes_and_non_bools(self):
        value = identity()
        for name in OLD_OPTIONS:
            with self.subTest(name=name), self.assertRaises(OracleError):
                stages.stage.Native(NONCE, value, **OPTION, **{name: True})
        for bad in (1, None, 'true'):
            with self.subTest(bad=bad), self.assertRaises(OracleError):
                stages.stage.Native(NONCE, value, catalog_readonly_binding=bad)

    @unittest.skipIf(os.name == 'nt', 'POSIX shell launcher')
    def test_shell_whitelist_forwards_only_single_exact_flag(self):
        stub = self.root / 'python3'
        stub.write_bytes(b'#!/bin/sh\nprintf "%s\\n" "$@"\n')
        stub.chmod(0o755)
        command = ['/bin/bash', str(ROOT / 'scripts/native_1c_db_oracle/probe.sh'), '--invocation-nonce', NONCE]
        for flags, expected in (([], 0), ([FLAG], 0), ([FLAG, '--config-content-decode-observation'], 2),
                                ([FLAG + '=1'], 2), (['--config-root-reference-observation'], 2)):
            result = subprocess.run(command + flags, env={'PATH': str(self.root)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            self.assertEqual(result.returncode, expected)
            self.assertEqual(result.stderr, b'')
            wanted = ('\n'.join(['-B', '/oracle/run.py', '--invocation-nonce', NONCE] + flags) + '\n').encode()
            self.assertEqual(result.stdout, wanted if expected == 0 else b'')



if __name__ == "__main__": unittest.main()
