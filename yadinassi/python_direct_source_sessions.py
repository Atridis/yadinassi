"""Finite actual-caller source session-parameter access, without VM dispatch."""
from weakref import ReferenceType
from .session_parameters import BSLSessionParameters,_DIRECT_SESSION_PARAMETERS_ABI
from .values import HostFunction
from .experimental_naked_boundaries import BoundaryViolation
from .python_direct_source_storage import finish
from . import source_transactions,safe_mode

_NAMES=('sessionparameters','параметрысеанса')


def owns(value):return type(value) is BSLSessionParameters


def check(boundary,value):
    boundary._check();app=boundary.app;caller=boundary.vm
    from .configuration_source_runtime import SourceApplication,_DIRECT_SOURCE_SESSION_INITIALIZER
    if (type(app) is not SourceApplication or 'initialize_session_parameters' in vars(app)
            or SourceApplication.initialize_session_parameters is not _DIRECT_SOURCE_SESSION_INITIALIZER):
        raise BoundaryViolation('source session initializer hook changed')
    if (not owns(value) or value is not app.session_parameters
            or type(value._application) is not ReferenceType or value._application() is not app
            or type(value._source_family) is not ReferenceType or value._source_family() is not app.interpreter
            or any(name in vars(value) or getattr(BSLSessionParameters,name) is not expected
                   for name,expected in _DIRECT_SESSION_PARAMETERS_ABI)):
        raise BoundaryViolation('foreign or noncanonical source session parameters')
    if (getattr(caller,'application',None) is not app or caller._family_owner is not app.interpreter
            or source_transactions._current.get() is not app or safe_mode._CURRENT.get() is not app.safe_mode):
        raise BoundaryViolation('source session parameter scope changed')
    # Preserve canonical wrong-side/closed-family messages, before any access.
    value._authorize(caller)


def namespace(boundary,name):
    if name not in _NAMES:return None
    value=boundary.app.session_parameters;check(boundary,value);return value


def get(boundary,value,name):
    check(boundary,value)
    try:return finish(BSLSessionParameters.read(value,boundary.vm,name))
    finally:check(boundary,value)


def set_member(boundary,value,name):
    check(boundary,value);value._key(name)
    def assign(new_value):
        check(boundary,value)
        try:return BSLSessionParameters.write(value,boundary.vm,name,new_value)
        finally:check(boundary,value)
    return assign


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False):
    check(boundary,value)
    if name not in ('__getitem__','__setitem__'):
        raise ValueError('source session parameter methods are not supported')
    expected=1 if name=='__getitem__' else 2
    if argument_count is not None and argument_count!=expected:
        raise TypeError('invalid session parameter index argument count')
    operation=(lambda key:get(boundary,value,key)) if expected==1 else (lambda key,new_value:set_member(boundary,value,key)(new_value))
    return boundary.resolve_callable(HostFunction(name,operation,returns_value=expected==1),
        require_value=require_value,allow_references=allow_references)
