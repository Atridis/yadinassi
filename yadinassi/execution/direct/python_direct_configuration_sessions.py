"""Direct session state on admitted server activations, without a new call route."""
from types import MethodType

from yadinassi.application.session_parameters import BSLSessionParameters, _DIRECT_SESSION_PARAMETERS_ABI
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Cell
from yadinassi.runtime import Interpreter, _DIRECT_CONFIGURATION_MESSAGE_ABI
from yadinassi.syntax import ast
from yadinassi.types.values import BSLArray, HostFunction
from .python_direct_configuration import (
    ConfigurationBoundary, _COMMAND_SCOPE, check_owner, invoke_routine, parameter_entries,
)

NAMES=('sessionparameters','параметрысеанса')
_WRITE=BSLSessionParameters.write
_READ=BSLSessionParameters.read


def initialize(app,names=None):
    binding=app._session_binding
    if type(binding) is not tuple or len(binding)!=3:
        raise BoundaryViolation('configuration session initializer binding changed')
    owner,routine,plan=binding
    if (type(owner) is not Interpreter or owner is not app._session_owner
            or type(routine) is not ast.Routine or routine is not app._session_handler
            or routine.execution_context!='server' or routine.is_function or routine.is_async
            or routine.is_dual or not routine.module_context or owner._direct_configuration_plan is not plan):
        raise BoundaryViolation('configuration session initializer binding changed')
    entries=parameter_entries(plan,routine)
    if len(entries)!=1 or len(routine.parameters)!=1:
        raise BoundaryViolation('configuration session initializer parameter changed')
    parameter,name,by_value,default,_=entries[0]
    if (routine.parameters[0] is not parameter or parameter.name is not name
            or by_value is not False or parameter.by_value is not False
            or default is not None or parameter.default is not None):
        raise BoundaryViolation('configuration session initializer parameter changed')
    invoke_routine(app,owner,routine,(_Cell(names),))


def initialize_lazy(app,names):
    # The shared reader supplies a fresh one-name array while that name is
    # being initialized. Startup's Undefined request is never a lazy request.
    store=app.session_parameters
    items=names.items if type(names) is BSLArray else None
    if (type(items) is not list or len(items)!=1
            or type(items[0]) is not str or items[0].casefold() not in store._initializing):
        raise BoundaryViolation('invalid lazy session parameter request')
    if app._session_binding is not None:
        initialize(app,items.copy())

def _read(store,owner,name):
    iterator=_READ(store,owner,name)
    try:
        next(iterator)
    except StopIteration as result:
        return result.value
    iterator.close()
    raise BoundaryViolation('session initialization must not suspend')


class _SessionAccess:
    def _check_store(self):
        if (type(self.store) is not BSLSessionParameters or self.store is not self.app.session_parameters
                or any(name in vars(self.store) or getattr(BSLSessionParameters,name) is not method
                       for name,method in _DIRECT_SESSION_PARAMETERS_ABI)):
            raise BoundaryViolation('configuration session store changed')

    def external_get(self,name):
        if name.casefold() in NAMES:
            self._session_access()
            return self.store
        return super().external_get(name)

    def get_member(self,value,name):
        if value is not self.store:return super().get_member(value,name)
        self._session_access()
        return _read(value,self.owner,name)

    def resolve_set_member(self,value,name):
        if value is not self.store:return super().resolve_set_member(value,name)
        self._session_access()
        value._key(name)
        def write(new):
            self._session_access()
            return _WRITE(value,self.owner,name,new)
        return write

    def resolve_member(self,value,name):
        if value is self.store:
            if name=='__getitem__':return lambda key:self.get_member(value,key)
            if name=='__setitem__':return lambda key,new:self.resolve_set_member(value,key)(new)
        return super().resolve_member(value,name)


class SessionServer(_SessionAccess,ConfigurationBoundary):
    def __init__(self,app,owner,routine):
        super().__init__(app,owner,routine)
        self.store=app.session_parameters

    def _session_access(self):
        self._check()
        self._check_store()


class SessionStartup(_SessionAccess,BoundaryContext):
    def __init__(self,app,owner,routine):
        message=HostFunction('Message',MethodType(_DIRECT_CONFIGURATION_MESSAGE_ABI,owner),returns_value=False)
        super().__init__(services={'message':message,'сообщить':message})
        self.app,self.owner,self.routine=app,owner,routine
        self.binding,self.store=app._session_binding,app.session_parameters
        self.state=app.state

    def _check(self):
        super()._check()
        app,owner=self.app,self.owner
        if (_COMMAND_SCOPE.get() is not None or self.state not in ('starting','running')
                or app.state!=self.state or owner.execution_context!='server'
                or app._session_binding is not self.binding or app._session_owner is not owner
                or app._session_handler is not self.routine or owner._direct_configuration_plan is not self.binding[2]
                or owner.server_routines.get(self.routine.name.casefold()) is not self.routine):
            raise BoundaryViolation('configuration session initializer scope changed')
        check_owner(app,owner,allow_database=app._client_sqlite is not None)
        self._check_store()

    def _session_access(self):
        # The initializer is generated direct code with only the existing
        # Message effect. Its entry/exit and Message already check the owner.
        pass

    def resolve_service(self,name,_fallback=None,**kwargs):
        if name.casefold() not in self._services:
            raise BoundaryViolation('unsupported session initializer host service: '+name)
        return super().resolve_service(name,**kwargs)

    def resolve_callable(self,*args,**kwargs):
        raise BoundaryViolation('session initializer does not accept captured host callables')
