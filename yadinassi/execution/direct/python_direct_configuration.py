"""Narrow direct declaration execution for configured startup/common modules.

Metadata owners and existing module/transport gates remain authoritative. No AST
execution, scheduler dispatcher, arbitrary host reflection or implicit fallback.
"""
from decimal import localcontext
from contextvars import ContextVar
from types import FunctionType
from weakref import WeakKeyDictionary, ref

_PARAMETERS = WeakKeyDictionary()

def parameter_snapshot(plan):
    function=plan.function
    if type(function) is not FunctionType:raise BoundaryViolation('configuration plan function changed')
    entry=_PARAMETERS.get(function)
    if entry is None or entry[0]() is not plan or plan._configuration_parameters is not entry[1]:
        raise BoundaryViolation('configuration parameter snapshot changed')
    return entry[1]


def parameter_entries(plan,routine):
    parameter_snapshot(plan)
    witness=_PARAMETERS[plan.function][2].get(id(routine))
    if witness is None or witness[0] is not routine:
        raise BoundaryViolation('configuration routine is not installed')
    return witness[1]


_COMMAND_SCOPE = ContextVar("direct_configuration_command", default=None)
from yadinassi.execution import safe_mode
from yadinassi.db import source_transactions, database_transactions
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Cell
from yadinassi.execution.codegen.experimental_direct_ast import compile_owned
from yadinassi.execution.codegen.experimental_naked_errors import convert_error
from .python_direct import REPAIRS, _snapshot
from yadinassi.execution.codegen.native_targets import target_context
from yadinassi.syntax import ast
from yadinassi.types.values import HostFunction


def check_owner(app, owner, *, allow_database=False):
    app.require_open()
    root=app.interpreter
    if (owner._family_owner is not root or owner._configuration_runtime is not app
            or owner._scheduler is not root._scheduler or root._family_closed
            or owner._family_released or owner._family_generation != root._family_generation):
        raise BoundaryViolation('direct configuration owner is no longer active')
    if (safe_mode._CURRENT.get() is not None or source_transactions._current.get() is not None
            or database_transactions._execution.get() is not None
            or root._scheduler.pending or root._scheduler._active_task is not None):
        raise BoundaryViolation('direct configuration restricted execution is not connected')
    if owner.database_context is not None and not allow_database:
        raise BoundaryViolation('direct configuration database execution is not connected')


class ConfigurationBoundary(BoundaryContext):
    def __init__(self,app,owner,routine=None):
        super().__init__()
        self._services=owner.functions
        self.app,self.owner,self.routine=app,owner,routine
        self._command_scope=_COMMAND_SCOPE.get()
        if self._command_scope is not None:
            from .python_direct_configuration_commands import _Scope
            if type(self._command_scope) is not _Scope:raise BoundaryViolation('invalid command scope')
    def _check(self):
        super()._check()
        scope=self._command_scope
        if _COMMAND_SCOPE.get() is not scope:
            raise BoundaryViolation('direct configuration boundary left its command context')
        # Within a command, scope validates state/thread/context before the
        # generic owner's catchable closed-application diagnostic. A revoked
        # command must not enter a BSL Except handler after a host callback.
        if scope is not None:scope.check(self.app,self.owner)
        else:check_owner(self.app,self.owner)
        if self.routine is not None:self.app.check_call(self.routine,self.owner)
    def external_get(self,name):
        self._check()
        if self._command_scope is not None:
            from .python_direct_configuration_metadata import ROOT_NAMES
            if name.casefold() in ROOT_NAMES:return self._command_scope.metadata.root(self)
        result=self.app.resolve_module(name,self.owner)
        if result is None:raise BoundaryViolation('unsupported configuration name: '+name)
        if self._command_scope is not None:self._command_scope.admit_module(name,result)
        return result
    def get_member(self,value,name):
        if self._command_scope is not None:
            from .python_direct_configuration_metadata import is_reader
            if is_reader(value):return self._command_scope.metadata.get(self,value,name)
        return super().get_member(value,name)

    def external_set(self,name,value):
        raise ValueError('common module names are read-only')
    def resolve_service(self,name,fallback=None,*,require_value=False,allow_references=False,argument_count=None):
        self._check()
        if name.casefold() in ('new:uuid','new:уникальныйидентификатор'):
            from yadinassi.types.unique_identifiers import BSLUUID
            alias=name.split(':',1)[1].casefold()
            factory=self.owner.types.get(alias)
            def validate():
                self._check()
                if (self.owner.types.get(alias) is not factory
                        or type(factory) is not HostFunction or factory.function is not BSLUUID
                        or type(factory.reference_parameters) is not frozenset or factory.reference_parameters
                        or factory.returns_value is not True):
                    raise BoundaryViolation('configuration UUID requires canonical constructor')
            validate()
            # Bind only the admitted scalar constructor. This does not authorize
            # arbitrary host services or extend command transfer/cache values.
            call=BoundaryContext.resolve_callable(self,factory,require_value=True)
            def construct(*args):
                validate()
                # Bound callable performs policy admission and the post-call
                # owner check; do not duplicate its finally check here.
                return call(*args)
            return construct
        function=self._services.get(name.casefold())
        if type(function) is not HostFunction:
            raise BoundaryViolation('unsupported configuration service: '+name)
        self.app.check_host_service(function,self.owner)
        scope=self._command_scope
        if scope is not None:scope.service(function,self.owner)
        call=super().resolve_service(name,require_value=require_value,allow_references=allow_references)
        def invoke(*args):
            self._check();self.app.check_host_service(function,self.owner)
            if scope is not None:scope.service(function,self.owner);scope.values(args)
            result=call(*args)
            if scope is not None:scope.values((result,))
            return result
        if allow_references:invoke.requires_reference=call.requires_reference
        return invoke
    def resolve_callable(self,value,*,require_value=False,allow_references=False):
        scope=self._command_scope
        if scope is None:
            return super().resolve_callable(value,require_value=require_value,allow_references=allow_references)
        self._check();scope.service(value,self.owner)
        self.app.check_host_service(value,self.owner)
        call=super().resolve_callable(value,require_value=require_value,allow_references=allow_references)
        def invoke(*args):
            self._check();self.app.check_host_service(value,self.owner)
            scope.service(value,self.owner);scope.values(args)
            result=call(*args);scope.values((result,));return result
        if allow_references:invoke.requires_reference=call.requires_reference
        return invoke

    def resolve_member(self,value,name):
        self._check()
        if self._command_scope is not None:
            from .python_direct_configuration_metadata import is_reader
            if is_reader(value):return self._command_scope.metadata.method(self,value,name)
        if self._command_scope is not None:
            binding=self._command_scope.module_bindings.get(id(value))
            if binding is None or binding[1] is not value:
                raise BoundaryViolation('unsupported configuration member receiver')
            module_name,side=binding[0]
        else:
            matches=[key for key,module in self.app._modules.items() if module is value]
            if not matches:raise BoundaryViolation('unsupported configuration member receiver')
            module_name,side=matches[0]
        if self.app.resolve_module(module_name,self.owner) is not value:
            raise BoundaryViolation('common module side changed')
        routine=value.routine(name);target=value.interpreter
        def admit():
            self._check();check_owner(self.app,target,allow_database=self._command_scope is not None)
            if self.app.resolve_module(module_name,self.owner) is not value:
                raise BoundaryViolation('common module binding changed')
            if self._command_scope is not None:self._command_scope.parameter_values(target,routine)
            self.app.check_call(routine,self.owner)
            if self._command_scope is not None:self._check()
            if any(not p.by_value for p in routine.parameters):
                raise BoundaryViolation('direct public common-module byref arguments are not connected')
            if routine.is_async or routine.is_dual:
                raise BoundaryViolation('direct common-module async/dual calls are not connected')
        admit()
        reuse_entry=self.app._reuse_routines.get(id(routine))
        reusable=(reuse_entry is not None and reuse_entry[0] is routine and routine.is_function)
        def invoke_arguments(args,omitted=()):
            admit()
            scope=self._command_scope
            if scope is not None:args=scope.arguments(target,routine,args,omitted)
            if len(args)!=len(routine.parameters):raise TypeError('common-module argument count mismatch')
            binding=target._invocation_bindings.get(routine.name.casefold())
            if binding is not None:
                if binding[0] is not routine:raise BoundaryViolation('invocation binding changed')
                try:return binding[1](list(args))
                finally:self._check()
            if side!=self.owner.execution_context:
                raise BoundaryViolation('direct common-module crossing requires explicit transport')
            scope=self._command_scope
            if scope is not None:scope.values(args)
            if reusable:
                result=invoke_reusable(self.app,self.owner,target,routine,args)
                self._check()
            else:result=invoke_routine(self.app,target,routine,args)
            if scope is not None:scope.values((result,))
            return result
        def invoke(*args):return invoke_arguments(args)
        def check_argument_count(count):
            self._check()
            entries=self._command_scope.parameter_values(target,routine)
            minimum=max((i+1 for i,entry in enumerate(entries) if entry[3] is None),default=0)
            if not minimum<=count<=len(entries):raise TypeError('common-module argument count mismatch')
        def with_omissions(omitted):
            self._check()
            self._command_scope.omissions(target,routine,omitted)
            def call(*args):return invoke_arguments(args,omitted)
            call.returns_value=routine.is_function
            call.check_argument_count=check_argument_count
            return call
        invoke.returns_value=routine.is_function
        if self._command_scope is not None:
            invoke.with_omissions=with_omissions
            invoke.check_argument_count=check_argument_count
        return invoke

    def resolve_configuration_member_call(self,value,name,*,require_value=False,omitted=(),argument_count):
        bound=self.resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        if self._command_scope is not None and hasattr(bound,'check_argument_count'):
            bound.check_argument_count(argument_count)
        return bound

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if self._command_scope is None:
            return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        bound=self.resolve_member(value,name)
        if self._command_scope is not None and require_value and not bound.returns_value:
            raise TypeError('Процедура не возвращает значение: '+name)
        if omitted:
            if not hasattr(bound,'with_omissions'):
                raise TypeError('metadata methods do not accept omitted arguments')
            return bound.with_omissions(omitted)
        return bound


def install(app,owner,program,source_text=''):
    check_owner(app,owner);app.check_program(program)
    if any(type(n) not in (ast.Routine,ast.Var) for n in program):
        raise BoundaryViolation('direct configured module requires declarations only')
    if any(type(n) is ast.Routine and (n.is_async or n.is_dual) for n in program):
        raise BoundaryViolation('direct configured async/dual routines are not connected')
    owned=_snapshot(program)
    plan=compile_owned(owned,source_text=source_text,source_name=program[0].token.source if program else '<configuration>',
        external_names=tuple(app._definitions),constructors=('uuid','уникальныйидентификатор'),
        exports=True,authority_checks=True,configuration_calls=True)
    # Capture original declaration bindings when this exact plan is installed.
    # Never infer a default from later host-mutated declaration metadata.
    plan._configuration_parameters=tuple((node,tuple(
        (parameter,parameter.name,parameter.by_value,parameter.default,
         parameter.default.value if type(parameter.default) is ast.Literal else None)
        for parameter in node.parameters)) for node in program if type(node) is ast.Routine)
    _PARAMETERS[plan.function]=(ref(plan),plan._configuration_parameters,
        {id(routine):(routine,entries) for routine,entries in plan._configuration_parameters})
    owner._direct_configuration_plan=plan
    for node in program:
        if type(node) is ast.Routine:
            (owner.server_routines if node.execution_context=='server' else owner.routines)[node.name.casefold()]=node
        elif type(node) is ast.Var:
            for name in node.names:owner.variables.setdefault(name.casefold(),None)
    owner._self_module.ready=True


def invoke_reusable(app,caller,owner,routine,arguments):
    """Lazy same-side scalar reuse; no transport or collection admission."""
    scope=_COMMAND_SCOPE.get()
    if scope is None:raise BoundaryViolation('reusable command scope is absent')
    from .python_direct_configuration_commands import _Scope
    if type(scope) is not _Scope:raise BoundaryViolation('invalid reusable command scope')
    scope.check(app,owner)
    scope.values(arguments)
    from decimal import Decimal
    if any(type(value) is Decimal and not value.is_finite() for value in arguments):
        raise TypeError('reusable arguments require finite numbers')
    entry=app._reuse_routines.get(id(routine))
    if entry is not None and entry[0] is routine and routine.is_function and entry[2].return_values_reuse=='DuringRequest':
        scope=_COMMAND_SCOPE.get()
        if scope is None:raise BoundaryViolation('reusable command scope is absent')
        scope.request_reuse()
    reusable=app.reusable_call(caller,owner,routine,True)
    if reusable is None:return invoke_routine(app,owner,routine,arguments)
    cache,key=reusable
    cache._open()
    wrappers=getattr(cache,'_direct_functions',None)
    if wrappers is None:wrappers={};cache._direct_functions=wrappers
    plan=owner._direct_configuration_plan
    entry=wrappers.get(key)
    if entry is None or entry[0] is not owner or entry[1] is not routine or entry[2] is not plan.function:
        from functools import lru_cache
        @lru_cache(maxsize=256,typed=True)
        def call(*args):
            result=invoke_routine(app,owner,routine,args)
            scope=_COMMAND_SCOPE.get()
            if scope is None:raise BoundaryViolation('reusable command scope is absent')
            scope.values((result,))
            return result
        entry=(owner,routine,plan.function,call)
        wrappers[key]=entry
    return entry[3](*arguments)


def invoke_routine(app,owner,routine,arguments):
    check_owner(app,owner,allow_database=_COMMAND_SCOPE.get() is not None);app.check_call(routine,owner)
    plan=getattr(owner,'_direct_configuration_plan',None)
    if plan is None:raise BoundaryViolation('unprepared direct configuration routine')
    registry=owner.server_routines if routine.execution_context=='server' else owner.routines
    if registry.get(routine.name.casefold()) is not routine:
        raise BoundaryViolation('direct configuration routine replaced')
    if len(arguments)!=len(routine.parameters):raise TypeError('configuration argument count mismatch')
    context=ConfigurationBoundary(app,owner,routine)
    previous=getattr(owner,'_transaction_activation_allowed',True)
    owner._transaction_activation_allowed=False
    owner._context_stack.append(routine.execution_context)
    owner._module_context_stack.append(True)
    try:
        with target_context(owner.native_target),localcontext():
            context.enter()
            try:
                try:
                    exports=plan.function(owner.variables,plan.constants,[],context)
                    return exports[routine.name.casefold()](*arguments)
                finally:context._check()
            except Exception as error:
                converted=convert_error(error,plan.source_name,plan.source_text)
                if converted is error:raise
                raise converted from None
            finally:context.leave()
    finally:
        owner._module_context_stack.pop();owner._context_stack.pop()
        owner._transaction_activation_allowed=previous


def invoke_event(app,routine,values):
    slots=[_Cell(obj.get_member(name)) for obj,name in values]
    try:return invoke_routine(app,app.interpreter,routine,slots)
    finally:
        for (obj,name),slot in zip(values,slots):obj.set_member(name,slot.value)
