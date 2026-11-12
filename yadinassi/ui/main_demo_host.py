"""One exact database, one active UI owner, epoch-fenced surface dispatch.

Switching is navigation, never an implicit save/discard or a retry. Original
catalog forms and document forms retain separate protocols and authority.
"""
from threading import Lock
from uuid import uuid4

from ..database_context import SQLiteDBContext
from .database_launch import verify_binding
from .main_demo import require_backend, document_forms
from .protocol import MAX_COUNTER, encode_line, decode_line

PROTOCOL = 'yadinassi-main-demo/1'
SURFACES = ('catalogs', 'documents')


class MainDemoHost:
    def __init__(self, database, expected_binding):
        self.database = database
        self.binding = expected_binding
        self.surface = None
        self.epoch = None
        self.owner = self.broker = self.session = None
        self._retired = []
        self.closed = False
        self.unknown = False
        self.gate = Lock()
        self._activate('catalogs')

    def _activate(self, surface):
        context = SQLiteDBContext(self.database)
        try:
            verify_binding(context.backend, self.binding, route='main-demo')
            configuration = require_backend(context.backend)
            if surface == 'catalogs':
                from .catalog_editor import CatalogEditorApplication
                from .editor_protocol import CatalogEditorSession
                owner = CatalogEditorApplication(context)
                session = CatalogEditorSession(owner)
                broker = None
                context = None  # CatalogEditorApplication owns it.
            else:
                from .configuration_app import ConfigurationBroker, ConfigurationController
                forms = document_forms(configuration)
                context.close(); context = None
                broker = ConfigurationBroker(forms, self.database, main_demo_application=True,
                    launch_binding=self.binding, launch_route='main-demo')
                def exchange(raw):
                    request = decode_line(raw)
                    result = broker.exchange({k:request[k] for k in ('operation','session','payload')})
                    return encode_line({'id':request['id'],'session':request['session'],'result':result,'error':None})
                try:
                    owner = ConfigurationController(forms, exchange, main_demo_application=True)
                except BaseException:
                    broker.close()
                    raise
                session = owner
            self.owner, self.session, self.broker = owner, session, broker
            self.surface, self.epoch = surface, uuid4().hex
        finally:
            if context is not None: context.close()

    def _can_leave(self):
        if self.closed or self.unknown or self.owner is None:
            return False
        if self.surface == 'catalogs':
            return (not self.owner.closed and self.owner.editor is None
                    and self.owner._reference_chooser is None)
        owner = self.owner
        # operations retains open-intent replay receipts after session retirement.
        # It is history, not live work; sessions/pending/uncertain fence live owners.
        return not (owner.closed or owner.uncertain or owner.sessions or owner.pending
                    or owner.choice or owner.dialogs or owner.inputs
                    or owner._dispatch_active)

    def _retire(self):
        resources = self._retired + [resource for resource in (self.owner, self.broker)
                                     if resource is not None]
        self.owner = self.broker = self.session = None
        # Retire authority immediately. Failed resources remain cleanup-only,
        # never eligible for dispatch, activation or replay on shutdown retry.
        self.epoch = None
        self._retired = []
        failure = None
        for resource in resources:
            try:
                resource.close()
            except BaseException as error:
                self._retired.append(resource)
                if failure is None: failure = error
        if failure is not None: raise failure

    def _state(self):
        return {'kind':'closed' if self.closed else 'main-demo',
                'surface':self.surface, 'epoch':self.epoch,
                'canSwitch':self._can_leave(), 'uncertain':self.unknown}

    def exchange(self, request):
        if not self.gate.acquire(blocking=False):
            raise ValueError('main demo dispatch busy')
        try:
            if (type(request) is not dict or set(request) != {'jsonrpc','id','method','params'}
                    or request['jsonrpc'] != '2.0' or type(request['id']) is not int
                    or not 1 <= request['id'] <= MAX_COUNTER or type(request['params']) is not dict):
                raise ValueError('invalid main demo message')
            method, params = request['method'], request['params']
            error = payload = None
            if method in ('demo.hello','demo.snapshot'):
                if params != {'protocol':PROTOCOL}: raise ValueError('invalid main demo protocol')
            elif self.closed:
                error = 'closed'
            elif method in ('demo.select','demo.dispatch','demo.close'):
                keys = {'epoch'} | ({'surface'} if method == 'demo.select' else {'request'} if method == 'demo.dispatch' else set())
                if set(params) != keys: raise ValueError('invalid main demo parameters')
                if type(params['epoch']) is not str or params['epoch'] != self.epoch:
                    error = 'stale_surface'
                elif method == 'demo.select':
                    if type(params['surface']) is not str or params['surface'] not in SURFACES: raise ValueError('unknown surface')
                    if not self._can_leave(): error = 'finish_current_surface'
                    elif params['surface'] != self.surface:
                        try:
                            self._retire()
                            self._activate(params['surface'])
                        except BaseException:
                            self.unknown = True
                            raise
                elif method == 'demo.close':
                    if not self._can_leave(): error = 'finish_current_surface'
                    else:
                        self.closed = True
                        self._retire()
                else:
                    nested = params['request']
                    prefix = 'editor.' if self.surface == 'catalogs' else 'application.'
                    if (type(nested) is not dict or type(nested.get('method')) is not str
                            or not nested['method'].startswith(prefix)):
                        raise ValueError('wrong surface protocol')
                    payload = (decode_line(self.session.exchange(encode_line(nested)))
                               if self.surface == 'catalogs' else self.session.exchange(nested))
                    if payload.get('result',{}).get('state',{}).get('kind') == 'closed':
                        self.closed = True
                        self._retire()
            else:
                raise ValueError('unknown main demo method')
            response = {'jsonrpc':'2.0','id':request['id'], 'result':{
                'protocol':PROTOCOL,'state':self._state(),'error':error,'payload':payload}}
            encode_line(response)
            return response
        finally:
            self.gate.release()

    def idle_close(self):
        if not self.gate.acquire(blocking=False): return False
        try:
            if not self._can_leave(): return False
            self.closed = True
            self._retire()
            return True
        finally: self.gate.release()

    def close(self):
        self.closed = True
        self._retire()
