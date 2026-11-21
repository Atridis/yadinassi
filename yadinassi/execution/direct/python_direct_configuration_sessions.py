"""Direct startup-only session parameters in the existing server activation."""
from types import MethodType

from yadinassi.application.session_parameters import BSLSessionParameters, _DIRECT_SESSION_PARAMETERS_ABI, _UNSET
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Cell
from yadinassi.runtime import Interpreter, _DIRECT_CONFIGURATION_MESSAGE_ABI
from yadinassi.syntax import ast
from yadinassi.types.values import HostFunction
from .python_direct_configuration import _COMMAND_SCOPE, check_owner, invoke_routine, parameter_entries

NAMES=('sessionparameters','параметрысеанса')
_WRITE=BSLSessionParameters.write


def start(app):
    owner,routine,plan=app._session_binding
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
    invoke_routine(app,owner,routine,(_Cell(None),))


class SessionStartup(BoundaryContext):
    def __init__(self,app,owner,routine):
        message=HostFunction('Message',MethodType(_DIRECT_CONFIGURATION_MESSAGE_ABI,owner),returns_value=False)
        super().__init__(services={'message':message,'сообщить':message})
        self.app,self.owner,self.routine=app,owner,routine
        self.binding,self.store=app._session_binding,app.session_parameters

    def _check(self):
        super()._check()
        app,owner=self.app,self.owner
        if (_COMMAND_SCOPE.get() is not None or app.state!='starting' or owner.execution_context!='server'
                or app._session_binding is not self.binding or app._session_owner is not owner
                or app._session_handler is not self.routine or owner._direct_configuration_plan is not self.binding[2]
                or owner.server_routines.get(self.routine.name.casefold()) is not self.routine):
            raise BoundaryViolation('configuration session initializer scope changed')
        check_owner(app,owner,allow_database=app._client_sqlite is not None)
        if (type(self.store) is not BSLSessionParameters or self.store is not app.session_parameters
                or any(name in vars(self.store) or getattr(BSLSessionParameters,name) is not method
                       for name,method in _DIRECT_SESSION_PARAMETERS_ABI)):
            raise BoundaryViolation('configuration session store changed')

    def resolve_service(self,name,_fallback=None,**kwargs):
        if name.casefold() not in self._services:
            raise BoundaryViolation('unsupported session initializer host service: '+name)
        return super().resolve_service(name,**kwargs)

    def resolve_callable(self,*args,**kwargs):
        raise BoundaryViolation('session initializer does not accept captured host callables')

    def external_get(self,name):
        if name.casefold() in NAMES:return self.store
        return super().external_get(name)

    def get_member(self,value,name):
        if value is not self.store:return super().get_member(value,name)
        value._authorize(self.owner)
        result=value._values[value._key(name)]
        if result is _UNSET:raise ValueError('session parameter value is not set')
        return result

    def resolve_set_member(self,value,name):
        if value is not self.store:return super().resolve_set_member(value,name)
        value._key(name)
        return lambda new:_WRITE(value,self.owner,name,new)

    def resolve_member(self,value,name):
        if value is self.store:
            if name=='__getitem__':return lambda key:self.get_member(value,key)
            if name=='__setitem__':return lambda key,new:self.resolve_set_member(value,key)(new)
        return super().resolve_member(value,name)
