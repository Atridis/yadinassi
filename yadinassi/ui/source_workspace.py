"""Explicit memory-only source workspace. Inventory is not a CRUD grant."""
import json
from threading import Lock

from ..errors import BSLError
from ..source_forms import SourceFormController
from .local_app import _Handler

PROTOCOL = 'yadinassi-source-workspace/1'
MAX_OPEN_FORMS = 8
MAX_NAVIGATION_LABEL = 256
MAX_SUBSYSTEM_MEMBERS = 2048
MAX_NAVIGATION_MEMBERS = 32768


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
        self.pending_navigation = []
        self.navigation_total = 0
        self.navigation_event = None
        self.selected = None
        self.error = None
        self.query = ''
        self.object_query = ''
        self.object_family = ''
        self.object_subsystem = ''
        self.object_selected = None
        self.default_form_cache = {}
        self.form_preview = None
        self.module_preflight = None
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
        self._prepare_navigation()

    def _navigation_diagnostic(self, name, reason):
        message = name[:160] + ': ' + reason
        if len(self.navigation_diagnostics) < 16:
            self.navigation_diagnostics.append(message[:256])
        else:
            self.omitted_navigation_diagnostics += 1

    def _prepare_navigation(self):
        """Presentation from admitted XML; direct membership is not authority.

        Parent subsystem selection does not union child subsystem contents.
        Unknown/ambiguous Content invalidates that subsystem's whole filter,
        rather than inventing a group or silently accepting a partial one.
        """
        from ..configuration_source_metadata import SourceMetadataObject
        from ..configuration_xml import MD, XR, XSI
        v8 = '{http://v8.1c.ru/8.1/data/core}'
        md = '{' + MD + '}'
        self.navigation_labels = {name: entry.name for name, entry in self.objects.items()}
        self.navigation_diagnostics = []
        self.omitted_navigation_diagnostics = 0
        self.subsystems, self.omitted_subsystems = self._bounded_names(
            sorted(name for name, entry in self.objects.items() if entry.family == 'Subsystem'), 4096)
        self.subsystem_members = {name: frozenset() for name in self.subsystems}
        membership_total = 0
        for name, entry in self.objects.items():
            metadata = SourceMetadataObject(self.application.metadata, entry)
            properties = metadata._object().find(md + 'Properties')
            self.navigation_labels[name] = entry.name
            synonyms = properties.findall(md + 'Synonym') if properties is not None else []
            if synonyms:
                try:
                    if len(synonyms) != 1 or synonyms[0].attrib or (synonyms[0].text or '').strip():
                        raise ValueError('malformed synonym')
                    russian = []
                    for item in synonyms[0]:
                        langs, texts = item.findall(v8 + 'lang'), item.findall(v8 + 'content')
                        if (item.tag != v8 + 'item' or item.attrib or (item.text or '').strip()
                                or len(langs) != 1 or len(texts) != 1 or len(item) != 2
                                or len(langs[0]) or len(texts[0]) or langs[0].attrib or texts[0].attrib):
                            raise ValueError('malformed localized synonym')
                        if (langs[0].text or '').strip().lower() == 'ru':
                            russian.append(texts[0].text or '')
                    if len(russian) > 1: raise ValueError('ambiguous Russian synonym')
                    if russian:
                        label = ' '.join(russian[0].split())
                        if not label or len(label) > MAX_NAVIGATION_LABEL:
                            raise ValueError('Russian synonym length bound')
                        self.navigation_labels[name] = label
                except ValueError as error:
                    self._navigation_diagnostic(name, str(error))
            if name not in self.subsystem_members:
                continue
            content = properties.findall(md + 'Content') if properties is not None else []
            try:
                if not content:
                    continue  # No declared members means an empty direct group.
                if len(content) != 1 or content[0].attrib or (content[0].text or '').strip():
                    raise ValueError('malformed subsystem Content')
                membership_total += len(content[0])
                if len(content[0]) > MAX_SUBSYSTEM_MEMBERS or membership_total > MAX_NAVIGATION_MEMBERS:
                    raise ValueError('subsystem membership bound')
                members = set()
                for item in content[0]:
                    qname = item.get('{' + XSI + '}type', '').split(':')
                    prefix, local = qname if len(qname) == 2 else ('', qname[0])
                    reference = item.text or ''
                    if (item.tag != '{' + XR + '}Item' or len(item)
                            or set(item.attrib) != {'{' + XSI + '}type'}
                            or len(qname) > 2 or local != 'MDObjectRef'
                            or metadata._namespaces[item].get(prefix) != XR
                            or (item.tail or '').strip()):
                        raise ValueError('unsupported subsystem reference')
                    if reference not in self.objects:
                        raise ValueError('undeclared subsystem reference')
                    if reference in members:
                        raise ValueError('duplicate subsystem reference')
                    members.add(reference)
                self.subsystem_members[name] = frozenset(members)
            except ValueError as error:
                self._navigation_diagnostic(name, str(error))

    def _labels(self, names, budget=8192):
        labels, size = {}, 2
        for name in names:
            label = self.navigation_labels.get(name, name)
            cost = len(json.dumps({name: label}, ensure_ascii=False).encode('utf-8'))
            if size + cost > budget:
                continue  # Missing labels explicitly fall back to canonical names.
            labels[name] = label; size += cost
        return labels

    @classmethod
    def start(cls, application):
        """Queue startup UI intent; create forms only after successful startup.

        This opt-in host belongs only to the memory-only workspace. Headless and
        explicitly selected single-form startup remain unchanged.
        """
        if application.state != 'prepared' or application.constant_store is not None:
            raise ValueError('fresh memory-only source application required')
        pending = []
        accepting = True
        def open_form(name, parameters=None):
            if (not accepting or application.state != 'starting'
                    or application.interpreter.execution_context != 'client'):
                raise ValueError('OpenForm requires active client workspace startup')
            if type(name) is not str or not name or len(name) > 1024:
                raise ValueError('declared source form name required')
            if len(pending) >= MAX_OPEN_FORMS:
                raise ValueError('source startup form capacity exhausted')
            from .configuration_app import _parameters
            pending.append((name, _parameters(parameters)))
        application.interpreter.register_function('OpenForm', open_form, 'ОткрытьФорму', returns_value=False)
        try:
            if not application.start():
                return None
            accepting = False
            workspace = cls(application)
            for name, parameters in pending:
                try:
                    name = workspace._resolve_form_name(name)
                    workspace._new_form(name, parameters)
                    workspace.navigation_total += 1
                except (BSLError, ValueError, TypeError, RecursionError) as error:
                    workspace.error = 'Startup OpenForm '+name+': '+str(error)[:2048]
                    break
            return workspace
        finally:
            accepting = False
            pending.clear()

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

    def _resolve_form_name(self, name):
        """Resolve spelling/default aliases to one admitted memory-only form.

        This is not a GetForm handler or automatic database-form generator.
        An absent declared default remains unavailable.
        """
        if type(name) is not str or not name or len(name) > 1024:
            raise ValueError('declared source form required for OpenForm')
        from ..configuration_source_metadata import _FAMILIES
        families = {alias.casefold(): family for family, _, _, russian in _FAMILIES
                    for alias in (family, russian)}
        parts = name.split('.')
        if len(parts) not in (2, 3, 4) or any(not part for part in parts):
            raise ValueError('declared source form required for OpenForm')
        family = families.get(parts[0].casefold())
        if family is None:
            raise ValueError('declared source form required for OpenForm')
        parts[0] = family
        if len(parts) == 4:
            if parts[2].casefold() not in ('form', 'форма'):
                raise ValueError('declared source form required for OpenForm')
            parts[2] = 'Form'
        canonical = '.'.join(parts)
        matches = [form for form in self.forms if form.casefold() == canonical.casefold()]
        if len(matches) == 1:
            return matches[0]
        if len(parts) != 3:
            raise ValueError('declared source form required for OpenForm')
        standard = {
            'objectform':'DefaultObjectForm', 'формаобъекта':'DefaultObjectForm',
            'listform':'DefaultListForm', 'формасписка':'DefaultListForm',
            'choiceform':'DefaultChoiceForm', 'формавыбора':'DefaultChoiceForm',
            'folderform':'DefaultFolderForm', 'формагруппы':'DefaultFolderForm',
            'folderchoiceform':'DefaultFolderChoiceForm', 'формавыборагруппы':'DefaultFolderChoiceForm',
            'recordform':'DefaultRecordForm', 'формазаписи':'DefaultRecordForm',
            'form':'DefaultForm', 'форма':'DefaultForm',
        }
        prop = standard.get(parts[2].casefold())
        owners = [owner for owner in self.objects if owner.casefold() == '.'.join(parts[:2]).casefold()]
        if prop and len(owners) == 1:
            matches = [item['name'] for item in self._default_forms(owners[0])[0] if item['property'] == prop]
            if len(matches) == 1:
                return matches[0]
        raise ValueError('declared source default form is unavailable')

    def _request_navigation(self, generation, name, parameters=None):
        if (self.closed or generation != self.navigation_event or generation != self.generation or generation not in self.open_forms
                or not self._live(self.open_forms[generation][1])):
            raise ValueError('inactive source form navigation')
        name = self._resolve_form_name(name)
        if (sum(self._live(form) for _, form in self.open_forms.values()) + len(self.pending_navigation) >= MAX_OPEN_FORMS
                or self.navigation_total + len(self.pending_navigation) >= 256):
            raise ValueError('source form navigation capacity exhausted')
        from .configuration_app import _parameters
        values = _parameters(parameters)
        self.pending_navigation.append((name, values))

    def _new_form(self, name, parameters=None):
        generation = self.next_generation + 1
        form = SourceFormController(self.application, name, progressive=True, parameters=parameters,
                                    navigation=lambda target, values=None: self._request_navigation(generation, target, values))
        self.open_forms = {key: value for key, value in self.open_forms.items() if self._live(value[1])}
        self.next_generation = generation
        self.open_forms[generation] = (name, form)
        self._select(generation)

    def _complete_navigation(self, result):
        requests, self.pending_navigation = self.pending_navigation, []
        if result.get('result', {}).get('error') is not None:
            return  # No deferred opens survive a failed handler; never replay them later.
        for name, parameters in requests:
            self.navigation_total += 1
            try:
                self._new_form(name, parameters)
            except (BSLError, ValueError, TypeError, RecursionError) as error:
                self.error = 'OpenForm '+name+': '+str(error)[:2048]
                break

    def visible_forms(self):
        matches = [name for name in self.forms if (self.query.casefold() in name.casefold() or self.query.casefold() in self.navigation_labels.get(name, '').casefold())]
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
                       and (not self.object_subsystem or name in self.subsystem_members[self.object_subsystem])
                       and (self.object_query.casefold() in name.casefold()
                            or self.object_query.casefold() in self.navigation_labels.get(name, '').casefold()))
        visible, omitted = self._bounded_names(names)
        return visible, omitted

    def _default_forms(self, name):
        """Explicit source declarations only; never guess or instantiate an object."""
        if name in self.default_form_cache:
            return self.default_form_cache[name]
        from ..configuration_source_metadata import SourceMetadataObject
        from ..configuration_xml import MD
        family = self.objects[name].family
        properties_by_family = {
            'Catalog': ('DefaultObjectForm', 'DefaultFolderForm', 'DefaultListForm',
                        'DefaultChoiceForm', 'DefaultFolderChoiceForm'),
            'Document': ('DefaultObjectForm', 'DefaultListForm', 'DefaultChoiceForm'),
            'DataProcessor': ('DefaultForm',), 'Report': ('DefaultForm',),
            'InformationRegister': ('DefaultRecordForm', 'DefaultListForm'),
            'AccumulationRegister': ('DefaultListForm',),
        }
        defaults, diagnostics = [], []
        properties = SourceMetadataObject(self.application.metadata, self.objects[name])._object().find('{'+MD+'}Properties')
        for prop in properties_by_family.get(family, ()):
            nodes = properties.findall('{'+MD+'}'+prop) if properties is not None else []
            if not nodes:
                continue
            if len(nodes) != 1 or nodes[0].attrib or len(nodes[0]):
                diagnostics.append(prop+': malformed default form declaration')
                continue
            target = nodes[0].text or ''
            if not target:
                continue
            if (len(target) > 1024 or target not in self.forms
                    or not (target.startswith(name+'.Form.') or self.objects[target].family == 'CommonForm')):
                diagnostics.append(prop+': unavailable declared source form')
                continue
            defaults.append({'property': prop, 'name': target})
        result = (defaults, diagnostics)
        self.default_form_cache[name] = result
        return result

    def object_detail(self):
        if self.object_selected is None:
            return None
        name = self.object_selected
        entry = self.objects[name]
        related = sorted(form for form in self.forms if form == name or form.startswith(name+'.Form.'))
        forms, omitted = self._bounded_names(related, 8192)
        defaults, diagnostics = self._default_forms(name)
        return {'name': name, 'title': self.navigation_labels.get(name, entry.name),
                'family': entry.family, 'source_path': entry.path,
                'forms': forms, 'form_labels': self._labels(forms + [item['name'] for item in defaults], 8192), 'omitted_forms': omitted,
                'default_forms': [dict(item) for item in defaults], 'default_form_diagnostics': list(diagnostics),
                'execution': 'explicit_form_selection' if related or defaults else 'metadata_only',
                'storage_granted': False}

    def _visible_form_targets(self):
        detail = self.object_detail() or {}
        admitted = set(self.visible_forms()[0]) | set(detail.get('forms', []))
        admitted.update(item['name'] for item in detail.get('default_forms', []))
        return admitted

    def _preview_form(self, name):
        """Inspect bounded XML projection only; no module compilation or execution."""
        from hashlib import sha256
        import xml.etree.ElementTree as ET
        from ..configuration_forms import L
        from ..source_form_projection import project_source_form
        from ..configuration_source_metadata import SourceMetadataObject
        entry = self.objects[name]
        path = entry.path[:-4] + '/Ext/Form.xml'
        raw = self.application.files.get(path)
        preview = {'name': name, 'source_path': path,
                   'source_sha256': sha256(raw).hexdigest() if raw is not None else None,
                   'status': 'unavailable', 'diagnostics': [], 'omitted_diagnostics': 0, 'counts': None,
                   'module_checked': False, 'runtime_checked': False,
                   'storage_granted': False, 'native_parity': False}
        try:
            form_type = SourceMetadataObject(self.application.metadata, entry)._property('FormType')
            if form_type.attrib or len(form_type) or form_type.text != 'Managed':
                raise ValueError('source form must declare Managed FormType')
            if raw is None:
                raise ValueError('declared form XML is missing')
            projection = project_source_form(raw)
            root = ET.fromstring(projection.xml)
            preview['status'] = 'projected'
            preview['counts'] = {
                'attributes': len(root.findall('./'+L+'Attributes/'+L+'Attribute')),
                'commands': len(root.findall('./'+L+'Commands/'+L+'Command')),
                'controls': sum(len(node) for node in root.iter(L+'ChildItems')),
            }
            diagnostic_bytes = 2
            for item in projection.diagnostics:
                cost = len(json.dumps(item, ensure_ascii=False).encode('utf-8')) + 1
                if diagnostic_bytes + cost > 6144:
                    preview['omitted_diagnostics'] += 1
                    continue
                preview['diagnostics'].append(dict(item))
                diagnostic_bytes += cost
        except (ValueError, TypeError, RecursionError, ET.ParseError) as error:
            preview['diagnostics'] = [{'path': 'Form', 'reason': str(error)[:256]}]
        self.form_preview = preview

    def _preflight_module(self, name):
        """Compile declared BSL only; no definition, interpreter or lifecycle."""
        from hashlib import sha256
        from ..form_program import compile_form_module
        prefix = self.objects[name].path[:-4]
        path = prefix + '/Ext/Form/Module.bsl'
        raw = self.application.files.get(path)
        xml = self.application.files.get(prefix + '/Ext/Form.xml')
        result = {'name': name, 'module_path': path,
                  'module_sha256': sha256(raw).hexdigest() if raw is not None else None,
                  'xml_sha256': sha256(xml).hexdigest() if xml is not None else None,
                  'compilation_profile': self.application.compilation_profile,
                  'status': 'unavailable', 'error': None, 'handler_names': None,
                  'bindings_checked': False, 'runtime_checked': False,
                  'storage_granted': False, 'native_parity': False}
        try:
            if raw is None:
                raise ValueError('declared form module file is absent')
            program = compile_form_module(raw.decode('utf-8-sig'),
                                compilation_profile=self.application.compilation_profile)
            result['status'] = 'compiled'
            from ..source_form_handler_audit import audit_handler_names
            result['handler_names'] = audit_handler_names(xml, program)
        except (BSLError, ValueError, TypeError, RecursionError) as error:
            result['error'] = str(error)[:1024]
        self.module_preflight = result

    def snapshot(self):
        visible, omitted = self.visible_forms()
        objects, object_omitted = self.object_inventory()
        label_forms = list(dict.fromkeys([name for name, _ in self.open_forms.values()] + visible))
        return {'protocol': PROTOCOL, 'state': {'kind': 'closed' if self.closed else 'workspace',
                'name': self.application.source.name, 'forms': visible, 'form_labels': self._labels(label_forms),
                'omitted_forms': omitted, 'query': self.query, 'selected': self.selected,
                'generation': self.generation, 'active': self._active(), 'error': self.error,
                'form_diagnostics': list(self.form.diagnostics) if self.form else [],
                'open_forms': [{'generation': generation, 'name': name, 'active': self._live(form)}
                               for generation, (name, form) in self.open_forms.items()],
                'form_limit': MAX_OPEN_FORMS, 'any_active': self._any_active(),
                'objects': objects, 'object_labels': self._labels(objects), 'omitted_objects': object_omitted,
                'subsystems': self.subsystems, 'subsystem_labels': self._labels(self.subsystems, 4096),
                'omitted_subsystems': self.omitted_subsystems, 'object_subsystem': self.object_subsystem,
                'navigation_diagnostics': list(self.navigation_diagnostics),
                'omitted_navigation_diagnostics': self.omitted_navigation_diagnostics,
                'object_query': self.object_query, 'object_family': self.object_family,
                'object_families': self.object_families, 'omitted_families': self.omitted_families, 'object_detail': self.object_detail(),
                'form_preview': json.loads(json.dumps(self.form_preview)),
                'module_preflight': json.loads(json.dumps(self.module_preflight)),
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
        if method != 'workspace.snapshot':
            self.error = None
        if method == 'workspace.open':
            if set(params) != {'name'} or type(params['name']) is not str:
                raise ValueError('declared workspace form required')
            if params['name'] not in self._visible_form_targets():
                raise ValueError('declared workspace form required')
            existing = next((generation for generation, (name, form) in self.open_forms.items()
                             if name == params['name'] and self._live(form)), None)
            if existing is not None:
                self._select(existing)
            elif sum(self._live(form) for _, form in self.open_forms.values()) >= MAX_OPEN_FORMS:
                self.error = 'Достигнут предел открытых форм: 8. Закройте одну из форм.'
            else:
                try:
                    self._new_form(params['name'])
                except (BSLError, ValueError, TypeError, RecursionError) as error:
                    self.error = str(error)[:4096]
        elif method in ('workspace.preview', 'workspace.preflight'):
            if (set(params) != {'name'} or type(params['name']) is not str
                    or params['name'] not in self._visible_form_targets()):
                raise ValueError('declared visible source form required')
            if method == 'workspace.preview':
                self._preview_form(params['name'])
            else:
                self._preflight_module(params['name'])
        elif method == 'workspace.select':
            if (set(params) != {'generation'} or type(params['generation']) is not int
                    or params['generation'] not in self.open_forms):
                raise ValueError('unknown workspace form')
            self._select(params['generation'])
        elif method == 'workspace.objects':
            if (set(params) not in ({'query', 'family'}, {'query', 'family', 'subsystem'}) or type(params['query']) is not str
                    or len(params['query']) > 128 or type(params['family']) is not str
                    or params['family'] not in ('', *self.object_families)
                    or type(params.get('subsystem', '')) is not str
                    or params.get('subsystem', '') not in ('', *self.subsystems)):
                raise ValueError('invalid object search')
            self.object_query, self.object_family = params['query'], params['family']
            self.object_subsystem = params.get('subsystem', '')
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
            self.pending_navigation = []
            nested = params['request']
            # Only an explicit user event may defer client navigation. The form
            # exchange still validates revision/control/value before invoking BSL.
            # Lifecycle/snapshot/close never gain this intent scope.
            self.navigation_event = (self.generation if type(nested) is dict and nested.get('method') == 'form.event'
                                     and type(nested.get('params')) is dict and nested['params'].get('event') in ('command', 'change') else None)
            try:
                result = self.form.exchange(params['request'])
            except BaseException:
                self.pending_navigation = []
                raise
            finally:
                self.navigation_event = None
            self._complete_navigation(result)
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
    methods = ('workspace.snapshot','workspace.preview','workspace.preflight','workspace.open','workspace.search','workspace.objects','workspace.inspect','workspace.select','workspace.form','workspace.close')
