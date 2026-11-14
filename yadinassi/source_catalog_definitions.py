"""Closed source-catalog storage declarations; no module or database activation."""
from dataclasses import dataclass
from .errors import BSLError
from uuid import uuid5
from .configuration_source import ConfigurationSource
from .configuration_source_constants import ScalarConstantDefinition, _constant_type
from .configuration_xml import MD, _object, _props, _text, _uuid, _name, _int
from .source_defined_types import SourceDefinedTypes


@dataclass(frozen=True, slots=True)
class SourceCatalogDefinition:
    identity: object
    name: str
    fields: tuple
    object_module: str | None = None


def catalog_definition_record(definition):
    record = [str(definition.identity), definition.name,
            [[str(f.identity), f.name, f.kind, f.qualifiers, f.type_dependencies]
             for f in definition.fields]]
    if definition.object_module is not None:
        record.append(["object_module", definition.object_module])
    return record


_INERT = {'Name', 'Synonym', 'Comment', 'ObjectPresentation', 'ExtendedObjectPresentation',
          'ListPresentation', 'ExtendedListPresentation', 'Explanation'}
_POLICIES = {'Hierarchical': 'false', 'Autonumbering': 'false', 'CheckUnique': 'true',
             'CodeSeries': 'WholeCatalog', 'DataHistory': 'DontUse',
             'FillChecking': 'DontCheck', 'FillFromFillingValue': 'false'}
_RESERVED = {n.casefold() for n in ('Code','Код','Description','Наименование','DeletionMark',
    'ПометкаУдаления','Ref','Ссылка','Read','Прочитать','Write','Записать','IsNew','ЭтоНовый',
    'Metadata','Метаданные','GetObject','ПолучитьОбъект','ThisObject','ЭтотОбъект',
    'Parent','Родитель','IsFolder','ЭтоГруппа','Owner','Владелец')}


def _policies(props, *, attribute=False):
    extra = {'Type'} if attribute else {'CodeType','CodeLength','DescriptionLength','Owners','HierarchyType'}
    for tag, node in props.items():
        if not tag.startswith('{'+MD+'}'):
            raise ValueError('unknown catalog property namespace')
        name = tag[len(MD)+2:]
        if name in _INERT or name in extra:
            continue
        if name not in _POLICIES:
            raise ValueError('unsupported catalog property: '+name)
        if node.attrib or len(node) or (node.text or '').strip() != _POLICIES[name]:
            raise ValueError('unsupported catalog behavior: '+name)
    if not attribute:
        owners = props.get('{'+MD+'}Owners')
        if owners is not None and (owners.attrib or len(owners) or (owners.text or '').strip()):
            raise ValueError('catalog owners unsupported')


def source_catalog_definitions(source, enum_namespace=None, reference_scope=None):
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
        raise ValueError('source catalog reference scope mismatch')
    files = {f.path:f.content for f in source.files}
    aliases = SourceDefinedTypes(source)
    definitions, unsupported = {}, {}
    catalogs = [e for e in source.metadata if e.family == 'Catalog']
    global_block = any(e.family in ('CommonAttribute','EventSubscription') for e in source.metadata)
    for entry in catalogs:
        try:
            if len(catalogs) > 1024:
                raise ValueError('catalog count bound')
            if global_block:
                raise ValueError('catalog subscriptions/data separation unsupported')
            obj, ns = _object(files[entry.path], 'Catalog')
            props = _props(obj)
            name = _name(_text(props,'Name'))
            if name != entry.name or _uuid(obj.get('uuid')) != entry.identity:
                raise ValueError('catalog identity mismatch')
            _policies(props)
            for policy in ('Hierarchical','Autonumbering','CheckUnique','CodeSeries'):
                if _text(props,policy) != _POLICIES[policy]:
                    raise ValueError('explicit catalog policy required: '+policy)
            for scalar in ('CodeType','CodeLength','DescriptionLength','HierarchyType'):
                node = props.get('{'+MD+'}'+scalar)
                if node is not None and (node.attrib or len(node)):
                    raise ValueError('structured catalog qualifier')
            if _text(props,'CodeType') != 'String':
                raise ValueError('catalog requires explicit String Code')
            code_length = _int(props,'CodeLength',1,64)
            description_length = _int(props,'DescriptionLength',1,1024)
            prefix = entry.path[:-4]+'/'
            module_path = prefix+'Ext/ObjectModule.bsl'
            module_files = [path for path,raw in files.items() if path.startswith(prefix)
                            and path.lower().endswith('/objectmodule.bsl') and raw.strip()]
            if any(path != module_path for path in module_files):
                raise ValueError('catalog object module location unsupported')
            module_path = module_path if module_files else None
            if any(n.tag not in ('{'+MD+'}Properties','{'+MD+'}ChildObjects') for n in obj):
                raise ValueError('unsupported catalog object component')
            children = obj.findall('{'+MD+'}ChildObjects')
            if len(children)>1:
                raise ValueError('duplicate catalog children')
            fields = [ScalarConstantDefinition(uuid5(entry.identity,'source-standard:'+n),n,k,q)
                      for n,k,q in (('Code','string',(code_length,)),
                                    ('Description','string',(description_length,)),
                                    ('DeletionMark','boolean',()))]
            used_names = set(_RESERVED)
            used_ids = {e.identity for e in source.metadata} | {f.identity for f in fields}
            for child in children[0] if children else ():
                if child.tag != '{'+MD+'}Attribute':
                    raise ValueError('catalog tabular sections/child kind unsupported')
                if set(child.attrib) != {'uuid'} or any(n.tag!='{'+MD+'}Properties' for n in child):
                    raise ValueError('unsupported catalog attribute envelope')
                p = _props(child); _policies(p,attribute=True)
                fn = _name(_text(p,'Name')); identity = _uuid(child.get('uuid'))
                if fn.casefold() in used_names or identity in used_ids:
                    raise ValueError('catalog attribute identity/name collision')
                used_names.add(fn.casefold()); used_ids.add(identity)
                resolved, scopes, dependencies = aliases.resolve(p,ns)
                kind, qualifiers = _constant_type(resolved,scopes,enum_namespace,reference_scope)
                if kind not in ('string','number','boolean','datetime','enum_ref') and not (kind == 'object_ref' and qualifiers[0] in ('Catalog','Document')):
                    raise ValueError('catalog attribute requires scalar, EnumRef or CatalogRef/DocumentRef type')
                fields.append(ScalarConstantDefinition(identity,fn,kind,qualifiers,
                    enum_namespace=enum_namespace,type_dependencies=dependencies,reference_scope=reference_scope))
                if len(fields)>67:
                    raise ValueError('catalog attribute count bound')
            if module_path is not None:
                catalog_module_program(files[module_path],module_path,fields)
            definitions[name.casefold()] = SourceCatalogDefinition(entry.identity,name,tuple(fields),module_path)
        except (ValueError,KeyError,AttributeError,BSLError) as error:
            unsupported[entry.name.casefold()] = str(error)
    return definitions, unsupported


_EVENT_NAMES = (('beforewrite','передзаписью'), ('onwrite','призаписи'))
_UNSUPPORTED_EVENTS = {'fillcheckprocessing','обработкапроверкизаполнения','onread','причтении',
    'beforedelete','передудалением','oncopy','прикопировании','filling','fillingprocessing','обработказаполнения',
    'choiceprocessing','обработкавыбора','presentationgetprocessing','обработкаполученияпредставления'}

def catalog_module_program(raw,path,fields):
    """Compile and validate declarations only, never execute during admission."""
    from .configuration_modules import compile_module
    from .syntax import ast
    program=compile_module(raw,path,'server',common=False)
    reserved=_RESERVED | {f.name.casefold() for f in fields} | {'__catalog_cancel'}
    routines=[node for node in program if type(node) is ast.Routine]
    for node in program:
        if type(node) is ast.Var and any(n.casefold() in reserved for n in node.names):
            raise ValueError('catalog module reserved field conflict')
        if type(node) is ast.Routine:
            if (node.name.casefold() in reserved or node.is_async
                    or any(p.name.casefold() in reserved for p in node.parameters)):
                raise ValueError('catalog module reserved/async routine unsupported')
            if node.name.casefold() in _UNSUPPORTED_EVENTS:
                raise ValueError('catalog object event unsupported: '+node.name)
    for aliases in _EVENT_NAMES:
        matches=[r for r in routines if r.name.casefold() in aliases]
        if len(matches)>1:
            raise ValueError('ambiguous catalog write event')
        if matches:
            r=matches[0]
            if r.is_function or len(r.parameters)!=1 or r.parameters[0].by_value or r.parameters[0].default is not None:
                raise ValueError('unsupported catalog event signature')
    return program
