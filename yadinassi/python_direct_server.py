"""Synchronous logical server calls with fresh side-local state, no VM dispatch.

Only module-context Val signatures are admitted. NoContext, dual declarations,
server initializers and cross-side reference copyback remain explicit gaps.
"""
from decimal import Decimal
from .experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from .python_direct_database import CatalogBoundary
from .values import HostFunction, NULL


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


class ServerBoundary(CatalogBoundary,BoundaryContext):
    _server_side=True
    def __init__(self,parent):
        super().__init__()
        self.vm=parent.vm;self._services=self.vm.functions
        self.database=self.vm.database_context
        self._routine_exports={};self.state={}
    def _check(self):
        super()._check()
        from . import safe_mode,source_transactions,database_transactions
        vm=self.vm
        if (vm._family_closed or vm.database_context is not self.database
                or vm._configuration_runtime is not None or vm.locals is not None
                or not vm._has_module_context or vm.execution_context!='server'
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
    def execute(context,arguments):
        exports=context._routine_exports.get(id(module))
        if exports is None:
            for key in module.server_layout:context.state.setdefault(key,None)
            exports=module.server_plan.function(context.state,module.server_plan.constants,[],context)
            context._routine_exports[id(module)]=exports
        try:return exports[name](*arguments)
        except Exception as error:
            from .experimental_naked_errors import convert_error
            converted=convert_error(error,module.server_plan.source_name,module.server_plan.source_text)
            if converted is error:raise
            raise converted from None
    def invoke(*arguments):
        if getattr(parent,'_server_side',False):return execute(parent,arguments)
        parent._check()
        packet=transfer(list(arguments))
        context=ServerBoundary(parent)
        previous=getattr(vm,'_transaction_activation_allowed',True)
        vm._transaction_activation_allowed=False
        vm._context_stack.append('server')
        try:
            context.enter()
            try:
                try:return transfer(execute(context,packet))
                finally:context._check()
            finally:context.leave()
        finally:
            vm._context_stack.pop()
            vm._transaction_activation_allowed=previous
            parent._check()
    function=HostFunction(name,invoke,returns_value=module.signatures[name][0])
    return parent.resolve_callable(function,require_value=require_value,allow_references=allow_references)
