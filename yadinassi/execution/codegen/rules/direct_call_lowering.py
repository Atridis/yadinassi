"""Call lowering: declarations, omissions, and explicit runtime boundaries."""
import ast as p
from yadinassi.execution.direct.python_direct_names import CHARS_ALIASES
from yadinassi.execution.direct.python_direct_json_handlers import JSON_CALLBACKS
from yadinassi.syntax import ast as b
from .direct_reference_lowering import SELF_NAMES, slot_actual
from ..direct_python_ast import _node, attr, call, literal, name

_CALLBACK_CONSTRUCTORS = ('new:callbackdescription','new:описаниеоповещения')


def ungroup(arg):
    while type(arg) is b.Group:
        arg = arg.expression
    return arg


def omissions(args):
    return tuple(i for i,arg in enumerate(args) if type(arg) is b.OmittedArgument)


def local_call(self,key,args,want_value,token):
    key_for_call=key
    bound=self.routines[key]
    params=self.parameters[key]
    minimum=max((i+1 for i,param in enumerate(params) if param.default is None),default=0)
    if not minimum<=len(args)<=len(params):
        return _node(call('_InvalidCallArity',literal(key),literal(len(params)),literal(len(args))),token)
    if want_value and key in self.procedures:
        return _node(call('_ProcedureValue',literal(key)),token)
    omitted=self.omissions(args)
    def actual(i):
        if params[i].by_value:
            return literal(None) if i in omitted else self.expr(args[i])
        if i in omitted:
            return p.List(elts=[literal(None)],ctx=p.Load()),literal(0)
        return slot_actual(self,args[i])

    defaults=tuple(i for i in omitted if params[i].default is not None)
    prefix=defaults[0] if defaults else len(args)
    lowered=call(bound)
    for i in range(prefix):
        argument=actual(i)
        if params[i].by_value:
            lowered.args.append(argument)
        elif type(argument) is tuple:
            lowered.args.extend(argument)
        else:
            lowered.args.append(p.Starred(value=argument,ctx=p.Load()))
    for i in range(prefix,len(args)):
        if i in defaults:
            continue
        formal=params[i].name.casefold()
        argument=actual(i)
        if params[i].by_value:
            lowered.keywords.append(p.keyword(arg=formal,value=argument))
        else:
            key=self.routine_slot_keys[key_for_call][formal]
            if type(argument) is tuple:
                lowered.keywords.extend(p.keyword(arg=n,value=v) for n,v in zip((formal,key),argument))
            else:
                lowered.keywords.append(p.keyword(arg=None,value=call(
                    '_KeywordPair',literal(formal),literal(key),argument)))
    return lowered


def service_call(self,key,args,want_value):
    omitted=self.omissions(args)
    resolver='resolve_optional_service' if omitted else 'resolve_service'
    folded=key.casefold()
    host_capture=self.host_extensions and not self.owned and not self.source_dispatch
    if host_capture and folded in self.locals:
        bound=call(attr(name('_C'),'resolve_extension_value'),self.var(folded),
                   require_value=literal(want_value),allow_references=literal(True))
        return self.bound_call(bound,args,omitted,references=True,captured_host=True)
    crossing=folded in self.server_services
    dynamic_host_call=(host_capture
                       and not folded.startswith('new:') and not self.external(folded)
                       and folded not in self.named_services and folded not in self.reference_services
                       and not crossing)
    references=(folded in self.reference_services or dynamic_host_call or
                self.source_dispatch and not folded.startswith('new:') and folded not in self.value_services)
    target=[literal(key)]
    if self.source_dispatch and not folded.startswith('new:') and not self.external(folded):
        if folded in self.locals:
            target.append(self.var(folded))
        elif folded not in self.value_services:
            target.append(call(attr(name('_S'),'get'),literal(folded),name('_ServiceMissing')))
    contract={'require_value':literal(want_value),'argument_count':literal(len(args))}
    if references:
        contract['allow_references']=literal(True)
    # Prepared calls bind the current routine, which may now cross from
    # client to server. Pass only static shape metadata; the resolver
    # rejects it at the actual crossing, before evaluating arguments.
    if (crossing and references) or folded in self.persistent_services:
        non_names=tuple(i for i,arg in enumerate(args)
                        if type(ungroup(arg)) not in (b.Name,b.OmittedArgument))
        if non_names:
            contract['_non_name_actuals']=literal(non_names)
    bound=call(attr(name('_C'),resolver),*target,**contract)
    if key.casefold() in ('eval','вычислить'):
        bound=call('_Eval',bound,*self.fragment_arguments())
    callback_slot=None
    if self.import_roots:
        entry=JSON_CALLBACKS.get(folded)
        if entry is not None:
            callback_slot=entry[1]
        elif folded in _CALLBACK_CONSTRUCTORS:
            callback_slot=1
    callback = self.import_path(args[callback_slot]) if (callback_slot is not None
                                                         and callback_slot < len(args)) else None
    return self.bound_call(bound,args,omitted,references=references,crossing=crossing,
                           callback=(callback_slot,callback) if callback is not None else None,
                           captured_host=dynamic_host_call)


def bound_call(self,bound,args,omitted,*,references=False,crossing=False,shapes=False,callback=None,captured_host=False):
    if shapes:
        named=tuple(type(ungroup(arg)) in (b.Name,b.OmittedArgument) for arg in args)
        bound=call('_SourceShapes',bound,literal(named))
    # The boundary still binds the target before any actual. A temporary is
    # only needed if an actual will consult the target (holes, ByRef,
    # an imported conversion hook, or a named client/server argument).
    consults_bound=(omitted or (references and args) or callback is not None
                    or (crossing and any(type(ungroup(arg)) is b.Name for arg in args)))
    if not consults_bound:
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
        plain=ungroup(arg)
        named=crossing and type(plain) is b.Name
        is_reference=call('_RequiresReference',function,literal(i))
        if not named:
            return self.actual_address(arg,is_reference,captured_host=captured_host) if references else self.expr(arg)
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


def actual_address(self,arg,test,*,captured_host=False):
    plain=ungroup(arg)
    if type(plain) is b.Name:
        key=plain.name.casefold()
        if (captured_host and not self.fragment and key not in self.locals and key not in self.references
                and not self.external(key) and self.import_path(plain) is None
                and not (self.current_module and key in SELF_NAMES)
                and not (key in CHARS_ALIASES and key not in self.module_declarations)):
            # A Python caller can supply an existing Reference in its module slot.
            address=call('_LiveHostRef',name('_S'),literal(key))
        else:
            address=call('_HostRef',self.reference(arg),name('_C'))
        return p.IfExp(test=test,body=address,orelse=self.expr(arg))
    if type(plain) is b.Index:
        owned=self.meter_loops or self.source_dispatch or self.configuration_dispatch
        bind=call('_IndexedActual',name('_C'),test,self.expr(plain.object),literal(owned))
        return call(bind,self.expr(plain.index))
    if type(plain) is b.Attribute:
        return call('_MemberActual',name('_C'),test,self.expr(plain.object),literal(plain.name))
    if captured_host:return self.expr(arg)
    convert=p.IfExp(test=test,body=name('_CellActual'),orelse=name('_Unchanged'))
    return call(convert,self.expr(arg))
