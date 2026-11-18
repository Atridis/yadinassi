"""Prepared declaration factories for direct synchronous form/event procedures.

This is code and signature metadata, NOT a grant to a form, database or side.
The owning host supplies current storage, a fresh boundary context and an
invocation scope. No interpreter AST-dispatch path is imported or executed.
"""
from contextlib import nullcontext
from dataclasses import dataclass
from types import MappingProxyType
from .syntax import ast
from .python_direct import REPAIRS, _snapshot
from .experimental_naked_collections import _Cell
from .experimental_direct_ast import compile_owned
from .experimental_naked_errors import convert_error
from .experimental_naked_live_state import validate_state


@dataclass(frozen=True, slots=True)
class HandlerDescriptor:
    name: str
    side: str
    by_value: tuple
    is_function: bool


@dataclass(frozen=True, slots=True)
class PreparedHandlers:
    _plans: object
    descriptors: object
    source_text: str
    source_name: str

    def bind(self,name,side,arity,*,allow_functions=False):
        if type(name) is not str or side not in ('client','server'):
            raise ValueError('unsupported direct handler identity')
        descriptor=self.descriptors.get((side,name.casefold()))
        if descriptor is None or (descriptor.is_function and not allow_functions) or len(descriptor.by_value)!=arity:
            raise ValueError('Форма: обработчик отсутствует или имеет неподдерживаемую сигнатуру')
        return descriptor

    def invoke(self,name,side,arguments,*,state,context_factory,execution_scope=nullcontext):
        descriptor=self.bind(name,side,len(arguments))
        _,updated=self._execute(descriptor,arguments,state=state,context_factory=context_factory,execution_scope=execution_scope)
        return updated

    def invoke_export(self,name,side,arguments,*,is_function,state,context_factory,execution_scope=nullcontext):
        descriptor=self.bind(name,side,len(arguments),allow_functions=True)
        if descriptor.is_function is not is_function or not all(descriptor.by_value):
            raise ValueError('direct RPC requires matching required Val signature')
        result,_=self._execute(descriptor,arguments,state=state,context_factory=context_factory,execution_scope=execution_scope)
        return result

    def _execute(self,descriptor,arguments,*,state,context_factory,execution_scope):
        # A new context and closure family belong to this invocation only. The
        # caller's scope performs lifecycle/side/budget setup before any factory
        # initialization or source handler effects.
        slots=[value if by_value else _Cell(value)
               for value,by_value in zip(arguments,descriptor.by_value)]
        plan=self._plans[descriptor.side]
        with execution_scope():
            validate_state(state)
            context=context_factory()
            context.enter()
            try:
                try:
                    # Do not use Program.run: it would leave the boundary before
                    # the returned generated function has actually executed.
                    exports=plan.function(state,plan.constants,[],context)
                    result=exports[descriptor.name](*slots)
                finally:context._check()
            except Exception as error:
                converted=convert_error(error,self.source_name,self.source_text)
                if converted is error:raise
                raise converted from None
            finally:context.leave()
        return result,[slot if by_value else slot.value
                for slot,by_value in zip(slots,descriptor.by_value)]


def prepare_handlers(program,*,source_text,source_name='<direct-form>',module_names=(),external_names=(),constructors=(),repairs=REPAIRS,_source_routine_scopes=False):
    """Prepare an already-admitted form module; never infer host capabilities.

    Only same-side routines share a generated closure family. A cross-side call
    must resolve through an explicit service supplied by the owning runtime.
    """
    if type(_source_routine_scopes) is not bool:raise TypeError('source routine scopes require Boolean')
    if type(program) is not list or any(type(node) not in (ast.Routine,ast.Var) for node in program):
        raise ValueError('direct handlers require a declaration-only AST list')
    owned=_snapshot(program)
    descriptors={}
    for node in owned:
        if type(node) is not ast.Routine:continue
        if node.is_async or node.is_dual or not node.module_context or node.execution_context not in ('client','server'):
            raise ValueError('direct handlers require synchronous module-context routines')
        key=(node.execution_context,node.name.casefold())
        if key in descriptors:raise ValueError('duplicate direct handler')
        descriptors[key]=HandlerDescriptor(key[1],key[0],tuple(p.by_value for p in node.parameters),node.is_function)
    plans={}
    for side in ('client','server'):
        if not any(key[0]==side for key in descriptors):continue
        selected=[node for node in owned if node.execution_context==side]
        plans[side]=compile_owned(selected,source_text=source_text,source_name=source_name,
            module_names=module_names,external_names=external_names,constructors=constructors,
            exports=True,source_scopes=_source_routine_scopes,
            authority_checks='authority_checkpoints' in repairs)
    return PreparedHandlers(MappingProxyType(plans),MappingProxyType(descriptors),source_text,source_name)
