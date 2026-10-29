"""Separate, fixed codec host selection; no native execution in these tests."""
import hashlib
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import test_native_catalog_reference_route as old
import inputs
import protocol

host = old.host


class CodecHostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(lambda: old.old.old.writable(self.root))

    def test_fixed_inventory_and_strict_selector(self):
        self.assertEqual(set(inputs.CATALOG_CODEC_SOURCE_FILES) - set(inputs.CATALOG_REFERENCE_SOURCE_FILES), {
            'scripts/native_1c_db_oracle/catalog_reference_codec.py',
            'yadinassi/storage/catalog_reference_uuid.py'})
        for case in ('distinct_a', 'distinct_b'):
            self.assertIs(inputs.inventory(reference_case=case, reference_codec=True), inputs.CATALOG_CODEC_SOURCE_FILES)
            self.assertIs(inputs.inventory(reference_case=case), inputs.CATALOG_REFERENCE_SOURCE_FILES)
        for value in (None, 0, 1, [], 'true'):
            with self.assertRaises(Exception):
                inputs.inventory(reference_case='distinct_a', reference_codec=value)
        with self.assertRaises(Exception): inputs.inventory(reference_codec=True)
        with self.assertRaises(Exception): inputs.inventory(reference_case='distinct_a', reference_codec=True, record_reader=True)

    def test_stage_source_pin_invocation_case_and_route(self):
        for case in ('distinct_a', 'distinct_b'):
            options = {'reference_case': case, 'reference_codec': True}
            value = old.old.identity()
            value['sources'] = inputs.source_hashes(old.old.ROOT, **options)
            stage = self.root / case
            inputs.stage_inputs(old.old.ROOT, stage, old.old.NONCE, value, **options)
            self.assertEqual(inputs.verify_inputs(stage, old.old.NONCE, **options), value)
            invocation = protocol.decode((stage / 'invocation.json').read_bytes())
            self.assertEqual(set(invocation), {'schema', 'lane', 'nonce', 'provenance', 'reference_case'})
            self.assertEqual((invocation['schema'], invocation['lane'], invocation['reference_case']),
                             (25, 'catalog-reference-codec-v1', case))
            command = host.container_command(stage, 'onec-db-oracle-' + 'a'*32, old.old.NONCE, **options)
            self.assertEqual(command[-1], '--catalog-reference-codec-' + case.replace('_', '-'))
            with self.assertRaises(Exception): inputs.verify_inputs(stage, old.old.NONCE, reference_case=case)
            codec = stage / 'catalog_reference_uuid.py'
            codec.chmod(0o600); codec.write_bytes(codec.read_bytes() + b'\n')
            with self.assertRaises(Exception): inputs.verify_inputs(stage, old.old.NONCE, **options)

    @unittest.skipUnless(old.DESCRIPTOR_HANDOFF, 'POSIX no-follow dirfd boundary')
    def test_codec_a_descriptor_path_digest_and_run_authentication(self):
        parent = self.root / 'native-db-oracle'; parent.mkdir()
        raw = b'{"nonce":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n'
        path = parent / 'codec_distinct_a.json'; path.write_bytes(raw)
        info = self.root.stat(); identity = (info.st_dev, info.st_ino)
        env = {'GITHUB_RUN_ID':'123', 'GITHUB_RUN_ATTEMPT':'2', 'REFERENCE_A_RUN_ID':'123',
               'REFERENCE_A_RUN_ATTEMPT':'2', 'REFERENCE_A_SHA256':hashlib.sha256(raw).hexdigest()}
        policy = types.SimpleNamespace(validate_report=mock.Mock(return_value={'reference_case':'distinct_a','accepted':True}))
        with mock.patch.object(host, 'ROOT', self.root), mock.patch.object(host, 'provenance', return_value={}) as provenance, \
                mock.patch.dict('sys.modules', {'catalog_reference_codec': policy}), mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(host.validate_reference_a(identity, reference_codec=True), raw)
            provenance.assert_called_once_with(reference_case='distinct_b', reference_codec=True)
            policy.validate_report.assert_called_once_with(raw, nonce='a'*32, provenance={}, final=True)
            for key, value in (('REFERENCE_A_SHA256','f'*64), ('REFERENCE_A_RUN_ID','124'), ('REFERENCE_A_RUN_ATTEMPT','1')):
                with mock.patch.dict(os.environ,{key:value}), self.assertRaises(Exception):
                    host.validate_reference_a(identity, reference_codec=True)
            with self.assertRaises(Exception): host.read_reference_a(identity)
            extra = parent / 'distinct_a.json'; extra.write_bytes(raw)
            with self.assertRaises(Exception): host.read_reference_a(identity, reference_codec=True)
            extra.unlink(); path.unlink(); path.symlink_to(self.root/'elsewhere')
            with self.assertRaises(Exception): host.read_reference_a(identity, reference_codec=True)

    def test_preflight_rejects_credentials_before_handoff(self):
        with mock.patch.dict(os.environ, {'GHCR_TOKEN':'private'}, clear=True), \
                mock.patch.object(host,'validate_reference_a') as validate:
            self.assertEqual(host.main(['--validate-codec-a']), 1)
            validate.assert_not_called()

    def test_positive_cli_exports_only_codec_paths_and_b_requires_handoff(self):
        common = ['--execute-approved-image', '--file-db-oracle', '--catalog-reference-codec']
        report = {'accepted': True, 'provenance': {}}
        aggregate = {'codec_verified': True}
        policy = types.SimpleNamespace(aggregate_reports=mock.Mock(return_value=aggregate))
        for case in ('distinct_a', 'distinct_b'):
            calls = []
            with mock.patch.object(host, 'ROOT', self.root), mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch.object(host, 'run_oracle', side_effect=lambda *a, **k: calls.append(('run', k)) or report), \
                    mock.patch.object(host, 'validate_reference_a', side_effect=lambda *a, **k: calls.append(('handoff', k)) or b'prior'), \
                    mock.patch.object(host, 'export_report') as export, \
                    mock.patch.dict('sys.modules', {'catalog_reference_codec': policy}):
                self.assertEqual(host.main(common + [case, '--output', str(host.CODEC_OUTPUTS[case])]), 0)
                self.assertEqual(calls[-1], ('run', {'reference_case':case, 'reference_codec':True}))
                if case == 'distinct_b':
                    self.assertEqual(calls[0], ('handoff', {'reference_codec':True}))
                    self.assertEqual(export.call_args_list[-1].kwargs, {'output':host.CODEC_AGGREGATE})
                    policy.aggregate_reports.assert_called_once_with(b'prior', protocol.encode(report)+b'\n', provenance={})
                else:
                    self.assertEqual(len(calls), 1)
                self.assertEqual(export.call_args_list[0].kwargs, {'output':host.CODEC_OUTPUTS[case]})

    def test_codec_cli_keeps_closed_mode_and_output(self):
        common = ['--execute-approved-image', '--file-db-oracle']
        for extra in (['--catalog-reference-codec','other'],
                      ['--catalog-reference-codec','distinct_a','--catalog-reference-identity','distinct_a'],
                      ['--catalog-reference-codec','distinct_a'],
                      ['--catalog-reference-codec','distinct_a','--output','native-db-oracle/distinct_a.json']):
            with self.assertRaises(SystemExit) as error:
                host.main(common + extra)
            self.assertEqual(error.exception.code, 2)
        self.assertEqual(host.CODEC_OUTPUTS['distinct_a'], Path('native-db-oracle/codec_distinct_a.json'))
        self.assertEqual(host.CODEC_AGGREGATE, Path('native-db-oracle/codec-aggregate.json'))


if __name__ == '__main__':
    unittest.main()
