"""Offline host/security contracts. Synthetic fixtures are not native 1C proof.

No Docker, network, credentials, or native executable is used by this suite.
Windows uses a consistent path-metadata fixture reader, not an emulation of the
Linux no-follow/descriptor-race security boundary; those checks run on POSIX.
"""
from __future__ import annotations

import contextlib
import copy
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / 'scripts/native_1c_db_oracle'
NONCE = 'a' * 32
PRIVATE = 'PRIVATE-SYNTHETIC-NATIVE-DATA'
APPROVED = ['--execute-approved-image', '--file-db-oracle']
DESCRIPTOR_EXPORT = (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
                     and os.open in os.supports_dir_fd)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The production entry points use sibling imports. Preserve the runner's path
# and generic module names so collection order cannot redirect unrelated tests.
_saved_path = sys.path[:]
_saved_bytecode = sys.dont_write_bytecode
_names = ('protocol', 'snapshots', 'inputs', 'inject_metadata', 'inject_modules', 'native_1c_smoke')
_saved_modules = {name: sys.modules.get(name) for name in _names}
try:
    sys.path[:0] = [str(HELPERS), str(ROOT / 'scripts'), str(ROOT / 'scripts/native_1c_bootstrap')]
    for _name in _names:
        sys.modules.pop(_name, None)
    fixtures = _load('db_oracle_security_fixtures', ROOT / 'tests/test_native_1c_db_oracle_stage.py')
    host = _load('db_oracle_security_host', ROOT / 'scripts/native_1c_db_oracle.py')
    inputs = importlib.import_module('inputs')
    protocol = importlib.import_module('protocol')
    OracleError = importlib.import_module('snapshots').OracleError
finally:
    sys.path[:] = _saved_path
    sys.dont_write_bytecode = _saved_bytecode
    for _name, _module in _saved_modules.items():
        if _module is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _module


def synthetic_reader(path):
    """Bounded static fixtures using one metadata API on Windows only."""
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise OracleError('invalid_input')
        if not 0 < before.st_size <= inputs.MAX_SOURCE:
            raise OracleError('invalid_input')
        with path.open('rb') as source:
            raw = source.read(inputs.MAX_SOURCE + 1)
        after = path.lstat()
        fields = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if fields(before) != fields(after) or len(raw) != before.st_size:
            raise OracleError('invalid_input')
        return raw
    except OSError:
        raise OracleError('invalid_input') from None


def make_writable(root):
    if root.exists():
        for path in root.rglob('*'):
            if not path.is_symlink():
                path.chmod(0o755 if path.is_dir() else 0o644)
        root.chmod(0o755)


class SourceCase(unittest.TestCase):
    def setUp(self):
        # verify_inputs deliberately imports its validator lazily. Keep that
        # binding scoped to this test instead of mutating suite import state.
        protocol_import = mock.patch.dict(sys.modules, {'protocol': protocol})
        protocol_import.start()
        self.addCleanup(protocol_import.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(lambda: make_writable(self.root))
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        for relative in inputs.SOURCE_FILES:
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / relative).read_bytes())
        if os.name == 'nt':
            patcher = mock.patch.object(inputs, 'read_source', side_effect=synthetic_reader)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.identity = fixtures.provenance()
        self.identity['sources'] = inputs.source_hashes(self.repo)
        self.staged = self.root / 'staged'

    def stage(self):
        inputs.stage_inputs(self.repo, self.staged, NONCE, self.identity)
        return self.staged

    def assert_rejected(self, action, kind=None):
        with self.assertRaises(OracleError) as caught:
            action()
        if kind is not None:
            self.assertEqual(caught.exception.kind, kind)
        self.assertNotIn(PRIVATE, str(caught.exception))


class InputSecurityTests(SourceCase):
    def test_exact_reviewed_source_manifest_and_hashes(self):
        expected = {
            'scripts/native_1c_db_oracle.py': 'host.py',
            **{'scripts/native_1c_db_oracle/' + name: name for name in (
                'probe.sh', 'run.py', 'protocol.py', 'snapshots.py', 'inject_metadata.py', 'inputs.py',
                'metadata/Catalog.xml', 'metadata/CommonModule.xml', 'metadata/Role.xml',
                'metadata/SetupRights.xml', 'metadata/CRUDRights.xml', 'modules/SessionModule.bsl',
                'modules/ManagedApplicationModule.bsl', 'modules/NativeOracleServer.bsl')},
            'scripts/native_1c_bootstrap/inject_modules.py': 'inject_modules.py',
        }
        self.assertEqual(inputs.SOURCE_FILES, expected)
        self.stage()
        self.assertEqual(inputs.staged_hashes(self.staged), self.identity['sources'])
        self.assertEqual(inputs.verify_inputs(self.staged, NONCE), self.identity)
        self.assertEqual({p.relative_to(self.staged).as_posix() for p in self.staged.rglob('*') if p.is_file()},
                         set(expected.values()) | {'invocation.json'})
        for source, target in expected.items():
            self.assertEqual((self.staged / target).read_bytes(), (self.repo / source).read_bytes())

    @unittest.skipIf(os.name == 'nt', 'POSIX read-only permissions are not NTFS isolation')
    def test_staged_inputs_are_nonwritable_before_mount(self):
        self.stage()
        for path in (self.staged, *self.staged.rglob('*')):
            self.assertEqual(path.stat().st_mode & 0o222, 0)

    def test_missing_extra_or_empty_staged_file_rejected(self):
        for mutation in ('missing', 'extra', 'empty', 'directory'):
            with self.subTest(mutation=mutation):
                self.stage(); make_writable(self.staged)
                if mutation == 'missing': (self.staged / 'probe.sh').unlink()
                elif mutation == 'extra': (self.staged / 'native.1CD').write_text(PRIVATE)
                elif mutation == 'empty': (self.staged / 'probe.sh').write_bytes(b'')
                else: (self.staged / 'unreviewed').mkdir()
                self.assert_rejected(lambda: inputs.staged_hashes(self.staged), 'invalid_input')
                shutil.rmtree(self.staged)

    def test_source_mutation_after_provenance_cannot_be_staged(self):
        (self.repo / 'scripts/native_1c_db_oracle/probe.sh').write_bytes(b'changed synthetic input')
        self.assert_rejected(self.stage, 'provenance_mismatch')

    def test_staged_mutation_and_wrong_invocation_nonce_rejected(self):
        self.stage(); make_writable(self.staged)
        self.assert_rejected(lambda: inputs.verify_inputs(self.staged, 'b' * 32), 'provenance_mismatch')
        (self.staged / 'probe.sh').write_text('changed synthetic input')
        self.assert_rejected(lambda: inputs.verify_inputs(self.staged, NONCE), 'provenance_mismatch')

    def test_forged_invocation_fields_cannot_select_image_platform_or_sources(self):
        self.stage(); make_writable(self.staged)
        original = json.loads((self.staged / 'invocation.json').read_text())
        mutations = [lambda d: d.update(schema=True), lambda d: d.update(external_db=PRIVATE),
                     lambda d: d['provenance'].update(image='attacker/image'),
                     lambda d: d['provenance'].update(platform='linux/arm64'),
                     lambda d: d['provenance'].update(actual_version=protocol.VERSION),
                     lambda d: d['provenance'].update(sources={})]
        for mutate in mutations:
            value = copy.deepcopy(original); mutate(value)
            (self.staged / 'invocation.json').write_text(json.dumps(value))
            self.assert_rejected(lambda: inputs.verify_inputs(self.staged, NONCE))

    def test_stale_destination_never_overwritten(self):
        self.staged.mkdir(); sentinel = self.staged / 'private'; sentinel.write_text(PRIVATE)
        self.assert_rejected(self.stage, 'stale_evidence')
        self.assertEqual(sentinel.read_text(), PRIVATE)

    @unittest.skipIf(os.name == 'nt', 'POSIX no-follow links are checked on the native host platform')
    def test_symlink_sources_ancestors_staging_and_dangling_destination_rejected(self):
        source = self.repo / 'scripts/native_1c_db_oracle/probe.sh'
        real = self.root / 'source'; source.rename(real); source.symlink_to(real)
        self.assert_rejected(lambda: inputs.source_hashes(self.repo), 'invalid_input')
        source.unlink(); real.rename(source)
        directory = self.repo / 'scripts/native_1c_db_oracle'
        directory.rename(self.root / 'helper-real'); directory.symlink_to(self.root / 'helper-real', target_is_directory=True)
        self.assert_rejected(lambda: inputs.source_hashes(self.repo), 'invalid_input')
        directory.unlink(); (self.root / 'helper-real').rename(directory)
        self.staged.symlink_to(self.root / 'missing', target_is_directory=True)
        self.assert_rejected(self.stage, 'stale_evidence'); self.staged.unlink()
        self.stage(); make_writable(self.staged)
        target = self.staged / 'probe.sh'; target.unlink(); target.symlink_to(source)
        self.assert_rejected(lambda: inputs.staged_hashes(self.staged), 'invalid_input')

    @unittest.skipIf(os.name == 'nt', 'POSIX hardlink/special-file boundary')
    def test_hardlinked_and_special_source_files_rejected(self):
        path = self.root / 'input'; path.write_bytes(b'fixture')
        os.link(path, self.root / 'hardlink')
        self.assert_rejected(lambda: inputs.read_source(path), 'invalid_input')
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        self.assert_rejected(lambda: inputs.read_source(fifo), 'invalid_input')

    def test_source_size_limit_and_missing_input_rejected(self):
        for value in (b'', b'x' * (inputs.MAX_SOURCE + 1)):
            path = self.root / 'size'; path.write_bytes(value)
            self.assert_rejected(lambda: inputs.read_source(path), 'invalid_input')
        self.assert_rejected(lambda: inputs.read_source(self.root / 'missing'), 'invalid_input')

    @unittest.skipIf(os.name == 'nt', 'Descriptor identity/mtime checks are POSIX-specific')
    def test_reader_rejects_replacement_and_mutation_during_read(self):
        path = self.root / 'input'; path.write_bytes(b'fixture')
        actual = path.stat()
        def changed(**updates):
            return SimpleNamespace(**{key: updates.get(key, getattr(actual, key)) for key in
                ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
        with mock.patch.object(inputs.os, 'fstat', return_value=changed(st_ino=actual.st_ino + 1)):
            self.assert_rejected(lambda: inputs.read_source(path), 'invalid_input')
        with mock.patch.object(inputs.os, 'fstat', side_effect=[actual, changed(st_mtime_ns=actual.st_mtime_ns + 1)]):
            self.assert_rejected(lambda: inputs.read_source(path), 'invalid_input')


class ContainerCommandTests(SourceCase):
    def test_fixed_image_isolation_single_readonly_mount_and_empty_environment(self):
        self.stage()
        command = host.container_command(self.staged, 'onec-db-oracle-' + NONCE, NONCE)
        values = {'--pull': 'never', '--platform': 'linux/amd64', '--network': 'none', '--user': '1000:1000',
                  '--cap-drop': 'ALL', '--security-opt': 'no-new-privileges:true', '--pids-limit': '256',
                  '--memory': '2g', '--memory-swap': '2g', '--cpus': '2', '--ipc': 'private',
                  '--log-driver': 'none', '--entrypoint': '/usr/bin/env'}
        for option, expected in values.items():
            self.assertEqual(command[command.index(option) + 1], expected)
        for option in ('--read-only', '--no-healthcheck', '--init'):
            self.assertIn(option, command)
        self.assertEqual(command.count('--mount'), 1)
        self.assertEqual(command[command.index('--mount') + 1],
                         f'type=bind,src={self.staged.resolve()},dst=/oracle,readonly')
        self.assertEqual(command[command.index('--tmpfs') + 1], '/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777')
        self.assertEqual(command.count(protocol.IMAGE), 1)
        self.assertEqual(command[command.index(protocol.IMAGE) + 1], '-i')
        self.assertEqual(command[command.index(protocol.IMAGE) + 2:command.index('/bin/bash')], [
            'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            'HOME=/tmp/onec-db-oracle/home', 'TMPDIR=/tmp/onec-db-oracle/temp',
            'XDG_RUNTIME_DIR=/tmp/runtime', 'DISPLAY=:99', 'LANG=ru_RU.UTF-8',
            'LC_ALL=ru_RU.UTF-8', 'TZ=Etc/UTC'])
        self.assertEqual(command[-6:], ['/bin/bash', '--noprofile', '--norc', '/oracle/probe.sh', '--invocation-nonce', NONCE])
        for forbidden in ('--privileged', '--volume', '-v', '--env', '-e', '--env-file', '--device', '--pid'):
            self.assertNotIn(forbidden, command)
        self.assertNotIn('docker.sock', ' '.join(command))
        self.assertNotIn('auth', ' '.join(command))

    def test_malformed_name_nonce_or_mount_path_rejected(self):
        self.stage()
        for name, nonce in ((PRIVATE, NONCE), ('onec-db-oracle-' + NONCE, PRIVATE),
                            ('onec-db-oracle-' + NONCE + ';', NONCE)):
            self.assert_rejected(lambda: host.container_command(self.staged, name, nonce), 'invalid_input')
        comma = self.root / 'comma,path'; self.staged.rename(comma)
        self.assert_rejected(lambda: host.container_command(comma, 'onec-db-oracle-' + NONCE, NONCE), 'invalid_input')


class HostSecurityTests(SourceCase):
    def setUp(self):
        super().setUp()
        self.work = self.root / 'work'; self.work.mkdir()
        self.events = []; self.configs = []; self.captured = []
        self.output = self.repo / host.OUTPUT
        self.github_output = self.root / 'github-output'

    def invoke(self, *, payload=None, exit_code=0, fail=None, cleanup_bad=False,
               private_cleanup_bad=False, main=False, credentials=True, changed_provenance=False,
               image_result=(0, b'linux/amd64|0'), actor='Atridis'):
        env = {'GHCR_USER': actor, 'GHCR_TOKEN': PRIVATE, 'DOCKER_AUTH_CONFIG': PRIVATE,
               'DOCKER_HOST': 'tcp://attacker:2375', 'HTTPS_PROXY': PRIVATE, 'LD_PRELOAD': PRIVATE,
               'GITHUB_OUTPUT': str(self.github_output)}
        if not credentials:
            env.pop('GHCR_TOKEN')
        def identity():
            self.assertNotIn('GHCR_TOKEN', os.environ); self.assertNotIn('GHCR_USER', os.environ)
            self.events.append('provenance')
            value = copy.deepcopy(self.identity)
            if changed_provenance and self.events.count('provenance') > 1:
                value['tree'] = 'd' * 40
            return value
        def boundary(args, command_env, seconds):
            self.assertNotIn('GHCR_TOKEN', os.environ); self.assertNotIn('GHCR_USER', os.environ)
            self.assertEqual(set(command_env), {'PATH', 'HOME', 'DOCKER_CONFIG', 'LANG', 'LC_ALL'})
            self.assertNotIn(PRIVATE, json.dumps(args)); self.assertNotIn(PRIVATE, json.dumps(command_env))
            action = args[1]; self.events.append(action)
            config = Path(command_env['DOCKER_CONFIG']); self.configs.append(config)
            self.assertTrue(config.is_dir())
            if action not in ('login', 'pull'):
                self.assertEqual(config.name, 'no-auth')
                self.assertFalse((config.parent / 'auth').exists())
                self.assertEqual(list(config.iterdir()), [])
            if fail == action:
                raise host.smoke.SmokeError('container_timeout' if action == 'run' else PRIVATE)
        def silent(args, command_env, seconds, input_bytes=None):
            boundary(args, command_env, seconds)
            if args[1] == 'login':
                self.assertEqual(input_bytes, PRIVATE.encode())
                self.assertEqual(args, ['docker', 'login', 'ghcr.io', '--username', 'Atridis', '--password-stdin'])
                (Path(command_env['DOCKER_CONFIG']) / 'config.json').write_text(PRIVATE)
            else:
                self.assertIsNone(input_bytes)
            if args[1] == 'pull':
                self.assertEqual(args, ['docker', 'pull', '--platform', 'linux/amd64', protocol.IMAGE])
        def bounded(args, command_env, seconds, limit):
            boundary(args, command_env, seconds)
            if args[1] == 'image':
                self.assertEqual(limit, 128)
                return image_result
            if args[1] == 'ps':
                self.assertEqual(limit, 128)
                self.assertIn('name=^/onec-db-oracle-' + NONCE + '$', args)
                return 0, b'still-live' if cleanup_bad else b''
            self.assertEqual(args[1], 'run'); self.captured.append(args)
            self.assertEqual(seconds, 2400); self.assertEqual(limit, 32768)
            if payload is not None:
                return exit_code, payload
            report, _ = fixtures.fixture_report()
            report['provenance'] = copy.deepcopy(self.identity)
            report['provenance']['actual_version'] = protocol.VERSION
            return exit_code, protocol.encode(report)
        class LeftoverDirectory:
            def __init__(self, **kwargs): self.name = tempfile.mkdtemp(**kwargs)
            def __enter__(self): return self.name
            def __exit__(self, *args): return False
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, env, clear=True))
            stack.enter_context(mock.patch.object(host, 'ROOT', self.repo))
            stack.enter_context(mock.patch.object(host, 'provenance', side_effect=identity))
            stack.enter_context(mock.patch.object(host.uuid, 'uuid4', return_value=SimpleNamespace(hex=NONCE)))
            stack.enter_context(mock.patch.object(host.smoke, 'run_silent', side_effect=silent))
            stack.enter_context(mock.patch.object(host.smoke, 'bounded_run', side_effect=bounded))
            popen = stack.enter_context(mock.patch.object(host.smoke.subprocess, 'Popen', side_effect=AssertionError('real process forbidden')))
            process_run = stack.enter_context(mock.patch.object(host.smoke.subprocess, 'run', side_effect=AssertionError('real process forbidden')))
            if private_cleanup_bad:
                stack.enter_context(mock.patch.object(host.tempfile, 'TemporaryDirectory', LeftoverDirectory))
            stdout = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stderr = stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            if main:
                stack.enter_context(mock.patch.object(host.tempfile, 'gettempdir', return_value=str(self.work)))
                original_export = host.export_report
                def checked_export(raw, root_identity):
                    self.assertIn('ps', self.events)
                    if not private_cleanup_bad:
                        self.assertEqual(list(self.work.iterdir()), [])
                    self.assertFalse(self.github_output.exists())
                    result = original_export(raw, root_identity)
                    self.events.append('export')
                    return result
                stack.enter_context(mock.patch.object(host, 'export_report', side_effect=checked_export))
                value = host.main(APPROVED)
            else:
                value = host.run_oracle(self.work)
            popen.assert_not_called(); process_run.assert_not_called()
            self.logs = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(PRIVATE, self.logs)
        if not private_cleanup_bad:
            self.assertEqual(list(self.work.iterdir()), [])
        self.assertTrue(all(not path.exists() for path in self.configs) or private_cleanup_bad)
        return value

    def test_credentials_removed_before_provenance_and_every_external_command(self):
        report = self.invoke()
        self.assertTrue(report['accepted'])
        self.assertEqual(self.events, ['provenance', 'login', 'pull', 'image', 'run', 'rm', 'ps', 'provenance'])
        self.assertNotIn(PRIVATE, protocol.encode(report).decode())

    def test_only_private_auth_for_login_pull_and_noauth_for_run_cleanup(self):
        self.invoke()
        self.assertEqual([p.name for p in self.configs], ['auth', 'auth', 'no-auth', 'no-auth', 'no-auth', 'no-auth'])

    def test_missing_registry_credentials_fails_before_docker(self):
        report = self.invoke(credentials=False)
        self.assertEqual(report['failure_kind'], 'registry_credentials_missing')
        self.assertEqual(self.events, ['provenance']); self.assertFalse(report['accepted'])
        self.assertEqual(report['artifacts'], [])

    def test_malformed_registry_actor_never_reaches_external_command(self):
        for actor in ('', '--config=' + PRIVATE, 'name with spaces', 'a' * 40):
            self.events.clear(); self.configs.clear()
            with self.subTest(actor=actor):
                report = self.invoke(actor=actor)
                self.assertEqual(report['failure_kind'], 'registry_credentials_missing')
                self.assertEqual(self.events, ['provenance'])
                self.assertFalse(report['accepted'])

    def test_non_amd64_image_or_declared_image_volumes_never_runs_native(self):
        for result in ((0, b'linux/arm64|0'), (0, b'linux/amd64|1'), (1, b'linux/amd64|0'), (0, PRIVATE.encode())):
            self.events.clear(); self.configs.clear()
            with self.subTest(result=result):
                report = self.invoke(image_result=result)
                self.assertEqual(report['failure_kind'], 'container_unavailable')
                self.assertNotIn('run', self.events); self.assertFalse(report['accepted'])

    def test_login_pull_and_inspection_failure_never_runs_native(self):
        for step in ('login', 'pull', 'image'):
            self.events.clear(); self.configs.clear()
            with self.subTest(step=step):
                report = self.invoke(fail=step)
                self.assertFalse(report['accepted']); self.assertNotIn('run', self.events)
                self.assertNotIn(PRIVATE, protocol.encode(report).decode())
                self.assertEqual(report['artifacts'], [])

    def test_native_timeout_still_removes_and_verifies_container(self):
        report = self.invoke(fail='run')
        self.assertEqual(report['failure_kind'], 'timeout')
        self.assertEqual(self.events[-2:], ['rm', 'ps'])
        self.assertFalse(report['accepted']); self.assertTrue(report['cleanup']['container_removed'])

    def test_container_or_private_cleanup_failure_never_accepts_or_exports_artifacts(self):
        for options in ({'cleanup_bad': True}, {'fail': 'rm'}, {'fail': 'ps'}, {'private_cleanup_bad': True}):
            self.events.clear(); self.configs.clear()
            with self.subTest(options=options):
                report = self.invoke(**options)
                self.assertFalse(report['accepted']); self.assertEqual(report['failure_kind'], 'cleanup_unverified')
                self.assertEqual(report['artifacts'], [])
                protocol.validate_report(protocol.encode(report), nonce=NONCE, provenance=self.identity, final=True)
                make_writable(self.work)
                for child in self.work.iterdir(): shutil.rmtree(child)

    def test_native_cleanup_failure_cannot_be_overridden_by_host_cleanup(self):
        report, _ = fixtures.fixture_report()
        report['provenance'] = copy.deepcopy(self.identity)
        report['provenance']['actual_version'] = protocol.VERSION
        report.update(status='failed', failed_stage='cleanup', failure_kind='cleanup_unverified', artifacts=[])
        report['cleanup']['raw_files_removed'] = False
        report['stages'][-1]['status'] = 'failed'
        report['stages'][-1]['checks']['raw_files_removed'] = False
        observed = self.invoke(payload=protocol.encode(report), exit_code=1)
        self.assertFalse(observed['accepted']); self.assertFalse(observed['cleanup']['raw_files_removed'])
        self.assertTrue(observed['cleanup']['container_removed'])
        self.assertTrue(observed['cleanup']['private_staging_removed'])
        self.assertEqual(observed['artifacts'], [])

    def test_provenance_change_after_execution_prevents_acceptance(self):
        report = self.invoke(changed_provenance=True)
        self.assertEqual(report['failure_kind'], 'provenance_mismatch')
        self.assertFalse(report['accepted']); self.assertEqual(report['artifacts'], [])

    def test_mismatched_exit_and_forged_or_raw_or_oversize_payload_never_leaks(self):
        good, _ = fixtures.fixture_report()
        good['provenance'] = copy.deepcopy(self.identity); good['provenance']['actual_version'] = protocol.VERSION
        forged = copy.deepcopy(good); forged['nonce'] = 'b' * 32
        rawfield = copy.deepcopy(good); rawfield['raw'] = PRIVATE
        for payload, code in ((protocol.encode(good), 1), (protocol.encode(forged), 0),
                (json.dumps(rawfield).encode(), 0), (PRIVATE.encode(), 1),
                (PRIVATE.encode() * 2000, 0), (b'{"schema":1,"schema":1}', 0)):
            self.events.clear(); self.configs.clear()
            with self.subTest(payload_length=len(payload), code=code):
                report = self.invoke(payload=payload, exit_code=code)
                self.assertFalse(report['accepted']); self.assertEqual(report['artifacts'], [])
                self.assertIn('rm', self.events); self.assertIn('ps', self.events)
                self.assertNotIn(PRIVATE, protocol.encode(report).decode())

    @unittest.skipUnless(DESCRIPTOR_EXPORT, 'Native host export requires POSIX no-follow dirfd support')
    def test_export_is_fixed_finite_report_after_cleanup_and_readiness(self):
        self.assertEqual(self.invoke(main=True), 0)
        report = json.loads(self.output.read_text())
        self.assertTrue(report['accepted']); self.assertTrue(all(report['cleanup'].values()))
        self.assertEqual(self.github_output.read_text(), 'report_ready=true\n')
        self.assertEqual(self.events[-1], 'export')
        self.assertEqual([p.relative_to(self.output.parent).as_posix() for p in self.output.parent.iterdir()], ['report.json'])
        self.assertLessEqual(self.output.stat().st_size, 32768)
        self.assertNotIn(PRIVATE, self.output.read_text())

    @unittest.skipUnless(DESCRIPTOR_EXPORT, 'Native host export requires POSIX no-follow dirfd support')
    def test_cleanup_failed_diagnostic_can_be_ready_but_never_accepted(self):
        self.assertEqual(self.invoke(main=True, cleanup_bad=True), 1)
        report = json.loads(self.output.read_text())
        self.assertFalse(report['accepted']); self.assertEqual(report['artifacts'], [])
        self.assertEqual(report['failure_kind'], 'cleanup_unverified')
        self.assertEqual(self.github_output.read_text(), 'report_ready=true\n')

    @unittest.skipUnless(DESCRIPTOR_EXPORT, 'Native host export requires POSIX no-follow dirfd support')
    def test_raw_failure_main_exports_only_sanitized_finite_diagnosis(self):
        self.assertEqual(self.invoke(main=True, payload=PRIVATE.encode(), exit_code=1), 1)
        report = json.loads(self.output.read_text())
        self.assertFalse(report['accepted']); self.assertEqual(report['failure_kind'], 'transport_invalid')
        self.assertEqual(report['artifacts'], []); self.assertEqual(report['snapshots'], [])
        self.assertNotIn(PRIVATE, self.output.read_text())


class ArgumentSecurityTests(unittest.TestCase):
    def test_explicit_independent_optins_and_only_fixed_output(self):
        vectors = [[], ['--execute-approved-image'], ['--file-db-oracle'],
                   APPROVED + ['--output', PRIVATE], APPROVED + ['--output', '../report.json']]
        for arguments in vectors:
            with self.subTest(arguments=arguments), mock.patch.object(host, 'run_oracle') as run, \
                    contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit) as caught:
                host.main(arguments)
            self.assertEqual(caught.exception.code, 2); run.assert_not_called()
            self.assertEqual(stderr.getvalue(), 'File-DB oracle rejected: invalid_input\n')

    def test_legacy_flags_and_external_inputs_are_rejected(self):
        for flag in ('--full-suite', '--bootstrap', '--client-probe', '--async-probe', '--export',
                     '--database', '--infobase', '--config', '--cf', '--dt', '--dump', '--image', '--input'):
            with self.subTest(flag=flag), mock.patch.object(host, 'run_oracle') as run, \
                    contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
                host.main(APPROVED + [flag, PRIVATE])
            run.assert_not_called(); self.assertNotIn(PRIVATE, stderr.getvalue())
            self.assertEqual(stderr.getvalue(), 'File-DB oracle rejected: invalid_input\n')

    def test_stale_output_not_overwritten_or_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / host.OUTPUT
            output.parent.mkdir(); output.write_text(PRIVATE)
            with mock.patch.object(host, 'ROOT', root), mock.patch.object(host, 'run_oracle') as run, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                host.main(APPROVED)
            run.assert_not_called(); self.assertEqual(output.read_text(), PRIVATE)

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink creation may require elevated Windows privileges')
    def test_symlink_and_dangling_output_or_parent_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); target = root / 'elsewhere'; target.mkdir()
            parent = root / host.OUTPUT.parent
            parent.symlink_to(target, target_is_directory=True)
            for parent_link in (True, False):
                if not parent_link:
                    parent.unlink(); parent.mkdir(); (root / host.OUTPUT).symlink_to(root / 'missing')
                with mock.patch.object(host, 'ROOT', root), mock.patch.object(host, 'run_oracle') as run, \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    host.main(APPROVED)
                run.assert_not_called()

    @unittest.skipIf(os.name == 'nt', 'POSIX export-path substitution security boundary')
    def test_output_parent_substituted_during_run_cannot_redirect_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / 'repo'; repo.mkdir()
            outside = root / 'outside'; outside.mkdir()
            github_output = root / 'github-output'
            def substitute_parent(_):
                (repo / host.OUTPUT.parent).symlink_to(outside, target_is_directory=True)
                report, _ = fixtures.fixture_report()
                report['cleanup'].update(container_removed=True, private_staging_removed=True)
                report['accepted'] = True
                return report
            with mock.patch.object(host, 'ROOT', repo), \
                    mock.patch.object(host, 'run_oracle', side_effect=substitute_parent), \
                    mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(github_output)}), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(host.main(APPROVED), 1)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse(github_output.exists())

    def test_unexpected_host_exception_sanitized_and_no_ready_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); github_output = root / 'github-output'
            with mock.patch.object(host, 'ROOT', root), \
                    mock.patch.object(host, 'run_oracle', side_effect=RuntimeError(PRIVATE)), \
                    mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(github_output)}), \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(host.main(APPROVED), 1)
            self.assertFalse((root / host.OUTPUT).exists()); self.assertFalse(github_output.exists())
            self.assertNotIn(PRIVATE, stderr.getvalue())

    def test_container_entrypoint_rejects_external_inputs_without_starting_native(self):
        for arguments in ([], ['--file-db-oracle'], ['--invocation-nonce', PRIVATE],
                          ['--invocation-nonce', NONCE, '--database', PRIVATE]):
            with mock.patch.object(sys, 'argv', ['run.py', *arguments]), \
                    mock.patch.object(fixtures.stage, 'Native') as native:
                self.assertEqual(fixtures.stage.main(), 2)
            native.assert_not_called()


@unittest.skipUnless(DESCRIPTOR_EXPORT, 'Native host export requires POSIX no-follow dirfd support')
class ExportSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.outside = self.root / 'outside'; self.outside.mkdir()
        self.output = self.repo / host.OUTPUT
        info = self.repo.stat(); self.identity = (info.st_dev, info.st_ino)
        patcher = mock.patch.object(host, 'ROOT', self.repo)
        patcher.start(); self.addCleanup(patcher.stop)

    def test_exclusive_private_fixed_report_does_not_overwrite(self):
        host.export_report(b'{}', self.identity)
        self.assertEqual(self.output.read_bytes(), b'{}\n')
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.parent.stat().st_mode & 0o777, 0o700)
        with self.assertRaises((OracleError, OSError)):
            host.export_report(PRIVATE.encode(), self.identity)
        self.assertEqual(self.output.read_bytes(), b'{}\n')

    def test_newline_counts_toward_32k_cap_and_unsupported_hosts_fail_closed(self):
        for raw in (b'x' * 32768, b'x' * 32769):
            with self.assertRaises(OracleError): host.export_report(raw, self.identity)
        self.assertFalse(self.output.exists())
        with mock.patch.object(host.os, 'supports_dir_fd', set()), self.assertRaises(OracleError):
            host.export_report(b'{}', self.identity)
        self.assertFalse(self.output.exists())
        host.export_report(b'x' * 32767, self.identity)
        self.assertEqual(self.output.stat().st_size, 32768)

    def test_repository_inode_change_rejects_export(self):
        with self.assertRaises(OracleError):
            host.export_report(b'{}', (self.identity[0], self.identity[1] + 1))
        self.assertFalse(self.output.exists())

    def test_parent_swap_between_mkdir_and_open_never_follows_symlink(self):
        original = os.mkdir
        def swap_after_mkdir(path, mode=0o777, *, dir_fd=None):
            result = original(path, mode, dir_fd=dir_fd)
            if path == host.OUTPUT.parent.name and dir_fd is not None:
                self.output.parent.rename(self.repo / 'previous-parent')
                self.output.parent.symlink_to(self.outside, target_is_directory=True)
            return result
        with mock.patch.object(host.os, 'mkdir', side_effect=swap_after_mkdir), \
                self.assertRaises((OracleError, OSError)):
            host.export_report(b'{}', self.identity)
        self.assertEqual(list(self.outside.iterdir()), [])
        self.assertFalse((self.repo / 'previous-parent/report.json').exists())


class BoundedStdoutTests(unittest.TestCase):
    def test_native_stdout_over_32k_kills_reaps_and_never_prints(self):
        child = mock.MagicMock(); child.__enter__.return_value = child
        child.stdout.fileno.return_value = 123
        selector = mock.MagicMock(); selector.__enter__.return_value = selector
        selector.get_map.return_value = {123: object()}; selector.select.return_value = [object()]
        with mock.patch.object(host.smoke.subprocess, 'Popen', return_value=child) as launch, \
                mock.patch.object(host.smoke.selectors, 'DefaultSelector', return_value=selector), \
                mock.patch.object(host.smoke.os, 'read', return_value=b'x' * 4096) as read, \
                contextlib.redirect_stdout(io.StringIO()) as stdout, \
                contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(host.smoke.SmokeError) as caught:
                host.smoke.bounded_run(['synthetic-command'], {}, 30, protocol.MAX_REPORT_BYTES)
        self.assertEqual(str(caught.exception), 'container_output_limit')
        self.assertEqual(read.call_count, 9)
        child.kill.assert_called_once(); child.wait.assert_called_once()
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')
        self.assertEqual(launch.call_args.kwargs['stderr'], host.smoke.subprocess.DEVNULL)
        self.assertEqual(launch.call_args.kwargs['stdin'], host.smoke.subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
