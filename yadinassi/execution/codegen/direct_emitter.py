"""Clean-sheet direct emitter: Python owns control flow and scalar arithmetic."""
import ast as p
from dataclasses import replace
from . import direct_goto
from decimal import Decimal
from functools import partial
from types import FunctionType

from yadinassi.syntax import ast as b
from .direct_collections import Program, UnsupportedNakedSyntax, _Cell, _Reference, _bound_ref, _host_omission_error, _host_omission_values, _OMITTED_REF
from yadinassi.types.array_index import array_offset
from yadinassi.execution.direct.python_direct_plain_map import PlainMap, plain_map
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.collections.structures import BSLKeyAndValue, BSLStructure, BSLFixedStructure
from .direct_errors import handled_error, reraise_handled
from .direct_resources import bounded_array, bounded_insert
from .direct_scalar_semantics import typed_find
from .direct_structure import _DirectStructure, new_structure
from yadinassi.execution.direct.python_direct_names import CHARS_ALIASES, NAMES as SYSTEM_NAMES
from yadinassi.types.errors import BSLRuntimeError
from .direct_live_state import UNSET, source_reference, _SlotReference, _ForwardReference
from .direct_boundaries import BoundaryViolation, _MISSING as _SERVICE_MISSING
from yadinassi.execution.direct.python_direct_eval import bind_eval
from yadinassi.execution.direct.python_direct_execute import FragmentScope, execute_fragment
from yadinassi.types.values import BSLArray, BSLFixedArray, BSLObject, HostFunction, Reference
from .direct_scalar_semantics import concatenate, presentation, truth
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.direct.python_direct_numbers import divide, remainder, sign, public_number
from yadinassi.execution.direct.python_direct_dynamic_new import construct
from yadinassi.execution.direct.python_direct_error_info import raise_arity_error, raise_error


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


def owned_index(context,receiver):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        return lambda key: receiver[array_offset(receiver,key)]
    if kind is PlainMap or kind is _DirectStructure:
        return receiver.__getitem__
    return context.resolve_member(receiver,'__getitem__')


def read_bracket(context, receiver, key):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        return receiver[array_offset(receiver,key)]
    if kind is dict:
        return receiver.get(key)
    if kind is not BSLMap and kind is not BSLFixedMap and issubclass(kind,BSLObject):
        return context.resolve_member(receiver,'__getitem__')(key)
    return receiver[key]


def write_bracket(context, receiver, key, value):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        key=array_offset(receiver,key)
    elif kind is not BSLMap and kind is not BSLFixedMap and issubclass(kind,BSLObject):
        context.resolve_member(receiver,'__setitem__')(key,value)
        return
    receiver[key]=value


def owned_set_index(context,value,receiver,key):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        receiver[array_offset(receiver,key)] = value
    elif kind is PlainMap or kind is _DirectStructure:
        receiver[key] = value
    else:
        context.resolve_member(receiver,'__setitem__')(key,value)


def owned_iterable(context, iterable):
    kind=type(iterable)
    if kind is list or kind is PlainArray or kind is _DirectStructure:
        return iter(iterable)
    if kind is PlainMap:
        return iterable.bsl_entries()
    return context.resolve_member(iterable,'__iter__')()


def bsl_iterable(context, iterable):
    # PlainMap implements the Python mapping protocol for host callers. Only
    # BSL's loop enumerates its logical pairs instead of its keys.
    kind=type(iterable)
    if kind is PlainMap:
        return iterable.bsl_entries()
    if issubclass(kind,BSLObject):
        return context.resolve_member(iterable,'__iter__')()
    return iterable


def native_array_expression(value):
    return isinstance(value,p.List) or (
        isinstance(value,p.Call) and isinstance(value.func,p.Name) and value.func.id=='_Array')


def metered(context, iterable):
    iterator=iter(owned_iterable(context,iterable))
    while True:
        context.checkpoint()
        try:
            value=next(iterator)
        except StopIteration:
            return
        yield value


# Only boxed collections arriving through codecs or a host boundary need a
# stable borrowed backing. Ordinary Python lists/references do not use this.
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
    if (kind is BSLArray or kind is BSLFixedArray) and context.policy is None:
        return partial(boxed_array_reference, context, receiver)
    return bind_index_reference(context, receiver)


def bind_index_reference(context, receiver):
    kind=type(receiver)
    if not (kind is list or kind is PlainArray or kind is PlainMap or kind is _DirectStructure):
        return context.bind_reference_index(receiver)
    def bind_index(key):
        def index():
            return array_offset(receiver,key) if kind is list or kind is PlainArray else key
        def get():
            if kind is PlainMap:
                return receiver.get(key)
            return receiver[index()]
        def set_value(value):
            receiver[index()] = value
        get()
        return Address(get,set_value)
    return bind_index


def fragment_reference(read,write):
    try:
        read()
    except NameError:
        return None
    return Reference(read,write)


def source_shapes(bound, named):
    prepare=getattr(bound,'prepare_argument_shapes',None)
    if prepare is not None:prepare(named)
    return bound


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


def unchanged(value):
    return value


def lexical_reference(get, set_value):
    if get() is UNSET:raise NameError("Uninitialized reference")
    return Address(get,set_value,name_sink=True)


_BINARY = {'+': p.Add, '-': p.Sub, '*': p.Mult}
_COMPARE = {'=': p.Eq, '<>': p.NotEq, '<': p.Lt, '<=': p.LtE, '>': p.Gt, '>=': p.GtE}
_MISSING = object()
_SELF_NAMES = frozenset(('thisobject','этотобъект'))
_NATIVE_CONSTRUCTORS = frozenset(('array','массив','map','соответствие','structure','структура'))
_VALUE_TYPE_NAMES = frozenset(('date','дата','sortdirection','направлениесортировки','promise','обещание'))
_CALLBACK_MODULE_SLOTS = {'readjson':5,'прочитатьjson':5,'writejson':4,'записатьjson':4,
                          'new:callbackdescription':1,'new:описаниеоповещения':1}
_NONCONSTRUCTIBLE = frozenset(('formdatacollection','данныеформыколлекция',
    'formdatacollectionitem','данныеформыэлементколлекции','formtable','таблицаформы',
    'collectionindex','индексколлекции','collectionindexes','индексыколлекции'))


ARRAY_ALIASES={'количество':'count','вграница':'ubound','добавить':'add','очистить':'clear',
          'получить':'get','установить':'set','вставить':'insert','удалить':'delete','найти':'find'}


def self_read(context,state,key):
    return state[key] if key in state else context.current_module()


def self_write(state,key,value):
    if key not in state:raise ValueError('Модульное имя только для чтения: '+key)
    state[key]=value


def self_reference(context,state,key):
    return source_reference(state,key) if key in state else _Cell(context.current_module())


def nonconstructible(key, missing=False):
    if missing:
        raise TypeError('Тип не определен: '+key)
    raise TypeError('Тип нельзя создать оператором Новый: '+key)
_OP = dict(_Truth=truth, _PublicNumber=public_number, _Divide=divide, _Remainder=remainder, _Sign=sign,
           _GotoTransfer=direct_goto.GotoTransfer,_String=concatenate, _Missing=_MISSING, _OmittedRef=_OMITTED_REF, _ServiceMissing=_SERVICE_MISSING, _Unset=UNSET, _Map=PlainMap, _Nonconstructible=nonconstructible, _SelfRead=self_read, _SelfWrite=self_write, _SelfRef=self_reference,
           _Recoverable=(ArithmeticError,TypeError,ValueError,IndexError,NameError,RecursionError,BSLRuntimeError),
           _Handled=handled_error, _Reraise=reraise_handled, _Raise=raise_error,
           _RaiseArity=raise_arity_error, _Presentation=presentation,
           _LexicalRef=lexical_reference, _FragmentRef=fragment_reference, _Eval=bind_eval, _Execute=execute_fragment, _GetAttr=getattr, _SourceShapes=source_shapes, _VarRef=source_reference, _Cell=_Cell, _BoundRef=_bound_ref,
           _BindIndexRef=bind_index_reference, _BindLocalIndexRef=bind_local_index_reference, _HostRef=host_reference, _IndexedActual=indexed_actual, _MemberActual=member_actual, _CellActual=cell_actual, _Unchanged=unchanged, _ImportedRef=_ForwardReference,
           _Construct=construct, _Array=bounded_array, _Structure=new_structure, _MapFrom=plain_map, _Omissions=_host_omission_values, _InvalidOmissions=_host_omission_error)


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


def get_field(context, receiver, key):
    kind = type(receiver)
    if kind is list or kind is PlainArray:
        operation = ARRAY_ALIASES.get(key.casefold(), key.casefold())
        if operation in _ARRAY_ARITY:
            from yadinassi.execution.direct.python_direct_captured_values import register

            def invoke(*args):
                return array_method(receiver, key, len(args), False, ())(*args)

            return register(HostFunction(key, invoke, returns_value=operation not in _ARRAY_PROCEDURES))
    if kind is _DirectStructure:
        return receiver[key]
    if kind is BSLKeyAndValue:
        return receiver.get_member(key)
    return context.get_member(receiver,key)


def owns_property_output(receiver):
    kind=type(receiver)
    return kind is _DirectStructure or kind is BSLStructure or kind is BSLFixedStructure


def set_field(context, receiver, key):
    if type(receiver) is _DirectStructure:
        return lambda value: receiver.__setitem__(key,value)
    return context.resolve_set_member(receiver,key)


_ARRAY_ARITY = {'ubound':(0,0),'count':(0,0),'add':(0,1),'clear':(0,0),
                'get':(1,1),'set':(2,2),'insert':(1,2),'delete':(1,1),'find':(1,1)}
_ARRAY_PROCEDURES = frozenset(('add','clear','set','insert','delete'))


def array_get(receiver,index):
    return receiver[array_offset(receiver,index,method=True)]


def array_set(receiver,index,value):
    receiver[array_offset(receiver,index,method=True)] = value


def array_add(receiver,value=None):
    receiver.append(value)


def array_ubound(receiver):
    return len(receiver)-1


def array_delete(receiver,index):
    if type(index) is Decimal and (not index.is_finite() or index!=index.to_integral_value()):
        raise ValueError('Ожидается целое число')
    del receiver[array_offset(receiver,index)]


def array_find(receiver,value):
    if type(value) in (int,Decimal):
        for index,item in enumerate(receiver):
            if type(item) in (int,Decimal) and item==value:
                return index
        return None
    return typed_find(receiver,value)


_ARRAY_CALLS = {'ubound':array_ubound,'add':array_add,'get':array_get,'set':array_set,
                'insert':bounded_insert,'delete':array_delete,'find':array_find}
_MAP_ALIASES = {'вставить':'insert','удалить':'delete','очистить':'clear',
                'получить':'get','количество':'count'}
_MAP_ARITY = {'insert':(1,2),'delete':(1,1),'clear':(0,0),'get':(1,1),'count':(0,0)}


def reject_runtime_arity(key,count,arity):
    # A resolved collection method evaluates ordinary actuals before reporting
    # invalid arity, and drops temporaries before entering the BSL handler.
    expected=str(arity[0]) if arity[0]==arity[1] else f'{arity[0]}–{arity[1]}'
    def wrong_arity(*actuals):
        del actuals
        raise TypeError(f'{key} ожидает {expected} аргументов, получено {count}')
    return wrong_arity


def array_method(receiver,key,count,want_value,omitted):
    folded=key.casefold()
    operation=ARRAY_ALIASES.get(folded,folded)
    arity=_ARRAY_ARITY.get(operation)
    if arity is None:
        raise ValueError('Метод или свойство не найдено: '+key)
    if omitted:
        raise TypeError('Неверное количество аргументов: '+key)
    if not arity[0]<=count<=arity[1]:
        return reject_runtime_arity(key,count,arity)
    if want_value and operation in _ARRAY_PROCEDURES:
        raise TypeError('Процедура не возвращает значение: '+key)
    if operation=='count':return receiver.__len__
    if operation=='add' and count:return receiver.append
    if operation=='clear':return receiver.clear
    return partial(_ARRAY_CALLS[operation],receiver)


def requires_reference(bound,index):
    test=getattr(bound,'requires_reference',None)
    return test is not None and test(index)


def member(context, receiver, key, count, want_value, omitted=(), source_dispatch=False,configuration_dispatch=False):
    kind=type(receiver)
    if kind is list or kind is PlainArray:return array_method(receiver,key,count,want_value,omitted)
    folded=key.casefold()
    if not omitted and type(receiver) is _DirectStructure:
        if folded in ('property','свойство') and count in (1,2):return receiver.property
        if folded in ('insert','вставить') and count in (1,2):
            if want_value:raise TypeError('Процедура не возвращает значение: '+key)
            return receiver.insert
        if folded in ('delete','удалить') and count==1:
            if want_value:raise TypeError('Процедура не возвращает значение: '+key)
            return receiver.__delitem__
        if folded in ('clear','очистить') and not count:
            if want_value:raise TypeError('Процедура не возвращает значение: '+key)
            return receiver.clear
        if folded in ('count','количество') and not count:return receiver.__len__
    if type(receiver) is PlainMap:
        operation=_MAP_ALIASES.get(folded,folded)
        arity=_MAP_ARITY.get(operation)
        if arity is None:
            raise ValueError('Метод соответствия не найден: '+key)
        if omitted:
            raise TypeError('Неверное количество аргументов: '+key)
        if not arity[0]<=count<=arity[1]:
            return reject_runtime_arity(key,count,arity)
        if operation=='get':return receiver.get
        if operation=='count':return receiver.__len__
        if want_value:raise TypeError('Процедура не возвращает значение: '+key)
        if operation=='insert':
            if count==2:return receiver.__setitem__
            return lambda item:receiver.__setitem__(item,None)
        if operation=='delete':return receiver.__delitem__
        return receiver.clear
    if (omitted and not (configuration_dispatch or source_dispatch)
            and folded in ('openfile','открытьфайл')):
        return context.resolve_optional_open_file(receiver,key,require_value=want_value,
                                                  omitted=omitted,argument_count=count)
    if configuration_dispatch:
        return context.resolve_configuration_member_call(receiver,key,require_value=want_value,omitted=omitted,argument_count=count)
    if source_dispatch:
        return context.resolve_source_member(receiver,key,require_value=want_value,argument_count=count,allow_references=True)
    return context.resolve_member_call(receiver,key,require_value=want_value,omitted=omitted)


_OP.update(_RequiresReference=requires_reference,_OwnedIndex=owned_index,_OwnedSetIndex=owned_set_index,_Metered=metered,_OwnedIterable=owned_iterable,_BSLIterable=bsl_iterable,_Member=member,_GetField=get_field,_SetField=set_field,_FieldRef=field_reference,_LocalFieldRef=local_field_reference,_OwnsPropertyOutput=owns_property_output)
_OP.update(_WriteBracket=write_bracket,_ReadBracket=read_bracket)


def _node(n, token):
    if 'lineno' in n._attributes:
        n.lineno=n.end_lineno=token.line
        n.col_offset=max(0,token.column-1)
        n.end_col_offset=n.col_offset+1
    return n


def name(value, store=False):
    return p.Name(id=value, ctx=p.Store() if store else p.Load())


def call(target, *args, **kwargs):
    if isinstance(target,str):
        target=name(target)
    return p.Call(func=target, args=list(args),
                  keywords=[p.keyword(arg=k,value=v) for k,v in kwargs.items()])


def attr(target,key):
    return p.Attribute(value=target, attr=key, ctx=p.Load())


def literal(value):
    return p.Constant(value=value)


def arguments(names):
    return p.arguments(posonlyargs=[],args=[p.arg(arg=k) for k in names],vararg=None,
                       kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])


def bind(template,state):
    # Helpers are closures, never Python names exposed through BSL state.
    # A compiled BSL global has no Python builtin fallback.
    old=dict.get(state,'__builtins__',_MISSING)
    dict.__setitem__(state,'__builtins__',{})
    try:
        return FunctionType(template.__code__,state,closure=template.__closure__)
    finally:
        if old is _MISSING:
            dict.__delitem__(state,'__builtins__')
        else:
            dict.__setitem__(state,'__builtins__',old)


class Emit:
    def __init__(self, filename):
        self.filename=filename
        self.number=0
        self.constants=[]
        self.loop=[]
        self.dispatch=[]
        self.has_jumps=False
        self.goto_labels={}
        self.goto_transfers={}
        self.tail=None
        self.tail_requires_value=False
        self.globals=set()
        self.written=set()
        self.locals=set()
        self.module_declarations=set()
        self.routines={}
        self.parameters={}
        self.in_async=False
        self.references=set()
        self.addresses={}
        self.reference_services=set()
        self.value_services=frozenset()
        self.fragment=False
        self.in_routine=False
        self.owned=False
        self.externals=frozenset()
        self.current_module=False
        self.meter_loops=False
        self.source_scopes=False
        self.server_services=set()
        self.import_roots=frozenset()
        self.source_dispatch=False
        self.scalar_routines=False
        self.shadowable=frozenset()
        self.implicit_shadows=set()
        self.shadows=frozenset()
        self.constructor_profile=None
        self.ordinary_constructors=()
        self.tree_constructors=()
        self.host_extensions=False
        self.catalog_budget=False
        self.bound_constructors=frozenset()
        self.configuration_dispatch=False

    def temp(self):
        self.number+=1
        return f'_T{self.number}'

    def var(self,key,store=False):
        key=key.casefold()
        if key in self.references:
            return p.Attribute(value=name(key),attr='value',ctx=p.Store() if store else p.Load())
        if key not in self.locals:
            self.globals.add(key)
            if store:self.written.add(key)
            if self.fragment:
                return p.Subscript(value=name('_S'),slice=literal(key),ctx=p.Store() if store else p.Load())
        return name(key,store)

    def opaque(self,value):
        pos=len(self.constants)
        self.constants.append(value)
        return p.Subscript(value=name('_K'),slice=literal(pos),ctx=p.Load())

    def literal(self,value):
        if type(value) is Decimal:
            if value.as_tuple().exponent==0 and not (value.is_zero() and value.is_signed()):
                return literal(int(value))
            return self.opaque(value)
        if type(value) in (bool,str,type(None)):
            return literal(value)
        return self.opaque(value)

    def expr(self,x,want_value=True):
        value=self.expression(x,want_value)
        if self.catalog_budget:
            step=call(attr(name('_C'),'preparation_step'))
            sequenced=p.Subscript(value=p.Tuple(elts=[step,value],ctx=p.Load()),slice=literal(1),ctx=p.Load())
            value=call(attr(name('_C'),'preparation_value'),sequenced)
        return _node(value,x.token)

    def external(self,key):
        return key in self.externals and key not in self.locals and key not in self.module_declarations

    def read_external(self,key):
        return call(attr(name('_C'),'external_get'),literal(key))

    def write_external(self,key,value):
        if self.meter_loops:
            value=call('_PublicNumber',value)
        return p.Expr(value=call(attr(name('_C'),'external_set'),literal(key),value))

    def import_path(self,expr):
        attributes=[]
        while True:
            if type(expr) is b.Group:
                expr=expr.expression
            elif type(expr) is b.Attribute:
                attributes.append(expr.name.casefold())
                expr=expr.object
            else:
                break
        if type(expr) is not b.Name:
            return None
        key=expr.name.casefold()
        if key not in self.import_roots or key in self.locals:
            return None
        return (key,*reversed(attributes))

    def expression(self,x,want_value):
        path=self.import_path(x)
        if path is not None:
            return call(attr(name('_C'),'import_get'),literal(path))
        if type(x) is b.Literal:return self.literal(x.value)
        if type(x) is b.Name:
            key=x.name.casefold()
            if key in self.shadows:
                value=self.var(key)
                return p.IfExp(test=p.Compare(left=value,ops=[p.Is()],comparators=[name('_Unset')]),
                    body=call(attr(name('_C'),'external_get'),literal(key)),orelse=self.var(key))
            if key not in self.locals and key not in self.module_declarations:
                if self.current_module and key in _SELF_NAMES:
                    return call('_SelfRead',name('_C'),name('_S'),literal(key))
                if key in self.externals:
                    return self.read_external(key)
                if key in SYSTEM_NAMES and not self.owned:
                    if key in CHARS_ALIASES:
                        return call(attr(name('_C'),'character_namespace'),literal(key))
                    return self.opaque(SYSTEM_NAMES[key])
            return self.var(x.name)
        if type(x) is b.Group:return self.expr(x.expression,want_value)
        if type(x) is b.Await:
            if not self.in_async:
                raise PythonDirectUnsupported('Await outside an asynchronous routine')
            return p.Yield(value=call('_AwaitRequest',self.expr(x.operand)))
        if type(x) is b.Conditional:
            return p.IfExp(test=self.condition(x.condition),
                           body=self.expr(x.when_true),orelse=self.expr(x.when_false))
        if type(x) is b.Unary:
            if x.operator=='NOT':return p.UnaryOp(op=p.Not(),operand=self.condition(x.operand))
            if type(x.operand) is b.Literal and type(x.operand.value) is Decimal:
                val=x.operand.value
                return self.literal(val.copy_negate() if x.operator=='-' else val)
            return call('_Sign',self.expr(x.operand),literal(x.operator))
        if type(x) is b.Binary:
            op=x.operator
            if op in ('AND','OR'):
                return p.BoolOp(op=p.And() if op=='AND' else p.Or(),
                                values=[self.condition(x.left),self.condition(x.right)])
            l,r=self.expr(x.left),self.expr(x.right)
            if op in _BINARY:
                if op=='+' and (type(l) is p.Constant and type(l.value) is str
                                or type(l) is p.Call and type(l.func) is p.Name and l.func.id=='_String'):
                    return call('_String',l,r)
                return p.BinOp(left=l,op=_BINARY[op](),right=r)
            if op in _COMPARE:return p.Compare(left=l,ops=[_COMPARE[op]()],comparators=[r])
            if op=='/':return call('_Divide',l,r)
            if op=='%':return call('_Remainder',l,r)
        if type(x) is b.Index:
            return self.index(x)
        if type(x) is b.Attribute:
            return call('_GetField',name('_C'),self.expr(x.object),literal(x.name))
        if type(x) is b.DynamicNew:
            params=literal(None) if x.parameters is None else self.expr(x.parameters)
            return call('_Construct',name('_C'),self.expr(x.type_expression),params)
        if type(x) is b.New:
            key=x.name.casefold()
            if key in ('date','дата') and not x.arguments:
                return call('_Nonconstructible',literal(x.name),literal(True))
            if key in _NONCONSTRUCTIBLE or key in _VALUE_TYPE_NAMES and not x.arguments:
                return call('_Nonconstructible',literal(x.name))
            if (self.constructor_profile is not None and key not in _NATIVE_CONSTRUCTORS
                    and key not in self.constructor_profile and key not in self.ordinary_constructors
                    and key not in self.tree_constructors):
                raise PythonDirectUnsupported(f'constructor {x.name}; unavailable in this execution profile')
            if key in self.bound_constructors:return self.service_call('new:'+key,x.arguments,want_value)
            if key in ('array','массив','map','соответствие'):
                if self.omissions(x.arguments):
                    return call('_InvalidOmissions')
                if not x.arguments:
                    return p.List(elts=[],ctx=p.Load()) if key in ('array','массив') else call('_Map')
                return call('_Array' if key in ('array','массив') else '_MapFrom',
                            *(self.expr(arg) for arg in x.arguments))
            if key in ('structure','структура'):
                if self.omissions(x.arguments):return call('_InvalidOmissions')
                return call('_Structure',*(self.expr(arg) for arg in x.arguments))
            return self.service_call('new:'+key,x.arguments,want_value)
        if type(x) is b.Call:
            c=x.callee
            while type(c) is b.Group:c=c.expression
            if type(c) is not b.Name and type(c) is not b.Attribute:
                omitted=self.omissions(x.arguments)
                bound=call(attr(name('_C'),'resolve_extension_value'),self.expr(c),
                           require_value=literal(want_value),allow_references=literal(True))
                return self.bound_call(bound,x.arguments,omitted,references=True)
            path=self.import_path(c)
            if path is not None:
                omitted=self.omissions(x.arguments)
                options={'require_value':literal(want_value),'argument_count':literal(len(x.arguments))}
                if omitted:options['omitted']=literal(omitted)
                bound=call(attr(name('_C'),'resolve_import_call'),literal(path),**options)
                return self.bound_call(bound,x.arguments,omitted,references=True)
            if type(c) is b.Name:
                key=c.name.casefold()
                if key in self.routines:
                    return self.local_call(key,x.arguments)
                return self.service_call(c.name,x.arguments,want_value)
            omitted=self.omissions(x.arguments)
            root=c.object
            while type(root) is b.Group:root=root.expression
            if (self.current_module and not self.owned and type(root) is b.Name
                    and root.name.casefold() in _SELF_NAMES
                    and root.name.casefold() not in self.locals
                    and root.name.casefold() not in self.module_declarations):
                options={'require_value':literal(want_value),'argument_count':literal(len(x.arguments))}
                if omitted:options['local_omissions']=literal(True)
                bound=call(attr(name('_C'),'resolve_public_module_call'),self.expr(root),literal(c.name),**options)
                return self.bound_call(bound,x.arguments,omitted,references=True)
            qualifier=root
            while type(qualifier) in (b.Group,b.Attribute):
                qualifier=qualifier.expression if type(qualifier) is b.Group else qualifier.object
            if self.source_dispatch and type(qualifier) is b.Name and self.external(qualifier.name.casefold()):
                bound=call('_Member',name('_C'),self.expr(c.object),literal(c.name),
                           literal(len(x.arguments)),literal(want_value),literal(omitted),source_dispatch=literal(True))
                return self.bound_call(bound,x.arguments,omitted,references=True,crossing=True,shapes=True)
            if omitted:
                target=root
                while type(target) in (b.Group,b.Attribute):
                    target=target.expression if type(target) is b.Group else target.object
                if type(target) is not b.Name:return call('_InvalidOmissions')
            binding=[] if not omitted else [literal(omitted)]
            receiver=self.expr(c.object)
            property_output=not omitted and len(x.arguments)==2 and c.name.casefold() in ('property','свойство')
            if property_output:
                slot=self.temp()
                receiver=p.NamedExpr(target=name(slot,True),value=receiver)
            bound=call('_Member',name('_C'),receiver,literal(c.name),
                       literal(len(x.arguments)),literal(want_value),*binding,
                       **({'source_dispatch':literal(True)} if self.source_dispatch else
                          {'configuration_dispatch':literal(True)} if self.configuration_dispatch else {}))
            if self.source_dispatch and not omitted and not property_output:
                return self.bound_call(bound,x.arguments,omitted,references=True,crossing=True,shapes=True)
            if property_output:
                native=call('_OwnsPropertyOutput',name(slot))
                return call(bound,self.expr(x.arguments[0]),self.actual_address(x.arguments[1],native))
            return call(bound,*(literal(None) if i in omitted else self.expr(arg)
                                for i,arg in enumerate(x.arguments)))
        raise PythonDirectUnsupported(f'clean emitter: {type(x).__name__}')

    @staticmethod
    def omissions(args):
        return tuple(i for i,arg in enumerate(args) if type(arg) is b.OmittedArgument)

    def local_call(self,key,args):
        bound=self.routines[key]
        params=self.parameters[key]
        omitted=self.omissions(args)
        if len(args)>len(params) or any(params[i].default is None for i in omitted):
            return call('_InvalidOmissions')
        def actual(i):
            return self.expr(args[i]) if params[i].by_value else self.reference(args[i],known_local=True)
        if not omitted:
            return call(bound,*(actual(i) for i in range(len(args))))
        # Only a call with a positional hole needs spelling its suffix by name.
        prefix=omitted[0]
        return call(bound,*(actual(i) for i in range(prefix)),
                    **{params[i].name.casefold():actual(i)
                       for i in range(prefix,len(args)) if i not in omitted})

    def reference(self,arg,known_local=False):
        while type(arg) is b.Group:
            arg=arg.expression
        path=self.import_path(arg)
        if path is not None:
            return call('_ImportedRef',call(attr(name('_C'),'import_reference'),literal(path)))
        if type(arg) is b.Name:
            key=arg.name.casefold()
            if key in self.references:
                return call('_BoundRef',name(key))
            if self.external(key):
                return call(attr(name('_C'),'external_reference'),literal(key))
            if self.current_module and key in _SELF_NAMES and key not in self.locals and key not in self.module_declarations:
                return call('_SelfRef',name('_C'),name('_S'),literal(key))
            if key not in self.locals:
                if not self.owned and key in CHARS_ALIASES and key not in self.module_declarations:
                    return call(attr(name('_C'),'character_namespace_reference'),literal(key))
                return call('_VarRef',name('_S'),literal(key))
            # Python lifts only explicitly borrowed locals into closure cells.
            getter,setter=self.address(key)
            return call('_LexicalRef',name(getter),name(setter))
        if type(arg) is b.Index:
            return call(call('_BindLocalIndexRef' if known_local else '_BindIndexRef',name('_C'),self.expr(arg.object)),self.expr(arg.index))
        if type(arg) is b.Attribute:
            return call('_LocalFieldRef' if known_local else '_FieldRef',name('_C'),self.expr(arg.object),literal(arg.name))
        return call('_Cell',self.expr(arg))

    def address(self,key):
        if key not in self.addresses:
            self.addresses[key]=self.temp(),self.temp()
        return self.addresses[key]

    def fragment_arguments(self):
        pairs=[]
        if self.in_routine:
            for key in sorted(self.locals):
                if key in self.references:
                    value=call('_HostRef',name(key))
                else:
                    getter,setter=self.address(key)
                    value=call('_FragmentRef',name(getter),name(setter))
                pairs.append((literal(key),value))
        bindings=p.Dict(keys=[k for k,_ in pairs],values=[v for _,v in pairs])
        visible=literal(tuple(sorted(self.module_declarations)) if self.in_routine else None)
        return name('_C'),name('_S'),bindings,visible

    def address_definitions(self):
        for key,(getter,setter) in self.addresses.items():
            yield p.FunctionDef(name=getter,args=arguments(()),
                                body=[p.Return(value=name(key))],decorator_list=[])
            yield p.FunctionDef(name=setter,args=arguments(('_Value',)),
                                body=[p.Nonlocal(names=[key]),p.Assign(targets=[name(key,True)],
                                      value=name('_Value'))],decorator_list=[])

    def service_call(self,key,args,want_value):
        omitted=self.omissions(args)
        resolver='resolve_optional_service' if omitted else 'resolve_service'
        folded=key.casefold()
        references=(folded in self.reference_services or
                    self.source_dispatch and not folded.startswith('new:') and folded not in self.value_services)
        crossing=folded in self.server_services
        target=[literal(key)]
        if self.source_dispatch and not folded.startswith('new:') and not self.external(folded):
            if folded in self.locals:
                target.append(self.var(folded))
            elif folded not in self.value_services:
                target.append(call(attr(name('_S'),'get'),literal(folded),name('_ServiceMissing')))
        contract={'require_value':literal(want_value),'argument_count':literal(len(args))}
        if references:
            contract['allow_references']=literal(True)
        if crossing and references:
            non_names=[]
            for i,arg in enumerate(args):
                while type(arg) is b.Group:arg=arg.expression
                if type(arg) not in (b.Name,b.OmittedArgument):
                    non_names.append(i)
            if non_names:
                contract['_non_name_actuals']=literal(tuple(non_names))
        bound=call(attr(name('_C'),resolver),*target,**contract)
        if key.casefold() in ('eval','вычислить'):
            bound=call('_Eval',bound,*self.fragment_arguments())
        callback_slot=_CALLBACK_MODULE_SLOTS.get(folded) if self.import_roots else None
        callback = self.import_path(args[callback_slot]) if (callback_slot is not None
                                                             and callback_slot < len(args)) else None
        return self.bound_call(bound,args,omitted,references=references,crossing=crossing,
                               callback=(callback_slot,callback) if callback is not None else None)

    def bound_call(self,bound,args,omitted,*,references=False,crossing=False,shapes=False,callback=None):
        if shapes:
            named=[]
            for arg in args:
                while type(arg) is b.Group:arg=arg.expression
                named.append(type(arg) in (b.Name,b.OmittedArgument))
            bound=call('_SourceShapes',bound,literal(tuple(named)))
        if not omitted and not references and not crossing and callback is None:
            return call(bound,*(self.expr(arg) for arg in args))
        slot=self.temp()
        prepared=p.NamedExpr(target=name(slot,True),value=bound)
        def item(obj,index):
            return p.Subscript(value=obj,slice=literal(index),ctx=p.Load())
        if omitted:
            prepared.value=call('_Omissions',bound,literal(omitted),literal(len(args)))
            bound=item(prepared,0)
        else:
            bound=prepared
        def actual(i,arg):
            if i in omitted:
                return item(item(name(slot),1),i)
            function=item(name(slot),0) if omitted else name(slot)
            if callback is not None and i==callback[0]:
                allowed=call('_GetAttr',function,literal('accepts_callback_module'),literal(False))
                return p.IfExp(test=p.Compare(left=allowed,ops=[p.Is()],comparators=[literal(True)]),
                    body=call(attr(name('_C'),'import_callback_module'),literal(callback[1])),
                    orelse=self.expr(arg))
            plain=arg
            while type(plain) is b.Group:plain=plain.expression
            named=crossing and type(plain) is b.Name
            is_reference=call('_RequiresReference',function,literal(i))
            if not named:
                return self.actual_address(arg,is_reference) if references else self.expr(arg)
            value=self.expr(arg)
            reference=call('_HostRef',self.reference(arg),name('_C'))
            late=self.temp()
            factory=p.NamedExpr(target=name(late,True),
                value=call('_GetAttr',function,literal('prepare_named_value'),literal(None)))
            value=p.IfExp(test=p.Compare(left=factory,ops=[p.IsNot()],comparators=[literal(None)]),
                          body=call(late,reference),orelse=value)
            if not references:return value
            return p.IfExp(test=is_reference,body=reference,orelse=value)
        return call(bound,*(actual(i,arg) for i,arg in enumerate(args)))

    def actual_address(self,arg,test):
        plain=arg
        while type(plain) is b.Group:plain=plain.expression
        if type(plain) is b.Name:
            return p.IfExp(test=test,body=call('_HostRef',self.reference(arg),name('_C')),orelse=self.expr(arg))
        if type(plain) is b.Index:
            owned=self.meter_loops or self.source_dispatch or self.configuration_dispatch
            bind=call('_IndexedActual',name('_C'),test,self.expr(plain.object),literal(owned))
            return call(bind,self.expr(plain.index))
        if type(plain) is b.Attribute:
            return call('_MemberActual',name('_C'),test,self.expr(plain.object),literal(plain.name))
        convert=p.IfExp(test=test,body=name('_CellActual'),orelse=name('_Unchanged'))
        return call(convert,self.expr(arg))


    def index(self,x):
        receiver,key=self.expr(x.object),self.expr(x.index)
        if self.meter_loops or self.source_dispatch or self.configuration_dispatch:
            return _node(call(call('_OwnedIndex',name('_C'),receiver),key),x.token)
        return _node(call('_ReadBracket',name('_C'),receiver,key),x.token)

    def routine(self,routine):
        from dataclasses import fields
        args=arguments(tuple(param.name.casefold() for param in routine.parameters))
        optional=False
        defaults=[]
        for param in routine.parameters:
            if param.default is not None:
                optional=True
                default=self.expr(param.default)
                key=param.name.casefold()
                if param.by_value:
                    deferred = type(param.default) is not b.Literal
                    args.defaults.append(name('_OmittedRef') if deferred else default)
                    if deferred or self.source_dispatch:
                        defaults.append(p.If(test=p.Compare(left=name(key),ops=[p.Is()],comparators=[name('_OmittedRef')]),
                            body=[p.Assign(targets=[name(key,True)],value=default)],orelse=[]))
                else:
                    args.defaults.append(name('_Missing'))
                    probe=p.Compare(left=name(key),ops=[p.Is()],comparators=[name('_Missing')])
                    if self.source_dispatch:
                        probe=p.BoolOp(op=p.Or(),values=[probe,p.Compare(left=name(key),ops=[p.Is()],comparators=[name('_OmittedRef')])])
                    defaults.append(p.If(test=probe,
                        body=[p.Assign(targets=[name(key,True)],value=call('_Cell',default))],orelse=[]))
            elif optional:
                raise PythonDirectUnsupported('clean emitter: parameter after default')
        local={param.name.casefold() for param in routine.parameters}
        declared=set()
        writes=set()
        direct_vars=({id(statement) for statement in routine.body if type(statement) is b.Var}
                     if self.externals else ())
        queue=[routine.body]
        has_fragments=False
        has_await=False
        while queue:
            item=queue.pop()
            if type(item) is b.Await:has_await=True
            if type(item) is b.Execute or (type(item) is b.Call and type(item.callee) is b.Name
                    and item.callee.name.casefold() in ('eval','вычислить')):
                has_fragments=True
            if isinstance(item,b.Var):
                keys={key.casefold() for key in item.names}
                if keys & self.externals and id(item) not in direct_vars:
                    raise PythonDirectUnsupported('conditional local Var shadowing external storage')
                declared.update(keys)
            elif isinstance(item,b.Assign) and type(item.target) is b.Name:writes.add(item.target.name.casefold())
            elif isinstance(item,(b.For,b.ForEach)):writes.add(item.name.casefold())
            if isinstance(item,b.Node) and not isinstance(item,b.Literal):
                queue.extend(getattr(item,f.name) for f in fields(item) if f.name!='token')
            elif type(item) in (list,tuple):queue.extend(item)
        old=self.locals,self.globals,self.references,self.addresses,self.in_routine,self.shadows,self.in_async
        self.in_routine=True
        self.in_async=routine.is_async
        implicit=_SELF_NAMES if self.current_module else frozenset()
        shadows=(writes & self.shadowable & self.externals)-self.module_declarations-declared-local
        if shadows and has_fragments:
            raise UnsupportedNakedSyntax('source implicit namespace shadow with Execute/Eval is not integrated')
        self.implicit_shadows.update(shadows)
        self.shadows=frozenset(shadows)
        self.locals=local|declared|shadows|(writes-self.module_declarations-self.externals-implicit)
        self.globals=set()
        self.references={param.name.casefold() for param in routine.parameters if not param.by_value}
        self.addresses={}
        try:
            body=self.block(routine.body)
            if self.scalar_routines:
                actuals=p.Tuple(elts=[call('_PublicNumber',name(param.name.casefold())) for param in routine.parameters],ctx=p.Load())
                body.insert(0,p.Expr(value=call(attr(name('_C'),'scalar_values'),actuals)))
            shadow_slots=[p.Assign(targets=[name(key,True)],value=name('_Unset')) for key in sorted(shadows)]
            body=[*self.address_definitions(),*defaults,*shadow_slots,*body]
            if self.globals and not self.fragment:body.insert(0,p.Global(names=sorted(self.globals)))
            if routine.is_async and not has_await:
                # A no-Await async routine is still started eagerly as a task.
                body.append(_node(p.If(test=literal(False),
                    body=[p.Expr(value=p.Yield(value=None))],orelse=[]),routine.token))
        finally:self.locals,self.globals,self.references,self.addresses,self.in_routine,self.shadows,self.in_async=old
        body=body or [p.Pass()]
        if self.source_scopes:
            manager=call(attr(name('_C'),'routine_scope'))
            body=[p.With(items=[p.withitem(context_expr=manager,optional_vars=None)],body=body)]
        return p.FunctionDef(name=self.routines[routine.name.casefold()],args=args,
                             body=body,decorator_list=[])

    def condition(self,x):
        root=x
        while type(root) is b.Group:root=root.expression
        value=self.expr(x)
        if (type(root) is b.Binary and root.operator in (*_COMPARE,'AND','OR')
                or type(root) is b.Unary and root.operator=='NOT'
                or type(root) is b.Literal and type(root.value) in (bool,Decimal)):
            return value
        return call('_Truth',value)

    def block(self,nodes):
        if self.goto_labels and any(id(n) in self.goto_labels for n in nodes):
            return self.goto_block(nodes)
        if self.has_jumps and any(type(n) is b.Goto for n in nodes):
            prefix,cycle=direct_goto.linear_path(nodes)
            result=[stmt for n in prefix for stmt in self.stmt(n)]
            if cycle is not None:
                direct_goto.check_cycle(cycle,self.routines,PythonDirectUnsupported)
                loop=p.While(test=self.loop_condition(literal(True)),
                             body=[stmt for n in cycle for stmt in self.stmt(n)] or [p.Pass()],
                             orelse=[])
                result.append(_node(loop,nodes[0].token))
            return result
        return [stmt for n in nodes for stmt in self.stmt(n)]

    def loop_condition(self,test):
        if self.meter_loops:
            boundary=call(attr(name('_C'),'checkpoint'))
            return p.Subscript(value=p.Tuple(elts=[boundary,test],ctx=p.Load()),slice=literal(1),ctx=p.Load())
        return test

    def jump(self,target):
        return p.Raise(exc=call('_GotoTransfer',literal(target)),cause=literal(None))

    def loop_control(self,continuing):
        if not self.loop:
            raise PythonDirectUnsupported(('Continue' if continuing else 'Break')+' outside a loop')
        if self.dispatch and self.dispatch[-1][0]==len(self.loop):
            target=-2 if continuing else -3
            self.dispatch[-1][1].add(target)
            return [self.jump(target)]
        if continuing:
            from copy import deepcopy
            prefix=[] if self.loop[-1] is None else [deepcopy(self.loop[-1])]
            return [*prefix,p.Continue()]
        return [p.Break()]

    def goto_block(self,nodes):
        pc,caught=self.temp(),self.temp()
        segments=[(-1,[])]
        for node in nodes:
            destination=self.goto_labels.get(id(node))
            if destination is not None:segments.append((destination,[]))
            else:segments[-1][1].append(node)
        def assign(value):
            return p.Assign(targets=[name(pc,True)],value=value)
        def is_at(target):
            return p.Compare(left=name(pc),ops=[p.Eq()],comparators=[literal(target)])
        controls=set()
        self.dispatch.append((len(self.loop),controls))
        try:
            cases=[]
            for i,(target,body) in enumerate(segments):
                following=segments[i+1][0] if i+1<len(segments) else -4
                cases.append(p.match_case(pattern=p.MatchValue(value=literal(target)),guard=None,
                                          body=[assign(literal(following)),*[s for n in body for s in self.stmt(n)]]))
        finally:
            self.dispatch.pop()
        accepted=tuple(k for k,_ in segments[1:])+tuple(sorted(controls))
        destination=attr(name(caught),'target')
        handler=p.If(test=p.Compare(left=destination,ops=[p.In()],comparators=[literal(accepted)]),
                     body=[assign(destination)],orelse=[p.Raise(exc=None,cause=None)])
        attempt=p.Try(body=[p.Match(subject=name(pc),cases=cases)],
                      handlers=[p.ExceptHandler(type=name('_GotoTransfer'),name=caught,body=[handler])],
                      orelse=[],finalbody=[])
        active=p.Compare(left=name(pc),ops=[p.GtE()],comparators=[literal(-1)])
        result=[assign(literal(-1)),p.While(test=self.loop_condition(active),body=[attempt],orelse=[])]
        for target in sorted(controls):
            result.append(p.If(test=is_at(target),body=self.loop_control(target==-2),orelse=[]))
        return [_node(stmt,nodes[0].token) for stmt in result]

    def stmt(self,n):
        statements=self.statement(n)
        if self.catalog_budget:
            statements.insert(0,p.Expr(value=call(attr(name('_C'),'preparation_step'))))
        return [_node(stmt,n.token) for stmt in statements]

    def statement(self,n):
        kind=type(n)
        if kind is b.Assign:
            t=n.target
            value=self.expr(n.value)
            path=self.import_path(t)
            if path is not None:
                write=call(attr(name('_C'),'resolve_import_write'),literal(path))
                return [p.Expr(value=call(write,value))]
            if type(t) is b.Name:
                key=t.name.casefold()
                if self.external(key):
                    return [self.write_external(key,value)]
                if self.current_module and key in _SELF_NAMES and key not in self.locals and key not in self.module_declarations:
                    return [p.Expr(value=call('_SelfWrite',name('_S'),literal(key),value))]
                target=self.var(t.name,True)
            elif type(t) is b.Index:
                if self.meter_loops or self.source_dispatch or self.configuration_dispatch:
                    return [p.Expr(value=call('_OwnedSetIndex',name('_C'),value,
                                              self.expr(t.object),self.expr(t.index)))]
                # Evaluate receiver, key and RHS before validating the target.
                return [p.Expr(value=call('_WriteBracket',name('_C'),
                                          self.expr(t.object),self.expr(t.index),value))]
            elif type(t) is b.Attribute:
                write=call('_SetField',name('_C'),self.expr(t.object),literal(t.name))
                if self.meter_loops:value=call('_PublicNumber',value)
                return [p.Expr(value=call(write,value))]
            else:raise PythonDirectUnsupported('clean emitter: assignment target')
            return [p.Assign(targets=[target],value=value)]
        if kind in (b.Import,b.Label):return []
        if kind is b.Goto:return [self.jump(self.goto_transfers[id(n)])]
        if kind is b.ExpressionStatement:
            if n is self.tail:
                return [p.Return(value=self.expr(n.expression,self.tail_requires_value))]
            return [p.Expr(value=self.expr(n.expression,want_value=False))]
        if kind is b.Var:
            if self.locals:
                return [p.Assign(targets=[self.var(k,True)],value=literal(None)) for k in n.names]
            return [p.Expr(value=call(attr(name('_S'),'setdefault'),literal(k.casefold()),literal(None))) for k in n.names]
        if kind is b.If:
            tail=self.block(n.otherwise)
            for condition,body in reversed(n.branches):
                tail=[p.If(test=self.condition(condition),body=self.block(body) or [p.Pass()],orelse=tail)]
            return tail
        if kind in (b.While,b.ForEach,b.For):
            prefix=[]
            advance=None
            if kind is b.For:
                first,last=self.expr(n.start),self.expr(n.end)
                if not isinstance(last,p.Constant):
                    if not isinstance(first,p.Constant):
                        slot=self.temp()
                        prefix.append(p.Assign(targets=[name(slot,True)],value=first))
                        first=name(slot)
                    slot=self.temp()
                    prefix.append(p.Assign(targets=[name(slot,True)],value=last))
                    last=name(slot)
                key=n.name.casefold()
                if self.external(key):
                    prefix.append(self.write_external(key,first))
                    advance=self.write_external(key,p.BinOp(left=self.read_external(key),op=p.Add(),right=literal(1)))
                    counter=self.read_external(key)
                else:
                    prefix.append(p.Assign(targets=[self.var(key,True)],value=first))
                    advance=p.AugAssign(target=self.var(key,True),op=p.Add(),value=literal(1))
                    counter=self.var(key)
                test=p.Compare(left=counter,ops=[p.LtE()],comparators=[last])
            elif kind is b.While:
                test=self.condition(n.condition)
            self.loop.append(advance)
            try:body=self.block(n.body)
            finally:self.loop.pop()
            if advance is not None:
                body.append(advance)
            if kind is b.ForEach:
                iterable=self.expr(n.collection)
                if self.meter_loops:iterable=call('_Metered',name('_C'),iterable)
                elif not native_array_expression(iterable):
                    iterable=call('_OwnedIterable' if self.source_dispatch else '_BSLIterable',name('_C'),iterable)
                key=n.name.casefold()
                if self.external(key):
                    item=self.temp()
                    target=name(item,True)
                    body.insert(0,self.write_external(key,name(item)))
                else:
                    target=self.var(key,True)
                return [p.For(target=target,iter=iterable,body=body or [p.Pass()],orelse=[])]
            return prefix+[p.While(test=self.loop_condition(test),body=body or [p.Pass()],orelse=[])]
        if kind is b.Execute:
            return [p.Expr(value=call('_Execute',self.expr(n.expression),*self.fragment_arguments()))]
        if kind in (b.Break,b.Continue):
            return self.loop_control(kind is b.Continue)
        if kind is b.Try:
            caught=self.temp()
            note=call('_Handled',name('_C'),name(caught),literal(self.filename),name('_Source'))
            handler=p.With(items=[p.withitem(context_expr=note,optional_vars=None)],body=self.block(n.handler) or [p.Pass()])
            return [p.Try(body=self.block(n.body) or [p.Pass()],handlers=[p.ExceptHandler(type=name('_Recoverable'),name=caught,
                body=[handler])],orelse=[],finalbody=[])]
        if kind is b.Raise:
            if n.value is None:
                return [p.Expr(value=call('_Reraise',name('_C')))]
            description=call('_Presentation',self.expr(n.value))
            args=n.optional_arguments or ()
            if len(args)>4:
                return [p.Expr(value=call('_RaiseArity',description))]
            options=p.Tuple(elts=[literal(None) if type(arg) is b.OmittedArgument
                                  else self.expr(arg) for arg in args],ctx=p.Load())
            t=n.token
            return [p.Expr(value=call('_Raise',name('_C'),description,options,
                                      literal(self.filename),literal(t.line),
                                      literal(t.column),literal(t.source_line)))]
        if kind is b.Return:
            value=literal(None) if n.value is None else self.expr(n.value)
            if self.scalar_routines:
                value=call(attr(name('_C'),'scalar_result'),call('_PublicNumber',value))
            elif self.in_async:
                value=call('_PublicNumber',value)
            return [p.Return(value=value)]
        raise PythonDirectUnsupported(f'clean emitter: {kind.__name__}')


def compile_module(vm,program,nodes,source_text,source_name,*,_exports=False,fragment=False,require_value=False,
                   owned=False,module_names=(),external_names=(),current_module=False,reference_names=(),meter_loops=False,retain_generated=True,source_scopes=False,source_dispatch=False,scalar_routines=False,shadowable_externals=(),value_services=(),constructor_profile=None,catalog_budget=False,bound_constructors=(),configuration_dispatch=False):
    filename=source_name or (program[0].token.source if program else '<строка>')
    compiler=Emit(filename)
    compiler.has_jumps=any(type(n) is b.Goto for n in nodes) if nodes else direct_goto.has_goto(program)
    if compiler.has_jumps:
        compiler.goto_labels,compiler.goto_transfers=direct_goto.plan(program,PythonDirectUnsupported)
    compiler.fragment=fragment
    compiler.owned=owned
    compiler.externals=frozenset(key.casefold() for key in external_names)
    compiler.current_module=current_module or not owned
    compiler.meter_loops=meter_loops
    compiler.source_scopes=source_scopes
    compiler.source_dispatch=source_dispatch
    compiler.catalog_budget=catalog_budget
    compiler.bound_constructors=frozenset(bound_constructors)
    compiler.configuration_dispatch=configuration_dispatch
    compiler.scalar_routines=scalar_routines
    compiler.shadowable=frozenset(shadowable_externals)
    compiler.value_services=frozenset(value_services)
    if constructor_profile is not None:
        compiler.constructor_profile=(constructor_profile if type(constructor_profile) is dict
                                      else frozenset(constructor_profile))
    if vm is not None:
        from yadinassi.execution.direct.python_direct_imports import import_names
        compiler.import_roots=frozenset(import_names(vm,program))
        compiler.host_extensions=vm.allow_extensions
        # Runtime-recognized types include read-only types and bindings with
        # explicit diagnostics even when no callable constructor is registered.
        from yadinassi.execution.direct.python_direct_services import ORDINARY_CONSTRUCTORS
        from yadinassi.execution.direct.python_direct_value_tree import CONSTRUCTOR_NAMES
        compiler.ordinary_constructors=ORDINARY_CONSTRUCTORS
        compiler.tree_constructors=CONSTRUCTOR_NAMES

    compiler.reference_services={key for key,module in getattr(vm,'_direct_routine_modules',{}).items()
                                 if module.signatures[key][3]}
    compiler.reference_services.update(reference_names)
    compiler.reference_services.update(key for key,value in getattr(vm,'functions',{}).items()
                                       if type(value) is HostFunction and value.reference_parameters)
    declarations=[node for node in program if type(node) is b.Routine]
    if not owned:
        compiler.server_services={node.name.casefold() for node in declarations
                                  if node.execution_context=='server'}
        compiler.server_services.update(key for key,module in getattr(vm,'_direct_routine_modules',{}).items()
                                       if key in module.server_names)
    routines=declarations if owned else [node for node in declarations if node.execution_context=='client' and not node.is_dual]
    compiler.reference_services.update(node.name.casefold() for node in declarations
                                       if node not in routines and any(not param.by_value for param in node.parameters))
    declarations_in_source={
        key.casefold() for node in program if type(node) is b.Var and (owned or node.execution_context=='client')
        for key in node.names}
    if declarations_in_source & compiler.externals:
        raise PythonDirectUnsupported('external names collide with module declarations')
    compiler.module_declarations={key.casefold() for key in module_names}|set(getattr(vm,'module_names',()))|declarations_in_source
    compiler.routines={node.name.casefold():compiler.temp() for node in routines}
    # Async parameters are values, including those written without Val.
    routines=[replace(node,parameters=[replace(param,by_value=True) for param in node.parameters])
              if node.is_async else node for node in routines]
    compiler.parameters={node.name.casefold():node.parameters for node in routines}
    defs=[]
    async_bodies={}
    for node in routines:
        routine=compiler.routine(node)
        if node.is_async:
            key=node.name.casefold()
            public_name=routine.name
            routine.name=compiler.temp()
            async_bodies['@async:'+key]=routine.name
            public_args=routine.args
            routine.args=arguments(tuple(param.name.casefold() for param in node.parameters))
            defs.append(routine)
            actuals=p.Tuple(elts=[name(param.name.casefold()) for param in node.parameters],ctx=p.Load())
            start=call(attr(name('_C'),'start_async'),call('_BindAsync',name('naked_module'),name('_S')),
                       name('_K'),literal('@async:'+key),actuals,literal(not node.is_function))
            routine=p.FunctionDef(name=public_name,args=public_args,body=[p.Return(value=start)],decorator_list=[])
        defs.append(routine)
    ordinary=[node for node in program if type(node) not in (b.Routine,b.ServerInitializer)
              and not (not owned and type(node) is b.Var and node.execution_context!='client')]
    if ordinary and type(ordinary[-1]) is b.ExpressionStatement:
        compiler.tail=ordinary[-1]
        compiler.tail_requires_value=require_value
    declarations_first=[node for node in ordinary if type(node) is b.Var]
    executable=[node for node in ordinary if type(node) is not b.Var]
    body=[stmt for node in declarations_first for stmt in compiler.stmt(node)]
    body.extend(compiler.block(executable))
    if compiler.tail is None or compiler.goto_labels:
        body.append(p.Return(value=name('_S')))
    if compiler.globals and not fragment:
        body.insert(0,p.Global(names=sorted(compiler.globals)))
    if routines:
        bindings={**compiler.routines,**async_bodies}
        exports=p.Dict(keys=[literal(k) for k in bindings],
                       values=[name(v) for v in bindings.values()])
        initialize=[]
        if _exports:
            initialize=[p.Expr(value=call(attr(name('_S'),'setdefault'),literal(key),literal(None)))
                        for key in sorted(compiler.module_declarations)]
        body[:0]=[*initialize,*defs,p.If(test=name('_Bind'),body=[p.Return(value=exports)],orelse=[])]
    entry=p.FunctionDef(name='naked_module',args=arguments(('_S','_K','_C','_Bind')),
                        body=body,decorator_list=[])
    helpers={**_OP,'_Source':source_text or ''}
    if async_bodies:
        from yadinassi.application.async_runtime import AwaitRequest
        helpers.update(_AwaitRequest=AwaitRequest,_BindAsync=bind)
    helper_names=tuple(helpers)
    factory=p.FunctionDef(name='_factory',args=arguments(helper_names),
                          body=[entry,p.Return(value=name('naked_module'))],decorator_list=[])
    tree=p.fix_missing_locations(p.Module(body=[factory],type_ignores=[]))
    ns={}
    exec(compile(tree,filename,'exec'),ns)
    template=ns['_factory'](*helpers.values())
    published=tuple(compiler.written)
    def run(state,constants,context,bind_only=False):
        # Only the public observation uses Decimal. No conversion or
        # publication runs in the body of the generated loop.
        try:
            if fragment:
                if type(state) is not FragmentScope:
                    raise BoundaryViolation('fragment requires its live scope')
                execute=template
            else:
                execute=bind(template,state)
            result=execute(state,constants,context,bind_only or _exports)
            return Decimal(result) if type(result) is int else result
        finally:
            if not bind_only and not fragment and not _exports:
                for key in published:
                    value=state.get(key)
                    if type(value) is int:state[key]=Decimal(value)
    program=Program(None,tuple(compiler.constants),run,
                   source_name=filename,source_text=source_text or '',
                   _generated_tree=entry if retain_generated else None)
    program._source_implicit_shadows=frozenset(compiler.implicit_shadows)
    return program


def compile_owned(program, *, source_text, source_name, module_names=(), external_names=(),
                  exports=False, retain_generated=True, current_module=False, reference_names=(), meter_loops=False, source_scopes=False, source_dispatch=False, scalar_routines=False, shadowable_externals=(), value_services=(), constructor_profile=None, catalog_budget=False, bound_constructors=(),configuration_dispatch=False):
    if shadowable_externals and not (source_scopes and source_dispatch):
        raise ValueError('shadowable external names require a source scope')
    return compile_module(None,program,(),source_text,source_name,_exports=exports,owned=True,
                          module_names=module_names,external_names=external_names,
                          current_module=current_module,reference_names=reference_names,
                          meter_loops=meter_loops,retain_generated=retain_generated,source_scopes=source_scopes,source_dispatch=source_dispatch,scalar_routines=scalar_routines,
                          shadowable_externals=shadowable_externals,value_services=value_services,constructor_profile=constructor_profile,catalog_budget=catalog_budget,bound_constructors=bound_constructors,configuration_dispatch=configuration_dispatch)
