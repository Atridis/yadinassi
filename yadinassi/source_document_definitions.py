"""Closed source-document storage declarations; no module or database activation."""
from dataclasses import dataclass
from .errors import BSLError
from uuid import uuid5
from .configuration_source import ConfigurationSource
from .configuration_source_constants import ScalarConstantDefinition, _constant_type
from .configuration_xml import MD, _object, _props, _text, _uuid, _name, _int
from .source_defined_types import SourceDefinedTypes


@dataclass(frozen=True, slots=True)
class SourceDocumentDefinition:
    identity: object
    name: str
    fields: tuple
    sections: tuple = ()
    object_module: str | None = None
    write_blockers: tuple = ()


@dataclass(frozen=True, slots=True)
class SourceDocumentSectionDefinition:
    identity: object
    name: str
    fields: tuple


def document_definition_record(definition):
    record = [str(definition.identity), definition.name,
            [[str(f.identity), f.name, f.kind, f.qualifiers, f.type_dependencies]
             for f in definition.fields]]
    if definition.sections:
        record.append(['sections', [[str(section.identity), section.name,
            [[str(f.identity),f.name,f.kind,f.qualifiers,f.type_dependencies] for f in section.fields]]
            for section in definition.sections]])
    if definition.object_module is not None:
        record.append(['object_module',definition.object_module,list(definition.write_blockers)])
    return record


_INERT = {'Name', 'Synonym', 'Comment', 'ObjectPresentation', 'ExtendedObjectPresentation',
          'ListPresentation', 'ExtendedListPresentation', 'Explanation'}
_POLICIES = {'Autonumbering': 'false', 'CheckUnique': 'true', 'NumberPeriodicity': 'Nonperiodical', 'Posting':'Deny', 'DataHistory':'DontUse', 'FillChecking':'DontCheck', 'FillFromFillingValue':'false'}

_RESERVED = {n.casefold() for n in ('Number','Номер','Date','Дата','Posted','Проведен','DeletionMark',
    'ПометкаУдаления','Ref','Ссылка','Read','Прочитать','Write','Записать','IsNew','ЭтоНовый',
    'Metadata','Метаданные','GetObject','ПолучитьОбъект','ThisObject','ЭтотОбъект',
    'Parent','Родитель','IsFolder','ЭтоГруппа','Owner','Владелец')}


def _policies(props, *, attribute=False):
    extra = {'Type'} if attribute else {'NumberType','NumberLength'}
    for tag, node in props.items():
        if not tag.startswith('{'+MD+'}'):
            raise ValueError('unknown document property namespace')
        name = tag[len(MD)+2:]
        if name in _INERT or name in extra:
            continue
        if name not in _POLICIES:
            raise ValueError('unsupported document property: '+name)
        if node.attrib or len(node) or (node.text or '').strip() != _POLICIES[name]:
            raise ValueError('unsupported document behavior: '+name)


def source_document_definitions(source, enum_namespace=None, reference_scope=None, *, allow_sections=False):
    if type(source) is not ConfigurationSource:
        raise TypeError('admitted ConfigurationSource required')
    from .configuration_source_enums import source_enum_definitions
    from .enumerations import BSLEnumerations
    enums,enum_errors,_=source_enum_definitions(source)
    if enum_namespace is None:
        enum_namespace=BSLEnumerations(enums,unsupported=enum_errors)
    elif (type(enum_namespace) is not BSLEnumerations
          or tuple(m._definition for m in enum_namespace.metadata)!=enums
          or enum_namespace._unsupported!=enum_errors):
        raise ValueError('record enumeration namespace/source mismatch')
    from .source_references import SourceReferences
    if reference_scope is None:
        from .configuration_source_metadata import SourceMetadataRoot
        reference_scope = SourceReferences(source, SourceMetadataRoot(source))
    elif type(reference_scope) is not SourceReferences or reference_scope.source != source:
        raise ValueError('source document reference scope mismatch')
    files = {f.path:f.content for f in source.files}
    aliases = SourceDefinedTypes(source)
    definitions, unsupported = {}, {}
    documents = [e for e in source.metadata if e.family == 'Document']
    global_block = any(e.family in ('CommonAttribute','EventSubscription') for e in source.metadata)
    for entry in documents:
        try:
            if len(documents) > 1024:
                raise ValueError('document count bound')
            if global_block:
                raise ValueError('document subscriptions/data separation unsupported')
            obj, ns = _object(files[entry.path], 'Document')
            props = _props(obj)
            name = _name(_text(props,'Name'))
            if name != entry.name or _uuid(obj.get('uuid')) != entry.identity:
                raise ValueError('document identity mismatch')
            _policies(props)
            for policy in ('Autonumbering','CheckUnique','NumberPeriodicity','Posting'):
                if _text(props,policy) != _POLICIES[policy]:
                    raise ValueError('explicit document policy required: '+policy)
            for scalar in ('NumberType','NumberLength'):
                node = props.get('{'+MD+'}'+scalar)
                if node is not None and (node.attrib or len(node)):
                    raise ValueError('structured document qualifier')
            if _text(props,'NumberType') != 'String':
                raise ValueError('document requires explicit String Number')
            number_length = _int(props,'NumberLength',1,9)
            prefix = entry.path[:-4]+'/'
            module_path=prefix+'Ext/ObjectModule.bsl'
            module_files=[path for path,raw in files.items() if path.startswith(prefix) and path.lower().endswith('/objectmodule.bsl') and raw.strip()]
            if any(path!=module_path for path in module_files):raise ValueError('document module path unsupported')
            module_path=module_path if module_files else None
            if any(n.tag not in ('{'+MD+'}Properties','{'+MD+'}ChildObjects') for n in obj):
                raise ValueError('unsupported document object component')
            children = obj.findall('{'+MD+'}ChildObjects')
            if len(children)>1:
                raise ValueError('duplicate document children')
            fields = [ScalarConstantDefinition(uuid5(entry.identity,'source-standard:'+n),n,k,q)
                      for n,k,q in (('Number','string',(number_length,)), ('Date','datetime',('DateTime',)),
                                    ('DeletionMark','boolean',()), ('Posted','boolean',()))]
            used_names = set(_RESERVED)
            used_ids = {e.identity for e in source.metadata} | {f.identity for f in fields}
            sections = []
            def parse_field(child, field_names):
                    if set(child.attrib) != {'uuid'} or any(n.tag!='{'+MD+'}Properties' for n in child):
                        raise ValueError('unsupported document attribute envelope')
                    p = _props(child); _policies(p,attribute=True)
                    fn = _name(_text(p,'Name')); identity = _uuid(child.get('uuid'))
                    if fn.casefold() in field_names or identity in used_ids:
                        raise ValueError('document attribute identity/name collision')
                    field_names.add(fn.casefold()); used_ids.add(identity)
                    resolved, scopes, dependencies = aliases.resolve(p,ns)
                    kind, qualifiers = _constant_type(resolved,scopes,enum_namespace,reference_scope)
                    if kind not in ('string','number','boolean','datetime','enum_ref') and not (kind == 'object_ref' and qualifiers[0] in ('Catalog','Document')):
                        raise ValueError('document attribute requires scalar, EnumRef or CatalogRef/DocumentRef type')
                    return ScalarConstantDefinition(identity,fn,kind,qualifiers,
                        enum_namespace=enum_namespace,type_dependencies=dependencies,reference_scope=reference_scope)
            for child in children[0] if children else ():
                if child.tag == '{'+MD+'}Attribute':
                    fields.append(parse_field(child, used_names))
                    if len(fields)>68:raise ValueError('document attribute count bound')
                elif child.tag == '{'+MD+'}TabularSection' and allow_sections:
                    if set(child.attrib)!={'uuid'} or any(n.tag not in ('{'+MD+'}Properties','{'+MD+'}ChildObjects') for n in child):
                        raise ValueError('unsupported section envelope')
                    sp=_props(child)
                    if any(tag not in {'{'+MD+'}'+n for n in _INERT} for tag in sp):
                        raise ValueError('unsupported section policy')
                    sn=_name(_text(sp,'Name'));sid=_uuid(child.get('uuid'))
                    if sn.casefold() in used_names or sid in used_ids:raise ValueError('section identity/name collision')
                    used_names.add(sn.casefold());used_ids.add(sid)
                    containers=child.findall('{'+MD+'}ChildObjects')
                    if len(containers)>1:raise ValueError('duplicate section children')
                    field_names=set(_RESERVED)|{'linenumber','номерстроки'}
                    section_fields=[]
                    for field in containers[0] if containers else ():
                        if field.tag!='{'+MD+'}Attribute':raise ValueError('unsupported section child')
                        section_fields.append(parse_field(field,field_names))
                    if not 1<=len(section_fields)<=64:raise ValueError('section field count bound')
                    sections.append(SourceDocumentSectionDefinition(sid,sn,tuple(section_fields)))
                    if len(sections)>16:raise ValueError('section count bound')
                else:raise ValueError('document tabular sections/child kind unsupported')
            blockers=()
            if module_path is not None:
                _,blockers=document_module_program(files[module_path],module_path,fields,sections)
            definitions[name.casefold()] = SourceDocumentDefinition(entry.identity,name,tuple(fields),tuple(sections),module_path,blockers)
        except (ValueError,KeyError,AttributeError,BSLError) as error:
            unsupported[entry.name.casefold()] = str(error)
    return definitions, unsupported


# Event declarations are checked before any initializer runs. Only OnWrite is
# executable in this source profile; all other known events block Write.
_EVENT_SPECS=(
    (('onwrite','призаписи'),1,True),
    (('beforewrite','передзаписью'),3,True),
    (('posting','обработкапроведения'),2,True),
    (('undoposting','обработкаудаленияпроведения'),1,True),
    (('fillcheckprocessing','обработкапроверкизаполнения'),2,True),
    (('onread','причтении'),0,False),
    (('beforedelete','передудалением'),1,True),
    (('oncopy','прикопировании'),1,False),
    (('fillingprocessing','обработказаполнения'),2,False),
)
_OTHER_EVENTS={'choiceprocessing','обработкавыбора','presentationgetprocessing','обработкаполученияпредставления'}

def document_module_program(raw,path,fields,sections=()):
    from .configuration_modules import compile_module
    from .syntax import ast
    program=compile_module(raw,path,'server',common=False)
    reserved=_RESERVED|{f.name.casefold() for f in fields}|{s.name.casefold() for s in sections}|{'__document_cancel'}
    routines=[n for n in program if type(n) is ast.Routine]
    for node in program:
        if type(node) is ast.Var and any(n.casefold() in reserved for n in node.names):raise ValueError('document module reserved field conflict')
        if type(node) is ast.Routine and (node.is_async or node.name.casefold() in reserved or any(p.name.casefold() in reserved for p in node.parameters)):
            raise ValueError('document module reserved/async routine unsupported')
    # Field-first object lookup must not silently discard a local declaration.
    pending=list(program)
    while pending:
        node=pending.pop()
        if isinstance(node,ast.Node):
            if type(node) is ast.Var and any(name.casefold() in reserved for name in node.names):
                raise ValueError('document module reserved local field conflict')
            pending.extend(value for key,value in vars(node).items() if key!='token')
        elif isinstance(node,(list,tuple)):
            pending.extend(node)
    blockers=[]
    for aliases,arity,cancel in _EVENT_SPECS:
        matches=[r for r in routines if r.name.casefold() in aliases]
        if len(matches)>1:raise ValueError('ambiguous document event')
        if matches:
            routine=matches[0]
            if routine.is_function or len(routine.parameters)!=arity or any(p.default is not None for p in routine.parameters) or (cancel and routine.parameters[0].by_value):
                raise ValueError('unsupported document event signature')
            if aliases[0]!='onwrite':blockers.append(aliases[0])
    blockers.extend(sorted({r.name.casefold() for r in routines}&_OTHER_EVENTS))
    return program,tuple(sorted(blockers))
