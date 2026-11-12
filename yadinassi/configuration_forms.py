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
    BSLFormCommand, BSLFormTable, BSLFormGroup, BSLFormFieldView, BSLClientApplicationForm, name, text, scalar)
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
    document_schema: object = None
    object_sections: tuple = ()
    tables: tuple = ()
    reference_targets: tuple = ()
    reference_slots: tuple = ()
    posting_application: bool = False
    layout: tuple = ()
    enum_targets: tuple = ()

    def client_package(self):
        return SimpleNamespace(source=self.program.client, handlers=self.program.handlers,
            bindings=self.program.server_bindings, discard_commands=(), dirty_attribute='')

    def create_server(self, *, parameters=None, database_context=None, object_session=None, interpreter_factory=None, _validate_only=False):
        from .form_replication import ReplicatedFormServer
        initial = {}; server_bindings = ()
        attributes, tables = self.attributes, self.tables
        reference_scope = None; enroll = None
        if (self.reference_targets or self.enum_targets) and not _validate_only:
            if object_session is None:
                raise ValueError('reference forms require an owned persistence activation')
            from .configuration_references import owned_reference_scope
            from .form_tables import FormTableColumn, FormTableSchema
            reference_scope, reference_managers, enroll = owned_reference_scope(object_session, self.reference_targets, self.enum_targets)
            slots = {(slot.casefold(), column.casefold()): target for slot, column, target in self.reference_slots}
            attributes = tuple(BSLFormAttribute(a.name, reference_scope.descriptor(slots[a.name.casefold(), ''])
                if (a.name.casefold(), '') in slots else a.value_type, title=a.title) for a in self.attributes)
            tables = tuple(FormTableSchema(t.name, tuple(FormTableColumn(c.name,
                reference_scope.descriptor(slots[t.name.casefold(), c.name.casefold()])
                if (t.name.casefold(), c.name.casefold()) in slots else c.value_type,
                c.title, c.read_only) for c in t.columns), t.title) for t in self.tables)
        if self.catalog_schema is not None or self.document_schema is not None:
            if object_session is not None:
                object_session.verify_source()
                if object_session.schema != (self.document_schema or self.catalog_schema):
                    raise ValueError('object form schema mismatch')
                values = dict(object_session.image().values) if self.document_schema else object_session.values()
                initial = {slot: values[field] for field, slot in self.object_fields}
            from .form_runtime import FormServerBinding
            def write(session):
                if object_session is None:
                    raise ValueError('object form has no persistence activation')
                if self.posting_application:
                    raise ValueError('posting requires an explicit host command after form dispatch')
                return (self._write_document(session, object_session) if self.document_schema
                        else self._write_object(session, object_session))
            server_bindings = (FormServerBinding('WriteObject', write),)
        choice_holder = {}
        if self.reference_targets or self.enum_targets:
            from .form_runtime import FormServerBinding
            server_bindings += (FormServerBinding('HostReferenceAction',
                lambda session: choice_holder['choice'].execute(session)),)
        server = ReplicatedFormServer(self.program.server, self.program.endpoints,
            handlers=self.program.handlers, attributes=attributes, tables=tables,
            bindings=dict(self.bindings), database_context=database_context,
            initial_values=initial, server_bindings=server_bindings, interpreter_factory=interpreter_factory, reference_scope=reference_scope)
        session = server.session; form = session.form
        if self.posting_application:
            form._host_readonly = frozenset((dict(self.object_fields)["Posted"].casefold(),))
        if enroll is not None:
            enroll(session.interpreter)
            session._reference_enroll_activation = enroll
            session._reference_managers = reference_managers
            session._reference_slots = self.reference_slots
            from .configuration_reference_choice import ConfigurationReferenceChoice
            choice_holder['choice'] = ConfigurationReferenceChoice(self, server, object_session)
            server._reference_choice = choice_holder['choice']
        if self.document_schema:
            session._document_row_ids = {}
            if object_session is not None:
                self._install_document_image(session, object_session.image())
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
            item = (BSLFormButton(form, item_name) if kind == 'Button' else
                    BSLFormTable(form, item_name) if kind == 'Table' else
                    BSLFormGroup(form, item_name) if kind in ('UsualGroup', 'Pages', 'Page') else BSLFormField(form, item_name))
            item.title, item.visible, item.enabled, item.read_only = title, visible, enabled, read_only
            if kind == 'Button':
                item.command_name = path
            elif type(item) is not BSLFormGroup:
                item.data_path = path
                if action:
                    session._bind(action, 'client', 1)
                item.action = action
                if kind != 'Table': item.view = {'InputField': BSLFormFieldView.INPUT,
                    'LabelField': BSLFormFieldView.LABEL, 'CheckBoxField': BSLFormFieldView.CHECKBOX}[kind]
            form.items._values[item_name.casefold()] = item
        if self.layout:
            from .form_layout import install_layout
            install_layout(form, self.layout)
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


    def _document_image(self, session):
        from .configuration_document import DocumentImage, DocumentRowImage
        form=session.form
        # Posting consumes a detached image only after the form dispatch exits.
        # Read immutable scalar storage without manufacturing a BSL activation.
        if self.posting_application and not session._busy:
            return DocumentImage(tuple((field,form._data[slot.casefold()]) for field,slot in self.object_fields),
                tuple((section,tuple(DocumentRowImage(session._document_row_ids.get((slot.casefold(),row._row_id)),
                    tuple((column.name,row._data[column.name.casefold()]) for column in table.schema.columns))
                    for row in table._rows))
                    for section,slot in self.object_sections for table in (form._tables[slot.casefold()],)))
        return DocumentImage(tuple((field,form.get_member(slot)) for field,slot in self.object_fields),
            tuple((section,tuple(DocumentRowImage(session._document_row_ids.get((slot.casefold(),row._row_id)),
                tuple((column.name,row.get_member(column.name)) for column in table.schema.columns))
                for row in table._rows))
                for section,slot in self.object_sections for table in (form._tables[slot.casefold()],)))

    def _install_document_image(self, session, image):
        from .configuration_document import DocumentImage
        from .form_tables import validate_table_data
        if type(image) is not DocumentImage: raise TypeError('document image required')
        if tuple(k for k,v in image.values)!=tuple(k for k,v in self.object_fields):
            raise ValueError('complete document header required')
        if tuple(k for k,v in image.sections)!=tuple(k for k,v in self.object_sections):
            raise ValueError('complete document sections required')
        data=session.form._data.copy()
        for (field,slot),(_,value) in zip(self.object_fields,image.values):
            key=slot.casefold()
            from .form_references import adjust
            adjusted=adjust(session.form._attributes[key].value_type, value)
            if type(adjusted) is not type(value) or adjusted!=value: raise ValueError("document header does not fit form type")
            data[key]=adjusted
        identities={};replacements={};allocations={}
        for (_,slot),(_,rows) in zip(self.object_sections,image.sections):
            table=session.form._tables[slot.casefold()]
            old_ids=[r._row_id for r in table._rows]
            allocated=table._allocated
            records=[]
            for index,row in enumerate(rows):
                if tuple(k for k,v in row.values)!=tuple(c.name for c in table.schema.columns):
                    raise ValueError('complete document row required')
                if index<len(old_ids): identity=old_ids[index]
                else: allocated+=1;identity=allocated
                values=tuple(v for k,v in row.values)
                for column,value in zip(table.schema.columns,values):
                    adjusted=column.value_type.adjust_value(value)
                    if type(adjusted) is not type(value) or adjusted!=value: raise ValueError('document row does not fit form type')
                records.append((identity,values))
                if row.identity is not None: identities[slot.casefold(),identity]=row.identity
            replacements[slot.casefold()]=tuple(records);allocations[slot.casefold()]=allocated
        validate_table_data(session.form,replacements,data)
        for key,records in replacements.items(): session.form._tables[key]._replace_rows(records,allocations[key])
        session.form._data=data
        session._document_row_ids=identities

    def _write_document(self, session, owned):
        from .form_tables import BSLFormDataCollection
        from .form_replication import _pack_state
        from .ui.protocol import encode_line
        if session.state!='open': raise ValueError('WriteObject requires open document form')
        # Recovery must not rebuild an intent from newer form values.
        candidate=None if owned.pending_commit or owned.pending_refresh else self._document_image(session)
        def preflight(result):
            if hasattr(owned,'projection_preflight'): owned.projection_preflight(result.listing)
            if len(result.listing)>256: raise ValueError('document list projection limit')
            old_data=session.form._data.copy();old_tables=session.form._tables;old_ids=session._document_row_ids
            try:
                session.form._tables={schema.name.casefold():BSLFormDataCollection(session.form,schema,i)
                    for i,schema in enumerate((t.schema for t in old_tables.values()),1)}
                for key,table in session.form._tables.items():
                    previous=old_tables[key]._snapshot()
                    table._replace_rows(previous.rows,previous.allocated)
                self._install_document_image(session,result.image)
                encode_line(_pack_state(session,session._replica_handler_names))
            finally:
                session.form._data=old_data;session.form._tables=old_tables;session._document_row_ids=old_ids
        result=owned.save(candidate,validate_result=preflight)
        if result.state in ('saved','unchanged'):
            self._install_document_image(session,result.image)
        locked=owned.pending_commit or owned.pending_refresh
        slots={slot.casefold() for _,slot in (*self.object_fields,*self.object_sections)}
        original={item[0].casefold():item[-1] for item in self.items}
        for key,item in session.form.items._values.items():
            if isinstance(item,BSLFormField) and item.data_path.casefold() in slots:
                item.read_only=locked or original.get(key,True)
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


def _definition(public_name, identity, raw, module, catalog_schema=None, document_schema=None, reference_catalogs=(), posting_application=False, enum_definitions=()):
    root, namespaces = _parse(raw)
    if root.tag != L + 'Form' or set(root.attrib) - {'version'}:
        raise ValueError('unsupported form definition envelope')
    props = _children(root, {L+k for k in ('Title', 'Attributes', 'ChildItems', 'Commands', 'Events')})
    attrs = []; object_fields = (); object_sections = (); tables = (); main_seen = False
    reference_slots = []
    reference_targets = tuple((i, catalog.identity, catalog.name) for i, catalog in enumerate(reference_catalogs, 1))
    enum_targets=tuple((i,enum.identity,enum.name) for i,enum in enumerate(enum_definitions,len(reference_targets)+1))
    references = {identity: target for target, identity, _ in reference_targets}
    enum_references={identity:target for target,identity,_ in enum_targets}
    def field_descriptor(field, slot, column=''):
        from .ui.catalog_editor import _descriptor
        if field.kind=='enum_ref':
            if field.target_enum_id not in enum_references:raise ValueError('enum target outside explicit form grant')
            reference_slots.append((slot,column,enum_references[field.target_enum_id]))
            return BSLTypeDescription('String')
        if field.kind != 'catalog_ref': return _descriptor(field.kind, field.qualifiers)
        if field.target_catalog_id not in references:
            raise ValueError('reference target is outside the explicit form source grant')
        reference_slots.append((slot, column, references[field.target_catalog_id]))
        # Metadata-only structural template. Live create_server materializes the
        # scoped descriptor before installing any value or running lifecycle code.
        return BSLTypeDescription('String')
    schema = document_schema or catalog_schema
    for node in _inventory(props.get(L+'Attributes'), {L+'Attribute'}, 128):
        values = _children(node, {L+k for k in ('Type', 'Title', 'MainAttribute')})
        if L+'MainAttribute' in values:
            if (schema is None or main_seen or node.get('name') != 'Object'
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
            if namespaces.get(id(child), {}).get(prefix) != 'http://v8.1c.ru/8.1/data/enterprise/current-config' or local != ('DocumentObject.' if document_schema else 'CatalogObject.')+schema.name:
                raise ValueError('object form owner/type mismatch')
            from .ui.catalog_editor import _descriptor
            if document_schema:
                from .configuration_document import require_document_form_schema
                from .form_tables import FormTableColumn, FormTableSchema
                require_document_form_schema(schema, reference_fields=bool(reference_catalogs), enum_fields=bool(enum_definitions))
                specs = [('Number', 'string', (schema.number_length,)), ('Date', 'datetime', ()), ('DeletionMark', 'boolean', ())]
                if posting_application: specs.append(('Posted', 'boolean', ()))
            else:
                if schema.tabular_sections or (not reference_catalogs and any(f.kind == 'catalog_ref' for f in schema.fields)):
                    raise ValueError('only scalar catalog object forms supported')
                specs = [('Code', 'string', (schema.code_length,)), ('Description', 'string', (schema.description_length,)), ('DeletionMark', 'boolean', ())]
            specs.extend((f.name, f.kind, f.qualifiers) for f in schema.fields)
            object_fields = tuple((field, 'ObjectField'+str(i)) for i, (field, _, _) in enumerate(specs, 1))
            for (field, kind, qualifiers), (_, slot) in zip(specs, object_fields):
                declared = next((f for f in schema.fields if f.name == field), None)
                descriptor = field_descriptor(declared, slot) if declared is not None else _descriptor(kind, qualifiers)
                attrs.append(BSLFormAttribute(slot, descriptor, title=field))
            if document_schema:
                object_sections = tuple((section.name, 'ObjectField'+str(i)) for i, section in enumerate(schema.tabular_sections, len(specs)+1))
                tables = tuple(FormTableSchema(slot, tuple(FormTableColumn(f.name, field_descriptor(f, slot, f.name), f.name) for f in section.fields), section.name)
                    for section, (_, slot) in zip(schema.tabular_sections, object_sections))
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
    if schema is not None and not main_seen:
        raise ValueError('catalog object form main attribute required')
    commands = []
    for node in _inventory(props.get(L+'Commands'), {L+'Command'}, 64):
        values = _children(node, {L+'Title', L+'Action'})
        commands.append((node.get('name'), _value(values, 'Title'), name(_value(values, 'Action'))))
    items = []; attr_names = {a.name.casefold() for a in attrs} | {t.name.casefold() for t in tables}; command_names = {c[0].casefold() for c in commands}
    layout = []; layout_names = set(); layout_ids = set(); has_groups = False
    def parse_items(container, parent='', parent_kind='', depth=1):
        nonlocal has_groups
        from .form_layout import MAX_LAYOUT_DEPTH
        if container is not None and len(container) and depth > MAX_LAYOUT_DEPTH:
            raise ValueError('form layout depth limit')
        for node in _inventory(container, {L+k for k in ('InputField','LabelField','CheckBoxField','Button','Table','UsualGroup','Pages','Page')}, 128):
            kind = node.tag[len(L):]; item_name = node.get('name')
            key = item_name.casefold(); identity = int(node.get('id'))
            if key in layout_names or identity in layout_ids or len(layout_names) >= 128:
                raise ValueError('duplicate form layout identity or item limit')
            layout_names.add(key); layout_ids.add(identity)
            if (kind == 'Page') != (parent_kind == 'Pages'):
                raise ValueError('Pages requires direct Page children only')
            if kind in ('UsualGroup','Pages','Page'):
                has_groups = True
                fields = ('Title','Visible','Enabled','ReadOnly','ChildItems') + (('PagesRepresentation',) if kind == 'Pages' else ('Group','ShowTitle'))
                values = _children(node, {L+k for k in fields})
                orientation = _value(values, 'Group', 'Vertical')
                if orientation not in ('Vertical','Horizontal') or _value(values,'PagesRepresentation','TabsOnTop') != 'TabsOnTop':
                    raise ValueError('unsupported group/page presentation')
                layout.append((item_name, parent, {'UsualGroup':'group','Pages':'pages','Page':'page'}[kind], orientation.lower(), _flag(values,'ShowTitle',True)))
                items.append((item_name, kind, _value(values,'Title'), '', '', _flag(values,'Visible',True), _flag(values,'Enabled',True), _flag(values,'ReadOnly',False)))
                children = values.get(L+'ChildItems')
                if kind == 'Pages' and (children is None or not len(children)):
                    raise ValueError('Pages requires at least one Page')
                if children is not None:
                    parse_items(children, item_name, kind, depth+1)
                continue
            layout.append((item_name, parent, 'control', 'vertical', True))
            fields = ('Title','Visible','Enabled','ReadOnly','CommandName') if kind == 'Button' else ('Title','Visible','Enabled','ReadOnly','DataPath','Events')
            values = _children(node, {L+k for k in fields})
            path = _value(values, 'CommandName' if kind == 'Button' else 'DataPath')
            if kind != 'Button' and path.startswith('Object.'):
                field = path[len('Object.'):]
                resolved = {key.casefold(): value for key, value in (*object_fields, *object_sections)}.get(field.casefold())
                if resolved is None:
                    raise ValueError('unknown object form path')
                path = resolved
            elif kind != 'Button' and path.casefold().startswith('objectfield'):
                raise ValueError('private object projection path')
            if path.casefold() not in (command_names if kind == 'Button' else attr_names):
                raise ValueError('unbound form item target')
            if (kind == 'Table') != (path.casefold() in {t.name.casefold() for t in tables}):
                raise ValueError('table item requires a declared section path')
            action = _events(values.get(L+'Events'), {'onchange'}).get('onchange', '')
            if posting_application and dict(object_fields).get('Posted') == path and (kind != 'LabelField' or action):
                raise ValueError('Posted is an authoritative label only')
            items.append((node.get('name'), kind, _value(values,'Title'), path, action,
                _flag(values,'Visible',True), _flag(values,'Enabled',True), _flag(values,'ReadOnly',False)))
    parse_items(props.get(L+'ChildItems'))
    source = module.decode('utf-8-sig')
    if posting_application:
        import re
        if re.search(r'\bYadinassiPostingSync\b', source, re.IGNORECASE):
            raise ValueError('reserved posting synchronization name')
        source += '\n&AtServer\nProcedure YadinassiPostingSync()\nEndProcedure\n'
    if reference_slots:
        import re
        if re.search(r'\b(?:YadinassiReferenceAction|HostReferenceAction)\b', source, re.IGNORECASE):
            raise ValueError('reserved internal reference dispatch name')
        source += '\n&AtServer\nFunction YadinassiReferenceAction()\nReturn HostReferenceAction();\nEndFunction\n'
    program = compile_form_module(source, object_fields=tuple(field for field, _ in (*object_fields, *object_sections)), object_sections=tuple(field for field, _ in object_sections))
    from .syntax import ast
    declared_names = set()
    for side in (program.client, program.server, program.nocontext):
        for declaration in side.program():
            declared_names.update([declaration.name.casefold()] if isinstance(declaration, ast.Routine)
                else (value.casefold() for value in declaration.names))
    if attr_names & declared_names:
        raise ValueError('form attribute shadows module declaration')
    allowed = set(BSLClientApplicationForm.EVENTS)
    if main_seen and document_schema is None:
        allowed.add('beforewriteatserver')
    bindings = _events(props.get(L+'Events'), allowed)
    write_handler = bindings.pop('beforewriteatserver', '')
    definition = FormDefinition(public_name, identity, sha256(raw+b'\0'+module).hexdigest(), program,
        tuple(attrs), MappingProxyType(bindings), _value(props,'Title'), tuple(items), tuple(commands),
        catalog_schema, object_fields, write_handler, document_schema, object_sections, tables,
        reference_targets if reference_slots else (), tuple(reference_slots), posting_application, tuple(layout) if has_groups else (), enum_targets if reference_slots else ())
    # Validate every declared handler and all reserved-name collisions eagerly.
    validation_server = definition.create_server(_validate_only=True)
    validation_server.session.interpreter.close()
    return definition


def load_configuration_forms(files, *, catalog_schemas=(), document_schemas=(), reference_catalogs=(), posting_application=False, enum_definitions=()):
    """Load declared CommonForms and Catalog/Document custom forms, explicitly."""
    accepted = _accept_source_files(files)
    schemas = {schema.name.casefold(): schema for schema in catalog_schemas}
    documents = {schema.name.casefold(): schema for schema in document_schemas}
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
                entries.append((kind+'.'+value+'.Form.'+form_name, prefix+'/Forms/'+form_name, 'Form', form_name, schemas.get(value.casefold()) if kind == 'Catalog' else documents.get(value.casefold())))
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
        is_document = public_name.startswith('Document.')
        definition = _definition(public_name, uid, files[path], files.get(module,b''),
            None if is_document else schema, schema if is_document else None, reference_catalogs, posting_application and is_document, enum_definitions)
        if public_name.casefold() in forms:
            raise ValueError('duplicate form name')
        forms[public_name.casefold()] = definition
    digest = sha256()
    for entry in accepted:
        digest.update(entry.path.encode('utf-8')+b'\0'+files[entry.path]+b'\0')
    return ConfigurationForms(identity, config_name, digest.hexdigest(), MappingProxyType(forms), MappingProxyType(dict(files)))
