"""Offline tests for the unmeasured deletion-mark source and native route."""
from pathlib import Path
import base64
import copy
import hashlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/native_1c_bootstrap'))
from catalog_deletion_mark_behavior import fixture, route
import catalog_deletion_mark_suite as suite

spec = importlib.util.spec_from_file_location('catalog_deletion_host', ROOT / 'scripts/native_1c_catalog_deletion_mark_profile.py')
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)
NONCE = 'a' * 32


def wire(values, nonce=NONCE):
    prefix = 'CDM|' + nonce + '|'
    return (prefix + 'entered\n' + ''.join(prefix + str(i) + '|B|' + ('1' if v else '0') + '\n'
            for i, v in enumerate(values, 1)) + prefix + 'completed\n').encode('ascii')


def envelope():
    hashes = {name: host.FULL.digest((ROOT / name).read_bytes()) for name in host.staged_files()}
    raw = route.canonical([False] * 32)
    stage = suite.empty_report(NONCE)
    module = host.FULL.digest(host.FULL.generated_module(route.program(fixture.load_saved()[0], NONCE)))
    stage.update(status='ok', failure_kind='none', failure_phase='final', input_sha256=hashes,
                 source_sha256=host.SOURCE_SHA256, module_sha256=module, module_verified_sha256=module,
                 output_sha256=host.FULL.digest(raw), output_size=len(raw), record_count=32)
    for flag in host.FLAGS: stage[flag] = True
    stage['process_diagnostics'].update(stage='after_exit', reason='none')
    payload = {'schema': host.SCHEMA, 'profile': host.PROFILE, 'nonce': NONCE,
               'report': {'status': 'ok', 'native_tests_completed': True, 'stage3': stage},
               'outputs': [{'name': 'catalog-object.out', 'size': len(raw),
                            'sha256': host.FULL.digest(raw), 'data_b64': base64.b64encode(raw).decode()}]}
    return payload, hashes, raw


def identity(raw, **kwargs):
    return json.loads(raw)


def read_windows_staging_fixture(path, limit, *, nonempty=False):
    """Synthetic Windows fixture only; not the Linux no-follow security gate."""
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError('link')
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise ValueError('file')
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
        after = path.lstat()
        identity = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                                 info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity(before) != identity(after) or len(data) != before.st_size or len(data) > limit or (nonempty and not data):
            raise ValueError('unstable')
        return data
    except (OSError, ValueError):
        raise host.FULL.FullError('invalid_private_file') from None


class DeletionMarkPacketTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_windows_staging_fixture)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_source_hash_and_fixture(self):
        setup, assets = fixture.load_saved()
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(), route.SOURCE_SHA256)
        self.assertEqual(assets['generated/observe.bsl'], route.source())
        self.assertEqual(setup.name, 'OwnedCatalog4f4ccaa9')

    def test_source_tampering_fails(self):
        with mock.patch.object(Path, 'read_bytes', return_value=b'not the source'):
            with self.assertRaises(ValueError): route.source()

    def test_program_binds_setup_and_nonce(self):
        setup, _ = fixture.load_saved()
        data = route.program(setup, NONCE)
        self.assertIn(('CDM|' + NONCE + '|entered').encode(), data)
        self.assertIn(route.source(), data)
        self.assertLessEqual(len(data), route.MAX_OUTPUT)

    def test_program_rejects_bad_identity_and_nonce(self):
        setup, _ = fixture.load_saved()
        for nonce in ('', 'g' * 32, 'a' * 31):
            with self.assertRaises(ValueError): route.program(setup, nonce)
        with self.assertRaises(ValueError): route.program(object(), NONCE)

    def test_wire_roundtrip_all_32_boolean_observations(self):
        values = [i % 2 == 0 for i in range(route.COUNT)]
        self.assertEqual(route.parse_wire(wire(values), NONCE), values)
        self.assertEqual(json.loads(route.canonical(values)), values)

    def test_wire_rejects_wrong_nonce(self):
        with self.assertRaises(ValueError): route.parse_wire(wire([False] * 32), 'b' * 32)

    def test_wire_rejects_missing_and_extra_results(self):
        for n in (31, 33):
            with self.assertRaises(ValueError): route.parse_wire(wire([False] * n), NONCE)

    def test_wire_rejects_duplicate_number_and_invalid_type(self):
        raw = wire([False] * 32)
        for altered in (raw.replace(b'|2|B|0', b'|1|B|0'), raw.replace(b'|2|B|0', b'|2|N|0')):
            with self.assertRaises(ValueError): route.parse_wire(altered, NONCE)

    def test_wire_rejects_crlf_and_partial(self):
        raw = wire([False] * 32)
        for altered in (raw.replace(b'\n', b'\r\n'), raw[:-1]):
            with self.assertRaises(ValueError): route.parse_wire(altered, NONCE)

    def test_canonical_rejects_integers_and_wrong_length(self):
        for values in ([0] * 32, [False] * 31):
            with self.assertRaises(ValueError): route.canonical(values)

    def test_staging_binds_new_suite_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp).resolve() / 'staged'
            hashes = host.stage_inputs(ROOT, destination, host.SMOKE)
            self.assertEqual(hashes[host.SOURCE], route.SOURCE_SHA256)
            self.assertEqual((destination / 'bootstrap/catalog_object_suite.py').read_bytes(),
                             (ROOT / 'scripts/native_1c_bootstrap/catalog_deletion_mark_suite.py').read_bytes())
            host.validate_inputs(destination, hashes, host.SMOKE)

    def test_staging_detects_changed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp).resolve() / 'staged'
            hashes = host.stage_inputs(ROOT, destination, host.SMOKE)
            (destination / 'bootstrap/catalog_deletion_mark_behavior/observe.bsl').write_bytes(b'changed')
            with self.assertRaises(host.CatalogObjectError): host.validate_inputs(destination, hashes, host.SMOKE)


    def test_envelope_accepts_bound_32_observations(self):
        payload, hashes, raw = envelope()
        self.assertEqual(host.validate_envelope(json.dumps(payload).encode(), NONCE, hashes, identity)[1], raw)

    def test_envelope_rejects_mismatched_witnesses(self):
        payload, hashes, _ = envelope()
        for key, value in (('source_sha256', 'f' * 64), ('module_sha256', 'f' * 64),
                           ('record_count', 24), ('completed', False)):
            changed = copy.deepcopy(payload)
            changed['report']['stage3'][key] = value
            with self.assertRaises(host.CatalogObjectError):
                host.validate_envelope(json.dumps(changed).encode(), NONCE, hashes, identity)

    def test_envelope_fails_closed_without_output(self):
        payload, hashes, _ = envelope()
        payload['outputs'] = []
        payload['report'].update(status='stage3_failed', native_tests_completed=False)
        payload['report']['stage3'].update(status='failed', failure_kind='module_mismatch',
                                          failure_phase='enterprise', completed=False)
        with self.assertRaises(host.CatalogObjectError) as caught:
            host.validate_envelope(json.dumps(payload).encode(), NONCE, hashes, identity)
        self.assertEqual(caught.exception.native_failure['failure_phase'], 'enterprise')


class DeletionMarkLifecycleIntegrationTests(unittest.TestCase):
    def setUp(self):
        if os.name == 'nt':
            patcher = mock.patch.object(host.FULL, 'read_regular', side_effect=read_windows_staging_fixture)
            patcher.start(); self.addCleanup(patcher.stop)

    def test_create_keeps_every_existing_isolation_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp).resolve() / 'staged'
            hashes = host.stage_inputs(ROOT, staged, host.SMOKE)
            command = host.container_command(staged, hashes, 'onec-catalog-object-' + NONCE, NONCE, host.SMOKE)
        expected = ['docker', 'create', '--name', 'onec-catalog-object-' + NONCE,
            '--label', host.DOCKER.OWNER_LABEL + '=' + NONCE, '--hostname', 'onec-smoke',
            '--pull', 'never', '--platform', 'linux/amd64', '--network', 'none',
            '--user', '1000:1000', '--read-only', '--no-healthcheck', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--pids-limit', '256',
            '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
            '--ulimit', 'nofile=1024:1024', '--ulimit', 'fsize=67108864:67108864',
            '--ipc', 'private', '--shm-size', '128m', '--log-driver', 'none',
            '--stop-timeout', '10', '--init',
            '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777',
            '--mount', f'type=bind,src={staged},dst=/smoke,readonly',
            '--workdir', '/tmp', '--entrypoint', '/usr/bin/env', host.SMOKE.IMAGE,
            '-i', 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME=/tmp/home', 'XDG_RUNTIME_DIR=/tmp/runtime', 'DISPLAY=:99',
            'LANG=ru_RU.UTF-8', 'LC_ALL=ru_RU.UTF-8', 'TZ=Etc/UTC',
            '/bin/bash', '--noprofile', '--norc', '/smoke/probe.sh',
            '--catalog-object-suite', '--invocation-nonce', NONCE]
        self.assertEqual(command, expected)

    def test_mismatched_name_nonce_is_rejected(self):
        with mock.patch.object(host, 'validate_inputs'):
            with self.assertRaises(host.CatalogObjectError):
                host.container_command(Path('/staged'), {}, 'onec-catalog-object-' + 'b' * 32, NONCE, host.SMOKE)

    def run_fake(self, temporary, *, failed_create=False, failed_cleanup=False):
        from test_native_docker_lifecycle import FakeDocker
        fake = FakeDocker()
        # The harness imports its lifecycle via an isolated sibling module.
        fake.snapshot[2] = host.SMOKE.IMAGE
        payload, _, raw = envelope()
        def start(command):
            fake.started = True
            return 0, json.dumps(payload).encode()
        fake.overrides['start'] = start
        if failed_create:
            fake.overrides['create'] = host.DOCKER.CliError('docker_command_timeout')
        if failed_cleanup: fake.overrides['ps'] = 0, b'still-present'
        real_validate = host.validate_envelope
        def validate(*args): return real_validate(*args, validator=identity)
        def export(root, files):
            self.assertEqual(list(Path(temporary).iterdir()), [])
            self.assertEqual(fake.calls[-1][0], 'ps')
            self.assertEqual(files['catalog-object.out'], raw)
        with mock.patch.dict(os.environ, {'GHCR_TOKEN': 'synthetic', 'GHCR_USER': 'owner'}), \
             mock.patch.object(host.uuid, 'uuid4', return_value=types.SimpleNamespace(hex=NONCE)), \
             mock.patch.object(host.FULL, 'repository_provenance', return_value={}), \
             mock.patch.object(host.FULL, 'interpreter_provenance', return_value={}), \
             mock.patch.object(host.FULL, 'windows_fingerprints', return_value={}), \
             mock.patch.object(host.SMOKE, 'run_silent'), \
             mock.patch.object(host.SMOKE, 'bounded_run', side_effect=AssertionError('legacy runner forbidden')), \
             mock.patch.object(host.DOCKER, 'bounded_cli', side_effect=fake), \
             mock.patch.object(host, 'validate_envelope', side_effect=validate) as validated, \
             mock.patch.object(host, 'export_artifact', side_effect=export) as exported:
            if failed_create or failed_cleanup:
                with self.assertRaises(host.DOCKER.LifecycleError) as caught:
                    host.run(ROOT, Path(temporary), export_native_outputs=True)
                exported.assert_not_called(); validated.assert_not_called()
                self.assertFalse(caught.exception.container_cleanup_verified)
                self.assertEqual(list(Path(temporary).iterdir()), [])
                return caught.exception, fake
            result = host.run(ROOT, Path(temporary), export_native_outputs=True)
            exported.assert_called_once()
            self.assertTrue(result['container_cleanup_verified'])
            self.assertTrue(result['docker_cli_reap_verified'])
            self.assertTrue(result['private_payloads_removed'])
            self.assertTrue(result['native_measurement_accepted'])
            self.assertFalse(result['runtime_parity_accepted'])
            self.assertIn('scripts/native_1c_docker_lifecycle.py', result['host_source_sha256'])
            return result, fake

    def test_native_envelope_and_export_follow_verified_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.run_fake(temporary)

    def test_create_uncertainty_discards_evidence_without_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            error, fake = self.run_fake(temporary, failed_create=True)
        self.assertEqual(str(error), 'docker_command_timeout')
        self.assertEqual([call[0] for call in fake.calls], ['image', 'create'])

    def test_cleanup_uncertainty_discards_attached_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            error, fake = self.run_fake(temporary, failed_cleanup=True)
        self.assertEqual(error.cleanup_error, 'container_cleanup_unverified')
        self.assertTrue(fake.started)

    def test_public_failure_distinguishes_cli_reap_from_container_cleanup(self):
        error = host.DOCKER.LifecycleError('docker_cli_reap_unverified',
            cli_reap_verified=False, container_cleanup_verified=True)
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(host, 'ROOT', Path(temporary)), \
             mock.patch.object(host, 'run', side_effect=error), \
             mock.patch.object(sys, 'argv', ['profile', '--execute-approved-image']), \
             mock.patch('builtins.print'):
            self.assertEqual(host.main(), 1)
            report = json.loads((Path(temporary) / 'native-smoke/catalog-deletion-mark.json').read_bytes())
        self.assertFalse(report['docker_cli_reap_verified'])
        self.assertTrue(report['container_cleanup_verified'])
        self.assertFalse(report['native_measurement_accepted'])
        self.assertNotIn('native_report', report)
        self.assertNotIn('cleanup_error', report)


if __name__ == '__main__': unittest.main()
