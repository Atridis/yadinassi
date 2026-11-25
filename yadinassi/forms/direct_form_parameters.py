"""Exact scalar-structure bridges at form input/result boundaries only."""
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


def structure_items(value):
    """Return exact supported Structure fields, or None; never duck-type maps."""
    kind=type(value)
    if kind is BSLStructure or kind is BSLFixedStructure:
        return tuple(value._items.values())
    from yadinassi.execution.codegen.direct_structure import _DirectStructure
    if kind is _DirectStructure:
        # Native backing entries retain original spelling and scalar value.
        return tuple(dict.values(value))
    return None


def is_parameters(session,value):
    return type(value) is BSLFixedStructure and value is getattr(session,'_parameters',None)


def _require(session,value):
    if not is_parameters(session,value):
        raise BoundaryViolation('unregistered or replaced form parameters')
    session.form._check()


def get_parameter(session,value,name):
    _require(session,value)
    return value.get_member(name)


def bind_parameter_method(session,value,name):
    _require(session,value)
    key=name.casefold()
    if key not in ('property','свойство','count','количество'):
        raise ValueError('Метод структуры не найден: '+name)
    method=value.get_method(name)
    def invoke(*args):
        _require(session,value)
        expected=1 if key in ('property','свойство') else 0
        if len(args)!=expected:
            raise TypeError('form Parameters method requires '+str(expected)+' arguments; Property output reference is unsupported')
        return method(*args)
    return invoke


def bind_parameter_write(session,value,name):
    _require(session,value)
    def write(new_value):
        _require(session,value)
        # The existing immutable Structure setter provides its exact diagnostic.
        value.set_member(name,new_value)
    return write
