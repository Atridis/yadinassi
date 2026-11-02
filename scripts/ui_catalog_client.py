"""Independent tiny renderer/client example, with no yadinassi imports.

Use HeadlessCatalogClient with a bytes exchange callable, or run this script
with an existing SQLite file to browse its first supported catalog in a subprocess.
Typed values are retained as JSON tags; this client never evaluates BSL.
The example trusts the host implementation. It validates identities/revisions,
but is not a hardened JSON decoder for hostile servers or network connections.
"""
import json
from pathlib import Path
import subprocess
import sys


class HeadlessCatalogClient:
    def __init__(self, exchange):
        self.exchange = exchange
        self.request_id = 0
        self.revision = 0
        self.snapshot = None
        self.closed = False

    @staticmethod
    def _counter(value):
        return type(value) is int and 0 <= value <= 2147483647

    def request(self, method, params):
        self.request_id += 1
        message = {'jsonrpc': '2.0', 'id': self.request_id, 'method': method, 'params': params}
        raw = (json.dumps(message, ensure_ascii=False) + '\n').encode('utf-8')
        frames = self.exchange(raw)
        if type(frames) not in (tuple, list) or not 1 <= len(frames) <= 2:
            raise ValueError('invalid response count')
        if any(type(line) is not bytes or len(line) > 131072 for line in frames):
            raise ValueError('invalid response frame')
        messages = [json.loads(line) for line in frames]
        if (any(type(item) is not dict or item.get('jsonrpc') != '2.0' for item in messages)
                or type(messages[0].get('id')) is not int or messages[0]['id'] != self.request_id):
            raise ValueError('invalid response identity')
        response = messages[0]
        if 'error' in response:
            if len(messages) != 1 or set(response) != {'jsonrpc', 'id', 'error'}:
                raise ValueError('invalid error response')
            raise ValueError(response['error']['data']['reason'])
        if set(response) != {'jsonrpc', 'id', 'result'} or type(response['result']) is not dict:
            raise ValueError('invalid result')
        result = response['result']
        if result.get('protocol') != 'yadinassi-ui/0':
            raise ValueError('unsupported protocol')
        revision = result.get('revision')
        if not self._counter(revision):
            raise ValueError('invalid revision')
        snapshot, closed = self.snapshot, self.closed
        if method == 'ui.snapshot':
            if len(messages) != 1 or set(result) != {'protocol', 'revision', 'snapshot'}:
                raise ValueError('unexpected notification')
            data = result['snapshot']
            if (type(data) is not dict or data.get('formId') != 'catalog-browser'
                    or not self._counter(data.get('revision'))
                    or data['revision'] != revision or revision != self.revision
                    or type(data.get('state')) is not dict or type(data.get('capabilities')) is not dict):
                raise ValueError('invalid snapshot identity or revision')
            snapshot = data
        else:
            if len(messages) != 2 or set(result) != {'protocol', 'revision'}:
                raise ValueError('missing notification')
            change = messages[1]
            if set(change) != {'jsonrpc', 'method', 'params'} or type(change['params']) is not dict:
                raise ValueError('invalid notification')
            data = change['params']
            if (data.get('formId') != 'catalog-browser' or not self._counter(data.get('revision'))
                    or data['revision'] != revision):
                raise ValueError('invalid form revision')
            if change['method'] == 'ui.open' and method == 'ui.hello':
                if (revision != 0 or self.snapshot is not None or type(data.get('state')) is not dict
                        or type(data.get('capabilities')) is not dict):
                    raise ValueError('invalid initial snapshot')
                snapshot = data
            elif change['method'] in ('ui.patch', 'ui.close') and method == 'ui.event':
                if (not self._counter(data.get('baseRevision')) or data['baseRevision'] != self.revision
                        or revision != self.revision + 1 or self.snapshot is None):
                    raise ValueError('out-of-order patch')
                closed = change['method'] == 'ui.close'
                snapshot = {**self.snapshot, 'revision': revision}
                if not closed:
                    if type(data.get('state')) is not dict:
                        raise ValueError('invalid patch state')
                    snapshot['state'] = data['state']
            else:
                raise ValueError('unexpected notification')
        self.snapshot, self.closed = snapshot, closed
        self.revision = revision
        return self.snapshot

    def hello(self):
        return self.request('ui.hello', {'protocol': 'yadinassi-ui/0'})

    def event(self, event, **values):
        return self.request('ui.event', {'formId': 'catalog-browser',
            'baseRevision': self.revision, 'event': event, **values})


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print('Expected one existing SQLite database file.', file=sys.stderr)
        return 2
    bridge = Path(__file__).with_name('ui_catalog_bridge.py')
    child = subprocess.Popen([sys.executable, str(bridge), arguments[0]],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    def exchange(raw):
        child.stdin.write(raw)
        child.stdin.flush()
        first = child.stdout.readline(131073)
        if not first or len(first) > 131072:
            raise ValueError('missing or oversized response')
        result = json.loads(first)
        if 'error' in result or 'snapshot' in result.get('result', {}):
            return (first,)
        second = child.stdout.readline(131073)
        if not second or len(second) > 131072:
            raise ValueError('missing or oversized notification')
        return first, second
    try:
        client = HeadlessCatalogClient(exchange)
        state = client.hello()
        print(json.dumps(state, ensure_ascii=False))
        catalogs = state['state']['catalogs']
        if catalogs:
            state = client.event('selectCatalog', catalog=catalogs[0]['id'])
            print(json.dumps(state, ensure_ascii=False))
            rows = state['state']['list']['rows']
            if rows:
                print(json.dumps(client.event('openCard', reference=rows[0]['reference']),
                                 ensure_ascii=False))
        client.event('close')
        return 0
    except (ValueError, OSError):
        print('Headless catalog operation rejected; inspect the supported SQLite profile.', file=sys.stderr)
        return 1
    finally:
        child.stdin.close()
        child.stdout.close()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == '__main__':
    raise SystemExit(main())
