"""Default trusted-client AST -> Python execution. No legacy fallback.

Client execution with either supported compilation profile and an explicit
host-selected catalog/query bridge live here. Configuration and forms use separate
direct entry points. Standalone client async routines use the owned scheduler.
Registered host services remain trusted
Python capabilities, not a sandbox.
"""
from dataclasses import dataclass, fields
from copy import copy
from decimal import Decimal, localcontext
from yadinassi.syntax import ast
from yadinassi.types.values import HostFunction


class PythonDirectUnsupported(ValueError):
    """A direct-backend contract is unavailable, before source effects."""


REPAIRS=('typed_map_keys','array_index_contract','array_insert_shape',
         'constructor_bounds','byref_routines','error_boundaries',
         'service_boundaries','bsl_truth','bsl_presentation','native_order','uca_string_order',
         'typed_find','structure_fields','method_values','dynamic_host_refs',
         'live_module_state','execute_fragments','array_identity_equality','structure_identity_equality','map_identity_equality','decimal_division','numeric_boolean_equality')


def _nodes(value):
    if isinstance(value,ast.Node):
        yield value
        for field in fields(value):
            if field.name!='token':yield from _nodes(getattr(value,field.name))
    elif isinstance(value,(list,tuple)):
        for item in value:yield from _nodes(item)


def _reject(message):
    raise PythonDirectUnsupported('python-direct: '+message)


def _admit_vm(vm,*,_transaction_owner=None,_async_entry=False,_async_guard=None):
    from yadinassi.runtime import Interpreter, _COMPILED_BASE_ABI_NAMES, _COMPILED_BASE_ABI, _DIRECT_VISITOR_ABI
    if type(vm) is not Interpreter:
        _reject('specialized Interpreter contexts are not integrated')
    for name,expected in zip(_COMPILED_BASE_ABI_NAMES,_COMPILED_BASE_ABI):
        if name in vars(vm) or vars(Interpreter).get(name) is not expected:
            _reject('custom policy/storage hooks are not integrated')
    if '_visit' in vars(vm) or vars(Interpreter).get('_visit') is not _DIRECT_VISITOR_ABI:
        _reject('custom visitor hooks are not integrated')
    from yadinassi.execution import safe_mode
    from yadinassi.db import source_transactions, database_transactions
    if safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None:
        _reject('application safe-mode/transaction contexts are not integrated')
    from .python_direct_transactions import check as check_transaction
    check_transaction(_transaction_owner,vm.database_context)
    if (vm._configuration_runtime is not None
            or (vm._family_owner is not vm and not _owned_import_child(vm)) or vm.locals is not None
            or not vm._has_module_context or vm.execution_context!='client'):
        _reject('configuration/server/NoContext contexts are not integrated')
    # The frontend has already selected branches using this source profile.
    # Compilation symbols do not grant server dispatch or a runtime context.
    if vm.compilation_profile not in ('standalone','managed-thick-file'):
        _reject('compilation profile is not integrated')
    if vm.database_context is not None:
        from yadinassi.db.database_context import SQLiteDBContext
        if type(vm.database_context) is not SQLiteDBContext:
            _reject("direct database requires host-selected SQLiteDBContext")
    if _async_guard is not None:_async_guard()
    if ((vm._scheduler.is_active and _async_guard is None)
            or (vm._scheduler.pending and not (_async_entry or _async_guard is not None))
            or getattr(vm,'_direct_active',False)):
        _reject('nested or asynchronous execution is not integrated')
    from .python_direct_imports import check_live
    check_live(vm)
    if vm.routines or vm.server_routines or vm._invocation_bindings:
        _reject('legacy imports/routine registries are not direct modules')
    if type(vm.variables) is not dict or type(vm.functions) is not dict or type(vm.types) is not dict or type(vm.module_names) is not set:
        _reject('custom namespace mappings are not supported')
    if vm.allow_extensions:
        for key,value in vm.functions.items():
            if type(key) is not str or type(value) is not HostFunction:
                _reject('host registry requires canonical HostFunction entries')
    # Plain mode validates the actual effectful lookup, not unused entries.


def _source_facts(program,*,allow_async=False):
    if type(program) is not list:
        _reject('execute_program requires a parsed AST list')
    nodes=tuple(_nodes(program))
    routines=frozenset(node.name.casefold() for node in program if type(node) is ast.Routine)
    routine_nodes=[node for node in program if type(node) is ast.Routine]
    if any(type(node) is ast.Var and node.execution_context=='server' for node in program) and not any(node.execution_context=='server' for node in routine_nodes):
        _reject('server variables require a server routine in the same declaration module')
    constructors=set();calls=set();checked_async=False
    native_names={'array','массив','map','соответствие','structure','структура','uuid','уникальныйидентификатор'}
    for node in nodes:
        if node.token is None:
            _reject('execute_program requires source tokens on every node')
        if not checked_async and (type(node) is ast.Await or type(node) is ast.Routine and node.is_async is not False):
            from yadinassi.syntax.parser import validate_async
            validate_async(program)
            checked_async=True
        if type(node) is ast.Var and node.execution_context not in ('client','server'):
            _reject('unsupported declaration side')
        if type(node) is ast.New and node.name.casefold() in native_names:
            constructors.add(node.name.casefold())
        if type(node) is ast.Routine and ((node.is_async and not allow_async) or (not node.module_context and not node.is_dual and node.execution_context!='server') or node.execution_context not in ('client','server')):
            _reject('async source routines are not integrated')
        if type(node) is ast.Import and node not in program:
            _reject('imports require module scope')
        if type(node) is ast.Call:
            callee=node.callee
            while type(callee) is ast.Group:callee=callee.expression
            if type(callee) is ast.Name:calls.add(callee.name.casefold())
    groups={}
    for node in routine_nodes:groups.setdefault(node.name.casefold(),[]).append(node)
    for group in groups.values():
        if any(node.is_dual for node in group):
            if (len(group)!=2 or not all(node.is_dual and not node.module_context for node in group)
                    or {node.execution_context for node in group}!={'client','server'}
                    or len({(node.token.source,node.token.line,node.token.column,node.token.kind) for node in group})!=1):
                _reject('dual routines require one client and one server declaration')
            def signature(node):
                return (node.is_function,[(p.name.casefold(),p.by_value,p.default) for p in node.parameters])
            if signature(group[0])!=signature(group[1]):_reject('dual routine signatures differ')
        elif len(group)!=1:_reject('duplicate routine declarations')
    return nodes,routines,frozenset(constructors),frozenset(calls)


def _admit_bindings(vm,routines,constructors,calls):
    if routines:
        ports=getattr(vm,'_direct_invocation_ports',None)
        if ports and not routines.isdisjoint(ports):
            _reject('invocation name already bound')
    if not constructors and not calls:return
    from yadinassi.types.values import BSLArray
    from yadinassi.collections.maps import BSLMap
    from yadinassi.collections.structures import BSLStructure
    from yadinassi.types.unique_identifiers import BSLUUID
    native_types={'array':BSLArray,'массив':BSLArray,'map':BSLMap,'соответствие':BSLMap,'structure':BSLStructure,'структура':BSLStructure,'uuid':BSLUUID,'уникальныйидентификатор':BSLUUID}
    for name in constructors:
        constructor=vm.types.get(name)
        if type(constructor) is not HostFunction or constructor.function is not native_types[name]:
            _reject('overridden direct collection constructors are not integrated')
    from .python_direct_routines import validate_calls
    validate_calls(vm,calls-routines)


def admit(vm,program,*,_async_entry=False):
    _admit_vm(vm,_async_entry=_async_entry)
    nodes,routines,constructors,calls=_source_facts(program,allow_async=_async_entry)
    from .python_direct_imports import preflight
    preflight(vm,program)
    _admit_bindings(vm,routines,constructors,calls)
    return nodes,routines,calls


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
    _routines: frozenset
    _constructors: frozenset
    _calls: frozenset
    _returns_expression: bool
    _exports: object
    _server_layout: frozenset
    _server_declared: frozenset
    _import_layout: frozenset
    _import_facts: object


def _contract(vm):
    return (vm.execution_backend, vm.native_target, vm.compilation_profile,
            vm.compiled_ast_contract, vm.database_context is not None,
            vm.allow_extensions, vm._family_owner.__dict__.get('_standalone_script') is True)


def _compile(vm,program,nodes,source_text,source_name,*,_exports=False):
    from yadinassi.execution.codegen.direct_emitter import compile_module
    from .python_direct_database import METADATA_NAMES, NAMES
    names=NAMES if vm.database_context is not None else METADATA_NAMES
    return compile_module(vm,program,nodes,source_text,source_name,_exports=_exports,
                          external_names=names,
                          constructor_profile=(vm.types if vm.allow_extensions else vm._builtin_types))


def _extension_source_audit(vm):
    from yadinassi.runtime import Interpreter
    return type(vm) is Interpreter and vm.allow_extensions


def _snapshot(value):
    """Copy parser-owned structure without invoking host deepcopy hooks."""
    from yadinassi.syntax.lexer import Token
    from yadinassi.temporal.dates import BSLDate
    from yadinassi.types.values import NULL

    # Capture the current syntax vocabulary once per copy. Retain actual classes
    # as values, but check IDs so unadmitted types cannot run metaclass hooks.
    base = ast.Node
    literal = ast.Literal
    nodes = {id(cls): cls for cls in vars(ast).values()
             if isinstance(cls, type) and issubclass(cls, base)}
    nodes[id(Token)] = Token
    scalars = {id(cls): cls for cls in (str, int, float, bool, Decimal, type(None), BSLDate)}

    def copy_node(item):
        kind = type(item)
        identity = id(kind)
        if item is NULL or identity in scalars:
            return item
        if kind is list:
            return [copy_node(part) for part in item]
        if kind is tuple:
            return tuple(copy_node(part) for part in item)
        if identity in nodes:
            if kind is literal and not (item.value is NULL or id(type(item.value)) in scalars):
                _reject('prepared AST literals require immutable parser values')
            return kind(**{field.name: copy_node(getattr(item, field.name)) for field in fields(item)})
        _reject('prepared AST contains unsupported host payloads')

    return copy_node(value)


def prepare_module(vm,program,*,source_text=None,source_name=None):
    from .python_direct_async import entry_mode
    mode=entry_mode(vm,program)
    admit(vm,program,_async_entry=mode)
    if vm._family_closed:
        _reject('prepared modules require an open interpreter')
    if vm.execution_backend != 'python-direct':
        _reject('prepared modules require the python-direct backend')
    from yadinassi.runtime import Interpreter
    Interpreter._require_family(vm)
    # The caller may edit/reuse its AST after this call. Never retain that AST.
    owned=_snapshot(program)
    nodes,routines,constructors,calls=_source_facts(owned,allow_async=mode)
    plan=_compile(vm,owned,nodes,source_text,source_name)
    declared=frozenset(name.casefold() for node in owned if type(node) is ast.Var and node.execution_context=='client' for name in node.names)
    from .python_direct_routines import prepare as prepare_routines
    exports=prepare_routines(vm,owned,plan) if routines or any(type(n) is ast.ServerInitializer for n in owned) else None
    server_declared=frozenset(name.casefold() for node in owned if type(node) is ast.Var and node.execution_context=='server' for name in node.names)
    server_layout=server_declared.union(*(m.server_layout for m in getattr(vm,'_direct_routine_modules',{}).values()))
    from .python_direct_imports import import_names, prepare_facts
    facts=prepare_facts(vm,owned)
    return PreparedDirectModule(tuple(owned),plan,frozenset(vm.module_names)|declared,
                                declared,_contract(vm),routines,constructors,calls,
                                bool(owned and type(owned[-1]) is ast.ExpressionStatement),exports,server_layout,server_declared,
                                frozenset(import_names(vm,facts=facts)),facts)


def execute_prepared(vm,prepared):
    if type(prepared) is not PreparedDirectModule:
        raise TypeError('execute_prepared requires a PreparedDirectModule')
    return execute(vm,None,_prepared=prepared)


def execute(vm,program,*,source_text=None,source_name=None,_prepared=None):
    from .python_direct_async import entry_mode
    mode=entry_mode(vm,program if _prepared is None else _prepared._snapshot)
    if _prepared is None:
        nodes,routines,calls=admit(vm,program,_async_entry=mode)
        declared=frozenset(name.casefold() for node in program if type(node) is ast.Var and node.execution_context=='client' for name in node.names)
        returns_expression=bool(program and type(program[-1]) is ast.ExpressionStatement)
    else:
        _admit_vm(vm,_async_entry=mode)
        from .python_direct_imports import preflight,import_names
        preflight(vm,facts=_prepared._import_facts)
        if frozenset(import_names(vm,facts=_prepared._import_facts))!=_prepared._import_layout:
            _reject('prepared import namespace layout changed; prepare again')
        _admit_bindings(vm,_prepared._routines,_prepared._constructors,_prepared._calls)
        routines=_prepared._routines
        declared=_prepared._declared
        returns_expression=_prepared._returns_expression
    if _prepared is not None:
        if vm._family_closed:
            _reject('prepared modules require an open interpreter')
        if _contract(vm) != _prepared._contract:
            _reject('prepared backend/target/profile contract changed; prepare again')
        current_server_layout=_prepared._server_declared.union(*(m.server_layout for m in getattr(vm,'_direct_routine_modules',{}).values()))
        if current_server_layout != _prepared._server_layout:
            _reject('prepared server module-name layout changed; prepare again')
        if frozenset(vm.module_names)|_prepared._declared != _prepared._layout:
            _reject('prepared module-name layout changed; prepare again')
    from yadinassi.runtime import Interpreter
    Interpreter._require_family(vm)
    from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
    from yadinassi.execution import safe_mode
    from yadinassi.db import source_transactions, database_transactions
    from yadinassi.execution.codegen.native_targets import target_context
    from yadinassi.execution.execution_policy import execution_backend_policy
    plan=_compile(vm,program,nodes,source_text,source_name) if _prepared is None else copy(_prepared._plan)
    if _prepared is None:plan._generated_tree=None
    from .python_direct_routines import prepare as prepare_routines, resolve as resolve_routine
    exports=(_prepared._exports if _prepared is not None else
             prepare_routines(vm,program,plan,retain_generated=False) if routines or any(type(n) is ast.ServerInitializer for n in program) else None)
    from .python_direct_routines import validate_calls
    prospective=dict(getattr(vm,'_direct_routine_modules',{}))
    if exports is not None:prospective.update({name:exports for name in exports.signatures})
    if _prepared is not None:
        calls=_prepared._calls
    elif source_text is None:
        # An externally supplied AST does not have the parsed-text ownership
        # contract. Preserve its late verification before effects.
        calls=_source_facts(program,allow_async=mode)[3]
    initializers=tuple(getattr(vm,'_direct_server_initializers',()))
    if exports is not None and exports.initializer_plan is not None:initializers+= (exports,)
    validate_calls(vm,calls,registry=prospective,layout=frozenset(vm.module_names)|declared,initializers=initializers)
    context=None
    async_scheduler=None
    database=vm.database_context
    from yadinassi.runtime import _DIRECT_EXECUTION_SCOPE_ABI
    with _DIRECT_EXECUTION_SCOPE_ABI(vm):
        vm.module_names.update(declared)
        if exports is not None:
            if not hasattr(vm,'_direct_routine_modules'):vm._direct_routine_modules={}
            vm._direct_routine_modules.update({name:exports for name in exports.signatures})
        vm._direct_server_initializers=initializers
        previous_transactions=getattr(vm,"_transaction_activation_allowed",True)
        if database is not None:vm._transaction_activation_allowed=False
        vm._direct_active=True
        try:
            with target_context(vm.native_target), execution_backend_policy('python-direct'), localcontext() as decimal_context:
                decimal_context.prec=38
                from .python_direct_imports import initialize, record_exports
                incoming=program if _prepared is None else ()
                facts=None if _prepared is None else _prepared._import_facts
                record_exports(vm,incoming,facts=facts)
                from yadinassi.db.database_transactions import admission as transaction_admission
                with transaction_admission(False):
                    initialize(vm,incoming,facts=facts)
                # A synchronous root may have just loaded an async module.
                if not mode and getattr(vm,'_direct_import_async',False):
                    mode=entry_mode(vm,incoming)
                pump=mode and vm._family_owner is vm
                if pump:async_scheduler=vm._scheduler
                vm._transaction_activation_allowed=previous_transactions
                from .python_direct_transactions import execution as transaction_execution
                with transaction_execution(vm) as owner:
                    if mode:
                        from .python_direct_async import root_guard
                        context=make_boundary(vm,_transaction_owner=owner,_async_guard=root_guard(vm))
                    else:
                        context=make_boundary(vm,_transaction_owner=owner)
                    if pump:
                        from .python_direct_async import inline_root
                        result=inline_root(vm,plan,context)
                    else:
                        result=plan.run(vm.variables,context=context)
            if pump:context._check()
            vm._self_module.ready=True
            if pump:vm._pump_async()
            vm._hybrid_stats['python_direct_modules']=vm._hybrid_stats.get('python_direct_modules',0)+1
            if pump:
                error=async_scheduler.take_procedure_error()
                if error is not None:raise error
            if returns_expression:
                if type(result) is list:
                    # The Python-facing Array keeps its identity. Normalize
                    # numeric leaves of this returned list only, not VM state.
                    for index,value in enumerate(result):
                        if type(value) is int:result[index]=Decimal(value)
                return result
            return None if result is vm.variables else result
        finally:
            if context is not None:context._routine_exports.clear()
            if async_scheduler is not None:async_scheduler.procedure_errors.clear()
            vm._direct_active=False
            vm._transaction_activation_allowed=previous_transactions


def make_boundary(vm,*,_parent_check=None,_transaction_owner=None,_async_guard=None):
    from .python_direct_database import CatalogBoundary
    from .python_direct_live_metadata import LiveMetadataBoundary
    from .python_direct_detached_metadata import DetachedMetadataBoundary
    database = vm.database_context
    sqlite_attached=False
    if database is not None:
        from yadinassi.db.database_context import SQLiteDBContext
        from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
        sqlite_attached=type(database) is SQLiteDBContext and type(database.backend) is SQLiteCatalogBackend
    from .python_direct_services import ServicesBoundary
    from .python_direct_value_tree import ValueTreeBoundary
    from .python_direct_imports import ImportBoundary,check_live
    from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
    from yadinassi.execution import safe_mode
    from yadinassi.db import source_transactions, database_transactions
    from .python_direct_routines import bind_omissions, resolve as resolve_routine
    class DirectBoundary(ImportBoundary,ValueTreeBoundary,ServicesBoundary, LiveMetadataBoundary, DetachedMetadataBoundary, CatalogBoundary, BoundaryContext):
        def current_module(self):
            return vm._self_module

        def character_namespace(self,key):
            if key in vm.variables:return vm.variables[key]
            if key in self._services or key in getattr(vm,'_direct_routine_modules',{}):
                return self.missing_value(key)
            from yadinassi.text.chars import CHARS
            return CHARS

        def character_namespace_reference(self,key):
            if key in vm.variables:
                from yadinassi.execution.codegen.experimental_naked_live_state import source_reference
                return source_reference(vm.variables,key)
            return self.external_reference(key)

        def missing_value(self,name):
            if name.casefold() in getattr(vm,'_direct_routine_modules',{}):
                from yadinassi.execution.codegen.experimental_naked_collections import _routine_value_error
                return _routine_value_error(name)
            return super().missing_value(name)

        def resolve_optional_service(self,name,*args,_non_name_actuals=(),**kwargs):
            key=name.casefold()
            module=getattr(vm,'_direct_routine_modules',{}).get(key)
            if module is not None and key in module.server_names:
                if self._verify_context or key not in module.dual_names:self._check()
                if getattr(vm,'_direct_routine_modules',{}).get(key) is module:
                    return resolve_routine(self,key,require_value=kwargs.get('require_value',False),
                                           allow_references=kwargs.get('allow_references',False),
                                           argument_count=kwargs.get('argument_count'),crossing_omissions=True,
                                           non_name_actuals=_non_name_actuals)
            if module is not None and key not in module.server_names and key not in module.dual_names:
                bound=self.resolve_service(name,*args,**kwargs)
                if getattr(self.vm,'_direct_routine_modules',{}).get(key) is module:
                    return bind_omissions(bound)
                return bound
            return super().resolve_optional_service(name,*args,**kwargs)

        def _unregistered_service(self,name):
            from .python_direct_names import NAMES
            if name.casefold() in NAMES:
                raise ValueError('Значение не является функцией: '+name)
            # A missing BSL routine during ordinary Eval is a language error,
            # not a denial of an existing host or transaction capability.
            depth=getattr(self,'_eval_depth',None)
            if (depth and depth[0] and self.policy is None
                    and getattr(self,'_direct_transaction_owner',None) is None and vm.database_context is None
                    and not name.startswith('new:')):
                raise ValueError('Переменная или функция не определена: '+name)
            super()._unregistered_service(name)

        def resolve_service(self,name,*args,_non_name_actuals=(),**kwargs):
            modules=getattr(vm,'_direct_routine_modules',None)
            key=name.casefold()
            ports=getattr(vm,'_direct_invocation_ports',None)
            entry=None if ports is None else ports.get(key)
            if entry is not None:
                from yadinassi.execution.invocation import resolve_direct_invocation
                return resolve_direct_invocation(self,key,entry,require_value=kwargs.get('require_value',False),
                    argument_count=kwargs.get('argument_count'))
            module=None if modules is None else modules.get(key)
            if module is not None:
                if self._verify_context or (key in module.server_names and key not in module.dual_names):self._check()
                routine=resolve_routine(self,key,require_value=kwargs.get('require_value',False),
                                        allow_references=kwargs.get('allow_references',False),
                                        argument_count=kwargs.get('argument_count'),
                                        non_name_actuals=_non_name_actuals)
                if routine is not None:return routine
            if key in ('new:uuid','new:уникальныйидентификатор'):
                from yadinassi.types.unique_identifiers import BSLUUID
                if self._verify_context:self._check()
                factory=vm.types.get(name.split(':',1)[1].casefold())
                if type(factory) is not HostFunction or factory.function is not BSLUUID:
                    raise BoundaryViolation('UUID constructor requires canonical registration')
                return super().resolve_callable(factory)
            if not args and key not in self._services and not key.startswith('new:'):
                value=vm.variables.get(key)
                if type(value) is HostFunction:
                    return self.resolve_extension_value(
                        value,require_value=kwargs.get('require_value',False),
                        allow_references=kwargs.get('allow_references',False))
            return super().resolve_service(name,*args,**kwargs)

        def leave(self):
            super().leave()
            # Do not audit a normal light exit. A Python object supplied by
            # an embedding can still run code and close the interpreter.
            if not self._verify_context and vm._family_closed:
                raise BoundaryViolation('python-direct interpreter was closed during execution')

        def _check_effect(self):
            if self._verify_context:
                self._check()
                return
            # Only the external effect's owning activation must still be live.
            # Its resource/receiver authorization is checked by the operation.
            self._check_lease()
            if _parent_check is not None:_parent_check()
            if vm._family_closed:
                raise BoundaryViolation('python-direct interpreter was closed during execution')
            if (vm.database_context is not database or vm._configuration_runtime is not None
                    or vm.execution_context!='client'):
                raise BoundaryViolation('python-direct owner context changed during external operation')
            if database is not None:
                from .python_direct_transactions import check as check_transaction
                check_transaction(_transaction_owner,database)

        _check_lent_reference=True

        def _check(self,*,_lent=None):
            super()._check()
            if _lent is not None:
                from .python_direct_lent_refs import LendScope
                if type(_lent) is not LendScope:
                    raise BoundaryViolation('invalid dual reference lend')
                _lent.check(self)
            if _parent_check is not None:_parent_check()
            if self._import_check_required or vm.imports or vm._family_owner is not vm:
                check_live(vm)
                self._import_check_required=True
            if vm._family_closed:
                raise BoundaryViolation('python-direct interpreter was closed during execution')
            if (vm._configuration_runtime is not None or vm.database_context is not database
                    or vm.locals is not None or (not vm._has_module_context and _lent is None)
                    or vm.execution_context!='client'
                    or safe_mode._CURRENT.get() is not None
                    or source_transactions._current.get() is not None
                    or (_async_guard is None and (vm._scheduler.is_active or vm._scheduler.pending))):
                raise BoundaryViolation('python-direct restricted context changed at a host boundary')
            if _async_guard is not None:_async_guard()
            from .python_direct_transactions import check as check_transaction
            check_transaction(_transaction_owner,database)
    # The live registry is assigned below; a normalized throwaway copy grants
    # nothing and must not be rebuilt on every invocation.
    if _async_guard is None:
        context=DirectBoundary()
    else:
        from .python_direct_async import bind_context, promise_opaque
        class AsyncBoundary(DirectBoundary):
            def _check_effect(self):
                super()._check_effect()
                if not self._verify_context:_async_guard()

            def get_member(self,value,name):
                promise_opaque(value)
                return super().get_member(value,name)

            def resolve_member(self,value,name):
                promise_opaque(value)
                return super().resolve_member(value,name)

        context=AsyncBoundary()
        bind_context(context,vm)
    context.vm=vm
    context._verify_context=(vm.allow_extensions or _parent_check is not None
                             or (database is not None and not sqlite_attached))
    # Attaching an ordinary SQLite database is not a host crossing. Runtime
    # SQL and transaction operations keep their own checks; dynamic code is
    # deliberately stricter whenever a database is attached.
    context._verify_dynamic_context=context._verify_context or database is not None
    if not context._verify_context and vm._family_owner is vm:
        context._known_method_local=True
        context._known_method_db=sqlite_attached

    context._restrict_python_extensions=not vm.allow_extensions
    context._direct_transaction_owner=_transaction_owner
    context._register_root=vm._information_registers if sqlite_attached else None
    context._import_check_required=bool(vm.imports)
    context._routine_exports={}
    # Preserve live registry updates at subsequent host boundaries, not a copy.
    context._services=vm.functions
    return context


def _owned_import_child(vm):
    from .python_direct_imports import owned_child
    return owned_child(vm)
