import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tree_profile_host_test', ROOT / 'scripts/native_1c_tree_profile.py')
HOST = importlib.util.module_from_spec(spec)
spec.loader.exec_module(HOST)


class TreeHostTests(unittest.TestCase):
    def test_rejects_malformed_envelopes(self):
        for raw in (b'{}', b'[]', b'{"schema":1,"schema":1}', b'null', b'x' * 65537):
            with self.subTest(raw=raw[:40]), self.assertRaises(HOST.TreeError):
                HOST.validate_envelope(raw, '1' * 32, {}, {}, lambda *a, **k: None)

    def test_nonce_is_not_coerced(self):
        for nonce in (None, 1, 'x' * 32, '1' * 31):
            with self.assertRaises(HOST.TreeError):
                HOST.validate_envelope(b'{}', nonce, {}, {}, lambda *a, **k: None)

    def test_source_is_fixed(self):
        self.assertEqual(HOST.FULL.digest((ROOT / HOST.SOURCE).read_text(encoding='utf-8').encode('utf-8')), HOST.SOURCE_SHA256)
        self.assertEqual(HOST.MESSAGE_COUNT, 33)

    def test_mapping_excludes_six_scenarios(self):
        smoke = HOST.sibling('native_1c_smoke')
        files = HOST.staged_files(smoke)
        self.assertEqual([p for p in files if p.startswith('integrational_tests/measurements/')], [HOST.SOURCE])
        self.assertFalse(any(p.startswith('integrational_tests/tests/') for p in files))
        self.assertEqual(len(files), len(set(files.values())))

    def test_full_inline_verdict_requires_tree(self):
        import os
        from unittest import mock
        text = (ROOT / '.github/workflows/native-1c-isolated-smoke.yml').read_text()
        begin = text.index('          # BEGIN NATIVE CI VERDICT')
        end = text.index('          PYTHON', begin)
        code = '\n'.join(line[10:] for line in text[begin:end].splitlines())
        for tree in ('success', 'failed', 'skipped', 'cancelled', ''):
            for required in ('true', 'false'):
                env = {'ELIGIBILITY_RESULT': 'success', 'NATIVE_RESULT': 'success',
                       'TREE_RESULT': tree, 'TREE_REQUIRED': required}
                with mock.patch.dict(os.environ, env, clear=True), mock.patch('builtins.print'):
                    with self.assertRaises(SystemExit) as result:
                        exec(code, {'os': os})
                self.assertEqual(result.exception.code, 0 if required == 'false' or tree == 'success' else 1)

    def test_raw_crlf_staging_source_is_rejected(self):
        from unittest import mock
        class Smoke:
            STAGED_FILES = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = (ROOT / HOST.SOURCE).read_text(encoding='utf-8').encode().replace(b'\n', b'\r\n')
            with mock.patch.object(HOST.FULL, 'read_regular', return_value=raw):
                with self.assertRaisesRegex(HOST.TreeError, 'tree_source_changed'):
                    HOST.stage_inputs(root, root / 'staged', Smoke)

    @unittest.skipUnless(__import__('sys').platform.startswith('linux'), 'atomic Linux artifact publisher')
    def test_artifact_publisher_is_exclusive_and_pinned(self):
        from unittest import mock
        files = {HOST.CASE + '.out': b'bounded', 'provenance.json': b'{}\n'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            HOST.export_artifact(root, files)
            self.assertEqual((root / 'native-smoke/tree-outputs' / (HOST.CASE + '.out')).read_bytes(), b'bounded')
            with self.assertRaises(HOST.FULL.FullError):
                HOST.export_artifact(root, files)
            self.assertEqual((root / 'native-smoke/tree-outputs' / (HOST.CASE + '.out')).read_bytes(), b'bounded')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            victim = root / 'victim'; victim.mkdir()
            (root / 'native-smoke').symlink_to(victim, target_is_directory=True)
            with self.assertRaises(HOST.FULL.FullError):
                HOST.export_artifact(root, files)
            self.assertEqual(list(victim.iterdir()), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def refuse(*args):
                raise HOST.FULL.FullError('synthetic_promotion_failure')
            with mock.patch.object(HOST.FULL, '_rename_artifact_exclusive', side_effect=refuse):
                with self.assertRaises(HOST.FULL.FullError):
                    HOST.export_artifact(root, files)
            self.assertEqual(list((root / 'native-smoke').iterdir()), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = HOST.FULL._rename_artifact_exclusive
            def swap(parent, source, destination):
                (root / 'native-smoke').rename(root / 'pinned-old')
                (root / 'native-smoke').mkdir()
                (root / 'native-smoke/sentinel').write_bytes(b'preserve')
                original(parent, source, destination)
            with mock.patch.object(HOST.FULL, '_rename_artifact_exclusive', side_effect=swap):
                with self.assertRaises(HOST.FULL.FullError):
                    HOST.export_artifact(root, files)
            self.assertEqual((root / 'native-smoke/sentinel').read_bytes(), b'preserve')
            self.assertEqual(list((root / 'pinned-old').iterdir()), [])

    def test_private_cleanup_failure_overrides_only_when_it_fails(self):
        from unittest import mock
        state={'stage':'comparison'}
        manager=mock.Mock(name='owned-private-directory')
        manager.name='unused-synthetic-path'
        with mock.patch.object(HOST.tempfile,'TemporaryDirectory',return_value=manager):
            with self.assertRaisesRegex(ValueError,'primary'):
                with HOST.private_work(Path('.'),state):
                    raise ValueError('primary')
        self.assertEqual(state['stage'],'comparison')
        manager.cleanup.side_effect=OSError('private path must never be exported')
        with mock.patch.object(HOST.tempfile,'TemporaryDirectory',return_value=manager):
            with self.assertRaises(OSError):
                with HOST.private_work(Path('.'),state):
                    raise ValueError('primary')
        self.assertEqual(state['stage'],'private_cleanup')

    def test_failure_diagnostics_are_closed_and_private(self):
        import json
        for secret in ('/private/account/token.txt', 'password=abc123', 'raw native output',
                       'docker_command_failed extra', 'unexpected\npath', '💥'):
            result = HOST.failure_diagnostic({'stage': secret}, RuntimeError(secret))
            self.assertEqual(result, {'stage': 'unknown', 'reason': 'unexpected_failure'})
            self.assertNotIn(secret, json.dumps(result))
        for stage in HOST.FAILURE_STAGES:
            for reason in HOST.FAILURE_REASONS:
                self.assertEqual(HOST.failure_diagnostic({'stage': stage}, HOST.TreeError(reason)),
                                 {'stage': stage, 'reason': reason})

    def test_lifecycle_failures_never_export(self):
        import contextlib
        import os
        from unittest import mock
        for failure in (None, 'container', 'cleanup', 'comparison', 'provenance'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
                root = Path(directory)
                smoke = HOST.sibling('native_1c_smoke')
                stack.enter_context(mock.patch.object(HOST, 'sibling', return_value=smoke))
                stack.enter_context(mock.patch.dict(os.environ, {'GHCR_TOKEN': 'synthetic-not-a-secret', 'GHCR_USER': 'Atridis'}))
                for name, result in (('repository_provenance', {'sha': 'a' * 40}),
                                     ('interpreter_provenance', {}), ('windows_fingerprints', {}),
                                     ('read_regular', b'host'), ('verify_client_interpreter', None)):
                    stack.enter_context(mock.patch.object(HOST.FULL, name, return_value=result))
                if failure == 'provenance':
                    HOST.FULL.repository_provenance.side_effect = [{'sha': 'a' * 40}, {'sha': 'b' * 40}]
                stack.enter_context(mock.patch.object(HOST, 'stage_inputs', return_value={HOST.SOURCE: HOST.SOURCE_SHA256, HOST.FULL.CLIENT_SOURCE: 'a' * 64}))
                stack.enter_context(mock.patch.object(HOST, 'module_hashes', return_value={}))
                stack.enter_context(mock.patch.object(HOST, 'validate_inputs'))
                stack.enter_context(mock.patch.object(HOST, 'container_command', return_value=['container']))
                stack.enter_context(mock.patch.object(HOST, 'validate_envelope', return_value=({}, b'observations')))
                comparison = stack.enter_context(mock.patch.object(HOST, 'compare_output', return_value={'acceptance_status': 'accepted'}))
                if failure == 'comparison':
                    comparison.side_effect = HOST.TreeError('test_failure')
                silent = stack.enter_context(mock.patch.object(smoke, 'run_silent'))
                outputs = [(0, b'linux/amd64|0'), (0, b'envelope'), (0, b'')]
                if failure == 'container':
                    outputs[1] = smoke.SmokeError('container_timeout')
                if failure == 'cleanup':
                    outputs[2] = (0, b'still-running')
                stack.enter_context(mock.patch.object(smoke, 'bounded_run', side_effect=outputs))
                export = stack.enter_context(mock.patch.object(HOST, 'export_artifact'))
                state = {}
                if failure:
                    with self.assertRaises((HOST.TreeError, smoke.SmokeError)):
                        HOST.run(root, root, export_native_outputs=True, failure_state=state)
                    export.assert_not_called()
                    self.assertEqual(state['stage'], {'container': 'container_run', 'cleanup': 'container_cleanup', 'comparison': 'comparison', 'provenance': 'final_provenance'}[failure])
                else:
                    result = HOST.run(root, root, export_native_outputs=True, failure_state=state)
                    self.assertTrue(result['private_payloads_removed'])
                    self.assertTrue(result['runtime_parity_accepted'])
                    export.assert_called_once()
                self.assertTrue(any(call.args[0][:3] == ['docker', 'rm', '--force'] for call in silent.call_args_list))
                self.assertFalse(list(root.glob('onec-tree-*')))

    def test_success_contract_and_tampered_witnesses(self):
        import base64
        import copy
        import json
        contract = HOST.CONTRACT
        lines = ['TF-C: [-]']
        for case in range(1, 33):
            before = contract.baseline(case)
            shared = before[:50] + 'R01Q0....' if case == 31 else before
            lines.append(f'TF-{case}: [E{before}{before}{shared}]')
        payload = ('\n'.join(lines) + '\n').encode()
        contract.validate_output(payload)
        digest = HOST.FULL.digest(payload)
        case = {'name': HOST.CASE, 'status': 'ok', 'source_sha256': HOST.SOURCE_SHA256,
                'module_sha256': 'a' * 64, 'output_sha256': digest, 'output_size': len(payload), 'message_count': 33}
        client = dict.fromkeys(HOST.FULL.CLIENT_FLAGS, True)
        client.update(status='ok', failure_kind='none', source_sha256=HOST.SOURCE_SHA256,
                      module_sha256='b' * 64, roundtrip_sha256='b' * 64,
                      output_sha256=digest, output_size=len(payload), message_count=33,
                      process_diagnostics={'stage': 'after_exit', 'reason': 'none', 'unexpected_count': 0,
                                           'zombie_count': 0, 'classes': dict.fromkeys(
                                               ('native', 'display', 'session_bus', 'shell', 'python', 'other', 'unreadable'), 0)})
        hashes = {HOST.SOURCE: HOST.SOURCE_SHA256}
        modules = {HOST.CASE: 'a' * 64, 'client_tree': 'b' * 64}
        stage = {'schema': HOST.STAGE_SCHEMA, 'profile': HOST.PROFILE, 'nonce': '1' * 32,
                 'status': 'ok', 'failure_kind': 'none', 'failed_case': None, 'input_sha256': hashes,
                 'cases': [case], 'client_tree': client, 'observation_diagnostic': None}
        envelope = {'schema': HOST.SCHEMA, 'profile': HOST.PROFILE, 'nonce': '1' * 32,
                    'report': {'status': 'ok', 'native_tests_completed': True, 'stage3': stage},
                    'outputs': [{'name': HOST.CASE + '.out', 'size': len(payload), 'sha256': digest,
                                 'data_b64': base64.b64encode(payload).decode()}]}
        def validate(value):
            return HOST.validate_envelope(json.dumps(value).encode(), '1' * 32, hashes, modules, lambda *a, **kw: None)
        self.assertEqual(validate(envelope)[1], payload)
        contradictory = copy.deepcopy(envelope)
        contradictory['report']['stage3']['observation_diagnostic'] = {
            'site': 'server', 'case': 1, 'category': 'probe_p', 'calibration': None}
        with self.assertRaises(HOST.TreeError) as rejected:
            validate(contradictory)
        self.assertFalse(hasattr(rejected.exception, 'observation_diagnostic'))
        failure = copy.deepcopy(contradictory)
        failure['report'].update(status='stage3_failed', native_tests_completed=False)
        fs = failure['report']['stage3']
        fs.update(status='failed', failure_kind='unsupported_observation', failed_case=HOST.CASE)
        fs['cases'][0].update(status='failed', module_sha256=None, output_sha256=None, output_size=None, message_count=None)
        fc = fs['client_tree']
        fc.update(dict.fromkeys(HOST.FULL.CLIENT_FLAGS, False))
        fc.update(dict.fromkeys(HOST.FULL.CLIENT_HASHES | HOST.FULL.CLIENT_OUTPUT_KEYS, None))
        fc.update(status='not_started', failure_kind='prerequisites_failed')
        fc['process_diagnostics']['stage'] = 'not_checked'
        failure['outputs'] = []
        with self.assertRaises(HOST.TreeError) as diagnostic:
            validate(failure)
        self.assertEqual(diagnostic.exception.observation_diagnostic['category'], 'probe_p')
        for key, value in (('source_sha256', 'c' * 64), ('name', 'wrong'), ('module_sha256', 'a' * 64)):
            wrong = copy.deepcopy(failure)
            wrong['report']['stage3']['cases'][0][key] = value
            with self.assertRaises(HOST.TreeError) as rejected:
                validate(wrong)
            self.assertFalse(hasattr(rejected.exception, 'observation_diagnostic'))
        native_failed = copy.deepcopy(failure)
        native_failed['report']['stage3'].update(observation_diagnostic=None, failure_kind='process_failed')
        with self.assertRaises(HOST.TreeError) as summary:
            validate(native_failed)
        self.assertEqual(summary.exception.native_failure, {'stage': 'tree', 'reason': 'process_failed',
                         'case': HOST.CASE, 'process_stage': 'not_checked', 'process_reason': 'none'})
        bad_changes = [lambda e: e.update(nonce='2' * 32),
                       lambda e: e['report']['stage3'].update(input_sha256={}),
                       lambda e: e['report']['stage3'].update(failure_kind='/secret/token=123'),
                       lambda e: e['report']['stage3'].update(failed_case='/private/path'),
                       lambda e: e['report']['stage3'].update(failure_kind='unsupported_observation'),
                       lambda e: e['report']['stage3'].update(failed_case=None),
                       lambda e: e['report']['stage3']['cases'][0].update(status='ok'),
                       lambda e: e['report']['stage3']['cases'][0].update(status='not_started'),
                       lambda e: e['report']['stage3']['cases'][0].update(source_sha256='c' * 64),
                       lambda e: e['report']['stage3']['client_tree']['process_diagnostics'].update(reason='private-log'),
                       lambda e: e['report']['stage3']['client_tree'].update(module_sha256='c' * 64),
                       lambda e: e.update(outputs=[{'data_b64':'rawsecret'}])]
        for change in bad_changes:
            altered = copy.deepcopy(native_failed)
            change(altered)
            with self.assertRaises(HOST.TreeError) as rejected:
                validate(altered)
            self.assertFalse(hasattr(rejected.exception, 'native_failure'))
        client_failed = copy.deepcopy(envelope)
        client_failed['outputs'] = []
        client_failed['report'].update(status='stage3_failed', native_tests_completed=False)
        cs = client_failed['report']['stage3']
        cs.update(status='failed', failure_kind='unsupported_observation',
                  observation_diagnostic={'site': 'client', 'case': 1, 'category': 'probe_p', 'calibration': None})
        cc = cs['client_tree']
        cc.update(status='failed', failure_kind='unsupported_observation', completed=False, witness_verified=False)
        cc.update(dict.fromkeys(HOST.FULL.CLIENT_OUTPUT_KEYS, None))
        with self.assertRaises(HOST.TreeError) as diagnostic:
            validate(client_failed)
        self.assertEqual(diagnostic.exception.observation_diagnostic['site'], 'client')
        generic_client = copy.deepcopy(client_failed)
        generic_client['report']['stage3'].update(observation_diagnostic=None, failure_kind='process_failed')
        generic_client['report']['stage3']['client_tree']['failure_kind'] = 'process_failed'
        with self.assertRaises(HOST.TreeError) as summary:
            validate(generic_client)
        self.assertEqual(summary.exception.native_failure['reason'], 'process_failed')
        self.assertEqual(summary.exception.native_failure['process_stage'], 'after_exit')
        mutations_generic = [lambda e: e['report']['stage3']['client_tree'].update(failure_kind='timeout'),
                             lambda e: e['report']['stage3']['cases'][0].update(module_sha256=None),
                             lambda e: e['report']['stage3']['cases'][0].update(output_sha256=None),
                             lambda e: e['report']['stage3']['cases'][0].update(output_size=True),
                             lambda e: e['report']['stage3']['cases'][0].update(message_count=True),
                             lambda e: e['report']['stage3'].update(failed_case=HOST.CASE)]
        for change in mutations_generic:
            altered = copy.deepcopy(generic_client)
            change(altered)
            with self.assertRaises(HOST.TreeError) as rejected:
                validate(altered)
            self.assertFalse(hasattr(rejected.exception, 'native_failure'))
        pre_case = copy.deepcopy(native_failed)
        ps = pre_case['report']['stage3']
        ps.update(failed_case=None, failure_kind='invalid_input')
        ps['cases'][0].update(status='not_started')
        ps['cases'][0].update(dict.fromkeys(HOST.FULL.CASE_KEYS - {'name', 'status'}, None))
        with self.assertRaises(HOST.TreeError) as summary:
            validate(pre_case)
        self.assertIsNone(summary.exception.native_failure['case'])
        post_client = copy.deepcopy(envelope)
        post_client['outputs'] = []
        post_client['report'].update(status='stage3_failed', native_tests_completed=False)
        post_client['report']['stage3'].update(status='failed', failure_kind='export_failed')
        with self.assertRaises(HOST.TreeError) as summary:
            validate(post_client)
        self.assertEqual(summary.exception.native_failure['reason'], 'export_failed')
        for key in HOST.FULL.CLIENT_FLAGS | HOST.FULL.CLIENT_HASHES:
            wrong = copy.deepcopy(client_failed)
            before = wrong['report']['stage3']['client_tree'][key]
            wrong['report']['stage3']['client_tree'][key] = not before if type(before) is bool else 'c' * 64
            with self.assertRaises(HOST.TreeError) as rejected:
                validate(wrong)
            self.assertFalse(hasattr(rejected.exception, 'observation_diagnostic'))
        for key, value in (('stage', 'before_probe'), ('reason', 'unverified')):
            wrong = copy.deepcopy(client_failed)
            wrong['report']['stage3']['client_tree']['process_diagnostics'][key] = value
            with self.assertRaises(HOST.TreeError) as rejected:
                validate(wrong)
            self.assertFalse(hasattr(rejected.exception, 'observation_diagnostic'))
        mutations = [lambda e: e.update(nonce='2' * 32),
                     lambda e: e['report']['stage3'].update(profile='full'),
                     lambda e: e['report']['stage3']['cases'][0].update(message_count=True),
                     lambda e: e['report']['stage3']['client_tree'].update(output_sha256='c' * 64),
                     lambda e: e['report']['stage3']['client_tree'].update(roundtrip_sha256='c' * 64),
                     lambda e: e['outputs'][0].update(size=True),
                     lambda e: e['outputs'][0].update(data_b64='AAAA'),
                     lambda e: e.update(outputs=[])]
        for change in mutations:
            altered = copy.deepcopy(envelope)
            change(altered)
            with self.assertRaises(HOST.TreeError):
                validate(altered)


if __name__ == '__main__':
    unittest.main()
