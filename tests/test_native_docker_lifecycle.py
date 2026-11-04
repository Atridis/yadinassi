"""Fake Docker/CLI only: no subprocess, daemon, native observation or sleep."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_docker_lifecycle as lifecycle

NONCE = 'a' * 32
NAME = 'onec-catalog-object-' + NONCE
IMAGE = 'ghcr.io/atridis/onec-ubuntu22@sha256:' + 'b' * 64
IMAGE_ID = 'sha256:' + 'c' * 64
ID = 'd' * 64
COMMAND = ['docker', 'create', '--name', NAME, '--label', lifecycle.OWNER_LABEL + '=' + NONCE,
           '--network', 'none', IMAGE, '/bin/false']


def encoded(value):
    return json.dumps(value).encode()


class FakeDocker:
    def __init__(self):
        self.calls = []
        self.image = [IMAGE_ID, 'linux', 'amd64', 0]
        self.snapshot = [ID, '/' + NAME, IMAGE, IMAGE_ID, NONCE,
                         'created', False, False, False, False, 0]
        self.overrides = {}
        self.started = False
        self.inspections = 0

    def __call__(self, command, env, *, deadline, limit):
        operation = ('inspect' if command[:3] == ['docker', 'container', 'inspect']
                     else 'image' if command[:3] == ['docker', 'image', 'inspect'] else command[1])
        self.calls.append((operation, command, deadline, limit))
        if operation in self.overrides:
            value = self.overrides[operation]
            if callable(value): return value(command)
            if isinstance(value, BaseException): raise value
            return value
        if operation == 'image': return 0, encoded(self.image)
        if operation == 'create': return 0, (ID + '\n').encode()
        if operation == 'inspect':
            self.inspections += 1
            snapshot = copy.copy(self.snapshot)
            if self.started: snapshot[5] = 'exited'
            return 0, encoded(snapshot)
        if operation == 'start':
            self.started = True
            return 0, b'owned output'
        if operation == 'rm': return 0, (ID + '\n').encode()
        if operation == 'ps': return 0, b''
        raise AssertionError('Unexpected fake operation')


class OwnedLifecycleTests(unittest.TestCase):
    def invoke(self, fake, **kwargs):
        options = dict(name=NAME, nonce=NONCE, image=IMAGE, seconds=120, output_limit=1024, runner=fake)
        options.update(kwargs)
        return lifecycle.run_owned(COMMAND, {}, **options)

    def failure(self, fake, code=None, **kwargs):
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            self.invoke(fake, **kwargs)
        if code: self.assertEqual(str(caught.exception), code)
        return caught.exception

    def test_create_inspect_start_exit_remove_order(self):
        fake = FakeDocker()
        self.assertEqual(self.invoke(fake), (0, b'owned output'))
        self.assertEqual([call[0] for call in fake.calls],
                         ['image', 'create', 'inspect', 'start', 'inspect', 'inspect', 'rm', 'ps'])
        self.assertEqual(fake.calls[3][1], ['docker', 'start', '--attach', ID])
        self.assertEqual(fake.calls[-2][1], ['docker', 'rm', '--force', ID])
        self.assertEqual(fake.calls[-1][1], ['docker', 'ps', '--all', '--no-trunc', '--filter',
                                            'id=' + ID, '--format', '{{.ID}}'])
        self.assertTrue(all(NAME not in call[1] for call in fake.calls if call[0] != 'create'))

    def test_name_is_bound_to_invocation_nonce(self):
        for kwargs in ({'name': NAME + 'x'}, {'nonce': 'e' * 32}, {'name': 'other-' + NONCE}):
            fake = FakeDocker()
            error = self.failure(fake, 'docker_lifecycle_invalid', **kwargs)
            self.assertEqual(fake.calls, [])
            self.assertTrue(error.container_cleanup_verified)

    def test_identity_options_are_exact_and_not_aliased(self):
        for suffix in (['--name', 'alien'], ['--name=alien'], ['-l', 'alien=value'],
                       ['--label=x=y'], ['--label-file', '/unexpected']):
            command = COMMAND[:-2] + suffix + COMMAND[-2:]
            with mock.patch.object(lifecycle, 'bounded_cli') as runner:
                with self.assertRaises(lifecycle.LifecycleError):
                    lifecycle.run_owned(command, {}, name=NAME, nonce=NONCE, image=IMAGE,
                                        seconds=120, output_limit=1024)
                runner.assert_not_called()

    def test_invalid_budgets_and_unpinned_image_are_preflight_failures(self):
        for kwargs in ({'seconds': True}, {'seconds': float('nan')}, {'seconds': 32},
                       {'seconds': 2401}, {'output_limit': True}, {'output_limit': 0},
                       {'image': 'image:latest'}):
            fake = FakeDocker()
            self.failure(fake, 'docker_lifecycle_invalid', **kwargs)
            self.assertEqual(fake.calls, [])

    def test_image_identity_platform_and_volumes_are_required(self):
        for index, replacement in ((0, 'c' * 64), (1, 'windows'), (2, 'arm64'), (3, 1), (3, False)):
            fake = FakeDocker(); fake.image[index] = replacement
            error = self.failure(fake, 'unexpected_image_platform_or_volumes')
            self.assertTrue(error.container_cleanup_verified)
            self.assertEqual([call[0] for call in fake.calls], ['image'])

    def test_create_requires_exact_full_id(self):
        for raw in (b'', ID[:12].encode(), (ID + ' extra').encode(), (ID + '\r\n').encode(),
                    ('E' * 64).encode(), (ID + '\n' + ID).encode()):
            fake = FakeDocker(); fake.overrides['create'] = 0, raw
            error = self.failure(fake, 'container_create_invalid')
            self.assertFalse(error.container_cleanup_verified)
            self.assertEqual([call[0] for call in fake.calls], ['image', 'create'])

    def test_failed_create_with_valid_id_does_not_start_or_remove(self):
        fake = FakeDocker(); fake.overrides['create'] = 1, ID.encode()
        error = self.failure(fake, 'docker_command_failed')
        self.assertFalse(error.container_cleanup_verified)
        self.assertFalse(fake.started)
        self.assertEqual(len(fake.calls), 2)

    def test_lost_create_response_never_uses_empty_ps_as_proof(self):
        for code in ('docker_command_timeout', 'docker_command_unavailable', 'docker_output_limit'):
            fake = FakeDocker(); fake.overrides['create'] = lifecycle.CliError(code)
            fake.overrides['ps'] = 0, b''
            error = self.failure(fake, code)
            self.assertEqual(error.cleanup_error, 'container_cleanup_unverified')
            self.assertTrue(error.cli_reap_verified)
            self.assertEqual([call[0] for call in fake.calls], ['image', 'create'])

    def test_unreaped_create_cli_does_not_prove_container_cleanup(self):
        fake = FakeDocker()
        fake.overrides['create'] = lifecycle.CliError('docker_cli_reap_unverified', cli_reap_verified=False)
        error = self.failure(fake, 'docker_cli_reap_unverified')
        self.assertFalse(error.cli_reap_verified)
        self.assertFalse(error.container_cleanup_verified)
        self.assertFalse(fake.started)

    def test_all_five_ownership_fields_must_match(self):
        for index in range(5):
            fake = FakeDocker(); fake.snapshot[index] = 'alien'
            error = self.failure(fake, 'container_ownership_unverified')
            self.assertFalse(error.container_cleanup_verified)
            self.assertEqual([call[0] for call in fake.calls], ['image', 'create', 'inspect'])

    def test_inspect_framing_is_closed(self):
        for value in (b'{}', b'null', b'[]', b'\xff', b'x' * 2049,
                      encoded([*FakeDocker().snapshot, 'extra'])):
            fake = FakeDocker(); fake.overrides['inspect'] = 0, value
            self.failure(fake, 'container_ownership_unverified')
            self.assertFalse(fake.started)
            self.assertFalse(any(call[0] == 'rm' for call in fake.calls))

    def test_created_state_and_exact_types_are_required_before_start(self):
        for index, replacement in ((5, 'running'), (6, True), (7, True), (8, True), (9, True),
                                   (10, 1), (6, 0), (10, False)):
            fake = FakeDocker(); fake.snapshot[index] = replacement
            error = self.failure(fake)
            self.assertFalse(error.container_cleanup_verified)
            self.assertFalse(fake.started)
            self.assertFalse(any(call[0] == 'rm' for call in fake.calls))

    def test_inspect_timeout_never_starts_or_deletes_unverified_id(self):
        fake = FakeDocker(); fake.overrides['inspect'] = lifecycle.CliError('docker_command_timeout')
        error = self.failure(fake, 'docker_command_timeout')
        self.assertFalse(error.container_cleanup_verified)
        self.assertEqual([call[0] for call in fake.calls], ['image', 'create', 'inspect'])

    def test_start_timeout_still_removes_only_verified_owned_id(self):
        fake = FakeDocker(); fake.overrides['start'] = lifecycle.CliError('docker_command_timeout')
        error = self.failure(fake, 'docker_command_timeout')
        self.assertTrue(error.container_cleanup_verified)
        self.assertIsNone(error.cleanup_error)
        self.assertEqual(fake.calls[-2][1], ['docker', 'rm', '--force', ID])

    def test_cli_reap_and_container_cleanup_are_independent(self):
        fake = FakeDocker()
        fake.overrides['start'] = lifecycle.CliError('docker_cli_reap_unverified', cli_reap_verified=False)
        error = self.failure(fake, 'docker_cli_reap_unverified')
        self.assertFalse(error.cli_reap_verified)
        self.assertTrue(error.container_cleanup_verified)

    def test_interruption_attempts_bounded_owned_cleanup(self):
        fake = FakeDocker(); fake.overrides['start'] = KeyboardInterrupt()
        error = self.failure(fake, 'docker_command_interrupted')
        self.assertTrue(error.container_cleanup_verified)

    def test_attached_exit_requires_matching_exited_snapshot(self):
        for attached_code, final_state in ((7, 'exited'), (0, 'running'), (True, 'exited')):
            fake = FakeDocker()
            fake.overrides['start'] = attached_code, b'private output'
            def inspect(command):
                fake.inspections += 1
                snapshot = copy.copy(fake.snapshot)
                if fake.inspections > 1: snapshot[5] = final_state
                return 0, encoded(snapshot)
            fake.overrides['inspect'] = inspect
            error = self.failure(fake, 'container_exit_unverified')
            self.assertTrue(error.container_cleanup_verified)
            self.assertNotIn('private', str(error))

    def test_nonzero_native_exit_is_returned_after_cleanup(self):
        fake = FakeDocker()
        def start(command):
            fake.started = True; fake.snapshot[10] = 7
            return 7, b'validated later'
        fake.overrides['start'] = start
        self.assertEqual(self.invoke(fake), (7, b'validated later'))

    def test_cleanup_rechecks_identity_and_never_falls_back_to_name(self):
        fake = FakeDocker()
        def inspect(command):
            fake.inspections += 1
            snapshot = copy.copy(fake.snapshot)
            if fake.inspections >= 2: snapshot[5] = 'exited'
            if fake.inspections == 3: snapshot[1] = '/replacement'
            return 0, encoded(snapshot)
        fake.overrides['inspect'] = inspect
        error = self.failure(fake, 'container_ownership_unverified')
        self.assertFalse(error.container_cleanup_verified)
        self.assertFalse(any(call[0] in ('rm', 'ps') for call in fake.calls))

    def test_remove_requires_completed_exact_id_acknowledgment(self):
        for result in ((1, ID.encode()), (0, b''), (0, ID[:12].encode()),
                       (0, ('e' * 64).encode()), lifecycle.CliError('docker_command_timeout')):
            fake = FakeDocker(); fake.overrides['rm'] = result
            error = self.failure(fake)
            self.assertFalse(error.container_cleanup_verified)
            self.assertFalse(any(call[0] == 'ps' for call in fake.calls))

    def test_confirmed_removal_requires_successful_empty_full_id_listing(self):
        for result in ((1, b''), (0, ID.encode()), (0, b' '), lifecycle.CliError('docker_command_timeout')):
            fake = FakeDocker(); fake.overrides['ps'] = result
            error = self.failure(fake)
            self.assertFalse(error.container_cleanup_verified)

    def test_primary_failure_survives_unverified_cleanup(self):
        fake = FakeDocker()
        fake.overrides['start'] = lifecycle.CliError('docker_output_limit')
        fake.overrides['rm'] = lifecycle.CliError('docker_command_timeout')
        error = self.failure(fake, 'docker_output_limit')
        self.assertEqual(error.cleanup_error, 'container_cleanup_unverified')

    def test_primary_stage_survives_cleanup_failure(self):
        for code in ('docker_command_timeout', 'docker_output_limit', 'docker_command_interrupted'):
            fake = FakeDocker(); state = {}
            fake.overrides['start'] = lifecycle.CliError(code, cli_reap_verified=False)
            fake.overrides['rm'] = lifecycle.CliError('docker_command_timeout')
            error = self.failure(fake, code, state=state)
            self.assertEqual(state['stage'], 'container_start')
            self.assertFalse(error.cli_reap_verified)
            self.assertEqual(error.cleanup_error, 'container_cleanup_unverified')
        fake = FakeDocker(); state = {}
        fake.overrides['rm'] = lifecycle.CliError('docker_command_timeout')
        self.failure(fake, 'docker_command_timeout', state=state)
        self.assertEqual(state['stage'], 'container_cleanup')

    def test_interrupted_create_without_cli_handle_is_never_verified(self):
        fake = FakeDocker(); state = {}
        fake.overrides['create'] = lifecycle.CliError('docker_command_interrupted', cli_reap_verified=False)
        error = self.failure(fake, 'docker_command_interrupted', state=state)
        self.assertEqual(state['stage'], 'container_create')
        self.assertFalse(error.cli_reap_verified)
        self.assertFalse(error.container_cleanup_verified)
        self.assertEqual([call[0] for call in fake.calls], ['image', 'create'])

    def test_one_deadline_includes_inspect_attach_and_cleanup(self):
        fake = FakeDocker(); now = [100.0]
        def runner(*args, **kwargs):
            result = fake(*args, **kwargs)
            now[0] += 1
            return result
        with mock.patch.object(lifecycle.time, 'monotonic', side_effect=lambda: now[0]):
            self.invoke(runner)
        self.assertEqual(fake.calls[3][2], 190.0)
        self.assertTrue(all(call[2] <= 190.0 for call in fake.calls[:5]))
        self.assertTrue(all(call[2] <= 220.0 for call in fake.calls[5:]))

    def test_expired_work_budget_leaves_cleanup_reserve_without_start(self):
        fake = FakeDocker(); now = [100.0]
        def runner(*args, **kwargs):
            result = fake(*args, **kwargs)
            if fake.calls[-1][0] == 'inspect': now[0] = 190.0
            return result
        with mock.patch.object(lifecycle.time, 'monotonic', side_effect=lambda: now[0]):
            error = self.failure(runner, 'docker_command_timeout')
        self.assertTrue(error.container_cleanup_verified)
        self.assertFalse(fake.started)

    def test_expired_cleanup_budget_never_starts_a_new_command(self):
        fake = FakeDocker(); now = [100.0]
        def runner(*args, **kwargs):
            result = fake(*args, **kwargs)
            if fake.calls[-1][0] == 'start': now[0] = 220.0
            return result
        with mock.patch.object(lifecycle.time, 'monotonic', side_effect=lambda: now[0]):
            error = self.failure(runner, 'docker_command_timeout')
        self.assertFalse(error.container_cleanup_verified)
        self.assertEqual(fake.calls[-1][0], 'start')


class ImageInspectTests(unittest.TestCase):
    """Check the exact CLI template and admission, not execution of Go templates.

    A typed nil or empty Volumes map is projected by Go len as integer zero.
    FakeDocker supplies that projection; a real Docker check remains separate.
    """
    CANARY = 'private-image-inspect-payload'

    def invoke(self, fake, state):
        with mock.patch.object(lifecycle, 'bounded_cli', side_effect=AssertionError('real CLI forbidden')), \
             mock.patch.object(lifecycle.subprocess, 'Popen', side_effect=AssertionError('process forbidden')):
            return lifecycle.run_owned(COMMAND, {}, name=NAME, nonce=NONCE, image=IMAGE,
                                       seconds=120, output_limit=1024, state=state, runner=fake)

    def refuse(self, response, expected='unexpected_image_platform_or_volumes', *, reaped=True):
        fake = FakeDocker(); state = {}
        fake.overrides['image'] = response
        with self.assertRaises(lifecycle.LifecycleError) as caught:
            self.invoke(fake, state)
        error = caught.exception
        self.assertEqual(error.args, (expected,))
        self.assertIs(error.cli_reap_verified, reaped)
        self.assertIs(error.container_cleanup_verified, True)
        self.assertIsNone(error.cleanup_error)
        self.assertEqual(state, {'stage': 'image_inspect'})
        self.assertEqual([call[0] for call in fake.calls], ['image'])
        self.assertFalse(fake.started)
        self.assertNotIn(self.CANARY, repr(error.args) + repr(vars(error)) + repr(state))

    def test_literal_template_uses_typed_id_without_fallback(self):
        expected = '[{{json .ID}},{{json .Os}},{{json .Architecture}},{{len .Config.Volumes}}]'
        self.assertEqual(lifecycle.IMAGE_FORMAT, expected)
        fake = FakeDocker()
        self.invoke(fake, {})
        self.assertEqual(fake.calls[0][1], ['docker', 'image', 'inspect', '--format', expected, IMAGE])
        self.assertEqual(fake.calls[0][3], lifecycle.MAX_INSPECT_OUTPUT)

    def test_zero_volume_projection_admits_linux_amd64(self):
        fake = FakeDocker()
        fake.overrides['image'] = 0, encoded([IMAGE_ID, 'linux', 'amd64', 0])
        self.assertEqual(self.invoke(fake, {}), (0, b'owned output'))
        self.assertEqual([call[0] for call in fake.calls],
                         ['image', 'create', 'inspect', 'start', 'inspect', 'inspect', 'rm', 'ps'])

    def test_nonzero_volume_projection_refuses_before_create(self):
        for count in (1, 2, 2048, -1):
            with self.subTest(count=count):
                self.refuse((0, encoded([IMAGE_ID, 'linux', 'amd64', count])))

    def test_volume_projection_requires_exact_integer_zero(self):
        for value in (False, True, 0.0, '0', None, [], {}):
            with self.subTest(value=value):
                self.refuse((0, encoded([IMAGE_ID, 'linux', 'amd64', value])))

    def test_image_identity_requires_full_lowercase_sha256(self):
        for value in (None, 42, 'c' * 64, 'sha256:' + 'c' * 63, 'sha256:' + 'C' * 64,
                      IMAGE_ID + '\n', self.CANARY):
            with self.subTest(value=value):
                self.refuse((0, encoded([value, 'linux', 'amd64', 0])))

    def test_os_and_architecture_are_exact(self):
        for os_name, architecture in (('windows', 'amd64'), ('linux', 'arm64'),
                                      ('Linux', 'amd64'), ('linux', 'AMD64'),
                                      (False, 'amd64'), ('linux', None)):
            with self.subTest(os_name=os_name, architecture=architecture):
                self.refuse((0, encoded([IMAGE_ID, os_name, architecture, 0])))

    def test_malformed_image_projection_refuses_before_create(self):
        malformed = (b'', b'\n', b'\xff', b'[', b'{}', b'null', b'[]',
                     encoded([IMAGE_ID, 'linux', 'amd64']),
                     encoded([IMAGE_ID, 'linux', 'amd64', 0, self.CANARY]),
                     b'x' * (lifecycle.MAX_INSPECT_OUTPUT + 1), self.CANARY)
        for raw in malformed:
            with self.subTest(kind=type(raw).__name__, size=len(raw)):
                self.refuse((0, raw))

    def test_inspect_nonzero_exit_rejects_even_valid_projection(self):
        for code in (1, 64, 125):
            with self.subTest(code=code):
                self.refuse((code, encoded([IMAGE_ID, 'linux', 'amd64', 0])))

    def test_template_or_lookup_failure_never_retries_or_creates(self):
        # Template failure, nil Config, raw-only response or missing image can
        # fail the CLI before a projection exists. None grants create authority.
        for raw in (b'', b'\n', self.CANARY.encode()):
            with self.subTest(size=len(raw)):
                self.refuse((1, raw))

    def test_inspect_cli_error_preserves_reap_and_safe_reason(self):
        for code in ('docker_command_timeout', 'docker_command_unavailable',
                     'docker_output_limit', 'docker_cli_reap_unverified'):
            for reaped in (False, True):
                with self.subTest(code=code, reaped=reaped):
                    self.refuse(lifecycle.CliError(code, cli_reap_verified=reaped), code, reaped=reaped)
        self.refuse(lifecycle.CliError(self.CANARY), 'docker_command_failed')


class FakeProcess:
    def __init__(self, *, unreapable=False):
        self.stdout = mock.Mock()
        self.stdout.fileno.return_value = 42
        self.returncode = None
        self.waits = []
        self.killed = False
        self.unreapable = unreapable

    def poll(self): return self.returncode
    def kill(self): self.killed = True
    def wait(self, *, timeout):
        self.waits.append(timeout)
        if self.unreapable: raise subprocess.TimeoutExpired('fake', timeout)
        self.returncode = 0
        return 0


class FakeSelector:
    def __init__(self): self.stream = None
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def register(self, stream, events): self.stream = stream
    def unregister(self, stream): self.stream = None
    def get_map(self): return {42: self.stream} if self.stream else {}
    def select(self, timeout): return [(types.SimpleNamespace(fileobj=self.stream), 1)]


class BoundedCliTests(unittest.TestCase):
    def invoke(self, chunks, process=None, *, deadline=10, limit=32, clock=lambda: 0):
        process = FakeProcess() if process is None else process
        with mock.patch.object(lifecycle.os, 'name', 'posix'), \
             mock.patch.object(lifecycle.subprocess, 'Popen', return_value=process) as launch, \
             mock.patch.object(lifecycle.selectors, 'DefaultSelector', FakeSelector), \
             mock.patch.object(lifecycle.os, 'set_blocking', create=True), \
             mock.patch.object(lifecycle.os, 'read', side_effect=chunks), \
             mock.patch.object(lifecycle.time, 'monotonic', side_effect=clock):
            result = lifecycle.bounded_cli(['docker', 'fake'], {}, deadline=deadline, limit=limit)
        self.assertEqual(launch.call_args.kwargs['stderr'], subprocess.DEVNULL)
        self.assertNotIn('shell', launch.call_args.kwargs)
        return result, process

    def test_success_reaps_and_closes_without_popen_context_manager(self):
        result, process = self.invoke([b'owned', b''])
        self.assertEqual(result, (0, b'owned'))
        self.assertEqual(process.waits, [8])
        process.stdout.close.assert_called_once()
        self.assertFalse(process.killed)

    def test_output_overflow_kills_and_reaps_within_original_deadline(self):
        process = FakeProcess()
        with self.assertRaisesRegex(lifecycle.CliError, '^docker_output_limit$'):
            self.invoke([b'x' * 33], process)
        self.assertTrue(process.killed)
        self.assertEqual(process.waits, [10])
        process.stdout.close.assert_called_once()

    def test_timeout_after_eof_uses_bounded_reap(self):
        process = FakeProcess(unreapable=True)
        with self.assertRaises(lifecycle.CliError) as caught:
            self.invoke([b''], process)
        self.assertEqual(str(caught.exception), 'docker_command_timeout')
        self.assertFalse(caught.exception.cli_reap_verified)
        self.assertEqual(process.waits, [8, 10])
        self.assertTrue(process.killed)
        process.stdout.close.assert_called_once()

    def test_no_reap_reserve_means_no_process_launch(self):
        with mock.patch.object(lifecycle.os, 'name', 'posix'), \
             mock.patch.object(lifecycle.time, 'monotonic', return_value=9), \
             mock.patch.object(lifecycle.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(lifecycle.CliError, 'docker_command_timeout'):
                lifecycle.bounded_cli(['docker', 'fake'], {}, deadline=10, limit=32)
        launch.assert_not_called()

    def test_read_failure_reaps_without_exposing_exception_text(self):
        process = FakeProcess()
        with self.assertRaisesRegex(lifecycle.CliError, '^docker_command_unavailable$'):
            self.invoke([OSError('private failure')], process)
        self.assertTrue(process.killed)
        process.stdout.close.assert_called_once()

    def test_interrupt_still_reaps_before_propagating(self):
        process = FakeProcess()
        with self.assertRaisesRegex(lifecycle.CliError, '^docker_command_interrupted$'):
            self.invoke([KeyboardInterrupt()], process)
        self.assertTrue(process.killed)
        self.assertEqual(process.waits, [10])

    def test_deadline_is_not_extended_for_cli_reap(self):
        process = FakeProcess()
        clock = iter([0, 0, 11, 11])
        with self.assertRaises(lifecycle.CliError) as caught:
            self.invoke([b''], process, clock=lambda: next(clock))
        self.assertEqual(str(caught.exception), 'docker_command_timeout')
        self.assertFalse(caught.exception.cli_reap_verified)
        self.assertEqual(process.waits, [])
        self.assertTrue(process.killed)

    def test_spawn_without_returned_handle_never_claims_verified_reap(self):
        for failure, expected in ((KeyboardInterrupt(), 'docker_command_interrupted'),
                                  (SystemExit('private'), 'docker_command_interrupted'),
                                  (OSError('private'), 'docker_command_unavailable')):
            with self.subTest(expected=expected), \
                 mock.patch.object(lifecycle.os, 'name', 'posix'), \
                 mock.patch.object(lifecycle.time, 'monotonic', return_value=0), \
                 mock.patch.object(lifecycle.subprocess, 'Popen', side_effect=failure), \
                 mock.patch.object(lifecycle, '_reap_cli') as reap:
                with self.assertRaises(lifecycle.CliError) as caught:
                    lifecycle.bounded_cli(['docker', 'fake'], {}, deadline=10, limit=32)
                self.assertEqual(str(caught.exception), expected)
                self.assertFalse(caught.exception.cli_reap_verified)
                reap.assert_not_called()

    def test_primary_reason_survives_unreaped_cli_and_pipe_close_failure(self):
        cases = (([b'x' * 33], 'docker_output_limit'),
                 ([lifecycle.CliError('docker_command_timeout')], 'docker_command_timeout'),
                 ([KeyboardInterrupt()], 'docker_command_interrupted'))
        for chunks, expected in cases:
            process = FakeProcess(unreapable=True)
            process.stdout.close.side_effect = OSError('private close failure')
            with self.subTest(expected=expected), self.assertRaises(lifecycle.CliError) as caught:
                self.invoke(chunks, process)
            self.assertEqual(str(caught.exception), expected)
            self.assertFalse(caught.exception.cli_reap_verified)
            self.assertEqual(process.waits, [10])
            process.stdout.close.assert_called_once()

    def test_pipe_close_failure_does_not_replace_primary_after_verified_reap(self):
        cases = (([b'x' * 33], 'docker_output_limit'),
                 ([lifecycle.CliError('docker_command_timeout')], 'docker_command_timeout'),
                 ([KeyboardInterrupt()], 'docker_command_interrupted'))
        for chunks, expected in cases:
            process = FakeProcess()
            process.stdout.close.side_effect = KeyboardInterrupt()
            with self.subTest(expected=expected), self.assertRaises(lifecycle.CliError) as caught:
                self.invoke(chunks, process)
            self.assertEqual(str(caught.exception), expected)
            self.assertTrue(caught.exception.cli_reap_verified)

    def test_pipe_close_only_failure_blocks_output_without_losing_reap_proof(self):
        for failure, expected in ((OSError('private'), 'docker_command_unavailable'),
                                  (KeyboardInterrupt(), 'docker_command_interrupted')):
            process = FakeProcess(); process.stdout.close.side_effect = failure
            with self.subTest(expected=expected), self.assertRaises(lifecycle.CliError) as caught:
                self.invoke([b'private output', b''], process)
            self.assertEqual(str(caught.exception), expected)
            self.assertTrue(caught.exception.cli_reap_verified)

    def test_signal_denial_does_not_prevent_bounded_reap_attempt(self):
        process = FakeProcess()
        process.kill = mock.Mock(side_effect=PermissionError())
        with mock.patch.object(lifecycle.time, 'monotonic', return_value=3):
            self.assertTrue(lifecycle._reap_cli(process, 10))
        self.assertEqual(process.waits, [7])

    def test_interrupted_reap_is_uncertain(self):
        process = FakeProcess()
        process.wait = mock.Mock(side_effect=KeyboardInterrupt())
        with mock.patch.object(lifecycle.time, 'monotonic', return_value=0):
            self.assertFalse(lifecycle._reap_cli(process, 10))


if __name__ == '__main__': unittest.main()
