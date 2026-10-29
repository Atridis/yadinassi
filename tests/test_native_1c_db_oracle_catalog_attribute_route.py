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

FLAG = '--config-catalog-attribute-binding'
OPTION = {'config_catalog_attribute_binding': True}
NONCE = old.NONCE
host = old.host
OLD_OPTIONS = ('record_metadata', 'record_reader', 'params_transport', 'params_extraction',
    'dbnames_identity', 'config_transport', 'config_framing', 'config_marker_census',
    'config_zero_marker_filename', 'config_entry_reference', 'config_blob_chain',
    'config_content_decode', 'config_root_reference_projection', 'config_catalog_observation',
    'config_catalog_name_binding', 'config_catalog_standard_binding',
    'config_catalog_identity_binding', 'config_catalog_field_matrix')


def identity():
    value = previous.identity()
    value['sources'] = inputs.source_hashes(ROOT, **OPTION)
    return value


class CatalogAttributeRoutingTests(unittest.TestCase):
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
        expected = (set(inputs.CONFIG_CATALOG_FIELD_MATRIX_SOURCE_FILES)
            - {'scripts/native_1c_db_oracle/config_catalog_field_matrix.py'}
            | {'scripts/native_1c_db_oracle/config_catalog_attribute_binding.py',
               'yadinassi/storage/config_catalog_attributes.py'})
        self.assertEqual(set(current), expected)
        self.assertEqual(len(current), 28)
        self.assertEqual(len(set(current.values())), 28)
        self.assertEqual(len(inputs.CONFIG_CATALOG_FIELD_MATRIX_SOURCE_FILES), 27)
        for name in OLD_OPTIONS:
            old_files = inputs.inventory(**{name: True})
            self.assertNotIn('yadinassi/storage/config_catalog_attributes.py', old_files)
            self.assertNotIn('scripts/native_1c_db_oracle/config_catalog_attribute_binding.py', old_files)
            with self.assertRaises(OracleError): inputs.inventory(**OPTION, **{name: True})
        for bad in (1, None, 'true', (), []):
            with self.assertRaises(OracleError): inputs.inventory(config_catalog_attribute_binding=bad)

    def test_invocation_twenty_two_exact_closed_stage_and_container_command(self):
        staged, value = self.stage()
        self.assertEqual(inputs.verify_inputs(staged, NONCE, **OPTION), value)
        invocation = json.loads((staged / 'invocation.json').read_bytes())
        self.assertEqual(invocation['schema'], 22)
        self.assertEqual(invocation['lane'], inputs.CONFIG_CATALOG_ATTRIBUTE_LANE)
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
        changes = [lambda v, n=n: v.update(schema=n) for n in (True, 13, 14, 15, 16, 17, 18, 19, 20, 21)]
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
        path = staged / 'config_catalog_attributes.py'
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
            'import config_catalog_attribute_binding as p;import config_root_projection;'
            'assert p.SCHEMA==35 and p.CAPTURE_SCHEMA==36;'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print("closed")')
        env = {key: value for key, value in os.environ.items()
               if key.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(staged)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertIn(result.stdout, (b'closed\n', b'closed\r\n'))


    def test_cold_staged_relative_sibling_loader_parses_real_private_bytes(self):
        from test_config_catalog_attributes import document, attribute, UUID1, UUID2
        staged, _ = self.stage()
        raw = document([attribute(UUID1, '"Text"', '{"Pattern",{"S",7,1}}'),
                        attribute(UUID2, '"Number"', '{"Pattern",{"N",17,5,1}}')])
        code = ('import sys;sys.path.insert(0,sys.argv[1]);'
            'import config_framing_reader as f;import filedb_catalog as c;import config_catalog_name as n;'
            'p=f.load_catalog_attribute_projector();'
            'assert p is f.load_catalog_attribute_projector();'
            'assert p._Cursor is n._Cursor;'
            'r=p.project_catalog_attributes(sys.stdin.buffer.read(),budget=c._Budget(c.CatalogLimits()));'
            'assert [(x.name,x.type_token,x.qualifiers) for x in r.attributes] == '
            '[("Text","S",(7,1)),("Number","N",(17,5,1))];'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print("parsed")')
        env = {key: value for key, value in os.environ.items()
               if key.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP')}
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(staged)],
            input=raw, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b'')
        self.assertIn(result.stdout, (b'parsed\n', b'parsed\r\n'))

    def test_host_cli_is_explicit_and_mutually_exclusive(self):
        with mock.patch.object(host, 'ROOT', self.root), \
             mock.patch.object(host, 'run_oracle', return_value={'accepted': False}) as run, \
             mock.patch.object(host, 'export_report'), mock.patch.dict(os.environ, {}, clear=True), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(host.main(['--execute-approved-image', '--file-db-oracle', FLAG]), 1)
            self.assertEqual(run.call_args.kwargs, OPTION)
            for other in ('--config-content-decode-observation', '--config-blob-chain-observation',
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


    def test_native_and_controller_select_policy_without_native_execution(self):
        import config_catalog_attribute_binding as policy
        value = identity()
        native = stages.stage.Native(NONCE, value, **OPTION)
        self.assertIs(native.params_policy, policy)
        self.assertTrue(native.catalog_field_matrix)
        self.assertFalse(stages.stage.Native(NONCE, value).catalog_field_matrix)
        report = policy.empty_report(NONCE, value)
        controller = stages.stage.Controller(mock.Mock(), report)
        self.assertIs(controller.params_policy, policy)
        self.assertIsNotNone(controller.observation)
        for name in OLD_OPTIONS:
            with self.assertRaises(OracleError):
                stages.stage.Native(NONCE, value, **OPTION, **{name: True})
        for bad in (1, None, 'true'):
            with self.assertRaises(OracleError):
                stages.stage.Native(NONCE, value, config_catalog_attribute_binding=bad)


    def test_runtime_main_exact_selection_and_no_policy_guessing(self):
        import config_catalog_attribute_binding as policy
        value = identity()
        result = policy.empty_report(NONCE, value)
        result['status'] = 'failed'
        output = io.BytesIO()
        with mock.patch.object(sys, 'argv', ['run.py', '--invocation-nonce', NONCE, FLAG]), \
             mock.patch.object(inputs, 'verify_inputs', return_value=value) as verify, \
             mock.patch.object(stages.stage, 'Native') as native, \
             mock.patch.object(stages.stage, 'Controller', return_value=types.SimpleNamespace(run=lambda: result)), \
             mock.patch.object(policy, 'validate_report') as validate, \
             mock.patch.object(sys, 'stdout', types.SimpleNamespace(buffer=output)):
            self.assertEqual(stages.stage.main(), 1)
        self.assertEqual(verify.call_args.kwargs, OPTION)
        self.assertEqual(native.call_args.kwargs, OPTION)
        self.assertEqual(json.loads(output.getvalue())['schema'], 35)
        validate.assert_called_once()
        for flags in ([FLAG, '--config-content-decode-observation'], [FLAG + '=1'], ['--config-root-reference-observation']):
            with mock.patch.object(sys, 'argv', ['run.py', '--invocation-nonce', NONCE] + flags), \
                 mock.patch.object(stages.stage, 'Native') as native:
                self.assertEqual(stages.stage.main(), 2)
                native.assert_not_called()


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
