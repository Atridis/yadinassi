"""Persistent code only; generated routine closures belong to one execution."""
from dataclasses import dataclass
from copy import copy

from .values import HostFunction, Reference
from .experimental_naked_live_state import _ForwardReference
from .experimental_naked_errors import convert_error


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


def prepare(vm, program, plan):
    from .syntax import ast
    from .python_direct import _snapshot, _source_facts, _contract
    declarations=_snapshot([node for node in program if type(node) in (ast.Var,ast.Routine)])
    nodes,names,constructors,calls=_source_facts(declarations)
    if not names:return None
    exports=copy(plan)
    exports.last_state=None;exports.output=None
    signatures={node.name.casefold():(node.is_function,
        max((i+1 for i,p in enumerate(node.parameters) if p.default is None),default=0),
        len(node.parameters),frozenset(i for i,p in enumerate(node.parameters) if not p.by_value))
        for node in declarations if type(node) is ast.Routine}
    declared={name.casefold() for node in declarations if type(node) is ast.Var and node.execution_context=='client' for name in node.names}
    server=[node for node in declarations if node.execution_context=='server']
    server_names=frozenset(node.name.casefold() for node in server if type(node) is ast.Routine)
    server_layout=frozenset(name.casefold() for node in server if type(node) is ast.Var for name in node.names)
    server_layout=server_layout.union(*(m.server_layout for m in getattr(vm,'_direct_routine_modules',{}).values()))
    server_plan=None
    if server_names:
        from .experimental_naked_collections import prepare as compile_server
        from .python_direct import REPAIRS
        from .python_direct_names import NAMES
        server_plan=compile_server(plan.source_text,source_name=plan.source_name,parsed_ast=server,
            repairs=REPAIRS,module_names=tuple(server_layout),external_names=tuple(NAMES),constructors=('uuid','уникальныйидентификатор'),
            _trusted_entry=True,_export_routines=True)
    return RoutineModule(exports,signatures,_contract(vm),frozenset(vm.module_names)|declared,
                         constructors,calls-names,server_plan,server_names,server_layout)


def validate_calls(vm, calls, seen=None, *, registry=None, layout=None):
    from .python_direct import _contract, _reject, _admit_bindings
    registry=getattr(vm,'_direct_routine_modules',{}) if registry is None else registry
    layout=frozenset(vm.module_names) if layout is None else layout
    seen=set() if seen is None else seen
    for name in calls:
        module=registry.get(name)
        if module is None or id(module) in seen:continue
        seen.add(id(module))
        if module.contract!=_contract(vm):_reject('persistent routine backend/target/profile contract changed; redeclare')
        if module.layout!=layout:_reject('persistent routine module-name layout changed; redeclare')
        current_server_layout=frozenset().union(*(m.server_layout for m in registry.values()))
        if module.server_names and module.server_layout!=current_server_layout:
            _reject('persistent server module-name layout changed; redeclare')
        if any(registry.get(key) is not module for key in module.signatures):
            _reject('routines declared together were partially replaced; redeclare the module')
        _admit_bindings(vm,frozenset(),module.constructors,frozenset())
        validate_calls(vm,module.calls,seen,registry=registry,layout=layout)


def resolve(context, name, *, require_value=False, allow_references=False, argument_count=None):
    vm=context.vm
    module=getattr(vm,'_direct_routine_modules',{}).get(name)
    if module is None:return None
    validate_calls(vm,(name,))
    returns_value,minimum,maximum,references=module.signatures[name]
    if argument_count is not None and not minimum<=argument_count<=maximum:
        raise TypeError('Неверное количество аргументов: '+name)
    if name in module.server_names:
        from .python_direct_server import resolve_server
        return resolve_server(context,module,name,require_value=require_value,allow_references=allow_references)
    if getattr(context,'_server_side',False):
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
