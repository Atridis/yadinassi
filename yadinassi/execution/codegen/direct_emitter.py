"""Clean-sheet direct emitter: Python owns control flow and scalar arithmetic."""
import ast as p
from dataclasses import replace
from . import direct_goto, direct_call_exceptions, direct_call_lowering, direct_reference_lowering, direct_flow_lowering
from . import direct_routine_lowering, direct_scalar_lowering, direct_object_lowering, direct_constructor_lowering
from .direct_python_ast import _node, arguments, attr, call, literal, name
from .direct_reference_lowering import SELF_NAMES
from .direct_access_runtime import (bsl_iterable, get_field, member, metered, owned_index, owned_iterable,
                                    owned_set_index, owns_property_output, read_bracket, set_field, write_bracket)
from .direct_reference_runtime import (bind_index_reference, bind_local_index_reference, cell_actual,
                                       field_reference, fragment_reference, host_reference, indexed_actual,
                                       lexical_reference, local_field_reference, member_actual)
from decimal import Decimal
from types import FunctionType

from yadinassi.syntax import ast as b
from .direct_collections import Program, _argument_count_error, _Cell, _bound_ref, _host_omission_error, _host_omission_values, _OMITTED_REF
from yadinassi.execution.direct.python_direct_plain_map import PlainMap, plain_map
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from .direct_errors import handled_error, reraise_handled
from .direct_resources import bounded_array
from .direct_structure import _DirectStructure, new_structure
from yadinassi.execution.direct.python_direct_names import CHARS_ALIASES, NAMES as SYSTEM_NAMES
from yadinassi.types.errors import BSLRuntimeError
from .direct_live_state import UNSET, source_reference, host_reference as live_host_reference, _ForwardReference
from .direct_boundaries import BoundaryViolation, _MISSING as _SERVICE_MISSING
from yadinassi.execution.direct.python_direct_eval import bind_eval
from yadinassi.execution.direct.python_direct_execute import FragmentScope, execute_fragment
from yadinassi.types.values import HostFunction
from .direct_scalar_semantics import compare_order, concatenate, presentation, truth
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.direct.python_direct_numbers import divide, remainder, sign, public_number
from yadinassi.execution.direct.python_direct_dynamic_new import construct
from yadinassi.execution.direct.python_direct_error_info import raise_arity_error, raise_error


def native_array_expression(value):
    return isinstance(value,p.List) or (
        isinstance(value,p.Call) and isinstance(value.func,p.Name) and value.func.id=='_Array')


def source_shapes(bound, named):
    prepare=getattr(bound,'prepare_argument_shapes',None)
    if prepare is not None:prepare(named)
    return bound


def unchanged(value):
    return value


_BINARY = {'+': p.Add, '-': p.Sub, '*': p.Mult}
_COMPARE = {'=': p.Eq, '<>': p.NotEq, '<': p.Lt, '<=': p.LtE, '>': p.Gt, '>=': p.GtE}
_MISSING = object()


def self_read(context,state,key):
    return state[key] if key in state else context.current_module()


def self_write(state,key,value):
    if key not in state:raise ValueError('Модульное имя только для чтения: '+key)
    state[key]=value


def self_reference(context,state,key):
    return source_reference(state,key) if key in state else _Cell(context.current_module())


def procedure_value_error(key):
    raise TypeError('Процедура не возвращает значение: '+key)


def nonconstructible(key, missing=False):
    if missing:
        raise TypeError('Тип не определен: '+key)
    raise TypeError('Тип нельзя создать оператором Новый: '+key)
_OP = dict(_Truth=truth, _PublicNumber=public_number, _Divide=divide, _Remainder=remainder, _Sign=sign, _CompareOrder=compare_order,
           _GotoTransfer=direct_goto.GotoTransfer,_String=concatenate, _Missing=_MISSING, _OmittedRef=_OMITTED_REF, _ServiceMissing=_SERVICE_MISSING, _Unset=UNSET, _Map=PlainMap, _Nonconstructible=nonconstructible, _SelfRead=self_read, _SelfWrite=self_write, _SelfRef=self_reference,
           _Recoverable=(ArithmeticError,TypeError,ValueError,IndexError,NameError,RecursionError,BSLRuntimeError),
           _Handled=handled_error, _Reraise=reraise_handled, _Raise=raise_error,
           _RaiseArity=raise_arity_error, _InvalidCallArity=_argument_count_error,
           _ProcedureValue=procedure_value_error, _Presentation=presentation,
           _LexicalRef=lexical_reference, _FragmentRef=fragment_reference, _Eval=bind_eval, _Execute=execute_fragment, _GetAttr=getattr, _SourceShapes=source_shapes, _VarRef=source_reference, _LiveHostRef=live_host_reference, _Cell=_Cell, _BoundRef=_bound_ref,
           _BindIndexRef=bind_index_reference, _BindLocalIndexRef=bind_local_index_reference, _HostRef=host_reference, _IndexedActual=indexed_actual, _MemberActual=member_actual, _CellActual=cell_actual, _Unchanged=unchanged, _ImportedRef=_ForwardReference,
           _Construct=construct, _Array=bounded_array, _Structure=new_structure, _MapFrom=plain_map, _Omissions=_host_omission_values, _InvalidOmissions=_host_omission_error)
_OP.update(direct_call_exceptions.HELPERS)


def requires_reference(bound,index):
    test=getattr(bound,'requires_reference',None)
    return test is not None and test(index)


_OP.update(_RequiresReference=requires_reference,_OwnedIndex=owned_index,_OwnedSetIndex=owned_set_index,_Metered=metered,_OwnedIterable=owned_iterable,_BSLIterable=bsl_iterable,_Member=member,_GetField=get_field,_SetField=set_field,_FieldRef=field_reference,_LocalFieldRef=local_field_reference,_OwnsPropertyOutput=owns_property_output)
_OP.update(_WriteBracket=write_bracket,_ReadBracket=read_bracket)


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
    # The emitter selects direct Python constructs. BSL-specific behavior is
    # attached here by operation, not by running a second generator.
    omissions=staticmethod(direct_call_lowering.omissions)
    local_call=direct_call_lowering.local_call
    service_call=direct_call_lowering.service_call
    bound_call=direct_call_lowering.bound_call
    actual_address=direct_call_lowering.actual_address
    reference=direct_reference_lowering.reference
    address=direct_reference_lowering.address
    fragment_arguments=direct_reference_lowering.fragment_arguments
    address_definitions=direct_reference_lowering.address_definitions
    index=direct_object_lowering.index
    routine=direct_routine_lowering.routine
    condition=direct_scalar_lowering.condition
    block=direct_flow_lowering.block
    loop_condition=direct_flow_lowering.loop_condition
    jump=direct_flow_lowering.jump
    loop_control=direct_flow_lowering.loop_control
    goto_block=direct_flow_lowering.goto_block

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
        self.procedures=frozenset()
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
        self.persistent_services=frozenset()
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
        self.named_services=frozenset()
        self.plain_calls=False
        self.call_slots={}
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
        token=x.token
        if type(x) is b.Call and type(x.callee) is b.Name:
            # A bare call starts at its callee, not at the opening parenthesis.
            token=x.callee.token
        return _node(value,token)

    def external(self,key):
        return key in self.externals and key not in self.locals and key not in self.module_declarations

    def implicit_self(self,key):
        return (self.current_module and key in SELF_NAMES
                and key not in self.locals and key not in self.module_declarations)

    def write_self(self,key,value):
        return p.Expr(value=call('_SelfWrite',name('_S'),literal(key),value))

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
                if self.current_module and key in SELF_NAMES:
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
            return direct_scalar_lowering.unary(self, x)
        if type(x) is b.Binary:
            op=x.operator
            if op in ('AND','OR'):
                return p.BoolOp(op=p.And() if op=='AND' else p.Or(),
                                values=[self.condition(x.left),self.condition(x.right)])
            l,r=self.expr(x.left),self.expr(x.right)
            adapted=direct_scalar_lowering.binary(op,l,r)
            if adapted is not None:
                return adapted
            if op in _BINARY:
                return p.BinOp(left=l,op=_BINARY[op](),right=r)
            if op in _COMPARE:
                return p.Compare(left=l,ops=[_COMPARE[op]()],comparators=[r])
        if type(x) is b.Index:
            return self.index(x)
        if type(x) is b.Attribute:
            return call('_GetField',name('_C'),self.expr(x.object),literal(x.name))
        if type(x) is b.DynamicNew or type(x) is b.New:
            return direct_constructor_lowering.lower(self, x, want_value)
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
                    return self.local_call(key,x.arguments,want_value,x.token)
                if self.plain_calls:
                    exceptional=direct_call_exceptions.lower(self,key,x.arguments)
                    if exceptional is not None:return exceptional
                    slot=self.call_slots.get(key)
                    if slot is None:
                        slot=self.call_slots[key]=self.temp()
                    actuals=(literal(None) if type(arg) is b.OmittedArgument else self.expr(arg)
                             for arg in x.arguments)
                    return call(slot,*actuals)
                return self.service_call(c.name,x.arguments,want_value)
            return direct_object_lowering.member_call(self, x, c, want_value)
        raise PythonDirectUnsupported(f'clean emitter: {type(x).__name__}')


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
                if self.implicit_self(key):
                    return [self.write_self(key,value)]
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
                elif self.implicit_self(key):
                    prefix.append(self.write_self(key,first))
                    counter=call('_SelfRead',name('_C'),name('_S'),literal(key))
                    advance=self.write_self(key,p.BinOp(left=counter,op=p.Add(),right=literal(1)))
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
                external=self.external(key)
                if external or self.implicit_self(key):
                    item=self.temp()
                    target=name(item,True)
                    write=self.write_external if external else self.write_self
                    body.insert(0,write(key,name(item)))
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
        compiler.plain_calls=not fragment and not vm.allow_extensions and vm.database_context is None
        if compiler.host_extensions:
            compiler.named_services=frozenset(vm.functions) | frozenset(getattr(vm,'_direct_routine_modules',()))
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
        compiler.persistent_services=frozenset(getattr(vm,'_direct_routine_modules',()))
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
    compiler.procedures=frozenset(node.name.casefold() for node in routines if not node.is_function)
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
    if compiler.call_slots:
        slots=p.Tuple(elts=[name(slot,True) for slot in compiler.call_slots.values()],ctx=p.Store())
        body.insert(0,p.Assign(targets=[slots],value=call(
            attr(name('_C'),'plain_callables'),literal(tuple(compiler.call_slots)))))
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
