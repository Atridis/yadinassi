"""Direct statement fragments over live addresses and private temporary names."""
from yadinassi.types.values import Reference
from yadinassi.execution.codegen.experimental_naked_collections import _Cell, _UNSET_REF
from yadinassi.execution.codegen.experimental_naked_live_state import _SlotReference, _ForwardReference, missing


def local_exists(value):
    return type(value) is not _Cell or value._value is not _UNSET_REF


def local_binding(getter,setter,exists,storage=None):
    if not exists():return None
    ref=Reference(getter,setter)
    ref._direct_name_sink=(storage is None or type(storage) in (_Cell,_SlotReference)
        or (type(storage) is _ForwardReference and type(storage.reference) is Reference
            and getattr(storage.reference,'_direct_name_sink',False) is True))
    return ref


class FragmentScope:
    def __init__(self,parent,bindings,visible,context):
        self.parent=parent;self.context=context;self.active=True
        self.names=frozenset(parent) if visible is None else frozenset(visible).intersection(parent)
        self.bindings={name:ref for name,ref in bindings.items() if ref is not None}
        self.names=self.names-self.bindings.keys()
        self.private={}
    def _check(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        if not self.active:raise BoundaryViolation('direct Execute scope has ended')
        if getattr(self.context,'_verify_dynamic_context',self.context._verify_context):self.context._check()
    def _get(self,ref):
        self._check()
        try:return ref.get()
        finally:self._check()
    def _set(self,ref,value):
        self._check()
        try:ref.set(value)
        finally:self._check()
    def __iter__(self):return iter(self.names|self.bindings.keys()|self.private.keys())
    def __contains__(self,name):return name in self.bindings or name in self.names or name in self.private
    def __getitem__(self,name):
        if name in self.bindings:return self._get(self.bindings[name])
        if name in self.names:
            value=self.parent[name]
            return self._get(value) if type(value) is Reference else value
        return self.private[name]
    def __setitem__(self,name,value):
        if name in self.bindings:self._set(self.bindings[name],value)
        elif name in self.names:
            current=self.parent[name]
            if type(current) is Reference:self._set(current,value)
            else:self.parent[name]=value
        else:self.private[name]=value
    def get(self,name,default=None):
        return self[name] if name in self else default
    def reference(self,name):
        self._check()
        ref=self._reference(name)
        result=Reference(lambda:self._get(ref),lambda value:self._set(ref,value))
        result._direct_name_sink=getattr(ref,'_direct_name_sink',False) is True
        return result
    def _reference(self,name):
        if name in self.bindings:return self.bindings[name]
        if name in self.names:
            if type(self.parent) is FragmentScope:return self.parent.reference(name)
            from yadinassi.execution.codegen.experimental_naked_live_state import host_reference
            return host_reference(self.parent,name)
        if name not in self.private:missing(name)
        ref=_SlotReference(self.private,name)
        result=Reference(ref.get,ref.set);result._direct_name_sink=True
        return result


def execute_fragment(text,context,parent,bindings,visible):
    if getattr(context,'app',None) is None and getattr(getattr(context,'vm',None),'application',None) is None:
        return _execute_fragment(text,context,parent,bindings,visible,None)
    from .source.python_direct_source_fragments import execution
    with execution(context,'execute',parent,bindings,visible) as profile:
        return _execute_fragment(text,context,parent,bindings,visible,profile)


def _execute_fragment(text,context,parent,bindings,visible,profile):
    if getattr(context,'_verify_dynamic_context',context._verify_context):context._check()
    from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
    vm=getattr(context,'vm',None)
    if vm is None:raise BoundaryViolation('direct Execute requires an interpreter-owned boundary')
    from yadinassi.runtime import EXECUTE_MAX_SOURCE, EXECUTE_MAX_DEPTH
    if text is None:text=''
    if type(text) is not str:raise TypeError('Выполнить: ожидается строка или Неопределено')
    if len(text)>EXECUTE_MAX_SOURCE:raise ValueError('Выполнить: превышен предел текста Yadinassi (65536 символов)')
    depth=getattr(context,'_execute_depth',None)
    if depth is None:depth=context._execute_depth=[0]
    if depth[0]>=EXECUTE_MAX_DEPTH:raise ValueError('Выполнить: превышен предел вложенности Yadinassi (16)')
    level=depth[0]
    depth[0]+=1
    scope=None
    try:
        from yadinassi.syntax.parser import parse_fragment
        from yadinassi.types.errors import BSLError, BSLRuntimeError
        from .python_direct import _source_facts,_admit_bindings,_contract,REPAIRS
        from yadinassi.execution.codegen.experimental_direct_ast import compile_module, compile_owned
        from .python_direct_services import CONSTRUCTORS
        from .python_direct_names import NAMES
        from .python_direct_database import NAMES as DB_NAMES
        constructor_names=('uuid','уникальныйидентификатор',*CONSTRUCTORS)+(('query','запрос') if vm.database_context is not None else ())
        external_names=tuple(NAMES)+(DB_NAMES if vm.database_context is not None else ())
        if profile is not None:constructor_names,external_names=profile
        else:
            from .python_direct_value_tree import CONSTRUCTOR_NAMES
            constructor_names+=CONSTRUCTOR_NAMES
        source_repairs=REPAIRS+('authority_checkpoints',) if profile is not None else REPAIRS
        key=(text,_contract(vm),source_repairs,constructor_names,external_names,profile is not None,EXECUTE_MAX_SOURCE,EXECUTE_MAX_DEPTH)
        if profile is not None:
            from .source.python_direct_source_fragments import prepared_cache
            cache=prepared_cache(context,'execute')
        else:
            cache=getattr(context,'_execute_units',None)
            if cache is None:cache=context._execute_units={}
        unit=cache.get(key)
        if unit is None:
            try:program=parse_fragment(text)
            except BSLError as error:
                raise BSLRuntimeError(error.message,error.source,error.line,error.column) from None
            _,routines,constructors,calls=_source_facts(program)
            _admit_bindings(vm,routines,constructors,calls)
            from .python_direct import _nodes
            # Preparation failure is not a BSL runtime error: an enclosing
            # Try must not turn an unsupported fragment into successful execution.
            from .python_direct import PythonDirectUnsupported
            from yadinassi.execution.codegen.experimental_naked_collections import UnsupportedNakedSyntax
            try:
                if profile is not None:
                    plan=compile_owned(program,retain_generated=False,source_text=text,source_name='<Выполнить>',
                        external_names=external_names,constructors=constructor_names,
                        source_scopes=True,authority_checks=True,require_last_expression=False)
                else:
                    from .python_direct import _extension_source_audit
                    plan=compile_module(vm,program,tuple(_nodes(program)),text,'<Выполнить>', _whole_source=_extension_source_audit(vm), _retain_generated=False)
            except PythonDirectUnsupported as error:
                raise UnsupportedNakedSyntax(str(error)) from None
            # No AST, mutable Program, caller scope, references or authorization is retained.
            unit=(routines,constructors,calls,plan.function,plan.constants,plan.source_name,plan.source_text)
            if len(text)<=EXECUTE_MAX_SOURCE:
                while cache and (len(cache)>=16 or sum(len(k[0]) for k in cache)+len(text)>EXECUTE_MAX_SOURCE):
                    del cache[next(iter(cache))]
                cache[key]=unit
        else:
            _admit_bindings(vm,*unit[:3])
        function,constants,source_name,source_text=unit[3:]
        scope=FragmentScope(parent,bindings,visible,context)
        try:function(scope,constants,[],context)
        except Exception as error:
            from yadinassi.execution.codegen.experimental_naked_errors import convert_error
            converted=convert_error(error,source_name,source_text)
            if converted is error:raise
            raise converted from None
    finally:
        if scope is not None:scope.active=False
        if profile is None:depth[0]-=1
        else:
            changed=(type(depth) is not list or len(depth)!=1 or type(depth[0]) is not int
                     or depth[0]!=level+1 or getattr(context,'_execute_depth',None) is not depth)
            if type(depth) is list:list.__setitem__(depth,slice(None),[level])
            if changed:raise BoundaryViolation('source fragment depth changed during execution')
        if getattr(context,'_verify_dynamic_context',context._verify_context):context._check()
