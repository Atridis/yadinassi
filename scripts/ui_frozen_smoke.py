"""Isolated end-to-end check of the packaged local UI and child runtime."""
import http.client
import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]


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
    process = subprocess.Popen([executable, '--ui', '--f', str(database)],
        cwd=directory, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)
    lines = Queue()
    def read_output():
        for line in iter(process.stdout.readline, b''):
            lines.put(line)
        lines.put(None)
    reader = Thread(target=read_output, daemon=True)
    reader.start()
    completed = False
    try:
        launch = None
        for _ in range(3):
            try: line = lines.get(timeout=45)
            except Empty: raise AssertionError('frozen UI launch timed out') from None
            if line is None: raise AssertionError('frozen UI exited before launch URL')
            if line.startswith(b'http://127.0.0.1:'):
                launch = line.decode('ascii').strip()
        if not launch: raise AssertionError('frozen UI launch URL missing')
        url = urlsplit(launch)
        token = parse_qs(url.fragment, strict_parsing=True).get('session', [])
        if url.hostname != '127.0.0.1' or not url.port or len(token) != 1:
            raise AssertionError('invalid local UI launch URL')
        authority = f'127.0.0.1:{url.port}'
        origin = 'http://' + authority
        def request(method, path, body=None, headers=None):
            connection = http.client.HTTPConnection('127.0.0.1', url.port, timeout=35)
            try:
                connection.request(method, path, body, headers or {})
                response = connection.getresponse()
                data = response.read()
                if response.status != 200: raise AssertionError(f'frozen UI HTTP {response.status}')
                return data
            finally: connection.close()
        for path in ('/', '/app.js', '/style.css', '/LICENSE.txt'):
            if not request('GET', path): raise AssertionError('empty frozen UI asset')
        counter = 0
        revision = 0
        def rpc(method, **params):
            nonlocal counter, revision
            counter += 1
            message = {'jsonrpc':'2.0', 'id':counter, 'method':method, 'params':params}
            data = json.dumps(message, separators=(',', ':')).encode() + b'\n'
            response = json.loads(request('POST', '/rpc', data, {
                'Host':authority, 'Origin':origin, 'Content-Type':'application/x-ndjson',
                'X-Yadinassi-Session':token[0]}))
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
        if not completed and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)
        process.stdout.close()
        reader.join(timeout=2)
    print('Frozen UI smoke passed: assets, child transport, save, close, reopen')
