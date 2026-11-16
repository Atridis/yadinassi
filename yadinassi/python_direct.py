"""Default trusted-standalone AST -> Python execution. No legacy fallback.

Standalone execution and an explicit host-selected catalog/query bridge live
here. Configuration and forms use separate direct entry points; unsupported
async/server/NoContext contracts still require explicit compiled-strict. Registered host services remain trusted
Python capabilities, not a sandbox.
"""
from dataclasses import dataclass, fields
from copy import copy
from decimal import Decimal, localcontext
from .syntax import ast
from .values import HostFunction


class PythonDirectUnsupported(ValueError):
    """A direct-backend contract is unavailable, before source effects."""


REPAIRS=('typed_map_keys','array_index_contract','array_insert_shape',
         'constructor_bounds','byref_routines','error_boundaries',
         'service_boundaries','bsl_truth','bsl_presentation','native_order',
         'typed_find','structure_fields','method_values','dynamic_host_refs',
         'live_module_state')


def _nodes(value):
    if isinstance(value,ast.Node):
        yield value
        for field in fields(value):
            if field.name!='token':yield from _nodes(getattr(value,field.name))
    elif isinstance(value,(list,tuple)):
        for item in value:yield from _nodes(item)


def _reject(message):
    raise PythonDirectUnsupported('python-direct: '+message+'; select --legacy or execution_backend="compiled-strict"')


def admit(vm,program):
    from .runtime import Interpreter, _COMPILED_BASE_ABI_NAMES, _COMPILED_BASE_ABI, _HYBRID_RUNTIME_HOOKS
    if type(vm) is not Interpreter:
        _reject('specialized Interpreter contexts are not integrated')
    for name,expected in zip(_COMPILED_BASE_ABI_NAMES,_COMPILED_BASE_ABI):
        if name in vars(vm) or vars(Interpreter).get(name) is not expected:
            _reject('custom policy/storage hooks are not integrated')
    if '_visit' in vars(vm) or vars(Interpreter).get('_visit') is not _HYBRID_RUNTIME_HOOKS['_visit']:
        _reject('custom visitor hooks are not integrated')
    from . import safe_mode, source_transactions, database_transactions
    if safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None or database_transactions._execution.get() is not None:
        _reject('application safe-mode/transaction contexts are not integrated')
    if (vm._configuration_runtime is not None
            or vm._family_owner is not vm or vm.locals is not None
            or not vm._has_module_context or vm.execution_context!='client'
            or vm.compilation_profile!='standalone'):
        _reject('configuration/database/server/NoContext contexts are not integrated')
    if vm.database_context is not None:
        from .database_context import SQLiteDBContext
        if type(vm.database_context) is not SQLiteDBContext:
            _reject("direct database requires host-selected SQLiteDBContext")
    if vm._scheduler.is_active or vm._scheduler.pending or getattr(vm,'_direct_active',False):
        _reject('nested or asynchronous execution is not integrated')
    if vm.imports or vm.routines or vm.server_routines or vm._invocation_bindings:
        _reject('legacy imports/routine registries are not direct modules')
    if type(vm.variables) is not dict or type(vm.functions) is not dict or type(vm.types) is not dict or type(vm.module_names) is not set:
        _reject('custom namespace mappings are not supported')
    if any(type(key) is not str or type(value) is not HostFunction for key,value in vm.functions.items()):
        _reject('host registry requires canonical HostFunction entries')
    if type(program) is not list:
        _reject('execute_program requires a parsed AST list')
    nodes=tuple(_nodes(program))
    current={node.name.casefold() for node in program if type(node) is ast.Routine}
    previous=getattr(vm,'_direct_routine_names',set())
    from .values import BSLArray
    from .maps import BSLMap
    from .structures import BSLStructure
    native_types={'array':BSLArray,'массив':BSLArray,'map':BSLMap,'соответствие':BSLMap,'structure':BSLStructure,'структура':BSLStructure}
    for node in nodes:
        if node.token is None:
            _reject('execute_program requires source tokens on every node')
        if type(node) is ast.Var and node.execution_context!='client':
            _reject('server declarations are not integrated')
        if type(node) is ast.New and node.name.casefold() in native_types:
            constructor=vm.types.get(node.name.casefold())
            if type(constructor) is not HostFunction or constructor.function is not native_types[node.name.casefold()]:
                _reject('overridden direct collection constructors are not integrated')
        if type(node) is ast.Routine and (node.is_async or node.is_dual or not node.module_context or node.execution_context!='client'):
            _reject('async/server/NoContext source routines are not integrated')
        if type(node) is ast.Import or type(node) is ast.ServerInitializer:
            _reject('imports/server initialization are not integrated')
        if type(node) is ast.Call:
            callee=node.callee
            while type(callee) is ast.Group:callee=callee.expression
            if type(callee) is ast.Name and callee.name.casefold() in previous-current:
                _reject('routines do not persist across execute calls; redeclare the routine in this source')
    return nodes,current


@dataclass(frozen=True, slots=True)
class PreparedDirectModule:
    """Owned source snapshot; no VM, authorization or execution-state cache.

    Private fields are implementation details and must not be modified. Use
    Interpreter.execute_prepared to run against current state and permissions.
    """
    _snapshot: tuple
    _plan: object
    _layout: frozenset
    _declared: frozenset
    _contract: tuple


def _contract(vm):
    return (vm.execution_backend, vm.native_target, vm.compilation_profile,
            vm.compiled_ast_contract)


def _compile(vm,program,nodes,source_text,source_name):
    from .experimental_naked_collections import prepare,UnsupportedNakedSyntax
    from .python_direct_database import NAMES as DATABASE_NAMES
    source_name=source_name or (nodes[0].token.source if nodes else '<строка>')
    if source_text is None:
        lines={node.token.line:node.token.source_line for node in nodes if node.token is not None}
        source_text='\n'.join(lines.get(line,'') for line in range(1,max(lines,default=0)+1))
    try:
        plan=prepare(source_text,source_name=source_name,repairs=REPAIRS,
                     module_names=tuple(vm.module_names),
                     constructors=("query","запрос") if vm.database_context is not None else (),
                     external_names=DATABASE_NAMES if vm.database_context is not None else (),parsed_ast=program,_trusted_entry=True,_return_last_expression=True)
    except UnsupportedNakedSyntax as error:
        _reject(str(error))
    return plan


def _snapshot(value):
    """Copy parser-owned structure without invoking host deepcopy hooks."""
    from .syntax.lexer import Token
    from .dates import BSLDate
    from .values import NULL
    kind=type(value)
    if value is NULL or any(kind is cls for cls in (str,int,float,bool,Decimal,type(None),BSLDate)):
        return value
    if kind is list:return [_snapshot(item) for item in value]
    if kind is tuple:return tuple(_snapshot(item) for item in value)
    node_types=tuple(cls for cls in vars(ast).values() if isinstance(cls,type) and issubclass(cls,ast.Node))
    if kind is Token or any(kind is cls for cls in node_types):
        if kind is ast.Literal and not (value.value is NULL or any(type(value.value) is cls for cls in (str,int,float,bool,Decimal,type(None),BSLDate))):
            _reject('prepared AST literals require immutable parser values')
        return kind(**{field.name:_snapshot(getattr(value,field.name)) for field in fields(value)})
    _reject('prepared AST contains unsupported host payloads')


def prepare_module(vm,program,*,source_text=None,source_name=None):
    admit(vm,program)
    if vm._family_closed:
        _reject('prepared modules require an open interpreter')
    if vm.execution_backend != 'python-direct':
        _reject('prepared modules require the python-direct backend')
    from .runtime import Interpreter
    Interpreter._require_family(vm)
    # The caller may edit/reuse its AST after this call. Never retain that AST.
    owned=_snapshot(program)
    nodes=tuple(_nodes(owned))
    plan=_compile(vm,owned,nodes,source_text,source_name)
    declared=frozenset(name.casefold() for node in owned if type(node) is ast.Var for name in node.names)
    return PreparedDirectModule(tuple(owned),plan,frozenset(vm.module_names)|declared,
                                declared,_contract(vm))


def execute_prepared(vm,prepared):
    if type(prepared) is not PreparedDirectModule:
        raise TypeError('execute_prepared requires a PreparedDirectModule')
    return execute(vm,list(prepared._snapshot),_prepared=prepared)


def execute(vm,program,*,source_text=None,source_name=None,_prepared=None):
    nodes,routines=admit(vm,program)
    if _prepared is not None:
        if vm._family_closed:
            _reject('prepared modules require an open interpreter')
        if _contract(vm) != _prepared._contract:
            _reject('prepared backend/target/profile contract changed; prepare again')
        if frozenset(vm.module_names)|_prepared._declared != _prepared._layout:
            _reject('prepared module-name layout changed; prepare again')
    from .runtime import Interpreter
    Interpreter._require_family(vm)
    from .experimental_naked_boundaries import BoundaryContext,BoundaryViolation
    from . import safe_mode,source_transactions,database_transactions
    from .native_targets import target_context
    from .execution_policy import execution_backend_policy
    plan=_compile(vm,program,nodes,source_text,source_name) if _prepared is None else copy(_prepared._plan)
    from .python_direct_database import CatalogBoundary
    database = vm.database_context
    class DirectBoundary(CatalogBoundary, BoundaryContext):
        def _check(self):
            super()._check()
            if vm._family_closed:
                raise BoundaryViolation('python-direct interpreter was closed during execution')
            if (vm._configuration_runtime is not None or vm.database_context is not database
                    or vm.locals is not None or not vm._has_module_context
                    or vm.execution_context!='client'
                    or safe_mode._CURRENT.get() is not None
                    or source_transactions._current.get() is not None
                    or database_transactions._execution.get() is not None):
                raise BoundaryViolation('python-direct restricted context changed at a host boundary')
    context=DirectBoundary(services=vm.functions)
    context.vm=vm
    # Preserve live registry updates at subsequent host boundaries, not a copy.
    context._services=vm.functions
    vm.module_names.update(name.casefold() for node in program if type(node) is ast.Var for name in node.names)
    vm._direct_routine_names=getattr(vm,'_direct_routine_names',set())|routines
    previous_transactions=getattr(vm,"_transaction_activation_allowed",True)
    if database is not None:vm._transaction_activation_allowed=False
    vm._direct_active=True
    try:
        with target_context(vm.native_target), execution_backend_policy('python-direct'), localcontext() as decimal_context:
            decimal_context.prec=38
            result=plan.run(vm.variables,context=context)
        vm._self_module.ready=True
        vm._hybrid_stats['python_direct_modules']=vm._hybrid_stats.get('python_direct_modules',0)+1
        if program and type(program[-1]) is ast.ExpressionStatement:return result
        return None if result is vm.variables else result
    finally:
        vm._direct_active=False
        vm._transaction_activation_allowed=previous_transactions
