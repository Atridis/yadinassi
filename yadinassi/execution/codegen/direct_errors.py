"""Runtime diagnostics for generated Python code."""
from contextlib import contextmanager
from decimal import Decimal, DivisionByZero, InvalidOperation
from yadinassi.types.errors import BSLError, BSLRuntimeError


class _ErrorLocations:
    """One code table and one source, owned by the current boundary activation."""
    __slots__=('code','positions','source','lines')
    def __init__(self):
        self.code=None;self.positions=();self.source=None;self.lines=()
    def for_code(self,code):
        if self.code is not code:
            self.code=code;self.positions=tuple(code.co_positions())
        return self.positions
    def for_source(self,source):
        if self.source is not source:
            self.source=source;self.lines=source.splitlines()
        return self.lines


def _remainder_site(trace,source_line,column):
    if column is not None and source_line:
        return source_line[column:column+1]=='%'
    # Python 3.10 (or disabled debug ranges) has no expression column.
    # Inspect only the failed instruction, never re-evaluate either operand.
    from dis import get_instructions
    instruction=next((step for step in get_instructions(trace.tb_frame.f_code)
                      if step.offset==trace.tb_lasti),None)
    return instruction is not None and (instruction.opname=='BINARY_MODULO'
        or instruction.opname=='BINARY_OP' and instruction.argrepr=='%')


def _decimal_remainder_message(trace,source_line,column):
    invalid='Не удалось вычислить остаток: недопустимая десятичная операция'
    inner=trace.tb_next
    if inner is None:
        return invalid if _remainder_site(trace,source_line,column) else None
    from yadinassi.execution.direct.python_direct_numbers import remainder
    if inner.tb_next is not None or inner.tb_frame.f_code is not remainder.__code__:
        return None
    # The existing integer-lane helper still has the converted operands in
    # its fault frame, so this case can name the actual zero divisor.
    operands=inner.tb_frame.f_locals
    left,right=operands.get('left'),operands.get('right')
    if type(left) is Decimal and type(right) is Decimal and left.is_finite() and right.is_zero():
        return 'Деление на ноль'
    return invalid


def _missing_message(context, key, source_line, column):
    # Python symbols are casefolded; retain the source spelling only on error.
    from re import finditer
    names = [match for match in finditer(r"[^\W\d]\w*", source_line)
             if match[0].casefold() == key]
    at_column = next((match[0] for match in names if match.start() == column), None)
    spelling = at_column if at_column is not None else (names[-1][0] if names else key)
    if context is not None:
        try:
            context.missing_value(spelling)
        except (TypeError, ValueError) as diagnostic:
            return str(diagnostic)
    return 'Переменная или функция не определена: '+spelling


def convert_error(error,filename,source,*,_context=None):
    """Convert only recoverable runtime errors, preserving nonrecoverable boundaries."""
    if (getattr(_context,'_async_scheduler',None) is not None
            and _context._async_scheduler.active_context.host_failure is error):
        return error
    if isinstance(error,BSLError) or not isinstance(error,(ArithmeticError,ValueError,TypeError,IndexError,NameError,RecursionError)):
        return error
    chosen=None;tb=error.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename==filename:chosen=tb
        tb=tb.tb_next
    if chosen is None:return error
    locations=None
    if _context is not None:
        locations=getattr(_context,'_error_locations',None)
        if locations is None:
            locations=_ErrorLocations();_context._error_locations=locations
    line,column=chosen.tb_lineno,None
    # The generated AST carries BSL line numbers, also on Python 3.10.
    # PEP 657 adds expression columns on 3.11+; their absence is diagnostic only.
    if hasattr(chosen.tb_frame.f_code, 'co_positions'):
        code=chosen.tb_frame.f_code
        positions=tuple(code.co_positions()) if locations is None else locations.for_code(code)
        index=chosen.tb_lasti//2
        if index<len(positions):line,_,column,_=positions[index]
    line=line or chosen.tb_lineno
    lines=source.splitlines() if locations is None else locations.for_source(source)
    source_line=lines[line-1] if 0<line<=len(lines) else ''
    message=str(error) or type(error).__name__
    if isinstance(error,(ZeroDivisionError,DivisionByZero)):message='Деление на ноль'
    elif type(error) is NameError and chosen.tb_next is None and type(error.name) is str:
        message=_missing_message(_context,error.name,source_line,column)
    elif type(error) is InvalidOperation:
        message=_decimal_remainder_message(chosen,source_line,column) or message
    return BSLRuntimeError(message,filename,line,(column or 0)+1,source_line=source_line)


class _HandledError:
    __slots__=('error','filename','source','resolved')
    def __init__(self,error,filename,source):
        self.error=error;self.filename=filename;self.source=source;self.resolved=False
    def resolve(self,context):
        if not self.resolved:
            self.error=convert_error(self.error,self.filename,self.source,_context=context)
            self.resolved=True
        return self.error


@contextmanager
def handled_error(context,error,filename,source):
    """Activation-local diagnostics; nested handlers discard stale outer details."""
    scheduler=getattr(context,'_async_scheduler',None)
    if scheduler is not None and scheduler.active_context.host_failure is error:raise error
    errors=context._handled_errors
    for index in range(len(errors)):errors[index]=None
    errors.append(_HandledError(error,filename,source))
    try:yield
    finally:errors.pop()


def reraise_handled(context):
    errors=context._handled_errors
    if not errors:raise ValueError('Нет активного исключения для повторного вызова')
    if errors[-1] is None:
        raise ValueError('Повторный вызов исключения после вложенного обработчика пока не поддерживается; используйте явное сообщение')
    raise errors[-1].resolve(context)


def description_service(context,function):
    """Replace only the current owner's canonical diagnostic builtin."""
    from types import MethodType
    from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI
    HostFunction=_DIRECT_COLLECTION_CLASS_ABI[3][0]
    from yadinassi.runtime import _DIRECT_ERROR_DESCRIPTION_ABI, _DIRECT_ERROR_INFO_ABI
    method=function.function
    if (type(method) is not MethodType
            or (method.__func__ is not _DIRECT_ERROR_DESCRIPTION_ABI
                and method.__func__ is not _DIRECT_ERROR_INFO_ABI)
            or method.__self__ is not getattr(context,'vm',None)):
        return function
    if method.__func__ is _DIRECT_ERROR_INFO_ABI:
        from yadinassi.execution.direct.python_direct_error_info import BSLErrorInfo, snapshot
        def info():
            errors=context._handled_errors
            if (getattr(context,'_eval_depth',None) or [0])[0] or not errors or errors[-1] is None:
                return snapshot(empty=True)
            error=errors[-1].resolve(context)
            if type(error) is not BSLRuntimeError:
                raise ValueError('ИнформацияОбОшибке: тип исключения пока не поддерживается')
            if error.info is None:
                error.info=snapshot(error.message,module_name=error.source,
                    line_number=error.line,initial_string=error.source_line)
            if type(error.info) is not BSLErrorInfo:
                raise ValueError('ИнформацияОбОшибке: требуется штатный снимок ошибки')
            return error.info
        return HostFunction(function.name,info,reference_parameters=function.reference_parameters,returns_value=function.returns_value)
    def description():
        errors=context._handled_errors
        return str(errors[-1].resolve(context)) if errors and errors[-1] is not None else ''
    return HostFunction(function.name,description,reference_parameters=function.reference_parameters,returns_value=function.returns_value)
