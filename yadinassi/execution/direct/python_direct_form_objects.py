"""Exact current-form public model protocol, not arbitrary Python reflection."""
from yadinassi.forms.form_model import (BSLFormItems,BSLFormCommands,BSLFormField,BSLFormTable,
                         BSLFormGroup,BSLFormButton,BSLFormCommand,BSLFormAttribute,FORM_FIELD_VIEWS)
from yadinassi.forms.form_tables import BSLFormDataCollection,BSLFormDataCollectionItem
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction, _DIRECT_COLLECTION_CLASS_ABI
from yadinassi.types.type_descriptions import BSLTypeDescription
COLLECTIONS=(BSLFormItems,BSLFormCommands)
CONTROLS=(BSLFormField,BSLFormTable,BSLFormGroup,BSLFormButton,BSLFormCommand,BSLFormAttribute,FORM_FIELD_VIEWS)
KINDS=(BSLFormAttribute,BSLTypeDescription)+COLLECTIONS+CONTROLS+(BSLFormDataCollection,BSLFormDataCollectionItem)
_CONTROL_FIELDS = dict(_DIRECT_COLLECTION_CLASS_ABI[0][2])['__dict__']

def recognized(value):return type(value) in KINDS or value is FORM_FIELD_VIEWS

def require(session,value):
    if value is FORM_FIELD_VIEWS:
        session.form._check();return
    if type(value) is BSLFormAttribute:
        if value._session is not session:raise BoundaryViolation('foreign form attribute')
        value._check();return
    if type(value) is BSLTypeDescription:
        if not any(attribute.value_type is value for attribute in session.form._attributes.values()):
            raise BoundaryViolation('foreign form type descriptor')
        session.form._check();return
    if not recognized(value) or value._form is not session.form:
        raise BoundaryViolation('foreign direct form receiver')
    form=session.form
    if type(value) is BSLFormItems and value is not form.items:
        raise BoundaryViolation('retired form items')
    if type(value) is BSLFormCommands and value is not form.commands:
        raise BoundaryViolation('retired form commands')
    if type(value) in CONTROLS:
        registry=form.commands if type(value) is BSLFormCommand else form.items
        if registry._values.get(value.name.casefold()) is not value:
            # A model-retired control still belongs to this form. Its usual
            # deletion error is catchable, but it cannot resolve to a new
            # control with the same name. An unexplained mismatch stays fatal.
            fields = _CONTROL_FIELDS.__get__(value)
            if any(type(key) is str and key == '_removed' and marker is True
                   for key, marker in fields.items()):
                raise ValueError('Форма: объект удален')
            raise BoundaryViolation('retired form control')
    value._check()


def get(context,value,name):
    context._check();require(context.session,value)
    try:return value.get_member(name)
    finally:context._check()


def setter(context,value,name):
    context._check();require(context.session,value)
    def write(new):
        context._check();require(context.session,value)
        try:return value.set_member(name,new)
        finally:context._check()
    return write


def method(context,value,name):
    context._check();require(context.session,value)
    if name=='__iter__':
        if type(value) not in COLLECTIONS+(BSLFormDataCollection,):
            raise BoundaryViolation('unsupported form iteration')
        def iterate():
            context._check();require(context.session,value)
            for item in value:
                context._check();require(context.session,value)
                yield item
        return iterate
    if name=='__getitem__' and type(value) is BSLFormDataCollection:
        # Bind before the index expression; the shared invocation guard
        # rechecks this live collection before reading.
        function=value.get_index
    else:
        function=value.get_method(name)
        if type(function) is not HostFunction:raise BoundaryViolation('noncanonical form method')
    def invoke(*args):
        context._check();require(context.session,value)
        try:
            if type(value) is BSLFormDataCollection:
                from .python_direct_numbers import public_number
                return function(*(public_number(arg) for arg in args))
            return function(*args)
        finally:context._check()
    return invoke
