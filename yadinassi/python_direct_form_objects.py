"""Exact current-form public model protocol, not arbitrary Python reflection."""
from .form_model import (BSLFormItems,BSLFormCommands,BSLFormField,BSLFormTable,
                         BSLFormGroup,BSLFormButton,BSLFormCommand,BSLFormAttribute,FORM_FIELD_VIEWS)
from .form_tables import BSLFormDataCollection,BSLFormDataCollectionItem
from .experimental_naked_boundaries import BoundaryViolation
from .values import HostFunction
from .type_descriptions import BSLTypeDescription
COLLECTIONS=(BSLFormItems,BSLFormCommands)
CONTROLS=(BSLFormField,BSLFormTable,BSLFormGroup,BSLFormButton,BSLFormCommand,BSLFormAttribute,FORM_FIELD_VIEWS)
KINDS=(BSLFormAttribute,BSLTypeDescription)+COLLECTIONS+CONTROLS+(BSLFormDataCollection,BSLFormDataCollectionItem)

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
    function=value.get_method(name)
    if type(function) is not HostFunction:raise BoundaryViolation('noncanonical form method')
    def invoke(*args):
        context._check();require(context.session,value)
        try:return function(*args)
        finally:context._check()
    return invoke
