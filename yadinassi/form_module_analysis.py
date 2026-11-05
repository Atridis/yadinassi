"""Bounded static catalog-form description, never an execution/activation grant.

The v1 profile describes the complete two-handler name-validation workflow.
It is deliberately not a general BSL sandbox, FormData, or configuration importer.
"""
from dataclasses import dataclass, fields
from decimal import Decimal
from hashlib import sha256
from io import StringIO
import re
from uuid import UUID
from xml.etree import ElementTree as ET

from .errors import BSLError
from .syntax import ast
from .syntax.lexer import KEYWORDS, Lexer
from .syntax.parser import Parser

PROFILE = 'catalog-form-name-validation-static-v1'
NATIVE_PARITY = False
MAX_SOURCE_BYTES = 16384
MAX_XML_BYTES = 32768
MAX_TOKENS = 512
MAX_AST_NODES = 256
MAX_DEPTH = 24
MAX_XML_NODES = 256
MAX_TEXT = 1024
_MD = 'http://v8.1c.ru/8.3/MDClasses'
_FORM = 'http://v8.1c.ru/8.3/xcf/logform'
_CORE = 'http://v8.1c.ru/8.1/data/core'
_IDENTIFIER = re.compile(r'[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]{0,127}')
_TOKENS = frozenset(('EOF', 'ATCLIENT', 'ATSERVER', 'PROCEDURE', 'ENDPROCEDURE',
    'IDENT', 'IF', 'THEN', 'ENDIF', 'RETURN', 'NEW', 'TRUE', 'NUMBER', 'STRING',
    '(', ')', ';', '.', ',', '=', '<'))
_SHAPES = {
    ast.Routine: ('name', 'parameters', 'is_function', 'exported', 'body', 'execution_context', 'is_async', 'module_context', 'is_dual'),
    ast.Parameter: ('name', 'by_value', 'default'), ast.Assign: ('target', 'value'),
    ast.If: ('branches', 'otherwise'), ast.Return: ('value',),
    ast.ExpressionStatement: ('expression',), ast.Call: ('callee', 'arguments'),
    ast.New: ('name', 'arguments'), ast.Name: ('name',),
    ast.Attribute: ('object', 'name'), ast.Literal: ('value',),
    ast.Binary: ('left', 'operator', 'right'),
}


class FormModuleAnalysisError(ValueError):
    """Closed diagnostic with no source text or host exception detail."""


def _fail(reason):
    raise FormModuleAnalysisError('form module analysis: ' + reason) from None


@dataclass(frozen=True, slots=True)
class FormModuleBinding:
    """Host commitment, not independently authenticated metadata provenance."""
    database_id: UUID
    configuration_id: UUID
    configuration_generation: int
    catalog_id: UUID
    catalog_name: str
    form_id: UUID
    form_name: str
    source_sha256: str
    catalog_sha256: str
    form_sha256: str
    definition_sha256: str


@dataclass(frozen=True, slots=True)
class ScalarFieldDescription:
    item_name: str
    metadata_path: str
    source_path: str
    scalar_kind: str
    maximum_length: int
    read_only: bool


@dataclass(frozen=True, slots=True)
class FormEventDescription:
    event: str
    handler: str
    execution_context: str
    parameters: tuple
    message_text: str
    message_field: str


@dataclass(frozen=True, slots=True)
class FormModuleAnalysis:
    binding: FormModuleBinding
    source: bytes
    catalog_path: str
    form_path: str
    definition_path: str
    module_path: str
    fields: tuple
    events: tuple
    ast_nodes: int
    profile: str = PROFILE
    native_parity: bool = NATIVE_PARITY


def _name(value):
    if type(value) is not str or not _IDENTIFIER.fullmatch(value) or value.casefold() in KEYWORDS:
        _fail('identifier')
    return value


def _bytes(raw, digest, limit):
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        _fail('byte budget')
    if type(digest) is not str or not re.fullmatch('[0-9a-f]{64}', digest):
        _fail('hash format')
    if sha256(raw).hexdigest() != digest:
        _fail('hash mismatch')


def _xml(raw, *, with_namespaces=False):
    # Ban DTDs, entities, comments and CDATA before parsing. Byte bounds apply
    # before decoding; UTF-16 cannot hide declaration characters.
    try:
        text = raw.decode('utf-8-sig')
        without_declaration = re.sub(r'^<\?xml\s+[^?]*\?>', '', text, count=1)
        if '<!' in text or '<?' in without_declaration or '\x00' in text:
            _fail('XML declarations')
        parser = ET.iterparse(StringIO(text), events=('start-ns', 'start', 'end'))
        scopes = {}; stack = []; declarations = []; count = 0
        for event, value in parser:
            if event == 'start-ns':
                declarations.append(value)
            elif event == 'start':
                count += 1
                if count > MAX_XML_NODES or len(stack) > MAX_DEPTH:
                    _fail('XML budget')
                scope = dict(stack[-1]) if stack else {}
                scope.update(declarations); declarations.clear()
                stack.append(scope)
                if with_namespaces: scopes[value] = scope
            else:
                stack.pop()
        root = parser.root
    except (UnicodeError, ET.ParseError):
        _fail('XML syntax')
    return (root, scopes) if with_namespaces else root


def _one(root, path):
    found = root.findall(path)
    if len(found) != 1:
        _fail('metadata cardinality')
    return found[0]


def _leaf(root, path):
    node = _one(root, path)
    if len(node):
        _fail('metadata leaf')
    return node.text or ''


def _q(namespace, name):
    return '{' + namespace + '}' + name



def _metadata_structure(root, catalog):
    """Closed XML shape, while non-operative catalog settings remain projections.

    Recognizing a setting here does not assert support for its import semantics.
    """
    md = lambda n: _q(_MD, n)
    core = lambda n: _q(_CORE, n)
    xr = lambda n: _q('http://v8.1c.ru/8.3/xcf/readable', n)
    owner = 'Catalog' if catalog else 'Form'
    catalog_properties = (
        'Name Synonym Comment Hierarchical HierarchyType LimitLevelCount LevelCount '
        'FoldersOnTop UseStandardCommands Owners SubordinationUse CodeLength '
        'DescriptionLength CodeType CodeAllowedLength CodeSeries CheckUnique '
        'Autonumbering DefaultPresentation Characteristics PredefinedDataUpdate '
        'EditType QuickChoice ChoiceMode InputByString SearchStringModeOnInputByString '
        'FullTextSearchOnInputByString ChoiceDataGetModeOnInputByString DefaultObjectForm '
        'DefaultFolderForm DefaultListForm DefaultChoiceForm DefaultFolderChoiceForm '
        'AuxiliaryObjectForm AuxiliaryFolderForm AuxiliaryListForm AuxiliaryChoiceForm '
        'AuxiliaryFolderChoiceForm IncludeHelpInContents BasedOn DataLockFields '
        'DataLockControlMode FullTextSearch ObjectPresentation ExtendedObjectPresentation '
        'ListPresentation ExtendedListPresentation Explanation CreateOnInput '
        'ChoiceHistoryOnInput DataHistory').split()
    properties = catalog_properties if catalog else (
        'Name Synonym Comment FormType IncludeHelpInContents UsePurposes').split()
    shapes = {
        md('MetaDataObject'): (md(owner),),
        md(owner): tuple(md(n) for n in (('InternalInfo', 'Properties', 'ChildObjects') if catalog else ('Properties',))),
        md('Properties'): tuple(md(n) for n in properties),
        md('InternalInfo'): (xr('GeneratedType'),),
        xr('GeneratedType'): (xr('TypeId'), xr('ValueId')),
        md('Synonym'): (core('item'),), core('item'): (core('lang'), core('content')),
        md('InputByString'): (xr('Field'),), md('ChildObjects'): (md('Form'),),
        md('UsePurposes'): (core('Value'),),
    }
    attributes = {
        md('MetaDataObject'): ('version',), md(owner): ('uuid',),
        xr('GeneratedType'): ('name', 'category'),
        core('Value'): (_q('http://www.w3.org/2001/XMLSchema-instance', 'type'),),
    }
    repeats = (md('InternalInfo'), md('InputByString'), md('Synonym'))
    # The nested ChildObjects/Form is a name leaf, not another form owner.
    pending = [(root, False)]
    while pending:
        node, child_form = pending.pop()
        if any(key not in (() if child_form else attributes.get(node.tag, ())) for key in node.attrib):
            _fail('metadata attribute outside profile')
        permitted = () if child_form else shapes.get(node.tag, ())
        if any(child.tag not in permitted for child in node):
            _fail('metadata element outside profile')
        if node.tag not in repeats:
            tags = [child.tag for child in node]
            if len(tags) != len(set(tags)): _fail('duplicate metadata setting')
        if len(node) and ((node.text or '').strip() or any((c.tail or '').strip() for c in node)):
            _fail('metadata mixed text')
        pending.extend((child, node.tag == md('ChildObjects')) for child in node)

def _metadata(binding, catalog_xml, form_xml, definition_xml):
    md = lambda name: _q(_MD, name)
    f = lambda name: _q(_FORM, name)
    catalog_root = _xml(catalog_xml); form_root = _xml(form_xml)
    _metadata_structure(catalog_root, True); _metadata_structure(form_root, False)
    if catalog_root.tag != md('MetaDataObject') or form_root.tag != md('MetaDataObject'):
        _fail('metadata root')
    if len(catalog_root) != 1 or len(form_root) != 1:
        _fail('metadata owner count')
    catalog = _one(catalog_root, md('Catalog')); form = _one(form_root, md('Form'))
    if catalog.get('uuid') != str(binding.catalog_id) or form.get('uuid') != str(binding.form_id):
        _fail('metadata identity')
    cp = _one(catalog, md('Properties')); fp = _one(form, md('Properties'))
    if (_leaf(cp, md('Name')) != binding.catalog_name or
            _leaf(fp, md('Name')) != binding.form_name or
            _leaf(fp, md('FormType')) != 'Managed' or
            _leaf(cp, md('DefaultObjectForm')) !=
            f'Catalog.{binding.catalog_name}.Form.{binding.form_name}'):
        _fail('metadata owner')
    children = _one(catalog, md('ChildObjects'))
    if len(children) != 1 or _leaf(children, md('Form')) != binding.form_name:
        _fail('catalog children outside profile')
    if _leaf(cp, md('CodeType')) != 'String':
        _fail('scalar field type')
    lengths = []
    for name, bound in (('CodeLength', 64), ('DescriptionLength', 1024)):
        value = _leaf(cp, md(name))
        if not re.fullmatch('[1-9][0-9]{0,3}', value) or int(value) > bound:
            _fail('scalar field bounds')
        lengths.append(int(value))
    definition, namespaces = _xml(definition_xml, with_namespaces=True)
    if definition.tag != f('Form'):
        _fail('form root')
    # Entire form-definition structure is closed, including ignored visual leaves.
    allowed = {
        'Form': ('WindowOpeningMode', 'UseForFoldersAndItems', 'AutoCommandBar', 'Events', 'ChildItems', 'Attributes'),
        'Events': ('Event',), 'ChildItems': ('InputField',),
        'InputField': ('DataPath', 'ReadOnly', 'EditMode', 'ContextMenu', 'ExtendedTooltip', 'Events'),
        'Attributes': ('Attribute',), 'Attribute': ('Type', 'MainAttribute', 'SavedData'),
        'Type': (),
    }
    form_attributes = {
        'Form': ('version',), 'AutoCommandBar': ('name', 'id'),
        'InputField': ('name', 'id'), 'ContextMenu': ('name', 'id'),
        'ExtendedTooltip': ('name', 'id'), 'Attribute': ('name', 'id'),
        'Event': ('name',),
    }
    for node in definition.iter():
        local = node.tag.split('}', 1)[-1]
        if any(key not in form_attributes.get(local, ()) for key in node.attrib):
            _fail('form attribute outside profile')
        if node.tag == _q(_CORE, 'Type'):
            if len(node): _fail('form type children')
            continue
        if not node.tag.startswith('{' + _FORM + '}'):
            _fail('form namespace')
        local = node.tag.split('}', 1)[1]
        permitted = allowed.get(local, ())
        for child in node:
            if local == 'Type' and child.tag == _q(_CORE, 'Type'):
                continue
            if child.tag not in tuple(f(n) for n in permitted):
                _fail('form structure')
        # Repeated visual/semantic settings are ambiguous, never last-wins.
        if local not in ('ChildItems',):
            tags = [child.tag for child in node]
            if len(tags) != len(set(tags)):
                _fail('duplicate form setting')
        if len(node) and ((node.text or '').strip() or any((c.tail or '').strip() for c in node)):
            _fail('form mixed text')
    attributes = _one(definition, f('Attributes'))
    attribute = _one(attributes, f('Attribute'))
    if (attribute.get('name') != 'Объект' or
            _leaf(attribute, f('MainAttribute')) != 'true' or
            _leaf(attribute, f('SavedData')) != 'true' or
            _leaf(_one(attribute, f('Type')), _q(_CORE, 'Type')) !=
            'cfg:CatalogObject.' + binding.catalog_name):
        _fail('main object owner')
    # Resolve QName text at its exact use node, not from unrelated declarations.
    type_node = _one(_one(attribute, f('Type')), _q(_CORE, 'Type'))
    if namespaces[type_node].get('cfg') != 'http://v8.1c.ru/8.1/data/enterprise/current-config':
        _fail('main object namespace')
    event = _one(_one(definition, f('Events')), f('Event'))
    server_handler = _name(event.text or '')
    if event.get('name') != 'BeforeWriteAtServer':
        _fail('form event')
    items = _one(definition, f('ChildItems'))
    if len(items) != 2:
        _fail('scalar field count')
    result = []; client_handler = None; seen_names = set()
    for item, canonical, source, length in zip(items, ('Code', 'Description'), ('Код', 'Наименование'), lengths):
        item_name = _name(item.get('name'))
        if item_name.casefold() in seen_names: _fail('field identity collision')
        seen_names.add(item_name.casefold())
        if _leaf(item, f('DataPath')) != 'Объект.' + canonical:
            _fail('scalar field mapping')
        read_only = canonical == 'Code'
        read_values = item.findall(f('ReadOnly'))
        if (read_only and (len(read_values) != 1 or read_values[0].text != 'true') or
                not read_only and read_values and read_values[0].text != 'false'):
            _fail('scalar field access')
        if read_only:
            if item.findall(f('Events')): _fail('read-only event')
        else:
            change = _one(_one(item, f('Events')), f('Event'))
            if change.get('name') != 'OnChange': _fail('field event')
            client_handler = _name(change.text or '')
        result.append(ScalarFieldDescription(item_name, 'Объект.' + canonical,
            'Объект.' + source, 'string', length, read_only))
    if server_handler.casefold() == client_handler.casefold(): _fail('event collision')
    return tuple(result), client_handler, server_handler


def _parse(source):
    try:
        text = source.decode('utf-8-sig')
    except UnicodeError:
        _fail('source encoding')
    # No preprocessor/import directives, even hidden in comments or strings.
    # Only these two annotations may reach the lexer: no body-selection passes.
    annotations = re.findall(r'^\s*&(?:НаКлиенте|AtClient|НаСервере|AtServer)\s*$', text, re.M | re.I)
    if '#' in text or text.count('&') != 2 or len(annotations) != 2:
        _fail('source annotations')
    try:
        tokens = Lexer(text, '<static-form-module>').tokens()
        if len(tokens) > MAX_TOKENS: _fail('token budget')
        nesting = 0
        for token in tokens:
            if token.kind not in _TOKENS: _fail('token outside profile')
            if token.kind in ('(', 'IF', 'PROCEDURE'):
                nesting += 1
                if nesting > MAX_DEPTH: _fail('syntax depth')
            elif token.kind in (')', 'ENDIF', 'ENDPROCEDURE'):
                nesting -= 1
        program = Parser(tokens).parse()
    except (BSLError, RecursionError):
        _fail('source syntax')
    pending = [(program, 0)]; count = 0
    while pending:
        value, depth = pending.pop()
        if isinstance(value, ast.Node):
            shape = tuple(f.name for f in fields(value) if f.name != 'token')
            if _SHAPES.get(type(value)) != shape: _fail('AST outside profile')
            count += 1
            if count > MAX_AST_NODES or depth > MAX_DEPTH: _fail('AST budget')
            pending.extend((getattr(value, field), depth + 1) for field in shape)
        elif type(value) in (tuple, list):
            pending.extend((child, depth) for child in value)
    return program, count


def _shape(node):
    """Private comparison shape only; never returned as executable IR."""
    if type(node) is list: return tuple(_shape(n) for n in node)
    if type(node) is tuple: return tuple(_shape(n) for n in node)
    if type(node) is ast.Literal:
        return ('Literal', type(node.value).__name__, node.value)
    if isinstance(node, ast.Node):
        return (type(node).__name__,) + tuple(_shape(getattr(node, f)) for f in _SHAPES[type(node)])
    return node


def _name_node(name): return ('Name', name)
def _member(owner, member): return ('Attribute', _name_node(owner), member)
def _call(name, *args): return ('Call', _name_node(name), args)


def _body(routine, server):
    # A closed structural profile rather than a permissive recursive evaluator.
    # Every statement/member/call/constructor in both bodies must match.
    owner = 'ТекущийОбъект' if server else 'Объект'
    field = _member(owner, 'Наименование')
    body = routine.body
    offset = 1 if server else 0
    if len(body) != 2 + offset: _fail('event body')
    condition = body[1 + offset]
    if type(condition) is not ast.If or len(condition.branches) != 1 or condition.otherwise:
        _fail('validation branch')
    branch = condition.branches[0][1]
    text_index = 2 if server else 1
    if len(branch) != 4 + offset: _fail('message body')
    assignment = branch[text_index]
    if type(assignment) is not ast.Assign or type(assignment.value) is not ast.Literal:
        _fail('message text')
    message = assignment.value.value
    if type(message) is not str or not 1 <= len(message) <= MAX_TEXT or '\x00' in message:
        _fail('message text')
    message_body = (
        ('Assign', _name_node('Сообщение'), ('New', 'СообщениеПользователю', ())),
        ('Assign', _member('Сообщение', 'Текст'), ('Literal', 'str', message)),
        ('Assign', _member('Сообщение', 'Поле'), ('Literal', 'str', 'Объект.Наименование')),
        ('ExpressionStatement', ('Call', _member('Сообщение', 'Сообщить'), ())),
    )
    if server:
        message_body = (('Assign', _name_node('Отказ'), ('Literal', 'bool', True)),) + message_body
    expected = (
        ('Assign', field, _call('СокрЛП', field)),
        ('If', ((('Binary', _call('СтрДлина', field), '<', ('Literal', 'Decimal', Decimal(3))), message_body),), ()),
    )
    if server:
        expected = (('If', ((_member(owner, 'ПометкаУдаления'), (('Return', None),)),), ()),) + expected
    if _shape(body) != expected: _fail('body outside profile')
    return message


def analyze_form_module(source, binding, *, catalog_xml, form_xml, definition_xml,
                        catalog_path, form_path, definition_path, module_path):
    """Describe a fully checked bounded module; do not execute the result/source.

    XML inputs are bounded metadata projections, not imported configuration schemas.
    Caller supplies and authenticates provenance. Matching hashes/UUIDs are identity
    commitments only. No activation issues or runtime capabilities are changed.
    """
    if type(binding) is not FormModuleBinding: _fail('binding type')
    identities = (binding.database_id, binding.configuration_id, binding.catalog_id, binding.form_id)
    if any(type(i) is not UUID or not i.int for i in identities) or len(set(identities)) != 4:
        _fail('identity')
    if type(binding.configuration_generation) is not int or not 1 <= binding.configuration_generation < 2**63:
        _fail('generation')
    _name(binding.catalog_name); _name(binding.form_name)
    base = f'Catalogs/{binding.catalog_name}/Forms/{binding.form_name}'
    paths = (catalog_path, form_path, definition_path, module_path)
    if any(type(p) is not str for p in paths) or paths != (
            f'Catalogs/{binding.catalog_name}.xml', base + '.xml', base + '/Ext/Form.xml', base + '/Ext/Form/Module.bsl'):
        _fail('canonical paths')
    for raw, digest, limit in ((source, binding.source_sha256, MAX_SOURCE_BYTES),
            (catalog_xml, binding.catalog_sha256, MAX_XML_BYTES),
            (form_xml, binding.form_sha256, MAX_XML_BYTES),
            (definition_xml, binding.definition_sha256, MAX_XML_BYTES)):
        _bytes(raw, digest, limit)
    scalar_fields, client_handler, server_handler = _metadata(binding, catalog_xml, form_xml, definition_xml)
    program, count = _parse(source)
    if len(program) != 2 or any(type(r) is not ast.Routine for r in program): _fail('routine count')
    descriptions = []
    for routine, handler, context, parameters, event in zip(program,
            (client_handler, server_handler), ('client', 'server'),
            (('Элемент',), ('Отказ', 'ТекущийОбъект', 'ПараметрыЗаписи')),
            ('OnChange', 'BeforeWriteAtServer')):
        if (routine.name != handler or routine.execution_context != context or
                routine.is_function or routine.exported or routine.is_async or routine.is_dual or
                not routine.module_context or tuple(p.name for p in routine.parameters) != parameters or
                any(p.by_value or p.default is not None for p in routine.parameters)):
            _fail('event signature')
        message = _body(routine, context == 'server')
        descriptions.append(FormEventDescription(event, handler, context, parameters, message, 'Объект.Наименование'))
    return FormModuleAnalysis(binding, source, *paths, scalar_fields, tuple(descriptions), count)
