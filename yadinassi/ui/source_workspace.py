"""Explicit memory-only source workspace. Inventory is not a CRUD grant."""
import json
from threading import Lock

from ..errors import BSLError
from ..source_forms import SourceFormController
from .local_app import _Handler

PROTOCOL = 'yadinassi-source-workspace/1'
MAX_OPEN_FORMS = 8


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
        self.next_generation = 0
        self.open_forms = {}
        self.selected = None
        self.error = None
        self.query = ''
        self.object_query = ''
        self.object_family = ''
        self.object_selected = None
        inventory = application.metadata._inventory
        def full_name(entry):
            parent_path = entry.path.rsplit('/', 2)[0] + '.xml'
            parent = inventory.get(parent_path)
            own = entry.family + '.' + entry.name
            return full_name(parent) + '.' + own if parent is not None else own
        self.objects = {}
        object_names = set()
        for entry in inventory.values():
            name = full_name(entry)
            if name.casefold() in object_names:
                raise ValueError('ambiguous metadata full name: '+name[:256])
            object_names.add(name.casefold())
            self.objects[name] = entry
        self.object_families, self.omitted_families = self._bounded_names(sorted({entry.family for entry in inventory.values()}), 8192)
        self.forms = tuple(sorted(full_name(entry) for entry in inventory.values()
                                  if entry.family in ('Form', 'CommonForm')))

    @staticmethod
    def _live(form):
        return not form.client.session.closed or form.client.session.uncertain

    def _active(self):
        return self.form is not None and self._live(self.form)

    def _any_active(self):
        return any(self._live(form) for _, form in self.open_forms.values())

    def _select(self, generation):
        self.generation = generation
        self.selected, self.form = self.open_forms[generation]

    def visible_forms(self):
        matches = [name for name in self.forms if self.query.casefold() in name.casefold()]
        visible, size = [], 0
        for name in matches:
            cost = len(json.dumps(name, ensure_ascii=False).encode('utf-8')) + 1
            if len(visible) >= 512 or size + cost > 32768:
                break
            visible.append(name); size += cost
        return visible, len(matches)-len(visible)

    @staticmethod
    def _bounded_names(names, budget=16384):
        visible, size = [], 0
        for name in names:
            cost = len(json.dumps(name, ensure_ascii=False).encode('utf-8')) + 1
            if len(visible) >= 256 or size + cost > budget:
                break
            visible.append(name); size += cost
        return visible, len(names)-len(visible)

    def object_inventory(self):
        names = sorted(name for name, entry in self.objects.items()
                       if (not self.object_family or entry.family == self.object_family)
                       and self.object_query.casefold() in name.casefold())
        visible, omitted = self._bounded_names(names)
        return visible, omitted

    def object_detail(self):
        if self.object_selected is None:
            return None
        name = self.object_selected
        entry = self.objects[name]
        related = sorted(form for form in self.forms if form == name or form.startswith(name+'.Form.'))
        forms, omitted = self._bounded_names(related, 8192)
        return {'name': name, 'family': entry.family, 'source_path': entry.path,
                'forms': forms, 'omitted_forms': omitted,
                'execution': 'explicit_form_selection' if related else 'metadata_only',
                'storage_granted': False}

    def snapshot(self):
        visible, omitted = self.visible_forms()
        objects, object_omitted = self.object_inventory()
        return {'protocol': PROTOCOL, 'state': {'kind': 'closed' if self.closed else 'workspace',
                'name': self.application.source.name, 'forms': visible,
                'omitted_forms': omitted, 'query': self.query, 'selected': self.selected,
                'generation': self.generation, 'active': self._active(), 'error': self.error,
                'form_diagnostics': list(self.form.diagnostics) if self.form else [],
                'open_forms': [{'generation': generation, 'name': name, 'active': self._live(form)}
                               for generation, (name, form) in self.open_forms.items()],
                'form_limit': MAX_OPEN_FORMS, 'any_active': self._any_active(),
                'objects': objects, 'omitted_objects': object_omitted,
                'object_query': self.object_query, 'object_family': self.object_family,
                'object_families': self.object_families, 'omitted_families': self.omitted_families, 'object_detail': self.object_detail(),
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
            if set(params) != {'name'} or type(params['name']) is not str or params['name'] not in self.visible_forms()[0] and params['name'] not in (self.object_detail() or {}).get('forms', []):
                raise ValueError('declared workspace form required')
            existing = next((generation for generation, (name, form) in self.open_forms.items()
                             if name == params['name'] and self._live(form)), None)
            if existing is not None:
                self._select(existing)
            elif sum(self._live(form) for _, form in self.open_forms.values()) >= MAX_OPEN_FORMS:
                self.error = 'Достигнут предел открытых форм: 8. Закройте одну из форм.'
            else:
                try:
                    form = SourceFormController(self.application, params['name'], progressive=True)
                except (BSLError, ValueError, TypeError, RecursionError) as error:
                    self.error = str(error)[:4096]
                else:
                    self.open_forms = {key: value for key, value in self.open_forms.items() if self._live(value[1])}
                    self.next_generation += 1
                    self.open_forms[self.next_generation] = (params['name'], form)
                    self._select(self.next_generation)
        elif method == 'workspace.select':
            if (set(params) != {'generation'} or type(params['generation']) is not int
                    or params['generation'] not in self.open_forms):
                raise ValueError('unknown workspace form')
            self._select(params['generation'])
        elif method == 'workspace.objects':
            if (set(params) != {'query', 'family'} or type(params['query']) is not str
                    or len(params['query']) > 128 or type(params['family']) is not str
                    or params['family'] not in ('', *self.object_families)):
                raise ValueError('invalid object search')
            self.object_query, self.object_family = params['query'], params['family']
        elif method == 'workspace.inspect':
            if (set(params) != {'name'} or type(params['name']) is not str
                    or params['name'] not in self.object_inventory()[0]):
                raise ValueError('declared visible object required')
            self.object_selected = params['name']
        elif method == 'workspace.search':
            if set(params) != {'query'} or type(params['query']) is not str or len(params['query']) > 128:
                raise ValueError('invalid form search')
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
                if self._any_active():
                    self.error = 'Сначала закройте все открытые формы.'
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
    methods = ('workspace.snapshot','workspace.open','workspace.search','workspace.objects','workspace.inspect','workspace.select','workspace.form','workspace.close')
