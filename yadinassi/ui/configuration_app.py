"""Explicit trusted XML configuration forms, with retained independent replicas.

OpenForm is client BSL infrastructure, not a browser procedure-name endpoint.
The browser receives opaque entry/session IDs and the existing closed form UI
contract. A failed transport locks the entire application without replay.
"""
import argparse
from collections import deque
from contextlib import nullcontext
import os
from pathlib import Path
import sys
from threading import Lock
import webbrowser

from ..configuration_forms import load_configuration_forms
from ..configuration_import import read_configuration_directory
from ..database_context import SQLiteDBContext
from ..invocation import InvocationPort, InvocationServer, _decode_scalar, _encode_scalar
from ..structures import BSLStructure, BSLFixedStructure
from ..values import HostFunction
from .form_app import FormController, FormProcess, PROTOCOL as FORM_PROTOCOL
from .local_app import LocalTransportError, LocalUIServer, _Handler
from .protocol import decode_line, encode_line, MAX_LINE_BYTES, MAX_COUNTER

PROTOCOL = 'yadinassi-configuration-app/3'
MAX_FORMS = 8
MAX_SESSIONS = 256
MAX_PARAMETERS = 32


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields.split()):
        raise ValueError('invalid application envelope')


def _parameters(values):
    """Snapshot a small scalar map; never admit a form/object/reference handle."""
    if values is None:
        values = {}
    if type(values) in (BSLStructure, BSLFixedStructure):
        values = {pair.key: pair.value for pair in values}
    if type(values) is not dict or len(values) > MAX_PARAMETERS:
        raise ValueError('scalar form parameters required')
    seen = set(); result = {}
    for key, value in values.items():
        if type(key) is not str or not key.isidentifier() or len(key) > 128 or key.casefold() in seen:
            raise ValueError('invalid form parameter')
        seen.add(key.casefold())
        result[key] = _decode_scalar(_encode_scalar(value))
    encode_line({key: _encode_scalar(value) for key, value in result.items()})
    return result


def load_application(root, *, catalog_objects=False, application_host=False, document_objects=False, business_application=False, reference_application=False):
    if sum(bool(flag) for flag in (catalog_objects, application_host, document_objects, business_application, reference_application)) > 1:
        raise ValueError('configuration source profiles cannot be combined implicitly')
    files = read_configuration_directory(root)
    if reference_application:
        from ..configuration_reference_profile import import_reference_configuration
        imported = import_reference_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs, document_schemas=imported.documents, reference_catalogs=imported.catalogs)
    if business_application:
        from ..configuration_business_profile import import_business_configuration
        imported = import_business_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs, document_schemas=imported.documents)
    if application_host:
        if catalog_objects:
            raise ValueError('application host is a separate explicit profile')
        from ..configuration_application_profile import import_application_configuration
        imported = import_application_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs)
    if document_objects:
        from ..configuration_document_profile import import_document_forms_configuration
        imported = import_document_forms_configuration(files)
        return load_configuration_forms(files, document_schemas=imported.documents)
    if catalog_objects:
        from ..configuration_xml import import_catalog_forms_configuration
        imported = import_catalog_forms_configuration(files)
        return load_configuration_forms(files, catalog_schemas=imported.catalogs)
    return load_configuration_forms(files)


def _definitions(configuration):
    return {index: definition for index, (_, definition) in
            enumerate(sorted(configuration.forms.items()), 1)}


def _runtime(configuration, side, *, business_application=False, reference_application=False, **kwargs):
    from ..configuration_application_profile import import_application_configuration
    from ..configuration_runtime import ConfigurationApplication
    if reference_application:
        from ..configuration_reference_profile import import_reference_configuration
        imported = import_reference_configuration(dict(configuration.source_files))
    elif business_application:
        from ..configuration_business_profile import import_business_configuration
        imported = import_business_configuration(dict(configuration.source_files))
    else:
        imported = import_application_configuration(dict(configuration.source_files))
    return ConfigurationApplication(imported, side=side, **kwargs)


class ConfigurationBroker:
    """Server-process registry, bound to exactly one admitted configuration digest."""
    def __init__(self, configuration, database=None, *, bind_interpreter=None, application_host=False, business_application=False, reference_application=False):
        self.configuration = configuration
        self.reference_application = reference_application
        self.definitions = _definitions(configuration)
        self.database = database
        self.bind_interpreter = bind_interpreter
        self.sessions = {}
        self.allocated = 0
        self.ready = False
        self.objects = {}
        self.records = {}
        self.record_keys = {}
        self.projections = {}
        self.record_context = None
        self.application = None
        self.application_invocation = None
        if application_host or business_application or reference_application:
            if bind_interpreter is not None:
                raise ValueError('application owns its interpreter family')
            context = None if database is None else SQLiteDBContext(database)
            try:
                self.application = _runtime(configuration, 'server', business_application=business_application, reference_application=reference_application, database_context=context, output=lambda value: None)
                self.record_context = context
                if self.application.server_endpoints:
                    self.application_invocation = InvocationServer.from_handlers(
                        self.application.server_endpoints, message_scope=self.application.event_messages)
            except BaseException:
                if context is not None: context.close()
                raise

    def _catalog(self, entry):
        definition = self.definitions.get(entry) if type(entry) is int else None
        if definition is None or (definition.catalog_schema is None and definition.document_schema is None) or self.database is None:
            raise ValueError('declared object form and active database required')
        if self.record_context is None:
            self.record_context = SQLiteDBContext(self.database)
        context = self.record_context
        context.require_active(tabular_sections=True)
        if context.backend.export_configuration() != dict(self.configuration.source_files):
            raise ValueError('configuration/database source mismatch')
        document = definition.document_schema
        view = context.backend.begin_read() if document is None else context.backend.begin_document_read()
        try:
            if (definition.catalog_schema not in view.catalogs() if document is None
                    else document not in view.documents()):
                raise ValueError('configuration/database schema mismatch')
        finally:
            view.close()
        return definition, context

    def _projection_preflight(self, entry, listing):
        document = self.definitions[entry].document_schema is not None
        cards = listing if document else listing.cards
        needed = {(entry, card.key if document else card.reference) for card in cards} - self.record_keys.keys()
        if len(cards) > 256 or len(self.record_keys) + len(needed) > 4096:
            raise ValueError('catalog capability limit')

    def _records(self, entry):
        from .catalog_view import CatalogRepository
        definition, context = self._catalog(entry)
        document = definition.document_schema
        if document is None:
            repository = CatalogRepository(context.backend, own_backend=False)
            try: listing = repository.load(str(definition.catalog_schema.identity))
            finally: repository.close()
        else:
            from ..document_backend import DocumentSelection
            view = context.backend.begin_document_read()
            try: listing = view.select_documents(document.identity, DocumentSelection())
            finally: view.close()
        try:
            self._projection_preflight(entry, listing)
        except ValueError:
            return {'error': 'catalog_limit'}
        rows = []
        for card in (listing if document is not None else listing.cards):
            identity = (entry, card.key if document is not None else card.reference)
            key = self.record_keys.get(identity)
            if key is None:
                if len(self.record_keys) >= 4096:
                    return {'error': 'catalog_limit'}
                key = 'record-' + str(len(self.record_keys) + 1)
                self.record_keys[identity] = key
                self.records[key] = identity
            if document is None:
                rows.append({'key': key, 'code': card.values[0], 'description': card.values[1],
                             'deletionMark': card.values[2]})
            else:
                rows.append({'key': key, 'number': card.number, 'date': card.date.isoformat(sep=' '),
                             'deletionMark': card.deletion_mark})
        previous = self.projections.get(entry)
        version = 1 if previous is None else previous['version'] + (previous['rows'] != rows)
        result = {'entry': entry, 'version': version, 'rows': rows}
        encode_line(result)
        self.projections[entry] = result
        return result

    def exchange(self, request):
        _keys(request, 'operation session payload')
        operation, sid, payload = request['operation'], request['session'], request['payload']
        if type(sid) is not str:
            raise ValueError('invalid session')
        if operation == 'hello':
            _keys(payload, 'source')
            if sid or payload['source'] != self.configuration.source_sha256:
                raise ValueError('configuration source mismatch')
            if not self.ready and self.application is not None:
                self.application.start()
            self.ready = True
            return {'source': self.configuration.source_sha256}
        if not self.ready:
            raise ValueError('configuration handshake required')
        if operation == 'applicationInvoke':
            if sid or self.application_invocation is None:
                raise ValueError('application invocation is unavailable')
            return decode_line(self.application_invocation.exchange(encode_line(payload)))
        if operation == 'applicationStop':
            if sid or payload != {} or self.sessions or self.application is None:
                raise ValueError('application cannot stop with open forms')
            return {'closed': self.application.close()}
        if operation == 'catalog':
            _keys(payload, 'entry')
            if sid:
                raise ValueError('catalog operation has no form session')
            try:
                return self._records(payload['entry'])
            except Exception:
                return {'error': 'catalog_unavailable'}
        if operation == 'create':
            _keys(payload, 'entry parameters record')
            entry = payload['entry']
            if sid or type(entry) is not int or entry not in self.definitions:
                raise ValueError('unknown form entry')
            if type(payload['parameters']) is not dict:
                raise ValueError('invalid form parameters')
            values = _parameters({key: _decode_scalar(value) for key, value in payload['parameters'].items()})
            if len(self.sessions) >= MAX_FORMS or self.allocated >= MAX_SESSIONS:
                return {'error': 'capacity'}
            record = payload['record']
            definition = self.definitions[entry]
            reference = None
            if record is not None:
                if type(record) is not str or record not in self.records or self.records[record][0] != entry:
                    return {'error': 'invalid_record'}
                reference = self.records[record][1]
            if definition.catalog_schema is None and definition.document_schema is None and record is not None:
                return {'error': 'invalid_record'}
            if definition.catalog_schema is not None or definition.document_schema is not None:
                self._catalog(entry)
            self.allocated += 1
            sid = 'form-' + str(self.allocated)
            context = None if self.database is None else SQLiteDBContext(self.database)
            server = nocontext = None
            try:
                definition = self.definitions[entry]
                owned = None
                if definition.catalog_schema is not None:
                    from ..configuration_catalog import CatalogObjectSession
                    owned = CatalogObjectSession(context, definition.catalog_schema,
                        dict(self.configuration.source_files), reference=reference, reference_fields=self.reference_application)
                elif definition.document_schema is not None:
                    from ..configuration_document import DocumentObjectSession
                    owned = DocumentObjectSession(context, definition.document_schema,
                        dict(self.configuration.source_files), key=reference, reference_fields=self.reference_application)
                if owned is not None:
                    owned.projection_preflight = lambda listing, entry=entry: self._projection_preflight(entry, listing)
                server = definition.create_server(parameters=values, database_context=context, object_session=owned,
                    interpreter_factory=None if self.application is None else self.application.form_interpreter_factory)
                program = definition.program
                if program.nocontext_bindings:
                    nocontext = InvocationServer(program.nocontext, program.nocontext_endpoints,
                        database_context=context,
                        interpreter_factory=None if self.application is None else self.application.interpreter_factory)
                if self.bind_interpreter is not None:
                    self.bind_interpreter(server.session.interpreter)
                    if nocontext is not None:
                        self.bind_interpreter(nocontext._interpreter)
                self.sessions[sid] = (server, nocontext, context)
                if owned is not None:
                    self.objects[sid] = owned
                return {'session': sid, 'entry': entry}
            except BaseException:
                for vm in (None if server is None else server.session.interpreter,
                           None if nocontext is None else nocontext._interpreter):
                    if vm is not None:
                        vm.close()
                if context is not None:
                    context.close()
                raise
        if sid not in self.sessions:
            raise ValueError('retired session')
        server, nocontext, context = self.sessions[sid]
        if operation == 'guardClose':
            if payload != {}:
                raise ValueError('invalid close guard')
            owned = self.objects.get(sid)
            return {'allowed': (owned is None or not (owned.pending_commit or owned.pending_refresh))
                    and (self.application is None or not self.application.interpreter.pending_promises)}
        if operation == 'reference':
            _keys(payload, 'action form')
            chooser = getattr(server, '_reference_choice', None)
            binding = next((b for b in server.bindings if b.name == 'YadinassiReferenceAction'), None)
            frame = payload['form']
            if (chooser is None or binding is None or type(payload['action']) is not dict
                    or type(frame) is not dict or frame.get('operation') != 'call'
                    or frame.get('endpoint') != binding.endpoint):
                raise ValueError('unknown reference capability')
            owned = self.objects.get(sid)
            owned.verify_source()
            chooser.pending = payload['action']
            try:
                response = decode_line(server.exchange(encode_line(frame)))
            finally:
                chooser.pending = None
            return {'form': response, 'choice': chooser.projection(),
                    'changed': chooser.changed_control, 'uncertain': chooser.uncertain}
        if operation == 'form':
            chooser = getattr(server, '_reference_choice', None)
            if chooser is not None and (chooser.active or chooser.uncertain):
                raise ValueError('finish owned reference selection before another form dispatch')
            if (payload.get('operation') in ('close', 'dispose') and self.application is not None
                    and self.application.interpreter.pending_promises):
                raise ValueError('application tasks must finish before releasing a form')
            owned = self.objects.get(sid)
            if owned is not None:
                owned.verify_source()
                if payload.get('operation') in ('close', 'dispose'):
                    owned.require_discardable()
            scope = (nullcontext() if self.application is None else
                     self.application.event_messages(server.session._record_message))
            with scope:
                return decode_line(server.exchange(encode_line(payload)))
        if operation == 'invoke':
            if nocontext is None:
                raise ValueError('NoContext channel unavailable')
            scope = (nullcontext() if self.application is None else
                     self.application.event_messages(nocontext._message))
            with scope:
                return decode_line(nocontext.exchange(encode_line(payload)))
        if operation == 'retire':
            if payload != {}:
                raise ValueError('invalid retirement')
            if self.application is not None and self.application.interpreter.pending_promises:
                raise ValueError('application tasks must finish before releasing a form')
            del self.sessions[sid]
            self.objects.pop(sid, None)
            try:
                server.session.interpreter.close()
            finally:
                try:
                    if nocontext is not None:
                        nocontext._interpreter.close()
                finally:
                    if context is not None:
                        context.close()
            return {}
        raise ValueError('unknown application operation')

    def close(self):
        failure = None
        if self.application is not None:
            self.application.close(force=True)
        for sid in list(self.sessions):
            try:
                self.exchange({'operation': 'retire', 'session': sid, 'payload': {}})
            except Exception as error:
                failure = error
        if self.record_context is not None:
            self.record_context.close()
            self.record_context = None
        if self.application is not None:
            self.application.close(force=True)
        if failure is not None:
            raise failure


class ConfigurationProcess(FormProcess):
    def __init__(self, root, database=None, *, catalog_objects=False, application_host=False, document_objects=False, business_application=False, reference_application=False):
        environment = dict(os.environ, PYTHONIOENCODING='utf-8')
        environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
        command = ([sys.executable, '--configuration-ui-runtime', str(Path(root).resolve())]
                   if getattr(sys, 'frozen', False) else
                   [sys.executable, '-m', 'yadinassi.ui.configuration_app', str(Path(root).resolve()), '--runtime'])
        if database is not None:
            command += ['--f', str(Path(database).resolve())]
        if catalog_objects:
            command += ['--catalog-objects']
        if application_host:
            command += ['--application-host']
        if business_application:
            command += ['--business-application']
        if reference_application:
            command += ['--reference-application']
        if document_objects:
            command += ['--document-objects']
        self._start(command, environment)


def serve_runtime(root, database=None, *, input_stream=None, output_stream=None, catalog_objects=False,
                  application_host=False, document_objects=False, business_application=False, reference_application=False):
    broker = None
    try:
        broker = ConfigurationBroker(load_application(root, catalog_objects=catalog_objects,
            application_host=application_host, document_objects=document_objects, business_application=business_application, reference_application=reference_application), database, application_host=application_host, business_application=business_application, reference_application=reference_application)
        source = sys.stdin.buffer if input_stream is None else input_stream
        target = sys.stdout.buffer if output_stream is None else output_stream
        last_id = 0
        while True:
            raw = source.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return 0
            request = decode_line(raw)
            _keys(request, 'id operation session payload')
            if type(request['id']) is not int or not last_id < request['id'] <= MAX_COUNTER:
                return 1
            last_id = request['id']
            try:
                result = broker.exchange({key: request[key] for key in ('operation', 'session', 'payload')})
                error = None
            except Exception:
                result, error = None, 'operation_failed'
            target.write(encode_line({'id': request['id'], 'session': request['session'],
                                      'result': result, 'error': error})); target.flush()
    except Exception:
        return 1
    finally:
        if broker is not None:
            broker.close()


class ConfigurationController:
    """Several forms, one serialized application queue; no nested event dispatch."""
    def __init__(self, configuration, exchange, *, initial_form=None, bind_interpreter=None,
                 application_host=False, business_application=False, reference_application=False):
        self.configuration = configuration
        self.reference_application = reference_application
        self.definitions = _definitions(configuration)
        self.names = {definition.name.casefold(): entry for entry, definition in self.definitions.items()}
        self.initial_entry = None if initial_form is None else self._entry(initial_form)
        self.transport = exchange
        self.bind_interpreter = bind_interpreter
        self.sessions = {}
        self.issued = set()
        self.operations = {}
        self.pending = deque()
        self.counter = 0
        self.opened = self.closed = self.uncertain = False
        self.active = None
        self.catalog = None
        self.choice = None
        self._reference_action = None
        self._reference_changed = None
        self.catalog_versions = {}
        self.gate = Lock()
        self.application = None
        self.application_messages = []
        self._dispatch_active = False
        if application_host or business_application or reference_application:
            if bind_interpreter is not None:
                raise ValueError('application owns its interpreter family')
            service = HostFunction('OpenForm', self._application_open_form, returns_value=False)
            self.application = _runtime(configuration, 'client', business_application=business_application, reference_application=reference_application, output=self._application_message,
                host_services={'OpenForm': service, 'ОткрытьФорму': service},
                server_exchange=lambda raw: encode_line(self._call('applicationInvoke', payload=decode_line(raw))))

    def _application_message(self, value):
        if type(value) is not str or len(value) > 4096 or len(self.application_messages) >= 64:
            raise ValueError('application message limit')
        self.application_messages.append(value)

    def _application_open_form(self, name, parameters=None):
        if (not self._dispatch_active or self.uncertain or self.application is None
                or self.application.state not in ('starting', 'running')):
            raise ValueError('OpenForm requires an active application client event')
        entry, values = self._entry(name), _parameters(parameters)
        if len(self.sessions) + len(self.pending) >= MAX_FORMS or len(self.issued) + len(self.pending) >= MAX_SESSIONS:
            raise ValueError('form capacity exhausted')
        self.pending.append((entry, values))

    def _form_exchange(self, controller, request):
        queued_before = len(self.pending)
        scope = (nullcontext() if self.application is None else
                 self.application.event_messages(controller.session._record_message))
        with scope:
            response = controller.exchange(request)
        if response['result']['error'] is not None:
            while len(self.pending) > queued_before: self.pending.pop()
        return response

    def idle_close(self):
        # Never discard an open form or retry an unknown request because its
        # renderer disappeared. Ordinary BeforeExit can still refuse a clean app.
        if not self.opened or self.sessions or self.uncertain or self.pending:
            return False
        return self.exchange({'jsonrpc':'2.0','id':1,'method':'application.close','params':{}})['result']['state']['kind'] == 'closed'

    def close(self):
        if self.application is not None:
            self.application.close(force=True)

    @staticmethod
    def _validate_choice(choice):
        if choice is None: return
        import re
        _keys(choice, 'ticket control row column title code rows error')
        if (type(choice['ticket']) is not str or not re.fullmatch('[0-9a-f]{32}', choice['ticket'])
                or type(choice['control']) is not str or len(choice['control']) > 128
                or choice['row'] is not None and (type(choice['row']) is not int or not 1 <= choice['row'] <= 4096)
                or choice['column'] is not None and (type(choice['column']) is not str or len(choice['column']) > 128)
                or type(choice['title']) is not str or len(choice['title']) > 1024
                or type(choice['code']) is not str or len(choice['code']) > 64
                or choice['error'] not in (None, 'too_many_matches')
                or type(choice['rows']) is not list or len(choice['rows']) > 32):
            raise ValueError('invalid bounded reference choice')
        tokens = set()
        for row in choice['rows']:
            _keys(row, 'choice code description')
            if (type(row['choice']) is not str or not re.fullmatch('[0-9a-f]{32}', row['choice'])
                    or row['choice'] in tokens or type(row['code']) is not str or len(row['code']) > 64
                    or type(row['description']) is not str or len(row['description']) > 1024):
                raise ValueError('invalid reference choice row')
            tokens.add(row['choice'])

    def _reference_request(self, params):
        _keys(params, 'session revision action')
        sid = params['session']
        if not self.reference_application or type(sid) is not str or sid not in self.sessions:
            raise ValueError('reference application session required')
        controller, entry = self.sessions[sid]
        if self.choice is not None and self.choice['session'] != sid:
            raise ValueError('finish another form reference selection')
        binding = next((b for b in self.definitions[entry].program.server_bindings
                        if b.name == 'YadinassiReferenceAction'), None)
        if binding is None or type(params['action']) is not dict:
            raise ValueError('reference form action required')
        if not controller._gate.acquire(blocking=False): raise ValueError('form busy')
        session = controller.session
        begun = False; error = None; queued_before = len(self.pending)
        try:
            session._begin(params['revision']); begun = True
            self._reference_changed = None
            self._reference_action = (sid, params['action'])
            scope = (nullcontext() if self.application is None else
                     self.application.event_messages(session._record_message))
            with scope:
                session._request('call', binding)
                changed = self._reference_changed
                if changed is not None:
                    item = session.form.items._values[changed['control'].casefold()]
                    if changed['row'] is not None:
                        # Match ordinary cell dispatch: CurrentData identifies
                        # the changed row, not the previously selected sibling.
                        item._table()._lookup_id(changed['row'])
                        item.current_row = changed['row']
                    if item.action: session._invoke(item.action, 'client', [item])
        except Exception:
            if session.uncertain or self.uncertain:
                self._lock(); error = 'outcome_unknown'
            else:
                error = 'reference_refused'
        finally:
            self._reference_action = None
            if begun:
                session.revision += 1; session._busy = False; session._gate.release()
            controller._gate.release()
        if error is not None:
            # Preserve the known applied value, but discard only opens queued
            # by the failed event, just like the ordinary form dispatch path.
            while len(self.pending) > queued_before: self.pending.pop()
        return sid, {'jsonrpc':'2.0','id':1,'result':{
            'protocol':FORM_PROTOCOL, 'state':controller._snapshot(), 'error':error}}, error

    def _entry(self, name):
        if type(name) is not str or len(name) > 256 or name.casefold() not in self.names:
            raise ValueError('unknown declared form')
        return self.names[name.casefold()]

    def _lock(self):
        self.uncertain = True
        self.pending.clear()
        for controller, _ in self.sessions.values():
            controller.session.uncertain = True

    def _call(self, operation, sid='', payload=None):
        if self.uncertain or self.counter >= MAX_COUNTER:
            raise LocalTransportError('unavailable')
        self.counter += 1
        try:
            response = decode_line(self.transport(encode_line({'id': self.counter, 'operation': operation,
                'session': sid, 'payload': {} if payload is None else payload})))
            _keys(response, 'id session result error')
            if (type(response['id']) is not int or response['id'] != self.counter or response['session'] != sid
                    or response['error'] not in (None, 'operation_failed')):
                raise ValueError('mismatched application response')
            if response['error'] is not None:
                # Creation may already have allocated resources. Never retry an
                # uncertain management operation or invent successful cleanup.
                raise ValueError('application operation failed')
            result = response['result']
            if type(result) is not dict:
                raise ValueError('invalid application result')
            if operation == 'hello':
                _keys(result, 'source')
                if result['source'] != self.configuration.source_sha256:
                    raise ValueError('configuration source mismatch')
            elif operation == 'create':
                if 'error' in result:
                    _keys(result, 'error')
                    if result['error'] not in ('capacity', 'invalid_record'):
                        raise ValueError('invalid capacity refusal')
                else:
                    _keys(result, 'session entry')
                    new = result['session']
                    if (type(new) is not str or not new.startswith('form-') or not new[5:].isdigit()
                            or len(new) > 12 or new in self.issued or type(result['entry']) is not int
                            or result['entry'] != payload['entry']):
                        raise ValueError('invalid new form identity')
            elif operation == 'catalog':
                if 'error' in result:
                    _keys(result, 'error')
                    if result['error'] not in ('catalog_limit', 'catalog_unavailable'):
                        raise ValueError('invalid catalog refusal')
                else:
                    _keys(result, 'entry version rows')
                    if (result['entry'] != payload['entry'] or type(result['entry']) is not int
                            or type(result['version']) is not int or result['version'] < 1
                            or result['version'] < self.catalog_versions.get(result['entry'], 0)
                            or type(result['rows']) is not list or len(result['rows']) > 256):
                        raise ValueError('invalid catalog projection')
                    seen = set()
                    document = self.definitions[result['entry']].document_schema
                    for row in result['rows']:
                        _keys(row, 'key number date deletionMark' if document else 'key code description deletionMark')
                        key = row['key']
                        if (type(key) is not str or not key.startswith('record-') or not key[7:].isascii()
                                or not key[7:].isdigit() or len(key) > 12 or key in seen
                                or type(row['deletionMark']) is not bool):
                            raise ValueError('invalid object record')
                        if document:
                            from datetime import datetime
                            if (type(row['number']) is not str or len(row['number']) > document.number_length
                                    or type(row['date']) is not str or len(row['date']) != 19
                                    or datetime.fromisoformat(row['date']).isoformat(sep=' ') != row['date']):
                                raise ValueError('invalid document record')
                        elif (type(row['code']) is not str or len(row['code']) > 64
                                or type(row['description']) is not str or len(row['description']) > 1024):
                            raise ValueError('invalid catalog record')
                        seen.add(key)
                    self.catalog_versions[result['entry']] = result['version']
            elif operation == 'reference':
                _keys(result, 'form choice changed uncertain')
                if type(result['uncertain']) is not bool:
                    raise ValueError('invalid reference outcome')
                self._validate_choice(result['choice'])
                changed = result['changed']
                if changed is not None:
                    _keys(changed, 'control row column')
                    if type(changed['control']) is not str or len(changed['control']) > 128 or (changed['row'] is not None and (type(changed['row']) is not int or not 1 <= changed['row'] <= 4096)) or changed['column'] is not None and (type(changed['column']) is not str or len(changed['column']) > 128):
                        raise ValueError('invalid changed reference control')
                self.choice = None if result['choice'] is None else dict(result['choice'], session=sid)
                self._reference_changed = changed
                if result['uncertain']: self._lock()
            elif operation == 'guardClose':
                _keys(result, 'allowed')
                if type(result['allowed']) is not bool:
                    raise ValueError('invalid close guard response')
            elif operation == 'retire' and result != {}:
                raise ValueError('invalid retirement')
            return result
        except BaseException:
            self._lock()
            raise LocalTransportError('unavailable') from None

    def _bind(self, sid, interpreter):
        if self.application is not None:
            self.application.bind_interpreter(interpreter)
            return
        def open_form(name, parameters=None):
            controller = self.sessions.get(sid, (None, None))[0]
            # The interpreter is bound before it opens, but the entry is retained
            # before OnOpen. No server or idle host call can enqueue client work.
            if (controller is None or not controller.session._busy or self.uncertain
                    or not interpreter._context_stack or interpreter._context_stack[-1] != 'client'):
                raise ValueError('OpenForm requires an active client form event')
            entry, values = self._entry(name), _parameters(parameters)
            if len(self.sessions) + len(self.pending) >= MAX_FORMS or len(self.issued) + len(self.pending) >= MAX_SESSIONS:
                raise ValueError('form capacity exhausted')
            self.pending.append((entry, values))
        for alias in ('OpenForm', 'ОткрытьФорму'):
            key = alias.casefold()
            if key in interpreter.routines or key in interpreter.server_routines or key in interpreter.functions:
                raise ValueError('reserved OpenForm alias')
            interpreter.functions[key] = HostFunction(alias, open_form, returns_value=False)
        if self.bind_interpreter is not None:
            self.bind_interpreter(interpreter)

    def _open(self, entry, parameters, record=None):
        if len(self.sessions) >= MAX_FORMS or len(self.issued) >= MAX_SESSIONS:
            return None, None, 'capacity'
        result = self._call('create', payload={'entry': entry,
            'parameters': {key: _encode_scalar(value) for key, value in parameters.items()}, 'record': record})
        if result.get('error'):
            return None, None, result['error']
        sid = result['session']; self.issued.add(sid)
        definition = self.definitions[entry]
        controller = None
        queued_before = len(self.pending)
        try:
            def exchange(raw):
                if self._reference_action is not None:
                    owner, action = self._reference_action
                    if owner != sid: raise ValueError('reference action owner mismatch')
                    self._reference_action = None
                    result = self._call('reference', sid, {'action': action, 'form': decode_line(raw)})
                    return encode_line(result['form'])
                return encode_line(self._call('form', sid, decode_line(raw)))
            reference_scope = None
            if definition.reference_targets:
                from ..form_references import FormReferenceScope
                reference_scope = FormReferenceScope(targets={i: n for i, _, n in definition.reference_targets})
            controller = FormController(definition.client_package(), exchange, parameters=parameters, reference_scope=reference_scope,
                bind_interpreter=lambda vm: self._bind(sid, vm),
                interpreter_factory=None if self.application is None else self.application.form_interpreter_factory)
            self.sessions[sid] = (controller, entry)
            if definition.program.nocontext_bindings:
                port = InvocationPort(lambda raw: encode_line(self._call('invoke', sid, decode_line(raw))))
                for binding in definition.program.nocontext_bindings:
                    controller.session.bind_nocontext(port, binding)
            form = self._form_exchange(controller, {'jsonrpc': '2.0', 'id': 1, 'method': 'form.hello',
                                        'params': {'protocol': FORM_PROTOCOL}})
            if controller.session.uncertain:
                self._lock()
            if form['result']['error'] or controller.session.closed:
                raise ValueError('form opening refused')
            self.active = sid
            return sid, form, None
        except Exception:
            while len(self.pending) > queued_before:
                self.pending.pop()
            if controller is not None and controller.session.uncertain:
                self._lock()
            if not self.uncertain:
                self._call('retire', sid)
                self.sessions.pop(sid, None)
                if controller is not None:
                    controller.session.interpreter.close()
            return None, None, 'open_failed'

    def _drain(self):
        error = None
        # Capacity bounds even OnOpen -> OpenForm recursion. Each admission has
        # a fresh identity and completed lifecycle before another form opens.
        while self.pending and not self.uncertain:
            entry, values = self.pending.popleft()
            _, _, failed = self._open(entry, values)
            if failed:
                error = failed
        return error

    def _state(self):
        return {'kind': 'closed' if self.closed else 'application', 'title': self.configuration.title,
                'entries': [{'id': entry, 'title': definition.title,
                             'kind': ('document-object' if definition.document_schema is not None else
                                      'form' if definition.catalog_schema is None else 'catalog-object')} for entry, definition in self.definitions.items()],
                'sessions': [{'id': sid, 'entry': entry, 'title': controller.session.form.title or self.definitions[entry].title}
                             for sid, (controller, entry) in self.sessions.items()],
                'active': self.active, 'uncertain': self.uncertain, 'catalog': self.catalog,
                **({'choice': self.choice} if self.reference_application else {}),
                'lifecycle': 'forms' if self.application is None else self.application.state,
                'messages': list(self.application_messages),
                'exitWarning': '' if self.application is None else self.application.last_exit_warning}

    def exchange(self, request):
        if not self.gate.acquire(blocking=False):
            raise LocalTransportError('busy')
        self._dispatch_active = True
        try:
            _keys(request, 'jsonrpc id method params')
            if (request['jsonrpc'] != '2.0' or type(request['id']) is not int
                    or not 1 <= request['id'] <= MAX_COUNTER or type(request['params']) is not dict):
                raise ValueError('invalid renderer request')
            method, params = request['method'], request['params']
            error = None; sid = None; form = None
            if self.closed:
                error = 'closed'
            elif self.uncertain:
                error = 'outcome_unknown'
            elif method == 'application.hello':
                if params != {'protocol': PROTOCOL}:
                    raise ValueError('invalid application handshake')
                if not self.opened:
                    self.opened = True
                    self._call('hello', payload={'source': self.configuration.source_sha256})
                    if self.application is not None:
                        self.application_messages.clear()
                        try:
                            with self.application.event_messages(self._application_message):
                                started = self.application.start()
                            if not started:
                                self.pending.clear()
                                self._call('applicationStop')
                                self.closed = True
                                error = 'startup_cancelled'
                        except Exception:
                            self.pending.clear(); self._lock(); error = 'startup_failed'
                    if self.initial_entry is not None and not self.closed and not self.uncertain:
                        sid, form, error = self._open(self.initial_entry, {})
            elif not self.opened:
                raise ValueError('application handshake required')
            elif method == 'application.catalog':
                _keys(params, 'entry')
                entry = params['entry']
                if type(entry) is not int or entry not in self.definitions or (self.definitions[entry].catalog_schema is None and self.definitions[entry].document_schema is None):
                    raise ValueError('unknown record entry')
                projected = self._call('catalog', payload={'entry': entry})
                error = projected.get('error')
                self.catalog = None if error else projected
            elif method in ('application.open', 'application.openRecord'):
                _keys(params, 'entry request record' if method.endswith('openRecord') else 'entry request')
                entry, token = params['entry'], params['request']
                if (type(entry) is not int or entry not in self.definitions or type(token) is not str
                        or not 1 <= len(token) <= 64 or not token.isascii()):
                    raise ValueError('invalid form open intent')
                record = params.get('record')
                if method.endswith('openRecord') and (
                        type(record) is not str or self.catalog is None or self.catalog['entry'] != entry
                        or not any(row['key'] == record for row in self.catalog['rows'])):
                    raise ValueError('record is not in the selected catalog projection')
                intent = (entry, record)
                if token in self.operations:
                    previous, sid, error = self.operations[token]
                    if previous != intent:
                        raise ValueError('open intent reused')
                    if sid is not None and sid not in self.sessions:
                        sid, error = None, 'retired_session'
                elif len(self.operations) >= MAX_SESSIONS:
                    error = 'capacity'
                else:
                    sid, form, error = self._open(entry, {}, record)
                    self.operations[token] = (intent, sid, error)
            elif method == 'application.reference':
                sid, form, error = self._reference_request(params)
                # OnChange may synchronously persist an object even if a later
                # callback statement fails. Reconcile, never replay that write.
                if not self.uncertain and self.catalog is not None:
                    projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                    projection_error = projection.get('error')
                    self.catalog = None if projection_error else projection
                    error = error or projection_error
            elif method == 'application.form':
                _keys(params, 'session request')
                sid = params['session']
                if type(sid) is not str or sid not in self.sessions:
                    error = 'retired_session'
                else:
                    controller, entry = self.sessions[sid]
                    nested_request = params['request']
                    if (self.choice is not None and self.choice['session'] == sid
                            and (type(nested_request) is not dict or nested_request.get('method') not in ('form.hello', 'form.snapshot'))):
                        raise ValueError('finish reference selection first')
                    closing = (type(nested_request) is dict and nested_request.get('method') == 'form.event'
                               and type(nested_request.get('params')) is dict and nested_request['params'].get('event') == 'close')
                    blocked = (closing and ((self.application is not None
                                  and self.application.interpreter.pending_promises)
                               or ((self.definitions[entry].catalog_schema is not None or self.definitions[entry].document_schema is not None or self.application is not None)
                                  and not self._call('guardClose', sid)['allowed'])))
                    if blocked:
                        error = 'save_recovery_required'
                        form = self._form_exchange(controller, {'jsonrpc': '2.0', 'id': nested_request['id'],
                            'method': 'form.snapshot', 'params': {}})
                        form['result']['error'] = 'busy'
                    else:
                        form = self._form_exchange(controller, nested_request)
                    if controller.session.uncertain:
                        self._lock()
                    elif self.catalog is not None:
                        projection = self._call('catalog', payload={'entry': self.catalog['entry']})
                        projection_error = projection.get('error')
                        self.catalog = None if projection_error else projection
                        error = error or projection_error
                    if not controller.session.uncertain and controller.session.closed:
                        self._call('retire', sid)
                        del self.sessions[sid]
                        if self.active == sid:
                            self.active = next(reversed(self.sessions), None)
                        controller.session.interpreter.close()
            elif method == 'application.snapshot':
                if params:
                    raise ValueError('invalid snapshot request')
            elif method == 'application.close':
                if params:
                    raise ValueError('invalid shutdown request')
                if self.sessions:
                    error = 'forms_open'
                else:
                    if self.application is not None:
                        self.application_messages.clear()
                        with self.application.event_messages(self._application_message):
                            accepted = self.application.close()
                        if accepted:
                            if self._call('applicationStop') != {'closed': True}:
                                raise ValueError('server application did not stop')
                            self.closed = True
                        else:
                            error = 'exit_cancelled'
                    else:
                        self.closed = True
            else:
                raise ValueError('unknown application method')
            queued_error = self._drain()
            result = {'protocol': PROTOCOL, 'state': self._state(), 'error': error or queued_error,
                      'session': sid, 'form': form}
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
            try:
                encode_line(response)
            except Exception:
                self._lock()
                raise LocalTransportError('unavailable') from None
            return response
        finally:
            self._dispatch_active = False
            self.gate.release()


class ConfigurationHandler(_Handler):
    asset_directory = 'configuration'
    methods = ('application.hello', 'application.snapshot', 'application.open',
               'application.form', 'application.close', 'application.catalog', 'application.openRecord', 'application.reference')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run trusted configuration-declared managed forms.')
    parser.add_argument('configuration', metavar='CONFIGURATION_DIRECTORY')
    parser.add_argument('--form', help='Declared form name to open initially')
    parser.add_argument('--f', help='Existing SQLite database, server process only')
    parser.add_argument('--open-browser', action='store_true')
    parser.add_argument('--catalog-objects', action='store_true', help='Explicit scalar catalog object forms profile')
    parser.add_argument('--document-objects', action='store_true', help='Explicit non-posting document Object forms with bounded sections')
    parser.add_argument('--reference-application', action='store_true', help='Explicit typed catalog-reference application profile')
    parser.add_argument('--business-application', action='store_true', help='Explicit mixed catalog/document application profile')
    parser.add_argument('--application-host', action='store_true', help='Explicit application/CommonModules and declared forms profile')
    parser.add_argument('--browser-session', action='store_true', help='Single writer attachment, reconnect and safe idle lifetime')
    parser.add_argument('--runtime', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sum((args.catalog_objects, args.application_host, args.document_objects, args.business_application, args.reference_application)) > 1:
        parser.error('choose one explicit configuration source profile')
    if (args.document_objects or args.business_application or args.reference_application) and args.f is None:
        parser.error('document applications require --f with an existing explicitly created database')
    if args.runtime:
        return serve_runtime(args.configuration, args.f, catalog_objects=args.catalog_objects, application_host=args.application_host, document_objects=args.document_objects, business_application=args.business_application, reference_application=args.reference_application)
    process = server = controller = None
    try:
        configuration = load_application(args.configuration, catalog_objects=args.catalog_objects, application_host=args.application_host, document_objects=args.document_objects, business_application=args.business_application, reference_application=args.reference_application)
        process = ConfigurationProcess(args.configuration, args.f, catalog_objects=args.catalog_objects, application_host=args.application_host, document_objects=args.document_objects, business_application=args.business_application, reference_application=args.reference_application)
        controller = ConfigurationController(configuration, process.exchange, initial_form=args.form, application_host=args.application_host, business_application=args.business_application, reference_application=args.reference_application)
        server = LocalUIServer(controller, handler=ConfigurationHandler,
            browser_session=args.browser_session or args.application_host or args.document_objects or args.business_application or args.reference_application, idle_close=controller.idle_close)
        print('Trusted configuration forms. Open this private per-launch URL:')
        print(server.launch_url, flush=True)
        if args.open_browser:
            webbrowser.open(server.launch_url)
        server.serve_forever(poll_interval=0.1)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('Configuration forms unavailable.', file=sys.stderr)
        return 1
    finally:
        try:
            if server is not None:
                server.server_close()
        finally:
            if process is not None:
                process.close()
            if controller is not None:
                controller.close()


if __name__ == '__main__':
    raise SystemExit(main())
