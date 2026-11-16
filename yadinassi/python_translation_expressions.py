"""Expression-to-Python lowering with explicit value-service boundaries.

No AST execution adapters. The embedding driver owns admission, source mapping,
budgets and trusted service binding. Merely compiling an expression is not
permission to run it. Calls requiring references/omissions are explicitly
unsupported until the embedding service provides their dedicated lowering.
"""
from dataclasses import dataclass
from decimal import Decimal
from .syntax import ast
from .owned_syntax import syntax_kind
from . import dates, strings
from .values import boolean, divide, equal, require_number, to_string
from .collation import string_key
from .safe_mode import require_transfer
from .database_transactions import forbid_transfer
from .async_runtime import AwaitRequest

class UnsupportedExpression(Exception):
    pass


def unary(operator, value):
    if operator == 'NOT':
        return not boolean(value)
    value = require_number(value)
    if operator == '+': return value
    if operator == '-': return value.copy_negate()
    raise ValueError(f'Неизвестный оператор: {operator}')


def binary(operator, left, right):
    if operator in ("=", "<>", "<", "<=", ">", ">="):
        if type(left) is dates.BSLDate:
            left.require_known()
        if type(right) is dates.BSLDate:
            right.require_known()
    if (operator in ("=", "<>", "<", "<=", ">", ">=")
            and ((type(left) is Decimal and type(right) is bool)
                 or (type(left) is bool and type(right) is Decimal))):
        # BSL operator comparisons convert Boolean to Number (0 or 1).
        # Keep this separate from typed collection lookup equality.
        left = Decimal(1 if left else 0) if type(left) is bool else left
        right = Decimal(1 if right else 0) if type(right) is bool else right
    if operator == "=":
        return equal(left, right)
    if operator == "<>":
        return not equal(left, right)
    if operator in ("<", "<=", ">", ">="):
        if type(left) is dates.BSLDate and type(right) is dates.BSLDate:
            left, right = Decimal(left.ticks), Decimal(right.ticks)
        if type(left) is not type(right) or not isinstance(left, (Decimal, str, bool)):
            raise TypeError("Значения несовместимы для сравнения")
        if isinstance(left, str):
            left, right = string_key(left), string_key(right)
        if operator == "<":
            return left < right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        return left >= right
    if operator == "+" and isinstance(left, str):
        return strings.concatenate(left, to_string(right))
    if type(left) is dates.BSLDate and operator in ("+", "-"):
        if operator == "-" and type(right) is dates.BSLDate:
            return dates.date_difference(left, right)
        if type(right) is not Decimal:
            raise TypeError("Арифметика даты: ожидается число секунд")
        return dates.shift_date(left, right if operator == "+" else right.copy_negate())
    left, right = require_number(left), require_number(right)
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if operator == "/":
        return divide(left, right)
    if operator == "%":
        if right == 0:
            raise ZeroDivisionError
        return left % right
    raise ValueError(f"Неизвестный оператор: {operator}")

@dataclass(frozen=True)
class CallSite:
    # Immutable syntax only. Never store a resolved callable, receiver or grant.
    node: object
    callee: object
    callee_kind: str
    name: object
    has_omissions: bool


@dataclass(frozen=True)
class ExpressionPlan:
    functions: dict
    nodes: tuple
    source: str
    sync_functions: object = None
    binding_count: int = 0
    call_sites: object = None

    def bind(self, vm, *, guard, access, resolve=None, leaf_resolve=None):
        """guard(node) must perform current admission/budget/security accounting."""
        return ExpressionExecution(self, vm, guard, access, resolve, leaf_resolve)


class ExpressionExecution:
    def __init__(self, plan, vm, guard, access, resolve=None, leaf_resolve=None):
        self.plan, self.vm, self.guard, self.access = plan, vm, guard, access
        self.resolve=resolve
        self.leaf_resolve=leaf_resolve
        self._bound_callee = None

    def with_bound_callee(self, node, value):
        """Trusted runtime override for field/builtin name collisions.

        The source call identity stays admitted; no synthesized AST or late
        compiler is introduced. Scope the captured host to this invocation only.
        """
        item = self.plan.functions.get(id(node))
        if (item is None or item[0] is not node) and self._external_leaf(node) is None:
            raise UnsupportedExpression('bound callee not in prepared source')
        clone = ExpressionExecution(self.plan, self.vm, self.guard, self.access, self.resolve,self.leaf_resolve)
        clone._bound_callee = (node, value)
        return clone

    def bound_callee(self, node):
        return (self._bound_callee[1],) if self._bound_callee is not None and self._bound_callee[0] is node else ()

    def _external_leaf(self, node):
        return None if self.leaf_resolve is None else self.leaf_resolve(node)

    def leaf_node(self, identity):
        item=self._external_leaf(identity)
        if item is None:raise UnsupportedExpression('owned leaf identity not admitted')
        return item[0]

    def leaf_id(self, identity):
        item=self._external_leaf(identity)
        if item is None:raise UnsupportedExpression('owned leaf identity not admitted')
        return self.leaf(item[0],_resolved_external=item)

    def leaf(self, node, *, _resolved_external=None):
        """Invoke a source-admitted synchronous leaf; never dispatch AST kinds."""
        functions=self.plan.sync_functions
        item=functions.get(id(node)) if functions is not None else None
        external=(_resolved_external if _resolved_external is not None else self._external_leaf(node)) if item is None else None
        if external is not None:item=external
        if item is None or item[0] is not node:
            raise UnsupportedExpression('synchronous leaf not admitted')
        # A resolved item is used only within this synchronous invocation, never
        # cached across a hook, suspension, or another evaluation.
        value=converted=None
        self.vm.compiled_before(node)
        try:
            try:
                self.guard(node)
                value=(self._bound_callee[1] if self._bound_callee is not None and self._bound_callee[0] is node
                       else item[1](self.vm,node) if external is not None else item[1](self))
            except BaseException as error:
                converted=self.vm.compiled_exception(node,error)
                if converted is error:raise
                raise converted from None
            return self.vm.compiled_after(node,value)
        finally:
            # A retained exception traceback must not retain a discarded value.
            value=converted=None

    def evaluate(self, node):
        external=self._external_leaf(node)
        if external is not None:
            return self.leaf(node,_resolved_external=external)
        if self.resolve is not None:
            stats=self.vm._compiled().stats
            stats['python_expression_registry_entries']=stats.get('python_expression_registry_entries',0)+1
        item = self.plan.functions.get(id(node))
        if item is None or item[0] is not node:
            if self.resolve is not None:
                found=self.resolve(node)
                if found is not None:
                    execution,view=found
                    return (yield from execution.evaluate(view))
            raise UnsupportedExpression('expression not prepared in this source version')
        self.vm.compiled_before(node)
        try:
            self.guard(node)
            if self._bound_callee is not None and self._bound_callee[0] is node:
                value = self._bound_callee[1]
            else:
                value = yield from item[1](self)
        except BaseException as error:
            converted = self.vm.compiled_exception(node, error)
            if converted is error:
                raise
            raise converted from None
        return self.vm.compiled_after(node, value)

    def receiver(self, node):
        imported = self.vm.import_receiver(node)
        return imported if imported is not None else (yield from self.evaluate(node))

    def argument(self, node):
        return (yield from self.vm.argument(node, _evaluation=self))

    def call_site(self, node):
        site=(self.plan.call_sites or {}).get(id(node))
        return site if site is not None and site.node is node else None

    def call(self, node, require_value=True):
        return (yield from self.vm.call(node, require_value=require_value, _evaluation=self))


def prepare_expressions(roots, *, max_source_bytes=100000, max_nodes=10000, max_function_bytes=4*1024*1024, owned_leaves=False, max_bindings=100_000):
    """Prepare owned/admitted expression roots, not arbitrary Python input.

    The plan has no late compiler. Drivers must include routine defaults in roots.
    AST identity is retained only for authority/source services, never dispatched
    through the AST evaluator. Unsupported syntax fails preparation explicitly.
    """
    nodes, slots, bodies = [], {}, []
    shared = {}
    templates = {}
    active = set()
    generated_templates = {}
    generated_bindings = {}
    binding_count = 0
    call_sites = {}
    from .python_translation_template_bindings import bind_generated_source
    def shared_body(text, slot):
        """Canonicalize source-bound operands at admission, never at execution."""
        nonlocal binding_count
        canonical,operands=bind_generated_source(text,nodes)
        name=generated_templates.get(canonical)
        if name is None:
            name=f'_expression_template_{len(generated_templates)}'
            generated_templates[canonical]=name
            bodies.append(f'def {name}(_s, _p):\n if False: yield None\n '+canonical.replace('\n','\n ')+'\n')
        binding_count+=len(operands)
        if binding_count>max_bindings:raise UnsupportedExpression('expression operand binding budget')
        generated_bindings[slot]=(name,tuple(operands))

    def lower(node):
        key = id(node)
        if owned_leaves and syntax_kind(node) in (ast.Literal,ast.Name):return None
        if key in active: raise UnsupportedExpression('cyclic syntax')
        if key in slots: return slots[key]
        if len(nodes) >= max_nodes: raise UnsupportedExpression('expression node budget')
        slot=len(nodes); slots[key]=slot; nodes.append(node); active.add(key)
        kind=syntax_kind(node)
        def handle(value):
            if owned_leaves and syntax_kind(value) in (ast.Literal,ast.Name):
                return f'_s.leaf_node({id(value)})'
            return f'_nodes[{lower(value)}]'
        def child(value):
            if owned_leaves and syntax_kind(value) in (ast.Literal,ast.Name):
                return f'_s.leaf_id({id(value)})'
            return f'(yield from _s.evaluate({handle(value)}))'
        if kind is ast.Literal: text=f'return _nodes[{slot}].value'
        elif kind is ast.Name: text=f'return _s.vm.semantic_name(_nodes[{slot}])'
        elif kind is ast.Group: text='return '+child(node.expression)
        elif kind is ast.Unary:
            if node.operator not in ('NOT','+','-'): raise UnsupportedExpression('unary operator')
            text=f'return _unary({node.operator!r}, {child(node.operand)})'
        elif kind is ast.Binary:
            if node.operator not in ('AND','OR','=','<>','<','<=','>','>=','+','-','*','/','%'):
                raise UnsupportedExpression('binary operator')
            left,right=child(node.left),child(node.right)
            if node.operator in ('AND','OR'):
                text=f'return _boolean({left}) {node.operator.lower()} _boolean({right})'
            else: text=f'return _binary({node.operator!r}, {left}, {right})'
        elif kind is ast.Conditional:
            text=f'return {child(node.when_true)} if _boolean({child(node.condition)}) else {child(node.when_false)}'
        elif kind is ast.Attribute:
            obj=handle(node.object)
            text=f'_value = yield from _s.receiver({obj})\nreturn (yield from _s.access.read_attribute(_s.vm, _value, {node.name!r}))'
        elif kind is ast.Index:
            text=f'_value = {child(node.object)}\n_bound = _s.access.prepare_index_read(_s.vm, _value)\n_index = {child(node.index)}\nreturn (yield from _bound.finish(_index))'
        elif kind is ast.Await:
            operand=child(node.operand)
            text=("_require_transfer('Await')\n"
                  "_forbid_transfer(_s.vm._transaction_backend())\n"
                  f"_value = {operand}\n"
                  "_result = yield _await_request(_value)\n"
                  f"_s.guard(_nodes[{slot}])\nreturn _result")
        elif kind is ast.Call:
            lower(node.callee)
            for arg in node.arguments:
                if syntax_kind(arg) is not ast.OmittedArgument: lower(arg)
            text=f'return (yield from _s.call(_nodes[{slot}]))'
        elif kind is ast.New:
            for arg in node.arguments:
                if syntax_kind(arg) is not ast.OmittedArgument: lower(arg)
            text=f'return (yield from _s.vm.semantic_new(_nodes[{slot}], _evaluation=_s))'
        elif kind is ast.DynamicNew:
            lower(node.type_expression)
            if node.parameters is not None: lower(node.parameters)
            text=f'return (yield from _s.vm.semantic_dynamic_new(_nodes[{slot}], _evaluation=_s))'
        else:
            text=f'raise _unsupported({("unsupported expression: " + kind.__name__)!r})'
        if kind in (ast.Literal, ast.Name, ast.Group):
            template_name = '_shared_' + kind.__name__
            template_text = {
                ast.Literal: 'return _node.value',
                ast.Name: 'return _s.vm.semantic_name(_node)',
                ast.Group: 'return (yield from _s.evaluate(_node.expression))',
            }[kind]
            templates[template_name] = ('def '+template_name+'(_s, _node):\n if False: yield None\n '+template_text+'\n')
            shared[slot] = template_name
        else:
            shared_body(text, slot)
        active.remove(key)
        return slot
    for root in roots: lower(root)
    for name in ('Literal','Name'):
        original=templates.get('_shared_'+name)
        if original is not None:
            templates['_shared_sync_'+name]=original.replace('_shared_'+name,'_shared_sync_'+name).replace(' if False: yield None\n','')
    bodies = list(templates.values()) + bodies
    if any(len(body.encode())>max_function_bytes for body in bodies):raise UnsupportedExpression('expression function source budget')
    source='\n'.join(bodies)
    if len(source.encode())>max_source_bytes: raise UnsupportedExpression('expression source budget')
    from .owned_syntax import is_owned
    for node in nodes:
        if syntax_kind(node) is ast.Call and is_owned(node):
            callee=node.callee
            while syntax_kind(callee) is ast.Group:
                callee=callee.expression
            kind=syntax_kind(callee)
            shape='name' if kind is ast.Name else 'attribute' if kind is ast.Attribute else 'other'
            # Five descriptor operands plus its registry key are charged.
            binding_count+=6
            if binding_count>max_bindings:raise UnsupportedExpression('expression binding budget')
            call_sites[id(node)]=CallSite(node,callee,shape,
                callee.name if shape != 'other' else None,
                any(syntax_kind(arg) is ast.OmittedArgument for arg in node.arguments))
    namespace={'_nodes':tuple(nodes),'_unary':unary,'_binary':binary,'_boolean':boolean,'_unsupported':UnsupportedExpression,
               '_require_transfer':require_transfer,'_forbid_transfer':forbid_transfer,
               '_await_request':AwaitRequest}
    exec(compile(source,'<bsl-python-expressions>','exec',dont_inherit=True), namespace)
    from types import FunctionType
    functions={}
    sync_functions={}
    for index,node in enumerate(nodes):
        if index in shared:
            template=namespace[shared[index]]
            function=FunctionType(template.__code__,namespace,template.__name__,(node,))
            sync_name=shared[index].replace('_shared_','_shared_sync_')
            if sync_name in namespace:
                sync=namespace[sync_name]
                sync_functions[id(node)]=(node,FunctionType(sync.__code__,namespace,sync.__name__,(node,)))
        else:
            name,operands=generated_bindings[index]
            template=namespace[name]
            function=FunctionType(template.__code__,namespace,template.__name__,(operands,))
        functions[id(node)]=(node,function)
    return ExpressionPlan(functions,tuple(nodes),source,sync_functions,binding_count,call_sites)
