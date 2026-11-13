"""Explicit memory-only source workspace. Inventory is not a CRUD grant."""
import json
from threading import Lock

from ..errors import BSLError
from ..source_forms import SourceFormController
from .local_app import _Handler

PROTOCOL = 'yadinassi-source-workspace/1'


class SourceWorkspace:
    def __init__(self, application):
        application.require_open()
        if application.constant_store is not None:
            raise ValueError('source workspace requires memory-only startup')
        self.gate = Lock()
        self.application = application
        self.closed = False
        self.form = None
        self.generation = 0
        self.selected = None
        self.error = None
        self.query = ''
        inventory = application.metadata._inventory
        def full_name(entry):
            parent_path = entry.path.rsplit('/', 2)[0] + '.xml'
            parent = inventory.get(parent_path)
            own = entry.family + '.' + entry.name
            return full_name(parent) + '.' + own if parent is not None else own
        self.forms = tuple(sorted(full_name(entry) for entry in inventory.values()
                                  if entry.family in ('Form', 'CommonForm')))

    def _active(self):
        return self.form is not None and (not self.form.client.session.closed or self.form.client.session.uncertain)

    def visible_forms(self):
        matches = [name for name in self.forms if self.query.casefold() in name.casefold()]
        visible, size = [], 0
        for name in matches:
            cost = len(json.dumps(name, ensure_ascii=False).encode('utf-8')) + 1
            if len(visible) >= 512 or size + cost > 32768:
                break
            visible.append(name); size += cost
        return visible, len(matches)-len(visible)

    def snapshot(self):
        visible, omitted = self.visible_forms()
        return {'protocol': PROTOCOL, 'state': {'kind': 'closed' if self.closed else 'workspace',
                'name': self.application.source.name, 'forms': visible,
                'omitted_forms': omitted, 'query': self.query, 'selected': self.selected,
                'generation': self.generation, 'active': self._active(), 'error': self.error,
                'form_diagnostics': list(self.form.diagnostics) if self.form else [],
                'memory_only': True, 'native_parity': False}}

    def exchange(self, request):
        if not self.gate.acquire(blocking=False):
            raise ValueError('source workspace busy')
        try:
            return self._exchange(request)
        finally:
            self.gate.release()

    def _exchange(self, request):
        if (type(request) is not dict or set(request) != {'jsonrpc','id','method','params'}
                or request['jsonrpc'] != '2.0' or type(request['id']) is not int
                or type(request['params']) is not dict):
            raise ValueError('invalid workspace request')
        method, params = request['method'], request['params']
        if self.closed and method != 'workspace.snapshot':
            raise ValueError('source workspace closed')
        self.error = None
        if method == 'workspace.open':
            if set(params) != {'name'} or type(params['name']) is not str or params['name'] not in self.visible_forms()[0]:
                raise ValueError('declared workspace form required')
            if self._active():
                self.error = 'Сначала закройте открытую форму. Несохранённые изменения не будут отброшены.'
            else:
                try:
                    form = SourceFormController(self.application, params['name'], progressive=True)
                except (BSLError, ValueError, TypeError, RecursionError) as error:
                    self.error = str(error)[:4096]
                else:
                    self.form, self.selected = form, params['name']
                    self.generation += 1
        elif method == 'workspace.search':
            if set(params) != {'query'} or type(params['query']) is not str or len(params['query']) > 128:
                raise ValueError('invalid form search')
            if self._active():
                self.error = 'Сначала закройте открытую форму.'
            else:
                self.query = params['query']
        elif method == 'workspace.form':
            if (set(params) != {'generation','request'} or type(params['generation']) is not int
                    or params['generation'] != self.generation or self.form is None):
                raise ValueError('stale workspace form')
            result = self.form.exchange(params['request'])
            return {'jsonrpc':'2.0','id':request['id'],'result':result}
        elif method in ('workspace.close','workspace.snapshot'):
            if params: raise ValueError('invalid workspace parameters')
            if method == 'workspace.close':
                if self._active():
                    self.error = 'Сначала закройте открытую форму.'
                else:
                    self._close()
        else:
            raise ValueError('invalid workspace method')
        return {'jsonrpc':'2.0','id':request['id'],'result':self.snapshot()}

    def close(self):
        with self.gate:
            self._close()

    def _close(self):
        self.closed = True
        self.application.close()


class SourceWorkspaceHandler(_Handler):
    asset_directory = 'source-workspace'
    methods = ('workspace.snapshot','workspace.open','workspace.search','workspace.form','workspace.close')
