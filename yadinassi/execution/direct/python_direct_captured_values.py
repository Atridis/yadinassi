"""Private provenance for compiler-created closure method values.

Public HostFunction construction never registers a capability. Receiver-owned
methods use their existing finite boundary adapters before this final fallback.
No ordinary native operation or named service consults this weak registry.
"""
from types import FunctionType, MethodType
from weakref import ref
from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI
HostFunction=_DIRECT_COLLECTION_CLASS_ABI[3][0]
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_RECORDS={}


def _implementation(callback):
    if type(callback) is MethodType:return callback.__func__
    if type(callback) is FunctionType:return callback
    return type(callback).__call__


def _abi(function):
    if type(function) is not FunctionType:return None
    return (function.__code__,id(function.__defaults__),id(function.__kwdefaults__),
            tuple(id(cell.cell_contents) for cell in function.__closure__ or ()))


def register(value):
    """Private factory hook, not an extension API or a public wrapper flag."""
    if type(value) is not HostFunction:raise TypeError('canonical method wrapper required')
    identity=id(value);callback=value.function;implementation=_implementation(callback)
    def expired(reference):
        current=_RECORDS.get(identity)
        if current is not None and current[0] is reference:del _RECORDS[identity]
    _RECORDS[identity]=(ref(value,expired),ref(callback),value.name,value.reference_parameters,
                        value.returns_value,ref(implementation) if type(implementation) is FunctionType else implementation,_abi(implementation))
    return value


def resolve(context,value,*,require_value=False,allow_references=False):
    if type(value) is not HostFunction:return None
    record=_RECORDS.get(id(value))
    if record is None or record[0]() is not value:return None
    _,callback_ref,name,references,returns,implementation_ref,abi=record
    callback=callback_ref()
    if callback is None:raise BoundaryViolation('captured runtime method expired')
    implementation=implementation_ref() if abi is not None else implementation_ref
    def validate():
        context._check()
        if (value.function is not callback or value.name is not name
                or value.reference_parameters is not references or value.returns_value is not returns
                or _implementation(callback) is not implementation):
            raise BoundaryViolation('captured runtime method changed')
        if abi is not None:
            current=_abi(implementation)
            if (current[0] is not abi[0] or current[1:3]!=abi[1:3]
                    or len(current[3])!=len(abi[3])
                    or current[3]!=abi[3]):
                raise BoundaryViolation('captured runtime implementation changed')
    validate();context._validate_host_function(value,require_value,allow_references)
    def invoke(*args):
        validate();context._before('call_value',name.casefold());validate()
        try:return callback(*args)
        finally:context._check()
    if allow_references:invoke.requires_reference=lambda index:index in references
    return invoke
