"""Isolated end-to-end check of the packaged local UI and child runtime."""
import http.client
import json
import os
import re
import secrets
import signal
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import time
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = sys.platform == 'win32'


def _read_launch(capture, process):
    """Poll an owned regular file, never close a pipe behind a blocked reader."""
    deadline = time.monotonic() + 45
    data = b''
    with capture.open('rb') as stream:
        while True:
            data += stream.read(12289 - len(data))
            lines = data.splitlines(keepends=True)
            if len(data) > 12288 or any(len(line) > 4096 for line in lines[:3]):
                raise AssertionError('frozen UI startup output exceeds limit')
            if len(lines) >= 3 and all(line.endswith(b'\n') for line in lines[:3]):
                urls = [line for line in lines[:3] if line.startswith(b'http://127.0.0.1:')]
                if len(urls) != 1:
                    raise AssertionError('frozen UI launch URL missing')
                return urls[0].decode('ascii').strip()
            if process.poll() is not None:
                raise AssertionError('frozen UI exited before launch URL')
            if time.monotonic() >= deadline:
                raise AssertionError('frozen UI launch timed out')
            time.sleep(0.05)


def _stop_owned_tree(process):
    """Bounded failure-only cleanup of the process tree created by this smoke."""
    def group_exists():
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
    if process.poll() is not None:
        # Never signal a possibly reused PID after the original parent was reaped.
        if WINDOWS:
            return False
        try:
            return not group_exists()
        except OSError:
            return False
    deadline = time.monotonic() + 25
    def remaining():
        return min(25, max(0.001, deadline - time.monotonic()))
    verified = True
    try:
        if not WINDOWS:
            # Keep the unreaped parent PID owned through the final group signal.
            # In particular, do not poll/wait between TERM and KILL.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(min(0.2, remaining()))
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=remaining())
            return not group_exists()
        else:
            system_root = PureWindowsPath(os.environ.get('SystemRoot', r'C:\Windows'))
            if not system_root.is_absolute() or len(system_root.drive) != 2:
                raise OSError('invalid system directory')
            killer = system_root / 'System32' / 'taskkill.exe'
            result = subprocess.run([str(killer), '/PID', str(process.pid), '/T', '/F'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=min(10, remaining()), check=False)
            verified = result.returncode == 0
            if not verified and process.poll() is None:
                process.terminate()
        try:
            process.wait(timeout=min(10, remaining()))
        except subprocess.TimeoutExpired:
            verified = False
            process.kill()
            process.wait(timeout=remaining())
    except (OSError, subprocess.TimeoutExpired):
        verified = False
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=remaining())
        except (OSError, subprocess.TimeoutExpired):
            pass
    return verified and process.poll() is not None


def _launch_identity(launch):
    """The unified launcher requires an attachment, never a legacy fallback."""
    try:
        url = urlsplit(launch)
        fragment = parse_qs(url.fragment, strict_parsing=True, keep_blank_values=True)
        valid = (url.scheme == 'http' and url.hostname == '127.0.0.1'
                 and url.username is None and url.password is None and url.port
                 and url.path == '/' and not url.query
                 and set(fragment) == {'session', 'attachment'}
                 and fragment['attachment'] == ['1'] and len(fragment['session']) == 1
                 and re.fullmatch(r'[A-Za-z0-9_-]{43}', fragment['session'][0]))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise AssertionError('invalid local UI launch URL')
    return url.port, fragment['session'][0]


def _writer_headers(request, authority, origin, bootstrap):
    """Join the real writer protocol; the bootstrap is not an RPC credential."""
    base = {'Host': authority, 'Origin': origin, 'Content-Type': 'application/x-ndjson'}
    packet = json.dumps({'action': 'attach', 'instance': secrets.token_hex(16)},
                        separators=(',', ':')).encode() + b'\n'
    value = json.loads(request('POST', '/attachment', packet,
                              dict(base, **{'X-Yadinassi-Session': bootstrap})))
    fields = {'protocol', 'attachment', 'role', 'generation', 'leaseSeconds',
              'graceSeconds', 'recovery', 'closed', 'credential', 'resume'}
    if (type(value) is not dict or set(value) != fields
            or value['protocol'] != 'yadinassi-browser-attachment/1'
            or value['role'] != 'writer' or value['closed'] is not False
            or value['recovery'] is not False
            or type(value['generation']) is not int or not 1 <= value['generation'] <= 2**53 - 1
            or type(value['leaseSeconds']) is not int or not 10 <= value['leaseSeconds'] <= 3600
            or type(value['graceSeconds']) is not int or not 1 <= value['graceSeconds'] <= 3600
            or type(value['attachment']) is not str
            or not re.fullmatch(r'attachment-[1-9][0-9]{0,15}', value['attachment'])
            or any(type(value[name]) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}', value[name])
                   for name in ('credential', 'resume'))
            or len({bootstrap, value['credential'], value['resume']}) != 3):
        raise AssertionError('frozen UI attachment not admitted as writer')
    return dict(base, **{'X-Yadinassi-Session': value['credential'],
                        'X-Yadinassi-Attachment': value['attachment'],
                        'X-Yadinassi-Generation': str(value['generation'])})


def check_ui(executable, directory, env):
    # This fixture is used by the build host, never by the frozen application.
    sys.path.insert(0, str(ROOT / 'tests'))
    from browser_ui.fixture import seed
    from ui_catalog_fixture import CATEGORY
    from yadinassi.catalog_backend import CatalogSelection
    from yadinassi.sqlite_catalog import SQLiteCatalogBackend

    directory = Path(directory) / 'ui smoke база'
    directory.mkdir(parents=True)
    seed(directory)
    database = directory / 'owned.sqlite'
    # Contains an ephemeral launch capability. This private owned file is never
    # printed or exported as an artifact and is removed after child cleanup.
    capture = directory / 'private-launch-output.log'
    created = False
    try:
        with capture.open('xb') as output:
            created = True
            process = subprocess.Popen([executable, '--ui', '--f', str(database)],
                cwd=directory, env=env, stdin=subprocess.DEVNULL, stdout=output,
                stderr=subprocess.DEVNULL, start_new_session=not WINDOWS)
    except BaseException:
        if created:
            try: capture.unlink()
            except OSError: pass
        raise
    completed = False
    try:
        launch = _read_launch(capture, process)
        port, bootstrap = _launch_identity(launch)
        authority = f'127.0.0.1:{port}'
        origin = 'http://' + authority
        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=35)
            try:
                connection.request(method, path, body, headers or {})
                response = connection.getresponse()
                data = response.read()
                if response.status != 200: raise AssertionError(f'frozen UI HTTP {response.status}')
                return data
            finally: connection.close()
        for path in ('/', '/app.js', '/style.css', '/LICENSE.txt'):
            if not request('GET', path): raise AssertionError('empty frozen UI asset')
        writer_headers = _writer_headers(request, authority, origin, bootstrap)
        counter = 0
        revision = 0
        def rpc(method, **params):
            nonlocal counter, revision
            counter += 1
            message = {'jsonrpc':'2.0', 'id':counter, 'method':method, 'params':params}
            data = json.dumps(message, separators=(',', ':')).encode() + b'\n'
            response = json.loads(request('POST', '/rpc', data, writer_headers))
            if response.get('id') != counter or 'result' not in response:
                raise AssertionError('frozen UI RPC failed')
            result = response['result']
            revision = result['revision']
            return result
        def event(name, **params):
            return rpc('editor.event', event=name, baseRevision=revision, **params)
        rpc('editor.hello', protocol='yadinassi-editor/0')
        event('selectCatalog', catalog=str(CATEGORY))
        event('create')
        event('change', control='InputData0', value={'type':'String','value':'40'})
        event('change', control='InputData1', value={'type':'String','value':'Frozen persisted'})
        saved = event('command', control='SaveButton')
        if saved['state']['editor']['saveState'] != 'saved':
            raise AssertionError('frozen UI save not confirmed')
        event('closeCard')
        closed = event('close')
        if closed['state']['kind'] != 'closed': raise AssertionError('frozen UI close failed')
        if process.wait(timeout=15) != 0: raise AssertionError('frozen UI cleanup failed')
        completed = True
        backend = SQLiteCatalogBackend(database, read_only=True)
        view = None
        try:
            view = backend.begin_read()
            rows = view.select_catalog(CATEGORY, CatalogSelection(limit=10))
            if ('40', 'Frozen persisted') not in [(r.code, r.description) for r in rows]:
                raise AssertionError('frozen UI save not durable')
        finally:
            if view is not None: view.close()
            backend.close()
    finally:
        cleanup_ok = completed or _stop_owned_tree(process)
        try:
            capture.unlink()
        except OSError:
            cleanup_ok = False
        if not cleanup_ok:
            # Keep the original protocol/startup error, rather than replacing it
            # with an uncertain secondary cleanup result or hanging on a pipe.
            print('Frozen UI owned process-tree cleanup unverified.', file=sys.stderr)
            if sys.exc_info()[0] is None:
                raise AssertionError('frozen UI cleanup unverified')
    print('Frozen UI smoke passed: assets, child transport, save, close, reopen')
