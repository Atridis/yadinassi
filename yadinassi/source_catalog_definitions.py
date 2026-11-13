"""Closed source-catalog storage declarations; no module or database activation."""
from dataclasses import dataclass
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


def catalog_definition_record(definition):
    return [str(definition.identity), definition.name,
            [[str(f.identity), f.name, f.kind, f.qualifiers, f.type_dependencies]
             for f in definition.fields]]


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
            if any(path.startswith(prefix) and path.lower().endswith('/objectmodule.bsl') and raw.strip()
                   for path,raw in files.items()):
                raise ValueError('catalog object module unsupported')
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
                if kind not in ('string','number','boolean','datetime'):
                    raise ValueError('catalog attribute requires scalar type')
                fields.append(ScalarConstantDefinition(identity,fn,kind,qualifiers,
                    enum_namespace=enum_namespace,type_dependencies=dependencies,reference_scope=reference_scope))
                if len(fields)>67:
                    raise ValueError('catalog attribute count bound')
            definitions[name.casefold()] = SourceCatalogDefinition(entry.identity,name,tuple(fields))
        except (ValueError,KeyError,AttributeError) as error:
            unsupported[entry.name.casefold()] = str(error)
    return definitions, unsupported
