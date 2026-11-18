"""Narrow direct declaration execution for configured startup/common modules.

Metadata owners and existing module/transport gates remain authoritative. No AST
execution, scheduler dispatcher, arbitrary host reflection or implicit fallback.
"""
from decimal import localcontext
from contextvars import ContextVar

_COMMAND_SCOPE = ContextVar("direct_configuration_command", default=None)
from . import safe_mode, source_transactions, database_transactions
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .experimental_naked_collections import prepare, _Cell
from .experimental_naked_errors import convert_error
from .python_direct import REPAIRS, _snapshot
from .native_targets import target_context
from .syntax import ast
from .values import HostFunction


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
        matches=[key for key,module in self.app._modules.items() if module is value]
        if not matches:raise BoundaryViolation('unsupported configuration member receiver')
        module_name,side=matches[0]
        if self.app.resolve_module(module_name,self.owner) is not value:
            raise BoundaryViolation('common module side changed')
        routine=value.routine(name);target=value.interpreter
        def admit():
            self._check();check_owner(self.app,target)
            if self.app.resolve_module(module_name,self.owner) is not value:
                raise BoundaryViolation('common module binding changed')
            self.app.check_call(routine,self.owner)
            if any(not p.by_value for p in routine.parameters):
                raise BoundaryViolation('direct public common-module byref arguments are not connected')
            if routine.is_async or routine.is_dual:
                raise BoundaryViolation('direct common-module async/dual calls are not connected')
        admit()
        def invoke(*args):
            admit()
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
            result=invoke_routine(self.app,target,routine,args)
            if scope is not None:scope.values((result,))
            return result
        invoke.returns_value=routine.is_function
        return invoke

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if self._command_scope is None:
            return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        bound=self.resolve_member(value,name)
        if self._command_scope is not None and require_value and not bound.returns_value:
            raise TypeError('Процедура не возвращает значение: '+name)
        return bound


def install(app,owner,program,source_text=''):
    check_owner(app,owner);app.check_program(program)
    if any(type(n) not in (ast.Routine,ast.Var) for n in program):
        raise BoundaryViolation('direct configured module requires declarations only')
    if any(type(n) is ast.Routine and (n.is_async or n.is_dual) for n in program):
        raise BoundaryViolation('direct configured async/dual routines are not connected')
    owned=_snapshot(program)
    plan=prepare(source_text,source_name=program[0].token.source if program else '<configuration>',
        parsed_ast=owned,repairs=REPAIRS+('authority_checkpoints',),external_names=tuple(app._definitions),
        _trusted_entry=True,_export_routines=True)
    owner._direct_configuration_plan=plan
    for node in program:
        if type(node) is ast.Routine:
            (owner.server_routines if node.execution_context=='server' else owner.routines)[node.name.casefold()]=node
        elif type(node) is ast.Var:
            for name in node.names:owner.variables.setdefault(name.casefold(),None)
    owner._self_module.ready=True


def invoke_routine(app,owner,routine,arguments):
    check_owner(app,owner);app.check_call(routine,owner)
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
