"""Closed metadata and compilation contract for configured BSL modules.

Compilation is read-only. Module execution is owned by ConfigurationApplication
and the existing Interpreter, never by the XML importer or database opener.
"""
from dataclasses import dataclass, replace
from uuid import UUID
from .configuration_diagnostics import location

from .syntax import ast
from .syntax.lexer import KEYWORDS, Lexer
from .syntax.parser import Parser


MODULE_RUNTIME = 'managed-client-server-v1'
MAX_COMMON_MODULES = 128
MAX_ROUTINES = 2048
_ANNOTATIONS = frozenset(('ATCLIENT', 'ATSERVER', 'ATSERVERNOCONTEXT',
                          'ATCLIENTATSERVERNOCONTEXT'))


@dataclass(frozen=True, slots=True)
class CommonModuleDefinition:
    identity: UUID
    name: str
    global_module: bool
    client: bool
    server: bool
    server_call: bool

    @property
    def path(self):
        return 'CommonModules/' + self.name + '/Ext/Module.bsl'


def read_common_modules(files, names, used, issues):
    from .configuration_xml import (MD, _activation_properties, _envelope_issues,
                                    _fail, _name, _object, _props, _text, _uuid)
    if len(names) > MAX_COMMON_MODULES or len({n.casefold() for n in names}) != len(names):
        _fail('common module inventory')
    result = []
    allowed = {'Name', 'Synonym', 'Comment', 'Global', 'ClientManagedApplication',
               'ClientOrdinaryApplication', 'Server', 'ExternalConnection',
               'ServerCall', 'Privileged', 'ReturnValuesReuse'}
    for name in names:
        path = 'CommonModules/' + name + '.xml'
        if path not in files:
            _fail('missing common module XML')
        obj, _, root = _object(files[path], 'CommonModule', include_root=True)
        props = _props(obj)
        if _name(_text(props, 'Name')) != name or name.casefold() in KEYWORDS:
            _fail('common module filename/name mismatch')
        identity = _uuid(obj.get('uuid'))
        if identity in used:
            _fail('duplicate metadata UUID')
        used.add(identity)
        _envelope_issues(root, obj, issues, name)
        _activation_properties(obj, allowed, issues, name)
        child = obj.find('{' + MD + '}ChildObjects')
        if child is not None and len(child):
            _fail('common module child objects')

        def flag(key):
            value = _text(props, key, 'false')
            if value not in ('true', 'false'):
                _fail('invalid common module flag:' + key)
            return value == 'true'

        global_module, client, server, server_call = (
            flag('Global'), flag('ClientManagedApplication'), flag('Server'), flag('ServerCall'))
        # These properties change authority, execution or observable caching.
        # They cannot be treated as descriptive metadata or successful no-ops.
        if flag('Privileged') or flag('ClientOrdinaryApplication') or flag('ExternalConnection'):
            _fail('unsupported common module execution mode')
        if _text(props, 'ReturnValuesReuse', 'DontUse') != 'DontUse':
            _fail('common module return-value reuse unsupported')
        if not client and not server:
            _fail('common module has no supported execution side')
        if server_call and (global_module or not server or client):
            _fail('invalid common module server-call combination')
        result.append(CommonModuleDefinition(identity, name, global_module, client, server, server_call))
    return tuple(result)


def compile_module(content, path, side, *, common):
    """Reuse the normal lexer/parser; the metadata chooses an unannotated side.

    Conditional Client/Server branches use the existing standalone symbol
    profile. Native thin/web/file-mode flags are not inferred from host OS.
    """
    if type(content) is not bytes or type(path) is not str or side not in ('client', 'server'):
        raise TypeError('invalid configuration module input')
    text = content.decode('utf-8-sig')
    tokens = Lexer(text, '<configuration:' + path + '>', execution_context=side).tokens()
    if any(t.kind in _ANNOTATIONS or t.kind == 'IMPORT' for t in tokens):
        raise ValueError('configured module annotations/imports are outside this profile')
    program = Parser(tokens).parse()
    if common and any(type(node) is not ast.Routine for node in program):
        raise ValueError('common modules contain only procedures and functions')
    if sum(type(node) is ast.Routine for node in program) > MAX_ROUTINES:
        raise ValueError('configuration module routine bound')
    result = []
    for node in program:
        if type(node) is ast.Routine:
            if side == 'server' and node.is_async:
                raise ValueError('server common modules cannot contain Async routines')
            node = replace(node, execution_context=side)
        result.append(node)
    return result


def validate_module_sources(configuration):
    """Preflight all admitted bodies without running initializers or handlers."""
    files = {entry.path: entry.content for entry in configuration.files}
    total = 0
    for module in configuration.common_modules:
        if type(module) is not CommonModuleDefinition or module.path not in files:
            raise ValueError('missing or invalid common module source')
        for side, enabled in (('client', module.client), ('server', module.server)):
            if enabled:
                with location(stage='compile', file=module.path):
                    program = compile_module(files[module.path], module.path, side, common=True)
                total += len(program)
    app = 'Ext/ManagedApplicationModule.bsl'
    if app in files:
        with location(stage='compile', file=app):
            program = compile_module(files[app], app, 'client', common=False)
        total += sum(type(node) is ast.Routine for node in program)
    if total > MAX_ROUTINES:
        raise ValueError('configuration runtime routine bound')
    return configuration
