"""Opt-in module-only Decimal For compiler. NOT a Python security sandbox.

All eligibility checks finish before loop effects. Unsupported loops run unchanged
in the interpreter; execution errors never trigger replay. Default is interpreter.
"""
import ast as pyast
import time
import sys
from decimal import Decimal
from .syntax import ast
from .values import require_number
from .errors import BSLRuntimeError

class Unsupported(Exception):
    pass

def translate_error(error, token):
    message = str(error) or type(error).__name__
    if isinstance(error, ZeroDivisionError):
        message = 'Деление на ноль'
    return BSLRuntimeError(message, token.source, token.line, token.column,
                           source_line=token.source_line)

class Compiler:
    def __init__(self, vm):
        self.known = {k for k,v in vm.variables.items() if type(v) is Decimal}
        self.constants = []
        self.tokens = []
        self.lines = []
        self.serial = 0
        self.visited = 0

    def line(self, text, indent=0):
        self.lines.append('    ' * (indent + 1) + text)

    def guarded(self, expression, node, indent):
        self.serial += 1
        name = f't{self.serial}'
        index = len(self.tokens)
        self.tokens.append(node.token)
        self.line('try:', indent)
        self.line(f'{name} = {expression}', indent+1)
        self.line('except (ArithmeticError, ValueError, TypeError, IndexError, RecursionError) as error:', indent)
        self.line(f'raise translate_error(error, tokens[{index}]) from None', indent+1)
        return name

    def expression(self, node, indent, depth=0):
        self.visited += 1
        if depth > 64 or self.visited > 2048:
            raise Unsupported("compile budget")
        if type(node) is ast.Literal and type(node.value) is Decimal:
            i = len(self.constants)
            self.constants.append(node.value)
            return f'constants[{i}]'
        if type(node) is ast.Name:
            key = node.name.casefold()
            if key not in self.known:
                raise Unsupported('name is not a proven Decimal slot')
            return f'variables[{key!r}]'
        if type(node) is ast.Group:
            return self.expression(node.expression, indent, depth+1)
        if type(node) is ast.Unary and node.operator in ('+', '-'):
            value = self.expression(node.operand, indent, depth+1)
            value = f'number({value})'
            if node.operator == '-': value += '.copy_negate()'
            return self.guarded(value, node, indent)
        if type(node) is ast.Binary and node.operator in ('+', '-', '*'):
            # Materialize the left operand BEFORE evaluating the right subtree.
            left = self.guarded(self.expression(node.left, indent, depth+1), node.left, indent)
            right = self.expression(node.right, indent, depth+1)
            return self.guarded(f'number({left}) {node.operator} number({right})', node, indent)
        raise Unsupported('unsupported expression')

    def build(self, node):
        if type(node) is not ast.For: raise Unsupported('For only')
        if type(node.body) is not list or len(node.body) > 256:
            raise Unsupported('compile body budget')
        start = self.guarded(f'number({self.expression(node.start, 0)})', node, 0)
        end = self.guarded(f'number({self.expression(node.end, 0)})', node, 0)
        key = node.name.casefold()
        # Reserved/import names cannot be silently written as plain slots.
        if key in ('thisobject', 'этотобъект'): raise Unsupported('reserved counter')
        self.known.add(key)
        self.line(f'variables[{key!r}] = {start}')
        self.line(f'while number(variables[{key!r}]) <= {end}:')
        for statement in node.body:
            if type(statement) is not ast.Assign or type(statement.target) is not ast.Name:
                raise Unsupported('body supports only plain numeric assignments')
            target = statement.target.name.casefold()
            if target in ('thisobject', 'этотобъект'): raise Unsupported('reserved target')
            value = self.expression(statement.value, 1)
            self.line(f'variables[{target!r}] = {value}', 1)
            self.known.add(target)
        # Re-read the counter after body, never Python range or cached counter.
        self.line(f'variables[{key!r}] = number(variables[{key!r}]) + one', 1)
        code = 'def execute(variables, constants, tokens, number, one, translate_error):\n' + '\n'.join(self.lines) + '\n'
        module = pyast.parse(code, filename='<hybrid-generated>')
        namespace = {}
        exec(compile(module, '<hybrid-generated>', 'exec'), namespace)
        return namespace['execute'], tuple(self.constants), tuple(self.tokens)

def eligible(vm):
    # Runtime snapshots are recorded at class definition, not at first backend use.
    # Both instance and later class instrumentation must keep ordinary dispatch.
    from .runtime import Interpreter, _HYBRID_RUNTIME_HOOKS
    from . import runtime
    if (type(vm) is not Interpreter or runtime.require_number is not require_number
            or sys.gettrace() is not None or sys.getprofile() is not None):
        return False
    for name, original in _HYBRID_RUNTIME_HOOKS.items():
        if name in vm.__dict__ or Interpreter.__dict__.get(name) is not original:
            return False
    return (vm.locals is None and type(vm.variables) is dict
            and vm._has_module_context and vm._configuration_runtime is None
            and vm._database_context is None and vm._family_owner is vm
            and vm.compilation_profile == 'standalone' and not vm.imports
            and vm._eval_depth[0] == 0)


def execute_for(vm, node):
    """Return False before effects for fallback; never replay an execution error."""
    stats = vm._hybrid_stats
    if not eligible(vm):
        stats['fallback'] += 1
        return False
    started = time.perf_counter()
    try:
        function, constants, tokens = Compiler(vm).build(node)
    except (Unsupported, RecursionError):
        stats['fallback'] += 1
        return False
    finally:
        stats['compile_seconds'] += time.perf_counter() - started
    stats['compiled'] += 1
    function(vm.variables, constants, tokens, require_number, Decimal(1), translate_error)
    return True
