"""Expression-only direct evaluation over live caller addresses."""
from decimal import Decimal


def bind_eval(bound,context,parent,bindings,visible):
    capability=getattr(bound,'bind_eval',None)
    return bound if capability is None else capability(context,parent,bindings,visible)


def eval_capability(context,function,key):
    from .runtime import _eval_marker
    from .experimental_naked_boundaries import BoundaryViolation
    def bind(context,parent,bindings,visible):
        def invoke(value):
            context._before('call',key)
            try:
                if function.function is not _eval_marker or function.reference_parameters:
                    raise BoundaryViolation('Eval implementation changed during argument evaluation')
                return evaluate(value,context,parent,bindings,visible)
            except PermissionError as error:raise BoundaryViolation(str(error)) from error
            finally:context._check()
        invoke.requires_reference=lambda index:False
        return invoke
    return bind


def evaluate(value,context,parent,bindings,visible):
    if getattr(context,'app',None) is None and getattr(getattr(context,'vm',None),'application',None) is None:
        return _evaluate(value,context,parent,bindings,visible,None)
    from .python_direct_source_fragments import execution
    with execution(context,'eval',parent,bindings,visible) as profile:
        return _evaluate(value,context,parent,bindings,visible,profile)


def _evaluate(value,context,parent,bindings,visible,profile):
    context._check()
    from .runtime import EVAL_MAX_SOURCE,EVAL_MAX_DEPTH
    from .values import to_string
    from .errors import BSLError,BSLRuntimeError
    from .experimental_naked_boundaries import BoundaryViolation
    vm=getattr(context,'vm',None)
    if vm is None:raise BoundaryViolation('direct Eval requires an interpreter-owned boundary')
    if type(value) is str:text=value
    elif type(value) is Decimal and value.is_finite():text=to_string(value)
    else:raise TypeError('Вычислить: ожидается строка или конечное число')
    if len(text)>EVAL_MAX_SOURCE:raise ValueError('Вычислить: превышен предел текста Yadinassi (65536 символов)')
    depth=getattr(context,'_eval_depth',None)
    if depth is None:depth=context._eval_depth=[0]
    if depth[0]>=EVAL_MAX_DEPTH:raise ValueError('Вычислить: превышен предел вложенности Yadinassi (16)')
    level=depth[0]
    depth[0]+=1;scope=None
    try:
        from .syntax.parser import parse_expression
        from .syntax.ast import ExpressionStatement
        from .python_direct import _source_facts,_admit_bindings,_contract,REPAIRS
        from .experimental_naked_collections import prepare
        from .python_direct_services import CONSTRUCTORS
        from .python_direct_names import NAMES
        from .python_direct_database import NAMES as DB_NAMES
        from .python_direct_execute import FragmentScope
        constructor_names=('uuid','уникальныйидентификатор',*CONSTRUCTORS)+(('query','запрос') if vm.database_context is not None else ())
        external_names=tuple(NAMES)+(DB_NAMES if vm.database_context is not None else ())
        if profile is not None:constructor_names,external_names=profile
        else:
            from .python_direct_value_tree import CONSTRUCTOR_NAMES
            constructor_names+=CONSTRUCTOR_NAMES
        source_repairs=REPAIRS+('authority_checkpoints',) if profile is not None else REPAIRS
        key=(text,_contract(vm),source_repairs,constructor_names,external_names,profile is not None,EVAL_MAX_SOURCE,EVAL_MAX_DEPTH)
        if profile is not None:
            from .python_direct_source_fragments import prepared_cache
            cache=prepared_cache(context,'eval')
        else:
            cache=getattr(context,'_eval_units',None)
            if cache is None:cache=context._eval_units={}
        unit=cache.get(key)
        if unit is None:
            try:expression=parse_expression(text)
            except BSLError as error:
                raise BSLRuntimeError(error.message,error.source,error.line,error.column) from None
            program=[ExpressionStatement(expression.token,expression)]
            _,routines,constructors,calls=_source_facts(program)
            _admit_bindings(vm,routines,constructors,calls)
            plan=prepare(text,source_name='<Вычислить>',parsed_ast=program,repairs=source_repairs,
                constructors=constructor_names,external_names=external_names,
                _trusted_entry=True,_dynamic_new=profile is None,_return_last_expression=True,_source_routine_scopes=profile is not None,_require_last_expression=True)
            # Retain compilation only, never AST, mutable Program, bindings or authority.
            unit=(routines,constructors,calls,plan.function,plan.constants,plan.source_name,plan.source_text)
            while cache and (len(cache)>=16 or sum(len(k[0]) for k in cache)+len(text)>EVAL_MAX_SOURCE):
                del cache[next(iter(cache))]
            cache[key]=unit
        else:
            _admit_bindings(vm,*unit[:3])
        function,constants,source_name,source_text=unit[3:]
        scope=FragmentScope(parent,bindings,visible,context)
        try:return function(scope,constants,[],context)
        except Exception as error:
            from .experimental_naked_errors import convert_error
            converted=convert_error(error,source_name,source_text)
            if converted is error:raise
            raise converted from None
    finally:
        if scope is not None:scope.active=False
        if profile is None:depth[0]-=1
        else:
            changed=(type(depth) is not list or len(depth)!=1 or type(depth[0]) is not int
                     or depth[0]!=level+1 or getattr(context,'_eval_depth',None) is not depth)
            if type(depth) is list:list.__setitem__(depth,slice(None),[level])
            if changed:raise BoundaryViolation('source fragment depth changed during execution')
        context._check()
