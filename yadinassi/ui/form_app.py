"""Opt-in loopback renderer + local client BSL + separate server BSL process.

This launcher is for trusted local applications. It is neither a network BSL
server nor a sandbox. It never retries a request after its outcome is unknown.
"""
import argparse
import os
from pathlib import Path
from queue import Empty, Full
import sys
from threading import Lock
import webbrowser

from ..database_context import SQLiteDBContext
from ..form_replication import ReplicatedFormServer, ReplicatedFormSession
from ..invocation import InvocationError, _decode_scalar
from .form_package import load_client, load_server
from .local_app import RuntimeBridge, LocalTransportError, LocalUIServer, _Handler, EXCHANGE_TIMEOUT
from .protocol import encode_line, encode_value, decode_value, decode_line, MAX_LINE_BYTES, MAX_COUNTER

PROTOCOL = 'yadinassi-form-ui/1'


class FormProcess(RuntimeBridge):
    """Owned persistent byte pipe. Server file/database paths are host setup only."""
    def __init__(self, directory, database=None):
        environment = dict(os.environ)
        environment['PYTHONIOENCODING'] = 'utf-8'
        if getattr(sys, 'frozen', False):
            command = [sys.executable, '--form-ui-runtime', str(Path(directory).resolve())]
        else:
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
            command = [sys.executable, '-m', 'yadinassi.ui.form_app', '--runtime', str(Path(directory).resolve())]
        if database is not None:
            command += ['--f', str(Path(database).resolve())]
        self._start(command, environment)

    def exchange(self, raw):
        if not self.gate.acquire(blocking=False):
            raise LocalTransportError('busy')
        try:
            if self._closed or self.failed or self.counter >= 4096:
                raise LocalTransportError('unavailable')
            if type(raw) is not bytes or not 1 <= len(raw) <= MAX_LINE_BYTES or not raw.endswith(b'\n'):
                raise ValueError('invalid form frame')
            self.counter += 1
            self._requests.put_nowait(raw)
            reply = self._replies.get(timeout=EXCHANGE_TIMEOUT)
            if not reply or len(reply) > MAX_LINE_BYTES or not reply.endswith(b'\n'):
                raise LocalTransportError('unavailable')
            return reply
        except (OSError, LocalTransportError, Empty, Full):
            self.failed = True
            raise LocalTransportError('unavailable') from None
        except BaseException:
            # Once admitted, cancellation may interrupt a write/read anywhere.
            if self.counter:
                self.failed = True
            raise
        finally:
            self.gate.release()


def create_server(package, context=None):
    """Closed host application factory. Nothing is imported from package data."""
    application = None
    if package.application == 'orders-workbench/1':
        from .order_workbench import OrdersWorkbenchSession
        application = OrdersWorkbenchSession(context)
    server = ReplicatedFormServer(package.source, package.endpoints,
        handlers=package.handlers, attributes=package.attributes, tables=package.tables,
        initial_values=package.initial_values, bindings=package.lifecycle,
        database_context=context,
        server_bindings=() if application is None else application.bindings())
    return server


def serve_runtime(directory, database=None, *, input_stream=None, output_stream=None):
    """Host-owned stdio service. EOF closes the database, never creates one."""
    context = None
    try:
        package = load_server(directory)
        if database is not None:
            context = SQLiteDBContext(database)
        server = create_server(package, context)
        source = sys.stdin.buffer if input_stream is None else input_stream
        target = sys.stdout.buffer if output_stream is None else output_stream
        while True:
            raw = source.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return 0
            if len(raw) > MAX_LINE_BYTES or not raw.endswith(b'\n'):
                return 1
            response = server.exchange(raw)
            target.write(response); target.flush()
    except Exception:
        # No source, path, value or private exception is printed onto the wire.
        return 1
    finally:
        if context is not None:
            context.close()


class FormController:
    """One logical client session shared by renderer reattachments, not reloads."""
    def __init__(self, package, exchange):
        self.session = ReplicatedFormSession(package.source, exchange,
            handlers=package.handlers, bindings=package.bindings)
        self._gate = Lock()
        self._opened = False
        self._discard_commands = dict(package.discard_commands)
        self._dirty_attribute = package.dirty_attribute

    def _snapshot(self):
        session = self.session
        snapshot = session.snapshot()
        values = {key.casefold(): value for key, value in snapshot.attributes}
        views = {key.casefold(): value for key, value in snapshot.item_views}
        tables = {table.name.casefold(): table for table in snapshot.tables}
        selections = dict(snapshot.selections)
        items = []
        for name, kind, title, visible, enabled, read_only, path in snapshot.items:
            if kind == 'table':
                table = tables[path.casefold()]
                control_id = session.form.items._values[name.casefold()]._replica_id
                items.append({'name': name, 'kind': 'table', 'title': title or table.title,
                    'visible': visible, 'enabled': enabled, 'readOnly': read_only,
                    'controlId': control_id, 'tableId': table.identity,
                    'columns': [{'name': key, 'title': caption, 'type': value_type, 'readOnly': readonly}
                                for key, caption, value_type, readonly in table.columns],
                    'rows': [{'id': identity, 'values': [encode_value(value) for value in values]}
                             for identity, values in table.rows],
                    'currentRow': selections.get(name)})
                continue
            view = views.get(name.casefold(), 'input')
            # Native view names are not renderer-controlled.
            view = {'InputField': 'input', 'CheckBoxField': 'checkbox', 'LabelField': 'label'}.get(view, view)
            if view not in ('input', 'checkbox', 'label'):
                raise ValueError('unsupported form field view')
            value = None if kind == 'button' else encode_value(values.get(path.casefold()))
            items.append({'name': name, 'kind': kind, 'title': title, 'visible': visible,
                'enabled': enabled, 'readOnly': read_only, 'view': view, 'value': value})
        state = {'kind': 'closed' if session.closed and not session.uncertain else 'form',
            'revision': snapshot.revision, 'lifecycle': snapshot.state, 'title': snapshot.title,
            'uncertain': session.uncertain, 'items': items, 'messages': list(session.messages)}
        if self._dirty_attribute:
            dirty = values.get(self._dirty_attribute.casefold())
            if type(dirty) is not bool:
                raise ValueError('invalid trusted dirty attribute')
            state['dirty'] = dirty
            discard = []
            for item in session.form.items._values.values():
                if getattr(item, 'command_name', '') not in self._discard_commands:
                    continue
                command = session.form.commands._values.get(item.command_name.casefold())
                if command is None or command.action.casefold() != self._discard_commands[item.command_name].casefold():
                    raise ValueError('discard command binding changed')
                discard.append(item.name)
            state['discardCommands'] = discard
        return state

    def exchange(self, request):
        if not self._gate.acquire(blocking=False):
            raise LocalTransportError('busy')
        try:
            if (type(request) is not dict or set(request) != {'jsonrpc', 'id', 'method', 'params'}
                    or request['jsonrpc'] != '2.0' or type(request['id']) is not int
                    or not 1 <= request['id'] <= MAX_COUNTER or type(request['params']) is not dict):
                raise ValueError('invalid renderer request')
            method, params = request['method'], request['params']
            error = None
            if method == 'form.hello':
                if params != {'protocol': PROTOCOL}:
                    raise ValueError('invalid form handshake')
                if not self._opened:
                    self._opened = True  # A failed open is never tried again.
                    try:
                        self.session.open()
                    except Exception:
                        error = 'outcome_unknown' if self.session.uncertain else 'event_failed'
            elif not self._opened:
                raise ValueError('form handshake required')
            elif method == 'form.snapshot':
                if params:
                    raise ValueError('invalid form snapshot request')
            elif method == 'form.event':
                event = params.get('event')
                keys = {'event', 'revision'}
                if event in ('change', 'command', 'cell', 'select'):
                    keys.add('control')
                if event in ('change', 'cell'):
                    keys.add('value')
                if event in ('cell', 'select'):
                    keys.add('row')
                if event == 'cell':
                    keys.add('column')
                if (event not in ('change', 'command', 'close', 'cell', 'select') or set(params) != keys
                        or type(params['revision']) is not int or not 0 <= params['revision'] <= MAX_COUNTER
                        or event != 'close' and type(params['control']) is not str):
                    raise ValueError('invalid form event')
                if event in ('cell', 'select'):
                    row = params['row']
                    if (row is not None and (type(row) is not int or not 1 <= row <= 4096)
                            or event == 'cell' and (row is None or type(params['column']) is not str)):
                        raise ValueError('invalid table event')
                value = (decode_value(params['value']) if event == 'cell' else
                         _decode_scalar(params['value']) if event == 'change' else None)
                if self.session.uncertain:
                    error = 'outcome_unknown'
                elif params['revision'] != self.session.revision:
                    error = 'stale_revision'
                elif self.session.closed:
                    error = 'closed'
                else:
                    try:
                        self.session.dispatch(event, revision=params['revision'],
                            control=params.get('control', ''), value=value,
                            row=params.get('row'), column=params.get('column', ''))
                    except Exception:
                        error = 'outcome_unknown' if self.session.uncertain else 'event_failed'
            else:
                raise ValueError('invalid form method')
            try:
                response = {'jsonrpc': '2.0', 'id': request['id'], 'result': {
                    'protocol': PROTOCOL, 'state': self._snapshot(), 'error': error}}
                encode_line(response)  # Admit the entire response before giving it to HTTP.
            except Exception:
                # An event may already have effects. Never send partial display data.
                self.session.uncertain = True
                raise LocalTransportError('unavailable') from None
            return response
        finally:
            self._gate.release()


class FormHandler(_Handler):
    asset_directory = 'form'
    methods = ('form.hello', 'form.snapshot', 'form.event')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run a trusted local replicated form application.')
    parser.add_argument('package', metavar='PACKAGE_DIRECTORY')
    parser.add_argument('--f', metavar='SQLITE_FILE', help='Existing SQLite database, opened only by the server process')
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--runtime', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.runtime:
        return serve_runtime(args.package, args.f)
    process = server = None
    try:
        package = load_client(args.package)
        process = FormProcess(args.package, args.f)
        controller = FormController(package, process.exchange)
        server = LocalUIServer(controller, handler=FormHandler)
        print('Yadinassi replicated form — local client and separate server process.')
        print('Open this per-launch URL (do not share it):')
        print(server.launch_url, flush=True)
        if args.open_browser:
            webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Local form application unavailable.', file=sys.stderr)
        return 1
    finally:
        failed = False
        for owned, method in ((server, 'server_close'), (process, 'close')):
            try:
                if owned is not None:
                    getattr(owned, method)()
            except Exception:
                failed = True
        if failed:
            print('Local form application cleanup failed.', file=sys.stderr)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
