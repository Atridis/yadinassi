"""Static, source-bound catalog BeforeWrite IR. No executor or activation grant.

This intentionally narrower language is not a sandbox for the general BSL
interpreter. Never execute its original source/AST on the strength of this result.
"""
from dataclasses import dataclass, fields
from decimal import Decimal
from hashlib import sha256
import re
from uuid import UUID

from .catalog_backend import CatalogSchema, FieldSchema
from .errors import BSLError
from .syntax import ast
from .syntax.lexer import KEYWORDS, Lexer
from .syntax.parser import Parser

PROFILE = 'catalog-before-write-static-v1'
NATIVE_PARITY = False
MAX_SOURCE_BYTES = 16384
MAX_TOKENS = 2048
MAX_AST_NODES = 2048
MAX_AST_DEPTH = 48
MAX_NESTING = 16
MAX_ROUTINES = 16
MAX_PARAMETERS = 8
MAX_LOCALS = 32
MAX_STRING = 1024
MAX_EXPANDED_NODES = 8192

_IDENTIFIER = re.compile(r'[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё_0-9]{0,127}')
_EVENTS = frozenset(('beforewrite', 'передзаписью'))
_SELF = frozenset(('thisobject', 'этотобъект'))
_CANCEL = frozenset(('cancel', 'отказ'))
_STANDARD = {'code': 'code', 'код': 'code',
             'description': 'description', 'наименование': 'description'}
_RESERVED = frozenset((*_SELF, *_EVENTS, *_CANCEL, *_STANDARD,
    'ref', 'ссылка', 'deletionmark', 'пометкаудаления', 'write', 'записать',
    'isnew', 'этоновый', 'metadata', 'метаданные', 'dataexchange', 'обменданными',
    'additionalproperties', 'дополнительныесвойства'))
_TOKENS = frozenset(('EOF', 'IDENT', 'PROCEDURE', 'ENDPROCEDURE', 'VAR',
    'VAL', 'RETURN', 'IF', 'THEN', 'ELSIF', 'ELSE', 'ENDIF', 'NUMBER',
    'STRING', 'TRUE', 'FALSE', 'UNDEFINED', 'AND', 'OR', 'NOT',
    '+', '-', '*', '/', '%', '=', '<>', '<', '<=', '>', '>=',
    '(', ')', ';', '.', ',', '?'))
_BINARY = frozenset(('+', '-', '*', '/', '%', '=', '<>', '<', '<=', '>', '>=', 'AND', 'OR'))
_AST_FIELDS = {
    ast.Routine: ('name', 'parameters', 'is_function', 'exported', 'body', 'execution_context', 'is_async', 'module_context', 'is_dual'),
    ast.Parameter: ('name', 'by_value', 'default'),
    ast.Var: ('names', 'exported_names', 'execution_context'),
    ast.Assign: ('target', 'value'), ast.If: ('branches', 'otherwise'),
    ast.Return: ('value',), ast.ExpressionStatement: ('expression',),
    ast.Call: ('callee', 'arguments'), ast.Name: ('name',),
    ast.Attribute: ('object', 'name'), ast.Literal: ('value',),
    ast.Group: ('expression',), ast.Unary: ('operator', 'operand'),
    ast.Binary: ('left', 'operator', 'right'),
    ast.Conditional: ('condition', 'when_true', 'when_false'),
}


class ObjectModuleAnalysisError(ValueError):
    """Bounded diagnostic, without source, paths, or host exception details."""


def _fail(reason):
    raise ObjectModuleAnalysisError('object module analysis: ' + reason) from None


@dataclass(frozen=True, slots=True)
class ObjectModuleBinding:
    """Host-supplied identity commitment, not proof of metadata provenance."""
    database_id: UUID
    configuration_id: UUID
    configuration_generation: int
    catalog: CatalogSchema
    source_sha256: str


@dataclass(frozen=True, slots=True)
class IRNode:
    operation: str
    arguments: tuple = ()


@dataclass(frozen=True, slots=True)
class ProcedureIR:
    name: str
    parameters: tuple  # (canonical name, by_value) pairs
    locals: tuple
    body: tuple


@dataclass(frozen=True, slots=True)
class ObjectModuleAnalysis:
    binding: ObjectModuleBinding
    source: bytes
    module_path: str
    event: str
    procedures: tuple
    ast_nodes: int
    expanded_nodes: int
    profile: str = PROFILE
    native_parity: bool = NATIVE_PARITY


def _uuid(value):
    if type(value) is not UUID or not value.int:
        _fail('identity')


def _name(value):
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        _fail('identifier')
    key = value.casefold()
    if key in KEYWORDS:
        _fail('identifier')
    return key


def _binding(value):
    if type(value) is not ObjectModuleBinding:
        _fail('binding type')
    _uuid(value.database_id); _uuid(value.configuration_id)
    if (type(value.configuration_generation) is not int or
            not 1 <= value.configuration_generation <= 2**63 - 1):
        _fail('generation')
    if (type(value.source_sha256) is not str or
            re.fullmatch('[0-9a-f]{64}', value.source_sha256) is None):
        _fail('source hash')
    catalog = value.catalog
    if type(catalog) is not CatalogSchema:
        _fail('catalog type')
    _uuid(catalog.identity); _name(catalog.name)
    if catalog.identity == value.configuration_id:
        _fail('metadata identity collision')
    if (type(catalog.code_length) is not int or not 1 <= catalog.code_length <= 64 or
            type(catalog.description_length) is not int or not 0 <= catalog.description_length <= 1024):
        _fail('catalog bounds')
    if type(catalog.fields) is not tuple or len(catalog.fields) > 64:
        _fail('field count')
    # Scalar-only analysis must not silently discard tabular metadata.
    if type(catalog.tabular_sections) is not tuple or len(catalog.tabular_sections) != 0:
        _fail('tabular sections unsupported')
    names = dict(_STANDARD); used = {catalog.identity, value.configuration_id}
    for field in catalog.fields:
        if type(field) is not FieldSchema:
            _fail('field type')
        _uuid(field.identity); key = _name(field.name)
        if field.identity in used or key in names or key in _RESERVED or key.startswith('_om_'):
            _fail('field collision')
        used.add(field.identity)
        if type(field.kind) is not str or type(field.qualifiers) is not tuple or field.target_catalog_id is not None:
            _fail('field profile')
        q = field.qualifiers
        valid = ((field.kind == 'boolean' and not q) or
                 (field.kind == 'datetime' and len(q) == 1 and type(q[0]) is str and q[0] == 'DateTime') or
                 (field.kind == 'number' and len(q) == 3 and
                  type(q[0]) is int and type(q[1]) is int and type(q[2]) is str and q == (12, 2, 'Any')))
        if not valid:
            _fail('field profile')
        names[key] = key
    return names


def _parse(source, path):
    if type(source) is not bytes or not 1 <= len(source) <= MAX_SOURCE_BYTES:
        _fail('source bytes')
    try:
        text = source.decode('utf-8-sig')
    except UnicodeError:
        _fail('source encoding')
    # Reject even inside comments/strings. This conservative gate is deliberate:
    # neither preprocessing nor execution-context selection may hide any source.
    if '#' in text or '&' in text:
        _fail('directive characters')
    try:
        tokens = Lexer(text, path, allow_directives=False).tokens()
        if len(tokens) > MAX_TOKENS:
            _fail('token budget')
        nesting = 0; unary = 0
        for token in tokens:
            if token.kind not in _TOKENS:
                _fail('token outside profile')
            if token.kind in ('(', 'IF', 'PROCEDURE'):
                nesting += 1
                if nesting > MAX_NESTING:
                    _fail('nesting budget')
            elif token.kind in (')', 'ENDIF', 'ENDPROCEDURE'):
                nesting -= 1
            unary = unary + 1 if token.kind in ('NOT', '+', '-') else 0
            if unary > MAX_NESTING:
                _fail('unary budget')
        # Unlike parse(), this never selects or combines client/server passes.
        return Parser(tokens).parse()
    except (BSLError, RecursionError):
        _fail('syntax outside profile')


def _ast_budget(program):
    count = 0; pending = [(program, 0)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, ast.Node):
            shape = tuple(f.name for f in fields(item) if f.name != 'token')
            if _AST_FIELDS.get(type(item)) != shape:
                _fail('AST outside profile')
            count += 1
            if count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
                _fail('AST budget')
            pending.extend((getattr(item, f.name), depth + 1)
                           for f in fields(item) if f.name != 'token')
        elif type(item) in (list, tuple):
            pending.extend((child, depth) for child in item)
    return count


class _Lower:
    def __init__(self, program, field_names):
        self.field_names = field_names
        self.routines = {}; self.graph = {}; self.costs = {}
        if not 1 <= len(program) <= MAX_ROUTINES:
            _fail('routine count')
        for routine in program:
            if type(routine) is not ast.Routine:
                _fail('module state or initialization')
            key = _name(routine.name)
            if key in self.routines:
                _fail('routine collision')
            if key not in _EVENTS and not key.startswith('_om_'):
                _fail('unknown event or helper namespace')
            if (routine.is_function or routine.exported or routine.is_async or routine.is_dual or
                    not routine.module_context or routine.execution_context != 'client'):
                _fail('routine outside profile')
            if len(routine.parameters) > MAX_PARAMETERS:
                _fail('parameter count')
            names = set()
            for p in routine.parameters:
                name = _name(p.name)
                if p.default is not None or name in names or name in field_names or name in _SELF or name.startswith('_om_'):
                    _fail('parameter profile')
                if name in _RESERVED and name not in _CANCEL:
                    _fail('parameter collision')
                names.add(name)
            self.routines[key] = routine
            self.graph[key] = []
        events = tuple(key for key in self.routines if key in _EVENTS)
        if len(events) != 1:
            _fail('exactly one BeforeWrite required')
        self.event = events[0]
        parameters = self.routines[self.event].parameters
        if len(parameters) != 1 or parameters[0].by_value or parameters[0].name.casefold() not in _CANCEL:
            _fail('BeforeWrite signature')

    def slot(self, node, locals_):
        if type(node) is ast.Name:
            key = _name(node.name)
            if key in locals_:
                return IRNode('local', (key,))
            if key in self.field_names:
                return IRNode('field', (self.field_names[key],))
        elif (type(node) is ast.Attribute and type(node.object) is ast.Name and
                _name(node.object.name) in _SELF):
            key = _name(node.name)
            if key in self.field_names:
                return IRNode('field', (self.field_names[key],))
        _fail('unbound name or member')

    def expression(self, node, locals_, initialized):
        if type(node) is ast.Literal:
            value = node.value
            if type(value) is str and len(value) <= MAX_STRING:
                return IRNode('string', (value,))
            if type(value) is bool:
                return IRNode('boolean', (value,))
            if value is None:
                return IRNode('undefined')
            if type(value) is Decimal and value.is_finite():
                _, digits, exponent = value.as_tuple()
                if len(digits) <= 38 and -18 <= exponent <= 0:
                    return IRNode('number', (str(value),))
            _fail('literal profile')
        if type(node) in (ast.Name, ast.Attribute):
            slot = self.slot(node, locals_)
            if slot.operation == 'local' and slot.arguments[0] not in initialized:
                _fail('local read before assignment')
            return slot
        if type(node) is ast.Group:
            return self.expression(node.expression, locals_, initialized)
        if type(node) is ast.Unary and node.operator in ('+', '-', 'NOT'):
            return IRNode('unary', (node.operator, self.expression(node.operand, locals_, initialized)))
        if type(node) is ast.Binary and node.operator in _BINARY:
            return IRNode('binary', (node.operator, self.expression(node.left, locals_, initialized),
                                   self.expression(node.right, locals_, initialized)))
        if type(node) is ast.Conditional:
            return IRNode('conditional', tuple(self.expression(value, locals_, initialized)
                          for value in (node.condition, node.when_true, node.when_false)))
        _fail('expression outside profile')

    def block(self, body, locals_, initialized, caller):
        result = []; initialized = set(initialized)
        for node in body:
            if type(node) is ast.Assign:
                target = self.slot(node.target, locals_)
                value = self.expression(node.value, locals_, initialized)
                result.append(IRNode('assign', (target, value)))
                if target.operation == 'local':
                    initialized.add(target.arguments[0])
            elif type(node) is ast.If:
                branches = []; outputs = []
                for condition, branch in node.branches:
                    test = self.expression(condition, locals_, initialized)
                    lowered, assigned = self.block(branch, locals_, initialized, caller)
                    branches.append((test, lowered)); outputs.append(assigned)
                otherwise, assigned = self.block(node.otherwise, locals_, initialized, caller)
                outputs.append(assigned)
                initialized = set.intersection(*outputs)
                result.append(IRNode('if', (tuple(branches), otherwise)))
            elif type(node) is ast.Return and node.value is None:
                result.append(IRNode('return'))
                # Do not stop: even unreachable statements must be admitted.
            elif type(node) is ast.ExpressionStatement and type(node.expression) is ast.Call:
                call = node.expression
                if type(call.callee) is not ast.Name:
                    _fail('indirect or host call')
                callee = _name(call.callee.name)
                if callee not in self.routines or callee in _EVENTS:
                    _fail('call outside helper graph')
                parameters = self.routines[callee].parameters
                if len(call.arguments) != len(parameters):
                    _fail('helper arity')
                arguments = []
                for parameter, argument in zip(parameters, call.arguments):
                    lowered = self.expression(argument, locals_, initialized)
                    if not parameter.by_value and (type(argument) is not ast.Name or lowered.operation != 'local'):
                        _fail('reference argument must be initialized local')
                    arguments.append(lowered)
                self.graph[caller].append(callee)
                result.append(IRNode('call', (callee, tuple(arguments))))
            else:
                _fail('statement outside profile')
        return tuple(result), initialized

    def lower(self):
        result = []
        for key, routine in self.routines.items():
            parameters = tuple((p.name.casefold(), p.by_value) for p in routine.parameters)
            locals_ = {name for name, _ in parameters}; declarations = []; start = 0
            for node in routine.body:
                if type(node) is not ast.Var:
                    break
                if node.exported_names:
                    _fail('local export')
                for name in node.names:
                    name = _name(name)
                    if name in locals_ or name in self.field_names or name in _RESERVED or name.startswith('_om_'):
                        _fail('local collision')
                    locals_.add(name); declarations.append(name)
                start += 1
            if len(declarations) > MAX_LOCALS:
                _fail('local count')
            body, _ = self.block(routine.body[start:], locals_, {name for name, _ in parameters}, key)
            # Count original syntax conservatively, including expressions/branches.
            self.costs[key] = _ast_budget([routine])
            result.append(ProcedureIR(key, parameters, tuple(declarations), body))
        visiting = set(); costs = {}; reachable = set()
        def cost(key):
            if key in visiting:
                _fail('recursive helper graph')
            if key in costs:
                return costs[key]
            visiting.add(key); reachable.add(key)
            total = self.costs[key]
            for callee in self.graph[key]:
                total += cost(callee)
                if total > MAX_EXPANDED_NODES:
                    _fail('expanded graph budget')
            visiting.remove(key); costs[key] = total
            return total
        expanded = cost(self.event)
        if reachable != set(self.routines):
            _fail('unreachable helper declaration')
        return tuple(result), expanded


def analyze_object_module(source: bytes, binding: ObjectModuleBinding) -> ObjectModuleAnalysis:
    """Check exact source against a caller's verified identity/hash commitment.

    No module loading, BSL evaluation, file/database/network access, or activation
    occurs here. The caller must establish the binding's metadata provenance.
    A successful result is structural IR, not permission to execute any source.
    """
    field_names = _binding(binding)
    if type(source) is not bytes or not 1 <= len(source) <= MAX_SOURCE_BYTES:
        _fail('source bytes')
    if sha256(source).hexdigest() != binding.source_sha256:
        _fail('source hash mismatch')
    path = 'Catalogs/' + binding.catalog.name + '/Ext/ObjectModule.bsl'
    program = _parse(source, path)
    count = _ast_budget(program)
    lower = _Lower(program, field_names)
    procedures, expanded = lower.lower()
    return ObjectModuleAnalysis(binding, source, path, lower.event, procedures, count, expanded)
