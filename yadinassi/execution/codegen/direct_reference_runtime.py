"""Live BSL ByRef addresses and lending at host boundaries."""
from decimal import Decimal
from functools import partial

from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.execution.direct.python_direct_plain_map import PlainMap
from yadinassi.types.values import BSLArray, BSLFixedArray, BSLObject, Reference
from .direct_access_runtime import get_field, owned_index, read_bracket
from .direct_array_address import ArrayElementAddress
from .direct_boundaries import BoundaryViolation
from .direct_collections import _Cell, _Reference
from .direct_live_state import UNSET, _SlotReference, _ForwardReference
from .direct_structure import _DirectStructure


class Address(_Reference):
    __slots__ = ('read', 'write', 'name_sink')

    def __init__(self, read, write, *, name_sink=False):
        self.read = read
        self.write = write
        self.name_sink = name_sink

    @property
    def value(self):
        return self.read()

    @value.setter
    def value(self, value):
        self.write(value)


_BOX_DICT = vars(BSLObject)['__dict__']


_BOX_ARRAY_SET = BSLArray.set


_BOX_STRUCTURE_SET = BSLStructure.set


def boxed_storage(context, receiver, attribute, expected_type):
    context._check_effect()
    state = _BOX_DICT.__get__(receiver, type(receiver))
    if any(type(key) is not str for key in state):
        raise BoundaryViolation('canonical reference storage changed')
    backing = state.get(attribute)
    if type(backing) is not expected_type:
        raise BoundaryViolation('canonical reference storage changed')
    return backing


def boxed_array_reference(context, receiver, key):
    readonly = type(receiver) is BSLFixedArray
    storage_type = tuple if readonly else list
    items = boxed_storage(context, receiver, 'items', storage_type)
    if type(key) is Decimal:
        if not key.is_finite() or key != key.to_integral_value():
            raise ValueError('Ожидается целое число')
    elif type(key) is not int:
        raise TypeError('Ожидается число')
    if not 0 <= key < len(items):
        raise IndexError(f'Индекс массива вне границ: {key}')
    offset = int(key)

    def live():
        if boxed_storage(context, receiver, 'items', storage_type) is not items:
            raise BoundaryViolation('canonical reference backing changed')
        if offset >= len(items):
            raise IndexError(f'Индекс массива вне границ: {offset}')

    def get():
        live()
        return items[offset]

    def set_value(value):
        live()
        if readonly:
            raise ValueError('Фиксированный массив недоступен для записи')
        if vars(BSLArray).get('set') is not _BOX_ARRAY_SET:
            raise BoundaryViolation('canonical array setter changed')
        items[offset] = value
        live()

    return Address(get, set_value)


def bind_local_index_reference(context, receiver):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        return partial(ArrayElementAddress,receiver)
    if (kind is BSLArray or kind is BSLFixedArray) and context.policy is None:
        return partial(boxed_array_reference, context, receiver)
    return bind_index_reference(context, receiver)


def bind_index_reference(context, receiver):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        return partial(ArrayElementAddress,receiver)
    if kind is not PlainMap and kind is not _DirectStructure:
        return context.bind_reference_index(receiver)
    def bind_index(key):
        def get():
            return receiver.get(key) if kind is PlainMap else receiver[key]
        def set_value(value):
            receiver[key] = value
        get()
        return Address(get,set_value)
    return bind_index


def fragment_reference(read,write):
    try:
        read()
    except NameError:
        return None
    return Reference(read,write)


def host_reference(address, context=None):
    kind=type(address)
    read,write=address.get,address.set
    forwarded_name=(kind is _ForwardReference and type(address.reference) is Reference
                    and getattr(address.reference,'_direct_name_sink',False) is True)
    # BSL name addresses have their own lending checks when an imported or dual
    # routine uses them. Rechecking the suspended caller would reject the lend.
    if (kind is _ForwardReference and not forwarded_name
            and context is not None and context._verify_context):
        def guarded_get():
            context._check_effect()
            try:
                return read()
            finally:
                context._check_effect()

        def guarded_set(value):
            context._check_effect()
            try:
                write(value)
            finally:
                context._check_effect()

        result=Reference(guarded_get,guarded_set)
    else:
        result=Reference(read,write)
    result._direct_name_sink=(kind is _SlotReference
        or kind is Address and address.name_sink
        or forwarded_name)
    return result


def indexed_actual(context, byref, receiver, owned):
    if byref:
        address=bind_index_reference(context,receiver)
        return lambda key: host_reference(address(key))
    if owned:
        return owned_index(context,receiver)
    return partial(read_bracket,context,receiver)


def member_actual(context, byref, receiver, key):
    if byref:
        address=field_reference(context,receiver,key)
        # A module reference was already bound by its owner. Preserve the exact
        # reference so a synchronous dual call can lend that one address.
        if type(address) is _ForwardReference:
            return address.reference
        return host_reference(address)
    return get_field(context,receiver,key)


def cell_actual(value):
    return host_reference(_Cell(value))


def lexical_reference(get, set_value):
    if get() is UNSET:raise NameError("Uninitialized reference")
    return Address(get,set_value,name_sink=True)


def boxed_field_reference(context, receiver, name):
    from yadinassi.collections.structures import _key
    key = _key(name)
    items = boxed_storage(context, receiver, '_items', dict)

    def selected():
        if boxed_storage(context, receiver, '_items', dict) is not items:
            raise BoundaryViolation('canonical reference backing changed')
        if any(type(field) is not str for field in items):
            raise BoundaryViolation('canonical reference storage changed')
        if key not in items:
            raise ValueError(f'Свойство структуры не найдено: {name}')
        entry = items[key]
        if type(entry) is not tuple or len(entry) != 2 or type(entry[0]) is not str:
            raise BoundaryViolation('canonical reference storage changed')
        return entry

    def get():
        return selected()[1]

    def set_value(value):
        if type(receiver) is BSLFixedStructure:
            raise ValueError(f'Свойство фиксированной структуры недоступно для записи: {name}')
        if vars(BSLStructure).get('set') is not _BOX_STRUCTURE_SET:
            raise BoundaryViolation('canonical structure setter changed')
        items[key] = (selected()[0], value)
        context._check_effect()

    selected()
    return Address(get, set_value)


def local_field_reference(context, receiver, key):
    kind=type(receiver)
    if (kind is BSLStructure or kind is BSLFixedStructure) and context.policy is None:
        return boxed_field_reference(context, receiver, key)
    return field_reference(context, receiver, key)


def field_reference(context, receiver, key):
    if type(receiver) is _DirectStructure:
        receiver[key]
        return Address(lambda: receiver[key],lambda value: receiver.__setitem__(key,value))
    reference=context.reference_member(receiver,key)
    return _ForwardReference(reference) if type(reference) is Reference else reference
