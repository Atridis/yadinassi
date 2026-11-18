"""Read-only scalar fields of an exact canonical diagnostic snapshot."""
from .error_info import _DIRECT_SNAPSHOT_ABI
from .experimental_naked_boundaries import BoundaryViolation
from decimal import Decimal

BSLErrorInfo,_STATE,_CATEGORIES,_EMPTY_CATEGORIES=_DIRECT_SNAPSHOT_ABI

_FIELDS={alias:field for field,aliases in (
    ('description',('description','описание')),
    ('code',('code','код')),
    ('additional_information',('additionalinformation','дополнительнаяинформация')),
    ('cause',('cause','причина')),
    ('module_name',('modulename','имямодуля')),
    ('line_number',('linenumber','номерстроки')),
    ('initial_string',('initialstring','исходнаястрока')),
) for alias in aliases}

def owns(value):return type(value) is BSLErrorInfo

def read(context,value,name):
    context._check()
    field=_FIELDS.get(name.casefold())
    if field is None:raise ValueError('Свойство не найдено: '+name)
    state=_STATE.__get__(value,BSLErrorInfo)
    result=dict.get(state,field)
    expected=int if field=='line_number' else str
    if field=='cause':
        if result is not None and type(result) is not BSLErrorInfo:
            raise BoundaryViolation('invalid canonical error cause')
    elif type(result) is not expected or (field=='line_number' and result<0):
        raise BoundaryViolation('invalid canonical error field')
    return Decimal(result) if field=='line_number' else result


def snapshot(description='',*,module_name='',line_number=0,initial_string='',empty=False):
    if (type(description) is not str or type(module_name) is not str or
            type(line_number) is not int or line_number<0 or type(initial_string) is not str):
        raise BoundaryViolation('invalid direct diagnostic fields')
    value=object.__new__(BSLErrorInfo)
    state=_STATE.__get__(value,BSLErrorInfo)
    dict.update(state,description=description,code='',additional_information='',cause=None,
        categories=_EMPTY_CATEGORIES if empty else _CATEGORIES,module_name=module_name,
        line_number=line_number,initial_string=initial_string,_empty=empty)
    return value
