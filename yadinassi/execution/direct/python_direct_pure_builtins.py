"""Bind canonical pure services only in whole units with no host effects."""
from dataclasses import dataclass
from decimal import Decimal
from types import BuiltinMethodType, MappingProxyType, MethodType

from yadinassi.syntax import ast
from yadinassi.text import strings
from yadinassi.types import values
from yadinassi.types.values import HostFunction, NULL, _DIRECT_COLLECTION_CLASS_ABI

_SELECTED = (strings.string_length, strings.line_count, strings.upper, strings.lower,
             strings.trim_left, strings.trim_right, strings.trim_all,
             strings.is_blank, strings.starts_with, strings.ends_with, strings.left, strings.right)
_TWO_ARGS = (strings.starts_with, strings.ends_with, strings.left, strings.right)
# Numeric-producing builtins can attach their native implementation here.
_NATIVE_RESULTS = {strings.string_length: ('number', strings._string_length_units),
                   strings.line_count: ('number', strings._line_count_units)}
_BOOLEAN_RESULTS = (strings.is_blank, strings.starts_with, strings.ends_with)
_ABI = MappingProxyType({
    name.casefold(): (function, 2 if function in _TWO_ARGS else 1,
                      *_NATIVE_RESULTS.get(function, ('bool' if function in _BOOLEAN_RESULTS else 'string', function)))
    for primary, function, english in strings.BUILTINS if function in _SELECTED
    for name in (primary, english)
})
_MESSAGES = frozenset(('message', 'сообщить'))
_PRESENT = values._DIRECT_TO_STRING_ABI
_PRESENT_CODE = values._DIRECT_TO_STRING_CODE
_PRESENT_ARRAY = dict(values._DIRECT_COLLECTION_HELPER_ABI)['BSLArray']


def _literal_message(context, message):
    context.vm.output(strings.normalize_utf16_pairs(message))


def _literal_message_binding(vm, service):
    from yadinassi import runtime

    if (type(vm) is not runtime.Interpreter
            or runtime.Interpreter.__getattribute__ is not object.__getattribute__
            or vm._configuration_runtime is not None or vm._family_owner is not vm):
        return False
    output = vm.output
    implementation = service.function
    return (type(implementation) is MethodType and implementation.__self__ is vm
            and implementation.__func__ is runtime._DIRECT_CONFIGURATION_MESSAGE_ABI
            and implementation.__func__.__code__ is runtime._DIRECT_MESSAGE_CODE
            and service.returns_value is True and not service.reference_parameters
            and HostFunction.__call__.__code__ is values._DIRECT_HOST_FUNCTION_CALL_CODE
            and runtime.to_string is _PRESENT and values.to_string is _PRESENT
            and _PRESENT.__code__ is _PRESENT_CODE and values.BSLArray is _PRESENT_ARRAY
            and values.Decimal is Decimal and values.NULL is NULL
            and not any(key in vars(values) for key in ('isinstance', 'bool', 'str'))
            and type(output) is BuiltinMethodType and output.__name__ == 'append'
            and type(output.__self__) is list)


_HOST_CALL = next(dict(entries)['__call__'] for cls, _, entries in _DIRECT_COLLECTION_CLASS_ABI
                  if cls is HostFunction)
_SCALAR_TYPES = frozenset(map(id, (str, int, bool, Decimal, type(None))))
_ALLOWED = frozenset((ast.Literal, ast.Name, ast.Group, ast.Unary, ast.Binary,
                      ast.Conditional, ast.Assign, ast.ExpressionStatement,
                      ast.If, ast.For, ast.While, ast.Break, ast.Continue))


@dataclass(frozen=True)
class PureBindings:
    names: frozenset
    services: frozenset

    def active(self, vm, context=None):
        from .python_direct_services import builtin_binding
        if (vm.allow_extensions or vm.imports or vm.database_context is not None
                or HostFunction.__call__ is not _HOST_CALL
                or HostFunction.__getattribute__ is not object.__getattribute__
                or (context is not None and (context.policy is not None or context._services is not vm.functions))):
            return False
        state=vm.variables;registry=vm.functions;snapshot=vm._builtin_functions
        # A non-str key may run Python equality while looking up an otherwise
        # innocent name. Plain dictionaries themselves are checked at admission.
        if any(type(key) is not str for mapping in (state,registry) for key in mapping):
            return False
        modules=getattr(vm,'_direct_routine_modules',{})
        return (all(value is NULL or id(type(value)) in _SCALAR_TYPES
                    for name in self.names for value in (state.get(name),))
                and all(name not in modules and builtin_binding(registry.get(name), snapshot.get(name))
                        and ((context is None or not context._verify_context)
                             and _literal_message_binding(vm, registry[name]) if name in _MESSAGES
                             else registry[name].function is _ABI[name][0])
                        for name in self.services))


def _summarize(nodes, *, literal_output=False):
    """Describe one effect-free region; decline any unknown operation."""
    names=set();services=set()
    output_statement = None
    for node in nodes:
        kind=type(node)
        if kind is ast.Call:
            if type(node.callee) is not ast.Name:return None
            name=node.callee.name.casefold();entry=_ABI.get(name)
            if (literal_output and name in _MESSAGES and node is output_statement
                    and len(node.arguments) == 1 and type(node.arguments[0]) is ast.Literal
                    and type(node.arguments[0].value) is str):
                services.add(name)
                continue
            if entry is None or len(node.arguments)!=entry[1]:return None
            services.add(name)
        elif literal_output and kind is ast.ExpressionStatement:
            output_statement = node.expression
        elif kind not in _ALLOWED:
            return None
        elif kind is ast.Name:names.add(node.name.casefold())
        elif kind is ast.For:names.add(node.name.casefold())
        elif kind is ast.Literal and node.value is not NULL and id(type(node.value)) not in _SCALAR_TYPES:
            return None
    return PureBindings(frozenset(names),frozenset(services))


def analyze(nodes):
    result = _summarize(nodes, literal_output=True)
    return result if result is not None and result.services else None


def prefix(program):
    from .python_direct import _nodes

    names, services = set(), set()
    end = 0
    for node in program:
        facts = _summarize(_nodes(node))
        if facts is None:
            break
        names.update(facts.names)
        services.update(facts.services)
        end += 1
    return end, PureBindings(frozenset(names), frozenset(services)) if services else None


def has_literal_output(bindings):
    return not _MESSAGES.isdisjoint(bindings.services)


def result_kinds(names):
    return {name: ('null' if name in _MESSAGES else _ABI[name][2]) for name in names}


def resolve(name, *, native_numbers=False):
    return _literal_message if name in _MESSAGES else _ABI[name][3 if native_numbers else 0]
