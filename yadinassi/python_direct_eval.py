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
    depth[0]+=1;scope=None
    try:
        from .syntax.parser import parse_expression
        from .syntax.ast import ExpressionStatement
        from .python_direct import _source_facts,_admit_bindings,REPAIRS
        from .experimental_naked_collections import prepare
        from .python_direct_services import CONSTRUCTORS
        from .python_direct_names import NAMES
        from .python_direct_database import NAMES as DB_NAMES
        from .python_direct_execute import FragmentScope
        try:expression=parse_expression(text)
        except BSLError as error:
            raise BSLRuntimeError(error.message,error.source,error.line,error.column) from None
        program=[ExpressionStatement(expression.token,expression)]
        _,routines,constructors,calls=_source_facts(program)
        _admit_bindings(vm,routines,constructors,calls)
        plan=prepare(text,source_name='<Вычислить>',parsed_ast=program,repairs=REPAIRS,
            constructors=('uuid','уникальныйидентификатор',*CONSTRUCTORS)+
                (('query','запрос') if vm.database_context is not None else ()),
            external_names=tuple(NAMES)+(DB_NAMES if vm.database_context is not None else ()),
            _trusted_entry=True,_return_last_expression=True)
        scope=FragmentScope(parent,bindings,visible,context)
        try:return plan.function(scope,plan.constants,[],context)
        except Exception as error:
            from .experimental_naked_errors import convert_error
            converted=convert_error(error,plan.source_name,plan.source_text)
            if converted is error:raise
            raise converted from None
    finally:
        if scope is not None:scope.active=False
        depth[0]-=1
        context._check()
