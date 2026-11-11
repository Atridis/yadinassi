"""Closed, bounded Orders workspace. No browser-selected code or database keys."""
import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys
from threading import Lock
from types import SimpleNamespace
import webbrowser

from .. import Interpreter
from ..database_context import SQLiteDBContext
from ..form_replication import ReplicatedFormServer
from .form_app import FormController, FormProcess, PROTOCOL as FORM_PROTOCOL
from .form_package import load_client, load_server
from .local_app import LocalTransportError, LocalUIServer, _Handler
from .order_workbench import OrdersWorkbenchSession
from .protocol import encode_line, decode_line, encode_value, MAX_LINE_BYTES, MAX_COUNTER

PROTOCOL = 'yadinassi-orders-workspace/1'
MAX_FORMS = 4
MAX_SESSIONS = 256
PACKAGES = {'intake': 'order-intake', 'editor': 'order-editor'}


class WorkspaceOperationFailed(ValueError):
    """An authoritative management refusal, not a broken replica transport."""



def package_path(root, kind):
    return Path(root) / PACKAGES[kind]


def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected.split()):
        raise ValueError('invalid workspace envelope')


class OrdersBroker:
    """Child-only registry: each replica owns a database context and object session."""
    def __init__(self, root, database):
        self.root, self.database = root, database
        self.packages = {kind: load_server(package_path(root, kind)) for kind in PACKAGES}
        self.context = SQLiteDBContext(database)
        self.vm = Interpreter(database_context=self.context)
        self.listing = OrdersWorkbenchSession(self.context)
        self.sessions = {}
        self.revision = 0
        self.allocated = 0
        self.choices = {}

    def exchange(self, packet):
        keys(packet, 'operation session payload')
        operation, sid, payload = packet['operation'], packet['session'], packet['payload']
        if type(sid) is not str:
            raise ValueError('invalid session')
        if operation == 'list':
            keys(payload, 'code')
            page = self.listing.list_page(SimpleNamespace(interpreter=self.vm), payload['code'])
            if self.revision >= MAX_COUNTER:
                raise ValueError('list exhausted')
            revision = self.revision + 1
            if any(len(row.values[0]) > 8 or len(row.values[1]) > 64 for row in page.rows):
                raise ValueError('invalid list projection')
            rows = [{'id': index + 1, 'code': row.values[0], 'description': row.values[1],
                     'total': encode_value(row.values[2])} for index, row in enumerate(page.rows)]
            result = {'revision': revision, 'orders': rows, 'truncated': page.continuation is not None}
            encode_line(result)
            self.revision = revision
            self.choices = {index + 1: row.key.record_id for index, row in enumerate(page.rows)}
            return result
        if operation == 'create':
            keys(payload, 'revision row')
            if len(self.sessions) >= MAX_FORMS or self.allocated >= MAX_SESSIONS:
                return {'error': 'capacity'}
            if type(payload['revision']) is not int or payload['revision'] != self.revision:
                return {'error': 'stale_list'}
            row = payload['row']
            if row is not None and (type(row) is not int or row not in self.choices):
                return {'error': 'stale_list'}
            self.allocated += 1
            sid = 'form-' + str(self.allocated)
            kind = 'intake' if row is None else 'editor'
            context = SQLiteDBContext(self.database)
            try:
                package = self.packages[kind]
                application = None if row is None else OrdersWorkbenchSession(context, initial_record=self.choices[row])
                server = ReplicatedFormServer(package.source, package.endpoints,
                    handlers=package.handlers, attributes=package.attributes, tables=package.tables,
                    initial_values=package.initial_values, bindings=package.lifecycle,
                    database_context=context, server_bindings=() if application is None else application.bindings())
                self.sessions[sid] = (server, context)
                return {'session': sid, 'kind': kind}
            except BaseException:
                context.close()
                raise
        if operation == 'form':
            if sid not in self.sessions:
                raise ValueError('retired session')
            return decode_line(self.sessions[sid][0].exchange(encode_line(payload)))
        if operation == 'abandon':
            if payload != {} or sid not in self.sessions:
                raise ValueError('invalid discard')
            server, _ = self.sessions[sid]
            data = server.session.form._data
            if 'saveattempted' not in data or data['saveattempted'] is not False:
                return {'error': 'discard_refused'}
            self.exchange({'operation': 'retire', 'session': sid, 'payload': {}})
            return {'error': None}
        if operation == 'retire':
            if payload != {} or sid not in self.sessions:
                raise ValueError('invalid retirement')
            server, context = self.sessions.pop(sid)
            try:
                server.session.interpreter.close()
            finally:
                context.close()
            return {}
        raise ValueError('unknown operation')

    def close(self):
        try:
            for sid in list(self.sessions):
                self.exchange({'operation': 'retire', 'session': sid, 'payload': {}})
        finally:
            try:
                self.vm.close()
            finally:
                self.context.close()


class WorkspaceProcess(FormProcess):
    def __init__(self, root, database):
        environment = dict(os.environ, PYTHONIOENCODING='utf-8')
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
        self._start([sys.executable, '-m', 'yadinassi.ui.orders_workspace', str(Path(root).resolve()),
                     '--f', str(Path(database).resolve()), '--runtime'], environment)


def serve_runtime(root, database):
    broker = None
    try:
        broker = OrdersBroker(root, database)
        while True:
            raw = sys.stdin.buffer.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return 0
            request = decode_line(raw)
            keys(request, 'id operation session payload')
            try:
                result = broker.exchange({k: request[k] for k in ('operation', 'session', 'payload')})
                response = {'id': request['id'], 'session': request['session'], 'result': result, 'error': None}
            except Exception:
                response = {'id': request['id'], 'session': request['session'], 'result': None, 'error': 'operation_failed'}
            sys.stdout.buffer.write(encode_line(response)); sys.stdout.buffer.flush()
    except Exception:
        return 1
    finally:
        if broker is not None:
            broker.close()


class WorkspaceController:
    def __init__(self, root, exchange):
        self.root, self.transport = root, exchange
        self.packages = {kind: load_client(package_path(root, kind)) for kind in PACKAGES}
        self.sessions = {}
        self.operations = {}
        self.issued = set()
        self.counter = 0
        self.list_state = {'revision': 0, 'orders': [], 'truncated': False}
        self.opened = self.closed = self.uncertain = False
        self.gate = Lock()

    def _call(self, operation, sid='', payload=None):
        if self.uncertain:
            raise LocalTransportError('unavailable')
        self.counter += 1
        try:
            response = decode_line(self.transport(encode_line({'id': self.counter, 'operation': operation,
                'session': sid, 'payload': {} if payload is None else payload})))
            keys(response, 'id session result error')
            if type(response['id']) is not int or response['id'] != self.counter or response['session'] != sid:
                raise ValueError('mismatched response')
            if response['error'] not in (None, 'operation_failed'):
                raise ValueError('invalid child error')
            result = response['result']
            if response['error'] is None:
                if type(result) is not dict:
                    raise ValueError('invalid child result')
                if operation == 'list':
                    keys(result, 'revision orders truncated')
                    if (type(result['revision']) is not int or not 1 <= result['revision'] <= MAX_COUNTER
                            or type(result['truncated']) is not bool or type(result['orders']) is not list
                            or len(result['orders']) > 32):
                        raise ValueError('invalid list')
                    for index, row in enumerate(result['orders']):
                        keys(row, 'id code description total')
                        if (type(row['id']) is not int or row['id'] != index + 1
                                or type(row['code']) is not str or len(row['code']) > 8
                                or type(row['description']) is not str or len(row['description']) > 64):
                            raise ValueError('invalid list row')
                        from .protocol import decode_value
                        from decimal import Decimal
                        if type(decode_value(row['total'])) is not Decimal:
                            raise ValueError('invalid total')
                elif operation == 'create':
                    if 'error' in result:
                        keys(result, 'error')
                        if result['error'] not in ('capacity', 'stale_list'):
                            raise ValueError('invalid creation refusal')
                    else:
                        keys(result, 'session kind')
                        if (type(result['session']) is not str or not result['session'].startswith('form-')
                                or not result['session'][5:].isdigit() or len(result['session']) > 12
                                or result['session'] in self.issued or result['kind'] not in PACKAGES):
                            raise ValueError('invalid new session')
                elif operation == 'retire' and result != {}:
                    raise ValueError('invalid retirement')
                elif operation == 'abandon':
                    keys(result, 'error')
                    if result['error'] not in (None, 'discard_refused'):
                        raise ValueError('invalid discard')
        except BaseException:
            self.uncertain = True
            for controller, _ in self.sessions.values():
                controller.session.uncertain = True
            raise LocalTransportError('unavailable') from None
        if response['error'] is not None:
            if operation in ('create', 'list'):
                raise WorkspaceOperationFailed('workspace operation failed')
            # A failed retirement/abandon may already have removed child state.
            # Keep every parent form retained and fail closed, never fabricate a
            # sessionless ordinary response or replay cleanup on this transport.
            self.uncertain = True
            for controller, _ in self.sessions.values():
                controller.session.uncertain = True
            raise LocalTransportError('unavailable')
        return response['result']

    def _state(self):
        return {'kind': 'closed' if self.closed else 'workspace', **self.list_state,
                'sessions': [{'id': sid, 'kind': kind} for sid, (_, kind) in self.sessions.items()],
                'uncertain': self.uncertain}

    def exchange(self, request):
        if not self.gate.acquire(blocking=False):
            raise LocalTransportError('busy')
        try:
            keys(request, 'jsonrpc id method params')
            if request['jsonrpc'] != '2.0' or type(request['id']) is not int or not 1 <= request['id'] <= MAX_COUNTER:
                raise ValueError('invalid request')
            method, params = request['method'], request['params']
            error = None; sid = None; form = None
            if self.closed:
                error = 'closed'
            elif self.uncertain:
                error = 'outcome_unknown'
            elif method == 'workspace.hello':
                if params != {'protocol': PROTOCOL}:
                    raise ValueError('invalid handshake')
                if not self.opened:
                    self.opened = True
                    self.list_state = self._call('list', payload={'code': ''})
            elif not self.opened:
                raise ValueError('handshake required')
            elif method == 'workspace.list':
                keys(params, 'code')
                self.list_state = self._call('list', payload=params)
            elif method == 'workspace.open':
                keys(params, 'revision row request')
                token = params['request']
                if type(token) is not str or not 1 <= len(token) <= 64 or not token.isascii():
                    raise ValueError('invalid open token')
                intent = (params['revision'], params['row'])
                if token in self.operations:
                    previous, sid, error = self.operations[token]
                    if previous != intent:
                        raise ValueError('open token reused')
                    if sid is not None and sid not in self.sessions:
                        error, sid = 'retired_session', None
                elif len(self.operations) >= MAX_SESSIONS:
                    error = 'capacity'
                else:
                    result = self._call('create', payload={'revision': params['revision'], 'row': params['row']})
                    error = result.get('error')
                    if not error:
                        sid, kind = result['session'], result['kind']
                        self.issued.add(sid)
                        controller = None
                        try:
                            package = self.packages[kind]
                            # Trusted fixed intake lifecycle policy, independent of v2 application selection.
                            if kind == 'intake':
                                package = replace(package, dirty_attribute='Dirty')
                            def exchange(raw, session=sid):
                                return encode_line(self._call('form', session, decode_line(raw)))
                            controller = FormController(package, exchange)
                            form = controller.exchange({'jsonrpc': '2.0', 'id': 1, 'method': 'form.hello',
                                                        'params': {'protocol': FORM_PROTOCOL}})
                            if controller.session.uncertain:
                                self.uncertain = True
                                for other, _ in self.sessions.values():
                                    other.session.uncertain = True
                            if form['result']['error'] or form['result']['state']['kind'] == 'closed':
                                raise ValueError('open failed')
                            self.sessions[sid] = (controller, kind)
                        except Exception:
                            if controller is not None and controller.session.uncertain:
                                self.uncertain = True
                                for other, _ in self.sessions.values():
                                    other.session.uncertain = True
                            if not self.uncertain:
                                self._call('retire', sid)
                            sid, form, error = None, None, 'open_failed'
                    self.operations[token] = (intent, sid, error)
            elif method == 'workspace.form':
                keys(params, 'session request')
                sid = params['session']
                if type(sid) is not str or sid not in self.sessions:
                    error = 'retired_session'
                else:
                    controller, _ = self.sessions[sid]
                    form = controller.exchange(params['request'])
                    if controller.session.uncertain:
                        self.uncertain = True
                        for other, _ in self.sessions.values():
                            other.session.uncertain = True
                    if form['result']['state']['kind'] == 'closed':
                        self._call('retire', sid)
                        del self.sessions[sid]
            elif method == 'workspace.discard':
                keys(params, 'session')
                sid = params['session']
                if type(sid) is not str or sid not in self.sessions:
                    error = 'retired_session'
                elif self.sessions[sid][1] != 'intake':
                    error = 'discard_refused'
                else:
                    result = self._call('abandon', sid)
                    error = result['error']
                    if error is None:
                        del self.sessions[sid]
            elif method == 'workspace.close':
                if params != {}:
                    raise ValueError('invalid shutdown')
                # Require explicit ordinary close of every form, including hidden forms.
                if self.sessions:
                    error = 'forms_open'
                else:
                    self.closed = True
            else:
                raise ValueError('unknown workspace method')
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': {'protocol': PROTOCOL,
                'state': self._state(), 'error': error, 'session': sid, 'form': form}}
            encode_line(response)
            return response
        except WorkspaceOperationFailed:
            return {'jsonrpc': '2.0', 'id': request['id'], 'result': {'protocol': PROTOCOL,
                'state': self._state(), 'error': 'operation_failed', 'session': None, 'form': None}}
        finally:
            self.gate.release()


class WorkspaceHandler(_Handler):
    asset_directory = 'workspace'
    methods = ('workspace.hello', 'workspace.list', 'workspace.open', 'workspace.form', 'workspace.discard', 'workspace.close')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run the bounded trusted Orders workspace.')
    parser.add_argument('packages', help='Trusted forms root containing order-intake and order-editor')
    parser.add_argument('--f', required=True, help='Existing Orders SQLite database')
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--browser-session', action='store_true')
    parser.add_argument('--runtime', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runtime:
        return serve_runtime(args.packages, args.f)
    process = server = None
    try:
        process = WorkspaceProcess(args.packages, args.f)
        server = LocalUIServer(WorkspaceController(args.packages, process.exchange), handler=WorkspaceHandler,
                               browser_session=args.browser_session)
        print('Orders workspace. Open this private per-launch URL:')
        print(server.launch_url, flush=True)
        if args.open_browser:
            webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Orders workspace unavailable.', file=sys.stderr)
        return 1
    finally:
        try:
            if server is not None:
                server.server_close()
        finally:
            if process is not None:
                process.close()


if __name__ == '__main__':
    raise SystemExit(main())
