"""Finite standalone dynamic construction, after both source expressions run."""
from .values import (_DIRECT_COLLECTION_CLASS_ABI,
                     _DIRECT_DYNAMIC_TYPE_NAMES)
from .structures import _DIRECT_COLLECTION_CLASS_ABI as _STRUCTURE_ABI
from .maps import _DIRECT_COLLECTION_CLASS_ABI as _MAP_ABI
from .experimental_naked_boundaries import BoundaryViolation

BSLArray=_DIRECT_COLLECTION_CLASS_ABI[2][0]
HostFunction=_DIRECT_COLLECTION_CLASS_ABI[3][0]
BSLStructure=_STRUCTURE_ABI[1][0]
BSLMap=_MAP_ABI[1][0]

_MAX_ARGUMENTS=1024
_NATIVE={'array':BSLArray,'массив':BSLArray,
         'structure':BSLStructure,'структура':BSLStructure,
         'map':BSLMap,'соответствие':BSLMap}


def construct(context,target,parameters=None):
    # The compiler evaluates target and parameters left-to-right before entry.
    context._check()
    from .runtime import Interpreter
    vm=context.vm
    if type(vm) is not Interpreter or vm._configuration_runtime is not None:
        raise BoundaryViolation('dynamic construction requires a standalone direct boundary')
    if type(target) is str:name=target
    else:
        name=next((name for member,name in _DIRECT_DYNAMIC_TYPE_NAMES if target is member),None)
        if name is None:raise TypeError('Новый: ожидается имя типа или значение Тип')
    key=name.casefold()
    from .python_direct_services import CONSTRUCTORS
    from .python_direct_value_tree import CONSTRUCTOR_NAMES as TREE_NAMES
    if key not in _NATIVE and key not in CONSTRUCTORS and key not in TREE_NAMES and key not in ('uuid','уникальныйидентификатор'):
        raise ValueError('Тип не определен или не имеет direct конструктора: '+name)
    # No arbitrary iterable expansion, deep copying, or BSLFixedArray expansion.
    if type(parameters) is BSLArray:
        for cls,mro,fields in _DIRECT_COLLECTION_CLASS_ABI:
            current=vars(cls)
            slots=current.get('__slotnames__')
            if type(slots) is not list or slots:
                raise BoundaryViolation('dynamic constructor argument array slot cache changed')
            if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
                raise BoundaryViolation('dynamic constructor argument array hooks changed')
        parameters=object.__getattribute__(parameters,'items')
        if type(parameters) is not list:raise BoundaryViolation('dynamic constructor argument array storage changed')
    if type(parameters) is list:
        if len(parameters)>_MAX_ARGUMENTS:raise ValueError('Новый: превышен предел аргументов Yadinassi (1024)')
        arguments=tuple(parameters)
    else:arguments=()
    expected=_NATIVE.get(key)
    if expected is not None:
        factory=vm.types.get(key)
        if type(factory) is not HostFunction or factory.function is not expected:
            raise BoundaryViolation('dynamic native constructor requires canonical registration: '+key)
        try:
            if expected is BSLArray:
                from .experimental_naked_resources import bounded_array
                return bounded_array(*arguments)
            if expected is BSLStructure:
                from .experimental_naked_structure import new_structure
                return new_structure(*arguments)
            from .experimental_naked_collections import _TypedMap
            # Never expose dict(*foreign) iteration through a dynamic target.
            if arguments:raise TypeError('direct Map dynamic constructor currently requires no arguments')
            return _TypedMap()
        finally:context._check()
    # Preserve finite canonical factories and their current boundary/resource checks.
    bound=context.resolve_service('new:'+key)
    try:return bound(*arguments)
    finally:context._check()
