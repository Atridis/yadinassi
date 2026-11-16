"""Optional experiment-only source mapping; no checks on the success hot path."""
import ast
from decimal import DivisionByZero
from types import CodeType
from .errors import BSLError, BSLRuntimeError
from .syntax import ast as bsl_ast


def source_mapping_supported():
    return hasattr(CodeType, "co_positions")


def _normalized(text):
    text=text.strip()
    while text.startswith('(') and text.endswith(')'):
        balance=0;whole=True
        # Generated text is Python; AST normalization handles literals/quotes.
        try:
            tree=ast.parse(text,mode='eval')
            return ast.dump(tree.body,include_attributes=False)
        except SyntaxError:return text
    try:return ast.dump(ast.parse(text,mode='eval').body,include_attributes=False)
    except SyntaxError:return text


class SourceMap:
    def __init__(self):
        self.current=None;self.expressions=[];self.rows={};self.stack=[]
    def enter(self,node):
        self.stack.append((self.current,self.expressions));self.current=node;self.expressions=[]
    def leave(self):self.current,self.expressions=self.stack.pop()
    def expression(self,text,node):
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
        self.expressions.append((text,token));return text
    def line(self,number):
        if self.current is not None:self.rows[number]=(self.current.token,tuple(self.expressions))
    def compile(self,generated,filename,body_offset):
        tree=ast.parse(generated,filename=filename);by_line={};normalized={}
        # Repeated generated text needs normalization only once in this compile.
        # Nothing is retained between programs or added to the execution path.
        for line,(token,expressions) in self.rows.items():
            groups={}
            for text,where in expressions:
                if text not in normalized:normalized[text]=_normalized(text)
                groups.setdefault(normalized[text],[]).append(where)
            # An AST dump starts with its node class. Impossible root classes
            # cannot match; avoid recursively dumping their entire subtrees.
            by_line[line+body_offset]=(token,groups,{key.partition('(')[0] for key in groups})
        consumed={}
        def visit(node,inherited=None,parent_line=None):
            original=getattr(node,'lineno',None)
            token=inherited if original==parent_line else None
            row=by_line.get(original)
            if row:
                token=token or row[0]
                if isinstance(node,ast.expr) and type(node).__name__ in row[2]:
                    key=ast.dump(node,include_attributes=False)
                    # Attribute/source location fields do not enter the key.
                    matches=row[1].get(key)
                    if matches:
                        used=consumed.get((original,key),0)
                        token=matches[min(used,len(matches)-1)]
                        consumed[(original,key)]=used+1
            for child in ast.iter_child_nodes(node):visit(child,token,original)
            if token is not None and original is not None:
                node.lineno=token.line;node.end_lineno=token.line
                node.col_offset=max(0,token.column-1);node.end_col_offset=node.col_offset+1
        visit(tree)
        return compile(tree,filename,'exec')


def convert_error(error,filename,source):
    """Convert only recoverable runtime errors, preserving nonrecoverable boundaries."""
    if isinstance(error,BSLError) or not isinstance(error,(ArithmeticError,ValueError,TypeError,IndexError,RecursionError)):
        return error
    chosen=None;tb=error.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename==filename:chosen=tb
        tb=tb.tb_next
    if chosen is None:return error
    positions=list(chosen.tb_frame.f_code.co_positions())
    index=chosen.tb_lasti//2
    line,_,column,_=positions[index] if index<len(positions) else (chosen.tb_lineno,None,0,None)
    line=line or chosen.tb_lineno;column=(column or 0)+1
    message=str(error) or type(error).__name__
    if isinstance(error,(ZeroDivisionError,DivisionByZero)):message='Деление на ноль'
    lines=source.splitlines();source_line=lines[line-1] if 0<line<=len(lines) else ''
    return BSLRuntimeError(message,filename,line,column,source_line=source_line)
