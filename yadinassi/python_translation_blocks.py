"""Research full-block Python generation. Unsupported paths raise; no AST adapter.

Generated functions keep the scheduler's generator protocol for suspension, while
all statement/control dispatch is compiled ahead of execution. Runtime services
retain name/reference/call/context authority; this module grants none itself.
"""
from dataclasses import dataclass
from decimal import Decimal
from .syntax import ast
from .owned_syntax import syntax_kind
from .compiled_inline import _CODE_CACHE

class UnsupportedTranslation(Exception): pass

@dataclass(frozen=True)
class BlockUnit:
    blocks: dict
    expressions: object
    source_bytes: int

    def retained(self, owned_ids):
        """Retain code without pinning unrelated unit literals or compiling again."""
        from types import FunctionType
        from .owned_syntax import is_owned
        from .python_translation_expressions import ExpressionPlan
        namespaces={}
        def clone(function):
            original=function.__globals__
            if id(original) in namespaces:
                return FunctionType(function.__code__,namespaces[id(original)],function.__name__)
            namespace={k:v for k,v in original.items()
                       if k!='translated' and not k.startswith('_expression_')}
            namespace['_nodes']=tuple(node if id(node) in owned_ids or not is_owned(node) else None
                                      for node in original['_nodes'])
            namespaces[id(original)]=namespace
            return FunctionType(function.__code__,namespace,function.__name__)
        blocks={key:(block,clone(fn)) for key,(block,fn) in self.blocks.items() if id(block) in owned_ids}
        expressions=ExpressionPlan(
            {key:(node,clone(fn)) for key,(node,fn) in self.expressions.functions.items() if id(node) in owned_ids},
            tuple(node for node in self.expressions.nodes if id(node) in owned_ids),self.expressions.source)
        # Conservatively retain the full admitted source charge, not only keys.
        return BlockUnit(blocks,expressions,self.source_bytes)

    def bind(self, engine):
        return Execution(self,engine)

class Execution:
    def __init__(self,unit,engine):
        from . import translated_access
        self.unit,self.engine,self.vm=unit,engine,engine.vm
        self.access=translated_access
        self.outer_node=None
        self.expressions=unit.expressions.bind(self.vm,guard=self.guard,access=translated_access,resolve=engine._python_expression_execution)
    def guard(self,node):
        self.engine._verify_active_plans();self.engine.verify_node(node)
        kinds=self.engine.stats.setdefault('python_translated_node_kinds',{})
        kind=syntax_kind(node).__name__;kinds[kind]=kinds.get(kind,0)+1
    def block(self,key):
        block,function=self.unit.blocks[key]
        self.engine._verify_owned_identity(block)
        self.engine.stats['python_translated_blocks']=self.engine.stats.get('python_translated_blocks',0)+1
        return (yield from function(self))
    def unsupported(self,node):
        from .compiled_backend import CompiledUnsupported
        kind=syntax_kind(node).__name__
        gaps=self.engine.stats.setdefault('force_translation_gaps',{})
        gaps[kind]=gaps.get(kind,0)+1
        raise CompiledUnsupported(node,'force Python translation unsupported '+kind)

def prepare_blocks(blocks,expression_roots,*,max_source_bytes,max_function_bytes):
    from .python_translation_expressions import prepare_expressions
    from . import runtime as R
    # Every expression and block is generated before the admitted program runs.
    expressions=prepare_expressions(expression_roots,max_source_bytes=max_source_bytes,max_function_bytes=max_function_bytes)
    used=len(expressions.source.encode());namespace={'R':R,'Decimal':Decimal}
    originals={};sources=[];nodes=[]
    def bind(node):
        nodes.append(node);return f'_nodes[{len(nodes)-1}]'
    def ev(node):return f'(yield from _s.expressions.evaluate({bind(node)}))'
    def body(value):return f'(yield from _s.block({tuple(id(n) for n in value)!r}))'
    for block in blocks:
        key=tuple(id(node) for node in block)
        if key in originals:continue
        originals[key]=block
        lines=['def translated(_s):','    if False: yield None','    vm = _s.vm','    result = None','    pc = 0','    while True:',f'        if pc >= {len(block)}: break','        try:']
        def emit(d,s):lines.append('    '*d+s)
        if not block:emit(3,'pass')
        for i,node in enumerate(block):
            n=bind(node);kind=syntax_kind(node)
            emit(3,f'{"if" if i==0 else "elif"} pc == {i}:')
            emit(4,f'if _s.outer_node is not {n}: vm.compiled_before({n})');emit(4,'try:');emit(5,f'_s.guard({n})');emit(5,'result = None')
            d=5
            if kind is ast.ExpressionStatement:
                expression=node.expression
                while syntax_kind(expression) is ast.Group:expression=expression.expression
                if syntax_kind(expression) is ast.Call:emit(d,f'result = yield from _s.expressions.call({bind(expression)}, require_value=False)')
                else:emit(d,f'result = {ev(node.expression)}')
            elif kind is ast.Assign:
                target=syntax_kind(node.target)
                if target is ast.Name:emit(d,f'vm.set_variable({node.target.name!r}, {ev(node.value)})')
                elif target is ast.Attribute:
                    emit(d,f'receiver = yield from _s.expressions.receiver({bind(node.target.object)})')
                    emit(d,f'writer = _s.access.prepare_attribute_write(vm, receiver, {node.target.name!r})')
                    emit(d,f'writer({ev(node.value)})')
                elif target is ast.Index:
                    emit(d,f'receiver = yield from _s.expressions.receiver({bind(node.target.object)})')
                    emit(d,'binder = _s.access.prepare_index_write(vm, receiver)')
                    emit(d,f'writer = binder({ev(node.target.index)})');emit(d,f'writer({ev(node.value)})')
                else:emit(d,f'_s.unsupported({n})')
            elif kind is ast.Var:
                names=tuple(node.names)
                emit(d,f'if vm.locals is None and any(name.casefold() in vm.imports for name in {names!r}):')
                emit(d+1,'raise ValueError("Имя импорта конфликтует с объявлением")')
                emit(d,f'for name in {names!r}:');emit(d+1,'(vm.variables if vm.locals is None else vm.locals).setdefault(name.casefold(), None)')
            elif kind in (ast.Routine,ast.Label):emit(d,'pass')
            elif kind is ast.If:
                for j,(condition,child) in enumerate(node.branches):
                    emit(d,f'{"if" if j==0 else "elif"} R.boolean({ev(condition)}):');emit(d+1,body(child))
                emit(d,'else:');emit(d+1,body(node.otherwise))
            elif kind in (ast.For,ast.While,ast.ForEach):
                if kind is ast.For:
                    emit(d,f'first = R.require_number({ev(node.start)})');emit(d,f'last = R.require_number({ev(node.end)})')
                    emit(d,f'vm.set_variable({node.name!r},first)')
                    counter=ast.Name(node.token,node.name.casefold());counter_name=bind(counter)
                    emit(d,f'while R.require_number(vm.semantic_name({counter_name})) <= last:')
                elif kind is ast.While:emit(d,f'while R.boolean({ev(node.condition)}):')
                else:
                    emit(d,f'collection = {ev(node.collection)}');emit(d,'for item in vm.compiled_iterable(collection):')
                    emit(d+1,f'vm.set_variable({node.name!r},item)')
                emit(d+1,'try:');emit(d+2,body(node.body))
                emit(d+1,'except R._Continue:');emit(d+2,'pass')
                emit(d+1,'except R._Break:');emit(d+2,'break')
                if kind is ast.For:emit(d+1,f'vm.set_variable({node.name!r}, R.require_number(vm.semantic_name({counter_name})) + Decimal(1))')
            elif kind is ast.Try:
                emit(d,'try:');emit(d+1,body(node.body))
                emit(d,'except R.BSLRuntimeError as handled_error:')
                emit(d+1,'for handled_index in range(len(vm._handled_errors)):');emit(d+2,'vm._handled_errors[handled_index] = None')
                emit(d+1,'vm._handled_errors.append(handled_error)');emit(d+1,'try:');emit(d+2,body(node.handler))
                emit(d+1,'finally:');emit(d+2,'vm._handled_errors.pop()')
            elif kind is ast.Return:emit(d,f'raise R._Return({ev(node.value) if node.value is not None else "None"})')
            elif kind is ast.Import:emit(d,f'vm.semantic_import({n})')
            elif kind is ast.Execute:emit(d,f'yield from vm.semantic_execute({n}, _evaluation=_s.expressions)')
            elif kind is ast.Raise:emit(d,f'yield from vm.semantic_raise({n}, _evaluation=_s.expressions)')
            elif kind is ast.Goto:emit(d,f'raise R._Goto({n})')
            elif kind is ast.Break:emit(d,'raise R._Break')
            elif kind is ast.Continue:emit(d,'raise R._Continue')
            else:emit(d,f'_s.unsupported({n})')
            emit(4,'except BaseException as error:');emit(5,f'if _s.outer_node is {n}: raise');emit(5,f'converted = vm.compiled_exception({n},error)')
            emit(5,'if converted is error: raise');emit(5,'raise converted from None')
            emit(4,f'if _s.outer_node is not {n}: result = vm.compiled_after({n}, result)')
        labels={node.name.casefold():i for i,node in enumerate(block) if syntax_kind(node) is ast.Label}
        emit(2,'except R._Goto as jump:');emit(3,f'labels = {labels!r}')
        emit(3,'if jump.name not in labels: raise');emit(3,'pc = labels[jump.name]')
        emit(2,'else:');emit(3,'pc += 1');emit(1,'return result')
        source='\n'.join(lines)+'\n'
        if len(source.encode())>max_function_bytes:raise UnsupportedTranslation('generated function source budget')
        used+=len(source.encode())
        if used>max_source_bytes:raise UnsupportedTranslation('generated unit source budget')
        sources.append((key,source))
    namespace['_nodes']=tuple(nodes);functions={}
    for key,source in sources:
        exec(_CODE_CACHE.get(source),namespace)
        functions[key]=(originals[key],namespace['translated'])
    return BlockUnit(functions,expressions,used)
