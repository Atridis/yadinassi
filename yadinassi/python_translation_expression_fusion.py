"""Inline expression emission for whole Python block/routine functions.

No runtime AST evaluator. Calls and other suspending semantic services retain the
scheduler protocol; ordinary expression children are straight-line Python.
The driver owns source/function admission budgets and must release the returned
result temporary after consuming it. Child temporaries are cleared even when an
operation or context hook raises, and no operand is speculatively evaluated.
"""
from .syntax import ast
from .owned_syntax import syntax_kind
from .python_translation_expressions import binary, unary, UnsupportedExpression
from .values import boolean
from .safe_mode import require_transfer
from .database_transactions import forbid_transfer
from .async_runtime import AwaitRequest


class ExpressionEmitter:
    def __init__(self, bind, emit, temp, *, services='_s.expressions', vm='vm',
                 helpers='_PE', max_nodes=10000):
        self.bind, self.emit, self.temp = bind, emit, temp
        self.services, self.vm, self.helpers = services, vm, helpers
        self.max_nodes = max_nodes
        self.count = 0
        self.active = set()
        # Static emission inventory, not a claim about reached runtime coverage.
        self.emitted_kinds = {}
        self.service_boundaries = 0

    def release(self, result, depth):
        self.emit(depth, f'{result} = None')

    def emit_expression(self, node, depth):
        if depth >= 8:
            # Keep deeply nested code in its already admitted generated function,
            # not an AST adapter or a runtime compiler. Avoid CPython's static
            # nesting ceiling while retaining the complete node boundary once.
            result=self.temp();self.service_boundaries+=1
            self.emit(depth,f'{result} = yield from {self.services}.evaluate({self.bind(node)})')
            return result
        identity=id(node)
        if identity in self.active: raise UnsupportedExpression('cyclic fused expression')
        self.count += 1
        if self.count > self.max_nodes: raise UnsupportedExpression('fused expression node budget')
        self.active.add(identity)
        try:
            return self._expression(node, depth)
        finally:
            self.active.remove(identity)

    def _expression(self, node, depth):
        emit, vm, services, helper = self.emit, self.vm, self.services, self.helpers
        handle=self.bind(node); result=self.temp(); converted=self.temp(); error=self.temp()
        owned=[]
        def local():
            value=self.temp();owned.append(value);return value
        def child(value, d):
            value=self.emit_expression(value,d);owned.append(value);return value
        kind=syntax_kind(node)
        self.emitted_kinds[kind.__name__] = self.emitted_kinds.get(kind.__name__, 0) + 1
        if kind in (ast.Call, ast.New, ast.DynamicNew, ast.Attribute, ast.Index, ast.Await):
            self.service_boundaries += 1
        emit(depth,f'{result} = {converted} = None')
        emit(depth,f'{vm}.compiled_before({handle})')
        emit(depth,'try:')
        d=depth+1
        emit(d,f'{services}.guard({handle})')
        if kind is ast.Literal: emit(d,f'{result} = {handle}.value')
        elif kind is ast.Name: emit(d,f'{result} = {vm}.semantic_name({handle})')
        elif kind is ast.Group: emit(d,f'{result} = {child(node.expression,d)}')
        elif kind is ast.Unary:
            if node.operator not in ('NOT','+','-'):raise UnsupportedExpression('fused unary operator')
            value=child(node.operand,d);emit(d,f'{result} = {helper}.unary({node.operator!r}, {value})')
        elif kind is ast.Binary:
            if node.operator not in ('AND','OR','=','<>','<','<=','>','>=','+','-','*','/','%'):
                raise UnsupportedExpression('fused binary operator')
            left=child(node.left,d)
            if node.operator in ('AND','OR'):
                emit(d,f'{result} = {helper}.boolean({left})')
                emit(d,f'if {"not " if node.operator=="OR" else ""}{result}:')
                right=child(node.right,d+1)
                emit(d+1,f'{result} = {helper}.boolean({right})')
            else:
                right=child(node.right,d)
                emit(d,f'{result} = {helper}.binary({node.operator!r}, {left}, {right})')
        elif kind is ast.Conditional:
            condition=child(node.condition,d);emit(d,f'if {helper}.boolean({condition}):')
            yes=child(node.when_true,d+1);emit(d+1,f'{result} = {yes}')
            emit(d,'else:');no=child(node.when_false,d+1);emit(d+1,f'{result} = {no}')
        elif kind is ast.Attribute:
            receiver=local();obj=self.bind(node.object)
            emit(d,f'{receiver} = {vm}.import_receiver({obj})')
            emit(d,f'if {receiver} is None:')
            value=child(node.object,d+1);emit(d+1,f'{receiver} = {value}')
            emit(d,f'{result} = yield from {services}.access.read_attribute({vm}, {receiver}, {node.name!r})')
        elif kind is ast.Index:
            value=child(node.object,d);bound=local()
            emit(d,f'{bound} = {services}.access.prepare_index_read({vm}, {value})')
            index=child(node.index,d)
            emit(d,f'{result} = yield from {bound}.finish({index})')
        elif kind is ast.Call:
            emit(d,f'{result} = yield from {services}.call({handle})')
        elif kind is ast.New:
            emit(d,f'{result} = yield from {vm}.semantic_new({handle}, _evaluation={services})')
        elif kind is ast.DynamicNew:
            emit(d,f'{result} = yield from {vm}.semantic_dynamic_new({handle}, _evaluation={services})')
        elif kind is ast.Await:
            emit(d,f'{helper}.require_transfer("Await")')
            emit(d,f'{helper}.forbid_transfer({vm}._transaction_backend())')
            value=child(node.operand,d)
            emit(d,f'{result} = yield {helper}.AwaitRequest({value})')
            emit(d,f'{services}.guard({handle})')
        else: emit(d,f'raise {helper}.UnsupportedExpression({("unsupported fused expression: "+kind.__name__)!r})')
        emit(depth,f'except BaseException as {error}:')
        emit(d,f'{result} = None')
        emit(d,f'{converted} = {vm}.compiled_exception({handle}, {error})')
        emit(d,f'if {converted} is {error}: raise')
        emit(d,f'raise {converted} from None')
        emit(depth,'finally:')
        # Assignment is safe for branch-local temporaries not initialized on the
        # untaken branch; it neither reads them nor invokes arbitrary values.
        emit(d,' = '.join([converted,*owned])+' = None')
        emit(depth,'try:')
        emit(d,f'{result} = {vm}.compiled_after({handle}, {result})')
        emit(depth,'except BaseException:')
        emit(d,f'{result} = None');emit(d,'raise')
        return result
