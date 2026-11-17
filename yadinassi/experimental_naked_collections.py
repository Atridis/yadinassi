"""BSL AST to Python compiler for direct-default and diagnostic repair profiles.

Production callers use an explicit trusted internal entry; standalone diagnostic
use requires environment opt-in. Host/context admission belongs to the caller.
Optional profiles include deliberately raw Python behavior; compatibility is
incomplete and this compiler alone is not an authority or sandbox boundary.
"""
import os
from dataclasses import dataclass, fields
from decimal import Decimal
from types import SimpleNamespace
from .syntax import ast
from .syntax.parser import parse
from .experimental_naked_boundaries import _HostMemberReference, _HostIndexReference, _MISSING

from .values import Reference as _CanonicalReference

def _canonical_reference(value):
    return _CanonicalReference(value.get,value.set)

def _host_name_reference(getter,setter,name):
    try:getter()
    except NameError:raise ValueError('Переменная или функция не определена: '+name) from None
    return _CanonicalReference(getter,setter)

def _host_omission_error():
    raise TypeError('Пропуск аргументов встроенных функций, методов и конструкторов пока не поддерживается')

ENV='YADINASSI_UNSAFE_COLLECTION_ABLATION'

def _enabled():
    if os.environ.get(ENV)!='1':
        raise RuntimeError('unsafe collection ablation requires '+ENV+'=1')

class UnsupportedNakedSyntax(Exception):pass

def _native_property_missing(name):
    raise ValueError('Метод или свойство не найдено: '+name)

def _native_property_write_missing(name):
    raise ValueError('Свойство недоступно для записи: '+name)

def _native_method_missing(receiver,name):
    kind=type(receiver)
    if kind is list:raise ValueError('Метод или свойство не найдено: '+name)
    if id(kind) in _MAP_TYPE_IDS:raise ValueError('Метод соответствия не найден: '+name)
    raise ValueError('Метод структуры не найден: '+name)

def _invalid_native_arity(message):
    raise TypeError(message)

def _argument_count_error(name,expected,actual):
    raise TypeError(f"{name} ожидает {expected} аргументов, получено {actual}")

def _procedure_value_error(name):
    raise TypeError("Процедура не возвращает значение: "+name)

def _routine_value_error(name):
    raise TypeError("Процедуру или функцию необходимо вызвать: "+name)

@dataclass(frozen=True)
class _MapEntry:
    """Internal read-only iterator pair, never a generic host-object exemption."""
    key: object
    value: object


_ALIASES={'добавить':'add','вставить':'insert','получить':'get','установить':'set',
          'удалить':'delete','очистить':'clear','количество':'count','найти':'find',
          'вграница':'ubound','свойство':'property'}

# Named, independently selectable repairs. These are experiment variants, NOT a
# restoration of the production admission/runtime pipeline. Each repair has a
# specific reproduced failure; incomplete global contracts remain explicit.
REPAIRS=frozenset(('typed_map_keys','array_index_contract','array_insert_shape','constructor_bounds','byref_routines','error_boundaries','service_boundaries','authority_checkpoints','bsl_truth','bsl_presentation','native_order','typed_find','structure_fields','method_values','dynamic_host_refs','resource_bounds','live_module_state'))

class _NakedMap(dict):
    """Map kind only, needed for valid missing-key reference outputs."""

class _TypedMap(dict):
    @staticmethod
    def token(key):
        if type(key) is Decimal or type(key) is bool or type(key) is str or key is None:
            return type(key),key
        return object,id(key)
    def __init__(self,*args):
        dict.__init__(self)
        if args:
            for key,value in dict(*args).items():self[key]=value
    def __setitem__(self,key,value):dict.__setitem__(self,self.token(key),(key,value))
    def __getitem__(self,key):return dict.__getitem__(self,self.token(key))[1]
    def __delitem__(self,key):dict.__delitem__(self,self.token(key))
    def __contains__(self,key):return dict.__contains__(self,self.token(key))
    def get(self,key,default=None):
        entry=dict.get(self,self.token(key));return default if entry is None else entry[1]
    def items(self):return iter(dict.values(self))

_MAP_TYPE_IDS=(id(_NakedMap),id(_TypedMap))

def _checked_array_index(obj,key):
    if type(key) is not Decimal:raise TypeError('Ожидается число')
    if key!=key.to_integral_value():raise ValueError('Ожидается целое число')
    if key<0 or key>=len(obj):raise IndexError(f'Индекс массива вне границ: {key}')
    return int(key)

def _array_set_checked(obj,key,value):
    # Ordinary Python argument binding evaluates value before bounds validation.
    obj[_checked_array_index(obj,key)]=value

def _array_set_raw(obj,key,value):
    obj[int(key)]=value

def _array_insert_shape(obj,key,value=None):
    if type(key) is not Decimal:raise TypeError('Ожидается число')
    if not key.is_finite() or key!=key.to_integral_value():raise ValueError('Ожидается целое число')
    if key<0:raise IndexError('Индекс массива вне границ')
    index=int(key)
    if index<len(obj):obj.insert(index,value)
    else:obj.extend([None]*(index-len(obj))+[value])

def _array_constructor_bounds(*sizes):
    if not sizes:return []
    for size in sizes:
        if type(size) is not Decimal:raise TypeError('Ожидается число')
        if not size.is_finite() or size!=size.to_integral_value():raise ValueError('Ожидается целое число')
        if size<0:raise ValueError('Размер массива не может быть отрицательным')
    def build(depth):
        return ([None]*int(sizes[depth]) if depth==len(sizes)-1 else
                [build(depth+1) for _ in range(int(sizes[depth]))])
    return build(0)

class _Reference:
    def get(self):return self.value
    def set(self,value):self.value=value

_UNSET_REF=object()

class _Cell(_Reference):
    __slots__=('_value',)
    def __init__(self,value=_UNSET_REF):self._value=value
    @property
    def value(self):
        if self._value is _UNSET_REF:raise NameError('Uninitialized reference')
        return self._value
    @value.setter
    def value(self,value):self._value=value

def _bound_ref(value):
    # Missing actuals fail before entering the callee, without reading index refs.
    if type(value) is _Cell and value._value is _UNSET_REF:
        raise NameError('Uninitialized reference')
    return value

class _IndexRef(_Reference):
    __slots__=('owner','key','checked')
    def __init__(self,owner,key,checked=False):
        self.owner,self.key,self.checked=owner,key,checked
        self.value  # Argument binding validates before callee effects.
    def index(self):
        if isinstance(self.owner,list):
            return _checked_array_index(self.owner,self.key) if self.checked else int(self.key)
        return self.key
    @property
    def value(self):
        if id(type(self.owner)) in _MAP_TYPE_IDS:return self.owner.get(self.key)
        if type(self.owner) is dict and self.key not in self.owner:raise ValueError('Свойство структуры не найдено: '+str(self.key))
        return self.owner[self.index()]
    @value.setter
    def value(self,value):
        if type(self.owner) is dict and self.key not in self.owner:raise ValueError('Свойство структуры не найдено: '+str(self.key))
        self.owner[self.index()]=value

class _AttributeRef(_Reference):
    __slots__=('owner','name')
    def __init__(self,owner,name):
        self.owner,self.name=owner,name
        self.value
    @property
    def value(self):
        if id(type(self.owner)) in _MAP_TYPE_IDS:return _native_property_missing(self.name)
        if isinstance(self.owner,dict):
            if self.name not in self.owner:raise ValueError('Свойство структуры не найдено: '+self.name)
            return self.owner[self.name]
        return getattr(self.owner,self.name.casefold())
    @value.setter
    def value(self,value):
        if id(type(self.owner)) in _MAP_TYPE_IDS:return _native_property_write_missing(self.name)
        if isinstance(self.owner,dict):
            if self.name not in self.owner:raise ValueError('Свойство структуры не найдено: '+self.name)
            self.owner[self.name]=value
        else:setattr(self.owner,self.name.casefold(),value)

def _as_ref(value):return value if isinstance(value,(_Reference,_HostMemberReference,_HostIndexReference)) else _Cell(value)
_OMITTED_REF=object()

def _property_output(receiver,key,output):
    found=key in receiver
    output.value=receiver[key] if found else None
    return found

@dataclass
class Program:
    generated_source: str
    constants: tuple
    function: object
    symbols: dict
    repairs: frozenset=frozenset()
    last_state: object=None
    output: object=None
    source_name: str="<naked-collection-experiment>"
    source_text: str=""
    required_services: tuple=()
    trusted_entry: bool=False

    def run(self,initial=None,*,context=None):
        if not self.trusted_entry:_enabled()
        if 'live_module_state' in self.repairs:
            from .experimental_naked_live_state import validate_state
            state=validate_state(initial)
        else:state={} if initial is None else {key.casefold():value for key,value in initial.items()}
        self.last_state=state;self.output=[]
        bounded=bool(self.repairs & {'service_boundaries','authority_checkpoints'})
        if bounded:
            if context is None:raise ValueError('explicit BoundaryContext required')
            context.enter()
        try:
            try:
                if bounded:return self.function(state,self.constants,self.output,context)
                return self.function(state,self.constants,self.output)
            finally:
                if bounded:
                    try:context._check()
                    finally:context.leave()
        except Exception as error:
            if 'error_boundaries' not in self.repairs:raise
            from .experimental_naked_errors import convert_error
            converted=convert_error(error,self.source_name,self.source_text)
            if converted is error:raise
            raise converted from None


def prepare(source,*,source_name='<naked-collection-experiment>',repairs=(),constructors=(),service_references=None,module_names=(),external_names=(),parsed_ast=None,_trusted_entry=False,_return_last_expression=False,_export_routines=False):
    # Internal trusted backend entry, not an environment mutation or sandbox grant.
    if type(_trusted_entry) is not bool:raise TypeError("trusted entry requires Boolean")
    if not _trusted_entry:_enabled()
    if isinstance(repairs,str):repairs=tuple(name for name in repairs.split(',') if name)
    repairs=frozenset(repairs)
    if 'resource_bounds' in repairs:
        repairs=repairs | {'constructor_bounds','array_insert_shape'}
    if not repairs<=REPAIRS:raise ValueError('unknown naked repairs: '+repr(repairs-REPAIRS))
    services='service_boundaries' in repairs;authority='authority_checkpoints' in repairs
    constructors=frozenset(name.casefold() for name in constructors)
    if constructors and not services:raise ValueError('declared constructors require service_boundaries')
    service_references={name.casefold():frozenset(indices) for name,indices in (service_references or {}).items()}
    if service_references and (not services or 'byref_routines' not in repairs):raise ValueError('service references require explicit byref and service repairs')
    if any(type(index) is not int or index<0 for indices in service_references.values() for index in indices):raise ValueError('invalid service reference index')
    scalar_ops=None
    if repairs & {'bsl_truth','bsl_presentation','native_order','typed_find'}:
        from . import experimental_naked_scalar_semantics as scalar_ops
    structure_ops=None
    if 'structure_fields' in repairs:
        from . import experimental_naked_structure as structure_ops
    required_services=set()
    program=parse(source,source_name) if parsed_ast is None else parsed_ast
    if _export_routines and any(type(node) not in (ast.Routine,ast.Var) for node in program):
        raise UnsupportedNakedSyntax('routine export requires a declaration-only module')
    symbols={};constants=[];serial=0;lines=[];loops=[]
    from .experimental_naked_errors import SourceMap, source_mapping_supported
    if 'error_boundaries' in repairs and not source_mapping_supported():
        raise UnsupportedNakedSyntax('error_boundaries requires Python code line metadata (3.10+)')
    source_map=SourceMap() if 'error_boundaries' in repairs else None
    byref='byref_routines' in repairs
    live='live_module_state' in repairs
    if type(external_names) is not tuple and type(external_names) is not list:raise TypeError('external names require a tuple or list')
    if external_names and not (live and services):raise ValueError('external names require live module state and service boundaries')
    if any(type(name) is not str for name in external_names):raise TypeError('external names require strings')
    external_keys=frozenset(name.casefold() for name in external_names)
    from .python_direct_definite import definite_module_reads
    definite_reads = definite_module_reads(program,opaque_names=external_keys) if live and not authority else frozenset()
    source_checks=authority or (services and not live)
    if live and not byref:raise ValueError('live_module_state requires byref_routines')
    if module_names and not live:raise ValueError('module_names requires live_module_state')
    if any(type(name) is not str for name in module_names):raise TypeError('module names require strings')
    predeclared={name.casefold() for name in module_names}
    dynamic_refs='dynamic_host_refs' in repairs
    if dynamic_refs and not (byref and services):raise ValueError('dynamic_host_refs requires byref_routines and service_boundaries')
    routines={node.name.casefold():node for node in program if type(node) is ast.Routine}
    function_symbols={name:'fn'+str(i) for i,name in enumerate(routines)}
    module_variables={name.casefold() for node in program if type(node) is ast.Var for name in node.names} | predeclared
    scope_id=None
    if external_keys & (module_variables|routines.keys()):raise UnsupportedNakedSyntax("external names collide with module declarations")
    routine_externals={}
    source_ref_slots={}
    cells={None:set()};routine_globals={}
    def walk(value):
        if isinstance(value,ast.Node):
            yield value
            for field in fields(value):
                if field.name!='token':yield from walk(getattr(value,field.name))
        elif isinstance(value,(list,tuple)):
            for item in value:yield from walk(item)
    def ungroup(node):
        while type(node) is ast.Group:node=node.expression
        return node
    if byref:
        for routine in routines.values():
            parameters={parameter.name.casefold() for parameter in routine.parameters}
            declarations={name.casefold() for node in walk(routine.body) if type(node) is ast.Var for name in node.names}
            routine_globals[id(routine)]=module_variables-parameters-declarations
            routine_externals[id(routine)]=external_keys-parameters-declarations
            cells[id(routine)]={parameter.name.casefold() for parameter in routine.parameters if not parameter.by_value}
        for current,body in [(None,[node for node in program if type(node) is not ast.Routine]),*((id(routine),routine.body) for routine in routines.values())]:
            for node in walk(body):
                if type(node) is not ast.Call:continue
                callee=ungroup(node.callee)
                actuals=[]
                if type(callee) is ast.Name and callee.name.casefold() in routines:
                    routine=routines[callee.name.casefold()]
                    actuals=[arg for param,arg in zip(routine.parameters,node.arguments) if not param.by_value]
                elif type(callee) is ast.Name and callee.name.casefold() in service_references:
                    actuals=[arg for index,arg in enumerate(node.arguments) if index in service_references[callee.name.casefold()]]
                elif type(callee) is ast.Attribute and _ALIASES.get(callee.name.casefold(),callee.name.casefold())=='property':
                    actuals=node.arguments[1:2]
                for arg in actuals:
                    arg=ungroup(arg)
                    if type(arg) is ast.Name:
                        destination=None if arg.name.casefold() in routine_globals.get(current,()) else current
                        cells[destination].add(arg.name.casefold())
    lexical={key:set() for key in cells}
    if dynamic_refs:
        for current,body in [(None,[n for n in program if type(n) is not ast.Routine]),*((id(r),r.body) for r in routines.values())]:
            for node in walk(body):
                if type(node) is not ast.Call:continue
                callee=ungroup(node.callee)
                if type(callee) is ast.Attribute:continue
                if type(callee) is ast.Name and callee.name.casefold() in routines:continue
                for arg in node.arguments:
                    arg=ungroup(arg)
                    if type(arg) is ast.Name:
                        destination=None if arg.name.casefold() in routine_globals.get(current,()) else current
                        lexical[destination].add(arg.name.casefold())
    from .python_direct_arrays import array_facts
    array_receivers,array_indexes=frozenset(),frozenset()
    if live and not authority and not constructors.intersection(('array','массив')) and 'array_index_contract' in repairs:
        routine_array_opaque={id(r):routine_globals.get(id(r),set())|routine_externals.get(id(r),set())|
                             {p.name.casefold() for p in r.parameters if not p.by_value}
                             for r in routines.values()}
        array_definite_reads=set()
        array_receivers,array_indexes=array_facts(program,opaque_names=external_keys,routine_opaque=routine_array_opaque,
                                                  definite_reads=array_definite_reads)
        definite_reads=definite_reads|array_definite_reads
    # Raw diagnostic profiles return Python int from Count, which the existing
    # checked-index contract rejects. Do not silently repair that mismatch.
    if not repairs & {'bsl_truth','bsl_presentation','native_order','typed_find'}:array_indexes=frozenset()
    routine_locals={id(r):{p.name.casefold() for p in r.parameters}|{name.casefold() for n in r.body if type(n) is ast.Var for name in n.names} for r in routines.values()}
    if live:
        for r in routines.values():
            direct_vars={id(n) for n in r.body if type(n) is ast.Var}
            for n in walk(r.body):
                if type(n) is ast.Var and id(n) not in direct_vars and any(name.casefold() in module_variables|external_keys|{'thisobject','этотобъект'} for name in n.names):
                    raise UnsupportedNakedSyntax('conditional local Var shadowing module storage is unsupported')
    def external_name(name):
        return name.casefold() in (external_keys if scope_id is None else routine_externals.get(scope_id,()))
    def module_name(name):
        return live and (scope_id is None or name.casefold() in routine_globals.get(scope_id,()))
    def boxed(name):
        key=name.casefold()
        return byref and (key in cells[scope_id] or (key in routine_globals.get(scope_id,()) and key in cells[None]))
    def sym(name):
        key=name.casefold()
        if key not in symbols:symbols[key]='v'+str(len(symbols))
        return symbols[key]
    def temp():
        nonlocal serial
        serial+=1;return 't'+str(serial)
    def emit(depth,text):
        if source_map is not None:source_map.line(len(lines)+1)
        lines.append('    '*depth+text)
    def literal(value):
        constants.append(value);return '_constants['+str(len(constants)-1)+']'
    def variable(name):
        if external_name(name):return '_context.external_get('+repr(name.casefold())+')'
        if module_name(name):return '_initial['+repr(name.casefold())+']'
        return sym(name)+('.value' if boxed(name) else '')
    def read_variable(name):
        if external_name(name):return variable(name)
        if not module_name(name):return variable(name)
        value=temp()
        return '('+value+' if ('+value+' := _initial.get('+repr(name.casefold())+', _LIVE_UNSET)) is not _LIVE_UNSET else _live_missing('+repr(name)+'))'
    def reserved_target(name):
        return live and name.casefold() in ('thisobject','этотобъект') and (module_name(name) or name.casefold() not in routine_locals.get(scope_id,set()))
    def assign_name(name,value,depth):
        if external_name(name):
            emit(depth,'_context.external_set('+repr(name.casefold())+', '+value+')');return
        if reserved_target(name):
            saved=temp();emit(depth,saved+' = '+value)
            if module_name(name):emit(depth,'if '+repr(name.casefold())+' not in _initial: _live_readonly('+repr(name.casefold())+')')
            else:emit(depth,'_live_readonly('+repr(name.casefold())+')')
            value=saved
        emit(depth,variable(name)+' = '+value)
    def reference(node):
        node=ungroup(node)
        if type(node) is ast.Name:
            if external_name(node.name):return '_context.external_reference('+repr(node.name.casefold())+')'
            if module_name(node.name):
                key=node.name.casefold()
                if key not in source_ref_slots:source_ref_slots[key]=temp()
                text='_live_source_ref(_initial, '+repr(node.name)+', '+source_ref_slots[key]+')'
                return source_map.expression(text,node) if source_map is not None else text
            return '_bound_ref('+sym(node.name)+')'
        if type(node) is ast.Index:
            obj=expression(node.object);index=expression(node.index)
            if services:
                receiver=temp()
                return '(_IndexRef('+receiver+', '+index+', '+repr('array_index_contract' in repairs)+') if id(type(('+receiver+' := '+obj+'))) in _NATIVE_COLLECTION_IDS else _context.reference_index('+receiver+', '+index+'))'
            return '_IndexRef('+obj+', '+index+', '+repr('array_index_contract' in repairs)+')'
        if type(node) is ast.Attribute:
            obj=expression(node.object)
            if services:
                receiver=temp()
                return '(_AttributeRef('+receiver+', '+repr(node.name)+') if id(type(('+receiver+' := '+obj+'))) in _NATIVE_DICT_IDS else _context.reference_member('+receiver+', '+repr(node.name)+'))'
            return '_AttributeRef('+obj+', '+repr(node.name)+')'
        return '_Cell('+expression(node)+')'
    def lexical_helpers(current,depth):
        for name in sorted(lexical[current]):
            if external_name(name):continue
            if live and current is None:continue
            slot=sym(name)
            is_box=name in cells[current]
            target=slot+('.value' if is_box else '')
            if not is_box:emit(depth,'if False: '+slot+' = None')
            emit(depth,'def get_'+slot+'(): return '+target)
            emit(depth,'def set_'+slot+'(_new):')
            if not is_box:emit(depth+1,'nonlocal '+slot)
            emit(depth+1,target+' = _new')
    def host_reference(node):
        node=ungroup(node)
        if type(node) is ast.Name:
            if external_name(node.name):return '_context.external_reference('+repr(node.name.casefold())+')'
            if module_name(node.name):
                text='_live_host_ref(_initial, '+repr(node.name)+')'
                return source_map.expression(text,node) if source_map is not None else text
            slot=sym(node.name)
            text='_host_name_reference(get_'+slot+', set_'+slot+', '+repr(node.name)+')'
            return source_map.expression(text,node) if source_map is not None else text
        if type(node) is ast.Index or type(node) is ast.Attribute:
            return '_canonical_reference('+reference(node)+')'
        return expression(node)
    def dynamic_call(bound,node):
        token=temp()
        if any(type(arg) is ast.OmittedArgument for arg in node.arguments):
            return '(('+token+' := '+bound+'), _host_omission_error())[-1]'
        arguments=[]
        for index,arg in enumerate(node.arguments):
            arguments.append('('+host_reference(arg)+' if '+token+'.requires_reference('+str(index)+') else '+expression(arg)+')')
        return '(('+token+' := '+bound+'), '+token+'('+', '.join(arguments)+'))[-1]'
    def truth_expression(node):
        value=expression(node)
        if 'bsl_truth' not in repairs:return value
        if type(node) is ast.Literal and type(node.value) is bool:return value
        if type(node) is ast.Literal and type(node.value) is Decimal:return literal(node.value!=0)
        return '_bsl_truth('+value+')'
    def _expression(node,require_value=True):
        kind=type(node)
        if kind is ast.Literal:return literal(node.value)
        if kind is ast.Name:
            value=(variable(node.name) if scope_id is None and id(node) in definite_reads else read_variable(node.name))
            if node.name.casefold() in routines:
                presence=(repr(node.name.casefold())+' in _initial' if module_name(node.name) else repr(sym(node.name))+' in locals()')
                return '('+value+' if '+presence+' else _routine_value_error('+repr(node.name)+'))'
            return value
        if kind is ast.Group:return '('+expression(node.expression,require_value)+')'
        if kind is ast.Unary:
            if node.operator=='NOT' and 'bsl_truth' in repairs:return '(not '+truth_expression(node.operand)+')'
            return '('+('not ' if node.operator=='NOT' else node.operator)+expression(node.operand)+')'
        if kind is ast.Binary:
            if node.operator in ('AND','OR') and 'bsl_truth' in repairs:
                return '('+truth_expression(node.left)+(' and ' if node.operator=='AND' else ' or ')+truth_expression(node.right)+')'
            if node.operator=='+' and 'bsl_presentation' in repairs:
                if type(node.left) is ast.Literal and type(node.right) is ast.Literal and type(node.left.value) is str:
                    return literal(scalar_ops.concatenate(node.left.value,node.right.value))
                left=expression(node.left);right=expression(node.right)
                if type(node.left) is ast.Literal and type(node.left.value) is not str:return '('+left+' + '+right+')'
                captured=temp()
                return '(_bsl_concatenate('+captured+', '+right+') if type(('+captured+' := '+left+')) is str else '+captured+' + '+right+')'
            if node.operator in ('<','<=','>','>=') and 'native_order' in repairs:
                if type(node.left) is ast.Literal and type(node.right) is ast.Literal and type(node.left.value) is str and type(node.right.value) is str:
                    return literal(scalar_ops.order(node.left.value,node.right.value,node.operator))
                return '_native_order('+expression(node.left)+', '+expression(node.right)+', '+repr(node.operator)+')'
            operator={'=':'==','<>':'!=','AND':'and','OR':'or'}.get(node.operator,node.operator)
            return '('+expression(node.left)+' '+operator+' '+expression(node.right)+')'
        if kind is ast.Conditional:
            return '('+expression(node.when_true)+' if '+truth_expression(node.condition)+' else '+expression(node.when_false)+')'
        if kind is ast.New:
            args=[expression(arg) for arg in node.arguments];kindname=node.name.casefold()
            if services and kindname in constructors:
                required_services.add('new:'+kindname)
                return '_context.resolve_service('+repr('new:'+kindname)+')('+', '.join(args)+')'
            if kindname in ('array','массив'):
                if 'constructor_bounds' in repairs:return '_array_constructor_bounds('+', '.join(args)+')'
                if not args:return '[]'
                if len(args)==1:return '([None] * int('+args[0]+'))'
                dims=temp();shape='[None] * int('+dims+'['+str(len(args)-1)+'])'
                for dimension in reversed(range(len(args)-1)):
                    shape='['+shape+' for _ in range(int('+dims+'['+str(dimension)+']))]'
                return '(('+dims+' := ('+', '.join(args)+')), '+shape+')[1]'
            if kindname in ('map','соответствие'):return ('_TypedMap' if 'typed_map_keys' in repairs else '_NakedMap' if byref or 'bsl_presentation' in repairs else 'dict')+'('+', '.join(args)+')'
            if kindname in ('structure','структура'):
                if structure_ops is not None:
                    keys=ungroup(node.arguments[0]) if args else None
                    if keys is None or type(keys) is ast.Literal and type(keys.value) is str:
                        try:schema=structure_ops.prepare_structure_schema('' if keys is None else keys.value)
                        except ValueError:pass  # Invalid fields must fail after argument effects.
                        else:
                            return '_structure_from_schema('+literal(schema)+('' if not args[1:] else ', '+', '.join(args[1:]))+')'
                    return '_new_structure('+', '.join(args)+')'
                if not args:return '{}'
                values=temp()
                return '(('+values+' := ('+', '.join(args)+',)), {key: '+values+'[idx+1] if idx+1<len('+values+') else None for idx,key in enumerate('+values+'[0].split(","))})[1]'
            raise UnsupportedNakedSyntax('constructor '+node.name)
        if kind is ast.Index:
            if id(node) in array_receivers:
                obj=expression(node.object);index=expression(node.index)
                if id(node) in array_indexes:return '('+obj+')[int('+index+')]'
                receiver=temp()
                return '(('+receiver+' := '+obj+'), '+receiver+'[_checked_array_index('+receiver+', '+index+')])[1]'
            receiver=temp();index=expression(node.index)
            list_read=receiver+'['+('_checked_array_index('+receiver+', '+index+')' if 'array_index_contract' in repairs else 'int('+index+')')+']'
            other='('+receiver+'.get('+index+') if id(type('+receiver+')) in _MAP_TYPE_IDS else '+receiver+'['+index+'])'
            if services:
                obj=expression(node.object)
                native='('+list_read+' if type('+receiver+') is list else '+other+')'
                return '('+native+' if id(type(('+receiver+' := '+obj+'))) in _NATIVE_COLLECTION_IDS else _context.resolve_member('+receiver+', "__getitem__")('+index+'))'
            return '('+list_read+' if isinstance(('+receiver+' := '+expression(node.object)+'),list) else '+other+')'
        if kind is ast.Attribute:
            receiver=temp()
            if services:
                host='(_native_property_missing('+repr(node.name)+') if id(type('+receiver+')) in _MAP_TYPE_IDS else _context.get_member('+receiver+', '+repr(node.name)+'))'
                field={'key':'key','ключ':'key','value':'value','значение':'value'}.get(node.name.casefold())
                if field is not None:host='('+receiver+'.'+field+' if type('+receiver+') is _MapEntry else '+host+')'
                if 'method_values' in repairs:host='(_array_method_value('+receiver+', '+repr(node.name)+') if type('+receiver+') is list else '+host+')'
                if structure_ops is not None:host='(_structure_get_known('+receiver+', '+repr(node.name.casefold())+', '+repr(node.name)+') if type('+receiver+') is _DirectStructure else '+host+')'
                return '('+receiver+'['+repr(node.name)+'] if type(('+receiver+' := '+expression(node.object)+')) is dict else '+host+')'
            fallback='(_native_property_missing('+repr(node.name)+') if id(type('+receiver+')) in _MAP_TYPE_IDS else getattr('+receiver+','+repr(node.name.casefold())+'))'
            if 'method_values' in repairs:fallback='(_array_method_value('+receiver+', '+repr(node.name)+') if type('+receiver+') is list else '+fallback+')'
            return '('+receiver+'['+repr(node.name)+'] if isinstance(('+receiver+' := '+expression(node.object)+'),dict) and id(type('+receiver+')) not in _MAP_TYPE_IDS else '+fallback+')'
        if kind is ast.Call:
            callee=ungroup(node.callee)
            if type(callee) is ast.Attribute:
                obj=expression(callee.object);method=_ALIASES.get(callee.name.casefold(),callee.name.casefold())
                args=[expression(arg) for arg in node.arguments]
                if id(node) in array_receivers:
                    if method=='add':return '('+obj+').append('+(', '.join(args) if args else 'None')+')'
                    if method=='clear':return '('+obj+').clear()'
                    if method in ('count','ubound'):
                        value='len('+obj+')'+(' - 1' if method=='ubound' else '')
                        return 'Decimal('+value+')' if repairs & {'bsl_truth','bsl_presentation','native_order','typed_find'} else '('+value+')'
                    if method=='get':
                        if id(node) in array_indexes:return '('+obj+')[int('+args[0]+')]'
                        receiver=temp()
                        return '(('+receiver+' := '+obj+'), '+receiver+'[_checked_array_index('+receiver+', '+args[0]+')])[1]'
                original_obj=obj;guarded=temp() if services or structure_ops is not None else None
                if guarded is not None:obj=guarded
                allowed={'add':(list,), 'get':(list,_TypedMap,_NakedMap),'set':(list,), 'find':(list,), 'ubound':(list,), 'property':((structure_ops._DirectStructure,) if structure_ops is not None else (dict,))}.get(method)
                def route(direct):
                    if guarded is None:return direct
                    host_args=list(args)
                    if services and method=='property' and len(args)>1 and byref:host_args[1]='_canonical_reference('+reference(node.arguments[1])+')'
                    host=('_context.resolve_member('+guarded+', '+repr(callee.name)+')' if services else 'getattr('+guarded+', '+repr(callee.name.casefold())+')')+'('+', '.join(host_args)+')'
                    if allowed is not None:
                        failure='_native_method_missing('+guarded+', '+repr(callee.name)+')'
                        return '('+direct+' if id(type(('+guarded+' := '+original_obj+'))) in '+literal(tuple(map(id,allowed)))+' else ('+failure+' if id(type('+guarded+')) in _NATIVE_COLLECTION_IDS else '+host+'))'
                    return '('+direct+' if id(type(('+guarded+' := '+original_obj+'))) in _NATIVE_COLLECTION_IDS else '+host+')'
                bounds={'add':(0,1),'get':(1,1),'set':(2,2),'insert':(1,2),'delete':(1,1),'count':(0,0),'ubound':(0,0),'find':(1,1),'property':(1,2)}
                if method in bounds and not bounds[method][0]<=len(args)<=bounds[method][1]:
                    minimum,maximum=bounds[method]
                    expected=str(minimum) if minimum==maximum else str(minimum)+'..'+str(maximum)
                    message=callee.name+' ожидает '+expected+' аргументов, получено '+str(len(args))
                    # Invalid-only sequence: receiver, every argument, then error.
                    # Exact native/Python implementation names are not reproduced.
                    return route('('+', '.join([obj,*args,'_invalid_native_arity('+repr(message)+')'])+')[-1]')
                if services and method not in ('add','clear','find','count','ubound','get','insert','set','delete','property'):
                    host='_context.resolve_member('+guarded+', '+repr(callee.name)+')('+', '.join(args)+')'
                    return '(_native_method_missing('+guarded+', '+repr(callee.name)+') if id(type(('+guarded+' := '+original_obj+'))) in _NATIVE_COLLECTION_IDS else '+host+')'
                if method=='find' and 'typed_find' in repairs:return route('_typed_find('+obj+', '+', '.join(args)+')')
                if method in ('add','clear','find'):
                    native_args=['None'] if method=='add' and not args else args
                    target={'add':'append','clear':'clear','find':'index'}[method]
                    return route('('+obj+').'+target+'('+', '.join(native_args)+')')
                if method in ('count','ubound') and not args:
                    count='(len('+obj+')'+(' - 1' if method=='ubound' else '')+')'
                    if repairs & {'bsl_truth','bsl_presentation','native_order','typed_find'}:count='Decimal('+count+')'
                    return route(count)
                if method in ('get','insert','set','delete'):
                    receiver=temp();key=args[0] if args else 'None'
                    if method=='get':
                        yes=receiver+'['+('_checked_array_index('+receiver+', '+key+')' if 'array_index_contract' in repairs else 'int('+key+')')+']';no=receiver+'.get('+', '.join(args)+')'
                    elif method=='delete':
                        yes=receiver+'.__delitem__('+('_checked_array_index('+receiver+', '+key+')' if 'array_index_contract' in repairs else 'int('+key+')')+')';no=receiver+'.__delitem__('+key+')'
                    else:
                        value=args[1] if len(args)>1 else 'None'
                        if method=='insert' and 'array_insert_shape' in repairs:
                            yes='_array_insert_shape('+receiver+', '+key+', '+value+')'
                        else:
                            index=('_checked_array_index('+receiver+', '+key+')' if method=='set' and 'array_index_contract' in repairs else 'int('+key+')')
                            yes=receiver+('.insert' if method=='insert' else '.__setitem__')+'('+index+', '+value+')'
                            if method=='set':yes=('_array_set_checked' if 'array_index_contract' in repairs else '_array_set_raw')+'('+receiver+', '+key+', '+value+')'
                        no=receiver+'.__setitem__('+key+', '+value+')'
                        if method=='insert' and structure_ops is not None:no='(_structure_insert('+receiver+', '+key+', '+value+') if type('+receiver+') is _DirectStructure else '+no+')'
                    return route('('+yes+' if isinstance(('+receiver+' := '+obj+'),list) else '+no+')')
                if method=='property' and structure_ops is not None:
                    receiver=temp();actuals=[args[0]] if args else []
                    if len(args)>1:actuals.append(reference(node.arguments[1]) if byref else args[1])
                    actuals.extend(args[2:])
                    return route('_structure_property('+obj+(', ' if actuals else '')+', '.join(actuals)+')')
                if method=='property' and len(args)>1 and byref:
                    return route('_property_output('+obj+', '+args[0]+', '+reference(node.arguments[1])+''.join(', '+arg for arg in args[2:])+')')
                if method=='property' and args:
                    receiver=temp();key=temp()
                    values=['('+receiver+' := '+obj+')','('+key+' := '+args[0]+')',*args[1:],key+' in '+receiver]
                    return route('('+', '.join(values)+')[-1]')
                return route('('+obj+').'+method+'('+', '.join(args)+')')
            if type(callee) is ast.Name and callee.name.casefold() in routines and require_value and not routines[callee.name.casefold()].is_function:
                return '_procedure_value_error('+repr(callee.name)+')'
            if type(callee) is ast.Name and callee.name.casefold() in routines:
                routine=routines[callee.name.casefold()]
                required=max((index+1 for index,parameter in enumerate(routine.parameters) if parameter.default is None),default=0)
                if not required<=len(node.arguments)<=len(routine.parameters):
                    return '_argument_count_error('+repr(routine.name)+', '+str(len(routine.parameters))+', '+str(len(node.arguments))+')'
            if byref and type(callee) is ast.Name and callee.name.casefold() in routines:
                routine=routines[callee.name.casefold()];args=[]
                for index,arg in enumerate(node.arguments):
                    if type(arg) is ast.OmittedArgument:args.append('_OMITTED_REF')
                    elif index<len(routine.parameters) and not routine.parameters[index].by_value:args.append(reference(arg))
                    else:args.append(expression(arg))
                function=function_symbols[callee.name.casefold()]
                if source_checks:function='(_context._check(), '+function+')[-1]'
                return function+'('+', '.join(args)+')'
            if source_checks and type(callee) is ast.Name and callee.name.casefold() in routines:
                return '(_context._check(), '+function_symbols[callee.name.casefold()]+')[-1]('+', '.join(expression(arg) for arg in node.arguments)+')'
            if type(callee) is ast.Name and callee.name.casefold() in routines:
                return function_symbols[callee.name.casefold()]+'('+', '.join(expression(arg) for arg in node.arguments)+')'
            if services and type(callee) is ast.Name and callee.name.casefold() not in routines:
                if external_name(callee.name):raise UnsupportedNakedSyntax('external namespace names are not callable: '+callee.name)
                required_services.add(callee.name.casefold())
                fallback=('_initial.get('+repr(callee.name.casefold())+', _MISSING)' if module_name(callee.name) else '('+variable(callee.name)+' if '+repr(sym(callee.name))+' in locals() else _MISSING)')
                if dynamic_refs and callee.name.casefold() not in service_references:
                    return dynamic_call('_context.resolve_service('+repr(callee.name.casefold())+', '+fallback+', require_value='+repr(require_value)+', allow_references=True)',node)
                return '_context.resolve_service('+repr(callee.name.casefold())+', '+fallback+', require_value='+repr(require_value)+')('+', '.join(reference(arg) if index in service_references.get(callee.name.casefold(),()) else expression(arg) for index,arg in enumerate(node.arguments))+')'
            if services and dynamic_refs:return dynamic_call('_context.resolve_callable('+expression(callee)+', require_value='+repr(require_value)+', allow_references=True)',node)
            if services:return '_context.resolve_callable('+expression(callee)+', require_value='+repr(require_value)+')('+', '.join(expression(arg) for arg in node.arguments)+')'
            return expression(callee)+'('+', '.join(expression(arg) for arg in node.arguments)+')'
        if kind is ast.OmittedArgument:return 'None'
        raise UnsupportedNakedSyntax('expression '+kind.__name__)
    def expression(node,require_value=True):
        text=_expression(node,require_value)
        return source_map.expression(text,node) if source_map is not None else text
    def statement(node,depth):
        if source_map is None:return _statement(node,depth)
        source_map.enter(node)
        try:return _statement(node,depth)
        finally:source_map.leave()
    def sequence(block,depth):
        if not block:emit(depth,'pass')
        for node in block:statement(node,depth)
    module_variables={name.casefold() for node in program if type(node) is ast.Var for name in node.names} | predeclared
    def _statement(node,depth):
        nonlocal scope_id
        kind=type(node)
        if kind is ast.Assign:
            value=expression(node.value);target=node.target
            if type(target) is ast.Name:assign_name(target.name,value,depth)
            elif type(target) is ast.Index:
                receiver=temp();index=temp();stored=temp()
                emit(depth,receiver+' = '+expression(target.object))
                writer=temp() if services else None
                if services:emit(depth,writer+' = None if id(type('+receiver+')) in _NATIVE_COLLECTION_IDS else _context.resolve_member('+receiver+', "__setitem__")')
                emit(depth,index+' = '+expression(target.index));emit(depth,stored+' = '+value)
                position=('_checked_array_index('+receiver+', '+index+')' if 'array_index_contract' in repairs else 'int('+index+')')
                if services:
                    emit(depth,'if '+writer+' is not None: '+writer+'('+index+', '+stored+')')
                    emit(depth,'else: '+receiver+'['+position+' if type('+receiver+') is list else '+index+'] = '+stored)
                else:emit(depth,receiver+'['+position+' if isinstance('+receiver+',list) else '+index+'] = '+stored)
            elif type(target) is ast.Attribute:
                receiver=temp();stored=temp();emit(depth,receiver+' = '+expression(target.object))
                writer=temp() if services else None
                if services:emit(depth,writer+' = None if id(type('+receiver+')) in _NATIVE_DICT_IDS else _context.resolve_set_member('+receiver+', '+repr(target.name)+')')
                emit(depth,stored+' = '+value)
                if services:
                    emit(depth,'if id(type('+receiver+')) in _MAP_TYPE_IDS: _native_property_write_missing('+repr(target.name)+')')
                    emit(depth,'elif '+writer+' is None: '+receiver+'['+repr(target.name)+'] = '+stored)
                    emit(depth,'else: '+writer+'('+stored+')')
                else:
                    emit(depth,'if id(type('+receiver+')) in _MAP_TYPE_IDS: _native_property_write_missing('+repr(target.name)+')')
                    emit(depth,'elif isinstance('+receiver+',dict): '+receiver+'['+repr(target.name)+'] = '+stored)
                    emit(depth,'else: setattr('+receiver+','+repr(target.name.casefold())+','+stored+')')
            else:raise UnsupportedNakedSyntax('assignment target')
        elif kind is ast.Var:
            for name in node.names:
                slot=sym(name)
                if module_name(name):emit(depth,'_initial.setdefault('+repr(name.casefold())+', None)')
                elif boxed(name):emit(depth,f'if {slot}._value is _UNSET_REF: {slot}.value = None')
                else:emit(depth,f'if {slot!r} not in locals(): {slot} = None')
        elif kind is ast.ExpressionStatement:
            prefix='return ' if _return_last_expression and scope_id is None and node is program[-1] else ''
            emit(depth,prefix+expression(node.expression,False))
        elif kind is ast.Return:emit(depth,'return '+(expression(node.value) if node.value is not None else 'None'))
        elif kind is ast.If:
            for index,(condition,block) in enumerate(node.branches):
                emit(depth,('if ' if index==0 else 'elif ')+truth_expression(condition)+':');sequence(block,depth+1)
            if node.otherwise:emit(depth,'else:');sequence(node.otherwise,depth+1)
        elif kind is ast.For:
            counter=variable(node.name);last=temp()
            if live:
                first=temp();emit(depth,first+' = '+expression(node.start));emit(depth,last+' = '+expression(node.end));assign_name(node.name,first,depth)
            else:emit(depth,counter+' = '+expression(node.start));emit(depth,last+' = '+expression(node.end))
            proven_counter = scope_id is None and id(node) in definite_reads
            condition=read_variable(node.name) if live and not proven_counter else counter
            if authority:
                emit(depth,'while True:');emit(depth+1,'_context.checkpoint()')
                emit(depth+1,f'if not ({condition} <= {last}): break')
            else:emit(depth,f'while {condition} <= {last}:')
            if external_name(node.name):increment='_context.external_set('+repr(node.name.casefold())+', '+read_variable(node.name)+' + 1)'
            else:increment=counter+' = '+(counter if proven_counter else read_variable(node.name))+' + 1' if module_name(node.name) else counter+' += 1'
            loops.append(increment);sequence(node.body,depth+1);loops.pop();emit(depth+1,increment)
        elif kind is ast.While:
            if authority:
                emit(depth,'while True:');emit(depth+1,'_context.checkpoint()')
                emit(depth+1,'if not ('+truth_expression(node.condition)+'): break')
            else:emit(depth,'while '+truth_expression(node.condition)+':')
            loops.append(None);sequence(node.body,depth+1);loops.pop()
        elif kind is ast.ForEach:
            loop_target=temp() if reserved_target(node.name) or external_name(node.name) else variable(node.name)
            receiver=temp();emit(depth,receiver+' = '+expression(node.collection))
            entry='_MapEntry' if services else 'SimpleNamespace'
            iterable='(('+entry+'(key=k,value=v) for k,v in '+receiver+'.items()) if isinstance('+receiver+',dict) else '+receiver+')'
            if services:
                bound=temp();emit(depth,bound+' = iter('+iterable+') if id(type('+receiver+')) in _NATIVE_COLLECTION_IDS else _context.resolve_member('+receiver+', "__iter__")()');iterable=bound
            if authority or source_map is not None:
                iterator=temp();emit(depth,iterator+' = iter('+iterable+')')
                emit(depth,'while True:')
                if authority:emit(depth+1,'_context.checkpoint()')
                emit(depth+1,'try: '+loop_target+' = next('+iterator+')')
                emit(depth+1,'except StopIteration: break')
                if source_map is not None:
                    emit(depth+1,'except RuntimeError:')
                    emit(depth+2,'if id(type('+receiver+')) not in _MAP_TYPE_IDS: raise')
                    emit(depth+2,'raise ValueError("Изменение состава соответствия во время обхода пока не поддерживается") from None')
            else:emit(depth,'for '+loop_target+' in '+iterable+':')
            if reserved_target(node.name) or external_name(node.name):assign_name(node.name,loop_target,depth+1)
            loops.append(None);sequence(node.body,depth+1);loops.pop()
        elif kind is ast.Break:emit(depth,'break')
        elif kind is ast.Continue:
            if loops and loops[-1] is not None:emit(depth,loops[-1])
            emit(depth,'continue')
        elif kind is ast.Try:
            emit(depth,'try:');sequence(node.body,depth+1)
            emit(depth,'except (ArithmeticError,ValueError,TypeError,IndexError,RecursionError,_BSLRuntimeError):' if source_map is not None else 'except Exception:');sequence(node.handler,depth+1)
        elif kind is ast.Raise:
            if source_map is not None and node.value is not None:
                emit(depth,f'raise _BSLRuntimeError(str({expression(node.value)}), {source_name!r}, {node.token.line}, {node.token.column})')
            else:emit(depth,'raise'+(' RuntimeError('+expression(node.value)+')' if node.value is not None else ''))
        elif kind is ast.Routine:
            if byref:
                parameters=[sym(parameter.name)+('=_OMITTED_REF' if parameter.default is not None else '') for parameter in node.parameters]
            else:parameters=[sym(parameter.name)+('='+expression(parameter.default) if parameter.default is not None else '') for parameter in node.parameters]
            emit(depth,'def '+function_symbols[node.name.casefold()]+'('+', '.join(parameters)+'):')
            nonlocals=(routine_globals[id(node)] if byref else module_variables-{p.name.casefold() for p in node.parameters})
            if nonlocals and not live:emit(depth+1,'nonlocal '+', '.join(sym(name) for name in sorted(nonlocals)))
            if source_checks:
                emit(depth+1,'_context._check()');emit(depth+1,'try:')
            body_depth=depth+2 if source_checks else depth+1
            previous_scope=scope_id
            if byref:
                scope_id=id(node)
                for parameter in node.parameters:
                    slot=sym(parameter.name)
                    fallback=expression(parameter.default) if parameter.default is not None else 'None'
                    emit(body_depth,f'if {slot} is _OMITTED_REF: {slot} = {fallback}')
                    if parameter.name.casefold() in cells[scope_id]:
                        emit(body_depth,slot+' = '+('_Cell' if parameter.by_value else '_as_ref')+'('+slot+')')
                for key in sorted(cells[scope_id]-{parameter.name.casefold() for parameter in node.parameters}):
                    emit(body_depth,sym(key)+' = _Cell()')
            if dynamic_refs:lexical_helpers(id(node),body_depth)
            saved=loops[:];loops.clear();sequence(node.body,body_depth);loops[:]=saved;scope_id=previous_scope
            if source_checks:
                emit(depth+1,'finally:');emit(depth+2,'_context._check()')
        else:raise UnsupportedNakedSyntax('statement '+kind.__name__)
    root_depth=1 if live else 2
    if dynamic_refs:lexical_helpers(None,root_depth)
    # Emit declarations first: BSL routines are available before textual calls.
    sequence([node for node in program if type(node) is ast.Routine],root_depth)
    sequence([node for node in program if type(node) is not ast.Routine],root_depth)
    body=lines;lines=[]
    builtin_names={'message':'_outputs.append','сообщить':'_outputs.append','string':'str','строка':'str',
                   'number':'Decimal','число':'Decimal','typeof':'type','типзнч':'type',
                   'boolean':'bool','булево':'bool'}
    emit(0,'def naked_module(_initial, _constants, _outputs'+(', _context' if services or authority else '')+'):')
    if live:
        for key,slot in source_ref_slots.items():emit(1,slot+' = _live_slot_ref(_initial, '+repr(key)+')')
        for name in sorted(module_variables):emit(1,'_initial.setdefault('+repr(name)+', None)')
    for name,slot in symbols.items():
        if live:continue
        if name in builtin_names:emit(1,slot+' = '+builtin_names[name])
        if byref and name in cells[None]:emit(1,f'{slot} = _Cell(_initial.get({name!r}, _UNSET_REF))')
        else:emit(1,f'if {name!r} in _initial: {slot} = _initial[{name!r}]')
    if not live:emit(1,'try:')
    body_offset=len(lines);lines.extend(body)
    if not live:
        emit(1,'finally:')
        emit(2,'_locals = locals()')
    for name,slot in symbols.items():
        if live:continue
        output=f'_locals[{slot!r}]'+('.value' if byref and name in cells[None] else '')
        condition=f'{slot!r} in _locals'
        if byref and name in cells[None]:condition+=f' and _locals[{slot!r}]._value is not _UNSET_REF'
        emit(2,f'if {condition}: _initial[{name!r}] = {output}')
    if _export_routines:
        emit(1,'return {'+', '.join(repr(name)+': '+symbol for name,symbol in function_symbols.items())+'}')
    else:emit(1,'return _initial')
    generated='\n'.join(lines)+'\n'
    namespace={name:value for name,value in globals().items() if name.startswith('_')}
    if live:
        from . import experimental_naked_live_state as live_ops
        namespace.update(_live_slot_ref=live_ops._SlotReference,_LIVE_UNSET=live_ops.UNSET,_live_missing=live_ops.missing,_live_readonly=live_ops.readonly,_live_source_ref=live_ops.source_reference,_live_host_ref=live_ops.host_reference)
    if 'resource_bounds' in repairs:
        from .experimental_naked_resources import bounded_array, bounded_insert
        namespace.update(_array_constructor_bounds=bounded_array,_array_insert_shape=bounded_insert)
    if scalar_ops is not None:namespace.update(_bsl_truth=scalar_ops.truth,_bsl_concatenate=scalar_ops.concatenate,_native_order=scalar_ops.order,_typed_find=scalar_ops.typed_find)
    native_dicts=(dict,_TypedMap,_NakedMap)
    if structure_ops is not None:
        native_dicts+= (structure_ops._DirectStructure,)
        namespace.update(_DirectStructure=structure_ops._DirectStructure,_new_structure=structure_ops.new_structure,_structure_from_schema=structure_ops.structure_from_schema,_structure_get_known=structure_ops.structure_get_known,_structure_insert=structure_ops.structure_insert,_structure_property=structure_ops.structure_property)
    if 'method_values' in repairs:
        from .experimental_naked_array_methods import array_method_value
        index=_checked_array_index if 'array_index_contract' in repairs else lambda obj,key:int(key)
        insert=namespace['_array_insert_shape'] if 'array_insert_shape' in repairs else lambda obj,key,value=None:obj.insert(int(key),value)
        find=scalar_ops.typed_find if 'typed_find' in repairs else None
        namespace['_array_method_value']=lambda obj,name:array_method_value(obj,name,index=index,insert=insert,find=find,delete=lambda obj,key:obj.__delitem__(index(obj,key)))
    namespace.update(Decimal=Decimal,SimpleNamespace=SimpleNamespace,_NATIVE_COLLECTION_TYPES=(list,*native_dicts),_NATIVE_DICT_TYPES=native_dicts,_NATIVE_COLLECTION_IDS=tuple(map(id,(list,*native_dicts))),_NATIVE_DICT_IDS=tuple(map(id,native_dicts)))
    from .errors import BSLRuntimeError
    namespace['_BSLRuntimeError']=BSLRuntimeError
    code=source_map.compile(generated,source_name,body_offset) if source_map is not None else compile(generated,source_name,'exec')
    exec(code,namespace)
    return Program(generated,tuple(constants),namespace['naked_module'],dict(symbols),repairs,source_name=source_name,source_text=source,required_services=tuple(sorted(required_services)),trusted_entry=_trusted_entry)

compile_source=prepare

def execute(source,initial=None,*,repairs=()):return prepare(source,repairs=repairs).run(initial)
