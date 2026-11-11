"""Offline loader-control contracts. Native execution is always mocked."""
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'scripts/native_1c_bootstrap')]
from accumulation_loader_control import fixture, contract
import native_1c_accumulation_loader_control as host
import accumulation_loader_control_suite as suite
from test_catalog_object_fixture import baseline
from test_catalog_object_native import synthetic_container_files, write_files
import catalog_object_suite
from test_native_1c_smoke import bootstrap_report
from test_native_1c_ci_policy import fixtures as ci_fixtures, policy, BASE, HEAD, MERGE

NONCE = 'a' * 32


def hashes():
    return {path: 'b' * 64 for path in host.staged_files()}


def successful_stage(inputs=None, nonce=NONCE):
    stage = suite.empty_report(nonce)
    stage.update(status='ok', failure_kind='none', failure_phase='final',
        input_sha256=hashes() if inputs is None else inputs,
        prepared_sha256='c' * 64, redump_sha256='d' * 64, completed_case_count=1,
        target_input_schema_version='2.4', target_redump_schema_version='2.4',
        process_diagnostics=dict(suite.full.empty_process_diagnostics(), stage='after_exit', reason='none'),
        **{key: True for key in contract.FLAGS})
    return stage


def envelope(stage=None, nonce=NONCE):
    report = bootstrap_report()
    report['stage3'] = successful_stage(nonce=nonce) if stage is None else stage
    if report['stage3']['status'] != 'ok':
        report['status'] = 'stage3_failed'
    report['native_tests_completed'] = False
    return dict(schema=contract.SCHEMA, profile=contract.PROFILE, nonce=nonce, report=report, outputs=[])


def encode(value):
    return json.dumps(value, separators=(',', ':')).encode()


@contextlib.contextmanager
def static_container_files(root):
    # Synthetic native-process tests only, not Linux race/containment evidence.
    # Reuse the portable static-reader seam without changing production readers.
    with synthetic_container_files(root):
        with mock.patch.object(suite, 'os', catalog_object_suite.os):
            yield


class FixtureTests(unittest.TestCase):
    def prepared(self):
        return fixture.prepare(baseline())[1]

    def reject(self, expected, actual):
        self.assertNotEqual(expected, actual, 'mutation must change the fixture bytes or file set')
        with self.assertRaises(ValueError):
            fixture.verify_redump(expected, actual)

    def test_exact_native_asset_and_three_target_substitutions(self):
        files = baseline()
        source = fixture.source.prepare(files)[1]
        actual = fixture.prepare(files)[1]
        self.assertEqual(set(source) - set(actual), {fixture.MODULE, fixture.SOURCE_REGISTER})
        self.assertEqual(set(actual) - set(source), {fixture.REGISTER})
        substitutions = {
            'Configuration.xml': (b'>OwnedAccumulationRows<', ('>' + fixture.REGISTER_NAME + '<').encode()),
            fixture.DOCUMENT: (fixture.OLD_TARGET, fixture.NEW_TARGET),
            fixture.original.ROLE_FILES[1]: (b'>' + fixture.OLD_TARGET + b'<', b'>' + fixture.NEW_TARGET + b'<'),
        }
        self.assertEqual(len(substitutions), 3)
        for name, (before, after) in substitutions.items():
            self.assertEqual(source[name].count(before), 1)
            self.assertEqual(actual[name], source[name].replace(before, after, 1))
        for name in set(actual) - set(substitutions) - {fixture.REGISTER}:
            self.assertEqual(actual[name], source[name])
        self.assertEqual(actual[fixture.REGISTER], fixture.native_declaration())

    def test_original_inputs_and_rights_are_not_broadened(self):
        files = baseline()
        original = dict(files)
        actual = fixture.prepare(files)[1]
        source = fixture.source.prepare(files)[1]
        self.assertEqual(files, original)
        role, rights = fixture.original.ROLE_FILES
        self.assertEqual(actual[role], source[role])
        self.assertEqual(actual[rights].count(fixture.NEW_TARGET), 1)
        self.assertEqual(actual[rights].replace(fixture.NEW_TARGET, fixture.OLD_TARGET), source[rights])

    def test_equal_strict_redump_passes(self):
        expected = self.prepared()
        self.assertTrue(fixture.verify_redump(expected, dict(expected)))

    def test_generated_type_identity_changes_fail(self):
        expected = self.prepared()
        actual = dict(expected)
        actual[fixture.REGISTER] = actual[fixture.REGISTER].replace(
            b'c2ca0ce2-1e82-4cae-b478-30d241ab9233', b'c2ca0ce2-1e82-4cae-b478-30d241ab9234')
        self.reject(expected, actual)

    def test_document_identity_and_recorder_link_changes_fail(self):
        expected = self.prepared()
        for before, after in ((b'98ed6b79', b'98ed6b78'),
                              (fixture.NEW_TARGET, b'AccumulationRegister.Other')):
            actual = dict(expected)
            actual[fixture.DOCUMENT] = actual[fixture.DOCUMENT].replace(before, after)
            self.reject(expected, actual)

    def test_changed_register_and_document_properties_fail(self):
        expected = self.prepared()
        for name, before, after in ((fixture.REGISTER, b'<RegisterType>Balance', b'<RegisterType>Turnovers'),
                (fixture.REGISTER, b'<EnableTotalsSplitting>true', b'<EnableTotalsSplitting>false'),
                (fixture.DOCUMENT, b'<Posting>Allow', b'<Posting>Deny'),
                (fixture.DOCUMENT, b'<SequenceFilling>AutoFill', b'<SequenceFilling>DontFill')):
            actual = dict(expected)
            actual[name] = actual[name].replace(before, after)
            self.reject(expected, actual)

    def test_old_register_and_handler_cannot_reappear(self):
        expected = self.prepared()
        source = fixture.source.prepare(baseline())[1]
        for path in (fixture.SOURCE_REGISTER, fixture.MODULE):
            actual = dict(expected)
            actual[path] = source[path]
            self.reject(expected, actual)

    def test_extra_files_grants_and_changed_bootstrap_fail(self):
        expected = self.prepared()
        for path, raw in (('Extra.xml', b'<Extra/>'), ('Ext/SessionModule.bsl', b'// altered'),
                (fixture.original.ROLE_FILES[1], expected[fixture.original.ROLE_FILES[1]].replace(b'<name>Read</name>', b'<name>Delete</name>'))):
            actual = dict(expected)
            actual[path] = raw
            self.reject(expected, actual)

    def test_unknown_designer_defaults_are_not_silently_accepted(self):
        expected = self.prepared()
        actual = dict(expected)
        actual[fixture.DOCUMENT] = actual[fixture.DOCUMENT].replace(b'</Properties>', b'<Unknown>true</Unknown></Properties>')
        self.reject(expected, actual)

    def test_tampered_expected_owned_source_is_refused(self):
        expected = self.prepared()
        before = expected[fixture.DOCUMENT]
        expected[fixture.DOCUMENT] = before.replace(b'<Posting>Allow', b'<Posting>Deny')
        self.assertNotEqual(before, expected[fixture.DOCUMENT])
        with self.assertRaises(ValueError):
            fixture.verify_redump(expected, expected)

    def test_inventory_digest_binds_names_and_bytes(self):
        expected = self.prepared()
        self.assertEqual(fixture.inventory_digest(expected), fixture.inventory_digest(dict(reversed(list(expected.items())))))
        actual = dict(expected)
        actual['Ext/SessionModule.bsl'] += b'\n'
        self.assertNotEqual(fixture.inventory_digest(expected), fixture.inventory_digest(actual))

    def test_export_bookkeeping_exception_does_not_relax_file_set(self):
        expected = self.prepared()
        actual = dict(expected, **{'ConfigDumpInfo.xml': b'<ExportInfo changed="yes"/>'})
        self.assertTrue(fixture.verify_redump(expected, actual))
        del actual['ConfigDumpInfo.xml']
        self.reject(expected, actual)

    def test_public_source_and_license_are_exact_and_attributed(self):
        root = fixture.PUBLIC_ROOT
        self.assertEqual({path.name for path in root.iterdir()},
            {fixture.REGISTER_NAME + '.xml', 'LICENSE', 'SOURCE.json', 'NOTICE.md'})
        value = json.loads((root / 'SOURCE.json').read_text(encoding='utf-8'))
        self.assertEqual(value['repository'], 'vanessa-opensource/add')
        self.assertEqual(value['commit'], '2deeed6636dfbb84f42ae625fd40c8ab662bb64e')
        self.assertEqual(value['git_blob'], fixture.NATIVE_GIT_BLOB)
        self.assertEqual(value['sha256'], fixture.NATIVE_SHA256)
        raw = fixture.native_declaration()
        self.assertEqual(len(raw), value['bytes'])
        self.assertEqual(len(raw), 10303)
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture.NATIVE_SHA256)
        self.assertEqual(hashlib.sha1(b'blob 10303\0' + raw).hexdigest(), fixture.NATIVE_GIT_BLOB)
        license_raw = (root / 'LICENSE').read_bytes()
        self.assertEqual(value['license']['spdx'], 'MPL-2.0')
        self.assertEqual(value['license']['git_blob'], 'a612ad9813b006ce81d1ee438dd784da99a54007')
        self.assertEqual(hashlib.sha256(license_raw).hexdigest(),
            '1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5')
        self.assertIn(b'Mozilla Public License Version 2.0', license_raw)
        notice = (root / 'NOTICE.md').read_text(encoding='utf-8')
        self.assertIn(value['source_url'], notice)
        self.assertIn('unmodified', notice)
        self.assertIn('Mozilla Public License', notice)
        attributes = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
        self.assertIn('scripts/accumulation_loader_control/** text eol=lf', attributes)

    def test_native_asset_retains_complete_identity_descriptors_and_fields(self):
        root, _ = fixture.original._xml(fixture.native_declaration())
        md = '{' + fixture.original.MD + '}'
        xr = '{http://v8.1c.ru/8.3/xcf/readable}'
        v8 = '{' + fixture.original.V8 + '}'
        self.assertEqual(root.get('version'), '2.4')
        register = root[0]
        self.assertEqual(register.get('uuid'), '8d62a3dc-3d13-40e5-aab1-f73487263e75')
        properties = register.find(md + 'Properties')
        self.assertEqual(properties.find(md + 'Name').text, fixture.REGISTER_NAME)
        self.assertEqual(properties.find(md + 'RegisterType').text, 'Balance')
        self.assertEqual(properties.find(md + 'DataLockControlMode').text, 'Managed')
        self.assertEqual(properties.find(md + 'EnableTotalsSplitting').text, 'true')
        self.assertEqual(len(register.find(md + 'InternalInfo').findall(xr + 'GeneratedType')), 6)
        self.assertEqual([node.get('name') for node in properties.find(md + 'StandardAttributes')],
            ['RecordType', 'Active', 'LineNumber', 'Recorder', 'Period'])
        fields = register.find(md + 'ChildObjects')
        self.assertEqual([node.tag for node in fields], [md + 'Resource', md + 'Dimension'])
        resource, dimension = [node.find(md + 'Properties') for node in fields]
        self.assertEqual(resource.find(md + 'Name').text, 'РесурсЧисло1')
        self.assertEqual(dimension.find(md + 'Name').text, 'Измерение1')
        number = resource.find(md + 'Type/' + v8 + 'NumberQualifiers')
        self.assertEqual([node.text for node in number], ['10', '2', 'Any'])
        string = dimension.find(md + 'Type/' + v8 + 'StringQualifiers')
        self.assertEqual([node.text for node in string], ['10', 'Variable'])
        self.assertEqual(dimension.find(md + 'UseInTotals').text, 'true')
        self.assertEqual([node.text for node in root.iter(v8 + 'Type')], ['xs:decimal', 'xs:string'])
        for node in root.iter():
            self.assertNotIn(node.tag.rsplit('}', 1)[-1], ('Form', 'Template', 'Command', 'ObjectModule'))
        self.assertNotIn('cfg:', fixture.native_declaration().decode('utf-8-sig'))

    def test_native_input_pin_refuses_bom_newline_schema_or_identity_drift(self):
        raw = fixture.native_declaration()
        for changed in (raw[3:], raw.replace(b'\n', b'\r\n'),
                raw.replace(b'version="2.4"', b'version="2.20"'),
                raw.replace(b'8d62a3dc', b'8d62a3dd')):
            self.assertNotEqual(raw, changed)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / (fixture.REGISTER_NAME + '.xml')).write_bytes(changed)
                with mock.patch.object(fixture, 'PUBLIC_ROOT', root), self.assertRaises(ValueError):
                    fixture.native_declaration()

    def test_native_fields_and_standard_descriptors_remain_strict(self):
        expected = self.prepared()
        for before, after in ((b'<v8:Digits>10', b'<v8:Digits>11'),
                (b'<v8:Length>10', b'<v8:Length>12'),
                (b'<UseInTotals>true', b'<UseInTotals>false'),
                (b'<xr:FillChecking>ShowError', b'<xr:FillChecking>DontCheck')):
            actual = dict(expected)
            actual[fixture.REGISTER] = actual[fixture.REGISTER].replace(before, after)
            self.reject(expected, actual)
        actual = dict(expected)
        actual[fixture.REGISTER] = actual[fixture.REGISTER].replace(b'</ChildObjects>',
            b'<Attribute uuid="extra"><Properties><Name>Extra</Name></Properties></Attribute></ChildObjects>')
        self.reject(expected, actual)

    def test_schema_upgrade_is_observed_but_never_silently_normalized(self):
        expected = self.prepared()
        actual = dict(expected)
        actual[fixture.REGISTER] = actual[fixture.REGISTER].replace(b'version="2.4"', b'version="2.20"')
        self.assertEqual(fixture.target_schema_version(expected), '2.4')
        self.assertEqual(fixture.target_schema_version(actual), '2.20')
        self.reject(expected, actual)
        actual[fixture.REGISTER] = expected[fixture.REGISTER].replace(b'version="2.4"', b'version="private-token"')
        self.assertEqual(fixture.target_schema_version(actual), 'other')
        self.assertEqual(fixture.target_schema_version({}), None)


class TransportTests(unittest.TestCase):
    def validate(self, value):
        return host.validate_envelope(encode(value), NONCE, hashes())

    def test_success_is_one_diagnostic_and_never_measurement_acceptance(self):
        report = self.validate(envelope())
        self.assertEqual(report['stage3']['case_count'], 1)
        self.assertEqual(report['stage3']['completed_case_count'], 1)
        self.assertFalse(report['native_tests_completed'])
        self.assertTrue(all(report['stage3'][key] is False for key in contract.ACCEPTANCE_FLAGS))

    def test_failure_retains_finite_loader_facts_only(self):
        stage = suite.empty_report(NONCE)
        stage.update(failure_kind='process_failed', failure_phase='load', entered=True,
            input_sha256=hashes(), prepared_sha256='c' * 64, target_input_schema_version='2.4',
            install_diagnostics=[contract.install_diagnostic('private-value secret=xyz', 'load',
                exit_code=-11, source_root_present=True, configuration_present=True)])
        report = self.validate(envelope(stage))
        diagnostic = report['stage3']['install_diagnostics'][0]
        self.assertEqual(diagnostic['exit_code'], -11)
        self.assertNotIn('private-value', str(report))
        self.assertNotIn('xyz', str(report))

    def test_acceptance_true_or_coerced_false_is_rejected(self):
        for key in contract.ACCEPTANCE_FLAGS:
            for value in (True, 0, None, 'false'):
                data = envelope()
                data['report']['stage3'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.validate(data)

    def test_native_tests_completed_cannot_claim_control_as_measurement(self):
        data = envelope()
        data['report']['native_tests_completed'] = True
        with self.assertRaises(ValueError):
            self.validate(data)

    def test_old_sixteen_case_profile_and_non_one_counts_are_refused(self):
        for field, value in (('profile', fixture.source.route.PROFILE), ('profile', 'accumulation-loader-control-v1'),
                             ('schema', 'native-1c-accumulation-loader-control-stage-v1'), ('case_count', 16),
                             ('case_count', True), ('completed_case_count', 0)):
            data = envelope()
            data['report']['stage3'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(data)

    def test_wrong_nonce_or_hash_inventory_is_rejected(self):
        for mutate in (lambda data: data.update(nonce='e' * 32),
                       lambda data: data['report']['stage3'].update(nonce='e' * 32),
                       lambda data: data['report']['stage3'].update(input_sha256={}),
                       lambda data: data['report']['stage3']['input_sha256'].update(extra='b' * 64)):
            data = envelope()
            mutate(data)
            with self.assertRaises(ValueError):
                self.validate(data)

    def test_extra_payloads_keys_and_raw_console_are_rejected(self):
        for mutate in (lambda data: data.update(outputs=[{'data_b64': 'cHJpdmF0ZQ=='}]),
                       lambda data: data.update(console='private'),
                       lambda data: data['report']['stage3'].update(console='private')):
            data = envelope()
            mutate(data)
            with self.assertRaises(ValueError):
                self.validate(data)

    def test_invalid_json_duplicates_and_limits_are_rejected(self):
        for raw in (b'{}', b'{"schema":1,"schema":1}', b'private', b'\xff', b' ' * (contract.MAX_TRANSPORT + 1)):
            with self.assertRaises(ValueError):
                host.validate_envelope(raw, NONCE, hashes())

    def test_success_requires_every_lifecycle_witness(self):
        for key in contract.FLAGS:
            data = envelope()
            data['report']['stage3'][key] = False
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(data)

    def test_failure_cannot_claim_completed_case(self):
        stage = suite.empty_report(NONCE)
        stage['completed_case_count'] = 1
        with self.assertRaises(ValueError):
            self.validate(envelope(stage))

    def test_update_step_and_arbitrary_diagnostic_text_are_refused(self):
        for value in ('update', 'private'):
            with self.assertRaises(ValueError):
                contract.install_diagnostic('error', value)
        data = envelope(suite.empty_report(NONCE))
        diagnostic = contract.install_diagnostic('error', 'load')
        diagnostic['tokens'].append('private')
        data['report']['stage3']['install_diagnostics'] = [diagnostic]
        with self.assertRaises(ValueError):
            self.validate(data)

    def test_failed_process_and_redump_are_not_green(self):
        for key, value in (('status', 'failed'), ('failure_kind', 'process_failed'),
                ('failure_phase', 'load'), ('prepared_sha256', None), ('configuration_validation', 'other')):
            data = envelope()
            data['report']['stage3'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(data)

    def test_schema_facts_are_finite_and_verified_redump_cannot_claim_upgrade(self):
        for field, value in (('target_input_schema_version', '2.20'),
                ('target_redump_schema_version', '2.20'), ('target_redump_schema_version', 'private'),
                ('target_redump_schema_version', 2.4), ('target_input_schema_version', None)):
            data = envelope()
            data['report']['stage3'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.validate(data)
        stage = suite.empty_report(NONCE)
        stage.update(entered=True, load_completed=True, redump_completed=True,
            target_input_schema_version='2.4', target_redump_schema_version='2.20',
            failure_kind='output_mismatch', failure_phase='redump', input_sha256=hashes())
        report = self.validate(envelope(stage))
        self.assertTrue(report['stage3']['load_completed'])
        self.assertTrue(report['stage3']['redump_completed'])
        self.assertFalse(report['stage3']['config_verified'])
        self.assertTrue(all(report['stage3'][key] is False for key in contract.ACCEPTANCE_FLAGS))


class HostIsolationTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            from test_native_1c_full_host import read_synthetic_file
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_synthetic_file)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_exact_source_staging_and_closed_container_command(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            inputs = host.stage_inputs(ROOT, staged, host.SMOKE)
            command = host.container_command(staged, inputs, 'onec-accumulation-loader-control-' + NONCE, NONCE, host.SMOKE)
            self.assertEqual(command[-3:], ['--accumulation-loader-control', '--invocation-nonce', NONCE])
            for key, value in {'--network': 'none', '--user': '1000:1000', '--cap-drop': 'ALL',
                    '--security-opt': 'no-new-privileges:true', '--log-driver': 'none', '--pull': 'never',
                    '--platform': 'linux/amd64', '--pids-limit': '256'}.items():
                self.assertEqual(command[command.index(key) + 1], value)
            self.assertIn('--read-only', command)
            self.assertIn(host.SMOKE.IMAGE, command)
            self.assertEqual(json.loads((staged / contract.MANIFEST).read_bytes()), host.staged_files())
            self.assertNotIn('bootstrap/accumulation_register_suite.py', host.staged_files().values())

    def test_staged_mutation_extra_file_or_directory_refused(self):
        for change in ('modify', 'file', 'directory'):
            with tempfile.TemporaryDirectory() as directory:
                staged = Path(directory).resolve() / 'inputs'
                inputs = host.stage_inputs(ROOT, staged, host.SMOKE)
                if change == 'modify':
                    (staged / 'probe.sh').write_bytes(b'changed')
                elif change == 'file':
                    (staged / 'extra').write_bytes(b'extra')
                else:
                    (staged / 'extra').mkdir()
                with self.assertRaises(ValueError):
                    host.validate_inputs(staged, inputs, host.SMOKE)

    def test_staging_symlink_and_wrong_container_identity_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory).resolve() / 'inputs'
            inputs = host.stage_inputs(ROOT, staged, host.SMOKE)
            with self.assertRaises(ValueError):
                host.container_command(staged, inputs, 'onec-accumulation-register-' + NONCE, NONCE, host.SMOKE)
            try:
                (staged / 'alias').symlink_to(staged / 'probe.sh')
            except OSError:
                self.skipTest('symlink unavailable')
            with self.assertRaises(ValueError):
                host.validate_inputs(staged, inputs, host.SMOKE)

    def test_private_work_cleanup_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {'stage': 'inputs'}
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                with host.private_work(Path(directory), state) as private:
                    raise RuntimeError('synthetic')
            self.assertFalse(Path(private).exists())
            self.assertEqual(state['stage'], 'inputs')

    def fake_host_run(self, *, lifecycle_error=False, changed_source=False):
        calls = []
        def lifecycle(command, env, **kwargs):
            self.assertNotIn('GHCR_TOKEN', os.environ)
            self.assertNotIn('GHCR_USER', os.environ)
            self.assertFalse(Path(env['DOCKER_CONFIG']).parent.joinpath('auth').exists())
            calls.append(command)
            if lifecycle_error:
                raise host.LoaderControlError('container_cleanup_unverified')
            staged = Path(command[command.index('--mount') + 1].split('src=', 1)[1].split(',dst=', 1)[0])
            inputs = {source: host.FULL.digest(host.FULL.read_regular(staged / target, host.FULL.MAX_FILE, nonempty=True))
                      for source, target in host.staged_files().items()}
            return 0, encode(envelope(successful_stage(inputs, kwargs['nonce']), kwargs['nonce']))
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, {'GHCR_USER': 'Atridis', 'GHCR_TOKEN': 'synthetic'}, clear=True))
            stack.enter_context(mock.patch.object(host.FULL, 'repository_provenance', return_value={'commit': '1' * 40, 'tree': '2' * 40}))
            stack.enter_context(mock.patch.object(host.FULL, 'interpreter_provenance', return_value={}))
            stack.enter_context(mock.patch.object(host.FULL, 'windows_fingerprints', return_value={}))
            stack.enter_context(mock.patch.object(host.SMOKE, 'run_silent'))
            stack.enter_context(mock.patch.object(host.DOCKER, 'run_owned', side_effect=lifecycle))
            if changed_source:
                original = host.validate_inputs
                invocations = []
                def validate(*args):
                    invocations.append(1)
                    if len(invocations) == 3:
                        raise host.LoaderControlError('accumulation_loader_control_staged_source_changed')
                    return original(*args)
                stack.enter_context(mock.patch.object(host, 'validate_inputs', side_effect=validate))
            try:
                return host.run(ROOT, Path(directory)), calls
            finally:
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_host_success_cleans_credentials_and_keeps_all_acceptance_false(self):
        report, calls = self.fake_host_run()
        self.assertEqual(len(calls), 1)
        self.assertTrue(report['diagnostic_control_passed'])
        self.assertTrue(report['private_payloads_removed'])
        self.assertTrue(report['container_cleanup_verified'])
        self.assertTrue(all(report[key] is False for key in contract.ACCEPTANCE_FLAGS))
        self.assertIsNone(report['comparison'])
        self.assertNotIn('native_artifact_sha256', report)

    def test_cleanup_failure_prevents_any_success_report(self):
        with self.assertRaisesRegex(ValueError, 'container_cleanup_unverified'):
            self.fake_host_run(lifecycle_error=True)

    def test_final_source_change_prevents_any_success_report(self):
        with self.assertRaisesRegex(ValueError, 'staged_source_changed'):
            self.fake_host_run(changed_source=True)

    def test_cross_platform_byte_pins_and_no_export_option(self):
        attributes = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
        for path in ('scripts/accumulation_loader_control/**',
                'scripts/native_1c_accumulation_loader_control.py',
                'scripts/native_1c_accumulation_loader_control_probe.sh',
                'scripts/native_1c_bootstrap/accumulation_loader_control_suite.py'):
            self.assertIn(path + ' text eol=lf', attributes)
        source = (ROOT / 'scripts/native_1c_accumulation_loader_control.py').read_text(encoding='utf-8')
        self.assertNotIn('--export-native-outputs', source)
        self.assertNotIn('GITHUB_OUTPUT', source)


class SuiteTests(unittest.TestCase):
    def simulate(self, *, failed_load=False, changed_redump=False, changed_prepared=False, invalid_user=False, schema_upgrade=False):
        calls = []
        baseline_files = baseline()
        loaded_files = {}
        with tempfile.TemporaryDirectory() as directory:
            container = Path(directory).resolve()
            root = container / 'control'
            platform = types.SimpleNamespace(user='Other' if invalid_user else 'NativeSmoke', password=None,
                timeout=120, executable=Path('/synthetic/onec'), command=lambda mode: ['synthetic-onec', mode])
            def process(command, directory, log, timeout, **kwargs):
                self.assertEqual(command[1], 'DESIGNER')
                self.assertEqual(timeout, 120)
                self.assertIs(kwargs['require_clean_tree'], True)
                self.assertNotIn('/UpdateDBCfg', command)
                action = command[2]
                calls.append(action)
                if action == '/DumpConfigToFiles':
                    # Redump the actual loaded snapshot, not a new fixture with fresh UUIDs.
                    files = dict(baseline_files if len(calls) == 1 else loaded_files)
                    if len(calls) > 1 and (changed_redump or schema_upgrade):
                        before = files[fixture.REGISTER]
                        files[fixture.REGISTER] = (before.replace(b'version="2.4"', b'version="2.20"') if schema_upgrade else
                            before.replace(b'<RegisterType>Balance', b'<RegisterType>Turnovers'))
                        self.assertNotEqual(files[fixture.REGISTER], before)
                    write_files(Path(command[3]), files)
                    if len(calls) > 1 and changed_prepared:
                        (root / 'prepared' / fixture.DOCUMENT).write_bytes(b'<Altered/>')
                elif action == '/LoadConfigFromFiles':
                    if failed_load:
                        log.write_bytes(b'X Error: BadName private-person secret=hidden')
                        error = suite.full.FullError('process_failed')
                        error.exit_code = -11
                        raise error
                    loaded_files.update(suite.dump_files(Path(command[3])))
            with static_container_files(container), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(suite, 'input_hashes', return_value=hashes()))
                stack.enter_context(mock.patch.object(suite.full, 'run_process', side_effect=process))
                stack.enter_context(mock.patch.object(suite.full, 'client_process_baseline', return_value=set()))
                stack.enter_context(mock.patch.object(suite.full, 'client_process_snapshot', return_value=set()))
                stack.enter_context(mock.patch.object(suite.full, 'native_processes_quiet', return_value=True))
                stack.enter_context(mock.patch.object(suite.full, 'require_session_bus'))
                report = suite.run_suite(platform, root, container / 'inputs', NONCE)
        return report, calls

    def test_one_control_is_only_dump_load_redump(self):
        report, calls = self.simulate()
        self.assertEqual(calls, ['/DumpConfigToFiles', '/LoadConfigFromFiles', '/DumpConfigToFiles'])
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['completed_case_count'], 1)
        self.assertTrue(all(report[key] is False for key in contract.ACCEPTANCE_FLAGS))
        host.validate_envelope(encode(envelope(report)), NONCE, hashes())

    def test_load_failure_stops_before_redump_and_preserves_only_finite_facts(self):
        report, calls = self.simulate(failed_load=True)
        self.assertEqual(calls, ['/DumpConfigToFiles', '/LoadConfigFromFiles'])
        self.assertEqual(report['failure_phase'], 'load')
        self.assertEqual(report['completed_case_count'], 0)
        diagnostic = report['install_diagnostics'][0]
        self.assertEqual(diagnostic['exit_code'], -11)
        self.assertIs(diagnostic['source_root_present'], True)
        self.assertIs(diagnostic['configuration_present'], True)
        self.assertNotIn('private-person', str(report))
        self.assertNotIn('hidden', str(report))
        host.validate_envelope(encode(envelope(report)), NONCE, hashes())

    def test_redump_mismatch_cannot_complete_control(self):
        report, calls = self.simulate(changed_redump=True)
        self.assertEqual(len(calls), 3)
        self.assertEqual(report['failure_phase'], 'redump')
        self.assertFalse(report['config_verified'])
        self.assertEqual(report['completed_case_count'], 0)

    def test_prepared_source_mutation_cannot_complete_control(self):
        report, _ = self.simulate(changed_prepared=True)
        self.assertEqual(report['failure_phase'], 'final')
        self.assertFalse(report['source_verified'])
        self.assertEqual(report['completed_case_count'], 0)

    def test_wrong_platform_identity_fails_before_native_commands(self):
        report, calls = self.simulate(invalid_user=True)
        self.assertEqual(calls, [])
        self.assertEqual(report['failure_kind'], 'invalid_input')

    def test_finish_report_has_no_outputs_even_on_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / ('stage3-' + NONCE)
            root.mkdir()
            (root.parent / 'stage3-report.json').write_bytes(encode(successful_stage()))
            with static_container_files(root.parent), mock.patch.object(suite.full, 'final_client_process_census'):
                raw = suite.finish_report(bootstrap_report(), NONCE, root, quiet=True, bus_cleanup_failed=False)
            value = json.loads(raw)
            self.assertEqual(value['outputs'], [])
            self.assertEqual(value['report']['stage3']['status'], 'ok')
            self.assertFalse(value['report']['native_tests_completed'])
            host.validate_envelope(raw, NONCE, hashes())

    def test_finish_report_cleanup_failure_cannot_export_success(self):
        for quiet, bus_failed in ((False, False), (True, True)):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve() / ('stage3-' + NONCE)
                root.mkdir()
                (root.parent / 'stage3-report.json').write_bytes(encode(successful_stage()))
                with static_container_files(root.parent), mock.patch.object(suite.full, 'final_client_process_census'):
                    raw = suite.finish_report(bootstrap_report(), NONCE, root, quiet=quiet, bus_cleanup_failed=bus_failed)
                report = host.validate_envelope(raw, NONCE, hashes())
                self.assertEqual(report['status'], 'stage3_failed')
                self.assertEqual(report['stage3']['completed_case_count'], 0)

    def test_native_source_has_no_postload_enterprise_or_update(self):
        source = (ROOT / 'scripts/native_1c_bootstrap/accumulation_loader_control_suite.py').read_text(encoding='utf-8')
        self.assertNotIn("command('ENTERPRISE')", source)
        self.assertNotIn('/UpdateDBCfg', source)
        self.assertNotIn('run_case(', source)
        self.assertIn('run_stage.main([])', source)
        probe = (ROOT / 'scripts/native_1c_accumulation_loader_control_probe.sh').read_text(encoding='utf-8')
        self.assertIn('!= --accumulation-loader-control', probe)
        self.assertNotIn('--accumulation-register-suite', probe)
        self.assertIn('stop_session_bus', probe)
        self.assertIn('client-process-baseline.json', probe)
        self.assertIn('accumulation_loader_control_suite.py', probe)

    def test_dump_rejects_symlink_and_hardlink_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / 'owned.xml').write_bytes(b'<Owned/>')
            try:
                (root / 'alias.xml').symlink_to(root / 'owned.xml')
            except OSError:
                self.skipTest('symlink unavailable')
            with static_container_files(root), self.assertRaises(suite.full.FullError):
                suite.dump_files(root)
            (root / 'alias.xml').unlink()
            try:
                os.link(root / 'owned.xml', root / 'alias.xml')
            except OSError:
                self.skipTest('hardlink unavailable')
            with static_container_files(root), self.assertRaises(suite.full.FullError):
                suite.dump_files(root)

    def test_manifest_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / contract.MANIFEST).write_bytes(encode({'scripts/owned.py': '../outside'}))
            with static_container_files(root), self.assertRaises(suite.full.FullError):
                suite.input_hashes(root)

    def test_native_schema_upgrade_retains_load_success_and_fails_only_redump(self):
        report, calls = self.simulate(schema_upgrade=True)
        self.assertEqual(calls, ['/DumpConfigToFiles', '/LoadConfigFromFiles', '/DumpConfigToFiles'])
        self.assertEqual(report['failure_phase'], 'redump')
        self.assertEqual(report['failure_kind'], 'output_mismatch')
        self.assertTrue(report['load_completed'])
        self.assertTrue(report['redump_completed'])
        self.assertFalse(report['config_verified'])
        self.assertEqual(report['target_input_schema_version'], '2.4')
        self.assertEqual(report['target_redump_schema_version'], '2.20')
        self.assertEqual(report['completed_case_count'], 0)
        self.assertTrue(all(report[key] is False for key in contract.ACCEPTANCE_FLAGS))
        host.validate_envelope(encode(envelope(report)), NONCE, hashes())


class WorkflowTests(unittest.TestCase):
    def workflow(self):
        return (ROOT / '.github/workflows/native-1c-accumulation-loader-control.yml').read_text(encoding='utf-8')

    def test_temporary_workflow_is_exact_owner_branch_and_draft_only(self):
        source = self.workflow()
        for condition in ("github.repository == 'Atridis/yadinassi'", "github.repository_id == '359770628'",
                "github.repository_owner_id == '30860798'", "github.actor == 'Atridis'", "github.actor_id == '30860798'",
                "github.triggering_actor == 'Atridis'", "head.repo.full_name == 'Atridis/yadinassi'",
                "head.ref == 'codex/accumulation-loader-control'", 'github.event.pull_request.draft == true',
                "base.ref == 'main'"):
            self.assertIn(condition, source)
        self.assertIn('types: [opened, synchronize, reopened]', source)
        for forbidden in ('pull_request_target', 'workflow_dispatch', '\n  push:', 'contents: write', 'packages: write'):
            self.assertNotIn(forbidden, source)

    def test_pinned_actions_immutable_checkout_and_binding_before_credentials(self):
        source = self.workflow()
        actions = re.findall(r'uses: ([^\n ]+)', source)
        self.assertEqual(len(actions), 3)
        self.assertTrue(all(re.fullmatch(r'actions/[a-z-]+@[0-9a-f]{40}', action) for action in actions))
        self.assertIn('ref: ${{ github.sha }}', source)
        self.assertIn('persist-credentials: false', source)
        self.assertLess(source.index('native_1c_ci_policy.py bind'), source.index('GHCR_TOKEN:'))
        self.assertIn('cancel-in-progress: false', source)

    def test_one_job_one_control_command_one_bounded_summary(self):
        source = self.workflow()
        self.assertEqual(re.findall(r'^  ([a-z_]+):$', source.split('jobs:', 1)[1], re.M), ['control'])
        self.assertEqual(source.count('native_1c_accumulation_loader_control.py --execute-approved-image'), 1)
        self.assertNotIn('--export-native-outputs', source)
        self.assertEqual(source.count('uses: actions/upload-artifact@'), 1)
        self.assertIn('path: native-smoke/accumulation-loader-control.json', source)
        self.assertNotIn('native_1c_accumulation_register_profile.py', source)

    def test_original_sixteen_case_workflow_does_not_select_control_branch(self):
        original = (ROOT / '.github/workflows/native-1c-accumulation-register.yml').read_text(encoding='utf-8')
        self.assertIn("head.ref == 'codex/accumulation-balance-registers'", original)
        self.assertNotIn('codex/accumulation-loader-control', original)

    def test_shared_binding_accepts_exact_merge_and_refuses_stale_or_dirty(self):
        event, context = ci_fixtures()
        event['pull_request']['head']['ref'] = 'codex/accumulation-loader-control'
        policy.validate_binding(event, context, MERGE, [BASE, HEAD], '')
        for commit, parents, status in ((HEAD, [BASE, HEAD], ''), (MERGE, [HEAD, BASE], ''),
                                        (MERGE, [BASE, HEAD], ' M source.py')):
            with self.assertRaises(policy.PolicyError):
                policy.validate_binding(event, context, commit, parents, status)

    def test_shared_binding_refuses_other_owner_or_fork(self):
        for mutation in ('actor', 'fork'):
            event, context = ci_fixtures()
            if mutation == 'actor':
                context['GITHUB_ACTOR_ID'] = '1'
            else:
                event['pull_request']['head']['repo']['fork'] = True
            with self.assertRaises(policy.PolicyError):
                policy.validate_binding(event, context, MERGE, [BASE, HEAD], '')
