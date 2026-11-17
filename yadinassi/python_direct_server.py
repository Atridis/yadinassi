"""Synchronous logical server calls with fresh side-local state, no VM dispatch.

Module-context and NoContext calls support Val and named-variable copyback.
Dual declarations select a side-local NoContext plan.
"""
from decimal import Decimal
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .python_direct_database import CatalogBoundary
from .python_direct_services import ServicesBoundary
from .values import HostFunction, Reference, NULL
from .experimental_naked_collections import _Cell
from .experimental_naked_live_state import _ForwardReference


def transfer(value):
    """Copy the bounded direct Array/Structure envelope, preserving no aliases."""
    from .experimental_naked_structure import _DirectStructure
    from .runtime import Interpreter
    from .values import BSLArray
    from .structures import BSLStructure
    active=set();remaining=10000
    def copy(item,depth):
        nonlocal remaining
        remaining-=1
        if remaining<0 or depth>64:raise ValueError('Межконтекстная передача: превышен предел размера или глубины')
        if item is None or item is NULL or type(item) in (str,bool,Decimal):return item
        if type(item) not in (list,_DirectStructure,BSLArray,BSLStructure):
            return Interpreter._copy_context_packet([item])[0]
        if id(item) in active:raise ValueError('Межконтекстная передача циклических коллекций пока не поддерживается')
        active.add(id(item))
        try:
            if type(item) is list:return [copy(child,depth+1) for child in item]
            if type(item) is BSLArray:
                result=BSLArray();result.items=[copy(child,depth+1) for child in item.items]
                return result
            if type(item) is BSLStructure:
                result=BSLStructure()
                for key,(spelling,child) in item._items.items():result._items[key]=(spelling,copy(child,depth+1))
                return result
            result=_DirectStructure()
            for key,(spelling,child) in dict.items(item):dict.__setitem__(result,key,(spelling,copy(child,depth+1)))
            result._version=item._version
            return result
        finally:active.remove(id(item))
    return copy(value,0)


class ServerBoundary(ServicesBoundary,CatalogBoundary,BoundaryContext):
    _server_side=True
    def __init__(self,parent,*,module_context=True,side="server"):
        self._server_side=side=="server"
        self.side=side
        super().__init__()
        self.vm=parent.vm;self._services=self.vm.functions
        self.database=self.vm.database_context
        self._routine_exports={};self.state={}
        self.module_context=module_context
    def _check(self):
        super()._check()
        from . import safe_mode,source_transactions,database_transactions
        vm=self.vm
        if (vm._family_closed or vm.database_context is not self.database
                or vm._configuration_runtime is not None or vm.locals is not None
                or vm._has_module_context!=self.module_context or vm.execution_context!=self.side
                or safe_mode._CURRENT.get() is not None
                or source_transactions._current.get() is not None
                or database_transactions._execution.get() is not None):
            raise BoundaryViolation('direct server context changed at a host boundary')
    def resolve_service(self,name,*args,**kwargs):
        self._check()
        from .python_direct_routines import resolve
        routine=resolve(self,name.casefold(),require_value=kwargs.get('require_value',False),
            allow_references=kwargs.get('allow_references',False),argument_count=kwargs.get('argument_count'))
        if routine is not None:return routine
        return super().resolve_service(name,*args,**kwargs)


def resolve_server(parent,module,name,*,require_value,allow_references):
    vm=parent.vm
    references=module.signatures[name][3]
    module_context=name not in module.nocontext_names
    server_plan=module.server_plan if module_context else module.nocontext_plan
    if not getattr(parent,'module_context',True) and module_context:
        raise TypeError('Подпрограмма без контекста не может вызывать контекстную подпрограмму')
    def execute(context,arguments):
        exports=context._routine_exports.get(id(module))
        if exports is None:
            if module_context:
                for key in module.server_layout:context.state.setdefault(key,None)
            exports=server_plan.function(context.state,server_plan.constants,[],context)
            context._routine_exports[id(module)]=exports
        try:return exports[name](*arguments)
        except Exception as error:
            from .experimental_naked_errors import convert_error
            converted=convert_error(error,server_plan.source_name,server_plan.source_text)
            if converted is error:raise
            raise converted from None
    def invoke(*arguments):
        if getattr(parent,'_server_side',False):
            bound=tuple(_ForwardReference(value) if i in references and type(value) is Reference else value
                        for i,value in enumerate(arguments))
            if parent.module_context==module_context:return execute(parent,bound)
            # Contextual server -> NoContext is a same-side call: references stay
            # live, but globals and initializer capabilities do not follow it.
            context=ServerBoundary(parent,module_context=False)
            module_stack=vm._module_context_stack
            module_stack.append(False)
            try:
                context.enter()
                try:
                    try:return execute(context,bound)
                    finally:context._check()
                finally:context.leave()
            finally:
                module_stack.pop()
                parent._check()
        parent._check()
        outputs=[]
        for i,value in enumerate(arguments):
            if i in references:
                if type(value) is not Reference or getattr(value,'_direct_name_sink',False) is not True:
                    raise TypeError('Межконтекстные параметры без Знач пока требуют имя переменной')
                outputs.append((i,value))
        # Named byref actuals are storage: read only after all argument effects.
        packet=transfer([value.get() if i in references else value for i,value in enumerate(arguments)])
        for i,_ in outputs:packet[i]=_Cell(packet[i])
        context=ServerBoundary(parent,module_context=module_context)
        previous=getattr(vm,'_transaction_activation_allowed',True)
        vm._transaction_activation_allowed=False
        side_stack=vm._context_stack;module_stack=vm._module_context_stack
        side_stack.append('server');module_stack.append(module_context)
        try:
            context.enter()
            try:
                try:
                    for initializer in (getattr(vm,'_direct_server_initializers',()) if module_context else ()):
                        for key in initializer.server_layout:context.state.setdefault(key,None)
                        plan=initializer.initializer_plan
                        try:plan.function(context.state,plan.constants,[],context)
                        except Exception as error:
                            from .experimental_naked_errors import convert_error
                            converted=convert_error(error,plan.source_name,plan.source_text)
                            if converted is error:raise
                            raise converted from None
                        context._check()
                    result=execute(context,packet)
                    outgoing=transfer([result]+[packet[i].value for i,_ in outputs])
                finally:context._check()
            finally:context.leave()
        finally:
            module_stack.pop();side_stack.pop()
            vm._transaction_activation_allowed=previous
            parent._check()
        # Publish only after the complete packet and current caller validate.
        # Ordered independent copy-out intentionally gives the rightmost alias.
        for (_,reference),value in zip(outputs,outgoing[1:]):reference.set(value)
        return outgoing[0]
    function=HostFunction(name,invoke,reference_parameters=references,returns_value=module.signatures[name][0])
    return parent.resolve_callable(function,require_value=require_value,allow_references=allow_references)


def resolve_dual_client(parent,module,name,*,require_value,allow_references):
    vm=parent.vm
    references=module.signatures[name][3]
    def invoke(*arguments):
        parent._check()
        context=ServerBoundary(parent,module_context=False,side='client')
        stack=vm._module_context_stack
        stack.append(False)
        try:
            context.enter()
            try:
                exports=module.dual_plan.function({},module.dual_plan.constants,[],context)
                bound=tuple(_ForwardReference(value) if i in references and type(value) is Reference else value
                            for i,value in enumerate(arguments))
                try:
                    try:return exports[name](*bound)
                    except Exception as error:
                        from .experimental_naked_errors import convert_error
                        converted=convert_error(error,module.dual_plan.source_name,module.dual_plan.source_text)
                        if converted is error:raise
                        raise converted from None
                finally:context._check()
            finally:context.leave()
        finally:
            stack.pop()
            parent._check()
    function=HostFunction(name,invoke,reference_parameters=references,returns_value=module.signatures[name][0])
    return parent.resolve_callable(function,require_value=require_value,allow_references=allow_references)
