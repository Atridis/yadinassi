"""Explicit trusted activation of a closed Designer managed-form subset.

This loader does not activate inert database archives, object persistence,
standard commands, arbitrary XML behavior, or a native windowing service.
"""
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

from .configuration_xml import (MD, V8, _LOGFORM, _accept_source_files,
    _object, _parse, _props, _text, _type)
from .form_model import (BSLFormAttribute, BSLFormField, BSLFormButton,
    BSLFormCommand, BSLFormFieldView, BSLClientApplicationForm, name, text, scalar)
from .form_program import compile_form_module
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers, BSLAllowedSign
from .structures import BSLStructure, BSLFixedStructure

L = '{' + _LOGFORM + '}'
M = '{' + MD + '}'
_RESERVED = {'parameters', 'параметры', 'openform', 'открытьформу'}


def _children(node, allowed):
    if (node.text or '').strip():
        raise ValueError('unexpected XML text')
    result = {}
    for child in node:
        if child.tag not in allowed or child.tag in result or (child.tail or '').strip():
            raise ValueError('unsupported or repeated form property')
        result[child.tag] = child
    return result


def _value(nodes, key, default=''):
    node = nodes.get(L + key)
    if node is None:
        return default
    if node.attrib or len(node):
        raise ValueError('scalar form property required')
    return text((node.text or '').strip(), 1024)


def _flag(nodes, key, default):
    value = _value(nodes, key, 'true' if default else 'false')
    if value not in ('true', 'false'):
        raise ValueError('boolean form property required')
    return value == 'true'


def _inventory(node, tag, maximum):
    if node is None:
        return ()
    if node.attrib or (node.text or '').strip() or len(node) > maximum:
        raise ValueError('invalid form inventory')
    names, ids = set(), set()
    for child in node:
        if child.tag not in tag or set(child.attrib) != {'name', 'id'} or (child.tail or '').strip():
            raise ValueError('invalid form declaration')
        key = name(child.get('name')).casefold()
        identity = child.get('id')
        if not identity.isascii() or not identity.isdecimal() or not 1 <= int(identity) <= 1000000:
            raise ValueError('invalid form element ID')
        if key in names or int(identity) in ids or key in _RESERVED:
            raise ValueError('duplicate or reserved form declaration')
        names.add(key); ids.add(int(identity))
    return tuple(node)


def _events(node, allowed):
    if node is None:
        return {}
    if node.attrib or (node.text or '').strip():
        raise ValueError('invalid event envelope')
    result = {}
    for event in node:
        key = event.get('name', '').casefold()
        key = BSLClientApplicationForm.EVENT_NAMES.get(key, key)
        if (event.tag != L + 'Event' or set(event.attrib) != {'name'} or len(event)
                or key not in allowed or key in result or (event.tail or '').strip()):
            raise ValueError('unsupported or duplicate form event')
        result[key] = name((event.text or '').strip())
    return result


def bind_parameters(session, parameters=None):
    """Copy scalar parameters into this one activation before any lifecycle event."""
    if session.state != 'created' or session._busy:
        raise ValueError('parameters must precede form open')
    if parameters is None:
        parameters = {}
    if type(parameters) in (BSLStructure, BSLFixedStructure):
        parameters = {key: value for key, value in parameters._items.values()}
    if type(parameters) is not dict or len(parameters) > 64:
        raise ValueError('bounded scalar parameter structure required')
    result = BSLStructure(); seen = set(); size = 0
    for key, value in parameters.items():
        key = name(key)
        if key.casefold() in seen:
            raise ValueError('duplicate form parameter')
        seen.add(key.casefold()); value = scalar(value)
        size += len(value) if type(value) is str else 0
        if size > 65536:
            raise ValueError('form parameter text limit')
        result.insert(key, value)
    session._parameters = BSLFixedStructure(result)


@dataclass(frozen=True)
class FormDefinition:
    name: str
    identity: UUID
    source_sha256: str
    program: object
    attributes: tuple
    bindings: object
    title: str
    items: tuple
    commands: tuple
    catalog_schema: object = None
    object_fields: tuple = ()
    write_handler: str = ''

    def client_package(self):
        return SimpleNamespace(source=self.program.client, handlers=self.program.handlers,
            bindings=self.program.server_bindings, discard_commands=(), dirty_attribute='')

    def create_server(self, *, parameters=None, database_context=None, object_session=None):
        from .form_replication import ReplicatedFormServer
        initial = {}; server_bindings = ()
        if self.catalog_schema is not None:
            if object_session is not None:
                object_session.verify_source()
                if object_session.schema != self.catalog_schema:
                    raise ValueError('object form schema mismatch')
                initial = {slot: object_session.values()[field] for field, slot in self.object_fields}
            from .form_runtime import FormServerBinding
            def write(session):
                if object_session is None:
                    raise ValueError('object form has no persistence activation')
                return self._write_object(session, object_session)
            server_bindings = (FormServerBinding('WriteObject', write),)
        server = ReplicatedFormServer(self.program.server, self.program.endpoints,
            handlers=self.program.handlers, attributes=self.attributes,
            bindings=dict(self.bindings), database_context=database_context,
            initial_values=initial, server_bindings=server_bindings)
        session = server.session; form = session.form
        if self.write_handler:
            routine = session._bind(self.write_handler, 'server', 1)
            if routine.parameters[0].by_value:
                raise ValueError('BeforeWriteAtServer requires reference Cancel')
        bind_parameters(session, parameters)
        form.title = self.title
        for item_name, title, action in self.commands:
            session._bind(action, 'client', 1)
            command = BSLFormCommand(form, item_name)
            command.title, command.action = title, action
            form.commands._values[item_name.casefold()] = command
        for item_name, kind, title, path, action, visible, enabled, read_only in self.items:
            item = BSLFormButton(form, item_name) if kind == 'Button' else BSLFormField(form, item_name)
            item.title, item.visible, item.enabled, item.read_only = title, visible, enabled, read_only
            if kind == 'Button':
                item.command_name = path
            else:
                item.data_path = path
                if action:
                    session._bind(action, 'client', 1)
                item.action = action
                item.view = {'InputField': BSLFormFieldView.INPUT,
                    'LabelField': BSLFormFieldView.LABEL, 'CheckBoxField': BSLFormFieldView.CHECKBOX}[kind]
            form.items._values[item_name.casefold()] = item
        session._allocated = len(self.items) + len(self.commands)
        return server


    def _write_object(self, session, owned):
        """Explicit local WriteObject service, not native standard FormWrite."""
        from .form_replication import _pack_state
        from .ui.protocol import encode_line
        if session.state != 'open':
            raise ValueError('WriteObject requires an open object form')
        def values():
            return {field: session.form.get_member(slot) for field, slot in self.object_fields}
        def prepare(candidate):
            for field, slot in self.object_fields:
                session.form.set_member(slot, candidate[field])
            if self.write_handler:
                cancelled = session._invoke(self.write_handler, 'server', [False])[0]
                if type(cancelled) is not bool:
                    raise ValueError('invalid form write cancellation')
                if cancelled:
                    return None
            return values()
        projected_values = {}
        def preflight(result):
            if hasattr(owned, 'projection_preflight'):
                owned.projection_preflight(result.listing)
            if len(result.listing.cards) > 256:
                raise ValueError('catalog projection limit')
            # Validate the whole bounded authoritative list, not merely the
            # saved card's old eight-row page. No success with an unusable list.
            encode_line({'entry': 64, 'version': 2147483647, 'rows': [
                {'key': 'record-4096', 'code': card.values[0],
                 'description': card.values[1], 'deletionMark': card.values[2]}
                for card in result.listing.cards]})
            previous = session.form._data.copy()
            try:
                for field, value in result.values:
                    session.form.set_member(dict(self.object_fields)[field], value)
                encode_line(_pack_state(session, session._replica_handler_names))
                projected_values.clear()
                projected_values.update((slot.casefold(), session.form._data[slot.casefold()])
                                        for _, slot in self.object_fields)
            finally:
                session.form._data = previous
        result = owned.save(values(), before_write=prepare, validate_result=preflight)
        if result.state in ('saved', 'unchanged'):
            # Preflight already validated the complete scalar projection.
            session.form._data.update(projected_values)
        locked = owned.pending_commit or owned.pending_refresh
        slots = {slot.casefold() for _, slot in self.object_fields}
        original = {item[0].casefold(): item[-1] for item in self.items}
        for key, item in session.form.items._values.items():
            if isinstance(item, BSLFormField) and item.data_path.casefold() in slots:
                item.read_only = locked or original.get(key, True)
        return result.state


@dataclass(frozen=True)
class ConfigurationForms:
    identity: UUID
    name: str
    source_sha256: str
    forms: object
    source_files: object = None

    @property
    def title(self):
        return self.name

    def resolve(self, form_name):
        if type(form_name) is not str:
            raise ValueError('declared form name required')
        try:
            return self.forms[form_name.casefold()]
        except KeyError:
            raise ValueError('undeclared configuration form') from None


def _definition(public_name, identity, raw, module, catalog_schema=None):
    root, namespaces = _parse(raw)
    if root.tag != L + 'Form' or set(root.attrib) - {'version'}:
        raise ValueError('unsupported form definition envelope')
    props = _children(root, {L+k for k in ('Title', 'Attributes', 'ChildItems', 'Commands', 'Events')})
    attrs = []; object_fields = (); main_seen = False
    for node in _inventory(props.get(L+'Attributes'), {L+'Attribute'}, 128):
        values = _children(node, {L+k for k in ('Type', 'Title', 'MainAttribute')})
        if L+'MainAttribute' in values:
            if (catalog_schema is None or main_seen or node.get('name') != 'Object'
                    or not _flag(values, 'MainAttribute', False)):
                raise ValueError('one catalog Object main attribute required')
            type_node = values.get(L+'Type')
            if type_node is None or type_node.attrib or len(type_node) != 1 or (type_node.text or '').strip():
                raise ValueError('exact catalog object type required')
            child = type_node[0]
            target = (child.text or '').strip()
            if (child.tag != '{'+V8+'}Type' or child.attrib or len(child) or (child.tail or '').strip()
                    or ':' not in target):
                raise ValueError('exact catalog object type required')
            prefix, local = target.split(':', 1)
            if namespaces.get(id(child), {}).get(prefix) != 'http://v8.1c.ru/8.1/data/enterprise/current-config' or local != 'CatalogObject.'+catalog_schema.name:
                raise ValueError('object form owner/type mismatch')
            if catalog_schema.tabular_sections or any(f.kind == 'catalog_ref' for f in catalog_schema.fields):
                raise ValueError('only scalar catalog object forms supported')
            from .ui.catalog_editor import _descriptor
            specs = [('Code', 'string', (catalog_schema.code_length,)),
                     ('Description', 'string', (catalog_schema.description_length,)),
                     ('DeletionMark', 'boolean', ())]
            specs.extend((f.name, f.kind, f.qualifiers) for f in catalog_schema.fields)
            object_fields = tuple((field, 'ObjectField'+str(i)) for i, (field, _, _) in enumerate(specs, 1))
            for (field, kind, qualifiers), (_, slot) in zip(specs, object_fields):
                attrs.append(BSLFormAttribute(slot, _descriptor(kind, qualifiers), title=field))
            main_seen = True
            continue
        if node.get('name').casefold() in ('object', 'объект', 'writeobject') or node.get('name').casefold().startswith('objectfield'):
            raise ValueError('reserved object form attribute')
        if L+'Type' not in values:
            raise ValueError('form attribute type required')
        kind, q, _ = _type({M+'Type': values[L+'Type']}, namespaces, {})
        if kind == 'string':
            value_type = BSLTypeDescription('String', None, BSLStringQualifiers(Decimal(q[0])))
        elif kind == 'number':
            value_type = BSLTypeDescription('Number', BSLNumberQualifiers(Decimal(q[0]), Decimal(q[1]),
                BSLAllowedSign.NONNEGATIVE if q[2] == 'Nonnegative' else BSLAllowedSign.ANY))
        elif kind in ('boolean', 'datetime'):
            value_type = BSLTypeDescription('Boolean' if kind == 'boolean' else 'Date')
        else:
            raise ValueError('only scalar form attributes supported')
        attrs.append(BSLFormAttribute(node.get('name'), value_type, title=_value(values, 'Title')))
    if catalog_schema is not None and not main_seen:
        raise ValueError('catalog object form main attribute required')
    commands = []
    for node in _inventory(props.get(L+'Commands'), {L+'Command'}, 64):
        values = _children(node, {L+'Title', L+'Action'})
        commands.append((node.get('name'), _value(values, 'Title'), name(_value(values, 'Action'))))
    items = []; attr_names = {a.name.casefold() for a in attrs}; command_names = {c[0].casefold() for c in commands}
    for node in _inventory(props.get(L+'ChildItems'), {L+k for k in ('InputField','LabelField','CheckBoxField','Button')}, 128):
        kind = node.tag[len(L):]
        fields = ('Title','Visible','Enabled','ReadOnly','CommandName') if kind == 'Button' else ('Title','Visible','Enabled','ReadOnly','DataPath','Events')
        values = _children(node, {L+k for k in fields})
        path = _value(values, 'CommandName' if kind == 'Button' else 'DataPath')
        if kind != 'Button' and path.startswith('Object.'):
            field = path[len('Object.'):]
            resolved = {key.casefold(): value for key, value in object_fields}.get(field.casefold())
            if resolved is None:
                raise ValueError('unknown object form path')
            path = resolved
        elif kind != 'Button' and path.casefold().startswith('objectfield'):
            raise ValueError('private object projection path')
        if path.casefold() not in (command_names if kind == 'Button' else attr_names):
            raise ValueError('unbound form item target')
        action = _events(values.get(L+'Events'), {'onchange'}).get('onchange', '')
        items.append((node.get('name'), kind, _value(values,'Title'), path, action,
            _flag(values,'Visible',True), _flag(values,'Enabled',True), _flag(values,'ReadOnly',False)))
    program = compile_form_module(module.decode('utf-8-sig'), object_fields=tuple(field for field, _ in object_fields))
    from .syntax import ast
    declared_names = set()
    for side in (program.client, program.server, program.nocontext):
        for declaration in side.program():
            declared_names.update([declaration.name.casefold()] if isinstance(declaration, ast.Routine)
                else (value.casefold() for value in declaration.names))
    if attr_names & declared_names:
        raise ValueError('form attribute shadows module declaration')
    allowed = set(BSLClientApplicationForm.EVENTS)
    if main_seen:
        allowed.add('beforewriteatserver')
    bindings = _events(props.get(L+'Events'), allowed)
    write_handler = bindings.pop('beforewriteatserver', '')
    definition = FormDefinition(public_name, identity, sha256(raw+b'\0'+module).hexdigest(), program,
        tuple(attrs), MappingProxyType(bindings), _value(props,'Title'), tuple(items), tuple(commands),
        catalog_schema, object_fields, write_handler)
    # Validate every declared handler and all reserved-name collisions eagerly.
    validation_server = definition.create_server()
    validation_server.session.interpreter.close()
    return definition


def load_configuration_forms(files, *, catalog_schemas=()):
    """Load declared CommonForms and Catalog/Document custom forms, explicitly."""
    accepted = _accept_source_files(files)
    schemas = {schema.name.casefold(): schema for schema in catalog_schemas}
    config, _ = _object(files['Configuration.xml'], 'Configuration')
    identity = UUID(config.get('uuid')); config_name = name(_text(_props(config),'Name'))
    used = {identity}; forms = {}
    def object_at(path, kind):
        obj, _ = _object(files[path], kind)
        uid = UUID(obj.get('uuid'))
        if uid in used:
            raise ValueError('duplicate metadata identity')
        used.add(uid)
        return obj, uid
    def declarations(obj):
        containers = obj.findall(M+'ChildObjects')
        if len(containers) != 1 or containers[0].attrib:
            raise ValueError('metadata declarations required')
        seen = set()
        for node in containers[0]:
            if node.tag not in {M+'CommonForm',M+'Catalog',M+'Document',M+'Form'}:
                continue
            if node.attrib or len(node):
                raise ValueError('invalid metadata declaration')
            value = name((node.text or '').strip()); key = (node.tag,value.casefold())
            if key in seen:
                raise ValueError('duplicate metadata declaration')
            seen.add(key)
            yield node.tag[len(M):], value
    entries = []
    for kind, value in declarations(config):
        if kind == 'CommonForm':
            entries.append(('CommonForm.'+value, 'CommonForms/'+value, 'CommonForm', value, None))
        elif kind in ('Catalog','Document'):
            prefix = kind+'s/'+value
            owner, _ = object_at(prefix+'.xml',kind)
            if _text(_props(owner),'Name') != value:
                raise ValueError('metadata filename/name mismatch')
            for child_kind, form_name in declarations(owner):
                if child_kind != 'Form':
                    raise ValueError('unexpected form owner declaration')
                entries.append((kind+'.'+value+'.Form.'+form_name, prefix+'/Forms/'+form_name, 'Form', form_name, schemas.get(value.casefold()) if kind == 'Catalog' else None))
    if not 1 <= len(entries) <= 64:
        raise ValueError('configuration form count')
    for public_name, prefix, kind, form_name, schema in entries:
        obj, uid = object_at(prefix+'.xml', kind); props = _props(obj)
        if set(props) - {M+'Name', M+'FormType'}:
            raise ValueError('unsupported executable form metadata property')
        for prop in props.values():
            if prop.attrib or len(prop) or (prop.tail or '').strip():
                raise ValueError('unsupported form metadata scalar envelope')
        if set(obj.attrib) != {'uuid'} or any(child.tag not in {M+'Properties', M+'ChildObjects'} for child in obj):
            raise ValueError('unsupported form metadata envelope')
        if any(len(child) or child.attrib or (child.text or '').strip() for child in obj.findall(M+'ChildObjects')):
            raise ValueError('form child metadata unsupported')
        if _text(props,'Name') != form_name or _text(props,'FormType','Managed') != 'Managed':
            raise ValueError('declared managed form required')
        path = prefix+'/Ext/Form.xml'; module = prefix+'/Ext/Form/Module.bsl'
        definition = _definition(public_name, uid, files[path], files.get(module,b''), schema)
        if public_name.casefold() in forms:
            raise ValueError('duplicate form name')
        forms[public_name.casefold()] = definition
    digest = sha256()
    for entry in accepted:
        digest.update(entry.path.encode('utf-8')+b'\0'+files[entry.path]+b'\0')
    return ConfigurationForms(identity, config_name, digest.hexdigest(), MappingProxyType(forms), MappingProxyType(dict(files)))
