"""Direct BSL-to-Python AST compiler under default-path replacement.

The default whole-source lane parses generated source, verifies its structure,
transplants BSL positions, and compiles that actual tree. It does not fall back
or replay through the former text emitter. The pure AST lane remains a test
comparison. Legacy interpreter execution is separate and unchanged.

Auxiliary-fragment audit events from the former compiler are intentionally not
reproduced; real generated-source and executable-AST audit gates run before
source effects. Replacement parity is still being established by the full suite.
"""
import ast as py
import _operator as _OPERATOR_MODULE
from types import ModuleType as _ModuleType
from _operator import add as _NATIVE_ADD, getitem as _NATIVE_GETITEM
from functools import partial
from .experimental_naked_collections import _TypedMap, _NakedMap, _checked_array_index, _native_property_write_missing, _native_property_missing, _MapEntry, _array_insert_shape, _native_method_missing, _ALIASES, _canonical_reference, _IndexRef, _AttributeRef, _procedure_value_error, _routine_value_error, _argument_count_error, _OMITTED_REF, _Cell, _as_ref, _bound_ref, _UNSET_REF
from .experimental_naked_structure import _DirectStructure, structure_get_known, structure_property
from .experimental_naked_array_methods import array_method_value
from .experimental_naked_resources import bounded_array,bounded_insert
from .experimental_naked_collections import _array_set_checked, _invalid_native_arity, _host_omission_error, _host_omission_values
from .experimental_naked_structure import prepare_structure_schema,new_structure,structure_from_schema,structure_insert
from decimal import Decimal
from .syntax import ast as bsl
from .experimental_naked_collections import Program, _host_name_reference, _host_omission_values
from .experimental_naked_boundaries import _MISSING
from .experimental_naked_live_state import UNSET,missing,readonly,host_reference,source_reference,_SlotReference
from . import experimental_naked_scalar_semantics as scalar
from .experimental_naked_errors import handled_error,reraise_handled
from .python_direct_error_info import raise_error, raise_arity_error
from .python_direct_dynamic_new import construct as dynamic_construct
from .python_direct_execute import execute_fragment, local_binding, local_exists
from .python_direct_eval import bind_eval
from .python_direct import REPAIRS,PythonDirectUnsupported
from .python_direct_names import NAMES
from .errors import BSLRuntimeError
from dataclasses import fields, replace



def _reject(message):
    raise PythonDirectUnsupported('direct-AST: '+message)


def _fragment_binding(storage):
    return local_binding(lambda:storage.value,lambda value:setattr(storage,'value',value),
                         lambda:local_exists(storage),storage)

def _list_get(receiver,index):
    return receiver[_checked_array_index(receiver,index)]


def _array_member(receiver,name):
    return array_method_value(receiver,name,index=_checked_array_index,
        insert=_array_insert_shape,find=scalar.typed_find,
        delete=lambda obj,key:obj.__delitem__(_checked_array_index(obj,key)))


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
    count=0;pending=[(program,0)]
    while pending:
        value,depth=pending.pop()
        if isinstance(value,bsl.Node):
            count+=1
            if value.token is None or value.token.line<1:_reject('source location is invalid')
            pending.extend((getattr(value,f.name),depth+1) for f in fields(value) if f.name!='token' and not (type(value) is bsl.Literal and f.name=='value'))
        elif type(value) is list or type(value) is tuple:
            pending.extend((item,depth+1) for item in value)
    return count


class Emitter:
    def __init__(self,filename,source):
        self.filename=filename;self.source=source;self.constants=[];self.serial=0
        self.owned_constructors=False;self.configuration_calls=False;self.host_bindings=False;self.catalog_bounds=False;self.source_scopes=False;self.authority=False;self.scalar_routines=False;self.callable_externals=frozenset();self.shadowable=frozenset();self.implicit_shadows=set()
        self.import_names=frozenset();self.require_last_expression=None;self.region_active=False;self.region_ops={};self.region_states={};self.routines={};self.routine_symbols={};self.module_globals=set();self.scope=None;self.source_refs={};self.loop_increments=[];self.required=set();self.visits=0;self.python_nodes=0
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
    def invoke(self,func,args,token,keywords=()):return self.node(py.Call,token,func=func,args=args,keywords=list(keywords))
    def region_helper(self,operation,token):
        return self.node(py.Subscript,token,value=self.name('_collection_helpers',token),slice=self.const(operation,token),ctx=py.Load())
    def region_selected(self,selected,operation,receiver,token,extra=()):
        helper=self.call('_partial',[self.region_helper(operation,token),self.name('_context',token),self.name(receiver,token),*extra],token)
        return self.node(py.IfExp,token,test=self.name('_collection_fast',token),body=helper,orelse=selected)
    def literal(self,value,token):
        index=len(self.constants);self.constants.append(value)
        return self.node(py.Subscript,token,value=self.name('_constants',token),slice=self.const(index,token),ctx=py.Load())
    def initialize_local(self,key):
        if key not in self.scope['initialized']:
            self.scope['initialized'].add(key)
            journals=self.scope.get('initialization_journals',[])
            if journals:journals[-1].add(key)
    def target(self,name,token):
        self.check_name(name)
        if self.scope is not None and name.casefold() not in self.scope['globals']:
            key=name.casefold()
            if key not in self.scope['slots']:self.scope['slots'][key]=self.temp()
            self.initialize_local(key)
            slot=self.name(self.scope['slots'][key],token)
            if key in self.scope['boxed']:return self.node(py.Attribute,token,value=slot,attr='value',ctx=py.Store())
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
        return self.node(py.Assign,t,targets=[self.target(name,t)],value=value)
    def read(self,name,token):
        if self.external_name(name):return self.invoke(self.attribute(self.name('_context',token),'external_get',token),[self.const(name.casefold(),token)],token)
        self.check_name(name)
        if self.scope is not None and name.casefold() not in self.scope['globals']:
            key=name.casefold()
            if key in self.scope['bindings']:
                if key not in self.scope['slots']:self.scope['slots'][key]=self.temp()
                slot=self.name(self.scope['slots'][key],token)
                value=self.attribute(slot,'value',token) if key in self.scope['boxed'] else slot
                if self.source_scopes or self.host_bindings:
                    raw=self.attribute(slot,'_value',token) if key in self.scope['boxed'] else slot
                    test=self.node(py.Compare,token,left=raw,ops=[py.IsNot()],comparators=[self.name('_UNSET_REF' if key in self.scope['boxed'] else '_UNSET',token)])
                    if key in self.scope['boxed']:
                        forwarded=self.node(py.Compare,token,left=self.call('type',[slot],token),ops=[py.IsNot()],comparators=[self.name('_Cell',token)])
                        test=self.node(py.BoolOp,token,op=py.Or(),values=[forwarded,test])
                    missing=self.invoke(self.attribute(self.name('_context',token),'external_get',token),[self.const(key,token)],token) if key in self.scope['shadows'] else self.call('_missing',[self.const(name,token)],token)
                    return self.node(py.IfExp,token,test=test,body=value,orelse=missing)
                return value
            return self.call('_missing',[self.const(name,token)],token)
        temporary=self.temp()
        value=self.invoke(self.attribute(self.name('_initial',token),'get',token),[self.const(name.casefold(),token),self.name('_UNSET',token)],token)
        bound=self.node(py.NamedExpr,token,target=self.name(temporary,token,True),value=value)
        test=self.node(py.Compare,token,left=bound,ops=[py.IsNot()],comparators=[self.name('_UNSET',token)])
        return self.node(py.IfExp,token,test=test,body=self.name(temporary,token),orelse=self.call('_missing',[self.const(name,token)],token))
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
    def fragment_arguments(self,t):
        names=() if self.scope is None else tuple(sorted(self.scope.get('fragment_names',())))
        bindings=self.node(py.Dict,t,keys=[self.const(key,t) for key in names],
            values=[self.call('_fragment_binding',[self.name(self.scope['slots'][key],t)],t) for key in names])
        visible=None if self.scope is None else tuple(sorted(self.scope['globals']))
        return [self.name('_context',t),self.name('_initial',t),bindings,self.const(visible,t)]
    def expr(self,node,require_value=True):
        value=self._expr(node,require_value)
        if not self.catalog_bounds:return value
        t=node.token
        step=self.invoke(self.attribute(self.name('_context',t),'preparation_step',t),[],t)
        pair=self.node(py.Tuple,t,elts=[step,value],ctx=py.Load())
        reached=self.node(py.Subscript,t,value=pair,slice=self.const(1,t),ctx=py.Load())
        return self.invoke(self.attribute(self.name('_context',t),'preparation_value',t),[reached],t)
    def member_call(self,receiver,name,require_value,omitted,count,t):
        method='resolve_configuration_member_call' if self.configuration_calls else 'resolve_member_call'
        keywords=[self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='omitted',value=self.const(omitted,t))]
        if self.configuration_calls:keywords.append(self.node(py.keyword,t,arg='argument_count',value=self.const(count,t)))
        return self.invoke(self.attribute(self.name('_context',t),method,t),[self.name(receiver,t),self.const(name,t)],t,keywords)
    def _expr(self,node,require_value=True):
        self.visits+=1;t=node.token;k=type(node)
        if k is bsl.Call and type(node.callee) is bsl.Group:
            callee=node.callee
            while type(callee) is bsl.Group:callee=callee.expression
            node=replace(node,callee=callee)
        path=self.import_path(node)
        if path is not None:
            return self.invoke(self.attribute(self.name('_context',t),'import_get',t),[self.const(path,t)],t)
        if k is bsl.Call and self.import_path(node.callee) is not None:
            path=self.import_path(node.callee)
            if any(type(arg) is bsl.OmittedArgument for arg in node.arguments):_reject('omitted imported call argument')
            bound=self.invoke(self.attribute(self.name('_context',t),'resolve_import_call',t),[self.const(path,t)],t,
                [self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),
                 self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))])
            return self.dynamic_call(bound,node)
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
            if node.operator in ('+','-'):return self.call('_sign',[self.expr(node.operand),self.const(node.operator,t)],t)
            if node.operator=='NOT':return self.node(py.UnaryOp,t,op=py.Not(),operand=self.truth(node.operand,t))
        if k is bsl.Binary:
            op=node.operator
            if not self.catalog_bounds and op=='+' and type(node.left) is bsl.Literal and type(node.right) is bsl.Literal and type(node.left.value) is str:
                return self.literal(scalar.concatenate(node.left.value,node.right.value),t)
            if op in ('AND','OR'):
                return self.node(py.BoolOp,t,op=py.And() if op=='AND' else py.Or(),values=[self.truth(node.left,t),self.truth(node.right,t)])
            left=self.expr(node.left);right=self.expr(node.right)
            if op=='+':
                if type(node.left) is bsl.Literal and type(node.left.value) is not str:
                    return self.node(py.BinOp,t,left=left,op=py.Add(),right=right)
                # Preserve ordinary-direct left-temporary lifetime, evaluate
                # the type decision before RHS, and emit RHS only once.
                temporary=self.temp()
                bound=self.node(py.NamedExpr,t,target=self.name(temporary,t,True),value=left)
                kind=self.call('type',[bound],t)
                test=self.node(py.Compare,t,left=kind,ops=[py.Is()],comparators=[self.name('str',t)])
                operation=self.node(py.IfExp,t,test=test,body=self.name('_concatenate',t),orelse=self.name('_native_add',t))
                return self.invoke(operation,[self.name(temporary,t),right],t)
            helpers={'/':'_divide','=':'_equal','<>':'_not_equal'}
            if op in helpers:return self.call(helpers[op],[left,right],t)
            if op in ('<','<=','>','>='):return self.call('_order',[left,right,self.const(op,t)],t)
            operators={'-':py.Sub,'*':py.Mult,'%':py.Mod}
            if op in operators:return self.node(py.BinOp,t,left=left,op=operators[op](),right=right)
        if k is bsl.DynamicNew:
            return self.call('_dynamic_construct',[self.name('_context',t),self.expr(node.type_expression),self.expr(node.parameters) if node.parameters is not None else self.const(None,t)],t)
        if k is bsl.New:
            kindname=node.name.casefold()
            if self.owned_constructors and kindname in self.constructor_names:
                key='new:'+kindname;self.required.add(key)
                keywords=[self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))] if self.source_scopes else []
                bound=self.invoke(self.attribute(self.name('_context',t),'resolve_service',t),[self.const(key,t)],t,keywords)
                if any(type(arg) is bsl.OmittedArgument for arg in node.arguments):return self.dynamic_call(bound,node,references=False)
                return self.invoke(bound,[self.expr(arg) for arg in node.arguments],t)
            native=kindname in ('array','массив','map','соответствие','structure','структура')
            if not native and kindname not in self.constructor_names:
                _reject(f'constructor {node.name}; outside research subset')
            if any(type(arg) is bsl.OmittedArgument for arg in node.arguments):
                if native:return self.call('_host_omission_error',[],t)
                key='new:'+kindname;self.required.add(key)
                bound=self.invoke(self.attribute(self.name('_context',t),'resolve_service',t),[self.const(key,t)],t,
                    [self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))] if self.source_scopes else [])
                return self.dynamic_call(bound,node,references=False)
            args=[self.expr(arg) for arg in node.arguments]
            if kindname in ('array','массив'):
                return self.call('_array_constructor_bounds',args,t)
            if kindname in ('map','соответствие'):
                return self.call('_TypedMap',args,t)
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
            return self.invoke(bound,args,t)
        if k is bsl.Attribute:
            receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            host=self.invoke(self.attribute(self.name('_context',t),'get_member',t),[self.name(receiver,t),self.const(node.name,t)],t)
            maps=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_TypedMap'),exact('_NakedMap')])
            host=self.node(py.IfExp,t,test=maps,body=self.call('_native_property_missing',[self.const(node.name,t)],t),orelse=host)
            field={'key':'key','ключ':'key','value':'value','значение':'value'}.get(node.name.casefold())
            if field is not None:host=self.node(py.IfExp,t,test=exact('_MapEntry'),body=self.attribute(self.name(receiver,t),field,t),orelse=host)
            host=self.node(py.IfExp,t,test=exact('list'),body=self.call('_array_member',[self.name(receiver,t),self.const(node.name,t)],t),orelse=host)
            structure=self.call('_structure_get_known',[self.name(receiver,t),self.const(node.name.casefold(),t),self.const(node.name,t)],t)
            host=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=structure,orelse=host)
            dictionary=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(node.name,t),ctx=py.Load())
            read=self.node(py.IfExp,t,test=exact('dict'),body=dictionary,orelse=host)
            operation=self.region_ops.get(id(node)) if self.region_active else None
            if operation in ('row_get','item_get'):
                arguments=[self.name('_context',t),self.name(receiver,t)]
                if operation=='row_get':arguments.append(self.const(node.name,t))
                fast=self.invoke(self.region_helper(operation,t),arguments,t)
                read=self.node(py.IfExp,t,test=self.name('_collection_fast',t),body=fast,orelse=read)
            pair=self.node(py.Tuple,t,elts=[bind,read],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Index:
            receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
            def exact(kind):
                return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            bound_native=self.call('_partial',[self.name('_native_getitem',t),self.name(receiver,t)],t)
            map_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_TypedMap'),exact('_NakedMap')])
            bound_map=self.attribute(self.name(receiver,t),'get',t)
            native=self.node(py.IfExp,t,test=map_test,body=bound_map,orelse=bound_native)
            native_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('dict','_TypedMap','_NakedMap','_DirectStructure')])
            host=self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__getitem__',t)],t)
            other=self.node(py.IfExp,t,test=native_test,body=native,orelse=host)
            bound_list=self.call('_partial',[self.name('_list_get',t),self.name(receiver,t)],t)
            select=self.node(py.IfExp,t,test=exact('list'),body=bound_list,orelse=other)
            call=self.invoke(select,[self.expr(node.index)],t)
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Conditional:
            return self.node(py.IfExp,t,test=self.truth(node.condition,t),body=self.expr(node.when_true),orelse=self.expr(node.when_false))
        if k is bsl.Call and type(node.callee) is bsl.Attribute and any(type(arg) is bsl.OmittedArgument for arg in node.arguments):
            callee=node.callee;root=callee.object
            while type(root) in (bsl.Group,bsl.Attribute):root=root.expression if type(root) is bsl.Group else root.object
            if type(root) is not bsl.Name:return self.call('_host_omission_error',[],t)
            t=root.token;receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_TypedMap','_NakedMap','_DirectStructure')])
            omitted=tuple(i for i,arg in enumerate(node.arguments) if type(arg) is bsl.OmittedArgument)
            bound=self.member_call(receiver,callee.name,require_value,omitted,len(node.arguments),t)
            if self.source_scopes:
                source_bound=self.invoke(self.attribute(self.name('_context',t),'resolve_source_member',t),[self.name(receiver,t),self.const(callee.name,t)],t,
                    [self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t)),self.node(py.keyword,t,arg='allow_references',value=self.const(True,t))])
                call=self.node(py.IfExp,t,test=native,body=self.call('_host_omission_error',[],t),orelse=self.dynamic_call(source_bound,node))
                pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
                return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
            args=[self.const(None,arg.token) if type(arg) is bsl.OmittedArgument else self.expr(arg) for arg in node.arguments]
            if callee.name.casefold() in ('property','свойство') and len(args)>1:
                output=node.arguments[1]
                args[1]=self.call('_canonical_reference',[self.output_reference(output,node.token) if type(output) is not bsl.OmittedArgument else self.const(None,t)],t)
            call=self.node(py.IfExp,t,test=native,body=self.call('_host_omission_error',[],t),orelse=self.invoke(bound,args,t))
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Call and type(node.callee) is bsl.Attribute and node.callee.name.casefold() in ('property','свойство'):
            callee=node.callee
            if not 1<=len(node.arguments)<=2 or type(node.arguments[0]) is bsl.OmittedArgument:
                _reject('Property arity outside research subset')
            output=None
            if len(node.arguments)==2:
                output=node.arguments[1]
                while type(output) is bsl.Group:output=output.expression
                if type(output) not in (bsl.Name,bsl.Index,bsl.Attribute):_reject('Property output shape outside research subset')
            location=callee
            while type(location) in (bsl.Attribute,bsl.Group,bsl.Call):
                location=location.object if type(location) is bsl.Attribute else location.expression if type(location) is bsl.Group else location.callee
            t=node.token;receiver=self.temp()
            bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            native_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_TypedMap','_NakedMap','_DirectStructure')])
            native=self.call('_partial',[self.name('_structure_property',t),self.name(receiver,t)],t)
            fail=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
            native=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=native,orelse=fail)
            host=self.member_call(receiver,callee.name,require_value,(),len(node.arguments),t)
            selected=self.node(py.IfExp,t,test=native_test,body=native,orelse=host)
            args=[self.expr(node.arguments[0])]
            if output is not None:
                converter=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=self.name('_identity_reference',t),orelse=self.name('_canonical_reference',t))
                args.append(self.invoke(converter,[self.output_reference(output,node.token if type(output) is not bsl.Name or self.external_name(output.name) else None)],node.token))
            call=self.invoke(selected,args,t)
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
            receiver=self.temp();bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(callee.object))
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            native_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_TypedMap','_NakedMap','_DirectStructure')])
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
                maps=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_TypedMap'),exact('_NakedMap')])
                fail=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
                mapped=self.node(py.IfExp,t,test=maps,body=self.attribute(self.name(receiver,t),'get',t),orelse=fail)
                native=self.node(py.IfExp,t,test=exact('list'),body=self.call('_partial',[self.name('_list_get',t),self.name(receiver,t)],t),orelse=mapped)
            else:
                native=self.attribute(self.name(receiver,t),'append',t)
                if not node.arguments:native=self.call('_partial',[native,self.const(None,t)],t)
                fail=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t)
                native=self.node(py.IfExp,t,test=exact('list'),body=native,orelse=fail)
            selected=self.node(py.IfExp,t,test=native_test,body=native,orelse=host)
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
                allowed={'add':('list',),'get':('list','_TypedMap','_NakedMap'),'set':('list',),'find':('list',),'ubound':('list',)}.get(method)
                if allowed:
                    ok=exact(allowed[0]) if len(allowed)==1 else self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in allowed])
                    native_callable=self.node(py.IfExp,t,test=ok,body=native_callable,orelse=self.call('_native_method_missing',[self.name(receiver,t),self.const(callee.name,t)],t))
                selected=self.node(py.IfExp,t,test=choose,body=native_callable,orelse=host)
                guard=self.node(py.IfExp,t,test=self.name(mode,t),body=self.call('_invalid_native_arity',[self.const(message,t)],t),orelse=self.const(None,t))
            if dynamic:
                call=self.dynamic_call(selected,node,native_mode=mode,argument_guard=guard)
            else:
                arguments=[self.expr(arg) for arg in node.arguments]
                if guard is not None:
                    packed=self.node(py.Tuple,t,elts=[*arguments,guard],ctx=py.Load())
                    actuals=self.node(py.Subscript,t,value=packed,slice=self.node(py.Slice,t,lower=None,upper=self.const(-1,t),step=None),ctx=py.Load())
                    arguments=[self.node(py.Starred,t,value=actuals,ctx=py.Load())]
                call=self.invoke(selected,arguments,t)
            pair=self.node(py.Tuple,t,elts=[bind,call],ctx=py.Load())
            return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())
        if k is bsl.Call and type(node.callee) is bsl.Name and node.callee.name.casefold() in self.routines:
            routine=self.routines[node.callee.name.casefold()]
            if require_value and not routine.is_function:
                return self.call('_procedure_value_error',[self.const(routine.name,node.callee.token)],node.callee.token)
            required=max((index+1 for index,parameter in enumerate(routine.parameters) if parameter.default is None),default=0)
            if not required<=len(node.arguments)<=len(routine.parameters):
                return self.call('_argument_count_error',[self.const(routine.name,node.callee.token),self.const(len(routine.parameters),node.callee.token),self.const(len(node.arguments),node.callee.token)],node.callee.token)
            arguments=[]
            for parameter,arg in zip(routine.parameters,node.arguments):
                if type(arg) is bsl.OmittedArgument:arguments.append(self.name('_OMITTED_REF',arg.token))
                elif parameter.by_value:arguments.append(self.expr(arg))
                else:
                    plain=arg
                    while type(plain) is bsl.Group:plain=plain.expression
                    arguments.append(self.output_reference(plain,node.callee.token if type(plain) is not bsl.Name or self.external_name(plain.name) else None) if type(plain) in (bsl.Name,bsl.Index,bsl.Attribute) else self.call('_Cell',[self.expr(arg)],node.callee.token))
            function=self.name(self.routine_symbols[routine.name.casefold()],node.callee.token)
            if self.source_scopes or self.authority:
                check=self.invoke(self.attribute(self.name('_context',t),'_check',t),[],t)
                function=self.node(py.Subscript,t,value=self.node(py.Tuple,t,elts=[check,function],ctx=py.Load()),slice=self.const(-1,t),ctx=py.Load())
            return self.invoke(function,arguments,node.callee.token)
        if k is bsl.Call and type(node.callee) is bsl.Name:
            name=node.callee.name.casefold();self.check_name(name);self.required.add(name)
            external_call=self.external_name(name) and name in self.callable_externals
            if self.external_name(name) and not external_call:_reject('external namespace names are not callable: '+node.callee.name)
            if external_call:fallback=self.name('_MISSING',t)
            elif self.scope is not None and name not in self.scope['globals']:
                # Presence is dynamic after conditional assignment. Preserve the
                # ordinary locals() probe even for known/absent bindings: its
                # retained frame-local values are observable to finalizers.
                if name not in self.scope['slots']:self.scope['slots'][name]=self.temp()
                slot=self.scope['slots'][name];value=self.name(slot,t)
                if name in self.scope['boxed']:value=self.attribute(value,'value',t)
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
            bound=self.invoke(self.attribute(self.name('_context',t),'resolve_service',t),[self.const(node.callee.name if self.source_scopes else name,t),fallback],node.callee.token,
                [self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='allow_references',value=self.const(True,t)),self.node(py.keyword,t,arg='argument_count',value=self.const(len(node.arguments),t))])
            if name in ('eval','вычислить'):
                bound=self.call('_bind_eval',[bound,*self.fragment_arguments(t)],t)
            return self.dynamic_call(bound,node)
        if k is bsl.Call:
            location=node.callee
            while type(location) in (bsl.Call,bsl.Group,bsl.Attribute):location=location.callee if type(location) is bsl.Call else location.expression if type(location) is bsl.Group else location.object
            t=location.token
            bound=self.invoke(self.attribute(self.name('_context',t),'resolve_callable',t),[self.expr(node.callee)],t,[self.node(py.keyword,t,arg='require_value',value=self.const(require_value,t)),self.node(py.keyword,t,arg='allow_references',value=self.const(True,t))])
            return self.dynamic_call(bound,node,call_token=t)
        _reject('unsupported expression '+k.__name__)
    def output_reference(self,node,reference_token=None):
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
                value=self.call('_bound_ref',[slot],t)
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
        def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
        kinds=('list','dict','_TypedMap','_NakedMap','_DirectStructure') if type(node) is bsl.Index else ('dict','_TypedMap','_NakedMap','_DirectStructure')
        native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in kinds])
        if type(node) is bsl.Index:
            constructor=self.call('_partial',[self.name('_IndexRef',t),self.name(receiver,t)],t,[self.node(py.keyword,t,arg='checked',value=self.const(True,t))])
            host=self.call('_partial',[self.attribute(self.name('_context',t),'reference_index',t),self.name(receiver,t)],t)
            argument=self.expr(node.index)
        else:
            constructor=self.call('_partial',[self.name('_AttributeRef',t),self.name(receiver,t)],t)
            host=self.call('_partial',[self.attribute(self.name('_context',t),'reference_member',t),self.name(receiver,t)],t)
            argument=self.const(node.name,t)
        selected=self.node(py.IfExp,t,test=native,body=constructor,orelse=host)
        result=self.invoke(selected,[argument],t)
        pair=self.node(py.Tuple,t,elts=[bind,result],ctx=py.Load())
        return self.node(py.Subscript,t,value=pair,slice=self.const(-1,t),ctx=py.Load())

    def access_argument(self,node,requires,call_token):
        # Select reference/value mode first, but emit receiver/index only once.
        mode=self.temp();receiver=self.temp();t=node.token;rt=call_token
        mode_bind=self.node(py.NamedExpr,rt,target=self.name(mode,rt,True),value=requires)
        bind=self.node(py.NamedExpr,t,target=self.name(receiver,t,True),value=self.expr(node.object))
        def exact(kind,token=t):return self.node(py.Compare,token,left=self.call('type',[self.name(receiver,token)],token),ops=[py.Is()],comparators=[self.name(kind,token)])
        def native_test(kinds,token=t):return self.node(py.BoolOp,token,op=py.Or(),values=[exact(kind,token) for kind in kinds])
        dicts=('dict','_TypedMap','_NakedMap','_DirectStructure')
        if type(node) is bsl.Index:
            reference=self.call('_partial',[self.name('_IndexRef',rt),self.name(receiver,rt)],rt,[self.node(py.keyword,rt,arg='checked',value=self.const(True,rt))])
            host_ref=self.call('_partial',[self.attribute(self.name('_context',rt),'reference_index',rt),self.name(receiver,rt)],rt)
            reference=self.node(py.IfExp,rt,test=native_test(('list',*dicts),rt),body=reference,orelse=host_ref)
            read=self.call('_partial',[self.name('_native_getitem',t),self.name(receiver,t)],t)
            maps=native_test(('_TypedMap','_NakedMap'))
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
            read=self.node(py.IfExp,t,test=native_test(('_TypedMap','_NakedMap')),body=self.call('_native_property_missing',[self.const(node.name,t)],t),orelse=read)
            field={'key':'key','ключ':'key','value':'value','значение':'value'}.get(node.name.casefold())
            if field is not None:read=self.node(py.IfExp,t,test=exact('_MapEntry'),body=self.attribute(self.name(receiver,t),field,t),orelse=read)
            read=self.node(py.IfExp,t,test=exact('list'),body=self.call('_array_member',[self.name(receiver,t),self.const(node.name,t)],t),orelse=read)
            structure=self.call('_structure_get_known',[self.name(receiver,t),self.const(node.name.casefold(),t),self.const(node.name,t)],t)
            read=self.node(py.IfExp,t,test=exact('_DirectStructure'),body=structure,orelse=read)
            dictionary=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(node.name,t),ctx=py.Load())
            read=self.node(py.IfExp,t,test=exact('dict'),body=dictionary,orelse=read)
            result=self.node(py.IfExp,rt,test=self.name(mode,rt),body=reference,orelse=read)
        converter=self.node(py.IfExp,rt,test=self.name(mode,rt),body=self.name('_canonical_reference',rt),orelse=self.name('_identity_reference',rt))
        converted=self.invoke(converter,[result],rt)
        pair=self.node(py.Tuple,rt,elts=[mode_bind,bind,converted],ctx=py.Load())
        return self.node(py.Subscript,rt,value=pair,slice=self.const(-1,rt),ctx=py.Load())

    def dynamic_call(self,bound,node,references=True,call_token=None,native_mode=None,argument_guard=None):
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
        args=[]
        for index,arg in enumerate(node.arguments):
            if index in omitted:
                args.append(self.node(py.Subscript,t,value=self.name(defaults,t),slice=self.const(index,t),ctx=py.Load()));continue
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
            if type(plain) is bsl.Name:
                self.check_name(plain.name)
                def reference():
                    key=plain.name.casefold()
                    if self.external_name(key):return self.invoke(self.attribute(self.name('_context',t),'external_reference',t),[self.const(key,t)],t)
                    if self.scope is not None and key not in self.scope['globals']:
                        getter,setter=self.scope['host_helpers'][key]
                        args=[self.name(getter,plain.token),self.name(setter,plain.token),self.const(plain.name,plain.token)]
                        if key in self.scope['boxed']:args.append(self.name(self.scope['slots'][key],plain.token))
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
        return self.call('_truth',[self.expr(node)],token)
    def sequence(self,nodes):
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
    def statement(self,node):
        t=node.token
        result=[]
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
        if self.authority and type(node) in (bsl.For,bsl.While,bsl.ForEach):
            for loop in emitted:
                if type(loop) is py.While:
                    check=self.invoke(self.attribute(self.name('_context',t),'checkpoint',t),[],t)
                    loop.test=self.node(py.Subscript,t,value=self.node(py.Tuple,t,elts=[check,loop.test],ctx=py.Load()),slice=self.const(-1,t),ctx=py.Load())
        result.extend(emitted)
        if self.region_active and type(node) is bsl.For:result.append(reset())
        return result
    def _statement(self,node):
        self.visits+=1;t=node.token;k=type(node)
        if k is bsl.Execute:
            return [self.node(py.Expr,t,value=self.call('_execute_fragment',[self.expr(node.expression),*self.fragment_arguments(t)],t))]
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
            target=node.target;receiver=self.temp();writer=self.temp();index=self.temp();stored=self.temp()
            def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_TypedMap','_NakedMap','_DirectStructure')])
            resolver=self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__setitem__',t)],t)
            selected=self.node(py.IfExp,t,test=native,body=self.const(None,t),orelse=resolver)
            body=[assign(receiver,self.expr(target.object)),assign(writer,selected),assign(index,self.expr(target.index)),assign(stored,self.expr(node.value))]
            invoke=self.node(py.Expr,t,value=self.invoke(self.name(writer,t),[self.name(index,t),self.name(stored,t)],t))
            checked=self.call('_checked_array_index',[self.name(receiver,t),self.name(index,t)],t)
            position=self.node(py.IfExp,t,test=exact('list'),body=checked,orelse=self.name(index,t))
            slot=self.node(py.Subscript,t,value=self.name(receiver,t),slice=position,ctx=py.Store())
            write=self.node(py.Assign,t,targets=[slot],value=self.name(stored,t))
            test=self.node(py.Compare,t,left=self.name(writer,t),ops=[py.IsNot()],comparators=[self.const(None,t)])
            body.append(self.node(py.If,t,test=test,body=[invoke],orelse=[write]));return body
        if k is bsl.Assign and type(node.target) is bsl.Attribute:
            target=node.target;receiver=self.temp();writer=self.temp();stored=self.temp()
            def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('dict','_TypedMap','_NakedMap','_DirectStructure')])
            resolver=self.invoke(self.attribute(self.name('_context',t),'resolve_set_member',t),[self.name(receiver,t),self.const(target.name,t)],t)
            selected=self.node(py.IfExp,t,test=native,body=self.const(None,t),orelse=resolver)
            if self.region_active and self.region_ops.get(id(node))=='row_set':
                selected=self.region_selected(selected,'row_set',receiver,t,[self.const(target.name,t)])
            body=[assign(receiver,self.expr(target.object)),assign(writer,selected),assign(stored,self.expr(node.value))]
            invoke=self.node(py.Expr,t,value=self.invoke(self.name(writer,t),[self.name(stored,t)],t))
            slot=self.node(py.Subscript,t,value=self.name(receiver,t),slice=self.const(target.name,t),ctx=py.Store())
            write=self.node(py.Assign,t,targets=[slot],value=self.name(stored,t))
            absent=self.node(py.Compare,t,left=self.name(writer,t),ops=[py.Is()],comparators=[self.const(None,t)])
            branch=self.node(py.If,t,test=absent,body=[write],orelse=[invoke])
            map_test=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_TypedMap'),exact('_NakedMap')])
            fail=self.node(py.Expr,t,value=self.call('_native_property_write_missing',[self.const(target.name,t)],t))
            body.append(self.node(py.If,t,test=map_test,body=[fail],orelse=[branch]));return body
        if k is bsl.Return:
            if self.scope is None:_reject('module Return outside research subset')
            value=self.expr(node.value) if node.value is not None else self.const(None,t)
            if self.scalar_routines:value=self.invoke(self.attribute(self.name('_context',t),'scalar_result',t),[value],t)
            return [self.node(py.Return,t,value=value)]
        if k is bsl.Var:
            result=[]
            for name in node.names:
                self.check_name(name)
                if self.scope is not None and name.casefold() not in self.scope['globals']:
                    if name.casefold() in self.scope['boxed']:
                        slot=self.name(self.scope['slots'][name.casefold()],t)
                        test=self.node(py.Compare,t,left=self.attribute(slot,'_value',t),ops=[py.Is()],comparators=[self.name('_UNSET_REF',t)])
                        assign=self.node(py.Assign,t,targets=[self.target(name,t)],value=self.const(None,t))
                        result.append(self.node(py.If,t,test=test,body=[assign],orelse=[]));continue
                    if name.casefold() not in self.scope['initialized']:
                        result.append(self.node(py.Assign,t,targets=[self.target(name,t)],value=self.const(None,t)))
                    continue
                result.append(self.node(py.Expr,t,value=self.invoke(self.attribute(self.name('_initial',t),'setdefault',t),[self.const(name.casefold(),t),self.const(None,t)],t)))
            return result
        if k is bsl.ExpressionStatement:return [self.node(py.Expr,t,value=self.expr(node.expression,node is self.require_last_expression))]
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
            for condition,body in node.branches:
                condition=self.truth(condition,t)
                branches.append(self.node(py.If,t,test=condition,body=branch_sequence(body) or [self.node(py.Pass,t)],orelse=[]))
            tail=branch_sequence(node.otherwise)
            if self.scope is not None:
                common=initialized_paths[0].intersection(*initialized_paths[1:])
                for key in common:self.initialize_local(key)
            for branch in reversed(branches):branch.orelse=tail;tail=[branch]
            return tail
        if k is bsl.For:
            first=self.temp();last=self.temp()
            result=[self.node(py.Assign,t,targets=[self.name(first,t,True)],value=self.expr(node.start)),self.node(py.Assign,t,targets=[self.name(last,t,True)],value=self.expr(node.end)),self.assign_name(node.name,self.name(first,t),t)]
            body=self.loop_body(node.body,(node.name,t))
            body.append(self.increment(node.name,t))
            condition=self.node(py.Compare,t,left=self.read(node.name,t),ops=[py.LtE()],comparators=[self.name(last,t)])
            result.append(self.node(py.While,t,test=condition,body=body,orelse=[]));return result
        if k is bsl.ForEach:
            self.check_name(node.name)
            receiver=self.temp();bound=self.temp();iterator=self.temp();key=self.temp();value=self.temp()
            def assign(name,value):return self.node(py.Assign,t,targets=[self.name(name,t,True)],value=value)
            def exact(kind):return self.node(py.Compare,t,left=self.call('type',[self.name(receiver,t)],t),ops=[py.Is()],comparators=[self.name(kind,t)])
            entry=self.call('_MapEntry',[],t,[self.node(py.keyword,t,arg='key',value=self.name(key,t)),self.node(py.keyword,t,arg='value',value=self.name(value,t))])
            pair=self.node(py.Tuple,t,elts=[self.name(key,t,True),self.name(value,t,True)],ctx=py.Store())
            items=self.invoke(self.attribute(self.name(receiver,t),'items',t),[],t)
            generator=self.node(py.GeneratorExp,t,elt=entry,generators=[py.comprehension(target=pair,iter=items,ifs=[],is_async=0)])
            dictionary=self.call('isinstance',[self.name(receiver,t),self.name('dict',t)],t)
            iterable=self.node(py.IfExp,t,test=dictionary,body=generator,orelse=self.name(receiver,t))
            native=self.node(py.BoolOp,t,op=py.Or(),values=[exact(kind) for kind in ('list','dict','_TypedMap','_NakedMap','_DirectStructure')])
            host=self.invoke(self.invoke(self.attribute(self.name('_context',t),'resolve_member',t),[self.name(receiver,t),self.const('__iter__',t)],t),[],t)
            selected=self.node(py.IfExp,t,test=native,body=self.call('iter',[iterable],t),orelse=host)
            result=[assign(receiver,self.expr(node.collection)),assign(bound,selected),assign(iterator,self.call('iter',[self.name(bound,t)],t))]
            changes=set();journals=self.scope.setdefault('initialization_journals',[]) if self.scope is not None else None
            if journals is not None:journals.append(changes)
            advance=self.assign_name(node.name,self.call('next',[self.name(iterator,t)],t),t)
            stop=self.node(py.ExceptHandler,t,type=self.name('StopIteration',t),name=None,body=[self.node(py.Break,t)])
            maps=self.node(py.BoolOp,t,op=py.Or(),values=[exact('_TypedMap'),exact('_NakedMap')])
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
        if k is bsl.Break:
            if not self.loop_increments:_reject('Break outside a loop')
            return [self.node(py.Break,t)]
        if k is bsl.Continue:
            if not self.loop_increments:_reject('Continue outside a loop')
            increment=self.loop_increments[-1] if self.loop_increments else None
            return ([self.increment(*increment)] if increment else [])+[self.node(py.Continue,t)]
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
            manager=self.call('_handled_error',[self.name('_context',t),self.name(caught,t),self.const(self.filename,t),self.const(self.source,t)],t)
            handler_body=self.node(py.With,t,items=[py.withitem(context_expr=manager,optional_vars=None)],body=error_path(node.handler) or [self.node(py.Pass,t)])
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
    from .python_direct_collection_regions import analyze
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


def compile_module(vm,program,nodes,source_text,source_name,*,_exports=False,_whole_source=False,_require_last_expression=False,_profile=None,_source_scopes=False,_authority=False,_scalar_routines=False,_callable_externals=(),_shadowable=(),_configuration_calls=False,_host_bindings=False,_catalog_bounds=False):
    """Lower a module; the whole-source wrapper is the default compile entry."""
    if not _native_partial_binding(partial):_reject('noncanonical partial binding is outside research contract')
    if not _native_operator_binding(_NATIVE_ADD,'add') or not _native_operator_binding(_NATIVE_GETITEM,'getitem'):
        _reject('noncanonical operator binding is outside research contract')
    from .python_direct_imports import import_names
    imported=import_names(vm,program) if _profile is None else ()
    program=[node for node in program if type(node) is not bsl.Import and
             (_profile is not None or (type(node) is not bsl.ServerInitializer and
              (type(node) not in (bsl.Var,bsl.Routine) or (node.execution_context=='client' and not getattr(node,'is_dual',False)))))]
    count=_bounds(program)
    if not program:
        from .syntax.lexer import Token
        token=nodes[0].token if nodes else Token('EOF','',1,1,source_name or '<строка>','')
        program=[bsl.ExpressionStatement(token,bsl.Literal(token,None))]
        if not nodes:nodes=tuple(program)
    filename=source_name or nodes[0].token.source
    if source_text is None:
        lines={node.token.line:node.token.source_line for node in nodes}
        source_text='\n'.join(lines.get(line,'') for line in range(1,max(lines,default=0)+1))
    emitter=Emitter(filename,source_text)
    emitter.owned_constructors=_profile is not None;emitter.configuration_calls=_configuration_calls;emitter.host_bindings=_host_bindings;emitter.catalog_bounds=_catalog_bounds;emitter.source_scopes=_source_scopes;emitter.authority=_authority;emitter.scalar_routines=_scalar_routines
    emitter.callable_externals=frozenset(_callable_externals);emitter.shadowable=frozenset(_shadowable)
    emitter.import_names=frozenset(imported);t=program[0].token
    if _require_last_expression:emitter.require_last_expression=program[-1]
    from .python_direct_services import CONSTRUCTORS
    from .python_direct_value_tree import CONSTRUCTOR_NAMES as TREE_NAMES
    emitter.constructor_names=frozenset(CONSTRUCTORS)|frozenset(TREE_NAMES)|{'uuid','уникальныйидентификатор'}
    from .python_direct_database import NAMES as DATABASE_NAMES
    emitter.external_names=set(NAMES)
    if _profile is None and vm.database_context is not None:
        emitter.external_names.update(DATABASE_NAMES);emitter.constructor_names|={'query','запрос'}
    if _profile is not None:
        module_names,external_names,constructors=_profile
        emitter.external_names={name.casefold() for name in external_names}
        emitter.constructor_names=frozenset(name.casefold() for name in constructors)
    else:module_names=vm.module_names
    emitter.routines={node.name.casefold():node for node in program if type(node) is bsl.Routine}
    emitter.routine_symbols={key:emitter.temp() for key in emitter.routines}
    emitter.module_globals={name.casefold() for node in program if type(node) is bsl.Var for name in node.names}|{name.casefold() for name in module_names}
    if emitter.external_names & (emitter.module_globals|emitter.routines.keys()):
        from .python_direct import _reject as reject_contract
        reject_contract('external names collide with module declarations')
    conditional_shadow_names=emitter.module_globals|emitter.external_names|{'thisobject','этотобъект'}
    definitions=[];any_region=False
    from .python_direct_collection_regions import analyze,admitted,helpers
    for key,routine in emitter.routines.items():
        if routine.is_async:
            _reject('asynchronous routine requires a scheduler-aware compiler')
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
            elif kind not in (bsl.Return,bsl.ExpressionStatement,bsl.Break,bsl.Continue,bsl.Raise,bsl.Execute):_reject('routine control flow outside research subset')
        parameters={parameter.name.casefold() for parameter in routine.parameters}
        globals_=emitter.module_globals-declarations-parameters
        slots={parameter.name.casefold():emitter.temp() for parameter in routine.parameters}
        emitter.scope={'globals':globals_,'externals':emitter.external_names-parameters-declarations,'local_declarations':parameters|{name.casefold() for stmt in routine.body if type(stmt) is bsl.Var for name in stmt.names},'bindings':assigned|declarations|parameters,'initialized':set(parameters),'slots':slots,'boxed':{parameter.name.casefold() for parameter in routine.parameters if not parameter.by_value}}
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
                if type(callee) is bsl.Name and callee.name.casefold() in emitter.routines:
                    signature=emitter.routines[callee.name.casefold()]
                    actuals=[arg for parameter,arg in zip(signature.parameters,value.arguments) if not parameter.by_value]
                elif type(callee) is bsl.Attribute and _ALIASES.get(callee.name.casefold(),callee.name.casefold())=='property':
                    actuals=value.arguments[1:2]
                elif type(callee) is not bsl.Attribute or emitter.source_scopes or emitter.host_bindings:
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
        # Unbound names are lexical missing values at execution, not a reason
        # to reject an otherwise valid declaration-only handler factory.
        emitter.scope['bindings'].update(lexical)
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
            assign=emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=fallback)
            prologue.append(emitter.node(py.If,token,test=test,body=[assign],orelse=[]))
            if parameter.name.casefold() in emitter.scope['boxed']:
                factory='_Cell' if parameter.by_value else '_as_ref'
                prologue.append(emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=emitter.call(factory,[emitter.name(slot,token)],token)))
        for name in sorted(emitter.scope['boxed']-parameters):
            prologue.append(emitter.node(py.Assign,routine.token,targets=[emitter.name(slots[name],routine.token,True)],value=emitter.call('_Cell',[],routine.token)))
        for name,(getter,setter) in emitter.scope['host_helpers'].items():
            slot=slots[name];token=routine.token;boxed=name in emitter.scope['boxed']
            if not boxed:
                declare=emitter.node(py.Assign,token,targets=[emitter.name(slot,token,True)],value=emitter.const(None,token))
                prologue.append(emitter.node(py.If,token,test=emitter.const(False,token),body=[declare],orelse=[]))
            target=emitter.read(name,token) if emitter.source_scopes or emitter.host_bindings else (emitter.attribute(emitter.name(slot,token),'value',token) if boxed else emitter.name(slot,token))
            args=py.arguments(posonlyargs=[],args=[],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
            prologue.append(emitter.node(py.FunctionDef,token,name=getter,args=args,body=[emitter.node(py.Return,token,value=target)],decorator_list=[],returns=None,type_comment=None))
            target=emitter.node(py.Attribute,token,value=emitter.name(slot,token),attr='value',ctx=py.Store()) if boxed else emitter.name(slot,token,True)
            assign=emitter.node(py.Assign,token,targets=[target],value=emitter.name('_new',token))
            body=[assign] if boxed else [emitter.node(py.Nonlocal,token,names=[slot]),assign]
            args=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,token,arg='_new',annotation=None)],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
            prologue.append(emitter.node(py.FunctionDef,token,name=setter,args=args,body=body,decorator_list=[],returns=None,type_comment=None))
        if shadows and has_fragments:_reject('source implicit namespace shadow with Execute/Eval is not integrated')
        routine_end,emitter.region_ops,emitter.region_states=(0,{}, {}) if emitter.authority or emitter.source_scopes else _routine_region(routine,emitter.scope)
        emitter.region_active=bool(routine_end)
        region_body=emitter.sequence(routine.body[:routine_end])
        emitter.region_active=False
        ordinary_body=emitter.sequence(routine.body[routine_end:])
        if routine_end:
            any_region=True
            prologue.append(emitter.node(py.Assign,routine.token,targets=[emitter.name('_collection_fast',routine.token,True)],value=emitter.const(False,routine.token)))
        routine_body=prologue+(region_body+ordinary_body or [emitter.node(py.Pass,routine.token)])
        if emitter.source_scopes:
            manager=emitter.invoke(emitter.attribute(emitter.name('_context',routine.token),'routine_scope',routine.token),[],routine.token)
            routine_body=[emitter.node(py.With,routine.token,items=[py.withitem(context_expr=manager,optional_vars=None)],body=routine_body)]
        elif emitter.authority:
            check=lambda:emitter.node(py.Expr,routine.token,value=emitter.invoke(emitter.attribute(emitter.name('_context',routine.token),'_check',routine.token),[],routine.token))
            routine_body=[check(),emitter.node(py.Try,routine.token,body=routine_body,handlers=[],orelse=[],finalbody=[check()])]
        emitter.region_ops={};emitter.region_states={}
        emitter.scope=None
        args=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,parameter.token,arg=slots[parameter.name.casefold()],annotation=None) for parameter in routine.parameters],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
        first_optional=next((index for index,parameter in enumerate(routine.parameters) if parameter.default is not None),len(routine.parameters))
        args.defaults=[emitter.name('_OMITTED_REF',routine.token) for _ in routine.parameters[first_optional:]]
        definitions.append(emitter.node(py.FunctionDef,routine.token,name=emitter.routine_symbols[key],args=args,body=routine_body,decorator_list=[],returns=None,type_comment=None))
    from .python_direct_collection_regions import analyze,admitted,helpers
    region_end=0
    if not emitter.routines and not emitter.authority and not emitter.source_scopes:
        region_end,emitter.region_ops,emitter.region_states=analyze(program,opaque_names=emitter.external_names)
    emitter.region_active=bool(region_end)
    body=emitter.sequence(program[:region_end])
    emitter.region_active=False
    body+=emitter.sequence([node for node in program[region_end:] if type(node) is not bsl.Routine])
    if region_end:body.insert(0,emitter.node(py.Assign,t,targets=[emitter.name('_collection_fast',t,True)],value=emitter.const(False,t)))
    if type(program[-1]) is bsl.ExpressionStatement:
        last=body.pop();body.append(emitter.node(py.Return,program[-1].token,value=last.value))
    else:body.append(emitter.node(py.Return,t,value=emitter.node(py.Dict,t,keys=[],values=[]) if _exports and not emitter.routines else emitter.name('_initial',t)))
    initializers=[emitter.node(py.Assign,t,targets=[emitter.name(slot,t,True)],value=emitter.call('_SlotReference',[emitter.name('_initial',t),emitter.const(key,t)],t)) for key,slot in emitter.source_refs.items()]
    if emitter.routines:
        exports=emitter.node(py.Dict,t,keys=[emitter.const(key,t) for key in emitter.routines],values=[emitter.name(emitter.routine_symbols[key],t) for key in emitter.routines])
        bind_return=emitter.node(py.If,t,test=emitter.name('_bind_only',t),body=[emitter.node(py.Return,t,value=exports)],orelse=[])
        declarations=[]
        for key in sorted(emitter.module_globals):
            initialize=emitter.invoke(emitter.attribute(emitter.name('_initial',t),'setdefault',t),[emitter.const(key,t),emitter.const(None,t)],t)
            declarations.append(emitter.node(py.Expr,t,value=initialize))
        initialize=emitter.node(py.If,t,test=emitter.const(True,t) if _exports else emitter.node(py.UnaryOp,t,op=py.Not(),operand=emitter.name('_bind_only',t)),body=declarations or [emitter.node(py.Pass,t)],orelse=[])
        body=[initialize,*definitions,bind_return,*body]
    body=initializers+body
    arguments=py.arguments(posonlyargs=[],args=[emitter.node(py.arg,t,arg=name,annotation=None) for name in ('_initial','_constants','_outputs','_context')],vararg=None,kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])
    if emitter.routines:
        arguments.args.append(emitter.node(py.arg,t,arg='_bind_only',annotation=None));arguments.defaults.append(emitter.const(_exports,t))
    function=emitter.node(py.FunctionDef,t,name='naked_module',args=arguments,body=body,decorator_list=[],returns=None,type_comment=None)
    tree=py.Module(body=[function],type_ignores=[])
    equal,not_equal=scalar.map_identity_operators(array=True,structure=True)
    equal,not_equal=scalar.numeric_boolean_operators(equal,not_equal)
    from . import experimental_naked_live_state as live_state
    namespace=dict(_execute_fragment=execute_fragment,_fragment_binding=_fragment_binding,_bind_eval=bind_eval,_raise_arity_error=raise_arity_error,_host_omission_error=_host_omission_error,_host_omission_values=_host_omission_values,_dynamic_construct=dynamic_construct,_invalid_native_arity=_invalid_native_arity,_typed_find=scalar.typed_find,_list_delete=_list_delete,_native_ubound=_native_ubound,_readonly=readonly,_array_set_checked=_array_set_checked,_bounded_insert=bounded_insert,_structure_insert=structure_insert,_array_constructor_bounds=bounded_array,_new_structure=new_structure,_structure_from_schema=structure_from_schema,_host_name_reference=_host_name_reference,_Cell=_Cell,_as_ref=_as_ref,_bound_ref=_bound_ref,_UNSET_REF=_UNSET_REF,_OMITTED_REF=_OMITTED_REF,_argument_count_error=_argument_count_error,_routine_value_error=_routine_value_error,_procedure_value_error=_procedure_value_error,_identity_reference=_identity_reference,_IndexRef=_IndexRef,_AttributeRef=_AttributeRef,_SlotReference=live_state._SlotReference,_source_reference=source_reference,_canonical_reference=_canonical_reference,_structure_property=structure_property,_native_method_missing=_native_method_missing,_native_count=_native_count,_MapEntry=_MapEntry,_array_member=_array_member,_native_property_missing=_native_property_missing,_structure_get_known=structure_get_known,_native_property_write_missing=_native_property_write_missing,_checked_array_index=_checked_array_index,_partial=partial,_native_getitem=_NATIVE_GETITEM,_list_get=_list_get,_TypedMap=_TypedMap,_NakedMap=_NakedMap,_DirectStructure=_DirectStructure,_host_reference=host_reference,_UNSET=UNSET,_missing=missing,_native_add=_NATIVE_ADD,_concatenate=scalar.concatenate,_divide=scalar.decimal_divide,_sign=scalar.decimal_sign,_order=scalar.uca_order,_truth=scalar.truth,_equal=equal,_not_equal=not_equal,_MISSING=_MISSING,_handled_error=handled_error,_reraise_handled=reraise_handled,_raise_error=raise_error,_presentation=scalar.presentation,_BSLRuntimeError=BSLRuntimeError)
    if region_end or any_region:namespace.update(_collection_admitted=admitted,_collection_helpers=helpers(),_routine_region_state_safe=_routine_region_state_safe)
    # Every route genuinely compiles executable code before source effects.
    # Whole-source research additionally parses the actual source, not a fake
    # notification or an ignored authorization probe.
    generated='<direct AST research: no generated text>';roundtrip_visits=0
    if _whole_source:tree,generated,roundtrip_visits=_source_roundtrip(tree,filename)
    code=compile(tree,filename,'exec');exec(code,namespace)
    result=Program(generated,tuple(emitter.constants),namespace['naked_module'],{},frozenset(REPAIRS),source_name=filename,source_text=source_text,required_services=tuple(sorted(emitter.required)),trusted_entry=True)
    if emitter.authority:result.repairs=result.repairs|{'authority_checkpoints'}
    result._source_implicit_shadows=frozenset(emitter.implicit_shadows)
    result._research_lowering_counts=(count,emitter.visits,emitter.python_nodes)
    result._research_roundtrip_visits=roundtrip_visits
    return result


def compile_module_whole_source(vm,program,nodes,source_text,source_name,*,_exports=False,_require_last_expression=False):
    """Default source-plus-AST compile entry; never replay through another compiler."""
    return compile_module(vm,program,nodes,source_text,source_name,
                          _exports=_exports,_whole_source=True,_require_last_expression=_require_last_expression)


def compile_owned(program, *, source_text, source_name, module_names=(),
                  external_names=(), constructors=(), exports=False, source_scopes=False,
                  authority_checks=False, scalar_routines=False, callable_externals=(),
                  shadowable_externals=(), require_last_expression=False, configuration_calls=False, host_bindings=False, catalog_bounds=False):
    """Compile an already-authorized side's declarations to Python definitions.

    Namespace inputs describe names, not a runtime grant. The owning invocation
    still supplies its checked context and state. No interpreter or old emitter
    is called, and no foreign side is inferred from ambient VM state.
    """
    for flag in (exports,source_scopes,authority_checks,scalar_routines,require_last_expression,configuration_calls,host_bindings,catalog_bounds):
        if type(flag) is not bool:raise TypeError('owned compile flags require Boolean')
    for names in (module_names,external_names,constructors,callable_externals,shadowable_externals):
        if type(names) is not tuple or any(type(name) is not str for name in names):
            raise TypeError('owned compile namespaces require tuples of names')
    if (scalar_routines or shadowable_externals) and not source_scopes:
        raise ValueError('source capabilities require source scopes')
    if callable_externals and not (source_scopes or host_bindings):raise ValueError('callable externals require an owning binding profile')
    if catalog_bounds and not authority_checks:raise ValueError('catalog bounds require authority checkpoints')
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
            _exports=exports,_whole_source=True,_require_last_expression=require_last_expression,
            _profile=(tuple(module_names),tuple(external_names),tuple(constructors)),
            _source_scopes=source_scopes,_authority=authority_checks,
            _scalar_routines=scalar_routines,_callable_externals=callable_externals,
            _shadowable=shadowable_externals,_configuration_calls=configuration_calls,_host_bindings=host_bindings,_catalog_bounds=catalog_bounds)
    except PythonDirectUnsupported as error:
        if not source_scopes:raise
        from .experimental_naked_collections import UnsupportedNakedSyntax
        raise UnsupportedNakedSyntax(str(error)) from None
