"""Full, fresh-only source grant for scalar recorder document applications.

The core projection is a validation intermediate, never the original source.
Both the form command manifest and all executable bytes remain in the full
canonical source. The older document-recorder-scalar-v1 importer is unchanged.
"""
from dataclasses import dataclass
from hashlib import sha256
import xml.etree.ElementTree as ET

from . import configuration_xml as xml
from .configuration_posting import import_posting_configuration, PROFILE as CORE_PROFILE

PROFILE = 'document-recorder-forms-v1'
MANIFEST = 'PostingApplication.xml'
NAMESPACE = 'urn:yadinassi:posting-application:1'
MODES = ('Write', 'Post', 'UndoPosting')


@dataclass(frozen=True, slots=True)
class PostingCommandGrant:
    form: str
    command: str
    command_id: int
    mode: str


@dataclass(frozen=True, slots=True)
class PostingApplicationConfiguration:
    identity: object
    name: str
    files: tuple
    documents: tuple
    registers: tuple
    handlers: tuple
    profile: str
    source_digest: str
    commands: tuple
    core_projection_digest: str


def _commands(raw, forms, source):
    root, _ = xml._parse(raw)
    n = '{' + NAMESPACE + '}'
    if (root.tag != n+'PostingApplication' or root.attrib != {'version': '1'}
            or (root.text or '').strip() or not 1 <= len(root) <= 64):
        raise ValueError('explicit posting command manifest required')
    grants = []; seen = set()
    for node in root:
        name = node.get('name', '')
        definition = forms.get(name.casefold())
        if (node.tag != n+'Form' or set(node.attrib) != {'name'} or definition is None
                or name != definition.name or name in seen or (node.text or '').strip()
                or (node.tail or '').strip() or len(node) != len(MODES)):
            raise ValueError('exact declared posting form required')
        seen.add(name)
        declared = {c[0]: c[2] for c in definition.commands}
        parts = name.split('.')
        form_xml, _ = xml._parse(source['Documents/'+parts[1]+'/Forms/'+parts[3]+'/Ext/Form.xml'])
        l = '{http://v8.1c.ru/8.3/xcf/logform}'
        ids = {c.get('name'): c.get('id') for c in form_xml.find(l+'Commands')}
        from .syntax import ast
        routines = {r.name.casefold(): r for r in definition.program.client.program() if type(r) is ast.Routine}
        modes = set(); commands = set()
        for command in node:
            key, mode = command.get('name'), command.get('mode')
            if (command.tag != n+'Command' or set(command.attrib) != {'name', 'id', 'mode'}
                    or len(command) or (command.text or '').strip() or (command.tail or '').strip()
                    or key not in declared or command.get('id') != ids.get(key)
                    or key in commands or mode not in MODES or mode in modes):
                raise ValueError('exact source-granted posting command required')
            routine = routines.get(declared[key].casefold())
            if (routine is None or routine.body or routine.is_function or routine.is_async
                    or routine.is_dual or len(routine.parameters) != 1
                    or routine.parameters[0].default is not None):
                raise ValueError('posting host command requires an empty synchronous client handler')
            commands.add(key); modes.add(mode)
            grants.append(PostingCommandGrant(name, key, int(command.get('id')), mode))
    if seen != {d.name for d in forms.values()}:
        raise ValueError('all posting forms require explicit host commands')
    return tuple(grants)


def import_posting_application(files, *, posting_runtime=None):
    if type(posting_runtime) is not str or posting_runtime != PROFILE:
        raise ValueError('explicit posting application source grant required')
    accepted = xml._accept_source_files(files)
    source = {entry.path: entry.content for entry in accepted}
    if MANIFEST not in source:
        raise ValueError('posting command manifest missing')
    m = '{'+xml.MD+'}'
    config, _ = xml._object(source['Configuration.xml'], 'Configuration')
    children = config.findall(m+'ChildObjects')
    if (len(children) != 1 or children[0].attrib or (children[0].text or '').strip()):
        raise ValueError('posting declaration envelope')
    expected = {'Configuration.xml', MANIFEST}
    projected = {'Configuration.xml': source['Configuration.xml']}
    form_names = set()
    for child in children[0]:
        if child.tag not in (m+'Document', m+'InformationRegister'):
            raise ValueError('posting application metadata family')
        if child.attrib or len(child) or (child.tail or '').strip():
            raise ValueError('posting declaration shape')
        name = xml._name(child.text or '')
        if child.tag == m+'InformationRegister':
            path = 'InformationRegisters/'+name+'.xml'
            expected.add(path); projected[path] = source[path]
            continue
        path = 'Documents/'+name+'.xml'
        obj, namespaces, root = xml._object(source[path], 'Document', include_root=True)
        props = xml._props(obj)
        default = props.get(m+'DefaultObjectForm')
        if (default is None or default.attrib or len(default) or (default.tail or '').strip()):
            raise ValueError('posting default object form required')
        default_name = default.text or ''
        obj.find(m+'Properties').remove(default)
        inventories = obj.findall(m+'ChildObjects')
        if len(inventories) != 1 or inventories[0].attrib or (inventories[0].text or '').strip():
            raise ValueError('posting document inventory')
        inventory = inventories[0]; owned = []
        for entry in list(inventory):
            if entry.tag == m+'Form':
                if entry.attrib or len(entry) or (entry.tail or '').strip():
                    raise ValueError('posting form declaration shape')
                form = xml._name(entry.text or '')
                public = 'Document.'+name+'.Form.'+form
                if public.casefold() in form_names:
                    raise ValueError('duplicate posting form')
                form_names.add(public.casefold()); owned.append(public)
                prefix = 'Documents/'+name+'/Forms/'+form
                expected.update((prefix+'.xml', prefix+'/Ext/Form.xml'))
                module = prefix+'/Ext/Form/Module.bsl'
                if module in source: expected.add(module)
                inventory.remove(entry)
            elif entry.tag not in (m+'Attribute', m+'TabularSection'):
                raise ValueError('unsupported posting document child')
        if default_name not in owned:
            raise ValueError('undeclared posting default form')
        # ElementTree rewrites namespace prefixes. Preserve QName-valued type
        # and recorder attributes explicitly in the temporary projection.
        for node in root.iter():
            qnames = []
            if node.tag == '{'+xml.V8+'}Type': qnames.append(node.text or '')
            value = node.get('{http://www.w3.org/2001/XMLSchema-instance}type')
            if value is not None: qnames.append(value)
            for value in qnames:
                if ':' in value:
                    prefix = value.split(':', 1)[0]
                    uri = namespaces[id(node)].get(prefix)
                    if uri is None: raise ValueError('unknown posting QName namespace')
                    node.set('xmlns:'+prefix, uri)
        expected.add(path); projected[path] = ET.tostring(root, encoding='utf-8')
        module = 'Documents/'+name+'/Ext/ObjectModule.bsl'
        expected.add(module); projected[module] = source[module]
    if set(source) != expected:
        raise ValueError('unexpected or missing posting application source')
    core = import_posting_configuration(projected, posting_runtime=CORE_PROFILE)
    from .configuration_document import require_document_form_schema
    from .configuration_forms import load_configuration_forms
    for document in core.documents: require_document_form_schema(document)
    forms = load_configuration_forms(source, document_schemas=core.documents, posting_application=True)
    if set(forms.forms) != form_names or any(d.document_schema is None for d in forms.forms.values()):
        raise ValueError('unbound posting form')
    commands = _commands(source[MANIFEST], forms.forms, source)
    identities = [core.identity, *(d.identity for d in core.documents),
        *(f.identity for d in core.documents for f in d.fields),
        *(s.identity for d in core.documents for s in d.tabular_sections),
        *(f.identity for d in core.documents for s in d.tabular_sections for f in s.fields),
        *(r.identity for r in core.registers), *(f.identity for r in core.registers for f in r.fields),
        *(d.identity for d in forms.forms.values())]
    if len(identities) != len(set(identities)):
        raise ValueError('duplicate posting application metadata identity')
    original = tuple(sorted(source.items()))
    digest = sha256(b''.join(path.encode()+b'\0'+sha256(raw).digest() for path, raw in original)).hexdigest()
    return PostingApplicationConfiguration(core.identity, core.name, original, core.documents,
        core.registers, core.handlers, PROFILE, digest, commands, core.source_digest)


def canonical(configuration):
    if type(configuration) is not PostingApplicationConfiguration or configuration.profile != PROFILE:
        raise ValueError('posting application configuration required')
    fresh = import_posting_application(dict(configuration.files), posting_runtime=PROFILE)
    if fresh != configuration: raise ValueError('posting application source/schema divergence')
    return fresh


def canonical_runtime(configuration):
    """Exact distinct grants, not a relaxation of the original core importer."""
    if type(configuration) is PostingApplicationConfiguration: return canonical(configuration)
    from .configuration_posting import canonical as core_canonical
    return core_canonical(configuration)


def import_variant(files, profile):
    if profile == PROFILE: return import_posting_application(files, posting_runtime=PROFILE)
    return import_posting_configuration(files, posting_runtime=profile)
