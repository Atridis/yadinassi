"""Optional experiment-only source mapping; no checks on the success hot path."""
import ast
from contextlib import contextmanager
from decimal import DivisionByZero
from types import CodeType
from .errors import BSLError, BSLRuntimeError
from .syntax import ast as bsl_ast


def source_mapping_supported():
    return hasattr(CodeType, "co_lines")


def _normalized(text):
    text=text.strip()
    try:return ast.parse(text,mode='eval').body
    except SyntaxError:return text


class _StructureIndex:
    """Compile-local exact structural identities, excluding source attributes.

    Child identities keep parent keys small: no repeated serialization of full
    subtrees. Node objects are retained as keys only for this compilation, avoiding
    id reuse while normalized expression trees are collected.
    """
    def __init__(self):
        self.nodes={};self.structures={}
    def key(self,value):
        if isinstance(value,ast.AST):
            if value in self.nodes:return self.nodes[value]
            structure=(type(value).__name__,tuple((name,self.key(child)) for name,child in ast.iter_fields(value)))
            result=self.structures.setdefault(structure,len(self.structures))
            self.nodes[value]=result
            return result
        if isinstance(value,list):return ('list',tuple(self.key(child) for child in value))
        # ast.dump uses repr for scalar fields; preserve its distinctions (bool
        # vs int, bytes vs str, signed zero), not Python numeric equality.
        return ('scalar',repr(value))


class SourceMap:
    _use_markers=False
    _allow_markers=True
    def __init__(self):
        self.current=None;self.expressions=[];self.rows={};self.stack=[]
        self.markers=self._use_markers;self.locations=[];self.expression_sources=[]
    def enter(self,node):
        self.stack.append((self.current,self.expressions));self.current=node;self.expressions=[]
    def leave(self):self.current,self.expressions=self.stack.pop()
    def expression(self,text,node,*,parenthesized=False):
        # Binding failures belong to the invoked name, not its opening paren.
        # Child expressions retain their own entries and override this location.
        location=node
        if type(node) is bsl_ast.Call:
            location=node.callee
            while type(location) in (bsl_ast.Attribute,bsl_ast.Group,bsl_ast.Call):
                location=location.object if type(location) is bsl_ast.Attribute else location.expression if type(location) is bsl_ast.Group else location.callee
        token=location.token
        if type(node) is bsl_ast.Call and type(node.callee) is bsl_ast.Attribute and node.callee.name.casefold() in ("property","свойство"):
            token=node.token
        if self.markers:
            # The emitter certifies a single enclosing pair; replace it rather
            # than increasing nesting depth for every source expression.
            if parenthesized and text.startswith('(') and text.endswith(')'):text=text[1:-1]
            index=len(self.locations);self.locations.append(token);self.expression_sources.append(text)
            self.expressions.append((index,token))
            return '_source_location_marker('+str(index)+', '+text+')'
        self.expressions.append((text,token));return text
    def line(self,number):
        if self.current is not None:self.rows[number]=(self.current.token,tuple(self.expressions))
    def compile(self,generated,filename,body_offset):
        tree=ast.parse(generated,filename=filename);by_line={};normalized={};index=_StructureIndex()
        marked={}
        def strip(node):
            if (type(node) is ast.Call and type(node.func) is ast.Name
                    and node.func.id=='_source_location_marker'):
                if (len(node.args)!=2 or node.keywords or type(node.args[0]) is not ast.Constant
                        or type(node.args[0].value) is not int
                        or not 0<=node.args[0].value<len(self.locations)):
                    raise ValueError('invalid compiler source-location marker')
                result=strip(node.args[1]);marked.setdefault(node.args[0].value,result)
                return result
            for field,value in ast.iter_fields(node):
                if isinstance(value,ast.AST):setattr(node,field,strip(value))
                elif isinstance(value,list):
                    for i,child in enumerate(value):
                        if isinstance(child,ast.AST):value[i]=strip(child)
            return node
        try:
            if self.locations:tree=strip(tree)
            # Marker ids reuse the already parsed expression subtree. Structural
            # matching and occurrence order remain exactly the old source-map rule.
            for line,(token,expressions) in self.rows.items():
                groups={};root_types=set()
                for text,where in expressions:
                    if text not in normalized:
                        if type(text) is int:
                            expression=marked.get(text)
                            if expression is None:
                                expression=_normalized(self.expression_sources[text])
                                if isinstance(expression,ast.AST):expression=strip(expression)
                            normalized[text]=expression
                        else:normalized[text]=_normalized(text)
                    expression=normalized[text]
                    if not isinstance(expression,ast.AST):continue
                    groups.setdefault(index.key(expression),[]).append(where)
                    root_types.add(type(expression).__name__)
                by_line[line+body_offset]=(token,groups,root_types)
        finally:del strip
        consumed={}
        def visit(node,inherited=None,parent_line=None):
            original=getattr(node,'lineno',None)
            token=inherited if original==parent_line else None
            row=by_line.get(original)
            if row:
                token=token or row[0]
                if isinstance(node,ast.expr) and type(node).__name__ in row[2]:
                    key=index.key(node);matches=row[1].get(key)
                    if matches:
                        used=consumed.get((original,key),0)
                        token=matches[min(used,len(matches)-1)]
                        consumed[(original,key)]=used+1
            for child in ast.iter_child_nodes(node):visit(child,token,original)
            if token is not None and original is not None:
                node.lineno=token.line;node.end_lineno=token.line
                node.col_offset=max(0,token.column-1);node.end_col_offset=node.col_offset+1
        try:visit(tree)
        finally:del visit
        return compile(tree,filename,'exec')

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


def convert_error(error,filename,source,*,_context=None):
    """Convert only recoverable runtime errors, preserving nonrecoverable boundaries."""
    if isinstance(error,BSLError) or not isinstance(error,(ArithmeticError,ValueError,TypeError,IndexError,RecursionError)):
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
    line,column=chosen.tb_lineno,0
    # SourceMap already rewrites AST line numbers to BSL lines on Python 3.10.
    # PEP 657 adds expression columns on 3.11+; their absence is diagnostic only.
    if hasattr(chosen.tb_frame.f_code, 'co_positions'):
        code=chosen.tb_frame.f_code
        positions=tuple(code.co_positions()) if locations is None else locations.for_code(code)
        index=chosen.tb_lasti//2
        if index<len(positions):line,_,column,_=positions[index]
    line=line or chosen.tb_lineno;column=(column or 0)+1
    message=str(error) or type(error).__name__
    if isinstance(error,(ZeroDivisionError,DivisionByZero)):message='Деление на ноль'
    lines=source.splitlines() if locations is None else locations.for_source(source)
    source_line=lines[line-1] if 0<line<=len(lines) else ''
    return BSLRuntimeError(message,filename,line,column,source_line=source_line)


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
    from .values import _DIRECT_COLLECTION_CLASS_ABI
    HostFunction=_DIRECT_COLLECTION_CLASS_ABI[3][0]
    from .runtime import _DIRECT_ERROR_DESCRIPTION_ABI, _DIRECT_ERROR_INFO_ABI
    method=function.function
    if (type(method) is not MethodType
            or (method.__func__ is not _DIRECT_ERROR_DESCRIPTION_ABI
                and method.__func__ is not _DIRECT_ERROR_INFO_ABI)
            or method.__self__ is not getattr(context,'vm',None)):
        return function
    if method.__func__ is _DIRECT_ERROR_INFO_ABI:
        from .python_direct_error_info import BSLErrorInfo, snapshot
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
