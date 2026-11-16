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
    statements: object = None
    binding_count: int = 0
    sync_routines: object = None
    sync_segments: object = None

    def retained(self, owned_ids):
        """Retain code without pinning unrelated unit literals or compiling again."""
        from types import FunctionType
        from .owned_syntax import is_owned
        from .python_translation_expressions import ExpressionPlan
        namespaces={}
        def clone(function):
            original=function.__globals__
            if id(original) in namespaces:
                return FunctionType(function.__code__,namespaces[id(original)],function.__name__,function.__defaults__)
            namespace={k:v for k,v in original.items()
                       if k!='translated' and not k.startswith(('_expression_', '_shared_', '_block_template_'))}
            namespace['_nodes']=tuple(node if id(node) in owned_ids or not is_owned(node) else None
                                      for node in original['_nodes'])
            namespaces[id(original)]=namespace
            return FunctionType(function.__code__,namespace,function.__name__,function.__defaults__)
        blocks={key:(block,clone(fn) if fn is not None else None) for key,(block,fn) in self.blocks.items() if id(block) in owned_ids}
        expressions=ExpressionPlan(
            {key:(node,clone(fn)) for key,(node,fn) in self.expressions.functions.items() if id(node) in owned_ids},
            tuple(node for node in self.expressions.nodes if id(node) in owned_ids),self.expressions.source,
            {key:(node,clone(fn)) for key,(node,fn) in (self.expressions.sync_functions or {}).items() if id(node) in owned_ids},self.expressions.binding_count,
            {key:site for key,site in (self.expressions.call_sites or {}).items() if id(site.node) in owned_ids})
        # Conservatively retain the full admitted source charge, not only keys.
        return BlockUnit(blocks,expressions,self.source_bytes,{key:(node,clone(fn)) for key,(node,fn) in (self.statements or {}).items() if id(node) in owned_ids},self.binding_count,
            {key:(routine,plan) for key,(routine,plan) in (self.sync_routines or {}).items()
             if id(routine) in owned_ids and all(id(node) in owned_ids for node in (*plan.nodes,*plan.containers))},
            {key:plan for key,plan in (self.sync_segments or {}).items()
             if all(id(node) in owned_ids for node in (*plan.nodes,*plan.containers))})

    def bind(self, engine):
        return Execution(self,engine)

class Execution:
    def __init__(self,unit,engine):
        from . import translated_access
        self.unit,self.engine,self.vm=unit,engine,engine.vm
        self.access=translated_access
        self.outer_node=None
        self.expressions=unit.expressions.bind(self.vm,guard=self.guard,access=translated_access,resolve=engine._python_expression_execution,leaf_resolve=engine._python_leaf_operation)
    def sync_segment(self,key,previous_result):
        if self.engine.DETAILED_INLINE_STATS:return None
        plan=(self.unit.sync_segments or {}).get(key)
        if plan is None:return None
        # Dropping a previous host result can itself call back through __del__.
        if not any(type(previous_result) is scalar for scalar in (Decimal,bool,str,type(None))):return None
        from .python_translation_scalar_regions import scope,closed_gc_lease,ClosedLease
        with closed_gc_lease():
            local=scope(self,plan.names,plan.names-set(plan.parameters),record=False,allow_module=True)
            if local is None:return None
            lease=ClosedLease(self,plan,local,allow_module=True);lease.check()
            self.engine.stats['python_sync_segment_calls']=self.engine.stats.get('python_sync_segment_calls',0)+1
            self.engine.stats['python_translated_blocks']=self.engine.stats.get('python_translated_blocks',0)+1
            return plan.function(self.vm,local,lease)
    def before(self,node):
        if self.outer_node is not node:self.vm.compiled_before(node)
    def after(self,node,result):
        return result if self.outer_node is node else self.vm.compiled_after(node,result)
    def guard(self,node):
        self.engine._verify_active_plans();self.engine.verify_node(node)
        kinds=self.engine.stats.setdefault('python_translated_node_kinds',{})
        kind=syntax_kind(node).__name__;kinds[kind]=kinds.get(kind,0)+1
    def statement(self,key):
        node,function=self.unit.statements[key]
        self.engine.stats['python_compact_statement_calls']=self.engine.stats.get('python_compact_statement_calls',0)+1
        return (yield from function(self))
    def block(self,key):
        block,function=self.unit.blocks[key]
        if function is None:
            self.engine._force_translation_gap(block[0] if block else None,'non-entry-block')
        self.engine._verify_owned_identity(block)
        self.engine.stats['python_translated_blocks']=self.engine.stats.get('python_translated_blocks',0)+1
        return (yield from function(self))
    def residual_block(self,key):
        self.engine.stats['python_residual_block_calls']=self.engine.stats.get('python_residual_block_calls',0)+1
        return (yield from self.block(key))
    def enter_inline_block(self,key):
        block,_ = self.unit.blocks[key]
        self.engine._verify_owned_identity(block)
        self.engine.stats['python_inlined_blocks']=self.engine.stats.get('python_inlined_blocks',0)+1
    def unsupported(self,node):
        from .compiled_backend import CompiledUnsupported
        kind=syntax_kind(node).__name__
        gaps=self.engine.stats.setdefault('force_translation_gaps',{})
        gaps[kind]=gaps.get(kind,0)+1
        raise CompiledUnsupported(node,'force Python translation unsupported '+kind)

def prepare_blocks(blocks,expression_roots,*,max_source_bytes,max_function_bytes,entry_keys=None, owned_leaves=False, compact_control=False, max_bindings=100_000, routines=(), min_sync_routine_nodes=32):
    from .python_translation_expressions import prepare_expressions
    from . import runtime as R
    from .python_translation_template_bindings import bind_generated_source
    from types import FunctionType
    from . import python_translation_expression_fusion as PE
    # Every expression and block is generated before the admitted program runs.
    expressions=prepare_expressions(expression_roots,max_source_bytes=max_source_bytes,max_function_bytes=max_function_bytes,owned_leaves=owned_leaves,max_bindings=max_bindings)
    binding_count=expressions.binding_count
    used=len(expressions.source.encode());namespace={'R':R,'Decimal':Decimal,'_PE':PE}
    originals={}
    for block in blocks:
        originals.setdefault(tuple(id(node) for node in block),block)
    sources=[];nodes=[];source_templates={}
    block_bindings={}
    queued=set(originals if entry_keys is None else entry_keys)
    pending=[(key,originals[key],False) for key in originals if key in queued]
    operation_nodes={}
    segment_plans={};segment_cache={}
    segment_reserved_bytes=0;segment_reserved_bindings=0
    cursor=0
    def bind(node):
        nodes.append(node);return f'_nodes[{len(nodes)-1}]'
    def body(value):return f'(yield from _s.residual_block({tuple(id(n) for n in value)!r}))'
    while cursor<len(pending):
        key,block,is_operation=pending[cursor];cursor+=1
        lines=['def translated(_s):',' if False: yield None',' vm = _s.vm',' result = None']
        emitted=sum(len(line.encode())+1 for line in lines)
        serial=0
        def temp():
            nonlocal serial
            serial+=1
            return f't{serial}'
        def emit(d,text):
            nonlocal emitted
            line=' '*d+text
            emitted+=len(line.encode())+1
            if emitted>max_function_bytes:
                raise UnsupportedTranslation('generated source budget')
            lines.append(line)
        expression_roots_stack=[]
        fusion=PE.ExpressionEmitter(bind,emit,temp,compact_leaves=True)
        def ev(node,d):
            if compact_control:
                value=temp();emit(d,f'{value} = yield from _s.expressions.evaluate({bind(node)})')
            else:value=fusion.emit_expression(node,d)
            expression_roots_stack[-1].append(value)
            return value
        def condition(node,d):
            value=ev(node,d);checked=temp()
            emit(d,f'{checked} = R.boolean({value})')
            fusion.release(value,d)
            return checked
        def nested(child,d):
            # A label dispatcher is a generated function, never an AST adapter.
            if compact_control or d > 10 or any(syntax_kind(n) is ast.Label for n in child):
                child_key=tuple(id(node) for node in child)
                if child_key not in queued:
                    queued.add(child_key);pending.append((child_key,originals[child_key],False))
                emit(d,body(child))
            else:
                emit(d,f'_s.enter_inline_block({tuple(id(n) for n in child)!r})')
                emit_sequence(child,d)
            emit(d,'result = None')
        def store(name,value,d):emit(d,f'vm.set_variable({name!r}, {value})')
        def counter_read(name,handle):return f'vm.semantic_name({handle})'
        def emit_statement(node,d):
            n=bind(node);kind=syntax_kind(node)
            if kind in (ast.Literal, ast.Name, ast.Group, ast.Unary, ast.Binary,
                        ast.Conditional, ast.Attribute, ast.Index, ast.Call,
                        ast.New, ast.DynamicNew, ast.Await):
                # Explicit expression-list block API: the existing generated
                # expression owns the single hook/guard/error boundary.
                previous_result=temp();emit(d,f'{previous_result} = result')
                emit(d,'try:')
                emit(d+1,f'result = yield from _s.expressions.evaluate({n})')
                emit(d,'finally:');emit(d+1,f'{previous_result} = None')
                return
            expression_roots_stack.append([])
            previous_result=temp();emit(d,f'{previous_result} = result')
            emit(d,'try:');d+=1
            first,last,collection,item,receiver,writer,binder,handled_error,handled_index=(temp() for _ in range(9))
            emit(d,f'_s.before({n})')
            emit(d,'try:');d+=1
            emit(d,f'_s.guard({n})');emit(d,'result = None')
            if kind is ast.ExpressionStatement:
                expression=node.expression
                while syntax_kind(expression) is ast.Group:expression=expression.expression
                if syntax_kind(expression) is ast.Call:emit(d,f'result = yield from _s.expressions.call({bind(expression)}, require_value=False)')
                else:emit(d,f'result = {ev(node.expression,d)}')
            elif kind is ast.Assign:
                target=syntax_kind(node.target)
                if target is ast.Name:store(node.target.name,ev(node.value,d),d)
                elif target is ast.Attribute:
                    emit(d,f'{receiver} = yield from _s.expressions.receiver({bind(node.target.object)})')
                    emit(d,f'{writer} = _s.access.prepare_attribute_write(vm, {receiver}, {node.target.name!r})')
                    emit(d,f'{writer}({ev(node.value,d)})')
                elif target is ast.Index:
                    emit(d,f'{receiver} = yield from _s.expressions.receiver({bind(node.target.object)})')
                    emit(d,f'{binder} = _s.access.prepare_index_write(vm, {receiver})')
                    emit(d,f'{writer} = {binder}({ev(node.target.index,d)})');emit(d,f'{writer}({ev(node.value,d)})')
                else:raise UnsupportedTranslation('assignment target has invalid AST role')
            elif kind is ast.Var:
                names=tuple(node.names)
                emit(d,f'if vm.locals is None and any(name.casefold() in vm.imports for name in {names!r}):')
                emit(d+1,f'raise ValueError("Имя импорта конфликтует с объявлением")')
                emit(d,f'for name in {names!r}:');emit(d+1,f'(vm.variables if vm.locals is None else vm.locals).setdefault(name.casefold(), None)')
            elif kind in (ast.Routine,ast.Label):emit(d,f'pass')
            elif kind is ast.If:
                matched=temp();emit(d,f'{matched} = False')
                for test,child in node.branches:
                    emit(d,f'if not {matched}:')
                    check=condition(test,d+1)
                    emit(d+1,f'if {check}:');emit(d+2,f'{matched} = True');nested(child,d+2)
                emit(d,f'if not {matched}:');nested(node.otherwise,d+1)
            elif kind in (ast.For,ast.While,ast.ForEach):
                if kind is ast.For:
                    emit(d,f'{first} = R.require_number({ev(node.start,d)})');emit(d,f'{last} = R.require_number({ev(node.end,d)})')
                    store(node.name,first,d)
                    counter=ast.Name(node.token,node.name.casefold());counter_name=bind(counter)
                    emit(d,f'while R.require_number({counter_read(node.name,counter_name)}) <= {last}:')
                elif kind is ast.While:
                    emit(d,'while True:')
                    check=condition(node.condition,d+1);emit(d+1,f'if not {check}: break')
                else:
                    emit(d,f'{collection} = {ev(node.collection,d)}');emit(d,f'for {item} in vm.compiled_iterable({collection}):')
                    emit(d+1,f'vm.set_variable({node.name!r},{item})')
                emit(d+1,f'try:');nested(node.body,d+2)
                emit(d+1,f'except R._Continue:');emit(d+2,f'pass')
                emit(d+1,f'except R._Break:');emit(d+2,f'break')
                if kind is ast.For:store(node.name,f'R.require_number({counter_read(node.name,counter_name)}) + Decimal(1)',d+1)
            elif kind is ast.Try:
                emit(d,f'try:');nested(node.body,d+1)
                emit(d,f'except R.BSLRuntimeError as {handled_error}:')
                emit(d+1,f'for {handled_index} in range(len(vm._handled_errors)):');emit(d+2,f'vm._handled_errors[{handled_index}] = None')
                emit(d+1,f'vm._handled_errors.append({handled_error})');emit(d+1,f'try:');nested(node.handler,d+2)
                emit(d+1,f'finally:');emit(d+2,f'vm._handled_errors.pop()')
            elif kind is ast.Return:emit(d,f'raise R._Return({ev(node.value,d) if node.value is not None else "None"})')
            elif kind is ast.Import:emit(d,f'vm.semantic_import({n})')
            elif kind is ast.Execute:emit(d,f'yield from vm.semantic_execute({n}, _evaluation=_s.expressions)')
            elif kind is ast.Raise:emit(d,f'yield from vm.semantic_raise({n}, _evaluation=_s.expressions)')
            elif kind is ast.Goto:emit(d,f'raise R._Goto({n})')
            elif kind is ast.Break:emit(d,f'raise R._Break')
            elif kind is ast.Continue:emit(d,f'raise R._Continue')
            else:raise UnsupportedTranslation('unsupported executable statement: '+kind.__name__)
            d-=1
            error,converted=temp(),temp()
            emit(d,f'except BaseException as {error}:')
            emit(d+1,f'if _s.outer_node is {n}: raise')
            emit(d+1,f'{converted} = vm.compiled_exception({n},{error})')
            emit(d+1,f'if {converted} is {error}: raise')
            emit(d+1,f'raise {converted} from None')
            emit(d,'finally:')
            scratch=[]
            if kind is ast.For:scratch=[first,last]
            elif kind is ast.ForEach:scratch=[collection,item]
            elif kind is ast.Try:scratch=[handled_error,handled_index]
            elif kind is ast.Assign:
                if target is ast.Attribute:scratch=[receiver,writer]
                elif target is ast.Index:scratch=[receiver,binder,writer]
            temporaries=[*scratch,converted,*expression_roots_stack.pop()]
            emit(d+1,' = '.join(temporaries)+' = None')
            emit(d,f'result = _s.after({n}, result)')
            d-=1;emit(d,'finally:');emit(d+1,f'{previous_result} = None')
        def closed(node):
            from dataclasses import fields
            kind=syntax_kind(node)
            if kind is ast.Literal:return any(type(node.value) is scalar for scalar in (Decimal,bool,str,type(None)))
            if kind not in (ast.Name,ast.Group,ast.Unary,ast.Binary,ast.Conditional,ast.Assign,ast.Var,ast.Return,ast.If,ast.For,ast.While,ast.Break,ast.Continue):return False
            if kind is ast.Assign and syntax_kind(node.target) is not ast.Name:return False
            def children(value):
                if isinstance(value,ast.Node):return closed(value)
                if isinstance(value,(tuple,list)):return all(children(item) for item in value)
                return True
            return all(children(getattr(node,field.name)) for field in fields(node) if field.name!='token')
        def emit_sequence(sequence,d,*,segments=True):
            nonlocal segment_reserved_bytes,segment_reserved_bindings
            if not sequence:emit(d,'pass');return
            if segments and not compact_control and not is_operation:
                from .owned_syntax import is_owned
                from .python_translation_sync_routines import lower_block,Ineligible
                if is_owned(sequence):
                    start=0
                    while start<len(sequence):
                        if not closed(sequence[start]):
                            emit_statement(sequence[start],d);start+=1;continue
                        stop=start+1
                        while stop<len(sequence) and closed(sequence[stop]):stop+=1
                        selected=sequence[start:stop]
                        profitable=(len(selected)>=4 or any(syntax_kind(node) in (ast.For,ast.While) for node in selected))
                        cache_key=(id(sequence),start,stop)
                        if profitable and cache_key not in segment_cache:
                            try:plan=lower_block(sequence,start=start,stop=stop,max_source_bytes=max_source_bytes-used-segment_reserved_bytes,
                                                max_function_bytes=max_function_bytes,max_bindings=max_bindings-binding_count-segment_reserved_bindings-1)
                            except Ineligible:segment_cache[cache_key]=None
                            else:
                                index=len(segment_cache);segment_cache[cache_key]=index;segment_plans[index]=plan
                                segment_reserved_bytes+=plan.source_bytes;segment_reserved_bindings+=plan.binding_count+1
                        index=segment_cache.get(cache_key)
                        if index is None:
                            for node in selected:emit_statement(node,d)
                        else:
                            outcome=temp();emit(d,f'{outcome} = _s.sync_segment({index}, result)')
                            emit(d,'try:');emit(d+1,f'if {outcome} is None:')
                            emit_sequence(selected,d+2,segments=False)
                            emit(d+1,f'elif {outcome}[0]:');emit(d+2,f'raise R._Return({outcome}[1])')
                            emit(d+1,'else:');emit(d+2,'result = None')
                            emit(d,'finally:');emit(d+1,f'{outcome} = None')
                        start=stop
                    return
            for node in sequence:
                if compact_control and not is_operation:
                    operation_key=('statement',id(node))
                    if operation_key not in queued:
                        queued.add(operation_key);operation_nodes[id(node)]=node
                        pending.append((operation_key,(node,),True))
                    emit(d,f'result = yield from _s.statement({id(node)})')
                else:emit_statement(node,d)
        labels={node.name.casefold():i for i,node in enumerate(block) if syntax_kind(node) is ast.Label}
        if not labels:
            emit_sequence(block,1)
        else:
            emit(1,'pc = 0');emit(1,'while True:')
            emit(2,f'if pc >= {len(block)}: break');emit(2,'try:')
            for i,node in enumerate(block):
                emit(3,f'{"if" if i==0 else "elif"} pc == {i}:')
                emit_sequence((node,),4)
            emit(2,'except R._Goto as jump:');emit(3,f'labels = {labels!r}')
            emit(3,'if jump.name not in labels: raise');emit(3,'pc = labels[jump.name]')
            emit(2,'else:');emit(3,'pc += 1')
        emit(1,'return result')
        lines[4:4] = [' '*depth+text for depth,text in fusion.helper_lines]
        source='\n'.join(lines)+'\n'
        source=source.replace('def translated(_s):','def translated(_s, _p):',1)
        canonical,operands=bind_generated_source(source,nodes)
        # Count only source actually compiled, once per shared control shape.
        # The raw emitter above remains independently bounded per function.
        if len(canonical.encode())>max_function_bytes:raise UnsupportedTranslation('generated function source budget')
        template=source_templates.get(canonical)
        if template is None:
            template=len(sources);source_templates[canonical]=template
            used+=len(canonical.encode())
            if used>max_source_bytes:raise UnsupportedTranslation('generated unit source budget')
            sources.append(canonical)
        binding_count+=len(operands)
        if binding_count>max_bindings:raise UnsupportedTranslation('generated operand binding budget')
        block_bindings[key]=(template,tuple(operands))
    namespace['_nodes']=();functions={key:(block,None) for key,block in originals.items()};statements={}
    compiled=[]
    for source in sources:
        exec(_CODE_CACHE.get(source),namespace)
        compiled.append(namespace['translated'])
    # Do not retain a template function back-reference to the unpruned globals.
    namespace.pop('translated',None)
    for key,(template,operands) in block_bindings.items():
        function=compiled[template]
        bound=FunctionType(function.__code__,namespace,function.__name__,(operands,))
        if key and key[0]=='statement':statements[key[1]]=(operation_nodes[key[1]],bound)
        else:functions[key]=(originals[key],bound)
    # An optional whole-routine specialization is admitted with this unit, not
    # compiled on call. It shares the same source/binding accounting and lifetime.
    from .python_translation_sync_routines import lower, Ineligible
    sync_routines={}
    for routine in routines:
        if min_sync_routine_nodes:
            # Cheap static profitability before generating a second function.
            from dataclasses import fields
            pending_cost=[routine];seen_cost=set();cost=0;has_loop=False
            while pending_cost and cost<min_sync_routine_nodes and not has_loop:
                value=pending_cost.pop()
                if id(value) in seen_cost:continue
                seen_cost.add(id(value))
                if isinstance(value,ast.Node):
                    cost+=1;kind=syntax_kind(value)
                    if kind in (ast.For,ast.While):has_loop=True
                    for field in fields(value):
                        if field.name!='token' and not (kind is ast.Literal and field.name=='value'):
                            pending_cost.append(getattr(value,field.name))
                elif isinstance(value,(tuple,list)):pending_cost.extend(value)
            if cost<min_sync_routine_nodes and not has_loop:continue
        try:
            plan=lower(routine,max_source_bytes=max_source_bytes-used,
                       max_function_bytes=max_function_bytes,max_bindings=max_bindings-binding_count-1)
        except Ineligible:continue
        # Do not add a full lease to tiny calls after generic activation. Their
        # existing translated call boundary is cheaper; loops amortize admission.
        if (len(plan.nodes)<min_sync_routine_nodes
                and not any(syntax_kind(node) in (ast.For,ast.While) for node in plan.nodes)):continue
        used+=plan.source_bytes;binding_count+=plan.binding_count+1
        sync_routines[id(routine)]=(routine,plan)
    admitted_segments={}
    for key,plan in segment_plans.items():
        if used+plan.source_bytes>max_source_bytes or binding_count+plan.binding_count+1>max_bindings:continue
        used+=plan.source_bytes;binding_count+=plan.binding_count+1
        admitted_segments[key]=plan
    return BlockUnit(functions,expressions,used,statements,binding_count,sync_routines,admitted_segments)

# Slots must not capture state across instrumented execution callbacks.
_SCALAR_EXECUTION_NAMES = ('before', 'after', 'guard', 'enter_inline_block', 'residual_block', 'block', 'sync_segment')
_SCALAR_EXECUTION_ABI = tuple(getattr(Execution, name) for name in _SCALAR_EXECUTION_NAMES)
