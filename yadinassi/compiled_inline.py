"""Whole-block lowering experiment. Explicit runtime node-policy ABI required.

Only compiler-owned Python source templates enter compile. No sandbox claim.
Node references remain diagnostic/helper handles; control operands are captured
in generated bindings rather than reread from mutable AST during execution.
"""
from dataclasses import dataclass
import ast as pyast
import sys
from decimal import Decimal

from collections import OrderedDict
from threading import Lock
from types import CodeType


class _CodeCache:
    """Bounded code objects only: never namespaces, bindings, ASTs or VM values."""
    def __init__(self, max_entries=256, max_bytes=16 * 1024 * 1024):
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self._lock = Lock()
        self._entries = OrderedDict()
        self._bytes = 0
        self.hits = self.misses = 0

    def reset(self):
        with self._lock:
            self._entries.clear(); self._bytes = 0
            self.hits = self.misses = 0

    def info(self):
        with self._lock:
            return dict(entries=len(self._entries), bytes=self._bytes,
                        hits=self.hits, misses=self.misses)

    @staticmethod
    def _weight(source, code):
        # Account for source plus nested code/constants, not only bytecode length.
        seen = set()
        def size(value):
            if id(value) in seen: return 0
            seen.add(id(value))
            total = sys.getsizeof(value)
            if isinstance(value, CodeType):
                total += size(value.co_code) + size(value.co_consts)
                total += size(value.co_names) + size(value.co_varnames)
                total += size(value.co_freevars) + size(value.co_cellvars)
                total += size(value.co_filename) + size(value.co_name)
                total += size(value.co_linetable) + size(getattr(value, 'co_exceptiontable', b''))
            elif type(value) is tuple or type(value) is frozenset:
                total += sum(size(item) for item in value)
            return total
        return size(source) + size(code)

    def get(self, source, *, flags=0, optimize=-1):
        # Only trusted compiler-generated strings call this internal helper.
        # Pin all compilation semantics; never inherit caller future flags.
        level = sys.flags.optimize if optimize == -1 else optimize
        key = (source, flags, level)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key); self.hits += 1
                return entry[0]
            self.misses += 1
        # Parsing/compilation intentionally outside lock. Concurrent misses may
        # compile twice, but share no namespaces or partially constructed code.
        code = compile(pyast.parse(source, filename='<bsl-inline>'),
                       '<bsl-inline>', 'exec', flags=flags,
                       dont_inherit=True, optimize=level)
        if type(code) is not CodeType:
            raise ValueError('inline cache accepts executable code objects only')
        # Include key/entry bookkeeping in the weighted bound.
        weight = self._weight(source, code) + sys.getsizeof(key) + sys.getsizeof((code, 0))
        if self.max_entries <= 0 or weight > self.max_bytes:
            return code
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._entries.move_to_end(key)
                return entry[0]
            while self._entries and (len(self._entries) >= self.max_entries
                                      or self._bytes + weight > self.max_bytes):
                _, (_, removed) = self._entries.popitem(last=False)
                self._bytes -= removed
            self._entries[key] = (code, weight); self._bytes += weight
        return code


_CODE_CACHE = _CodeCache()

_ONE = Decimal(1)
from .syntax import ast
from .owned_syntax import syntax_kind, OwnedList, is_owned


@dataclass(frozen=True)
class NodeIR:
    """Immutable admitted operation descriptor (opaque literal identity retained)."""
    kind: type
    node: object
    fields: tuple


def snapshot(node, engine=None):
    from dataclasses import fields
    cache = None
    if engine is not None and engine.OWNED_SNAPSHOT and is_owned(node):
        engine._verify_owned_identity(node)
        cache = engine._inline_ir
        cached = cache.get(id(node))
        if cached is not None:
            if cached.node is not node:
                from .compiled_backend import CompiledUnsupported
                raise CompiledUnsupported(node, 'owned IR identity mismatch')
            return cached
        if len(cache) >= engine.MAX_REGISTRY_ENTRIES:
            from .compiled_backend import CompiledUnsupported
            raise CompiledUnsupported(node, 'owned IR registry limit')
    def freeze(value):
        if isinstance(value, ast.Node):
            return snapshot(value, engine)
        if type(value) is list or type(value) is tuple or type(value) is OwnedList:
            return tuple(freeze(item) for item in value)
        return value
    result = NodeIR(syntax_kind(node), node, tuple((f.name, getattr(node, f.name)
        if syntax_kind(node) is ast.Literal and f.name == 'value'
        else freeze(getattr(node, f.name))) for f in fields(node)))
    if cache is not None:
        if len(cache) >= engine.MAX_REGISTRY_ENTRIES:
            from .compiled_backend import CompiledUnsupported
            raise CompiledUnsupported(node, 'owned IR registry limit')
        cache[id(node)] = result
    return result


class Emitter:
    def __init__(self, engine):
        self.engine = engine
        self.lines = []
        self.depth = 1
        self.bindings = {}
        self.serial = 0
        self.local_names = []
        self.source_bytes = 0

    def temp(self, prefix='v'):
        self.serial += 1
        name = f'{prefix}{self.serial}'
        if prefix != 'b':
            self.local_names.append(name)
        return name

    def bind(self, value):
        name = self.temp('b'); self.bindings[name] = value
        return name

    def line(self, text):
        from .compiled_backend import CompiledUnsupported
        line = '    ' * self.depth + text
        self.source_bytes += len(line.encode('utf-8')) + 1
        if self.source_bytes > self.engine.MAX_INLINE_FUNCTION_BYTES:
            raise CompiledUnsupported(None, 'inline function source budget')
        self.lines.append(line)

    def node(self, ir, *, boundary=True):
        from .compiled_backend import _HELPERS, _SYNTAX_ONLY, CompiledUnsupported
        kind, node, data = ir.kind, ir.node, dict(ir.fields)
        result, handle = self.temp(), self.bind(node)
        # Python limits static block nesting. Outline deeper code to an already
        # compiled fragment through the same policy ABI, never tree interpretation.
        if self.depth > 15 and boundary:
            self.line(f'{result} = yield from vm._visit({handle})')
            return result
        ticket = self.temp('ticket')
        stored_name = None
        assign_name = None
        if kind is ast.Name:
            available, stored_name = self.temp('available'), self.temp('stored_name')
            self.line(f'{available}, {stored_name} = engine.fast_name({self.bind(data["name"].casefold())})')
        if kind is ast.Assign and data['target'].kind is ast.Name:
            assign_name = dict(data['target'].fields)['name'].casefold()
        pure = kind not in _HELPERS and kind not in (ast.Call, ast.ExpressionStatement, ast.Await, ast.ForEach)
        if pure or stored_name is not None or assign_name is not None:
            condition = 'engine._fast_ready' if pure else available if stored_name is not None else f'engine.fast_assignable({self.bind(assign_name)})'
            self.line(f'if {condition}:'); self.depth += 1
            if self.engine.DETAILED_INLINE_STATS:
                self.line("stats['emitted_executions'] += 1" if pure else "stats['helper_executions'] += 1")
                self.line(f"kinds[{kind.__name__!r}] = kinds.get({kind.__name__!r}, 0) + 1")
            self.line(f'{ticket} = None'); self.depth -= 1
            self.line('else:'); self.depth += 1
            self.line(f'{ticket} = engine.inline_enter({handle})'); self.depth -= 1
        else:
            self.line(f'{ticket} = engine.inline_enter({handle})')
        self.line('try:'); self.depth += 1
        if boundary:
            self.line(f'if not engine._fast_ready: vm.compiled_before({handle})')
            self.line('try:'); self.depth += 1
        self.line(f'{result} = None')
        if kind in _SYNTAX_ONLY:
            self.line(f"raise CompiledUnsupported({handle}, 'syntax-only node cannot execute directly')")
        elif kind is ast.Name:
            self.line(f'if {ticket} is None: {result} = {stored_name}')
            self.line(f'else: {result} = vm.semantic_name({handle})')
        elif kind is ast.Assign and dict(data['target'].fields).get('name') is not None and data['target'].kind is ast.Name:
            name = self.bind(dict(data['target'].fields)['name'])
            self.line(f'if {ticket} is None:'); self.depth += 1
            # Unlike a separate interpreter frame, an inline RHS leaves its
            # Python locals alive until the whole block returns. Release only
            # this RHS's compiler-owned temporaries after assignment, including
            # exceptional exits; BSL variables/aliases retain their own values.
            first_local = len(self.local_names)
            self.line('try:'); self.depth += 1
            value = self.node(data['value'])
            self.line(f'engine.assign_value({name}, {value})'); self.depth -= 1
            self.line('finally:'); self.depth += 1
            rhs_locals = self.local_names[first_local:]
            for offset in range(0, len(rhs_locals), 12):
                self.line(' = '.join(rhs_locals[offset:offset + 12]) + ' = None')
            self.depth -= 2
            self.line('else:'); self.depth += 1
            self.line(f'{result} = yield from vm.semantic_assign({handle})'); self.depth -= 1
        elif kind in _HELPERS:
            method = _HELPERS[kind]
            expr = f'vm.{method}({handle})'
            self.line(f'{result} = {expr}' if kind in (ast.Name, ast.Import)
                      else f'{result} = yield from {expr}')
        elif kind is ast.Literal:
            self.line(f'{result} = {self.bind(data["value"])}')
        elif kind is ast.Group:
            value = self.node(data['expression']); self.line(f'{result} = {value}')
        elif kind is ast.Unary:
            value = self.node(data['operand'])
            self.line(f'{result} = checked_unary({self.bind(data["operator"])}, {value})')
        elif kind is ast.Binary:
            left = self.node(data['left']); operator = data['operator']
            if operator in ('AND', 'OR'):
                self.line(f'{result} = checked_boolean({left})')
                self.line(f'if {"not " if operator == "OR" else ""}{result}:'); self.depth += 1
                right = self.node(data['right']); self.line(f'{result} = checked_boolean({right})'); self.depth -= 1
            else:
                right = self.node(data['right'])
                self.line(f'if (type({left}) is not Decimal and type({left}) is not str and type({left}) is not bool and type({left}) is not none_type) or (type({right}) is not Decimal and type({right}) is not str and type({right}) is not bool and type({right}) is not none_type): engine.verify_all()')
                if operator in ('+', '-', '*'):
                    self.line(f'if engine._fast_ready and type({left}) is Decimal and type({right}) is Decimal:')
                    self.depth += 1; self.line(f'{result} = {left} {operator} {right}'); self.depth -= 1
                    self.line('else:'); self.depth += 1
                    self.line(f'{result} = R.binary_values({self.bind(operator)}, {left}, {right})'); self.depth -= 1
                else:
                    self.line(f'{result} = R.binary_values({self.bind(operator)}, {left}, {right})')
                self.line(f'if (type({left}) is not Decimal and type({left}) is not str and type({left}) is not bool and type({left}) is not none_type) or (type({right}) is not Decimal and type({right}) is not str and type({right}) is not bool and type({right}) is not none_type): engine.verify_all()')
        elif kind is ast.Conditional:
            condition = self.node(data['condition']); self.line(f'if checked_boolean({condition}):'); self.depth += 1
            value = self.node(data['when_true']); self.line(f'{result} = {value}'); self.depth -= 1
            self.line('else:'); self.depth += 1
            value = self.node(data['when_false']); self.line(f'{result} = {value}'); self.depth -= 1
        elif kind is ast.Call:
            self.line(f'{result} = yield from vm.call({handle}, require_value=True)')
        elif kind is ast.ExpressionStatement:
            expression = data['expression']
            while expression.kind is ast.Group:
                expression = dict(expression.fields)['expression']
            if expression.kind is ast.Call:
                self.line(f'{result} = yield from vm.call({self.bind(expression.node)}, require_value=False)')
            else:
                value = self.node(data['expression']); self.line(f'{result} = {value}')
        elif kind is ast.If:
            matched = self.temp(); self.line(f'{matched} = False')
            for branch_index, (condition, body) in enumerate(data['branches']):
                self.line(f'if not {matched}:'); self.depth += 1
                value = self.node(condition); self.line(f'if checked_boolean({value}):'); self.depth += 1
                self.line(f'{matched} = True'); self.block(body, source=node.branches[branch_index][1])
                self.depth -= 2
            self.line(f'if not {matched}:'); self.depth += 1
            self.block(data['otherwise'], source=node.otherwise); self.depth -= 1
        elif kind in (ast.For, ast.ForEach, ast.While):
            if kind is ast.For:
                start = self.node(data['start']); first = self.temp()
                self.line(f'{first} = checked_number({start})')
                end = self.node(data['end']); last = self.temp()
                self.line(f'{last} = checked_number({end})')
                name = self.bind(data['name'].casefold())
                counter = self.bind(ast.Name(node.token, data['name'].casefold()))
                self.line(f'engine.assign_value({name}, {first})')
                scope, stamp = self.temp('counter_scope'), self.temp('counter_epoch')
                self.line(f'{scope}, {stamp} = engine.counter_slot({name})')
                self.line('while True:')
            elif kind is ast.ForEach:
                value = self.node(data['collection']); item = self.temp()
                self.line(f'for {item} in vm.compiled_iterable({value}):')
            else:
                self.line('while True:')
            self.depth += 1
            if kind is ast.For:
                current = self.temp('counter_value')
                self.line(f'if {stamp} != engine._opaque_epoch: {scope}, {stamp} = engine.counter_slot({name})')
                self.line(f'if {scope} is not None:'); self.depth += 1
                self.line(f'{current} = {scope}[{name}]'); self.depth -= 1
                self.line('else:'); self.depth += 1
                self.line(f'{current} = engine.counter_value({counter})'); self.depth -= 1
                self.line(f'if type({current}) is Decimal and type({last}) is Decimal:'); self.depth += 1
                self.line(f'if not ({current} <= {last}): break'); self.depth -= 1
                self.line('else:'); self.depth += 1
                self.line(f'if not checked_counter_le(checked_number({current}), {last}): break'); self.depth -= 1
            if kind is ast.ForEach:
                self.line('engine.verify_all()')
                self.line(f'engine.assign_value({self.bind(data["name"])}, {item})')
            elif kind is ast.While:
                condition = self.node(data['condition'])
                self.line(f'if not checked_boolean({condition}): break')
            self.line('try:'); self.depth += 1; self.block(data['body'], source=node.body); self.depth -= 1
            self.line('except R._Continue:'); self.depth += 1; self.line('pass'); self.depth -= 1
            self.line('except R._Break:'); self.depth += 1; self.line('break'); self.depth -= 1
            if kind is ast.For:
                self.line(f'if {stamp} != engine._opaque_epoch: {scope}, {stamp} = engine.counter_slot({name})')
                self.line(f'if {scope} is not None:'); self.depth += 1
                self.line(f'{current} = {scope}[{name}]'); self.depth -= 1
                self.line('else:'); self.depth += 1
                self.line(f'{current} = engine.counter_value({counter})'); self.depth -= 1
                self.line(f'if {scope} is not None and type({current}) is Decimal:'); self.depth += 1
                self.line(f'{scope}[{name}] = {current} + ONE'); self.depth -= 1
                self.line('else:'); self.depth += 1
                self.line(f'engine.assign_value({name}, checked_increment(checked_number({current})))'); self.depth -= 1
            self.depth -= 1
        elif kind in (ast.Break, ast.Continue):
            self.line('raise R._Break' if kind is ast.Break else 'raise R._Continue')
        elif kind is ast.Return:
            value = 'None' if data['value'] is None else self.node(data['value'])
            self.line(f'raise R._Return({value})')
        elif kind is ast.Try:
            self.line('try:'); self.depth += 1; self.block(data['body'], source=node.body); self.depth -= 1
            error = self.temp('error'); index = self.temp('i')
            self.line(f'except R.BSLRuntimeError as {error}:'); self.depth += 1
            self.line('engine.verify_all()')
            self.line(f'for {index} in range(len(vm._handled_errors)): vm._handled_errors[{index}] = None')
            self.line(f'vm._handled_errors.append({error})')
            self.line('try:'); self.depth += 1; self.block(data['handler'], source=node.handler); self.depth -= 1
            self.line('finally:'); self.depth += 1; self.line('vm._handled_errors.pop()'); self.depth -= 2
        elif kind is ast.Goto:
            self.line(f'raise R._Goto({handle})')
        elif kind in (ast.Label, ast.Routine):
            pass
        elif kind is ast.Var:
            names = self.bind(tuple(data['names'])); name = self.temp('name')
            self.line(f'if vm.locals is None and any(n.casefold() in vm.imports for n in {names}):')
            self.depth += 1; self.line('raise ValueError("Имя импорта конфликтует с объявлением")'); self.depth -= 1
            self.line(f'for {name} in {names}:'); self.depth += 1
            self.line(f'(vm.variables if vm.locals is None else vm.locals).setdefault({name}.casefold(), None)'); self.depth -= 1
            self.line('engine.invalidate_counter_slots()')
        elif kind is ast.Await:
            self.line("require_transfer('Await')")
            self.line('forbid_transfer(vm._transaction_backend())')
            value = self.node(data['operand']); self.line(f'{result} = yield R.AwaitRequest({value})')
        else:
            raise CompiledUnsupported(node, f'inline lowering missing {kind.__name__}')
        if boundary:
            self.depth -= 1
            error = self.temp('error'); self.line(f'except BaseException as {error}:'); self.depth += 1
            converted = self.temp('converted')
            self.line(f'{converted} = vm.compiled_exception({handle}, {error})')
            # Exception traceback frames must not retain their own exception
            # through this temporary (notably internal _Return with a resource).
            self.line('try:'); self.depth += 1
            self.line(f'if {converted} is {error}: raise')
            self.line(f'raise {converted} from None'); self.depth -= 1
            self.line('finally:'); self.depth += 1
            self.line(f'{converted} = None'); self.depth -= 2
            self.line(f'if not engine._fast_ready: {result} = vm.compiled_after({handle}, {result})')
        self.depth -= 1
        self.line('finally:'); self.depth += 1
        self.line(f'if {ticket} is not None: engine.inline_exit({ticket}, unwinding=sys.exc_info()[0] is not None)'); self.depth -= 1
        return result

    def block(self, nodes, *, source=None):
        result = self.temp('block_result')
        self.line(f'{result} = None')
        check = None
        if source is not None and not is_owned(source):
            check = (self.bind(source), self.bind(self.engine._block_signature(source)))
        if not nodes:
            return result
        labels = {dict(node.fields)['name'].casefold(): i for i, node in enumerate(nodes)
                  if node.kind is ast.Label}
        if not labels:
            for node in nodes:
                if check: self.line(f'check_block({check[0]}, {check[1]})')
                value = self.node(node)
                self.line(f'{result} = {value}')
            return result
        pc, jump = self.temp('pc'), self.temp('jump')
        self.line(f'{pc} = 0'); self.line(f'while {pc} < {len(nodes)}:'); self.depth += 1
        self.line('try:'); self.depth += 1
        if check: self.line(f'check_block({check[0]}, {check[1]})')
        for index, node in enumerate(nodes):
            self.line(f'{"if" if index == 0 else "elif"} {pc} == {index}:'); self.depth += 1
            value = self.node(node); self.line(f'{result} = {value}'); self.depth -= 1
        self.line(f'{pc} += 1'); self.depth -= 1
        self.line(f'except R._Goto as {jump}:'); self.depth += 1
        mapping = self.bind(labels)
        self.line(f'if {jump}.name not in {mapping}: raise')
        self.line(f'{pc} = {mapping}[{jump}.name]')
        self.depth -= 2
        return result

    def compile(self, value, *, block=False):
        from . import runtime as R
        from .compiled_backend import _verify_block, CompiledUnsupported
        from .safe_mode import require_transfer
        from .database_transactions import forbid_transfer
        if block:
            result = self.block(tuple(snapshot(node, self.engine) for node in value), source=value)
            self.line(f'return {result}')
        else:
            result = self.node(snapshot(value, self.engine), boundary=False); self.line(f'return {result}')
        source = 'def generated(vm):\n    if False: yield None\n' + '\n'.join(self.lines) + '\n'
        def checked_boolean(value):
            if type(value) is Decimal or type(value) is bool: return R.boolean(value)
            self.engine.verify_all()
            result = R.boolean(value)
            self.engine.verify_all()
            return result
        def checked_number(value):
            if type(value) is Decimal or type(value) is bool: return R.require_number(value)
            self.engine.verify_all()
            result = R.require_number(value)
            self.engine.verify_all()
            return result
        def checked_counter_le(left, right):
            opaque = type(left) is not Decimal or type(right) is not Decimal
            if opaque: self.engine.verify_all()
            result = left <= right
            if opaque: self.engine.verify_all()
            return result
        def checked_increment(value):
            opaque = type(value) is not Decimal
            if opaque: self.engine.verify_all()
            result = value + _ONE
            if opaque: self.engine.verify_all()
            return result
        def checked_unary(operator, value):
            if type(value) is Decimal or type(value) is bool: return R.unary_value(operator, value)
            self.engine.verify_all()
            result = R.unary_value(operator, value)
            self.engine.verify_all()
            return result
        namespace = dict(self.bindings, R=R, Decimal=Decimal, ONE=_ONE, engine=self.engine, sys=sys,
                         stats=self.engine.stats, kinds=self.engine.stats['node_kinds'],
                         check_block=_verify_block, CompiledUnsupported=CompiledUnsupported,
                         none_type=type(None),
                         checked_boolean=checked_boolean, checked_number=checked_number, checked_unary=checked_unary,
                         checked_counter_le=checked_counter_le, checked_increment=checked_increment,
                         require_transfer=require_transfer, forbid_transfer=forbid_transfer)
        self.engine._inline_unit_bytes = getattr(self.engine, '_inline_unit_bytes', 0) + len(source.encode('utf-8'))
        if self.engine._inline_unit_bytes > self.engine.MAX_INLINE_UNIT_BYTES:
            raise CompiledUnsupported(None, 'inline unit source budget')
        # All per-function/unit budgets above apply even on a code-cache hit.
        # Each execution gets fresh bindings and function globals.
        exec(_CODE_CACHE.get(source), namespace)
        return namespace['generated']
