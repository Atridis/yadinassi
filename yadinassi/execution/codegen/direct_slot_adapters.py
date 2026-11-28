"""Adapt reference protocols only where they enter or leave direct BSL slots."""
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.types.array_index import array_offset
from .direct_collections import _bound_ref, _OMITTED_REF
from .direct_live_state import _ForwardReference, _SlotReference
from .direct_reference_runtime import Address, bind_local_index_reference, local_field_reference
from .direct_structure import _DirectStructure


class _ReferenceStorage:
    __slots__ = ('reference',)

    def __init__(self, reference):
        self.reference = reference

    def __getitem__(self, _):
        return self.reference.get()

    def __setitem__(self, _, value):
        self.reference.set(value)


class LocalStorage(dict):
    """Only implicit address-taken locals can start without a value."""
    __slots__ = ('name',)

    def __init__(self, name):
        self.name = name

    def __missing__(self, key):
        raise NameError("Переменная или функция не определена: " + self.name, name=self.name)


def host_storage(reference):
    return _ReferenceStorage(_ForwardReference(reference))


def reference_pair(value):
    if value is _OMITTED_REF:
        return value, None
    _bound_ref(value)
    if type(value) is _SlotReference:
        return value.state, value.key
    return _ReferenceStorage(value), 0


def slot_reference(storage, key):
    kind = type(storage)
    if kind is dict or kind is LocalStorage:
        return _SlotReference(storage, key)
    if kind is _ReferenceStorage:
        return storage.reference
    return Address(lambda: storage[key], lambda value: storage.__setitem__(key, value))


def index_pair(context, receiver, key):
    kind = type(receiver)
    if kind is list or kind is PlainArray:
        return receiver, array_offset(receiver, key)
    return reference_pair(bind_local_index_reference(context, receiver)(key))


def field_pair(context, receiver, key):
    if type(receiver) is _DirectStructure:
        receiver[key]
        return receiver, key
    return reference_pair(local_field_reference(context, receiver, key))


def keyword_pair(name, key_name, pair):
    return {name: pair[0], key_name: pair[1]}


def export_slot_routine(function, keys, names):
    """The caller boundary still supplies one logical argument per formal."""
    indexes = dict(zip(names, keys))

    def invoke(*actuals, **named):
        if len(actuals) > len(keys):
            raise TypeError('Слишком много аргументов')
        items = []
        for key, value in zip(keys, actuals):
            if key is None:
                items.append(value)
            else:
                items.extend(reference_pair(value))
        keywords = {}
        for name, value in named.items():
            key = indexes.get(name)
            if key is None:
                keywords[name] = value
            else:
                keywords.update(keyword_pair(name, key, reference_pair(value)))
        return function(*items, **keywords)
    invoke._bsl_formal_names = names
    return invoke
