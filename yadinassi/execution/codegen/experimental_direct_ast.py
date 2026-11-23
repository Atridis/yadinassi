"""Compile BSL directly to a compiler-owned Python AST.

Default execution compiles that AST before source effects. Explicit source
audit compares a genuine unparse/parse roundtrip with the emitted tree.
Neither lane falls back to another compiler, or retries a failed compile.
"""
import ast as py
from copy import deepcopy
import _operator as _OPERATOR_MODULE
from types import ModuleType as _ModuleType
from _operator import add as _NATIVE_ADD, getitem as _NATIVE_GETITEM
from functools import partial
from .experimental_naked_collections import _TypedMap, _NakedMap, _checked_array_index, _native_property_write_missing, _native_property_missing, _MapEntry, _array_insert_shape, _native_method_missing, _ALIASES, _canonical_reference, _IndexRef, _AttributeRef, _procedure_value_error, _routine_value_error, _argument_count_error, _OMITTED_REF, _Cell, _as_ref, _bound_ref, _UNSET_REF
from .experimental_naked_structure import _DirectStructure, structure_get_known, structure_set_known, structure_property
from .experimental_naked_array_methods import array_method_value
from yadinassi.execution.direct.python_direct_cells import host_reference as _native_host_reference
from yadinassi.execution.direct.python_direct_cells import NativeCell as _NativeCell,PublishedModuleCell as _PublishedModuleCell,adapt as _adapt_native_cell,reference as _native_cell_reference,fragment_binding as _native_fragment_binding
from yadinassi.execution.direct.python_direct_plain_array import PlainArray as _PlainArray
from .experimental_naked_resources import bounded_array,bounded_insert
from .experimental_naked_collections import _array_set_checked, _invalid_native_arity, _host_omission_error, _host_omission_values
from .experimental_naked_structure import prepare_structure_schema,new_structure,structure_from_schema,structure_insert
from decimal import Decimal
from yadinassi.syntax import ast as bsl
from .experimental_naked_collections import Program, _host_name_reference, _host_omission_values
from .experimental_naked_boundaries import BoundaryContext, _MISSING
from .experimental_naked_live_state import UNSET,missing,readonly,host_reference,source_reference,_SlotReference,_ForwardReference
from . import experimental_naked_scalar_semantics as scalar
from .experimental_naked_errors import handled_error,reraise_handled
from yadinassi.execution.direct.python_direct_error_info import raise_error, raise_arity_error
from yadinassi.execution.direct.python_direct_dynamic_new import construct as dynamic_construct
from yadinassi.execution.direct.python_direct_plain_map import plain_map, PlainMap
from yadinassi.collections.plain_value_list import (PlainValueList, PlainValueListItem, _FIELDS as _VALUE_LIST_ITEM_FIELDS,
    _METHODS as _VALUE_LIST_METHODS, _normalize_presentation, _normalize_check)
from yadinassi.execution.direct.python_direct_execute import execute_fragment, local_binding, local_exists
from yadinassi.execution.direct.python_direct_eval import bind_eval
from yadinassi.execution.direct.python_direct import REPAIRS,PythonDirectUnsupported
from yadinassi.execution.direct.python_direct_names import NAMES, CHARS_ALIASES, XML_CLEANUP_ALIASES, VALUE_LIST_CONSTRUCTOR_ALIASES
from yadinassi.execution.direct.python_direct_static_module import analyze as analyze_static, ordered_if, OTHERWISE, _simple_literal_boolean, table_schema_setup
from yadinassi.types.errors import BSLRuntimeError
from dataclasses import fields, replace



def _reject(message):
    raise PythonDirectUnsupported('direct-AST: '+message)


def _nonconstructible_type(name,source,line,column):
    raise BSLRuntimeError('Тип не определен: '+name,source,line,column)


class _GotoTransfer(BaseException):
    """Private control flow; never a catchable BSL error."""

    __slots__ = ('target',)

    def __init__(self, target):
        self.target = target


def _goto_lists(nodes):
    """Assign a stable identity to each label in an outward target list."""
    from yadinassi.syntax.parser import validate_labels
    validate_labels(nodes)  # execute_program also accepts caller-owned mutable ASTs.
    destinations={}; transfers={}; affected_routines=set(); seen=set(); next_target=0

    def scope(root,routine=None):
        nonlocal next_target
        labels={}; jumps=[]; lists={}; pending=[root]
        while pending:
            body=pending.pop(); key=id(body)
            lists[key]=[]
            for node in body:
                kind=type(node)
                if kind in (bsl.Label,bsl.Goto):
                    # execute_program can supply a host AST with a node reused
                    # under another lexical owner. Never let its ID rebind a jump.
                    identity=id(node)
                    if identity in seen:_reject('Goto and Label require distinct AST nodes')
                    seen.add(identity)
                if kind is bsl.Label:
                    labels[node.name.casefold()]=key
                    lists[key].append(node)
                elif kind is bsl.Goto:jumps.append((node,key))
                elif kind is bsl.If:pending.extend([node.otherwise,*(branch for _,branch in node.branches)])
                elif kind is bsl.Try:pending.extend((node.handler,node.body))
                elif kind in (bsl.For,bsl.ForEach,bsl.While):pending.append(node.body)
                elif kind in (bsl.Routine,bsl.ServerInitializer):scope(node.body,node)
        outward={labels[node.name.casefold()] for node,src in jumps if labels[node.name.casefold()]!=src}
        if outward and routine is not None:affected_routines.add(id(routine))
        numbers={}
        for key,body_labels in lists.items():
            if key not in outward:continue
            for label in body_labels:
                numbers[label.name.casefold()]=next_target
                destinations[id(label)]=next_target
                next_target+=1
        for node,_ in jumps:
            name=node.name.casefold()
            if name in numbers:transfers[id(node)]=numbers[name]

    scope(nodes)
    return destinations,transfers,affected_routines


def _goto_order(nodes):
    """Same-list unconditional edges form a prefix and at most one cycle."""
    labels={node.name.casefold():index for index,node in enumerate(nodes) if type(node) is bsl.Label}
    seen={};order=[];index=0;outward=None
    while index<len(nodes) and index not in seen:
        seen[index]=len(order);order.append(index)
        node=nodes[index]
        if type(node) is bsl.Goto:
            index=labels.get(node.name.casefold(),len(nodes))
            if index==len(nodes):outward=node
        else:index+=1
    split=seen.get(index,len(order))
    def statements(indices):
        return [nodes[i] for i in indices if nodes[i] is outward or type(nodes[i]) not in (bsl.Goto,bsl.Label)]
    return statements(order[:split]),statements(order[split:]),index<len(nodes)


def _goto_cycle_check(nodes):
    # A synthetic while must never capture a BSL loop's break/continue.
    pending=list(nodes)
    while pending:
        node=pending.pop();kind=type(node)
        if kind in (bsl.Break,bsl.Continue,bsl.Var):
            _reject('Goto cycle with outer loop control or variable declarations is not supported yet')
        if kind is bsl.If:
            pending.extend(node.otherwise)
            for _,body in node.branches:pending.extend(body)
        elif kind is bsl.Try:pending.extend(node.body);pending.extend(node.handler)
        # Real nested loops retain their own break/continue targets.


def _fragment_binding(storage):
    return local_binding(lambda:storage.value,lambda value:setattr(storage,'value',value),
                         lambda:local_exists(storage),storage)

def _list_get(receiver,index):
    return receiver[_checked_array_index(receiver,index)]


def _checked_literal_array_index(receiver,index):
    if index>=len(receiver):raise IndexError(f'Индекс массива вне границ: {index}')
    return index


def _array_member(receiver,name):
    from yadinassi.execution.direct.python_direct_captured_values import register
    return register(array_method_value(receiver,name,index=_checked_array_index,
        insert=_array_insert_shape,find=scalar.typed_find,
        delete=lambda obj,key:obj.__delitem__(_checked_array_index(obj,key))))


def _identity_reference(value):return value


def _native_count(receiver):
    return Decimal(len(receiver))

def _native_ubound(receiver):
    return Decimal(len(receiver)-1)

def _list_delete(receiver,index):
    return receiver.__delitem__(_checked_array_index(receiver,index))


def _native_operator_binding(value,name):
    if type(value) is not type(type.__dict__['__new__']):return False
    # __module__ is writable even on builtin methods (e.g. set().add).
    # Native module functions have a readonly owning-module binding.
    if type(_OPERATOR_MODULE) is not _ModuleType or value.__self__ is not _OPERATOR_MODULE:return False
    actual=value.__name__
    return type(actual) is str and actual==name


def _native_partial_binding(value):
    # Import-time replacement of a public Python binding must not introduce
    # callbacks into a region proved callback-free. Inspect without descriptors.
    if type(value) is not type:return False
    entries=type.__getattribute__(value,'__dict__')
    new=entries.get('__new__')
    if type(new) is not type(type.__dict__['__new__']) or new.__self__ is not value:return False
    call=entries.get('__call__')
    if type(call) is not type(type.__dict__['__call__']) or call.__objclass__ is not value:return False
    if not type.__getattribute__(value,'__flags__') & (1 << 8):return False  # CPython immutable native type
    name=type.__getattribute__(value,'__name__');module=type.__getattribute__(value,'__module__')
    return type(name) is str and type(module) is str and name=='partial' and module=='functools'


def _bounds(program):
    # Iterative preflight, not recursive subtree serialization/copying.
    count=0;has_goto=False;has_label=False;pending=[(program,0)]
    while pending:
        value,depth=pending.pop()
        if isinstance(value,bsl.Node):
            count+=1
            if type(value) is bsl.Goto:has_goto=True
            elif type(value) is bsl.Label:has_label=True
            if value.token is None or value.token.line<1:_reject('source location is invalid')
            pending.extend((getattr(value,f.name),depth+1) for f in fields(value) if f.name!='token' and not (type(value) is bsl.Literal and f.name=='value'))
        elif type(value) is list or type(value) is tuple:
            pending.extend((item,depth+1) for item in value)
    return count,has_goto,has_label


_BASE_LOOP_CHECKPOINT = BoundaryContext.checkpoint


def _plain_array_loop(context):
    # No special loop budget or metered owner may take the unmetered arm.
    return (type(context).checkpoint is _BASE_LOOP_CHECKPOINT
            and context.loop_budget is None and 'checkpoint' not in vars(context))


def _plain_append_receiver(value):
    kind=type(value)
    return kind is list or (kind is _PlainArray
                            and _PlainArray.__getattribute__ is list.__getattribute__
                            and _PlainArray.__dict__.get('append',list.append) is list.append)


# These names may pin the actual file-owning HTTPRequest in a generated
# receiver slot. No release expression is emitted for unrelated member calls.
_REQUEST_BODY_METHODS = frozenset((
    'setbodyfilename','установитьимяфайлатела','getbodyfilename','получитьимяфайлатела',
    'getbodyasstring','получитьтелокакстроку','getbodyasbinarydata','получитьтелокакдвоичныеданные',
    'getbodyasstream','получитьтелокакпоток','setbodyfromstring','установитьтелоизстроки',
    'setbodyfrombinarydata','установитьтелоиздвоичныхданных',
))


class Emitter:
    missing_database_roots=()
    missing_metadata_roots=()
    def __init__(self,filename):
        self.filename=filename;self.constants=[];self.serial=0
        self.has_goto=False;self.literal_reachability=False;self.table_prefix=False;self.goto_last_expression=None
        self.goto_destinations={};self.goto_transfers={};self.goto_dispatch=[]
        self.http_body_receiver=False
        self.known_calls={};self.known_origins=();self.known_selection_reads=set();self.known_selection_adds=set()
        self.local_field_facts={};self.integer_lane=False;self.native_cells=False;self.module_cells=set();self.static_module_names={};self.static_module_kinds={};self.scalar_kinds={};self.module_boundaries=0;self.range_indices={};self.external_actuals=0
        self.handler_depth=0;self.owned_constructors=False;self.configuration_calls=False;self.host_bindings=False;self.catalog_bounds=False;self.current_module=False;self.source_scopes=False;self.authority=False;self.scalar_routines=False;self.callable_externals=frozenset();self.shadowable=frozenset();self.implicit_shadows=set()
        self.standalone_script=False;self.row_cell_references=False;self.link_imports=False;self.import_links=[]
        self.import_names=frozenset();self.require_last_expression=None;self.region_active=False;self.region_ops={};self.region_states={};self.routines={};self.routine_symbols={};self.numeric_routine_symbols={};self.address_routine_symbols={};self.module_globals=set();self.scope=None;self.source_refs={};self.loop_increments=[];self.required=set();self.pure_builtins={};self.visits=0;self.python_nodes=0
    def node(self,kind,token,**fields):
        if kind is py.FunctionDef and 'type_params' in kind._fields:fields.setdefault('type_params',[])
        result=kind(**fields);self.python_nodes+=1
        if 'lineno' in result._attributes:
            result.lineno=token.line;result.end_lineno=token.line
            result.col_offset=max(0,token.column-1);result.end_col_offset=result.col_offset+1
        return result
    def name(self,name,token,store=False):return self.node(py.Name,token,id=name,ctx=py.Store() if store else py.Load())
    def const(self,value,token):
        if type(value) is tuple:return self.node(py.Tuple,token,elts=[self.const(item,token) for item in value],ctx=py.Load())
        if type(value) is int and value<0:
            return self.node(py.UnaryOp,token,op=py.USub(),operand=self.node(py.Constant,token,value=-value))
        return self.node(py.Constant,token,value=value)
    def call(self,name,args,token,keywords=()):
        return self.node(py.Call,token,func=self.name(name,token),args=args,keywords=list(keywords))
    def attribute(self,value,name,token):return self.node(py.Attribute,token,value=value,attr=name,ctx=py.Load())
    def exact_native(self,kind,value,token):
        compare=lambda name:self.node(py.Compare,token,left=self.call('type',[value],token),ops=[py.Is()],comparators=[self.name(name,token)])
        if kind=='list':return self.node(py.BoolOp,token,op=py.Or(),values=[compare('_PlainArray'),compare('list')])
        return compare(kind)
    def invoke(self,func,args,token,keywords=()):return self.node(py.Call,token,func=func,args=args,keywords=list(keywords))
    def region_helper(self,operation,token):
        return self.node(py.Subscript,token,value=self.name('_collection_helpers',token),slice=self.const(operation,token),ctx=py.Load())
    def region_selected(self,selected,operation,receiver,token,extra=()):
        helper=self.call('_partial',[self.region_helper(operation,token),self.name('_context',token),self.name(receiver,token),*extra],token)
        return self.node(py.IfExp,token,test=self.name('_collection_fast',token),body=helper,orelse=selected)
    def literal(self,value,token):
        if self.integer_lane and type(value) is Decimal and value.is_finite() and value.as_tuple().exponent == 0 and not (value.is_zero() and value.is_signed()):return self.const(int(value),token)
        index=len(self.constants);self.constants.append(value)
        return self.node(py.Subscript,token,value=self.name('_constants',token),slice=self.const(index,token),ctx=py.Load())
    def initialize_local(self,key):
        if key not in self.scope['initialized']:
            self.scope['initialized'].add(key)
            journals=self.scope.get('initialization_journals',[])
            if journals:journals[-1].add(key)
    def target(self,name,token,*,initializes=True):
        self.check_name(name)
        if self.scope is not None and name.casefold() not in self.scope['globals']:
            key=name.casefold()
            if key not in self.scope['slots']:self.scope['slots'][key]=self.temp()
            if initializes:self.initialize_local(key)
            address=self.scope.get('addresses',{}).get(key)
            if address is not None:
                return self.node(py.Subscript,token,value=self.name(address[0],token),
                                 slice=self.name(address[1],token),ctx=py.Store())
            slot=self.name(self.scope['slots'][key],token)
            if key in self.scope['boxed']:
                if self.native_cells:return self.node(py.Subscript,token,value=slot,slice=self.const(0,token),ctx=py.Store())
                return self.node(py.Attribute,token,value=slot,attr='value',ctx=py.Store())
            return self.name(self.scope['slots'][key],token,True)
        return self.node(py.Subscript,token,value=self.name('_initial',token),slice=self.const(name.casefold(),token),ctx=py.Store())
    def external_name(self,name):
        return name.casefold() in (self.external_names if self.scope is None else self.scope['externals'])
    def check_name(self,name):
        pass  # Read/write/reference semantics are selected at the use site.
    def assign_name(self,name,value,t):
        key=name.casefold()
        if self.external_name(name):
            return self.node(py.Expr,t,value=self.invoke(self.attribute(self.name('_context',t),'external_set',t),[self.const(key,t),value],t))
        if key in ('thisobject','этотобъект') and (self.scope is None or key not in self.scope['local_declarations']):
            saved=self.temp();binding=self.node(py.NamedExpr,t,target=self.name(saved,t,True),value=value)
            if self.scope is None or key in self.scope['globals']:
                allowed=self.node(py.Compare,t,left=self.const(key,t),ops=[py.In()],comparators=[self.name('_initial',t)])
            else:allowed=self.const(False,t)
            check=self.node(py.IfExp,t,test=allowed,body=self.name(saved,t),orelse=self.call('_readonly',[self.const(key,t)],t))
            value=self.node(py.Subscript,t,value=self.node(py.Tuple,t,elts=[binding,check],ctx=py.Load()),slice=self.const(-1,t),ctx=py.Load())
        targets=[self.target(name,t)]
        if self.scope is None and key in self.static_module_names:
            local=self.name(self.static_module_names[key],t,True)
            if key in self.module_cells:local=self.node(py.Subscript,t,value=self.name(self.static_module_names[key],t),slice=self.const(0,t),ctx=py.Store())
            targets=[local]
        return self.node(py.Assign,t,targets=targets,value=value)
    def read_missing(self,name,key,token):
        # A local or module value wins; only an actual unbound read reaches here.
        if key in self.missing_database_roots:
            return self.call('_require_database_context',[],token)
        if key in self.missing_metadata_roots:
            return self.invoke(self.attribute(self.name('_context',token),'external_get',token),
                               [self.const(key,token)],token)
        if (self.current_module and not self.owned_constructors
                and key in ('runcallback','выполнитьобработкуоповещения')):
            return self.invoke(self.attribute(self.name('_context',token),'capture_run_callback',token),
                               [self.const(key,token)],token)
        return self.call('_missing',[self.const(name,token)],token)

    def read(self,name,token):
        if self.scope is None and name.casefold() in self.static_module_names:
            value=self.name(self.static_module_names[name.casefold()],token)
            if name.casefold() in self.module_cells:value=self.node(py.Subscript,token,value=value,slice=self.const(0,token),ctx=py.Load())
            if self.static_module_kinds:return value
            test=self.node(py.Compare,token,left=value,ops=[py.IsNot()],comparators=[self.name('_UNSET',token)])
            return self.node(py.IfExp,token,test=test,body=value,orelse=self.call('_missing',[self.const(name,token)],token))
        if self.external_name(name):return self.invoke(self.attribute(self.name('_context',token),'external_get',token),[self.const(name.casefold(),token)],token)
        self.check_name(name)
        key=name.casefold()
        implicit_self=self.current_module and key in ('thisobject','этотобъект')
        if self.scope is not None and key not in self.scope['globals']:
            # A declared local or parameter shadows the implicit module value.
            if implicit_self and key not in self.scope['local_declarations']:
                return self.invoke(self.attribute(self.name('_context',token),'current_module',token),[],token)
            if key in self.scope['bindings']:
                if key not in self.scope['slots']:self.scope['slots'][key]=self.temp()
                address=self.scope.get('addresses',{}).get(key)
                if address is not None:
                    return self.node(py.Subscript,token,value=self.name(address[0],token),
                                     slice=self.name(address[1],token),ctx=py.Load())
                slot=self.name(self.scope['slots'][key],token)
                value=(self.node(py.Subscript,token,value=slot,slice=self.const(0,token),ctx=py.Load()) if self.native_cells else self.attribute(slot,'value',token)) if key in self.scope['boxed'] else slot
                if self.source_scopes or self.host_bindings:
                    raw=self.attribute(slot,'_value',token) if key in self.scope['boxed'] else slot
                    test=self.node(py.Compare,token,left=raw,ops=[py.IsNot()],comparators=[self.name('_UNSET_REF' if key in self.scope['boxed'] else '_UNSET',token)])
                    if key in self.scope['boxed']:
                        forwarded=self.node(py.Compare,token,left=self.call('type',[slot],token),ops=[py.IsNot()],comparators=[self.name('_Cell',token)])
                        test=self.node(py.BoolOp,token,op=py.Or(),values=[forwarded,test])
                    missing=self.invoke(self.attribute(self.name('_context',token),'external_get',token),[self.const(key,token)],token) if key in self.scope['shadows'] else self.call('_missing',[self.const(name,token)],token)
                    return self.node(py.IfExp,token,test=test,body=value,orelse=missing)
                if self.handler_depth and key not in self.scope['initialized'] and key not in self.scope['boxed']:
                    # The thunk contains exactly one lexical load. In
                    # particular, it cannot call a host value or accessor.
                    empty=py.arguments(posonlyargs=[],args=[],vararg=None,kwonlyargs=[],
                                       kw_defaults=[],kwarg=None,defaults=[])
                    load=self.node(py.Lambda,token,args=empty,body=value)
                    return self.call('_read_except_local',[load,self.const(name,token)],token)
                return value
            return self.read_missing(name,key,token)
        temporary=self.temp()
        value=self.invoke(self.attribute(self.name('_initial',token),'get',token),[self.const(name.casefold(),token),self.name('_UNSET',token)],token)
        bound=self.node(py.NamedExpr,token,target=self.name(temporary,token,True),value=value)
        test=self.node(py.Compare,token,left=bound,ops=[py.IsNot()],comparators=[self.name('_UNSET',token)])
        missing=(self.invoke(self.attribute(self.name('_context',token),'current_module',token),[],token)
                 if implicit_self else self.read_missing(name,key,token))
        return self.node(py.IfExp,token,test=test,body=self.name(temporary,token),orelse=missing)
    def temp(self):self.serial+=1;return '_temporary_'+str(self.serial)
    def import_path(self,node):
        parts=[]
        while type(node) is bsl.Group:node=node.expression
        while type(node) is bsl.Attribute:
            parts.append(node.name.casefold());node=node.object
            while type(node) is bsl.Group:node=node.expression
        if type(node) is not bsl.Name:return None
        root=node.name.casefold()
        if root not in self.import_names:return None
        if self.scope is not None and root in self.scope['bindings'] and root not in self.scope['globals']:return None
        return (root,*reversed(parts))
    def import_call(self,node,path,require_value):
        t=node.callee.token
        omitted=tuple(index for index,arg in enumerate(node.arguments) if type(arg) is bsl.OmittedArgument)
        kwargs=lambda:[self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),
                       self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))]
        def resolve(method):
            keywords=kwargs()
            if omitted:keywords.append(self.node(py.keyword,t,arg='omitted',value=self.const(omitted,t)))
            return self.invoke(self.attribute(self.name('_context',t),method,t),[self.const(path,t)],t,keywords)
        generic=self.dynamic_call(resolve('resolve_import_call'),node)
        if omitted or not self.link_imports:return generic
        # Linking before argument evaluation must not bypass a boundary used by
        # an argument itself. Names and literals are the closed call shape.
        for argument in node.arguments:
            while type(argument) is bsl.Group:argument=argument.expression
            if type(argument) not in (bsl.Literal,bsl.Name):return generic
            if type(argument) is bsl.Name and (self.external_name(argument.name)
                    or argument.name.casefold() in ('thisobject','этотобъект')
                    or (self.scope is not None and argument.name.casefold() in self.scope['boxed'])):
                return generic
        cache=self.temp();bound=self.temp();self.import_links.append(cache)
        cached=self.node(py.Compare,t,left=self.name(cache,t),ops=[py.IsNot()],comparators=[self.name('_UNSET',t)])
        first=self.node(py.NamedExpr,t,target=self.name(cache,t,True),value=resolve('link_import_call'))
        load=self.node(py.IfExp,t,test=cached,body=self.name(cache,t),orelse=first)
        bind=self.node(py.NamedExpr,t,target=self.name(bound,t,True),value=load)
        linked=self.node(py.Compare,t,left=bind,ops=[py.IsNot()],comparators=[self.const(None,t)])
        return self.node(py.IfExp,t,test=linked,
            body=self.invoke(self.name(bound,t),[self.expr(arg) for arg in node.arguments],t),orelse=generic)

    def fragment_arguments(self,t):
        names=() if self.scope is None else tuple(sorted(self.scope.get('fragment_names',())))
        bindings=self.node(py.Dict,t,keys=[self.const(key,t) for key in names],
            values=[self.call('_native_fragment_binding' if self.native_cells else '_fragment_binding',[self.name(self.scope['slots'][key],t)],t) for key in names])
        visible=None if self.scope is None else tuple(sorted(self.scope['globals']))
        return [self.name('_context',t),self.name('_initial',t),bindings,self.const(visible,t)]
    def module_sync(self,t,reload):
        return self.call('_reload_module' if reload else '_publish_module',[],t)
    def module_sync_body(self,t,reload):
        check=lambda:self.invoke(self.attribute(self.name("_context",t),"_check",t),[],t)
        operations=[] if reload or self.standalone_script else [check()]
        for key,slot in self.static_module_names.items():
            if reload:
                read=self.invoke(self.attribute(self.name('_initial',t),'get',t),[self.const(key,t),self.name('_UNSET',t)],t)
                if key in self.module_cells:
                    operations.append(self.invoke(self.attribute(self.name(slot,t),'__setitem__',t),[self.const(0,t),read],t))
                else:operations.append(self.node(py.NamedExpr,t,target=self.name(slot,t,True),value=read))
            else:
                value=self.name(slot,t)
                if key in self.module_cells:value=self.node(py.Subscript,t,value=value,slice=self.const(0,t),ctx=py.Load())
                present=self.node(py.Compare,t,left=value,ops=[py.IsNot()],comparators=[self.name('_UNSET',t)])
                published=value
                if self.integer_lane:
                    integer=self.node(py.Compare,t,left=self.call('type',[value],t),ops=[py.Is()],comparators=[self.name('int',t)])
                    published=self.node(py.IfExp,t,test=integer,body=self.call('_Decimal',[value],t),orelse=value)
                write=self.invoke(self.attribute(self.name('_initial',t),'__setitem__',t),[self.const(key,t),published],t)
                checked=write if self.standalone_script else self.node(py.Tuple,t,elts=[write,check()],ctx=py.Load())
                operations.append(self.node(py.IfExp,t,test=present,body=checked,orelse=self.const(None,t)))
        return self.node(py.Tuple,t,elts=operations,ctx=py.Load())
    def external_receiver(self,receiver,t):
        # Identity-only classification. This chooses namespace visibility, never
        # grants access: the existing authority resolver remains in both arms.
        kind=self.call('id',[self.call('type',[self.name(receiver,t)],t)],t)
        return self.node(py.Compare,t,left=kind,ops=[py.NotIn()],comparators=[self.name('_module_data_type_ids',t)])
    def receiver_boundary(self,value,receiver,t,*,native_array=False):
        if self.static_module_kinds:return value
        if self.standalone_script:
            # The resolver handles actual external calls. Built-in collections
            # in a standalone script do not need synthetic liveness probes.
            if self.static_module_names:
                return self.module_boundary(value,t,self.external_receiver(receiver,t))
            return value
        # Low-level containers have no authority resolver of their own. A
        # public alias may already exist; namespace copying is unnecessary but
        # liveness before/after its operation is not.
        kind=self.call('id',[self.call('type',[self.name(receiver,t)],t)],t)
        primitive=self.node(py.Compare,t,left=kind,ops=[py.In()],comparators=[self.name('_module_primitive_type_ids',t)])
        if native_array and self.source_scopes and not self.authority:
            # Exact array reads and append do not invoke any protocol on an
            # element. Other receivers still go through their effect boundary.
            array=self.exact_native('list',self.name(receiver,t),t)
            primitive=self.node(py.BoolOp,t,op=py.And(),values=[
                self.node(py.UnaryOp,t,op=py.Not(),operand=array),primitive])
        if type(value) is py.Call and not value.keywords:
            # Evaluate the single actual subtree first, then authorize the
            # mutation. No helper frame may retain arguments on failure.
            check=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t)
            guard=self.node(py.IfExp,t,test=primitive,body=check,orelse=self.const(None,t))
            packed=self.node(py.Tuple,t,elts=[*value.args,guard],ctx=py.Load())
            args=self.node(py.Subscript,t,value=packed,slice=self.node(py.Slice,t,lower=None,upper=self.const(-1,t),step=None),ctx=py.Load())
            value.args=[self.node(py.Starred,t,value=args,ctx=py.Load())]
        if self.static_module_names:return self.module_boundary(value,t,self.external_receiver(receiver,t),primitive)
        # Routine/public-input native calls have no module register file to
        # synchronize, but aliases remain externally visible and revocable.
        mode=self.temp();result=self.temp()
        capture=self.node(py.NamedExpr,t,target=self.name(mode,t,True),value=primitive)
        def check():
            call=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t)
            return self.node(py.IfExp,t,test=self.name(mode,t),body=call,orelse=self.const(None,t))
        bind=self.node(py.NamedExpr,t,target=self.name(result,t,True),value=value)
        parts=self.node(py.Tuple,t,elts=[capture,check(),bind,check(),self.name(result,t)],ctx=py.Load())
        return self.node(py.Subscript,t,value=parts,slice=self.const(-1,t),ctx=py.Load())
    def live_result(self,value,t):
        if self.standalone_script:return value
        result=self.temp()
        bind=self.node(py.NamedExpr,t,target=self.name(result,t,True),value=value)
        check=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t)
        parts=self.node(py.Tuple,t,elts=[bind,check,self.name(result,t)],ctx=py.Load())
        return self.node(py.Subscript,t,value=parts,slice=self.const(-1,t),ctx=py.Load())
    def module_boundary(self,value,t,condition=None,primitive=None):
        self.module_boundaries+=1
        def depth(change):
            updated=self.node(py.BinOp,t,left=self.name('_dynamic_depth',t),op=py.Add(),right=self.const(change,t))
            return self.node(py.NamedExpr,t,target=self.name('_dynamic_depth',t,True),value=updated)
        before=[self.module_sync(t,False),depth(1)];after=[self.module_sync(t,True),depth(-1)]
        prefix=[]
        if condition is not None:
            mode=self.temp();prefix=[self.node(py.NamedExpr,t,target=self.name(mode,t,True),value=condition)]
            def guarded(parts):
                return self.node(py.IfExp,t,test=self.name(mode,t),body=self.node(py.Tuple,t,elts=parts,ctx=py.Load()),orelse=self.const(None,t))
            before=[guarded(before)];after=[guarded(after)]
            if primitive is not None:
                checked=self.temp();prefix.append(self.node(py.NamedExpr,t,target=self.name(checked,t,True),value=primitive))
                def check():
                    call=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t)
                    return self.node(py.IfExp,t,test=self.name(checked,t),body=call,orelse=self.const(None,t))
                before.append(check());after.insert(0,check())
        # The tuple keeps the result alive during reload, without leaving a
        # hidden reference in the module frame after a discarded expression.
        parts=[*prefix,*before,value,*after]
        return self.node(py.Subscript,t,value=self.node(py.Tuple,t,elts=parts,ctx=py.Load()),slice=self.const(-len(after)-1,t),ctx=py.Load())
    def receiver_statements(self,body,receiver,t):
        if self.static_module_kinds:return body
        if not self.static_module_names:
            if self.standalone_script:return body
            def check():return self.node(py.Expr,t,value=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t))
            return [body[0],check(),*body[1:-1],check(),body[-1],check()]
        self.module_boundaries+=1
        mode=self.temp()
        capture=self.node(py.Assign,t,targets=[self.name(mode,t,True)],value=self.external_receiver(receiver,t))
        check=self.node(py.Expr,t,value=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t))
        enter=self.node(py.If,t,test=self.name(mode,t),body=[
            self.node(py.Expr,t,value=self.module_sync(t,False)),
            self.node(py.AugAssign,t,target=self.name('_dynamic_depth',t,True),op=py.Add(),value=self.const(1,t))],orelse=[])
        leave=self.node(py.If,t,test=self.name(mode,t),body=[
            self.node(py.Expr,t,value=self.module_sync(t,True)),
            self.node(py.AugAssign,t,target=self.name('_dynamic_depth',t,True),op=py.Sub(),value=self.const(1,t))],orelse=[])
        if self.standalone_script:return [body[0],capture,enter,*body[1:],leave]
        return [body[0],capture,check,enter,*body[1:-1],check,body[-1],check,leave]
    def native_array_index(self,node):
        leaf=node
        while type(leaf) is bsl.Group:leaf=leaf.expression
        if type(leaf) is bsl.Name and leaf.name.casefold() in self.range_indices:
            return self.name(self.range_indices[leaf.name.casefold()],node.token)
        # A raw count used only as an index cannot escape into collection data.
        if type(leaf) is bsl.Call and type(leaf.callee) is bsl.Attribute and not leaf.arguments:
            owner=self.static_module_kinds.get(id(leaf.callee.object))
            method=leaf.callee.name.casefold()
            if owner=='array' and method in ('count','количество','ubound','вграница'):
                count=self.call('len',[self.expr(leaf.callee.object)],node.token)
                return count if method in ('count','количество') else self.node(py.BinOp,node.token,left=count,op=py.Sub(),right=self.const(1,node.token))
        return self.call('int',[self.expr(node)],node.token)
    def expr(self,node,require_value=True):
        value=self._expr(node,require_value)
        if self.static_module_names and not self.static_module_kinds:
            callee=node.callee if type(node) is bsl.Call else None
            while type(callee) is bsl.Group:callee=callee.expression
            internal=type(callee) is bsl.Name and (callee.name.casefold() in self.routines or callee.name.casefold() in self.pure_builtins)
            external=(type(node) is bsl.Call and type(callee) is not bsl.Attribute and not internal) or type(node) is bsl.DynamicNew
            external=external or (type(node) is bsl.New and node.name.casefold() not in ('array','массив','map','соответствие','structure','структура'))
            if external:value=self.module_boundary(value,node.token)
            elif type(node) in (bsl.Binary,bsl.Unary) and id(node) not in self.scalar_kinds:value=self.live_result(value,node.token)
        if not self.catalog_bounds:return value
        t=node.token
        step=self.invoke(self.attribute(self.name('_context',t),'preparation_step',t),[],t)
        pair=self.node(py.Tuple,t,elts=[step,value],ctx=py.Load())
        reached=self.node(py.Subscript,t,value=pair,slice=self.const(1,t),ctx=py.Load())
        return self.invoke(self.attribute(self.name('_context',t),'preparation_value',t),[reached],t)
    def implicit_module_receiver(self,node):
        while type(node) is bsl.Group:node=node.expression
        if not self.current_module or type(node) is not bsl.Name:return False
        key=node.name.casefold()
        return (key in ('thisobject','этотобъект') and not self.external_name(key)
                and key not in self.module_globals
                and (self.scope is None or key not in self.scope['local_declarations']))

    def member_read(self,node,receiver,t):
        def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
        host=self.invoke(self.attribute(self.name('_context',t),'get_member',t),[self.name(receiver,t),self.const(node.name,t)],t)
        maps=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_PlainMap'),exact('dict'),exact('_TypedMap'),exact('_NakedMap')])
        host=self.node(py.IfExp,t,test=maps,body=self.call('_native_property_missing',[self.const(node.name,t)],t),orelse=host)
        field={'key':'key','ключ':'key','value':'value','значение':'value'}.get(node.name.casefold())
        if field is not None:
            item=self.call('_dynamic_public_number',[self.attribute(self.name(receiver,t),field,t)],t)
            host=self.node(py.IfExp,t,test=exact('_MapEntry'),body=item,orelse=host)
        host=self.node(py.IfExp,t,test=exact('list'),body=self.call('_array_member',[self.name(receiver,t),self.const(node.name,t)],t),orelse=host)
        structure=self.call('_structure_get_known',[self.name(receiver,t),self.const(node.name.casefold(),t),self.const(node.name,t)],t)
        host=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=structure,orelse=host)
        dictionary=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(node.name,t),ctx=py.Load())
        read=self.node(py.IfExp,t,test=exact('dict'),body=dictionary,orelse=host)
        field=_VALUE_LIST_ITEM_FIELDS.get(node.name.casefold())
        if field is not None:
            item=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(field,t),ctx=py.Load())
            read=self.node(py.IfExp,t,test=exact('_PlainValueListItem'),body=item,orelse=read)
        operation=self.region_ops.get(id(node)) if self.region_active else None
        if operation in ('row_get','item_get'):
            arguments=[self.name('_context',t),self.name(receiver,t)]
            if operation=='row_get':arguments.append(self.const(node.name,t))
            fast=self.invoke(self.region_helper(operation,t),arguments,t)
            read=self.node(py.IfExp,t,test=self.name('_collection_fast',t),body=fast,orelse=read)
        read=self.receiver_boundary(read,receiver,t)
        return read

    def member_call(self,receiver,name,require_value,omitted,count,t):
        method='resolve_configuration_member_call' if self.configuration_calls else 'resolve_member_call'
        keywords=[self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='omitted',value=self.const(omitted,t))]
        if not self.configuration_calls and omitted and name.casefold() in ('openfile','открытьфайл'):
            method='resolve_optional_open_file'
        if self.configuration_calls or method=='resolve_optional_open_file':
            keywords.append(self.node(py.keyword,t,arg='argument_count',value=self.const(count,t)))
        return self.invoke(self.attribute(self.name('_context',t),method,t),[self.name(receiver,t),self.const(name,t)],t,keywords)

    def known_method_phase(self,t):
        if self.scope is not None and 'known_phase' in self.scope:
            return self.name(self.scope['known_phase'],t)
        return self.attribute(self.name('_context',t),'_known_methods_live',t)

    def known_method_origin(self,value,t):
        if self.scope is None or 'known_phase' not in self.scope:return value
        # A generic fallback or caller callback must never arm this routine's
        # candidate. Capture the one selected origin before later local uses.
        phase=self.node(py.NamedExpr,t,target=self.name(self.scope['known_phase'],t,True),
            value=self.attribute(self.name('_context',t),'_known_methods_live',t))
        parts=self.node(py.Tuple,t,elts=[value,phase],ctx=py.Load())
        return self.node(py.Subscript,t,value=parts,slice=self.const(0,t),ctx=py.Load())

    def known_selection_add(self,operation,left,right,t):
        call=self.call('_known_selection_add',[self.name('_context',t),operation,left,right],t)
        if self.scope is None or 'known_phase' not in self.scope:return call
        # An operator can retire the lexical proof but is never a new origin.
        phase=self.scope['known_phase']
        live=self.node(py.BoolOp,t,op=py.And(),values=[
            self.name(phase,t),self.attribute(self.name('_context',t),'_known_methods_live',t)])
        keep=self.node(py.NamedExpr,t,target=self.name(phase,t,True),value=live)
        pair=self.node(py.Tuple,t,elts=[call,keep],ctx=py.Load())
        return self.node(py.Subscript,t,value=pair,slice=self.const(0,t),ctx=py.Load())

    def _expr(self,node,require_value=True):
        if type(node) is bsl.Await:
            if self.scope is None or not self.scope.get('async'):
                _reject('Await outside an admitted asynchronous routine')
            return self.node(py.Yield,node.token,value=self.call('_AwaitRequest',[self.expr(node.operand)],node.token))

        self.visits+=1;t=node.token;k=type(node)
        if self.static_module_kinds:
            if k is bsl.New and self.address_routine_symbols and self.static_module_kinds[id(node)]=='array':
                return self.call('_array_constructor_bounds',[],t)
            if k is bsl.New:return self.call({'map':'_PlainMap','array':'_PlainArray','table':'_PrivateTable','valuelist':'_PrivateValueList'}[self.static_module_kinds[id(node)]],[],t)
            if k is bsl.Binary and node.operator=='+':
                left,right=self.expr(node.left),self.expr(node.right)
                if self.static_module_kinds[id(node)]=='string':
                    return self.call('_concatenate',[left,right],t)
                return self.node(py.BinOp,t,left=left,op=py.Add(),right=right)
            if k is bsl.Attribute:
                owner=self.static_module_kinds[id(node.object)];receiver=self.expr(node.object)
                if owner=='table':return self.attribute(receiver,'columns',t)
                if owner=='item':return self.node(py.Subscript,t,value=receiver,slice=self.const(0,t),ctx=py.Load())
                if self.integer_lane and owner=='row':return self.call('_raw_table_value',[receiver,self.const(node.name,t)],t)
                return self.invoke(self.attribute(receiver,'get_member',t),[self.const(node.name,t)],t)
            if k is bsl.Index:
                owner=self.static_module_kinds[id(node.object)]
                if owner=='row':
                    if self.integer_lane:
                        getter='_raw_table_positional' if self.static_module_kinds[id(node.index)]=='number' else '_raw_table_value'
                        return self.call(getter,[self.expr(node.object),self.expr(node.index)],t)
                    return self.invoke(self.attribute(self.expr(node.object),'get_index',t),[self.expr(node.index)],t)
                if owner in ('table','valuelist'):
                    return self.invoke(self.attribute(self.expr(node.object),'get',t),[self.expr(node.index)],t)
                if self.static_module_kinds[id(node.object)]=='map':return self.call('_native_dict_get',[self.expr(node.object),self.expr(node.index)],t)
                if self.address_routine_symbols:return self.call('_list_get',[self.expr(node.object),self.expr(node.index)],t)
                return self.node(py.Subscript,t,value=self.expr(node.object),slice=self.native_array_index(node.index),ctx=py.Load())
            if k is bsl.Call and type(node.callee) is bsl.Attribute:
                receiver=self.expr(node.callee.object);method=node.callee.name.casefold()
                owner=self.static_module_kinds[id(node.callee.object)]
                if owner=='row' and self.integer_lane:
                    return self.call('_raw_table_positional',[receiver,self.expr(node.arguments[0])],t)
                if owner=='row':
                    return self.invoke(self.attribute(receiver,'get',t),[self.expr(node.arguments[0])],t)
                if self.integer_lane and owner in ('table','columns') and method in ('count','количество'):
                    storage=self.attribute(receiver,'rows' if owner=='table' else '_items',t)
                    return self.call('len',[storage],t)
                if owner in ('table','columns') and method in ('indexof','индекс'):
                    name='_index_of' if self.integer_lane else 'index_of'
                    return self.invoke(self.attribute(receiver,name,t),[self.expr(node.arguments[0])],t)
                if owner in ('table','valuelist','columns'):
                    name={'add':'add','добавить':'add','get':'get','получить':'get','count':'count','количество':'count','total':'total','итог':'total'}[method]
                    return self.invoke(self.attribute(receiver,name,t),[self.expr(arg) for arg in node.arguments],t)
                if method in ('add','добавить'):
                    return self.invoke(self.attribute(receiver,'append',t),[self.expr(node.arguments[0])],t)
                if method in ('insert','вставить'):
                    return self.call('_native_dict_setitem',[receiver,*[self.expr(arg) for arg in node.arguments]],t)
                if method in ('get','получить'):
                    if self.static_module_kinds[id(node.callee.object)]=='map':return self.call('_native_dict_get',[receiver,self.expr(node.arguments[0])],t)
                    if self.address_routine_symbols:return self.call('_list_get',[receiver,self.expr(node.arguments[0])],t)
                    return self.node(py.Subscript,t,value=receiver,slice=self.native_array_index(node.arguments[0]),ctx=py.Load())
                if method in ('count','количество','ubound','вграница'):
                    return self.call('_native_count' if method in ('count','количество') else '_native_ubound',[receiver],t)
        if k is bsl.Call and type(node.callee) is bsl.Group:
            callee=node.callee
            while type(callee) is bsl.Group:callee=callee.expression
            node=replace(node,callee=callee)
        path=self.import_path(node)
        if path is not None:
            return self.invoke(self.attribute(self.name('_context',t),'import_get',t),[self.const(path,t)],t)
        if k is bsl.Call and self.import_path(node.callee) is not None:
            return self.import_call(node,self.import_path(node.callee),require_value)
        if k is bsl.Literal:return self.literal(node.value,t)
        if k is bsl.Name:
            if node.name.casefold() in self.routines:
                key=node.name.casefold()
                if self.scope is None or key in self.scope['globals']:
                    present=self.node(py.Compare,t,left=self.const(key,t),ops=[py.In()],comparators=[self.name('_initial',t)])
                else:present=self.const(key in self.scope['initialized'],t)
                return self.node(py.IfExp,t,test=present,body=self.read(node.name,t),orelse=self.call('_routine_value_error',[self.const(node.name,t)],t))
            return self.read(node.name,t)
        if k is bsl.Group:return self.expr(node.expression,require_value)
        if k is bsl.Unary:
            if self.integer_lane and node.operator in ('+','-'):
                return self.call('_dynamic_sign',[self.expr(node.operand),self.const(node.operator,t)],t)
            if node.operator in ('+','-'):return self.call('_sign',[self.expr(node.operand),self.const(node.operator,t)],t)
            if node.operator=='NOT':return self.node(py.UnaryOp,t,op=py.Not(),operand=self.truth(node.operand,t))
        if k is bsl.Binary:
            op=node.operator
            if not self.catalog_bounds and op=='+' and type(node.left) is bsl.Literal and type(node.right) is bsl.Literal and type(node.left.value) is str:
                return self.literal(scalar.concatenate(node.left.value,node.right.value),t)
            if op in ('AND','OR'):
                return self.node(py.BoolOp,t,op=py.And() if op=='AND' else py.Or(),values=[self.truth(node.left,t),self.truth(node.right,t)])
            left=self.expr(node.left);right=self.expr(node.right)
            left_kind=self.scalar_kinds.get(id(node.left))
            right_kind=self.scalar_kinds.get(id(node.right))
            if op=='+':
                left_value=node.left
                while type(left_value) is bsl.Group:left_value=left_value.expression
                if (left_kind=='string'
                        or (type(left_value) is bsl.Literal and type(left_value.value) is str)):
                    # BSL converts a non-string RHS when the left operand is a string.
                    # No runtime type dispatch is needed for a known string.
                    if id(node) in self.known_selection_adds:
                        return self.known_selection_add(self.name('_concatenate',t),left,right,t)
                    return self.call('_concatenate',[left,right],t)
            if id(node) in self.scalar_kinds and left_kind==right_kind:
                if op=='+' and left_kind=='number':
                    return self.node(py.BinOp,t,left=left,op=py.Add(),right=right)
                if left_kind in ('number','bool'):
                    relation={'=':py.Eq,'<>':py.NotEq,'<':py.Lt,'<=':py.LtE,'>':py.Gt,'>=':py.GtE}.get(op)
                    if relation is not None:
                        return self.node(py.Compare,t,left=left,ops=[relation()],comparators=[right])
            if op=='+':
                if left_kind in ('number','bool') or type(left_value) is bsl.Literal:
                    if id(node) in self.known_selection_adds:
                        return self.known_selection_add(self.name('_native_add',t),left,right,t)
                    return self.node(py.BinOp,t,left=left,op=py.Add(),right=right)
                # Preserve ordinary-direct left-temporary lifetime, evaluate
                # the type decision before RHS, and emit RHS only once.
                temporary=self.temp()
                bound=self.node(py.NamedExpr,t,target=self.name(temporary,t,True),value=left)
                kind=self.call('type',[bound],t)
                test=self.node(py.Compare,t,left=kind,ops=[py.Is()],comparators=[self.name('str',t)])
                operation=self.node(py.IfExp,t,test=test,body=self.name('_concatenate',t),orelse=self.name('_native_add',t))
                if id(node) in self.known_selection_adds:
                    return self.known_selection_add(operation,self.name(temporary,t),right,t)
                return self.invoke(operation,[self.name(temporary,t),right],t)
            helpers={'/':'_divide','=':'_equal','<>':'_not_equal'}
            if op in helpers:return self.call('_dynamic_divide' if self.integer_lane and op=='/' else helpers[op],[left,right],t)
            if op in ('<','<=','>','>='):return self.call('_order',[left,right,self.const(op,t)],t)
            if self.integer_lane and op=='%':return self.call('_dynamic_remainder',[left,right],t)
            operators={'-':py.Sub,'*':py.Mult,'%':py.Mod}
            if op in operators:return self.node(py.BinOp,t,left=left,op=operators[op](),right=right)
        if k is bsl.DynamicNew:
            return self.call('_dynamic_construct',[self.name('_context',t),self.expr(node.type_expression),self.expr(node.parameters) if node.parameters is not None else self.const(None,t)],t)
        if k is bsl.New:
            kindname=node.name.casefold()
            if self.owned_constructors and kindname in self.constructor_names:
                key='new:'+kindname;self.required.add(key)
                shape=self.source_scopes or kindname in VALUE_LIST_CONSTRUCTOR_ALIASES
                keywords=[self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))] if shape else []
                bound=self.invoke(self.attribute(self.name('_context',t),'resolve_service',t),[self.const(key,t)],t,keywords)
                if any(type(arg) is bsl.OmittedArgument for arg in node.arguments):return self.dynamic_call(bound,node,references=False)
                return self.invoke(bound,[self.expr(arg) for arg in node.arguments],t)
            native=kindname in ('array','массив','map','соответствие','structure','структура')
            if not native and kindname not in self.constructor_names:
                # A finite set of known nonconstructible names has a runtime
                # rejection in its observed zero-argument form, not a factory.
                if kindname in ('date','дата','sortdirection','направлениесортировки','promise','обещание') and not node.arguments:
                    return self.call('_nonconstructible_type',[self.const(value,t) for value in
                        (node.name,self.filename,t.line,t.column)],t)
                _reject(f'constructor {node.name}; outside research subset')
            if any(type(arg) is bsl.OmittedArgument for arg in node.arguments):
                if native:return self.call('_host_omission_error',[],t)
                key='new:'+kindname;self.required.add(key)
                from yadinassi.execution.direct.python_direct_services import OPTIONAL_STREAM_CONSTRUCTORS
                resolver=('resolve_optional_service' if kindname in OPTIONAL_STREAM_CONSTRUCTORS
                          or kindname in ('jsonwritersettings','параметрызаписиjson') else 'resolve_service')
                bound=self.invoke(self.attribute(self.name('_context',t),resolver,t),[self.const(key,t)],t,
                    [self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))] if self.source_scopes else [])
                return self.dynamic_call(bound,node,references=False)
            if (kindname in ('callbackdescription','описаниеоповещения')
                    and len(node.arguments)>1 and self.import_path(node.arguments[1]) is not None):
                key='new:'+kindname;self.required.add(key)
                bound=self.invoke(self.attribute(self.name('_context',t),'resolve_service',t),[self.const(key,t)],t)
                return self.dynamic_call(bound,node,references=False)
            args=[self.expr(arg) for arg in node.arguments]
            if kindname in ('valuelist','списокзначений'):return self.call('_PlainValueList',args,t)
            if kindname in ('array','массив'):
                return self.call('_array_constructor_bounds',args,t)
            if kindname in ('map','соответствие'):
                return self.call('_plain_map',args,t) if args else self.call('_PlainMap',[],t)
            if kindname in ('structure','структура'):
                keys=node.arguments[0] if node.arguments else None
                while type(keys) is bsl.Group:keys=keys.expression
                if keys is None or type(keys) is bsl.Literal and type(keys.value) is str:
                    try:schema=prepare_structure_schema('' if keys is None else keys.value)
                    except ValueError:pass
                    else:return self.call('_structure_from_schema',[self.literal(schema,t),*args[1:]],t)
                return self.call('_new_structure',args,t)
            key='new:'+kindname;self.required.add(key)
            bound=self.invoke(self.attribute(self.name('_context',t),'resolve_service',t),[self.const(key,t)],t,
                    [self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))] if self.source_scopes else [])
            value=self.invoke(bound,args,t)
            if id(node) in self.known_origins:
                value=self.call('_known_construct_table',[self.name('_context',t),value],t)
                value=self.known_method_origin(value,t)
            return value
        if k is bsl.Attribute:
            if self.local_field_facts.get(id(node))=='structure':
                return self.call('_structure_get_known',[self.expr(node.object),self.const(node.name.casefold(),t),self.const(node.name,t)],t)
            receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
            read=self.member_read(node,receiver,t)
            if id(node) in self.known_selection_reads:
                protocol=self.call('_known_selection_read_protocol',[self.name('_context',t),self.name(receiver,t)],t)
                if self.scope is not None and 'known_phase' in self.scope:
                    retire=self.node(py.NamedExpr,t,target=self.name(self.scope['known_phase'],t,True),value=self.const(0,t))
                    protocol=self.node(py.BoolOp,t,op=py.Or(),values=[protocol,retire])
                live=self.node(py.Compare,t,left=self.known_method_phase(t),ops=[py.Eq()],comparators=[self.const(1,t)])
                check=self.node(py.BoolOp,t,op=py.And(),values=[live,protocol])
                parts=[bind,check,read]
            else:parts=[bind,read]
            pair=self.node(py.Tuple,t,elts=parts,ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Index:
            receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
            def exact(kind):
                return self.exact_native(kind,self.name(receiver,t),t)
            bound_native=self.call('_partial',[self.name('_native_getitem',t),self.name(receiver,t)],t)
            map_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_PlainMap'),exact('dict'),exact('_TypedMap'),exact('_NakedMap')])
            bound_map=self.attribute(self.name(receiver,t),'get',t)
            native=self.node(py.IfExp,t,test=map_test,body=bound_map,orelse=bound_native)
            native_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            host=self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__getitem__',t)],t)
            other=self.node(py.IfExp,t,test=native_test,body=native,orelse=host)
            other=self.node(py.IfExp,t,test=exact('_PlainValueList'),body=self.attribute(self.name(receiver,t),'get_index',t),orelse=other)
            bound_list=self.call('_partial',[self.name('_list_get',t),self.name(receiver,t)],t)
            select=self.node(py.IfExp,t,test=exact('list'),body=bound_list,orelse=other)
            leaf=node.index
            while type(leaf) is bsl.Group:leaf=leaf.expression
            if type(leaf) in (bsl.Name,bsl.Literal):
                # Leaf expressions have no recursive subtree. For exact native
                # lists, pass the receiver directly rather than allocating a
                # partial for every read. Other capabilities are still resolved
                # before evaluating their index, and all index checks remain.
                native_call=self.call('_list_get',[self.name(receiver,t),self.expr(leaf)],t)
                other_call=self.invoke(other,[self.expr(leaf)],t)
                call=self.node(py.IfExp,t,test=exact('list'),body=native_call,orelse=other_call)
            else:
                call=self.invoke(select,[self.expr(node.index)],t)
            call=self.receiver_boundary(call,receiver,t,native_array=True)
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Conditional:
            return self.node(py.IfExp,t,test=self.truth(node.condition,t),body=self.expr(node.when_true),orelse=self.expr(node.when_false))
        if k is bsl.Call and type(node.callee) is bsl.Attribute and self.implicit_module_receiver(node.callee.object):
            callee=node.callee
            bound=self.invoke(self.attribute(self.name('_context',t),'resolve_public_module_call',t),
                [self.expr(callee.object),self.const(callee.name,t)],t,
                [self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),
                 self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))])
            return self.dynamic_call(bound,node)
        if k is bsl.Call and type(node.callee) is bsl.Attribute and any(type(arg) is bsl.OmittedArgument for arg in node.arguments):
            callee=node.callee;root=callee.object
            while type(root) in (bsl.Group,bsl.Attribute):root=root.expression if type(root) is bsl.Group else root.object
            if type(root) is not bsl.Name:return self.call('_host_omission_error',[],t)
            t=root.token;receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
            def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            omitted=tuple(i for i,arg in enumerate(node.arguments) if type(arg) is bsl.OmittedArgument)
            bound=self.member_call(receiver,callee.name,require_value,omitted,len(node.arguments),t)
            if self.source_scopes:
                source_bound=self.invoke(self.attribute(self.name('_context',t),'resolve_source_member',t),[self.name(receiver,t),self.const(callee.name,t)],t,
                    [self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t)),self.node(py.keyword,t,arg='allow_references',value=self.const(True,t))])
                call=self.node(py.IfExp,t,test=native,body=self.call('_host_omission_error',[],t),orelse=self.dynamic_call(source_bound,node))
                call=self.receiver_boundary(call,receiver,t)
                pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
                return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
            args=[self.const(None,arg.token) if type(arg) is bsl.OmittedArgument else self.expr(arg) for arg in node.arguments]
            if callee.name.casefold() in ('property','свойство') and len(args)>1:
                output=node.arguments[1]
                args[1]=self.call('_canonical_reference',[self.property_output(output,node.token) if type(output) is not bsl.OmittedArgument else self.const(None,t)],t)
            call=self.node(py.IfExp,t,test=native,body=self.call('_host_omission_error',[],t),orelse=self.invoke(bound,args,t))
            call=self.receiver_boundary(call,receiver,t)
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Call and type(node.callee) is bsl.Attribute and node.callee.name.casefold() in ('property','свойство'):
            callee=node.callee
            t=node.token;receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
            def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
            native_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            native=self.call('_partial',[self.name('_structure_property',t),self.name(receiver,t)],t)
            fail=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
            native=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=native,orelse=fail)
            host=self.member_call(receiver,callee.name,require_value,(),len(node.arguments),t)
            selected=self.node(py.IfExp,t,test=native_test,body=native,orelse=host)
            if len(node.arguments)==2:
                converter=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=self.name('_identity_reference',t),orelse=self.name('_canonical_reference',t))
                args=[self.expr(node.arguments[0]),self.invoke(converter,[self.property_output(node.arguments[1],t)],t)]
            else:
                # Resolve the actual receiver and let its method enforce arity
                # at runtime, rather than rejecting the containing BSL module.
                args=[self.expr(arg) for arg in node.arguments]
            call=self.invoke(selected,args,t)
            call=self.receiver_boundary(call,receiver,t)
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Call and id(node) in self.known_calls:
            entry,fresh=self.known_calls[id(node)];callee=node.callee
            location=callee
            while type(location) in (bsl.Attribute,bsl.Group,bsl.Call):
                location=location.object if type(location) is bsl.Attribute else location.expression if type(location) is bsl.Group else location.callee
            t=location.token;receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
            if entry.effect=='database':
                call=self.call('_known_query_execute',[self.name('_context',t),self.name(receiver,t),self.const(callee.name,t),
                    self.const(require_value,t)],t)
                call=self.receiver_boundary(call,receiver,t)
                call=self.known_method_origin(call,t)
            else:
                fallback=self.call('_known_generic_call',[self.name('_context',t),self.name(receiver,t),
                    self.const(callee.name,t),self.const(require_value,t)],t)
                direct=self.invoke(self.attribute(self.name(receiver,t),entry.method,t),[],t)
                if fresh:
                    fallback=self.receiver_boundary(fallback,receiver,t)
                    phase=1 if entry.kind.startswith('query-') else 2
                    live=self.node(py.Compare,t,left=self.known_method_phase(t),
                        ops=[py.Eq()],comparators=[self.const(phase,t)])
                else:
                    live=self.call('_known_detached_after_publication',[self.name('_context',t),
                        self.name(receiver,t),self.const(entry.kind,t)],t)
                call=self.node(py.IfExp,t,test=live,body=direct,orelse=fallback)
                if not fresh:call=self.receiver_boundary(call,receiver,t)
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Call and type(node.callee) is bsl.Attribute:
            callee=node.callee;location=callee
            while type(location) in (bsl.Attribute,bsl.Group,bsl.Call):
                location=location.object if type(location) is bsl.Attribute else location.expression if type(location) is bsl.Group else location.callee
            t=location.token;method=_ALIASES.get(callee.name.casefold(),callee.name.casefold())
            arities={'add':(0,1),'count':(0,0),'get':(1,1),'set':(2,2),'insert':(1,2),'find':(1,1),'delete':(1,1),'ubound':(0,0)}
            generic=method not in arities and method!='clear'
            invalid_arity=method in arities and not arities[method][0]<=len(node.arguments)<=arities[method][1]
            if any(type(arg) is bsl.OmittedArgument for arg in node.arguments):
                _reject('omitted method arguments outside research subset')
            structural=self.standalone_script and not self.owned_constructors and method=='count' and not node.arguments
            projected=callee.object
            while type(projected) is bsl.Group:projected=projected.expression
            projection=None
            if (structural and type(projected) is bsl.Attribute and self.import_path(projected) is None
                    and not self.local_field_facts.get(id(projected))):
                projection={'rows':'rows','строки':'rows','columns':'columns','колонки':'columns',
                            'indexes':'indexes','индексы':'indexes'}.get(projected.name.casefold())
            receiver=self.temp()
            if projection is None:
                bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
                structural_receiver=receiver
            else:
                structural_receiver=self.temp()
                base=self.node(py.NamedExpr,t,target=self.name(structural_receiver,t,True),value=self.expr(projected.object))
                read=self.member_read(projected,structural_receiver,projected.token)
                bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=read)
            def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
            native_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            host=self.member_call(receiver,callee.name,require_value,(),len(node.arguments),t)
            if generic:native=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
            elif method in ('count','ubound'):
                native=self.call('_partial',[self.name('_native_count' if method=='count' else '_native_ubound',t),self.name(receiver,t)],t)
                if method=='ubound':native=self.node(py.IfExp,t,test=exact('list'),body=native,orelse=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t))
            elif method=='find':
                native=self.node(py.IfExp,t,test=exact('list'),body=self.call('_partial',[self.name('_typed_find',t),self.name(receiver,t)],t),orelse=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t))
            elif method=='delete':
                native=self.node(py.IfExp,t,test=exact('list'),body=self.call('_partial',[self.name('_list_delete',t),self.name(receiver,t)],t),orelse=self.attribute(self.name(receiver,t),'__delitem__',t))
            elif method=='clear':native=self.attribute(self.name(receiver,t),'clear',t)
            elif method in ('set','insert'):
                array=self.call('_partial',[self.name('_array_set_checked' if method=='set' else '_bounded_insert',t),self.name(receiver,t)],t)
                if method=='set':
                    other=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
                else:
                    structure=self.call('_partial',[self.name('_structure_insert',t),self.name(receiver,t)],t)
                    other=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=structure,orelse=self.attribute(self.name(receiver,t),'__setitem__',t))
                native=self.node(py.IfExp,t,test=exact('list'),body=array,orelse=other)
                if method=='insert' and len(node.arguments)==1:
                    key=self.temp(); bound=self.temp()
                    native=self.node(py.Lambda,t,args=self.node(py.arguments,t,posonlyargs=[],args=[self.node(py.arg,t,arg=key),self.node(py.arg,t,arg=bound)],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[native]),body=self.invoke(self.name(bound,t),[self.name(key,t),self.const(None,t)],t))
            elif method=='get':
                maps=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_PlainMap'),exact('dict'),exact('_TypedMap'),exact('_NakedMap')])
                fail=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
                mapped=self.node(py.IfExp,t,test=maps,body=self.attribute(self.name(receiver,t),'get',t),orelse=fail)
                native=self.node(py.IfExp,t,test=exact('list'),body=self.call('_partial',[self.name('_list_get',t),self.name(receiver,t)],t),orelse=mapped)
            else:
                native=self.attribute(self.name(receiver,t),'append',t)
                if not node.arguments:native=self.call('_partial',[native,self.const(None,t)],t)
                fail=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
                native=self.node(py.IfExp,t,test=exact('list'),body=native,orelse=fail)
            selected=self.node(py.IfExp,t,test=native_test,body=native,orelse=host)
            # Plain Map is the ordinary native representation. One receiver
            # classification preserves the host boundary for rebound values;
            # no token wrapper or repeated native-type ladder on this arm.
            if (method,len(node.arguments)) in (('insert',2),('get',1)):
                plain=self.attribute(self.name(receiver,t),'get' if method=='get' else '__setitem__',t)
                selected=self.node(py.IfExp,t,test=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_PlainMap'),exact('dict')]),body=plain,orelse=selected)
            operation=self.region_ops.get(id(node)) if self.region_active else None
            if operation in ('table_add','list_add','table_get','list_get'):
                selected=self.region_selected(selected,operation,receiver,t)
            dynamic=self.source_scopes or self.host_bindings
            if self.source_scopes:
                host=self.invoke(self.attribute(self.name('_context',t),'resolve_source_member',t),[self.name(receiver,t),self.const(callee.name,t)],t,
                    [self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t)),self.node(py.keyword,t,arg='allow_references',value=self.const(True,t))])
            mode=self.temp() if dynamic or invalid_arity else None
            choose=self.node(py.NamedExpr,t,target=self.name(mode,t,True),value=native_test) if mode else native_test
            if dynamic:selected=self.node(py.IfExp,t,test=choose,body=native,orelse=host)
            guard=None
            if invalid_arity:
                minimum,maximum=arities[method]
                expected=str(minimum) if minimum==maximum else str(minimum)+'..'+str(maximum)
                message=callee.name+' ожидает '+expected+' аргументов, получено '+str(len(node.arguments))
                native_callable=self.name('_invalid_native_arity',t)
                allowed={'add':('list',),'get':('list','dict','_PlainMap','_TypedMap','_NakedMap'),'set':('list',),'find':('list',),'ubound':('list',)}.get(method)
                if allowed:
                    ok=exact(allowed[0]) if len(allowed)==1 else self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in allowed])
                    native_callable=self.node(py.IfExp,t,test=ok,body=native_callable,orelse=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t))
                selected=self.node(py.IfExp,t,test=choose,body=native_callable,orelse=host)
                guard=self.node(py.IfExp,t,test=self.name(mode,t),body=self.call('_invalid_native_arity',[self.const(message,t)],t),orelse=self.const(None,t))
            if not dynamic:
                signature=_VALUE_LIST_METHODS.get(callee.name.casefold())
                if signature is None:
                    direct=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
                elif require_value and not signature[1]:
                    # Evaluate the receiver, but reject before resolving the
                    # native method or evaluating its arguments, just like a
                    # source procedure in a value position.
                    direct=self.call('_procedure_value_error',[self.const(callee.name,t)],t)
                else:
                    direct=self.attribute(self.name(receiver,t),signature[0],t)
                if invalid_arity:
                    mark=self.node(py.NamedExpr,t,target=self.name(mode,t,True),value=self.const(False,t))
                    direct=self.node(py.Subscript,t,value=self.node(py.Tuple,t,elts=[mark,direct],ctx=py.Load()),slice=self.const(-1,t),ctx=py.Load())
                selected=self.node(py.IfExp,t,test=exact('_PlainValueList'),body=direct,orelse=selected)
                if callee.name.casefold() in ('getid','получитьидентификатор'):
                    direct_item=self.attribute(self.name(receiver,t),'get_id',t)
                    selected=self.node(py.IfExp,t,test=exact('_PlainValueListItem'),body=direct_item,orelse=selected)
            if dynamic:
                call=self.dynamic_call(selected,node,native_mode=mode,argument_guard=guard)
            else:
                arguments=[self.expr(arg) for arg in node.arguments]
                if guard is not None:
                    packed=self.node(py.Tuple,t,elts=[*arguments,guard],ctx=py.Load())
                    actuals=self.node(py.Subscript,t,value=packed,slice=self.node(py.Slice,t,lower=None,upper=self.const(-1,t),step=None),ctx=py.Load())
                    arguments=[self.node(py.Starred,t,value=actuals,ctx=py.Load())]
                call=self.invoke(selected,arguments,t)
            call=self.receiver_boundary(call,receiver,t,
                native_array=not invalid_arity and method in ('add','get','count','ubound'))
            if generic and method in _REQUEST_BODY_METHODS:
                # The request owns the admitted file until the last real BSL
                # alias dies. A successful body call must not pin it in a
                # compiler-only local for the remainder of the routine.
                self.http_body_receiver=True
                release=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.const(None,t))
                release=self.node(py.IfExp,t,test=exact('_HTTPRequest'),body=release,orelse=self.const(None,t))
                pair=self.node(py.Tuple,t,elts=[bind,call,release],ctx=py.Load())
                return self.node(py.Subscript,t,value=pair,slice=self.const(1,t),ctx=py.Load())
            if structural:
                def structural_case(value_slot, field, fallback):
                    value=self.name(value_slot,t)
                    args=[self.name('_context',t),value,self.const(field,t)]
                    ids=self.node(py.Subscript,t,value=self.name('_structural_count_ids',t),
                        slice=self.const(field,t),ctx=py.Load())
                    kind=self.call('id',[self.call('type',[value],t)],t)
                    candidate=self.node(py.Compare,t,left=kind,ops=[py.In()],comparators=[ids])
                    test=self.node(py.BoolOp,t,op=py.And(),values=[candidate,self.call('_select_structural_read',args,t)])
                    fast=self.call('_structural_count',[*args,self.const(callee.name,t)],t)
                    fast=self.receiver_boundary(fast,value_slot,t)
                    return self.node(py.IfExp,t,test=test,body=fast,orelse=fallback)

                # A projected receiver is not necessarily the model's own
                # Rows/Columns/Indexes (for example, a Structure field).
                # If the fused read cannot apply, evaluate the member normally
                # and classify the exact value that will receive Count.
                call=structural_case(receiver,None,call)
                if projection is not None:
                    pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
                    fallback=self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
                    call=structural_case(structural_receiver,projection,fallback)
                    bind=base
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Call and type(node.callee) is bsl.Name and node.callee.name.casefold() in self.routines:
            routine=self.routines[node.callee.name.casefold()]
            if require_value and not routine.is_function:
                return self.call('_procedure_value_error',[self.const(routine.name,node.callee.token)],node.callee.token)
            required=max((index+1 for index,parameter in enumerate(routine.parameters) if parameter.default is None),default=0)
            if not required<=len(node.arguments)<=len(routine.parameters):
                return self.call('_argument_count_error',[self.const(routine.name,node.callee.token),self.const(len(routine.parameters),node.callee.token),self.const(len(node.arguments),node.callee.token)],node.callee.token)
            address=self.address_routine_symbols.get(routine.name.casefold())
            if address is not None and self.static_module_kinds.get(id(node))=='address_call':
                actuals=[]
                for parameter,arg in zip(routine.parameters,node.arguments):
                    if parameter.by_value:
                        actuals.append(self.expr(arg))
                        continue
                    while type(arg) is bsl.Group:arg=arg.expression
                    owner=self.temp()
                    actuals.append(self.node(py.NamedExpr,arg.token,target=self.name(owner,arg.token,True),
                                             value=self.expr(arg.object)))
                    index=arg.index
                    while type(index) is bsl.Group:index=index.expression
                    literal=index.value if type(index) is bsl.Literal else None
                    if type(literal) is Decimal and literal.is_finite() and literal.as_tuple().exponent==0 and 0<=literal<=2**63-1 and not literal.is_signed():
                        checked='_checked_literal_array_index';index_value=self.const(int(literal),index.token)
                    else:checked='_checked_array_index';index_value=self.expr(arg.index)
                    actuals.append(self.call(checked,[self.name(owner,arg.token),index_value],node.callee.token))
                return self.call(address,actuals,node.callee.token)
            numeric=self.numeric_routine_symbols.get(routine.name.casefold())
            if numeric is not None and id(node) in self.scalar_kinds:
                actuals=[]
                for index,parameter in enumerate(routine.parameters):
                    supplied=node.arguments[index] if index<len(node.arguments) else None
                    value=parameter.default if supplied is None or type(supplied) is bsl.OmittedArgument else supplied
                    actuals.append(self.expr(value))
                return self.call(numeric,actuals,node.callee.token)
            arguments=[]
            for parameter,arg in zip(routine.parameters,node.arguments):
                if type(arg) is bsl.OmittedArgument:arguments.append(self.name('_OMITTED_REF',arg.token))
                elif parameter.by_value:arguments.append(self.expr(arg))
                else:
                    plain=arg
                    while type(plain) is bsl.Group:plain=plain.expression
                    if self.implicit_module_receiver(plain):
                        arguments.append(self.call('_NativeCell' if self.native_cells else '_Cell',[self.expr(arg)],node.callee.token))
                        continue
                    if self.native_cells:
                        if type(plain) is bsl.Name:
                            key=plain.name.casefold()
                            if self.scope is None and key in self.module_cells:
                                actual=self.name(self.static_module_names[key],plain.token)
                                if self.external_actuals:
                                    actual=self.call('_PublishedModuleCell',[actual,self.name('_initial',plain.token),
                                                                             self.const(key,plain.token)],plain.token)
                            elif self.scope is not None and key in self.scope['boxed'] and key not in self.scope['globals']:
                                actual=self.name(self.scope['slots'][key],plain.token)
                            else:actual=self.call('_adapt_native_cell',[self.output_reference(plain,node.callee.token),self.name('_context',node.callee.token)],node.callee.token)
                        elif type(plain) in (bsl.Index,bsl.Attribute):actual=self.call('_adapt_native_cell',[self.output_reference(plain,node.callee.token,local_row=self.row_cell_references),self.name('_context',node.callee.token)],node.callee.token)
                        else:actual=self.call('_NativeCell',[self.expr(arg)],node.callee.token)
                        arguments.append(actual)
                    elif self.import_path(plain) is not None:
                        arguments.append(self.call('_ForwardReference',[self.output_reference(plain)],node.callee.token))
                    elif type(plain) in (bsl.Name,bsl.Index,bsl.Attribute):
                        reference_token=(node.callee.token if type(plain) is not bsl.Name
                                         or self.external_name(plain.name) else None)
                        arguments.append(self.output_reference(plain,reference_token,local_row=self.row_cell_references))
                    else:arguments.append(self.call('_Cell',[self.expr(arg)],node.callee.token))
            function=self.name(self.routine_symbols[routine.name.casefold()],node.callee.token)
            if self.authority and (self.source_scopes or not self.standalone_script):
                gate='_check_loop' if self.source_scopes else '_check'
                check=self.invoke(self.attribute(self.name('_context',t),gate,t),[],t)
                function=self.node(py.Subscript,t,value=self.node(py.Tuple,t,elts=[check,function],ctx=py.Load()),slice=self.const(-1,t),ctx=py.Load())
            keywords=[self.node(py.keyword,node.callee.token,arg='_native_cells',value=self.const(True,node.callee.token))] if self.native_cells else []
            return self.invoke(function,arguments,node.callee.token,keywords)
        if k is bsl.Call and type(node.callee) is bsl.Name:
            name=node.callee.name.casefold();self.check_name(name);self.required.add(name)
            if name in self.pure_builtins:
                args=[]
                for arg in node.arguments:
                    value=self.expr(arg)
                    if self.integer_lane and self.scalar_kinds.get(id(arg))=='number':
                        # Builtins still see BSL numeric presentation, even if a
                        # caller's intermediate is carried as a Python int.
                        value=self.call('_dynamic_public_number',[value],arg.token)
                    args.append(value)
                return self.call(self.pure_builtins[name],args,node.callee.token)
            external_call=self.external_name(name) and name in self.callable_externals
            if self.external_name(name) and not external_call:
                # Chars is a known non-callable value. Its measured error is
                # catchable and occurs before any actual argument is evaluated.
                if name in CHARS_ALIASES and not self.owned_constructors:
                    return self.call('_invalid_native_arity',
                                     [self.const('Значение не является функцией',t)],node.callee.token)
                _reject('external namespace names are not callable: '+node.callee.name)
            if external_call:fallback=self.name('_MISSING',t)
            elif self.scope is not None and name not in self.scope['globals']:
                # Presence is dynamic after conditional assignment. Preserve the
                # ordinary locals() probe even for known/absent bindings: its
                # retained frame-local values are observable to finalizers.
                if name not in self.scope['slots']:self.scope['slots'][name]=self.temp()
                slot=self.scope['slots'][name];value=self.name(slot,t)
                if name in self.scope['boxed']:value=self.node(py.Subscript,t,value=value,slice=self.const(0,t),ctx=py.Load()) if self.native_cells else self.attribute(value,'value',t)
                if self.source_scopes or self.host_bindings:
                    known=name in self.scope['bindings']
                    raw=self.attribute(self.name(slot,t),'_value',t) if name in self.scope['boxed'] else self.name(slot,t)
                    present=self.node(py.Compare,t,left=raw,ops=[py.IsNot()],comparators=[self.name('_UNSET_REF' if name in self.scope['boxed'] else '_UNSET',t)]) if known else self.const(False,t)
                    if known and name in self.scope['boxed']:
                        forwarded=self.node(py.Compare,t,left=self.call('type',[self.name(slot,t)],t),ops=[py.IsNot()],comparators=[self.name('_Cell',t)])
                        present=self.node(py.BoolOp,t,op=py.Or(),values=[forwarded,present])
                else:present=self.node(py.Compare,t,left=self.const(slot,t),ops=[py.In()],comparators=[self.call('locals',[],t)])
                fallback=self.node(py.IfExp,t,test=present,body=value,orelse=self.name('_MISSING',t))
            else:fallback=self.invoke(self.attribute(self.name('_initial',t),'get',t),[self.const(name,t),self.name('_MISSING',t)],t)
            resolver=('resolve_optional_service' if any(type(arg) is bsl.OmittedArgument for arg in node.arguments)
                      else 'resolve_service')
            keywords=[self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),
                self.node(py.keyword,t,arg='allow_references',value=self.const(True,t)),
                self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))]
            if not self.owned_constructors:
                shaped=[]
                for index,arg in enumerate(node.arguments):
                    while type(arg) is bsl.Group:arg=arg.expression
                    if type(arg) not in (bsl.Name,bsl.OmittedArgument):shaped.append(index)
                if shaped:
                    keywords.append(self.node(py.keyword,t,arg='_non_name_actuals',value=self.const(tuple(shaped),t)))
            bound=self.invoke(self.attribute(self.name('_context',t),resolver,t),[self.const(node.callee.name if self.source_scopes else name,t),fallback],node.callee.token,keywords)
            if name in ('eval','вычислить'):
                bound=self.call('_bind_eval',[bound,*self.fragment_arguments(t)],t)
            return self.dynamic_call(bound,node)
        if k is bsl.Call:
            location=node.callee
            while type(location) in (bsl.Call,bsl.Group,bsl.Attribute):location=location.callee if type(location) is bsl.Call else location.expression if type(location) is bsl.Group else location.object
            t=location.token
            bound=self.invoke(self.attribute(self.name('_context',t),'resolve_extension_value',t),[self.expr(node.callee)],t,[self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='allow_references',value=self.const(True,t))])
            return self.dynamic_call(bound,node,call_token=t)
        _reject('unsupported expression '+k.__name__)
    def property_output(self,node,token):
        while type(node) is bsl.Group:node=node.expression
        if type(node) in (bsl.Name,bsl.Index,bsl.Attribute):
            reference_token=None if type(node) is bsl.Name and not self.external_name(node.name) else token
            return self.output_reference(node,reference_token)
        # A non-addressable actual has a disposable output slot. Its
        # expression still runs exactly once, at the original argument point.
        return self.call('_Cell',[self.expr(node)],token)

    def output_reference(self,node,reference_token=None,*,local_row=False):
        while type(node) is bsl.Group:node=node.expression
        t=reference_token or node.token
        path=self.import_path(node)
        if path is not None:return self.invoke(self.attribute(self.name('_context',t),'import_reference',t),[self.const(path,t)],t)
        if type(node) is bsl.Name:
            if self.external_name(node.name):return self.invoke(self.attribute(self.name('_context',t),'external_reference',t),[self.const(node.name.casefold(),t)],t)
            self.check_name(node.name);key=node.name.casefold()
            if self.scope is not None and key not in self.scope['globals']:
                if key not in self.scope['boxed']:_reject('passing an unboxed routine local by reference outside research subset')
                slot=self.name(self.scope['slots'][key],t)
                value=self.call('_native_cell_reference' if self.native_cells else '_bound_ref',[slot],t)
                if self.source_scopes or self.host_bindings:
                    forwarded=self.node(py.Compare,t,left=self.call('type',[slot],t),ops=[py.IsNot()],comparators=[self.name('_Cell',t)])
                    initialized=self.node(py.Compare,t,left=self.attribute(slot,'_value',t),ops=[py.IsNot()],comparators=[self.name('_UNSET_REF',t)])
                    present=self.node(py.BoolOp,t,op=py.Or(),values=[forwarded,initialized])
                    missing=self.invoke(self.attribute(self.name('_context',t),'external_reference',t),[self.const(key,t)],t) if key in self.scope['shadows'] else self.call('_missing',[self.const(node.name,t)],t)
                    return self.node(py.IfExp,t,test=present,body=value,orelse=missing)
                return value
            if key not in self.source_refs:self.source_refs[key]=self.temp()
            return self.call('_source_reference',[self.name('_initial',t),self.const(node.name,t),self.name(self.source_refs[key],t)],t)
        if type(node) not in (bsl.Index,bsl.Attribute):_reject('output reference outside research subset')
        receiver=self.temp();bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
        def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
        kinds=('list','dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure') if type(node) is bsl.Index else ('dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')
        native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in kinds])
        if type(node) is bsl.Index:
            constructor=self.call('_partial',[self.name('_IndexRef',t),self.name(receiver,t)],t,[self.node(py.keyword,t,arg='checked',value=self.const(True,t))])
            host=self.invoke(self.attribute(self.name('_context',t),'bind_reference_index',t),[self.name(receiver,t)],t)
            argument=self.expr(node.index)
        else:
            constructor=self.call('_partial',[self.name('_AttributeRef',t),self.name(receiver,t)],t)
            host=self.call('_partial',[self.attribute(self.name('_context',t),'reference_member',t),self.name(receiver,t)],t)
            argument=self.const(node.name,t)
        if local_row:
            helper='_local_row_index' if type(node) is bsl.Index else '_local_row_member'
            address=self.call('_partial',[self.name(helper,t),self.name('_context',t),self.name(receiver,t)],t)
            if type(node) is bsl.Index:
                array=self.call('_partial',[self.name('_local_array_index',t),self.name('_context',t),self.name(receiver,t)],t)
                host=self.node(py.IfExp,t,test=exact('_BoxedArray'),body=array,orelse=host)
            else:
                structure=self.call('_partial',[self.name('_local_structure_member',t),self.name('_context',t),self.name(receiver,t)],t)
                host=self.node(py.IfExp,t,test=exact('_BoxedStructure'),body=structure,orelse=host)
            host=self.node(py.IfExp,t,test=exact('_PlainTableRow'),body=address,orelse=host)
        selected=self.node(py.IfExp,t,test=native,body=constructor,orelse=host)
        result=self.invoke(selected,[argument],t)
        pair=self.node(py.Tuple,t,elts=[bind,result],ctx=py.Load())
        return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())

    def access_argument(self,node,requires,call_token):
        # Select reference/value mode first, but emit receiver/index only once.
        mode=self.temp();receiver=self.temp();t=node.token;rt=call_token
        mode_bind=self.node(py.NamedExpr,rt,target=self.name(mode,rt,True),value=requires)
        bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
        def exact(kind,token=t):return self.exact_native(kind,self.name(receiver,token),token)
        def native_test(kinds,token=t):return self.node(py.BoolOp,token,op=py.Or(),values=[exact(kind,token) for kind in kinds])
        dicts=('dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')
        if type(node) is bsl.Index:
            reference=self.call('_partial',[self.name('_IndexRef',rt),self.name(receiver,rt)],rt,[self.node(py.keyword,rt,arg='checked',value=self.const(True,rt))])
            host_ref=self.invoke(self.attribute(self.name('_context',rt),'bind_reference_index',rt),[self.name(receiver,rt)],rt)
            reference=self.node(py.IfExp,rt,test=native_test(('list',*dicts),rt),body=reference,orelse=host_ref)
            read=self.call('_partial',[self.name('_native_getitem',t),self.name(receiver,t)],t)
            maps=native_test(('_PlainMap','dict','_TypedMap','_NakedMap'))
            read=self.node(py.IfExp,t,test=maps,body=self.attribute(self.name(receiver,t),'get',t),orelse=read)
            host=self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__getitem__',t)],t)
            read=self.node(py.IfExp,t,test=native_test(dicts),body=read,orelse=host)
            read=self.node(py.IfExp,t,test=exact('list'),body=self.call('_partial',[self.name('_list_get',t),self.name(receiver,t)],t),orelse=read)
            leaf=node.index
            while type(leaf) is bsl.Group:leaf=leaf.expression
            if type(leaf) in (bsl.Name,bsl.Literal):
                # Retain historical leaf-call locations without duplicating a
                # recursive subtree. The selected leaf is evaluated only once.
                ref_call=self.invoke(reference,[self.expr(leaf)],rt)
                read_call=self.invoke(read,[self.expr(leaf)],t)
                result=self.node(py.IfExp,rt,test=self.name(mode,rt),body=ref_call,orelse=read_call)
            else:
                # One target selection, one index expression, no wrapper frame
                # or retained index temporary. Complex indexing failures point
                # to the indexing expression in either value/reference mode;
                # errors inside its child expression retain their own tokens.
                selected=self.node(py.IfExp,t,test=self.name(mode,t),body=reference,orelse=read)
                result=self.invoke(selected,[self.expr(node.index)],t)
        else:
            ref=self.call('_AttributeRef',[self.name(receiver,rt),self.const(node.name,rt)],rt)
            host_ref=self.invoke(self.attribute(self.name('_context',rt),'reference_member',rt),[self.name(receiver,rt),self.const(node.name,rt)],rt)
            reference=self.node(py.IfExp,rt,test=native_test(dicts,rt),body=ref,orelse=host_ref)
            read=self.invoke(self.attribute(self.name('_context',t),'get_member',t),[self.name(receiver,t),self.const(node.name,t)],t)
            read=self.node(py.IfExp,t,test=native_test(('_PlainMap','dict','_TypedMap','_NakedMap')),body=self.call('_native_property_missing',[self.const(node.name,t)],t),orelse=read)
            field={'key':'key','ключ':'key','value':'value','значение':'value'}.get(node.name.casefold())
            if field is not None:read=self.node(py.IfExp,t,test=exact('_MapEntry'),body=self.attribute(self.name(receiver,t),field,t),orelse=read)
            read=self.node(py.IfExp,t,test=exact('list'),body=self.call('_array_member',[self.name(receiver,t),self.const(node.name,t)],t),orelse=read)
            structure=self.call('_structure_get_known',[self.name(receiver,t),self.const(node.name.casefold(),t),self.const(node.name,t)],t)
            read=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=structure,orelse=read)
            dictionary=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(node.name,t),ctx=py.Load())
            read=self.node(py.IfExp,t,test=exact('dict'),body=dictionary,orelse=read)
            item_field=_VALUE_LIST_ITEM_FIELDS.get(node.name.casefold())
            if item_field is not None:
                item=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(item_field,t),ctx=py.Load())
                read=self.node(py.IfExp,t,test=exact('_PlainValueListItem'),body=item,orelse=read)
            result=self.node(py.IfExp,rt,test=self.name(mode,rt),body=reference,orelse=read)
        converter=self.node(py.IfExp,rt,test=self.name(mode,rt),body=self.name('_canonical_reference',rt),orelse=self.name('_identity_reference',rt))
        converted=self.invoke(converter,[result],rt)
        pair=self.node(py.Tuple,rt,elts=[mode_bind,bind,converted],ctx=py.Load())
        return self.node(py.Subscript,rt,value=pair,slice=self.const(-1,rt),ctx=py.Load())

    def dynamic_call(self,bound,node,references=True,call_token=None,native_mode=None,argument_guard=None):
        # A direct collection member may take its native path. A named
        # dynamic dispatch owns a state synchronization boundary throughout.
        external_actuals=bool(native_mode is None and self.scope is None
                              and self.static_module_names and not self.static_module_kinds)
        self.external_actuals+=external_actuals
        try:
            return self._dynamic_call(bound,node,references,call_token,native_mode,argument_guard)
        finally:
            self.external_actuals-=external_actuals

    def callback_module_slot(self,node):
        if not self.import_names:return -1
        if type(node) is bsl.New and node.name.casefold() in ('callbackdescription','описаниеоповещения'):
            return 1
        if type(node) is bsl.Call and type(node.callee) is bsl.Name:
            name=node.callee.name.casefold()
            if name in ('readjson','прочитатьjson'):return 5
            if name in ('writejson','записатьjson'):return 4
        return -1

    def _dynamic_call(self,bound,node,references,call_token,native_mode,argument_guard):
        t=call_token or (node.callee.token if type(node) is bsl.Call else node.token);temporary=self.temp()
        setup=[self.node(py.NamedExpr,t,target=self.name(temporary,t,True),value=bound)]
        omitted=tuple(i for i,arg in enumerate(node.arguments) if type(arg) is bsl.OmittedArgument)
        if omitted:
            prepared=self.temp();defaults=self.temp()
            setup.append(self.node(py.NamedExpr,t,target=self.name(prepared,t,True),value=self.call('_host_omission_values',[self.name(temporary,t),self.const(omitted,t),self.const(len(node.arguments),t)],t)))
            for target,index in ((temporary,0),(defaults,1)):
                setup.append(self.node(py.NamedExpr,t,target=self.name(target,t,True),value=self.node(py.Subscript,t,value=self.name(prepared,t),slice=self.const(index,t),ctx=py.Load())))
        if self.source_scopes and references:
            def is_name(arg):
                while type(arg) is bsl.Group:arg=arg.expression
                return type(arg) is bsl.Name
            call=self.invoke(self.attribute(self.name(temporary,t),'prepare_argument_shapes',t),[self.const(tuple(is_name(arg) for arg in node.arguments),t)],t)
            has=self.call('hasattr',[self.name(temporary,t),self.const('prepare_argument_shapes',t)],t)
            if native_mode is not None:has=self.node(py.BoolOp,t,op=py.And(),values=[self.node(py.UnaryOp,t,op=py.Not(),operand=self.name(native_mode,t)),has])
            setup.append(self.node(py.IfExp,t,test=has,body=call,orelse=self.const(None,t)))
        def requires_reference(index):
            check=self.invoke(self.attribute(self.name(temporary,t),'requires_reference',t),[self.const(index,t)],t)
            if native_mode is None:return check
            return self.node(py.BoolOp,t,op=py.And(),values=[self.node(py.UnaryOp,t,op=py.Not(),operand=self.name(native_mode,t)),check])
        args=[];module_slot=self.callback_module_slot(node)
        for index,arg in enumerate(node.arguments):
            if index in omitted:
                args.append(self.node(py.Subscript,t,value=self.name(defaults,t),slice=self.const(index,t),ctx=py.Load()));continue
            if index==module_slot:
                path=self.import_path(arg)
                if path is not None:
                    accepted=self.call('getattr',[self.name(temporary,t),self.const('accepts_callback_module',t),self.const(False,t)],t)
                    test=self.node(py.Compare,t,left=accepted,ops=[py.Is()],comparators=[self.const(True,t)])
                    owner=self.invoke(self.attribute(self.name('_context',t),'import_callback_module',t),[self.const(path,t)],t)
                    args.append(self.node(py.IfExp,t,test=test,body=owner,orelse=self.expr(arg)));continue
            if not references:
                args.append(self.expr(arg));continue
            plain=arg
            while type(plain) is bsl.Group:plain=plain.expression
            if self.import_path(plain) is not None:
                requires=requires_reference(index)
                args.append(self.node(py.IfExp,t,test=requires,body=self.output_reference(plain),orelse=self.expr(plain)));continue
            if type(plain) in (bsl.Index,bsl.Attribute):
                requires=requires_reference(index)
                args.append(self.access_argument(plain,requires,t));continue
            value=self.expr(arg)
            if self.implicit_module_receiver(plain):
                # Read-only implicit self binds as a disposable byref actual,
                # never as a writable name in the public module dictionary.
                args.append(value)
                continue
            if type(plain) is bsl.Name:
                self.check_name(plain.name)
                def reference():
                    key=plain.name.casefold()
                    if self.external_name(key):return self.invoke(self.attribute(self.name('_context',t),'external_reference',t),[self.const(key,t)],t)
                    if self.scope is not None and key not in self.scope['globals']:
                        if key not in self.scope['bindings']:
                            return self.call('_missing',[self.const(plain.name,plain.token)],plain.token)
                        getter,setter=self.scope['host_helpers'][key]
                        args=[self.name(getter,plain.token),self.name(setter,plain.token),self.const(plain.name,plain.token)]
                        if key in self.scope['boxed']:args.append(self.name(self.scope['slots'][key],plain.token))
                        if self.native_cells:
                            if key not in self.scope['boxed']:args.append(self.const(None,plain.token))
                            args += [self.name('_cell_activation',plain.token),self.name('_context',plain.token)]
                            return self.call('_native_host_reference',args,plain.token)
                        return self.call('_host_name_reference',args,plain.token)
                    return self.call('_host_reference',[self.name('_initial',plain.token),self.const(plain.name,plain.token)],plain.token)
                has=self.call('hasattr',[self.name(temporary,t),self.const('prepare_named_value',t)],t)
                if native_mode is not None:has=self.node(py.BoolOp,t,op=py.And(),values=[self.node(py.UnaryOp,t,op=py.Not(),operand=self.name(native_mode,t)),has])
                prepared=self.invoke(self.attribute(self.name(temporary,t),'prepare_named_value',t),[reference()],t)
                value=self.node(py.IfExp,t,test=has,body=prepared,orelse=value)
                byref=reference()
            else:
                # Ordinary host-reference semantics use the expression value
                # for non-name arguments. Share no mutable Python AST nodes.
                # Select a call result, not duplicate emission of its subtree.
                requires=requires_reference(index)
                pair=self.node(py.Tuple,t,elts=[requires,value],ctx=py.Load())
                args.append(self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load()));continue
            requires=requires_reference(index)
            args.append(self.node(py.IfExp,t,test=requires,body=byref,orelse=value))
        if argument_guard is not None:
            packed=self.node(py.Tuple,t,elts=[*args,argument_guard],ctx=py.Load())
            actuals=self.node(py.Subscript,t,value=packed,slice=self.node(py.Slice,t,lower=None,upper=self.const(-1,t),step=None),ctx=py.Load())
            args=[self.node(py.Starred,t,value=actuals,ctx=py.Load())]
        invoked=self.invoke(self.name(temporary,t),args,t)
        pair=self.node(py.Tuple,t,elts=[*setup,invoked],ctx=py.Load())
        return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())

    def truth(self,node,token):
        if type(node) is bsl.Literal:
            if type(node.value) is bool:return self.expr(node)
            if not self.catalog_bounds and type(node.value) is Decimal:return self.literal(node.value!=0,token)
        kind=self.scalar_kinds.get(id(node))
        if kind=='bool':return self.expr(node)
        if kind=='number':
            return self.node(py.Compare,token,left=self.expr(node),ops=[py.NotEq()],comparators=[self.const(0,token)])
        return self.call('_truth',[self.expr(node)],token)
    def goto_signal(self,target,t):
        return self.node(py.Raise,t,exc=self.call('_GotoTransfer',[self.const(target,t)],t),cause=self.const(None,t))
    def loop_transfer(self,continuing,t):
        if not self.loop_increments:_reject(('Continue' if continuing else 'Break')+' outside a loop')
        if self.goto_dispatch and self.goto_dispatch[-1][0]==len(self.loop_increments):
            code=-3 if continuing else -2
            self.goto_dispatch[-1][1].add(code)
            return [self.goto_signal(code,t)]
        if continuing:
            increment=self.loop_increments[-1]
            return ([self.increment(*increment)] if increment else [])+[self.node(py.Continue,t)]
        return [self.node(py.Break,t)]
    def goto_sequence(self,nodes):
        """Emit a restart loop only for a list with outward jumps into its labels."""
        t=nodes[0].token; pc=self.temp(); caught=self.temp()
        segments=[(-1,[])]
        for node in nodes:
            number=self.goto_destinations.get(id(node))
            if number is None:segments[-1][1].append(node)
            else:segments.append((number,[]))
        def assign(value,token):
            return self.node(py.Assign,token,targets=[self.name(pc,token,True)],value=value)
        def at(value):
            return self.node(py.Compare,t,left=self.name(pc,t),ops=[py.Eq()],comparators=[self.const(value,t)])
        loop_controls=set();self.goto_dispatch.append((len(self.loop_increments),loop_controls))
        try:
            arms=[]
            for i,(number,body) in enumerate(segments):
                following=segments[i+1][0] if i+1<len(segments) else -4
                pattern=self.node(py.MatchValue,t,value=self.const(number,t))
                arms.append(self.node(py.match_case,t,pattern=pattern,guard=None,
                    body=[assign(self.const(following,t),t),*(stmt for node in body for stmt in self.statement(node))]))
        finally:self.goto_dispatch.pop()
        target=self.attribute(self.name(caught,t),'target',t)
        allowed=tuple(number for number,_ in segments[1:])+tuple(sorted(loop_controls))
        valid=self.node(py.Compare,t,left=target,ops=[py.In()],comparators=[self.const(allowed,t)])
        on_jump=self.node(py.If,t,test=valid,body=[assign(target,t)],orelse=[self.node(py.Raise,t,exc=None,cause=None)])
        catch=self.node(py.ExceptHandler,t,type=self.name('_GotoTransfer',t),name=caught,body=[on_jump])
        dispatch=self.node(py.Match,t,subject=self.name(pc,t),cases=arms)
        attempt=self.node(py.Try,t,body=[dispatch],handlers=[catch],orelse=[],finalbody=[])
        live=self.node(py.Compare,t,left=self.name(pc,t),ops=[py.GtE()],comparators=[self.const(-1,t)])
        loop=self.checkpoint_loop(self.node(py.While,t,test=live,body=[attempt],orelse=[]),t)
        result=[assign(self.const(-1,t),t),loop]
        for code in sorted(loop_controls):
            result.append(self.node(py.If,t,test=at(code),body=self.loop_transfer(code==-3,t),orelse=[]))
        return result
    def sequence(self,nodes):
        if self.goto_destinations and any(id(node) in self.goto_destinations for node in nodes):
            return self.goto_sequence(nodes)
        if self.has_goto and any(type(node) is bsl.Goto for node in nodes):
            prefix,cycle,cyclic=_goto_order(nodes)
            result=[]
            for node in prefix:result.extend(self.statement(node))
            if cyclic:
                _goto_cycle_check(cycle)
                if self.scope is not None:
                    # Routine-name shadowing uses a compile-time initialized
                    # fact. Do not freeze a fact that changes on a back edge.
                    pending=list(cycle)
                    while pending:
                        item=pending.pop()
                        if type(item) is bsl.Name and item.name.casefold() in self.routines and item.name.casefold() not in self.scope['initialized']:
                            _reject('Goto cycle with possibly uninitialized routine shadow is not supported yet')
                        if isinstance(item,bsl.Node):pending.extend(getattr(item,f.name) for f in fields(item) if f.name!='token')
                        elif type(item) in (list,tuple):pending.extend(item)
                body=[]
                for node in cycle:body.extend(self.statement(node))
                token=(cycle or nodes)[0].token
                condition=self.const(True,token)
                if self.authority and not self.standalone_script:
                    check=self.invoke(self.attribute(self.name('_context',token),'checkpoint',token),[],token)
                    condition=self.node(py.Subscript,token,value=self.node(py.Tuple,token,elts=[check,condition],ctx=py.Load()),slice=self.const(-1,token),ctx=py.Load())
                result.append(self.node(py.While,token,test=condition,
                    body=body or [self.node(py.Pass,token)],orelse=[]))
            return result
        result=[]
        for node in nodes:result.extend(self.statement(node))
        return result
    def loop_body(self,nodes,increment):
        self.loop_increments.append(increment)
        changes=set()
        journals=self.scope.setdefault('initialization_journals',[]) if self.scope is not None else None
        if journals is not None:journals.append(changes)
        try:return self.sequence(nodes)
        finally:
            self.loop_increments.pop()
            if journals is not None:
                journals.pop();self.scope['initialized'].difference_update(changes)
    def increment(self,name,t):
        value=self.node(py.BinOp,t,left=self.read(name,t),op=py.Add(),right=self.const(1,t))
        return self.assign_name(name,value,t)
    def checkpoint_loop(self,loop,t):
        if self.authority and not self.standalone_script:
            call=self.invoke(self.attribute(self.name('_context',t),'checkpoint',t),[],t)
            pair=self.node(py.Tuple,t,elts=[call,loop.test],ctx=py.Load())
            loop.test=self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        return loop

    def plain_array_loop(self,node,slow):
        """Move liveness checks out of an exact native append loop."""
        if (self.has_goto or self.catalog_bounds or self.region_active or len(node.body)!=1
                or self.source_scopes and not self.authority):
            return slow
        start,end=node.start,node.end
        if (type(start) is not bsl.Literal or type(end) is not bsl.Literal
                or type(start.value) is not Decimal or type(end.value) is not Decimal
                or not start.value.is_finite() or not end.value.is_finite() or start.value>end.value):
            return slow
        statement=node.body[0]
        call=statement.expression if type(statement) is bsl.ExpressionStatement else None
        if type(call) is not bsl.Call or type(call.callee) is not bsl.Attribute or len(call.arguments)!=1:
            return slow
        member=call.callee;array=member.object;value=call.arguments[0]
        if (member.name.casefold() not in ('add','добавить') or type(array) is not bsl.Name
                or type(value) is not bsl.Name or value.name.casefold()!=node.name.casefold()
                or array.name.casefold()==node.name.casefold()):
            return slow
        for name in (array.name,node.name):
            key=name.casefold()
            if (self.external_name(name) or key in self.import_names or key in self.shadowable
                    or key in self.module_cells or key in ('thisobject','этотобъект')
                    or self.scope is not None and (key in self.scope['boxed'] or key in self.scope['shadows'])):
                return slow

        # Prefix (including the initial counter write) is identical. In
        # particular, dropping the old value can invoke a Python finalizer.
        t=array.token;receiver=self.temp()
        value_of_array=self.read(array.name,t)
        bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=value_of_array)
        check=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t)
        exact=self.call('_plain_append_receiver',[bind],t)
        pair=self.node(py.Tuple,t,elts=[check,exact],ctx=py.Load())
        eligible=exact if self.standalone_script else self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if self.authority and not self.standalone_script:
            # The metered path keeps its own checkpoint and error order.
            unmetered=self.call('_plain_array_loop',[self.name('_context',t)],t)
            eligible=self.node(py.BoolOp,t,op=py.And(),values=[unmetered,eligible])
        append=self.node(py.Expr,member.token,value=self.call('_list_append',[self.name(receiver,t),self.read(node.name,value.token)],member.token))
        generic=slow[-1]
        fast=self.node(py.While,node.token,test=deepcopy(generic.test),body=[append,self.increment(node.name,node.token)],orelse=[])
        self.checkpoint_loop(generic,node.token)
        finished=self.node(py.Expr,t,value=deepcopy(check))
        chosen=self.node(py.If,t,test=eligible,body=[fast] if self.standalone_script else [fast,finished],orelse=[generic])
        return [*slow[:-1],chosen]

    def statement(self,node):
        t=node.token
        before_boundaries=self.module_boundaries
        statement_boundary=bool(self.static_module_names and not self.static_module_kinds and type(node) is bsl.Assign and (type(node.target) is bsl.Name and self.external_name(node.target.name)))
        result=[]
        if statement_boundary:
            self.module_boundaries+=1
            result.append(self.node(py.Expr,t,value=self.module_sync(t,False)))
            result.append(self.node(py.AugAssign,t,target=self.name('_dynamic_depth',t,True),op=py.Add(),value=self.const(1,t)))
        if self.catalog_bounds:result.append(self.node(py.Expr,t,value=self.invoke(self.attribute(self.name('_context',t),'preparation_step',t),[],t)))
        def reset():return self.node(py.Assign,t,targets=[self.name('_collection_fast',t,True)],value=self.const(False,t))
        if self.region_active and ((type(node) is bsl.Assign and type(node.value) is bsl.New) or (type(node) is bsl.ExpressionStatement and type(node.expression) is bsl.Call and id(node.expression) not in self.region_ops)):
            result.append(reset())
        if self.region_active and type(node) is bsl.For and id(node) in self.region_states:
            specification,writes=self.region_states[id(node)]
            # Compile-owned immutable-by-convention proof metadata, like old repr literals.
            metadata=self.node(py.Dict,t,keys=[self.const(key,t) for key in specification],values=[self.const(value,t) for value in specification.values()])
            state=self.name('_initial',t)
            if self.scope is not None:
                # No locals() snapshot or retained temporary: a new observer
                # would extend unrelated host-object/finalizer lifetimes.
                keys=sorted((set(specification)|set(writes)) & (self.scope['initialized']|self.scope['globals']))
                values=[self.invoke(self.attribute(self.name('_initial',t),'get',t),[self.const(key,t),self.const(None,t)],t) if key in self.scope['globals'] else self.name(self.scope['slots'][key],t) for key in keys]
                state=self.node(py.Dict,t,keys=[self.const(key,t) for key in keys],values=values)
            admission=self.call('_collection_admitted',[self.name('_context',t),state,metadata,self.const(writes,t)],t)
            if self.scope is not None:
                safe=self.call('_routine_region_state_safe',[self.name('_initial',t)],t)
                admission=self.node(py.BoolOp,t,op=py.And(),values=[safe,admission])
            result.append(self.node(py.Assign,t,targets=[self.name('_collection_fast',t,True)],value=admission))
        emitted=self._statement(node)
        if self.authority and not self.standalone_script and type(node) in (bsl.For,bsl.While,bsl.ForEach):
            for loop in emitted:
                if type(loop) is py.While:self.checkpoint_loop(loop,t)
        result.extend(emitted)
        if statement_boundary:
            result.append(self.node(py.Expr,t,value=self.module_sync(t,True)))
            result.append(self.node(py.AugAssign,t,target=self.name('_dynamic_depth',t,True),op=py.Sub(),value=self.const(1,t)))
        if self.region_active and type(node) is bsl.For:result.append(reset())
        if self.static_module_names and self.module_boundaries!=before_boundaries:
            reload=self.node(py.Expr,t,value=self.module_sync(t,True))
            clear=self.node(py.Assign,t,targets=[self.name('_dynamic_depth',t,True)],value=self.const(0,t))
            cleanup=self.node(py.If,t,test=self.name('_dynamic_depth',t),body=[reload,clear],orelse=[])
            # A successful boundary expression already balances its depth and
            # reloads. Only an exception can interrupt that sequence.
            rethrow=self.node(py.Raise,t,exc=None,cause=None)
            recover=self.node(py.ExceptHandler,t,type=None,name=None,body=[cleanup,rethrow])
            result=[self.node(py.Try,t,body=result,handlers=[recover],orelse=[],finalbody=[])]
        return result
    def without_module_facts(self, lower, node, *args, keep_integer_lane=False):
        # Still lower and validate the whole source. A proven-dead arm has
        # neither closed facts nor a live register file to synchronize.
        kinds,names,integer=self.static_module_kinds,self.static_module_names,self.integer_lane
        self.static_module_kinds,self.static_module_names,self.integer_lane={},{},integer and keep_integer_lane
        try:return lower(node,*args)
        finally:self.static_module_kinds,self.static_module_names,self.integer_lane=kinds,names,integer

    def _statement(self,node):
        self.visits+=1;t=node.token;k=type(node)
        if k is bsl.Label:return []
        if k is bsl.Goto:return [self.goto_signal(self.goto_transfers[id(node)],t)]
        if k is bsl.Execute:
            call=self.call('_execute_fragment',[self.expr(node.expression),*self.fragment_arguments(t)],t)
            if self.static_module_names:call=self.module_boundary(call,t)
            return [self.node(py.Expr,t,value=call)]
        if k is bsl.Assign and self.import_path(node.target) is not None:
            path=self.import_path(node.target)
            if len(path)==1:
                call=self.invoke(self.attribute(self.name('_context',t),'external_set',t),[self.const(path[0],t),self.expr(node.value)],t)
                return [self.node(py.Expr,t,value=call)]
            slot=self.temp()
            resolve=self.invoke(self.attribute(self.name('_context',t),'resolve_import_write',t),[self.const(path,t)],t)
            return [self.node(py.Assign,t,targets=[self.name(slot,t,True)],value=resolve),
                    self.node(py.Expr,t,value=self.invoke(self.name(slot,t),[self.expr(node.value)],t))]
        if k is bsl.Assign and type(node.target) is bsl.Name:
            value=self.expr(node.value)
            return [self.assign_name(node.target.name,value,node.target.token)]
        if k is bsl.Assign and type(node.target) is bsl.Index:
            if self.static_module_kinds:
                target=node.target;receiver=self.temp();index=self.temp();stored=self.temp()
                def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
                body=[assign(receiver,self.expr(target.object)),assign(index,self.expr(target.index)),assign(stored,self.expr(node.value))]
                if self.static_module_kinds[id(target.object)]=='map':
                    write=self.call('_native_dict_setitem',[self.name(receiver,t),self.name(index,t),self.name(stored,t)],t)
                    body.append(self.node(py.Expr,t,value=write));return body
                position=(self.call('_checked_array_index',[self.name(receiver,t),self.name(index,t)],t)
                          if self.address_routine_symbols else self.call('int',[self.name(index,t)],t))
                slot=self.node(py.Subscript,t,value=self.name(receiver,t),slice=position,ctx=py.Store())
                body.append(self.node(py.Assign,t,targets=[slot],value=self.name(stored,t)));return body
            target=node.target;receiver=self.temp();writer=self.temp();index=self.temp();stored=self.temp()
            def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
            def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            resolver=self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__setitem__',t)],t)
            selected=self.node(py.IfExp,t,test=native,body=self.const(None,t),orelse=resolver)
            body=[assign(receiver,self.expr(target.object)),assign(writer,selected),assign(index,self.expr(target.index)),assign(stored,self.expr(node.value))]
            invoke=self.node(py.Expr,t,value=self.invoke(self.name(writer,t),[self.name(index,t),self.name(stored,t)],t))
            checked=self.call('_checked_array_index',[self.name(receiver,t),self.name(index,t)],t)
            position=self.node(py.IfExp,t,test=exact('list'),body=checked,orelse=self.name(index,t))
            slot=self.node(py.Subscript,t,value=self.name(receiver,t),slice=position,ctx=py.Store())
            write=self.node(py.Assign,t,targets=[slot],value=self.name(stored,t))
            test=self.node(py.Compare,t,left=self.name(writer,t),ops=[py.IsNot()],comparators=[self.const(None,t)])
            body.append(self.node(py.If,t,test=test,body=[invoke],orelse=[write]));return self.receiver_statements(body,receiver,t)
        if k is bsl.Assign and type(node.target) is bsl.Attribute:
            if self.local_field_facts.get(id(node))=='structure':
                target=node.target
                call=self.call('_structure_set_known',[self.expr(target.object),self.const(target.name.casefold(),t),self.const(target.name,t),self.expr(node.value)],t)
                return [self.node(py.Expr,t,value=call)]
            if self.static_module_kinds:
                target=node.target;owner=self.static_module_kinds[id(target.object)]
                receiver=self.expr(target.object);value=self.expr(node.value)
                if owner=='item':
                    return [self.node(py.Assign,t,targets=[self.node(py.Subscript,t,value=receiver,slice=self.const(0,t),ctx=py.Store())],value=value)]
                write=self.invoke(self.attribute(receiver,'set_member',t),[self.const(target.name,t),value],t)
                return [self.node(py.Expr,t,value=write)]
            target=node.target;receiver=self.temp();writer=self.temp();stored=self.temp()
            def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
            def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            resolver=self.invoke(self.attribute(self.name('_context',t),'resolve_set_member',t),[self.name(receiver,t),self.const(target.name,t)],t)
            selected=self.node(py.IfExp,t,test=native,body=self.const(None,t),orelse=resolver)
            item_field=_VALUE_LIST_ITEM_FIELDS.get(target.name.casefold())
            if item_field is not None:selected=self.node(py.IfExp,t,test=exact('_PlainValueListItem'),body=self.const(None,t),orelse=selected)
            if self.region_active and self.region_ops.get(id(node))=='row_set':
                selected=self.region_selected(selected,'row_set',receiver,t,[self.const(target.name,t)])
            body=[assign(receiver,self.expr(target.object)),assign(writer,selected),assign(stored,self.expr(node.value))]
            invoke=self.node(py.Expr,t,value=self.invoke(self.name(writer,t),[self.name(stored,t)],t))
            slot=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(target.name,t),ctx=py.Store())
            write=self.node(py.Assign,t,targets=[slot],value=self.name(stored,t))
            if item_field is not None:
                itemslot=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(item_field,t),ctx=py.Store())
                itemvalue=self.name(stored,t)
                if item_field in (1,2):
                    normalizer='_normalize_item_presentation' if item_field == 1 else '_normalize_item_check'
                    itemvalue=self.call(normalizer,[itemvalue],t)
                itemwrite=self.node(py.Assign,t,targets=[itemslot],value=itemvalue)
                write=self.node(py.If,t,test=exact('_PlainValueListItem'),body=[itemwrite],orelse=[write])
            absent=self.node(py.Compare,t,left=self.name(writer,t),ops=[py.Is()],comparators=[self.const(None,t)])
            branch=self.node(py.If,t,test=absent,body=[write],orelse=[invoke])
            map_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_PlainMap'),exact('dict'),exact('_TypedMap'),exact('_NakedMap')])
            fail=self.node(py.Expr,t,value=self.call('_native_property_write_missing',[self.const(target.name,t)],t))
            body.append(self.node(py.If,t,test=map_test,body=[fail],orelse=[branch]));return self.receiver_statements(body,receiver,t)
        if k is bsl.Return:
            if self.scope is None:_reject('module Return outside research subset')
            value=self.expr(node.value) if node.value is not None else self.const(None,t)
            if self.scalar_routines:value=self.invoke(self.attribute(self.name('_context',t),'scalar_result',t),[value],t)
            return [self.node(py.Return,t,value=value)]
        if k is bsl.Var:
            result=[]
            for name in node.names:
                self.check_name(name)
                if self.static_module_names and name.casefold() in self.static_module_names:
                    slot=self.name(self.static_module_names[name.casefold()],t)
                    absent=self.node(py.Compare,t,left=slot,ops=[py.Is()],comparators=[self.name('_UNSET',t)])
                    assign=self.node(py.Assign,t,targets=[self.name(self.static_module_names[name.casefold()],t,True)],value=self.const(None,t))
                    result.append(self.node(py.If,t,test=absent,body=[assign],orelse=[]));continue
                if self.scope is not None and name.casefold() not in self.scope['globals']:
                    if name.casefold() in self.scope['boxed']:
                        slot=self.name(self.scope['slots'][name.casefold()],t)
                        raw=self.node(py.Subscript,t,value=slot,slice=self.const(0,t),ctx=py.Load()) if self.native_cells else self.attribute(slot,'_value',t)
                        test=self.node(py.Compare,t,left=raw,ops=[py.Is()],comparators=[self.name('_UNSET_REF',t)])
                        assign=self.node(py.Assign,t,targets=[self.target(name,t)],value=self.const(None,t))
                        result.append(self.node(py.If,t,test=test,body=[assign],orelse=[]));continue
                    if name.casefold() not in self.scope['initialized']:
                        result.append(self.node(py.Assign,t,targets=[self.target(name,t)],value=self.const(None,t)))
                    continue
                result.append(self.node(py.Expr,t,value=self.invoke(self.attribute(self.name('_initial',t),'setdefault',t),[self.const(name.casefold(),t),self.const(None,t)],t)))
            return result
        if k is bsl.ExpressionStatement:
            value=self.expr(node.expression,node is self.require_last_expression)
            return [self.node(py.Return if self.has_goto and node is self.goto_last_expression else py.Expr,t,value=value)]
        if k is bsl.If:
            branches=[];initialized_paths=[]
            def branch_sequence(body):
                if self.scope is None:return self.sequence(body)
                # Journal only newly initialized locals, not a copy of all locals
                # per branch. Sibling branches must start from the same facts.
                changes=set();journals=self.scope.setdefault('initialization_journals',[])
                journals.append(changes)
                try:return self.sequence(body)
                finally:
                    journals.pop();self.scope['initialized'].difference_update(changes)
                    initialized_paths.append(changes)
            proven=bool(self.static_module_kinds and self.literal_reachability)
            for condition,body,live_test,live_body,literal in ordered_if(node,literal_reachability=proven):
                if condition is not OTHERWISE:
                    if literal is not None:
                        # Extended reachability does not replace a test that
                        # could raise, nor skip validation of its dead operand.
                        test=(self.literal(literal,condition.token)
                              if _simple_literal_boolean(condition) is not None
                              else self.without_module_facts(self.truth,condition,t,keep_integer_lane=True))
                    else:
                        test=self.truth(condition,t) if live_test else self.without_module_facts(self.truth,condition,t)
                emitted=(branch_sequence(body) if live_body else
                         self.without_module_facts(branch_sequence,body))
                if condition is OTHERWISE:
                    tail=emitted
                    break
                branches.append(self.node(py.If,t,test=test,body=emitted or [self.node(py.Pass,t)],orelse=[]))
            if self.scope is not None:
                common=initialized_paths[0].intersection(*initialized_paths[1:])
                for key in common:self.initialize_local(key)
            for branch in reversed(branches):branch.orelse=tail;tail=[branch]
            return tail
        if k is bsl.For:
            routine_path=self.native_cells and bool(self.routines) and node.name.casefold() in self.static_module_names
            local_path=self.scope is None and node.name.casefold() in self.static_module_names and not self.authority and not self.catalog_bounds and not self.source_scopes
            if (not self.table_prefix and (self.static_module_kinds or routine_path or local_path)
                    and type(node.start) is bsl.Literal and type(node.end) is bsl.Literal):
                start,end=node.start.value,node.end.value
                pending=list(node.body);mutated=False
                while pending:
                    value=pending.pop()
                    if type(value) is bsl.Assign and type(value.target) is bsl.Name and value.target.name.casefold()==node.name.casefold():mutated=True
                    if type(value) in (bsl.For,bsl.ForEach) and value.name.casefold()==node.name.casefold():mutated=True
                    if routine_path and not self.static_module_kinds:
                        # Preserve the existing direct-routine path: an
                        # opaque call or passing the counter by reference
                        # still requires the live counter loop.
                        if type(value) in (bsl.Execute,bsl.DynamicNew):mutated=True
                        if type(value) is bsl.Call:
                            callee=value.callee
                            if type(callee) is not bsl.Name or callee.name.casefold() not in self.routines:mutated=True
                            else:
                                for parameter,arg in zip(self.routines[callee.name.casefold()].parameters,value.arguments):
                                    while type(arg) is bsl.Group:arg=arg.expression
                                    if not parameter.by_value and type(arg) is bsl.Name and arg.name.casefold()==node.name.casefold():mutated=True
                    elif not self.static_module_kinds:
                        # Unknown calls, including known routines that may write
                        # module globals, can change the induction variable.
                        # A call elsewhere in the module does not affect this loop.
                        if type(value) in (bsl.Execute,bsl.DynamicNew,bsl.Call,bsl.New):mutated=True
                        if type(value) is bsl.Attribute and id(value) in self.local_field_facts:continue
                        if type(value) in (bsl.Attribute,bsl.Index):mutated=True
                        if type(value) in (bsl.Name,bsl.Binary,bsl.Unary) and id(value) not in self.scalar_kinds:mutated=True
                    if type(value) is bsl.Assign and (type(value.target) is bsl.Name or id(value) in self.local_field_facts):pending.append(value.value)
                    elif type(value) is bsl.If and self.static_module_kinds and self.literal_reachability:
                        pending.extend(_live_if_children(value))
                    elif isinstance(value,bsl.Node):pending.extend(getattr(value,f.name) for f in fields(value) if f.name!='token' and not (type(value) is bsl.Literal and f.name=='value'))
                    elif type(value) in (list,tuple):pending.extend(value)
                if not mutated and type(start) is Decimal and type(end) is Decimal and start.is_finite() and end.is_finite() and start.as_tuple().exponent==0 and end.as_tuple().exponent==0:
                    name=node.name.casefold()
                    slot_counter=self.static_module_names.get(name) if self.integer_lane else None
                    counter=slot_counter or self.temp()
                    initialize=self.assign_name(node.name,self.literal(start,t),t)
                    # A counter used only for native indexing need not make a
                    # Decimal and immediately convert it back to int. Other uses
                    # still see Decimal, once per iteration, not per reference.
                    pending=list(node.body);decimal_use=False
                    def is_counter(value):
                        while type(value) is bsl.Group:value=value.expression
                        return type(value) is bsl.Name and value.name.casefold()==name
                    while pending:
                        value=pending.pop()
                        if type(value) is bsl.Name and value.name.casefold()==name:decimal_use=True
                        if type(value) is bsl.Index and is_counter(value.index) and self.static_module_kinds.get(id(value.object))!='valuelist':
                            pending.append(value.object);continue
                        if type(value) is bsl.Call and type(value.callee) is bsl.Attribute and value.callee.name.casefold() in ('get','получить') and len(value.arguments)==1 and is_counter(value.arguments[0]) and self.static_module_kinds.get(id(value.callee.object))!='valuelist':
                            pending.append(value.callee.object);continue
                        if type(value) is bsl.If and self.static_module_kinds and self.literal_reachability:
                            pending.extend(_live_if_children(value))
                        elif isinstance(value,bsl.Node):pending.extend(getattr(value,f.name) for f in fields(value) if f.name!='token' and not (type(value) is bsl.Literal and f.name=='value'))
                        elif type(value) in (list,tuple):pending.extend(value)
                    raw=self.name(counter,t)
                    advance=([] if slot_counter else [self.assign_name(
                        node.name,self.call('_Decimal',[raw],t) if decimal_use and not self.integer_lane else raw,t)])
                    previous=self.range_indices.get(name);self.range_indices[name]=counter
                    body=self.loop_body(node.body,None)
                    if previous is None:self.range_indices.pop(name)
                    else:self.range_indices[name]=previous
                    # For-else keeps the reached counter on Break, and otherwise
                    # publishes the historical post-increment value (or start).
                    final=max(int(start),int(end)+1)
                    done=self.assign_name(node.name,self.literal(Decimal(final),t),t)
                    loop=self.node(py.For,t,target=self.name(counter,t,True),iter=self.call('range',[self.const(int(start),t),self.const(int(end)+1,t)],t),body=[*advance,*body] or [self.node(py.Pass,t)],orelse=[done],type_comment=None)
                    # Internal integer induction must not escape through Break,
                    # an exception, or a following read/append of the BSL slot.
                    slot=self.read(node.name,t)
                    integer=self.node(py.Compare,t,left=self.call('type',[slot],t),ops=[py.Is()],comparators=[self.name('int',t)])
                    normalize=self.assign_name(node.name,self.call('_Decimal',[slot],t),t)
                    cleanup=self.node(py.If,t,test=integer,body=[normalize],orelse=[])
                    if self.integer_lane:return [initialize,loop]
                    return [initialize,self.node(py.Try,t,body=[loop],handlers=[],orelse=[],finalbody=[cleanup])]
            first=self.temp();last=self.temp()
            bounds=[self.node(py.Assign,t,targets=[self.name(first,t,True)],value=self.expr(node.start)),
                    self.node(py.Assign,t,targets=[self.name(last,t,True)],value=self.expr(node.end))]
            if self.scope is not None and not (self.source_scopes or self.host_bindings):
                caught=self.temp()
                convert=self.call('_for_bound_unbound',[self.name(caught,t)],t)
                handler=self.node(py.ExceptHandler,t,type=self.name('UnboundLocalError',t),name=caught,
                    body=[self.node(py.Expr,t,value=convert)])
                bounds=[self.node(py.Try,t,body=bounds,handlers=[handler],orelse=[],finalbody=[])]
            result=[*bounds,self.assign_name(node.name,self.name(first,t),t)]
            body=self.loop_body(node.body,(node.name,t))
            body.append(self.increment(node.name,t))
            condition=self.node(py.Compare,t,left=self.read(node.name,t),ops=[py.LtE()],comparators=[self.name(last,t)])
            result.append(self.node(py.While,t,test=condition,body=body,orelse=[]));return self.plain_array_loop(node,result)
        if k is bsl.ForEach:
            self.check_name(node.name)
            if self.scope is None and self.static_module_kinds.get(id(node.collection))=='array':
                slot=self.static_module_names[node.name.casefold()]
                body=self.loop_body(node.body,None)
                return [self.node(py.For,t,target=self.name(slot,t,True),iter=self.expr(node.collection),
                                  body=body or [self.node(py.Pass,t)],orelse=[],type_comment=None)]
            receiver=self.temp();bound=self.temp();iterator=self.temp();key=self.temp();value=self.temp()
            def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
            def exact(kind):return self.exact_native(kind,self.name(receiver,t),t)
            entry=self.call('_MapEntry',[],t,[self.node(py.keyword,t,arg='key',value=self.name(key,t)),self.node(py.keyword,t,arg='value',value=self.name(value,t))])
            pair=self.node(py.Tuple,t,elts=[self.name(key,t,True),self.name(value,t,True)],ctx=py.Store())
            items=self.invoke(self.attribute(self.name(receiver,t),'items',t),[],t)
            generator=self.node(py.GeneratorExp,t,elt=entry,generators=[py.comprehension(target=pair,iter=items,ifs=[],is_async=0)])
            dictionary=self.call('isinstance',[self.name(receiver,t),self.name('dict',t)],t)
            iterable=self.node(py.IfExp,t,test=dictionary,body=generator,orelse=self.name(receiver,t))
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_PlainMap','_TypedMap','_NakedMap','_DirectStructure')])
            host=self.invoke(self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__iter__',t)],t),[],t)
            if not self.owned_constructors:
                # Keep the live item identities and ordinary list traversal.
                # Bind the exact storage operation, not a host __iter__ hook.
                plain=self.invoke(self.attribute(self.name('list',t),'__iter__',t),[self.name(receiver,t)],t)
                host=self.node(py.IfExp,t,test=exact('_PlainValueList'),body=plain,orelse=host)
            selected=self.node(py.IfExp,t,test=native,body=self.call('iter',[iterable],t),orelse=host)
            result=[assign(receiver,self.expr(node.collection)),assign(bound,selected),assign(iterator,self.call('iter',[self.name(bound,t)],t))]
            changes=set();journals=self.scope.setdefault('initialization_journals',[]) if self.scope is not None else None
            if journals is not None:journals.append(changes)
            advance=self.assign_name(node.name,self.call('next',[self.name(iterator,t)],t),t)
            stop=self.node(py.ExceptHandler,t,type=self.name('StopIteration',t),name=None,body=[self.node(py.Break,t)])
            maps=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_PlainMap'),exact('dict'),exact('_TypedMap'),exact('_NakedMap')])
            reraised=self.node(py.If,t,test=self.node(py.UnaryOp,t,op=py.Not(),operand=maps),body=[self.node(py.Raise,t,exc=None,cause=None)],orelse=[])
            converted=self.node(py.Raise,t,exc=self.call('ValueError',[self.const('Изменение состава соответствия во время обхода пока не поддерживается',t)],t),cause=self.const(None,t))
            mutation=self.node(py.ExceptHandler,t,type=self.name('RuntimeError',t),name=None,body=[reraised,converted])
            attempt=self.node(py.Try,t,body=[advance],handlers=[stop,mutation],orelse=[],finalbody=[])
            self.loop_increments.append(None);body=self.sequence(node.body);self.loop_increments.pop()
            if journals is not None:
                journals.pop();self.scope['initialized'].difference_update(changes)
            result.append(self.node(py.While,t,test=self.const(True,t),body=[attempt,*body],orelse=[]));return result
        if k is bsl.While:
            condition=self.truth(node.condition,t)
            body=self.loop_body(node.body,None)
            return [self.node(py.While,t,test=condition,body=body or [self.node(py.Pass,t)],orelse=[])]
        if k is bsl.Break:return self.loop_transfer(False,t)
        if k is bsl.Continue:return self.loop_transfer(True,t)
        if k is bsl.Try:
            paths=[]
            def error_path(nodes):
                if self.scope is None:return self.sequence(nodes)
                changes=set();journals=self.scope.setdefault('initialization_journals',[])
                journals.append(changes)
                try:return self.sequence(nodes)
                finally:
                    journals.pop();self.scope['initialized'].difference_update(changes);paths.append(changes)
            body=error_path(node.body) or [self.node(py.Pass,t)]
            caught=self.temp()
            manager=self.call('_handled_error',[self.name('_context',t),self.name(caught,t),self.const(self.filename,t),self.name('_diagnostic_source',t)],t)
            self.handler_depth+=1
            try:handler=error_path(node.handler)
            finally:self.handler_depth-=1
            handler_body=self.node(py.With,t,items=[py.withitem(context_expr=manager,optional_vars=None)],body=handler or [self.node(py.Pass,t)])
            if self.scope is not None:
                for key in paths[0].intersection(paths[1]):self.initialize_local(key)
            classes=self.node(py.Tuple,t,elts=[self.name(name,t) for name in ('ArithmeticError','ValueError','TypeError','IndexError','RecursionError','_BSLRuntimeError')],ctx=py.Load())
            handler=self.node(py.ExceptHandler,t,type=classes,name=caught,body=[handler_body])
            return [self.node(py.Try,t,body=body,handlers=[handler],orelse=[],finalbody=[])]
        if k is bsl.Raise:
            if node.value is None:value=self.call('_reraise_handled',[self.name('_context',t)],t)
            else:
                description=self.call('_presentation',[self.expr(node.value)],t)
                if len(node.optional_arguments or ())>4:
                    value=self.call('_raise_arity_error',[description],t)
                else:
                    optional=[self.const(None,arg.token) if type(arg) is bsl.OmittedArgument else self.expr(arg) for arg in (node.optional_arguments or ())]
                    value=self.call('_raise_error',[self.name('_context',t),description,self.node(py.Tuple,t,elts=optional,ctx=py.Load()),self.const(self.filename,t),self.const(t.line,t),self.const(t.column,t),self.const(t.source_line,t)],t)
            return [self.node(py.Expr,t,value=value)]
        _reject('unsupported statement '+k.__name__)


def _source_roundtrip(tree,filename):
    """Real source audit parse, then a single paired structural/location walk.

    Both trees are compiler-owned. No subtree strings/dumps or source-position
    search indexes are built. Unsupported unparse normalizations fail closed.
    """
    source=py.unparse(tree)
    parsed=py.parse(source,filename=filename,mode='exec')
    pending=[(tree,parsed)];visited=0
    while pending:
        original,reparsed=pending.pop();visited+=1
        if type(original) is not type(reparsed):_reject('whole-source roundtrip changed executable structure')
        if isinstance(original,py.AST):
            left=dict(py.iter_fields(original));right=dict(py.iter_fields(reparsed))
            if left.keys()!=right.keys():_reject('whole-source roundtrip changed executable fields')
            pending.extend((value,right[name]) for name,value in left.items())
            for attribute in original._attributes:
                if hasattr(original,attribute):setattr(reparsed,attribute,getattr(original,attribute))
        elif type(original) is list:
            if len(original)!=len(reparsed):_reject('whole-source roundtrip changed executable list')
            pending.extend(zip(original,reparsed))
        elif type(original) in (str,int,bool,float,complex,type(None)):
            if original!=reparsed:_reject('whole-source roundtrip changed executable literal')
        else:_reject('whole-source roundtrip contains unsupported metadata')
    return parsed,source,visited


def _routine_region_state_safe(state):
    # Before extra snapshot lookups, reject hostile key equality and mapping
    # overrides. The ordinary path retains its original operation ordering.
    return type(state) is dict and all(type(key) is str for key in state)


def _routine_region(routine, scope):
    """Prove straight-line routine loops with an explicit binding-state lattice.

    Analysis-only numeric seeds never execute. A possibly-bound old local may
    have a finalizer, so an uncertain overwrite disables that loop's fast arm;
    absence is used only when no previous path could have bound the slot.
    """
    if scope['boxed'] or scope['host_helpers']:return 0, {}, {}
    from yadinassi.execution.direct.python_direct_collection_regions import analyze
    seeds=[bsl.Assign(p.token,bsl.Name(p.token,p.name),bsl.Literal(p.token,Decimal(0))) for p in routine.parameters]
    end,operations,states=analyze(seeds+routine.body,opaque_names=scope['externals'])
    end-=len(seeds)
    if end<=0:return 0, {}, {}
    prefix=routine.body[:end]
    top_loops={id(node) for node in prefix if type(node) is bsl.For}
    if not set(states)<=top_loops:return 0, {}, {}  # Nested regions deferred.
    definite={p.name.casefold() for p in routine.parameters};possible=set(definite)
    for node in prefix:
        if type(node) is bsl.Assign and type(node.target) is bsl.Name:
            key=node.target.name.casefold();definite.add(key);possible.add(key)
        elif type(node) is bsl.For:
            specification,writes=states[id(node)]
            relevant=(set(specification)|set(writes))-scope['globals']
            if relevant & (possible-definite):del states[id(node)]
            possible.update(writes)
            definite.add(node.name.casefold());possible.add(node.name.casefold())
    if not states:return 0, {}, {}
    return end,operations,states


def _live_if_children(node):
    for condition,body,live_test,live_body,_ in ordered_if(node,literal_reachability=True):
        if live_test:yield condition
        if live_body:yield from body


def _module_registers(program, emitter, *, literal_reachability):
    names=set();cells=set();pending=list(program)
    while pending:
        value=pending.pop()
        if type(value) is bsl.Routine:continue
        if type(value) is bsl.Call and type(value.callee) is bsl.Name and value.callee.name.casefold() in emitter.routines:
            signature=emitter.routines[value.callee.name.casefold()]
            for parameter,arg in zip(signature.parameters,value.arguments):
                while type(arg) is bsl.Group:arg=arg.expression
                if not parameter.by_value and type(arg) is bsl.Name:
                    cells.add(arg.name.casefold());names.add(arg.name.casefold())
        if type(value) is bsl.Assign and type(value.target) is bsl.Name:names.add(value.target.name.casefold())
        if type(value) is bsl.For:names.add(value.name.casefold())
        if type(value) is bsl.Var:names.update(name.casefold() for name in value.names)
        if type(value) is bsl.If and literal_reachability:
            pending.extend(_live_if_children(value))
        elif isinstance(value,bsl.Node):
            pending.extend(getattr(value,f.name) for f in fields(value) if f.name!='token' and not (type(value) is bsl.Literal and f.name=='value'))
        elif type(value) in (list,tuple):pending.extend(value)
    names-=emitter.external_names|emitter.module_globals|{'thisobject','этотобъект'}
    return names,cells & names


def compile_module(vm,program,nodes,source_text,source_name,*,_exports=False,_whole_source=False,_require_last_expression=False,_profile=None,_source_scopes=False,_authority=False,_scalar_routines=False,_callable_externals=(),_shadowable=(),_configuration_calls=False,_host_bindings=False,_catalog_bounds=False,_lean_configuration=False,_retain_generated=True,_allow_pure_builtins=False,_current_module=False):
    """Lower a module, optionally auditing the generated Python source."""
    if not _native_partial_binding(partial):_reject('noncanonical partial binding is outside research contract')
    if not _native_operator_binding(_NATIVE_ADD,'add') or not _native_operator_binding(_NATIVE_GETITEM,'getitem'):
        _reject('noncanonical operator binding is outside research contract')
    from yadinassi.execution.direct.python_direct_imports import import_names
    imported=import_names(vm,program) if _profile is None else ()
    program=[node for node in program if type(node) is not bsl.Import and
             (_profile is not None or (type(node) is not bsl.ServerInitializer and
              (type(node) not in (bsl.Var,bsl.Routine) or (node.execution_context=='client' and not getattr(node,'is_dual',False)))))]
    count,has_goto,has_label=_bounds(program)
    destinations,transfers,flow_routines=_goto_lists(program) if has_goto or has_label else ({},{},set())
    if not program:
        from yadinassi.syntax.lexer import Token
        token=nodes[0].token if nodes else Token('EOF','',1,1,source_name or '<строка>','')
        program=[bsl.ExpressionStatement(token,bsl.Literal(token,None))]
        if not nodes:nodes=tuple(program)
    filename=source_name or nodes[0].token.source
    if source_text is None:
        lines={node.token.line:node.token.source_line for node in nodes}
        source_text='\n'.join(lines.get(line,'') for line in range(1,max(lines,default=0)+1))
    emitter=Emitter(filename)
    pure_bindings=None
    if _allow_pure_builtins and _profile is None and not _whole_source and not vm.allow_extensions and not imported:
        from yadinassi.execution.direct.python_direct_pure_builtins import analyze
        candidate=analyze(nodes)
        if candidate is not None and candidate.active(vm):
            pure_bindings=candidate
            emitter.pure_builtins={name:'_pure_'+name for name in candidate.services}
    emitter.has_goto=has_goto
    emitter.goto_destinations=destinations;emitter.goto_transfers=transfers
    emitter.current_module=_profile is None or _current_module
    emitter.owned_constructors=_profile is not None;emitter.configuration_calls=_configuration_calls;emitter.host_bindings=_host_bindings;emitter.catalog_bounds=_catalog_bounds;emitter.source_scopes=_source_scopes;emitter.authority=_authority;emitter.scalar_routines=_scalar_routines
    emitter.callable_externals=frozenset(_callable_externals);emitter.shadowable=frozenset(_shadowable)
    emitter.import_names=frozenset(imported);t=program[0].token
    emitter.standalone_script=_lean_configuration or (
        _profile is None and not _authority and not _source_scopes and not vm.allow_extensions)
    emitter.literal_reachability=(emitter.standalone_script and _profile is None and not imported
                                  and vm.database_context is None and not has_goto and not has_label)
    emitter.link_imports=bool(imported) and emitter.standalone_script and (
        vm._family_owner.__dict__.get('_standalone_script') is True)
    if _require_last_expression:emitter.require_last_expression=program[-1]
    from yadinassi.execution.direct.python_direct_services import ORDINARY_CONSTRUCTORS
    from yadinassi.execution.direct.python_direct_value_tree import CONSTRUCTOR_NAMES as TREE_NAMES
    emitter.constructor_names=frozenset(ORDINARY_CONSTRUCTORS)|frozenset(TREE_NAMES)|{'uuid','уникальныйидентификатор'}
    from yadinassi.execution.direct.python_direct_database import NAMES as DATABASE_NAMES, DATABASE_ROOT_NAMES, METADATA_NAMES
    emitter.external_names=set(NAMES)
    emitter.missing_database_roots=DATABASE_ROOT_NAMES if _profile is None and vm.database_context is None else ()
    if emitter.missing_database_roots:emitter.missing_metadata_roots=METADATA_NAMES
    if _profile is None and vm.database_context is not None:
        emitter.external_names.update(DATABASE_NAMES);emitter.constructor_names|={'query','запрос'}
    known_methods=(_profile is None and emitter.standalone_script and not has_goto
            and any(type(node) is bsl.New and node.name.casefold() in
                    ('query','запрос','valuetable','таблицазначений') for node in nodes))
    if known_methods:
        from yadinassi.execution.direct.python_direct_known_methods import analyze as analyze_known
        emitter.known_calls,emitter.known_origins,emitter.known_selection_reads,emitter.known_selection_adds=analyze_known(
            program,database=vm.database_context is not None)
        if not emitter.known_calls:
            emitter.known_origins=set();emitter.known_selection_reads.clear();emitter.known_selection_adds.clear()
    if _profile is not None:
        module_names,external_names,constructors=_profile
        emitter.external_names={name.casefold() for name in external_names}
        emitter.constructor_names=frozenset(name.casefold() for name in constructors)
    else:module_names=vm.module_names
    emitter.routines={node.name.casefold():node for node in program if type(node) is bsl.Routine}
    async_bodies={}
    if any(node.is_async for node in emitter.routines.values()):
        if _profile is not None or vm.database_context is not None:
            _reject('asynchronous routines require a standalone client module')
        from dataclasses import replace
        for name,node in tuple(emitter.routines.items()):
            if node.is_async:
                emitter.routines[name]=replace(node,parameters=[replace(p,by_value=True) for p in node.parameters])
                async_bodies[name]=emitter.temp()

    emitter.native_cells=bool(emitter.routines) and _profile is None and not imported and vm.database_context is None
    # The row address does not depend on the native-cell calling convention.
    # SQLite-attached local routines keep their existing reference ABI.
    emitter.row_cell_references=(bool(emitter.routines) and _profile is None and not imported
                                 and emitter.standalone_script and not async_bodies)
    emitter.routine_symbols={key:emitter.temp() for key in emitter.routines}
    emitter.module_globals={name.casefold() for node in program if type(node) is bsl.Var for name in node.names}|{name.casefold() for name in module_names}
    collisions=emitter.external_names & (emitter.module_globals|emitter.routines.keys())
    if _profile is None and collisions:
        # Do not reserve a previously legal explicit module declaration.
        shadowed=collisions.intersection(XML_CLEANUP_ALIASES)
        emitter.external_names.difference_update(shadowed)
        collisions.difference_update(shadowed)
    if collisions:
        from yadinassi.execution.direct.python_direct import _reject as reject_contract
        reject_contract('external names collide with module declarations')
    conditional_shadow_names=emitter.module_globals|emitter.external_names|{'thisobject','этотобъект'}
    definitions=[];any_region=False
    from yadinassi.execution.direct.python_direct_collection_regions import analyze,admitted,helpers
    for key,routine in emitter.routines.items():
        link_start=len(emitter.import_links)

        declarations=set();assigned=set();pending=[(stmt,False) for stmt in routine.body]
        direct_vars={id(stmt) for stmt in routine.body if type(stmt) is bsl.Var}
        while pending:
            stmt,in_loop=pending.pop();kind=type(stmt)
            if kind is bsl.If:
                pending.extend((child,in_loop) for child in stmt.otherwise)
                for _,branch in stmt.branches:pending.extend((child,in_loop) for child in branch)
            elif kind is bsl.Try:
                pending.extend((child,in_loop) for child in stmt.body)
                pending.extend((child,in_loop) for child in stmt.handler)
            elif kind in (bsl.For,bsl.While,bsl.ForEach):
                if kind in (bsl.For,bsl.ForEach):assigned.add(stmt.name.casefold())
                pending.extend((child,True) for child in stmt.body)
            elif kind is bsl.Assign and type(stmt.target) in (bsl.Name,bsl.Index,bsl.Attribute):
                if type(stmt.target) is bsl.Name:assigned.add(stmt.target.name.casefold())
            elif kind is bsl.Var:
                if in_loop:_reject('routine loop-local Var outside research subset')
                if id(stmt) not in direct_vars and any(name.casefold() in conditional_shadow_names for name in stmt.names):
                    _reject('conditional local Var shadowing module storage is unsupported')
                declarations.update(name.casefold() for name in stmt.names)
            elif kind not in (bsl.Return,bsl.ExpressionStatement,bsl.Break,bsl.Continue,bsl.Raise,bsl.Execute,bsl.Label,bsl.Goto):_reject('routine control flow outside research subset')
        parameters={parameter.name.casefold() for parameter in routine.parameters}
        if id(routine) in flow_routines and (declarations or (assigned|parameters)&emitter.routines.keys()):
            _reject('outward Goto with routine Var or routine-name shadowing is not supported yet')
        globals_=emitter.module_globals-declarations-parameters
        slots={parameter.name.casefold():emitter.temp() for parameter in routine.parameters}
        emitter.scope={'globals':globals_,'externals':emitter.external_names-parameters-declarations,'local_declarations':parameters|{name.casefold() for stmt in routine.body if type(stmt) is bsl.Var for name in stmt.names},'bindings':assigned|declarations|parameters,'initialized':set(parameters),'slots':slots,'boxed':{parameter.name.casefold() for parameter in routine.parameters if not parameter.by_value}}
        if routine.is_async:emitter.scope['async']=True
        shadows=assigned & emitter.shadowable & emitter.scope['externals']-emitter.module_globals
        emitter.scope['shadows']=shadows;emitter.implicit_shadows.update(shadows)
        emitter.scope['externals']-=shadows;emitter.scope['boxed']|=shadows
        # Only names crossing a dynamic host-call argument boundary need
        # lexical getter/setter closures. Do not box every routine local.
        lexical=set();addressable=set();pending=list(routine.body);has_fragments=False
        while pending:
            value=pending.pop()
            callee=value.callee if type(value) is bsl.Call else None
            while type(callee) is bsl.Group:callee=callee.expression
            if type(value) is bsl.Execute or (type(callee) is bsl.Name and callee.name.casefold() in ('eval','вычислить')):has_fragments=True
            if type(value) is bsl.Call:
                actuals=[]
                # Imported calls use the dynamic routine ABI, including its
                # by-reference branch, before native member-name lowering.
                import_call=(type(callee) is bsl.Attribute and emitter.import_names
                             and emitter.import_path(callee) is not None)
                if type(callee) is bsl.Name and callee.name.casefold() in emitter.routines:
                    signature=emitter.routines[callee.name.casefold()]
                    actuals=[arg for parameter,arg in zip(signature.parameters,value.arguments) if not parameter.by_value]
                elif (not import_call and type(callee) is bsl.Attribute and not emitter.implicit_module_receiver(callee.object)
                      and _ALIASES.get(callee.name.casefold(),callee.name.casefold())=='property'):
                    actuals=value.arguments[1:2]
                elif (import_call or type(callee) is not bsl.Attribute or emitter.source_scopes or emitter.host_bindings
                      or emitter.implicit_module_receiver(callee.object)):
                    for arg in value.arguments:
                        while type(arg) is bsl.Group:arg=arg.expression
                        if type(arg) is bsl.Name and arg.name.casefold() not in globals_|emitter.scope['externals']:lexical.add(arg.name.casefold())
                for arg in actuals:
                    while type(arg) is bsl.Group:arg=arg.expression
                    if type(arg) is bsl.Name and arg.name.casefold() not in globals_|emitter.scope['externals']:addressable.add(arg.name.casefold())
            if isinstance(value,bsl.Node):
                pending.extend(getattr(value,field.name) for field in fields(value) if field.name!='token' and not (type(value) is bsl.Literal and field.name=='value'))
            elif type(value) in (list,tuple):pending.extend(value)
        if has_fragments:
            fragment_names=(assigned|declarations|parameters)-globals_-emitter.scope['externals']
            addressable.update(fragment_names)
            emitter.scope['fragment_names']=fragment_names
        emitter.scope['boxed'].update(addressable)
        emitter.scope['bindings'].update(addressable)
        for name in sorted(addressable):
            if name not in slots:slots[name]=emitter.temp()
        # Capture candidates aren't declarations. Ordinary value reads must
        # still reach the BSL missing-name path for a capture-only name.
        # Source/host profiles already give these slots an explicit sentinel.
        if emitter.source_scopes or emitter.host_bindings:
            emitter.scope['bindings'].update(lexical)
        else:
            lexical.intersection_update(emitter.scope['bindings'])
        emitter.scope['host_helpers']={}
        for name in sorted(lexical):
            if name not in slots:slots[name]=emitter.temp()
            emitter.scope['host_helpers'][name]=(emitter.temp(),emitter.temp())
        prologue=[]
        if emitter.source_scopes or emitter.host_bindings:
            for name in emitter.scope['bindings']-emitter.scope['globals']:
                if name not in slots:slots[name]=emitter.temp()
            for name in sorted(emitter.scope['bindings']-parameters-emitter.scope['globals']-emitter.scope['boxed']):
                prologue.append(emitter.node(py.Assign,routine.token,targets=[emitter.name(slots[name],routine.token,True)],value=emitter.name('_UNSET',routine.token)))
        if emitter.scalar_routines:
            actuals=emitter.node(py.Tuple,routine.token,elts=[emitter.name(slots[p.name.casefold()],p.token) for p in routine.parameters],ctx=py.Load())
            prologue.append(emitter.node(py.Expr,routine.token,value=emitter.invoke(emitter.attribute(emitter.name('_context',routine.token),'scalar_values',routine.token),[actuals],routine.token)))
        for parameter in routine.parameters:
            slot=slots[parameter.name.casefold()];token=parameter.token
            test=emitter.node(py.Compare,token,left=emitter.name(slot,token),ops=[py.Is()],comparators=[emitter.name('_OMITTED_REF',token)])
            fallback=emitter.expr(parameter.default) if parameter.default is not None else emitter.const(None,token)
            native_reference=emitter.native_cells and not parameter.by_value
            default=emitter.call('_NativeCell',[fallback],token) if native_reference else fallback
            assign=emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=default)
            if native_reference:
                adapt=emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=emitter.call('_adapt_native_cell',[emitter.name(slot,token),emitter.name('_context',token)],token))
                external=emitter.node(py.If,token,test=emitter.node(py.UnaryOp,token,op=py.Not(),operand=emitter.name('_native_cells',token)),body=[adapt],orelse=[])
                prologue.append(emitter.node(py.If,token,test=test,body=[assign],orelse=[external]))
            else:
                prologue.append(emitter.node(py.If,token,test=test,body=[assign],orelse=[]))
                if parameter.name.casefold() in emitter.scope['boxed']:
                    factory=('_NativeCell' if emitter.native_cells else '_Cell') if parameter.by_value else '_as_ref'
                    prologue.append(emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=emitter.call(factory,[emitter.name(slot,token)],token)))
        for name in sorted(emitter.scope['boxed']-parameters):
            prologue.append(emitter.node(py.Assign,routine.token,targets=[emitter.name(slots[name],routine.token,True)],value=emitter.call('_NativeCell' if emitter.native_cells else '_Cell',[],routine.token)))
        for name,(getter,setter) in emitter.scope['host_helpers'].items():
            slot=slots[name];token=routine.token;boxed=name in emitter.scope['boxed']
            if not boxed:
                declare=emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=emitter.const(None,token))
                prologue.append(emitter.node(py.If,token,test=emitter.const(False,token),body=[declare],orelse=[]))
            target=emitter.read(name,token) if emitter.native_cells or emitter.source_scopes or emitter.host_bindings else (emitter.attribute(emitter.name(slot,token),'value',token) if boxed else emitter.name(slot,token))
            args=py.arguments(posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
            prologue.append(emitter.node(py.FunctionDef,token,name=getter,args=args,body=[emitter.node(py.Return,token,value=target)],decorator_list=[],returns=None,type_comment=None))
            # Compiling a setter is not a BSL assignment to its slot.
            target=emitter.target(name,token,initializes=False) if emitter.native_cells else (emitter.node(py.Attribute,token,value=emitter.name(slot,token),attr='value',ctx=py.Store()) if boxed else emitter.name(slot,token,True))
            assign=emitter.node(py.Assign,token,targets=[target],value=emitter.name('_new',token))
            body=[assign] if boxed else [emitter.node(py.Nonlocal,token,names=[slot]),assign]
            args=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,token,arg='_new',annotation=None)],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
            prologue.append(emitter.node(py.FunctionDef,token,name=setter,args=args,body=body,decorator_list=[],returns=None,type_comment=None))
        if shadows and has_fragments:_reject('source implicit namespace shadow with Execute/Eval is not integrated')
        if known_methods and not imported and not has_fragments and routine.execution_context=='client' and not routine.is_dual:
            # Host getter/setter closures are not an escape by themselves.
            # The known-method analysis ends the lexical phase at a reachable
            # opaque call; dead or later calls need not poison earlier facts.
            local_slots=(assigned|declarations)-parameters-globals_-emitter.scope['externals']-emitter.scope['boxed']
            calls,origins,selection_reads,selection_adds=analyze_known(routine.body,database=vm.database_context is not None,local_slots=local_slots)
            if calls:
                emitter.scope['known_phase']=emitter.temp()
                emitter.known_calls.update(calls)
                emitter.known_origins.update(origins)
                emitter.known_selection_reads.update(selection_reads)
                emitter.known_selection_adds.update(selection_adds)
        routine_end,emitter.region_ops,emitter.region_states=(0,{}, {}) if routine.is_async or has_goto or emitter.authority or emitter.source_scopes else _routine_region(routine,emitter.scope)
        emitter.region_active=bool(routine_end)
        region_body=emitter.sequence(routine.body[:routine_end])
        emitter.region_active=False
        ordinary_body=emitter.sequence(routine.body[routine_end:])
        if routine_end:
            any_region=True
            prologue.append(emitter.node(py.Assign,routine.token,targets=[emitter.name('_collection_fast',routine.token,True)],value=emitter.const(False,routine.token)))
        routine_body=prologue+(region_body+ordinary_body or [emitter.node(py.Pass,routine.token)])
        if emitter.native_cells and lexical:
            activation=emitter.node(py.Assign,routine.token,targets=[emitter.name('_cell_activation',routine.token,True)],value=emitter.node(py.List,routine.token,elts=[emitter.const(True,routine.token)],ctx=py.Load()))
            retire=emitter.node(py.Assign,routine.token,targets=[emitter.node(py.Subscript,routine.token,value=emitter.name('_cell_activation',routine.token),slice=emitter.const(0,routine.token),ctx=py.Store())],value=emitter.const(False,routine.token))
            routine_body=[activation,emitter.node(py.Try,routine.token,body=routine_body,handlers=[],orelse=[],finalbody=[retire])]
        if emitter.source_scopes:
            manager=emitter.invoke(emitter.attribute(emitter.name('_context',routine.token),'routine_scope',routine.token),[],routine.token)
            routine_body=[emitter.node(py.With,routine.token,items=[py.withitem(context_expr=manager,optional_vars=None)],body=routine_body)]
        elif emitter.authority and not emitter.standalone_script:
            check=lambda:emitter.node(py.Expr,routine.token,value=emitter.invoke(emitter.attribute(emitter.name('_context',routine.token),'_check',routine.token),[],routine.token))
            routine_body=[check(),emitter.node(py.Try,routine.token,body=routine_body,handlers=[],orelse=[],finalbody=[check()])]
        emitter.region_ops={};emitter.region_states={}
        emitter.scope=None
        args=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,parameter.token,arg=slots[parameter.name.casefold()],annotation=None) for parameter in routine.parameters],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
        first_optional=next((index for index,parameter in enumerate(routine.parameters) if parameter.default is not None),len(routine.parameters))
        args.defaults=[emitter.name('_OMITTED_REF',routine.token) for _ in routine.parameters[first_optional:]]
        if emitter.native_cells:
            args.kwonlyargs=[emitter.node(py.arg,routine.token,arg='_native_cells',annotation=None)];args.kw_defaults=[emitter.const(False,routine.token)]
        if len(emitter.import_links)>link_start:
            routine_body.insert(0,emitter.node(py.Nonlocal,routine.token,names=emitter.import_links[link_start:]))
        if routine.is_async:
            token=routine.token
            # Even a routine without Await is eagerly started and owns a Promise.
            marker=emitter.node(py.If,token,test=emitter.const(False,token),
                body=[emitter.node(py.Expr,token,value=emitter.node(py.Yield,token,value=None))],orelse=[])
            definitions.append(emitter.node(py.FunctionDef,token,name=async_bodies[key],args=args,
                body=routine_body+[marker],decorator_list=[],returns=None,type_comment=None))
            actuals=emitter.node(py.Tuple,token,elts=[emitter.name(arg.arg,token) for arg in args.args],ctx=py.Load())
            start=emitter.invoke(emitter.attribute(emitter.name('_context',token),'start_async',token),
                [emitter.name('naked_module',token),emitter.name('_constants',token),
                 emitter.const('@async:'+key,token),actuals,emitter.const(not routine.is_function,token)],token)
            routine_body=[emitter.node(py.Return,token,value=start)]
        definitions.append(emitter.node(py.FunctionDef,routine.token,name=emitter.routine_symbols[key],args=args,body=routine_body,decorator_list=[],returns=None,type_comment=None))
    # Module locals are the register file; dynamic edges explicitly synchronize.
    static_facts=None
    table_prefix_end=0;table_prefix_start=0;table_prefix_origin=0;table_prefix_kinds={};extended_tests=set()
    builtin_results=None
    if pure_bindings is not None:
        from yadinassi.execution.direct.python_direct_pure_builtins import result_kinds
        builtin_results=result_kinds(pure_bindings.services)
    numeric_routines={};address_routines={}
    closed_with_declarations=emitter.literal_reachability
    if ((not async_bodies or closed_with_declarations) and _profile is None and not imported
            and not vm.allow_extensions and not _authority and not _source_scopes):
        for name,routine in emitter.routines.items():
            if (routine.is_async or not routine.is_function or not routine.body
                    or not all(p.by_value for p in routine.parameters)
                    or type(routine.body[-1]) is not bsl.Return or routine.body[-1].value is None
                    or any(type(stmt) is not bsl.Assign or type(stmt.target) is not bsl.Name
                           for stmt in routine.body[:-1])):
                continue
            formals={p.name.casefold() for p in routine.parameters}
            locals_={stmt.target.name.casefold() for stmt in routine.body[:-1]}-formals
            if ((locals_ | formals) & emitter.routines.keys()
                    or locals_ & (emitter.external_names | emitter.module_globals | {'thisobject','этотобъект'})):
                continue
            numeric_routines[name]=routine
        for name,routine in emitter.routines.items():
            if (routine.is_async or routine.is_function or not routine.body
                    or not any(not p.by_value for p in routine.parameters)
                    or any(p.default is not None for p in routine.parameters)):
                continue
            formals={p.name.casefold() for p in routine.parameters}
            if all(type(stmt) is bsl.Assign and type(stmt.target) is bsl.Name
                    and stmt.target.name.casefold() in formals for stmt in routine.body):
                address_routines[name]=routine
    if ((not async_bodies or closed_with_declarations) and _profile is None and not imported
            and not _exports and not _require_last_expression and vm.database_context is None):
        facts_reachability=emitter.literal_reachability
        names,cells=_module_registers(program,emitter,literal_reachability=facts_reachability)
        builtin_external_names=() if pure_bindings is None else pure_bindings.names-names
        if names or builtin_results or numeric_routines or address_routines:
            static_facts=analyze_static(program,opaque_names=emitter.external_names|emitter.module_globals,
               builtin_results=builtin_results,builtin_external_names=builtin_external_names,
               numeric_routines=numeric_routines,address_routines=address_routines,
               literal_reachability=facts_reachability,module_declarations=closed_with_declarations,extended_tests=extended_tests)
            emitter.static_module_kinds={} if static_facts is None else static_facts[1]
        # Starting a task (directly or through a reachable same-module
        # routine), Eval, and all opaque edges decline this closed proof.
        # Preserve the original dictionary-backed async module for them.
        if not async_bodies or static_facts is not None:
            if static_facts is not None:names.update(static_facts[0])
            elif facts_reachability:
                names,cells=_module_registers(program,emitter,literal_reachability=False)
                builtin_external_names=() if pure_bindings is None else pure_bindings.names-names
            emitter.module_cells.update(cells)
            emitter.static_module_names={key:emitter.temp() for key in sorted(names)}
            if not has_goto:
                opaque=emitter.external_names|emitter.module_globals|emitter.module_cells
                emitter.scalar_kinds=analyze_static(program,opaque_names=opaque,scalar_prefix=True,
                   builtin_results=builtin_results,builtin_external_names=builtin_external_names)
            if (not has_goto and static_facts is None and not emitter.authority and not emitter.source_scopes
                    and not emitter.catalog_bounds and (not emitter.routines or emitter.native_cells)):
                from yadinassi.execution.direct.python_direct_local_facts import analyze as analyze_local
                emitter.local_field_facts,local_scalars=analyze_local(program,opaque_names=opaque,routines=emitter.routines)
                emitter.scalar_kinds.update(local_scalars)
            if (static_facts is None and facts_reachability and pure_bindings is None
                    and not emitter.routines and not cells):
                for offset,statement in enumerate(program):
                    if type(statement) is not bsl.Assign or type(statement.target) is not bsl.Name:
                        continue
                    origin=statement.value
                    if (type(origin) is not bsl.New or origin.name.casefold() not in ('valuetable','таблицазначений')
                            or origin.arguments):
                        continue
                    key=statement.target.name.casefold()
                    setup=table_schema_setup(program,offset+1,key)
                    end,kinds=analyze_static(program,opaque_names=opaque,
                        literal_reachability=True,table_prefix_origin=origin,
                        schema_setup=(key,setup) if setup else None)
                    phase=max(setup,default=offset)+1
                    if setup and end==len(program) and type(program[-1]) is bsl.ExpressionStatement:
                        end-=1  # Keep the module's final expression/return outside the guard.
                    if (phase<end and (setup or end<len(program))
                            and any(type(node) is bsl.For for node in program[phase:end])):
                        table_prefix_origin,table_prefix_start,table_prefix_end,table_prefix_kinds=offset,phase,end,kinds
                    break
    if static_facts is not None and not emitter.module_cells and not emitter.authority and not emitter.catalog_bounds:
        integer_kinds=('number','bool','string','table','row','columns','column','map','map_insert','default_column_type')
        emitter.integer_lane=bool(static_facts[1]) and all(kind in integer_kinds for kind in static_facts[1].values())
        if emitter.integer_lane and (extended_tests or 'default_column_type' in static_facts[1].values()):
            # Newly closed table shapes may still use direct access without
            # switching old Decimal operations to a different numeric lane.
            previous=analyze_static(program,opaque_names=emitter.external_names|emitter.module_globals,
                builtin_results=builtin_results,builtin_external_names=builtin_external_names,
                numeric_routines=numeric_routines,address_routines=address_routines,
                literal_reachability=facts_reachability,module_declarations=closed_with_declarations,
                extended_reachability=False)
            emitter.integer_lane=(previous is not None and bool(previous[1])
                and all(kind in integer_kinds for kind in previous[1].values()))
        if emitter.integer_lane:
            emitter.scalar_kinds.update(static_facts[1])
            proven={name:routine for name,routine in numeric_routines.items()
                    if id(routine.body[-1].value) in static_facts[1]}
            emitter.numeric_routine_symbols={name:emitter.temp() for name in proven}
            # Only closed numeric calls use these definitions. The existing
            # generic definitions still own every persisted/exported signature.
            for name,routine in proven.items():
                keys={p.name.casefold():emitter.temp() for p in routine.parameters}
                for stmt in routine.body[:-1]:
                    key=stmt.target.name.casefold()
                    if key not in keys:keys[key]=emitter.temp()
                emitter.scope={'slots':keys,'bindings':set(keys),'globals':set(),'externals':set(),
                               'boxed':set(),'local_declarations':set(keys),'initialized':set(keys)}
                token=routine.token
                arguments=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,p.token,arg=keys[p.name.casefold()],annotation=None)
                                       for p in routine.parameters],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
                body=emitter.sequence(routine.body)
                definitions.append(emitter.node(py.FunctionDef,token,name=emitter.numeric_routine_symbols[name],
                                               args=arguments,body=body,decorator_list=[],returns=None,type_comment=None))
            emitter.scope=None
    if static_facts is not None and any(kind=='address_call' for kind in static_facts[1].values()):
        proven={name:routine for name,routine in address_routines.items()
                if id(routine.body[0].value) in static_facts[1]}
        emitter.address_routine_symbols={name:emitter.temp() for name in proven}
        emitter.scalar_kinds.update(static_facts[1])
        module_kinds=emitter.static_module_kinds
        emitter.static_module_kinds={}
        for name,routine in proven.items():
            keys={p.name.casefold():emitter.temp() for p in routine.parameters}
            accesses={p.name.casefold():(keys[p.name.casefold()],emitter.temp())
                      for p in routine.parameters if not p.by_value}
            emitter.scope={'slots':keys,'bindings':set(keys),'globals':set(),'externals':set(),
                           'boxed':set(),'local_declarations':set(keys),'initialized':set(keys),'addresses':accesses}
            token=routine.token;slots=[]
            for p in routine.parameters:
                key=p.name.casefold()
                slots.extend(emitter.node(py.arg,p.token,arg=slot,annotation=None)
                             for slot in accesses.get(key,(keys[key],)))
            arguments=py.arguments(posonlyargs=[],args=slots,vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
            body=emitter.sequence(routine.body)
            definitions.append(emitter.node(py.FunctionDef,token,name=emitter.address_routine_symbols[name],
                                           args=arguments,body=body,decorator_list=[],returns=None,type_comment=None))
        emitter.scope=None
        emitter.static_module_kinds=module_kinds
    from yadinassi.execution.direct.python_direct_collection_regions import analyze,admitted,helpers
    region_end=0
    if not has_goto and not emitter.static_module_names and not emitter.routines and not emitter.authority and not emitter.source_scopes:
        region_end,emitter.region_ops,emitter.region_states=analyze(program,opaque_names=emitter.external_names)
    emitter.region_active=bool(region_end)
    if has_goto and type(program[-1]) is bsl.ExpressionStatement:
        emitter.goto_last_expression=program[-1]
    if table_prefix_end:
        # Keep the ordinary constructor and one shared register file. Switch
        # lowering, never visibility: only normal generic edges and module exit
        # publish, so no old (possibly finalizable) values retire early.
        body=emitter.sequence(program[:table_prefix_start])
        segment=program[table_prefix_start:table_prefix_end]
        generic=emitter.sequence(segment)
        emitter.static_module_kinds=table_prefix_kinds
        # Use the ordinary Decimal counter/increments and public facade values.
        emitter.table_prefix=True
        specialized=emitter.sequence(segment)
        emitter.table_prefix=False
        emitter.static_module_kinds={}
        slot=emitter.static_module_names[program[table_prefix_origin].target.name.casefold()]
        arguments=[emitter.name('_context',t),emitter.name(slot,t)]
        if table_prefix_start!=table_prefix_origin+1:
            arguments.append(emitter.const(True,t))
        test=emitter.call('_fresh_closed_table',arguments,t)
        body.append(emitter.node(py.If,t,test=test,body=specialized,orelse=generic))
        body+=emitter.sequence(program[table_prefix_end:])
    else:
        body=emitter.sequence(program[:region_end])
        emitter.region_active=False
        body+=emitter.sequence([node for node in program[region_end:] if type(node) is not bsl.Routine])
    if region_end:body.insert(0,emitter.node(py.Assign,t,targets=[emitter.name('_collection_fast',t,True)],value=emitter.const(False,t)))
    if not has_goto and type(program[-1]) is bsl.ExpressionStatement:
        last=body.pop()
        if emitter.integer_lane:last.value=emitter.call('_dynamic_public_number',[last.value],program[-1].token)
        if type(last) is py.Try and emitter.static_module_names:
            last.body[-1]=emitter.node(py.Return,program[-1].token,value=last.body[-1].value);body.append(last)
        else:body.append(emitter.node(py.Return,program[-1].token,value=last.value))
    else:body.append(emitter.node(py.Return,t,value=emitter.node(py.Dict,t,keys=[],values=[]) if _exports and not emitter.routines else emitter.name('_initial',t)))
    if emitter.static_module_names:
        load=[]
        for key,slot in emitter.static_module_names.items():
            value=emitter.invoke(emitter.attribute(emitter.name('_initial',t),'get',t),[emitter.const(key,t),emitter.name('_UNSET',t)],t)
            if key in emitter.module_cells:value=emitter.call('_NativeCell',[value],t)
            load.append(emitter.node(py.Assign,t,targets=[emitter.name(slot,t,True)],value=value))
        depth=([emitter.node(py.Assign,t,targets=[emitter.name('_dynamic_depth',t,True)],value=emitter.const(0,t))]
               if emitter.module_boundaries else [])
        final=[emitter.node(py.Expr,t,value=emitter.module_sync(t,False))]
        sync_helpers=[]
        for reload in ((False,True) if emitter.module_boundaries else (False,)):
            helperbody=[]
            if reload:helperbody.append(emitter.node(py.Nonlocal,t,names=list(emitter.static_module_names.values())))
            helperbody.append(emitter.node(py.Expr,t,value=emitter.module_sync_body(t,reload)))
            args=emitter.node(py.arguments,t,posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
            sync_helpers.append(emitter.node(py.FunctionDef,t,name='_reload_module' if reload else '_publish_module',args=args,body=helperbody,decorator_list=[],returns=None,type_comment=None))
        body=[*load,*sync_helpers,*depth,emitter.node(py.Try,t,body=body,handlers=[],orelse=[],finalbody=final)]
        emitter.static_module_names={};emitter.static_module_kinds={}
    initializers=[emitter.node(py.Assign,t,targets=[emitter.name(slot,t,True)],value=emitter.call('_SlotReference',[emitter.name('_initial',t),emitter.const(key,t)],t)) for key,slot in emitter.source_refs.items()]
    if emitter.routines:
        exports=emitter.node(py.Dict,t,keys=[emitter.const(key,t) for key in emitter.routines]+
            [emitter.const('@async:'+key,t) for key in async_bodies],values=[emitter.name(emitter.routine_symbols[key],t) for key in emitter.routines]+
            [emitter.name(symbol,t) for symbol in async_bodies.values()])
        bind_return=emitter.node(py.If,t,test=emitter.name('_bind_only',t),body=[emitter.node(py.Return,t,value=exports)],orelse=[])
        declarations=[]
        for key in sorted(emitter.module_globals):
            initialize=emitter.invoke(emitter.attribute(emitter.name('_initial',t),'setdefault',t),[emitter.const(key,t),emitter.const(None,t)],t)
            declarations.append(emitter.node(py.Expr,t,value=initialize))
        initialize=emitter.node(py.If,t,test=emitter.const(True,t) if _exports else emitter.node(py.UnaryOp,t,op=py.Not(),operand=emitter.name('_bind_only',t)),body=declarations or [emitter.node(py.Pass,t)],orelse=[])
        body=[initialize,*definitions,bind_return,*body]
    initialize_links=[emitter.node(py.Assign,t,targets=[emitter.name(slot,t,True)],value=emitter.name('_UNSET',t))
                      for slot in emitter.import_links]
    body=initialize_links+initializers+body
    arguments=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,t,arg=name,annotation=None) for name in ('_initial','_constants','_outputs','_context')],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
    if emitter.routines:
        arguments.args.append(emitter.node(py.arg,t,arg='_bind_only',annotation=None));arguments.defaults.append(emitter.const(_exports,t))
    function=emitter.node(py.FunctionDef,t,name='naked_module',args=arguments,body=body,decorator_list=[],returns=None,type_comment=None)
    tree=py.Module(body=[function],type_ignores=[])
    equal,not_equal=scalar.map_identity_operators(array=True,structure=True)
    equal,not_equal=scalar.numeric_boolean_operators(equal,not_equal)
    from . import experimental_naked_live_state as live_state
    from yadinassi.collections import value_tables as _vt, value_lists as _vl
    data_types=(list,dict,_PlainArray,PlainMap,PlainValueList,PlainValueListItem,_TypedMap,_NakedMap,_DirectStructure,_MapEntry,
        _vt.BSLValueTable,_vt.BSLValueTableRow,_vt.BSLValueTableColumnCollection,_vt.BSLValueTableColumn,
        _vt.BSLCollectionIndexes,_vt.BSLCollectionIndex,_vl.BSLValueList,_vl.BSLValueListItem)
    from yadinassi.execution.direct.python_direct_numbers import divide, remainder, sign, public_number
    from yadinassi.collections.plain_table_storage import RowStorage
    from yadinassi.execution.direct.python_direct_table_references import local_index as _local_row_index, local_member as _local_row_member
    from yadinassi.execution.direct.python_direct_array_references import local_index as _local_array_index, ARRAY as _BoxedArray
    from yadinassi.execution.direct.python_direct_structure_references import local_member as _local_structure_member, STRUCTURE as _BoxedStructure
    from yadinassi.execution.direct.python_direct_structural_reads import TARGET_IDS, selects, count as structural_count
    from yadinassi.db.database_context import require_database_context
    from .experimental_naked_errors import for_bound_unbound, read_except_local
    namespace=dict(_for_bound_unbound=for_bound_unbound,_read_except_local=read_except_local,_normalize_item_presentation=_normalize_presentation,_normalize_item_check=_normalize_check,
        _require_database_context=require_database_context,_structural_count_ids=TARGET_IDS,_select_structural_read=selects,_structural_count=structural_count,_local_structure_member=_local_structure_member,_BoxedStructure=_BoxedStructure,_local_array_index=_local_array_index,_BoxedArray=_BoxedArray,_local_row_index=_local_row_index,_local_row_member=_local_row_member,_PlainTableRow=_vt.BSLValueTableRow,_raw_table_value=RowStorage.get_value,_raw_table_positional=_vt.BSLValueTableRow._positional_value,_dynamic_remainder=remainder,_dynamic_divide=divide,_dynamic_sign=sign,_dynamic_public_number=public_number,_plain_array_loop=_plain_array_loop,_plain_append_receiver=_plain_append_receiver,_list_append=list.append,_native_host_reference=_native_host_reference,_native_cell_reference=_native_cell_reference,_native_fragment_binding=_native_fragment_binding,_NativeCell=_NativeCell,_PublishedModuleCell=_PublishedModuleCell,_adapt_native_cell=_adapt_native_cell,_PrivateTable=_vt.BSLValueTable,_PrivateValueList=PlainValueList,_PlainValueList=PlainValueList,_PlainValueListItem=PlainValueListItem,_module_primitive_type_ids=frozenset(id(kind) for kind in (list,dict,_PlainArray,PlainMap,PlainValueList,PlainValueListItem,_TypedMap,_NakedMap,_DirectStructure)),_module_data_types=data_types,_module_data_type_ids=frozenset(id(kind) for kind in data_types),_native_dict_get=dict.get,_native_dict_setitem=dict.__setitem__,_PlainArray=_PlainArray,_Decimal=Decimal,_PlainMap=PlainMap,_plain_map=plain_map,_execute_fragment=execute_fragment,_fragment_binding=_fragment_binding,_bind_eval=bind_eval,_raise_arity_error=raise_arity_error,_host_omission_error=_host_omission_error,_host_omission_values=_host_omission_values,_dynamic_construct=dynamic_construct,_invalid_native_arity=_invalid_native_arity,_typed_find=scalar.typed_find,_list_delete=_list_delete,_native_ubound=_native_ubound,_readonly=readonly,_array_set_checked=_array_set_checked,_bounded_insert=bounded_insert,_structure_insert=structure_insert,_array_constructor_bounds=bounded_array,_new_structure=new_structure,_structure_from_schema=structure_from_schema,_host_name_reference=_host_name_reference,_Cell=_Cell,_ForwardReference=_ForwardReference,_as_ref=_as_ref,_bound_ref=_bound_ref,_UNSET_REF=_UNSET_REF,_OMITTED_REF=_OMITTED_REF,_argument_count_error=_argument_count_error,_routine_value_error=_routine_value_error,_procedure_value_error=_procedure_value_error,_identity_reference=_identity_reference,_IndexRef=_IndexRef,_AttributeRef=_AttributeRef,_SlotReference=live_state._SlotReference,_source_reference=source_reference,_canonical_reference=_canonical_reference,_structure_property=structure_property,_native_method_missing=_native_method_missing,_native_count=_native_count,_MapEntry=_MapEntry,_array_member=_array_member,_native_property_missing=_native_property_missing,_structure_get_known=structure_get_known,_structure_set_known=structure_set_known,_native_property_write_missing=_native_property_write_missing,_checked_array_index=_checked_array_index,_checked_literal_array_index=_checked_literal_array_index,_partial=partial,_native_getitem=_NATIVE_GETITEM,_list_get=_list_get,_TypedMap=_TypedMap,_NakedMap=_NakedMap,_DirectStructure=_DirectStructure,_host_reference=host_reference,_UNSET=UNSET,_missing=missing,_native_add=_NATIVE_ADD,_concatenate=scalar.concatenate,_divide=scalar.decimal_divide,_sign=scalar.decimal_sign,_order=scalar.uca_order,_truth=scalar.truth,_equal=equal,_not_equal=not_equal,_MISSING=_MISSING,_handled_error=handled_error,_reraise_handled=reraise_handled,_raise_error=raise_error,_presentation=scalar.presentation,_BSLRuntimeError=BSLRuntimeError)
    if emitter.known_calls:
        from yadinassi.execution.direct.python_direct_known_methods import execute, construct_table, detached_after_publication, generic_call
        namespace.update(_known_query_execute=execute,_known_construct_table=construct_table,
                         _known_detached_after_publication=detached_after_publication,
                         _known_generic_call=generic_call)
    if emitter.known_selection_reads:
        from yadinassi.execution.direct.python_direct_known_methods import selection_read_protocol
        namespace['_known_selection_read_protocol']=selection_read_protocol
    if emitter.known_selection_adds:
        from yadinassi.execution.direct.python_direct_known_methods import selection_add
        namespace['_known_selection_add']=selection_add
    if table_prefix_end:
        from yadinassi.execution.direct.python_direct_plain_tables import fresh_closed_table
        namespace['_fresh_closed_table']=fresh_closed_table
    if destinations:namespace['_GotoTransfer']=_GotoTransfer
    namespace['_nonconstructible_type'] = _nonconstructible_type
    if emitter.http_body_receiver:
        from yadinassi.http.http_client import BSLHTTPRequest
        namespace['_HTTPRequest'] = BSLHTTPRequest
    # Exception handlers share the module source instead of emitting one literal each.
    namespace['_diagnostic_source'] = source_text
    if pure_bindings is not None:
        from yadinassi.execution.direct.python_direct_pure_builtins import resolve
        namespace.update({symbol:resolve(name,native_numbers=emitter.integer_lane) for name,symbol in emitter.pure_builtins.items()})
    if region_end or any_region:namespace.update(_collection_admitted=admitted,_collection_helpers=helpers(),_routine_region_state_safe=_routine_region_state_safe)
    # Every route genuinely compiles executable code before source effects.
    # Whole-source research additionally parses the actual source, not a fake
    # notification or an ignored authorization probe.
    generated=None;roundtrip_visits=0
    if _whole_source:tree,generated,roundtrip_visits=_source_roundtrip(tree,filename)
    try:code=compile(tree,filename,'exec')
    except (SyntaxError,ValueError,TypeError,RecursionError,SystemError) as error:
        # Diagnostic only: never use a reparsed tree to retry failed compilation.
        if not _whole_source:
            try:_source_roundtrip(tree,filename)
            except Exception as diagnostic:
                note=getattr(error,'add_note',None)
                if note is not None:note('Generated Python roundtrip: '+str(diagnostic))
        raise
    if async_bodies:
        from yadinassi.application.async_runtime import AwaitRequest
        namespace['_AwaitRequest']=AwaitRequest
    exec(code,namespace)
    if async_bodies:namespace['naked_module']._direct_source_text=source_text
    result=Program(generated,tuple(emitter.constants),namespace['naked_module'],{},frozenset(REPAIRS),source_name=filename,source_text=source_text,required_services=tuple(sorted(emitter.required)),trusted_entry=True,_generated_tree=tree if _retain_generated and generated is None else None)
    if emitter.authority:result.repairs=result.repairs|{'authority_checkpoints'}
    result._source_implicit_shadows=frozenset(emitter.implicit_shadows)
    result._research_lowering_counts=(count,emitter.visits,emitter.python_nodes)
    result._research_roundtrip_visits=roundtrip_visits
    result._pure_bindings=pure_bindings
    return result


def compile_module_whole_source(vm,program,nodes,source_text,source_name,*,_exports=False,_require_last_expression=False):
    """Explicit source-plus-AST audit; never replay through another compiler."""
    return compile_module(vm,program,nodes,source_text,source_name,
                          _exports=_exports,_whole_source=True,_require_last_expression=_require_last_expression)


def compile_owned(program, *, source_text, source_name, module_names=(),
                  external_names=(), constructors=(), exports=False, source_scopes=False,
                  authority_checks=False, scalar_routines=False, callable_externals=(),
                  shadowable_externals=(), require_last_expression=False, configuration_calls=False, host_bindings=False, catalog_bounds=False,
                  lean_configuration=False, retain_generated=True, current_module=False):
    """Compile an already-authorized side's declarations to Python definitions.

    Namespace inputs describe names, not a runtime grant. The owning invocation
    still supplies its checked context and state. No interpreter or old emitter
    is called, and no foreign side is inferred from ambient VM state.
    """
    for flag in (exports,source_scopes,authority_checks,scalar_routines,require_last_expression,configuration_calls,host_bindings,catalog_bounds,lean_configuration,retain_generated,current_module):
        if type(flag) is not bool:raise TypeError('owned compile flags require Boolean')
    for names in (module_names,external_names,constructors,callable_externals,shadowable_externals):
        if type(names) is not tuple or any(type(name) is not str for name in names):
            raise TypeError('owned compile namespaces require tuples of names')
    if (scalar_routines or shadowable_externals) and not source_scopes:
        raise ValueError('source capabilities require source scopes')
    if callable_externals and not (source_scopes or host_bindings):raise ValueError('callable externals require an owning binding profile')
    if catalog_bounds and not authority_checks:raise ValueError('catalog bounds require authority checkpoints')
    if lean_configuration and (not configuration_calls or not authority_checks or source_scopes or host_bindings or catalog_bounds):
        raise ValueError('lean configuration requires the managed CLI compiler contract')
    nodes=[];pending=list(program)
    while pending:
        node=pending.pop()
        if type(node) in (list,tuple):
            pending.extend(node);continue
        if isinstance(node,bsl.Node):
            nodes.append(node)
            for field in fields(node):
                value=getattr(node,field.name)
                if isinstance(value,bsl.Node):pending.append(value)
                elif type(value) in (list,tuple):pending.extend(value)
    try:
        return compile_module(None,program,tuple(nodes),source_text,source_name,
            _exports=exports,_require_last_expression=require_last_expression,
            _profile=(tuple(module_names),tuple(external_names),tuple(constructors)),
            _source_scopes=source_scopes,_authority=authority_checks,
            _scalar_routines=scalar_routines,_callable_externals=callable_externals,
            _shadowable=shadowable_externals,_configuration_calls=configuration_calls,_host_bindings=host_bindings,_catalog_bounds=catalog_bounds,
            _lean_configuration=lean_configuration,_retain_generated=retain_generated,_current_module=current_module)
    except PythonDirectUnsupported as error:
        if not source_scopes:raise
        from .experimental_naked_collections import UnsupportedNakedSyntax
        raise UnsupportedNakedSyntax(str(error)) from None
