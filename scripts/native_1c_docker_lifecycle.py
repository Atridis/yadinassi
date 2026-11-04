"""Bounded create/verify/start/remove for one explicitly authorized native image.

Only the deletion-mark entrypoint uses this module. Docker CLI reaping is not
container cleanup, and a lost create response is never evidence of absence.
The Docker daemon is trusted; this is not isolation from an administrator able
to mutate containers. No command discovers or removes containers by name.
"""
from __future__ import annotations

import json
import math
import os
import re
import selectors
import subprocess
import time

OWNER_LABEL = 'org.yadinassi.native.invocation'
CLI_REAP_SECONDS = 2
COMMAND_SECONDS = 30
CLEANUP_SECONDS = 30
MAX_ID_OUTPUT = 65
MAX_INSPECT_OUTPUT = 2048
IMAGE_FORMAT = '[{{json .ID}},{{json .Os}},{{json .Architecture}},{{len .Config.Volumes}}]'
CONTAINER_FORMAT = ('[{{json .Id}},{{json .Name}},{{json .Config.Image}},{{json .Image}},'
                    '{{json (index .Config.Labels "' + OWNER_LABEL + '")}},'
                    '{{json .State.Status}},{{json .State.Running}},{{json .State.Paused}},'
                    '{{json .State.Restarting}},{{json .State.Dead}},{{json .State.ExitCode}}]')
FAILURE_CODES = frozenset({
    'docker_lifecycle_invalid', 'docker_command_timeout', 'docker_command_unavailable',
    'docker_command_failed', 'docker_output_limit', 'docker_cli_reap_unverified',
    'docker_command_interrupted', 'unexpected_image_platform_or_volumes',
    'container_create_invalid', 'container_ownership_unverified',
    'container_not_created', 'container_exit_unverified', 'container_cleanup_unverified',
})


class CliError(Exception):
    """Fixed code plus direct-child reap status, never daemon/container evidence."""
    def __init__(self, code, *, cli_reap_verified=True):
        super().__init__(code)
        self.cli_reap_verified = cli_reap_verified


class LifecycleError(Exception):
    """No native bytes are returned when either cleanup boundary is uncertain."""
    def __init__(self, code, *, cli_reap_verified, container_cleanup_verified):
        super().__init__(code if code in FAILURE_CODES else 'docker_command_failed')
        self.cli_reap_verified = cli_reap_verified
        self.container_cleanup_verified = container_cleanup_verified
        self.cleanup_error = None if container_cleanup_verified else 'container_cleanup_unverified'


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CliError('docker_command_timeout')
    return remaining


def _reap_cli(process, deadline):
    """Kill/reap only our direct child, without a new grace period or group claim."""
    try:
        if process.poll() is not None:
            return True
        try:
            process.kill()
        except OSError:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return process.poll() is not None
        process.wait(timeout=remaining)
        return True
    except BaseException:
        # Even an interruption while reaping is uncertainty, not a successful reap.
        return False


def bounded_cli(command, env, *, deadline, limit):
    """Bound explicit I/O/wait/reap after Popen returns to the shared deadline.

    OS process creation itself cannot be bounded here. Do not use a Popen context
    manager or subprocess.run, which can add an unbounded exit/error wait. stderr
    is discarded and stdout never reaches diagnostics. A missing process handle
    after attempted spawn is unknown ownership/reap, not proof of no CLI child.
    """
    if (os.name != 'posix' or type(limit) is not int or not 0 < limit <= 3_145_728
            or type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise CliError('docker_lifecycle_invalid')
    io_deadline = deadline - CLI_REAP_SECONDS
    _remaining(io_deadline)  # Do not launch a command without its reap reserve.
    process = None
    output = bytearray()
    failure = None
    code = None
    try:
        process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                for key, _ in selector.select(min(_remaining(io_deadline), 0.1)):
                    try:
                        chunk = os.read(key.fileobj.fileno(), min(4096, limit + 1 - len(output)))
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        output.extend(chunk)
                        if len(output) > limit:
                            raise CliError('docker_output_limit')
            code = process.wait(timeout=_remaining(io_deadline))
    except subprocess.TimeoutExpired:
        failure = CliError('docker_command_timeout')
    except OSError:
        failure = CliError('docker_command_unavailable')
    except CliError as error:
        failure = error
    except BaseException as error:
        failure = CliError('docker_command_interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit))
                           else 'docker_command_failed')
    finally:
        # Popen may spawn a child and be interrupted before returning its handle.
        # Without that handle no direct-child reap can be verified, even if the
        # caller's create response is missing and the container is never started.
        reaped = process is not None and _reap_cli(process, deadline)
        if process is not None and process.stdout is not None:
            try:
                process.stdout.close()  # Closing a read pipe never waits for the CLI.
            except BaseException as error:
                if failure is None:
                    failure = CliError('docker_command_interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit))
                                       else 'docker_command_unavailable')
    if failure is None and not reaped:
        failure = CliError('docker_cli_reap_unverified')
    if failure is not None:
        # Reap and pipe-close failures must not erase the primary fixed reason.
        failure.cli_reap_verified = failure.cli_reap_verified and reaped
        raise failure from None
    return code, bytes(output)


def _full_id(raw):
    if type(raw) is not bytes or re.fullmatch(rb'[0-9a-f]{64}\n?', raw) is None:
        raise CliError('container_create_invalid')
    return raw.decode('ascii').removesuffix('\n')


def _json_array(raw, length, code):
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_INSPECT_OUTPUT:
            raise ValueError
        result = json.loads(raw)
        if type(result) is not list or len(result) != length:
            raise ValueError
        return result
    except (ValueError, UnicodeError):
        raise CliError(code) from None


def _owned_snapshot(raw, container_id, name, nonce, image, image_id):
    data = _json_array(raw, 11, 'container_ownership_unverified')
    if (data[:5] != [container_id, '/' + name, image, image_id, nonce]
            or not all(type(value) is str for value in data[:6])
            or data[5] not in ('created', 'running', 'paused', 'restarting', 'removing', 'exited', 'dead')
            or not all(type(value) is bool for value in data[6:10])
            or type(data[10]) is not int or not 0 <= data[10] <= 255):
        raise CliError('container_ownership_unverified')
    return data


def run_owned(create_command, env, *, name, nonce, image, seconds, output_limit,
              state=None, runner=None):
    """Return attached output only after verified removal of the one owned ID.

    A completed create response and pre-start inspection must establish ownership.
    Any uncertain create leaves cleanup_unverified, even if a later listing might
    be empty: the daemon can complete create after the CLI has died. Never retry,
    discover by name, start, or remove an unverified container in that case.
    """
    runner = bounded_cli if runner is None else runner
    state = {} if state is None else state
    if (type(nonce) is not str or re.fullmatch('[0-9a-f]{32}', nonce) is None
            or type(name) is not str or re.fullmatch('onec-[a-z-]+-' + nonce, name) is None
            or type(image) is not str or re.fullmatch('[a-z0-9./_-]+@sha256:[0-9a-f]{64}', image) is None
            or type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not CLEANUP_SECONDS + CLI_REAP_SECONDS < seconds <= 2400
            or type(output_limit) is not int or not 0 < output_limit <= 3_145_728
            or type(create_command) is not list or create_command[:2] != ['docker', 'create']
            or not all(type(arg) is str for arg in create_command)):
        raise LifecycleError('docker_lifecycle_invalid', cli_reap_verified=True,
                             container_cleanup_verified=True)
    # The caller owns the fixed isolation policy; reject conflicting identity flags.
    if create_command.count(image) != 1:
        raise LifecycleError('docker_lifecycle_invalid', cli_reap_verified=True,
                             container_cleanup_verified=True)
    options = create_command[2:create_command.index(image)]
    if any(arg == '-l' or arg.startswith(('--name=', '--label=', '--label-file')) for arg in options):
        raise LifecycleError('docker_lifecycle_invalid', cli_reap_verified=True,
                             container_cleanup_verified=True)
    required = {'--name': name, '--label': OWNER_LABEL + '=' + nonce}
    for flag, value in required.items():
        if (options.count(flag) != 1 or options[-1] == flag
                or options[options.index(flag) + 1] != value):
            raise LifecycleError('docker_lifecycle_invalid', cli_reap_verified=True,
                                 container_cleanup_verified=True)
    deadline = time.monotonic() + seconds
    work_deadline = deadline - CLEANUP_SECONDS
    owned_id = None
    cleanup_verified = True
    cli_reaped = True
    failure = None
    failure_stage = None
    result = None

    def call(command, limit, end, *, short=True):
        nonlocal cli_reaped
        _remaining(end)
        selected = min(end, time.monotonic() + COMMAND_SECONDS) if short else end
        try:
            return runner(command, env, deadline=selected, limit=limit)
        except CliError as error:
            cli_reaped = cli_reaped and error.cli_reap_verified
            raise

    def inspect(container_id, end):
        code, raw = call(['docker', 'container', 'inspect', '--format', CONTAINER_FORMAT, container_id],
                         MAX_INSPECT_OUTPUT, end)
        if code != 0:
            raise CliError('container_ownership_unverified')
        return _owned_snapshot(raw, container_id, name, nonce, image, image_id)

    try:
        state['stage'] = 'image_inspect'
        code, raw = call(['docker', 'image', 'inspect', '--format', IMAGE_FORMAT, image],
                         MAX_INSPECT_OUTPUT, work_deadline)
        data = _json_array(raw, 4, 'unexpected_image_platform_or_volumes')
        if (code != 0 or type(data[0]) is not str or re.fullmatch('sha256:[0-9a-f]{64}', data[0]) is None
                or data[1:] != ['linux', 'amd64', 0] or type(data[3]) is not int):
            raise CliError('unexpected_image_platform_or_volumes')
        image_id = data[0]
        state['stage'] = 'container_create'
        cleanup_verified = False  # Set before sending the request, not after response.
        code, raw = call(create_command, MAX_ID_OUTPUT, work_deadline)
        if code != 0:
            raise CliError('docker_command_failed')
        candidate = _full_id(raw)
        state['stage'] = 'container_ownership'
        snapshot = inspect(candidate, work_deadline)
        if snapshot[5:] != ['created', False, False, False, False, 0]:
            raise CliError('container_not_created')
        owned_id = candidate
        state['stage'] = 'container_start'
        attached_code, output = call(['docker', 'start', '--attach', owned_id],
                                     output_limit, work_deadline, short=False)
        state['stage'] = 'container_exit'
        snapshot = inspect(owned_id, work_deadline)
        if (snapshot[5:10] != ['exited', False, False, False, False]
                or type(attached_code) is not int or attached_code != snapshot[10]):
            raise CliError('container_exit_unverified')
        result = attached_code, output
    except BaseException as error:
        failure = error
        failure_stage = state['stage']
    finally:
        if owned_id is not None:
            prior = state['stage']
            state['stage'] = 'container_cleanup'
            try:
                # Recheck the exact owned ID, never resolve the possibly reused name.
                inspect(owned_id, deadline)
                code, removed = call(['docker', 'rm', '--force', owned_id], MAX_ID_OUTPUT, deadline)
                if code != 0 or _full_id(removed) != owned_id:
                    raise CliError('container_cleanup_unverified')
                code, remaining = call(['docker', 'ps', '--all', '--no-trunc', '--filter',
                                        'id=' + owned_id, '--format', '{{.ID}}'], MAX_ID_OUTPUT, deadline)
                if code != 0 or remaining not in (b'', b'\n'):
                    raise CliError('container_cleanup_unverified')
                cleanup_verified = True
                state['stage'] = prior
            except BaseException as error:
                if failure is None:
                    failure = error
                    failure_stage = 'container_cleanup'
            finally:
                if failure_stage is not None:
                    state['stage'] = failure_stage
    if failure is not None or not cleanup_verified or not cli_reaped:
        code = str(failure) if isinstance(failure, CliError) else 'docker_command_interrupted'
        if not cleanup_verified and failure is None:
            code = 'container_cleanup_unverified'
        raise LifecycleError(code, cli_reap_verified=cli_reaped,
                             container_cleanup_verified=cleanup_verified) from None
    return result
