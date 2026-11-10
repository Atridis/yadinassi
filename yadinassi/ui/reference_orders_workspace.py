"""Opt-in reference Orders workspace with one owner and one owned choice.

The browser gets scalar presentation and opaque IDs, never CatalogKeys, file
paths or callable names. No native OpenForm or generic reference codec is added.
"""
import argparse
from decimal import Decimal
import os
from pathlib import Path
import sys
from threading import Lock
from types import SimpleNamespace
import webbrowser

from .. import Interpreter
from ..database_context import SQLiteDBContext
from ..form_replication import ReplicatedFormServer
from ..invocation import InvocationBinding
from .form_app import FormController, FormProcess, PROTOCOL as FORM_PROTOCOL
from .form_package import load_client, load_server
from .local_app import LocalTransportError, LocalUIServer, _Handler
from .orders_workspace import keys, WorkspaceOperationFailed
from .protocol import encode_line, decode_line, encode_value, decode_value, MAX_LINE_BYTES, MAX_COUNTER
from .reference_orders import ReferenceOrdersSession, CatalogChoiceSession, APPLY_CHOICE_ENDPOINT

PROTOCOL = 'yadinassi-reference-orders/1'
MAX_FORMS = 2
MAX_SESSIONS = 256
PACKAGES = {'order': 'reference-order', 'choice': 'catalog-choice'}
_APPLY = InvocationBinding('ApplyChoice', APPLY_CHOICE_ENDPOINT, (), False)
_EMPTY_DELTA = {'attributes': [], 'items': [], 'title': None, 'cells': [], 'selections': []}


class ReferenceOrdersBroker:
    """Server-only registry and one-shot capability transfer, with no key on wire."""
    def __init__(self, root, database):
        self.root, self.database = root, database
        self.packages = {kind: load_server(Path(root) / path, owned_choices=True)
                         for kind, path in PACKAGES.items()}
        for kind, selector in (('order', 'reference-orders/1'), ('choice', 'catalog-choice/1')):
            if self.packages[kind].application != selector:
                raise ValueError('invalid owned application package')
        if self.packages['order'].endpoints.get(APPLY_CHOICE_ENDPOINT) != 'ApplyChoice':
            raise ValueError('missing fixed choice endpoint')
        self.context = SQLiteDBContext(database)
        self.vm = Interpreter(database_context=self.context)
        self.listing = ReferenceOrdersSession(self.context)
        self.sessions = {}
        self.applications = {}
        self.owners = {}
        self.tickets = {}
        self.revision = self.allocated = 0
        self.choices = {}

    def _create(self, kind, *, record=None, owner=None, ticket=None):
        if len(self.sessions) >= MAX_FORMS or self.allocated >= MAX_SESSIONS:
            raise ValueError('workspace capacity')
        self.allocated += 1
        sid = 'form-' + str(self.allocated)
        context = SQLiteDBContext(self.database)
        try:
            application = (ReferenceOrdersSession(context, initial_record=record) if kind == 'order'
                           else CatalogChoiceSession(context, ticket.target))
            if kind == 'order':
                application.choice_limit = MAX_SESSIONS - self.allocated
            package = self.packages[kind]
            server = ReplicatedFormServer(package.source, package.endpoints,
                handlers=package.handlers, attributes=package.attributes, tables=package.tables,
                initial_values=package.initial_values, bindings=package.lifecycle,
                database_context=context, server_bindings=application.bindings())
            self.sessions[sid] = (server, context)
            self.applications[sid] = application
            self.owners[sid] = owner
            if ticket is not None:
                self.tickets[sid] = ticket
            return {'session': sid, 'kind': kind, 'owner': owner}
        except BaseException:
            context.close()
            raise

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
            result = {'revision': self.revision + 1,
                'orders': [{'id': i + 1, 'code': r.values[0], 'description': r.values[1],
                            'total': encode_value(r.values[2])} for i, r in enumerate(page.rows)],
                'truncated': page.continuation is not None}
            encode_line(result)
            self.revision = result['revision']
            self.choices = {i + 1: row.key.record_id for i, row in enumerate(page.rows)}
            return result
        if operation == 'create':
            keys(payload, 'revision row')
            if self.sessions or self.allocated >= MAX_SESSIONS - 1:
                return {'error': 'capacity'}
            if type(payload['revision']) is not int or payload['revision'] != self.revision:
                return {'error': 'stale_list'}
            row = payload['row']
            if row is not None and (type(row) is not int or row not in self.choices):
                return {'error': 'stale_list'}
            return self._create('order', record=None if row is None else self.choices[row])
        if sid not in self.sessions:
            raise ValueError('retired session')
        server, context = self.sessions[sid]
        application = self.applications[sid]
        if operation == 'form':
            if self.owners[sid] is None:
                internal = payload.get('operation') == 'call' and payload.get('endpoint') == APPLY_CHOICE_ENDPOINT
                if internal:
                    if not application.result_ready or payload.get('arguments') != [] or payload.get('delta') != _EMPTY_DELTA:
                        raise ValueError('invalid owned result application')
                elif application.active_choice is not None:
                    raise ValueError('owner blocked by owned choice')
            result = decode_line(server.exchange(encode_line(payload)))
            if getattr(application, 'apply_uncertain', False):
                raise ValueError('selection installation outcome unknown')
            return result
        if operation == 'choice':
            if payload != {} or self.owners[sid] is not None:
                raise ValueError('invalid owner')
            ticket = application.active_choice
            if ticket is None:
                return {'choice': None}
            for child, owner in self.owners.items():
                if owner == sid:
                    if self.tickets[child] is not ticket:
                        raise ValueError('stale owned choice')
                    return {'choice': {'session': child, 'kind': 'choice', 'owner': sid}}
            return {'choice': self._create('choice', owner=sid, ticket=ticket)}
        if operation == 'result':
            owner = self.owners[sid]
            if payload != {} or owner is None or owner not in self.sessions:
                raise ValueError('invalid owned result')
            # A failed child bootstrap is safely cancelled, never revived.
            finished = application.finished or server.session.closed
            if finished:
                self.applications[owner].stage_result(self.tickets[sid], application.result)
            return {'finished': finished, 'owner': owner}
        if operation == 'retire':
            if payload != {} or any(owner == sid for owner in self.owners.values()):
                raise ValueError('owner still has child')
            owner = self.owners[sid]
            if owner is not None and self.applications[owner].active_choice is not None:
                raise ValueError('owned result not consumed')
            # Remove only after both releases succeed; an uncertain cleanup is
            # never repeated by the controller and locks the complete workspace.
            try:
                server.session.interpreter.close()
            finally:
                context.close()
            del self.sessions[sid], self.applications[sid], self.owners[sid]
            self.tickets.pop(sid, None)
            return {}
        raise ValueError('unknown operation')

    def close(self):
        # Process teardown has no BSL callbacks and does not apply pending results.
        failure = None
        for server, context in reversed(tuple(self.sessions.values())):
            try:
                try:
                    server.session.interpreter.close()
                finally:
                    context.close()
            except Exception as error:
                failure = error
        self.sessions.clear(); self.applications.clear(); self.owners.clear(); self.tickets.clear()
        try:
            self.vm.close()
        finally:
            self.context.close()
        if failure is not None:
            raise failure


class ReferenceWorkspaceProcess(FormProcess):
    def __init__(self, root, database):
        environment = dict(os.environ, PYTHONIOENCODING='utf-8')
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
        self._start([sys.executable, '-m', 'yadinassi.ui.reference_orders_workspace',
            str(Path(root).resolve()), '--f', str(Path(database).resolve()), '--runtime'], environment)


def serve_runtime(root, database):
    broker = None
    try:
        broker = ReferenceOrdersBroker(root, database)
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


class ReferenceWorkspaceController:
    def __init__(self, root, exchange):
        self.transport = exchange
        self.packages = {kind: load_client(Path(root) / path) for kind, path in PACKAGES.items()}
        if any(b.endpoint == APPLY_CHOICE_ENDPOINT for b in self.packages['order'].bindings):
            raise ValueError('result endpoint must be host-only')
        self.sessions = {}
        self.owners = {}
        self.operations = {}
        self.issued = set()
        self.counter = 0
        self.list_state = {'revision': 0, 'orders': [], 'truncated': False}
        self.opened = self.closed = self.uncertain = False
        self.gate = Lock()

    def _unknown(self):
        self.uncertain = True
        for controller, _ in self.sessions.values():
            controller.session.uncertain = True

    def _descriptor(self, result, kind):
        keys(result, 'session kind owner')
        sid = result['session']
        if (type(sid) is not str or not sid.startswith('form-') or not sid[5:].isascii()
                or not sid[5:].isdigit() or len(sid) > 12 or result['kind'] != kind
                or kind == 'order' and result['owner'] is not None
                or kind == 'choice' and (type(result['owner']) is not str
                    or self.owners.get(result['owner'], False) is not None)):
            raise ValueError('invalid session descriptor')

    def _call(self, operation, sid='', payload=None):
        if self.uncertain:
            raise LocalTransportError('unavailable')
        self.counter += 1
        try:
            response = decode_line(self.transport(encode_line({'id': self.counter, 'operation': operation,
                'session': sid, 'payload': {} if payload is None else payload})))
            keys(response, 'id session result error')
            if (type(response['id']) is not int or response['id'] != self.counter or response['session'] != sid
                    or response['error'] not in (None, 'operation_failed')):
                raise ValueError('invalid response identity')
            result = response['result']
            if response['error'] is not None:
                if result is not None:
                    raise ValueError('invalid failure result')
            elif type(result) is not dict:
                raise ValueError('invalid child result')
            elif operation == 'list':
                keys(result, 'revision orders truncated')
                if (type(result['revision']) is not int or not self.list_state['revision'] < result['revision'] <= MAX_COUNTER
                        or type(result['truncated']) is not bool or type(result['orders']) is not list or len(result['orders']) > 32):
                    raise ValueError('invalid list')
                for index, row in enumerate(result['orders']):
                    keys(row, 'id code description total')
                    if (type(row['id']) is not int or row['id'] != index + 1
                            or type(row['code']) is not str or len(row['code']) > 8
                            or type(row['description']) is not str or len(row['description']) > 64
                            or type(decode_value(row['total'])) is not Decimal):
                        raise ValueError('invalid list row')
            elif operation == 'create':
                if 'error' in result:
                    keys(result, 'error')
                    if result['error'] not in ('capacity', 'stale_list'):
                        raise ValueError('invalid creation refusal')
                else:
                    self._descriptor(result, 'order')
                    if result['session'] in self.issued:
                        raise ValueError('reused session')
            elif operation == 'choice':
                keys(result, 'choice')
                if result['choice'] is not None:
                    self._descriptor(result['choice'], 'choice')
                    if result['choice']['owner'] != sid:
                        raise ValueError('wrong owner')
            elif operation == 'result':
                keys(result, 'finished owner')
                if type(result['finished']) is not bool or result['owner'] != self.owners[sid]:
                    raise ValueError('invalid choice completion')
            elif operation == 'retire' and result != {}:
                raise ValueError('invalid retirement')
        except BaseException:
            self._unknown()
            raise LocalTransportError('unavailable') from None
        if response['error'] is not None:
            if operation in ('create', 'list'):
                raise WorkspaceOperationFailed('workspace operation failed')
            self._unknown()
            raise LocalTransportError('unavailable')
        return result

    def _register(self, descriptor):
        sid, kind, owner = (descriptor[k] for k in ('session', 'kind', 'owner'))
        if sid in self.issued or len(self.sessions) >= MAX_FORMS:
            self._unknown()
            raise LocalTransportError('unavailable')
        def exchange(raw):
            return encode_line(self._call('form', sid, decode_line(raw)))
        controller = FormController(self.packages[kind], exchange)
        self.sessions[sid] = (controller, kind)
        self.owners[sid] = owner
        self.issued.add(sid)
        return controller

    def _retire(self, sid):
        self._call('retire', sid)
        del self.sessions[sid], self.owners[sid]

    def _finish_choice(self, sid, request, form):
        result = self._call('result', sid)
        if not result['finished']:
            return form
        owner = self.sessions[result['owner']][0].session
        child = self.sessions[sid][0]
        # The trusted host invokes the fixed zero-argument endpoint. The ordinary
        # replica machinery performs revision/sequence and complete-state checks.
        try:
            owner._begin(owner.revision)
            try:
                owner._request('call', _APPLY)
            finally:
                owner.revision += 1; owner._busy = False; owner._gate.release()
            if not child.session.closed:
                child.session.dispose()
            form = {'jsonrpc': '2.0', 'id': request['id'], 'result': {
                'protocol': FORM_PROTOCOL, 'state': child._snapshot(), 'error': form['result']['error']}}
            self._retire(sid)
            return form
        except BaseException:
            self._unknown()
            raise LocalTransportError('unavailable') from None

    def _state(self):
        return {'kind': 'closed' if self.closed else 'workspace', **self.list_state,
            'sessions': [{'id': sid, 'kind': kind, 'owner': self.owners[sid]}
                         for sid, (_, kind) in self.sessions.items()], 'uncertain': self.uncertain}

    def exchange(self, request):
        if not self.gate.acquire(blocking=False):
            raise LocalTransportError('busy')
        sid = form = error = None
        try:
            keys(request, 'jsonrpc id method params')
            if (request['jsonrpc'] != '2.0' or type(request['id']) is not int
                    or not 1 <= request['id'] <= MAX_COUNTER or type(request['params']) is not dict):
                raise ValueError('invalid workspace request')
            method, params = request['method'], request['params']
            if method == 'workspace.form' and type(params.get('session')) is str:
                sid = params['session']
            if self.closed:
                error = 'closed'
            elif self.uncertain:
                error = 'outcome_unknown'
            elif method == 'workspace.hello':
                if params != {'protocol': PROTOCOL}:
                    raise ValueError('invalid handshake')
                if not self.opened:
                    self.list_state = self._call('list', payload={'code': ''})
                    self.opened = True
            elif not self.opened:
                raise ValueError('handshake required')
            elif method == 'workspace.list':
                keys(params, 'code')
                self.list_state = self._call('list', payload=params)
            elif method == 'workspace.open':
                keys(params, 'revision row request')
                token = params['request']
                if (type(token) is not str or not 1 <= len(token) <= 64 or not token.isascii()
                        or type(params['revision']) is not int or not 0 <= params['revision'] <= MAX_COUNTER
                        or params['row'] is not None and (type(params['row']) is not int or not 1 <= params['row'] <= 32)):
                    raise ValueError('invalid open intent')
                intent = params['revision'], params['row']
                if token in self.operations:
                    previous, sid, error = self.operations[token]
                    if previous != intent:
                        raise ValueError('open token reused')
                    if sid is not None and sid not in self.sessions:
                        error, sid = 'retired_session', None
                    elif sid is not None:
                        form = self.sessions[sid][0].exchange({'jsonrpc': '2.0', 'id': 1,
                            'method': 'form.snapshot', 'params': {}})
                elif len(self.operations) >= MAX_SESSIONS:
                    error = 'capacity'
                else:
                    result = self._call('create', payload={'revision': params['revision'], 'row': params['row']})
                    error = result.get('error')
                    if error is None:
                        sid = result['session']
                        try:
                            controller = self._register(result)
                        except LocalTransportError:
                            raise
                        except Exception:
                            self._call('retire', sid)
                            sid, form, error = None, None, 'open_failed'
                        else:
                            form = controller.exchange({'jsonrpc': '2.0', 'id': 1, 'method': 'form.hello',
                                'params': {'protocol': FORM_PROTOCOL}})
                            if controller.session.uncertain:
                                self._unknown()
                            elif form['result']['error'] or form['result']['state']['kind'] == 'closed':
                                self._retire(sid)
                                sid, form, error = None, None, 'open_failed'
                    self.operations[token] = (intent, sid, error)
            elif method == 'workspace.form':
                keys(params, 'session request')
                sid, nested = params['session'], params['request']
                if type(sid) is not str or sid not in self.sessions:
                    error = 'retired_session'
                else:
                    controller, kind = self.sessions[sid]
                    if kind == 'order' and sid in self.owners.values() and nested.get('method') == 'form.event':
                        error = 'owner_blocked'
                        form = controller.exchange({'jsonrpc': '2.0', 'id': nested['id'], 'method': 'form.snapshot', 'params': {}})
                    else:
                        form = controller.exchange(nested)
                        if controller.session.uncertain:
                            self._unknown()
                        elif kind == 'choice':
                            form = self._finish_choice(sid, nested, form)
                        elif form['result']['state']['kind'] == 'closed':
                            self._retire(sid)
                        else:
                            child = self._call('choice', sid)['choice']
                            if child is not None and child['session'] not in self.sessions:
                                try:
                                    self._register(child)
                                except BaseException:
                                    self._unknown()
                                    raise LocalTransportError('unavailable') from None
            elif method == 'workspace.close':
                if params != {}:
                    raise ValueError('invalid shutdown')
                if self.sessions:
                    error = 'forms_open'
                else:
                    self.closed = True
            else:
                raise ValueError('unknown workspace method')
        except WorkspaceOperationFailed:
            sid, form, error = None, None, 'operation_failed'
        except LocalTransportError:
            self._unknown()
            form, error = None, 'outcome_unknown'
        finally:
            self.gate.release()
        response = {'jsonrpc': '2.0', 'id': request['id'], 'result': {
            'protocol': PROTOCOL, 'state': self._state(), 'error': error, 'session': sid, 'form': form}}
        try:
            encode_line(response)
        except Exception:
            self._unknown()
            raise LocalTransportError('unavailable') from None
        return response


class ReferenceWorkspaceHandler(_Handler):
    asset_directory = 'reference-workspace'
    methods = ('workspace.hello', 'workspace.list', 'workspace.open', 'workspace.form', 'workspace.close')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run the bounded reference Orders workspace.')
    parser.add_argument('packages', help='Trusted forms root with reference-order and catalog-choice')
    parser.add_argument('--f', required=True, help='Existing reference Orders SQLite database')
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--runtime', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runtime:
        return serve_runtime(args.packages, args.f)
    process = server = None
    try:
        process = ReferenceWorkspaceProcess(args.packages, args.f)
        server = LocalUIServer(ReferenceWorkspaceController(args.packages, process.exchange), handler=ReferenceWorkspaceHandler)
        print('Reference Orders workspace. Open this private per-launch URL:')
        print(server.launch_url, flush=True)
        if args.open_browser:
            webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Reference Orders workspace unavailable.', file=sys.stderr)
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
