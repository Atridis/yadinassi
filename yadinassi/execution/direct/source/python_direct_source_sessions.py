"""Finite actual-caller source session-parameter access, without VM dispatch."""
from weakref import ReferenceType
from uuid import UUID
from yadinassi.application.session_parameters import BSLSessionParameters,_DIRECT_SESSION_PARAMETERS_ABI
from yadinassi.execution.direct.python_direct_numbers import public_number
from yadinassi.configuration.configuration_source_metadata import SourceMetadataObject, SourceMetadata
from yadinassi.configuration.configuration_session_parameters import SessionParameterDefinition
from yadinassi.configuration.metadata import _scalar_description
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from .python_direct_source_storage import finish
from yadinassi.db import source_transactions
from yadinassi.execution import safe_mode

_NAMES=('sessionparameters','параметрысеанса')
_SCALAR_QUALIFIERS={'boolean':(), 'string':(int,), 'number':(int,int,str), 'datetime':(str,)}


def owns(value):return type(value) is BSLSessionParameters


def check(boundary,value):
    boundary._check();app=boundary.app;caller=boundary.vm
    from yadinassi.configuration.configuration_source_runtime import SourceApplication,_DIRECT_SOURCE_SESSION_INITIALIZER
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


def metadata_type(boundary, value):
    """Read the selected declared scalar, never the live session namespace."""
    if type(value) is not SourceMetadataObject:
        return None
    entry=value._entry
    if (type(entry) is not SourceMetadata or type(entry.family) is not str
            or entry.family!='SessionParameter'):
        return None
    root=boundary.app.metadata
    if (value._root is not root or type(entry.path) is not str or type(entry.name) is not str
            or type(root._objects) is not dict or type(root._inventory) is not dict
            or root._objects.get(entry.path) is not value
            or root._inventory.get(entry.path) is not entry or value._name is not entry.name):
        raise BoundaryViolation('source session metadata owner changed')
    store=boundary.app.session_parameters
    if (type(store) is not BSLSessionParameters
            or type(store._application) is not ReferenceType or store._application() is not boundary.app
            or type(store._definitions) is not dict):
        raise BoundaryViolation('source session metadata declarations changed')
    definition=store._definitions.get(entry.name.casefold())
    if definition is None:
        raise ValueError('unsupported source session metadata type')
    if (type(definition) is not SessionParameterDefinition or type(definition.name) is not str
            or definition.name!=entry.name or type(entry.identity) is not UUID
            or type(definition.identity) is not UUID or type(definition.identity.int) is not int
            or type(entry.identity.int) is not int or definition.identity.int!=entry.identity.int
            or type(definition.kind) is not str or type(definition.qualifiers) is not tuple):
        raise BoundaryViolation('source session metadata declaration changed')
    kind,qualifiers=definition.kind,definition.qualifiers
    expected=_SCALAR_QUALIFIERS.get(kind)
    if expected is None:
        raise ValueError('unsupported source session metadata type')
    if (len(qualifiers)!=len(expected)
            or any(type(field) is not scalar for field,scalar in zip(qualifiers,expected))):
        raise BoundaryViolation('source session metadata qualifiers changed')
    return _scalar_description(kind,qualifiers)


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
        try:return BSLSessionParameters.write(value,boundary.vm,name,public_number(new_value))
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
