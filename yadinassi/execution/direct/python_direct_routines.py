"""Persistent code only; generated routine closures belong to one execution."""
from dataclasses import dataclass
from copy import copy

from yadinassi.types.values import HostFunction, Reference
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
from yadinassi.execution.codegen.experimental_naked_errors import convert_error


@dataclass(frozen=True)
class RoutineModule:
    plan: object
    signatures: dict
    contract: tuple
    layout: frozenset
    constructors: frozenset
    calls: frozenset
    server_plan: object = None
    server_names: frozenset = frozenset()
    server_layout: frozenset = frozenset()
    initializer_plan: object = None
    initializer_constructors: frozenset = frozenset()
    initializer_calls: frozenset = frozenset()
    nocontext_plan: object = None
    nocontext_names: frozenset = frozenset()
    dual_plan: object = None
    dual_names: frozenset = frozenset()
    local_function_exports: frozenset = frozenset()
    async_names: frozenset = frozenset()


def prepare(vm, program, plan, *, retain_generated=True):
    from yadinassi.syntax import ast
    from .python_direct import _snapshot, _source_facts, _contract
    declarations=_snapshot([node for node in program if type(node) in (ast.Var,ast.Routine,ast.ServerInitializer)])
    async_names=frozenset(node.name.casefold() for node in declarations if type(node) is ast.Routine and node.is_async)
    nodes,names,constructors,calls=_source_facts(declarations,allow_async=bool(async_names))
    initializer_body=[item for node in declarations if type(node) is ast.ServerInitializer for item in node.body]
    if not names and not initializer_body:return None
    exports=copy(plan)
    exports.last_state=None;exports.output=None
    signatures={node.name.casefold():(node.is_function,
        max((i+1 for i,p in enumerate(node.parameters) if p.default is None),default=0),
        len(node.parameters),frozenset(i for i,p in enumerate(node.parameters) if not (node.is_async or p.by_value)))
        for node in declarations if type(node) is ast.Routine}
    declared={name.casefold() for node in declarations if type(node) is ast.Var and node.execution_context=='client' for name in node.names}
    server=[node for node in declarations if type(node) is not ast.ServerInitializer and node.execution_context=='server']
    server_names=frozenset(node.name.casefold() for node in server if type(node) is ast.Routine)
    nocontext=[node for node in server if type(node) is ast.Routine and not node.module_context]
    nocontext_names=frozenset(node.name.casefold() for node in nocontext)
    server=[node for node in server if type(node) is not ast.Routine or node.module_context]
    server_layout=frozenset(name.casefold() for node in server if type(node) is ast.Var for name in node.names)
    server_layout=server_layout.union(*(m.server_layout for m in getattr(vm,'_direct_routine_modules',{}).values()))
    server_plan=None
    if server_names or initializer_body or any(type(n) is ast.Routine and n.is_dual for n in declarations):
        from yadinassi.execution.codegen.experimental_direct_ast import compile_owned as compile_server
        from .python_direct import REPAIRS
        from .python_direct_services import ORDINARY_CONSTRUCTORS
        from .python_direct_names import NAMES
        from yadinassi.db.database_context import SQLiteDBContext
        external_names=tuple(NAMES)
        base_constructors=tuple(ORDINARY_CONSTRUCTORS)+('uuid','уникальныйидентификатор')
        # Recognize Query even without a database; its factory checks at use.
        constructor_names=base_constructors+('query','запрос')
        if type(vm.database_context) is SQLiteDBContext:
            # The existing owned catalog namespace supplies query parameters;
            # no other database/server services are added to this profile.
            external_names+=('catalogs','справочники')
    if server_names-nocontext_names:
        server_plan=compile_server(server,source_text=plan.source_text,source_name=plan.source_name,
            module_names=tuple(server_layout),external_names=external_names,constructors=constructor_names,
            exports=True,retain_generated=retain_generated,current_module=True)
    nocontext_plan=None
    if nocontext:
        nocontext_plan=compile_server(nocontext,source_text=plan.source_text,source_name=plan.source_name,
            external_names=external_names,constructors=constructor_names,
            exports=True,retain_generated=retain_generated)
    dual=[node for node in declarations if type(node) is ast.Routine and node.is_dual and node.execution_context=='client']
    dual_names=frozenset(node.name.casefold() for node in dual)
    dual_plan=None
    if dual:
        dual_plan=compile_server(dual,source_text=plan.source_text,source_name=plan.source_name,
            external_names=external_names,constructors=constructor_names,
            exports=True,retain_generated=retain_generated)
    initializer_plan=None;initializer_constructors=initializer_calls=frozenset()
    if initializer_body:
        _,_,initializer_constructors,initializer_calls=_source_facts(initializer_body)
        initializer_plan=compile_server(initializer_body,retain_generated=retain_generated,source_text=plan.source_text,source_name=plan.source_name,
            module_names=tuple(server_layout),external_names=tuple(NAMES),constructors=base_constructors,current_module=True)
    local_function_exports=frozenset(node.name.casefold() for node in declarations
        if type(node) is ast.Routine and node.exported and node.is_function
        and not node.is_async and not node.is_dual and node.execution_context=='client'
        and node.module_context)
    return RoutineModule(exports,signatures,_contract(vm),frozenset(vm.module_names)|declared,
                         constructors,calls-names,server_plan,server_names,server_layout,
                         initializer_plan,initializer_constructors,initializer_calls,nocontext_plan,nocontext_names,dual_plan,dual_names,local_function_exports,async_names)


def validate_calls(vm, calls, seen=None, *, registry=None, layout=None, initializers=None):
    if not calls:return
    from .python_direct import _contract, _reject, _admit_bindings
    registry=getattr(vm,'_direct_routine_modules',{}) if registry is None else registry
    layout=frozenset(vm.module_names) if layout is None else layout
    initializers=getattr(vm,'_direct_server_initializers',()) if initializers is None else initializers
    seen=set() if seen is None else seen
    for name in calls:
        module=registry.get(name)
        if module is None or id(module) in seen:continue
        seen.add(id(module))
        if module.contract!=_contract(vm):_reject('persistent routine backend/target/profile contract changed; redeclare')
        if module.layout!=layout:_reject('persistent routine module-name layout changed; redeclare')
        if module.server_names-module.nocontext_names:
            current_server_layout=frozenset().union(*(m.server_layout for m in registry.values()))
            if module.server_layout!=current_server_layout:
                _reject('persistent server module-name layout changed; redeclare')
        if any(registry.get(key) is not module for key in module.signatures):
            _reject('routines declared together were partially replaced; redeclare the module')
        _admit_bindings(vm,frozenset(),module.constructors,frozenset())
        validate_calls(vm,module.calls,seen,registry=registry,layout=layout,initializers=initializers)
        if module.server_names-module.nocontext_names:
            for initializer in initializers:
                marker=('initializer',id(initializer))
                if marker in seen:continue
                seen.add(marker)
                if initializer.contract!=_contract(vm):_reject('server initializer contract changed; reload in a fresh interpreter')
                if initializer.server_layout!=current_server_layout:_reject('server initializer layout changed; reload in a fresh interpreter')
                _admit_bindings(vm,frozenset(),initializer.initializer_constructors,frozenset())
                validate_calls(vm,initializer.initializer_calls,seen,registry=registry,layout=layout,initializers=initializers)


def bind_omissions(bound):
    """Attach the generated BSL routine's positional omission protocol."""
    from yadinassi.execution.codegen.experimental_naked_collections import _OMITTED_REF

    def omissions(current, positions, count):
        return current, dict.fromkeys(positions, _OMITTED_REF)

    bound.prepare_omissions=omissions
    return bound


def resolve(context, name, *, require_value=False, allow_references=False, argument_count=None, crossing_omissions=False, non_name_actuals=()):
    vm=context.vm
    module=getattr(vm,'_direct_routine_modules',{}).get(name)
    if module is None:return None
    validate_calls(vm,(name,))
    returns_value,minimum,maximum,references=module.signatures[name]
    if argument_count is not None and not minimum<=argument_count<=maximum:
        from yadinassi.execution.codegen.experimental_naked_collections import _argument_count_error
        _argument_count_error(name,maximum,argument_count)
    if name in module.dual_names and not getattr(context,'_server_side',False):
        from .python_direct_server import resolve_dual_client
        return resolve_dual_client(context,module,name,require_value=require_value,allow_references=allow_references)
    if name in module.server_names:
        # A root async task is already admitted to its live, database-free
        # client activation. Its synchronous server call does not suspend.
        # Imported tasks continue to use the narrower import admission.
        if (getattr(context,'_async_task',False) and vm._family_owner is not vm
                and (getattr(context,'_async_import_nocontext',None)!=name
                     or name not in module.nocontext_names or references)):
            raise ValueError('Серверный вызов из асинхронного задания пока не поддерживается')
        from .python_direct_server import resolve_server
        return resolve_server(context,module,name,require_value=require_value,allow_references=allow_references,
                              allow_omissions=crossing_omissions,non_name_actuals=non_name_actuals)
    if getattr(context,'_server_side',False) or getattr(context,'module_context',True) is False:
        raise TypeError('Вызов клиентской подпрограммы с сервера запрещён')
    def invoke(*arguments):
        # Rebind code to current state/services/boundary, never retain an old VM
        # activation or re-run module statements. Declared variables already exist.
        exports=context._routine_exports.get(id(module))
        if exports is None:
            exports=module.plan.function(vm.variables,module.plan.constants,[],context,True)
            context._routine_exports[id(module)]=exports
        arguments=tuple(_ForwardReference(value) if i in references and type(value) is Reference else value
                        for i,value in enumerate(arguments))
        try:return exports[name](*arguments)
        except Exception as error:
            converted=convert_error(error,module.plan.source_name,module.plan.source_text)
            if converted is error:raise
            raise converted from None
    function=HostFunction(name,invoke,reference_parameters=references,returns_value=returns_value)
    return context.resolve_callable(function,require_value=require_value,allow_references=allow_references)
