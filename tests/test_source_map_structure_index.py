"""Compare structural source mapping with the previous dump-based matcher."""
import ast
from pathlib import Path
from types import CodeType
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_errors import SourceMap, _StructureIndex


def dump_compile(self,generated,filename,body_offset):
    """Independent reference for the pre-optimization expression matcher."""
    tree=ast.parse(generated,filename=filename);rows={};normalized={}
    for line,(token,expressions) in self.rows.items():
        groups={}
        for text,where in expressions:
            if text not in normalized:
                try:normalized[text]=ast.dump(ast.parse(text.strip(),mode='eval').body,include_attributes=False)
                except SyntaxError:normalized[text]=text.strip()
            groups.setdefault(normalized[text],[]).append(where)
        rows[line+body_offset]=(token,groups,{key.partition('(')[0] for key in groups})
    consumed={}
    def visit(node,inherited=None,parent_line=None):
        original=getattr(node,'lineno',None)
        token=inherited if original==parent_line else None
        row=rows.get(original)
        if row:
            token=token or row[0]
            if isinstance(node,ast.expr) and type(node).__name__ in row[2]:
                key=ast.dump(node,include_attributes=False);matches=row[1].get(key)
                if matches:
                    used=consumed.get((original,key),0)
                    token=matches[min(used,len(matches)-1)];consumed[(original,key)]=used+1
        for child in ast.iter_child_nodes(node):visit(child,token,original)
        if token is not None and original is not None:
            node.lineno=token.line;node.end_lineno=token.line
            node.col_offset=max(0,token.column-1);node.end_col_offset=node.col_offset+1
    visit(tree)
    return compile(tree,filename,'exec')


def signature(code):
    return (code.co_code,code.co_names,code.co_varnames,code.co_freevars,code.co_cellvars,
        code.co_argcount,code.co_kwonlyargcount,code.co_flags,code.co_firstlineno,
        code.co_linetable if hasattr(code,'co_linetable') else code.co_lnotab,getattr(code,'co_exceptiontable',None),
        tuple(code.co_positions()) if hasattr(code,'co_positions') else tuple(code.co_lines()),
        tuple(signature(value) if isinstance(value,CodeType) else value for value in code.co_consts))


class SourceMapStructureTests(unittest.TestCase):
    def test_selective_auxiliary_compile_audit_denial_is_preserved(self):
        # Audit hooks cannot be removed: isolate both registration and denial.
        import subprocess,sys
        code="""
import sys
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_errors import SourceMap
source='T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;'
vm=Interpreter();default=SourceMap._allow_markers;SourceMap._allow_markers=False
vm.execute(source,'audit.bsl')
seen=[]
def observe(event,args):
    if event=='compile' and args[1]=='<unknown>' and type(args[0]) is bytes:seen.append(args[0])
sys.addaudithook(observe)
vm.execute(source,'audit.bsl')
if not seen:raise AssertionError('baseline has no real auxiliary parses')
target=b'_constants[0]'
if target not in seen:raise AssertionError('target auxiliary parse absent')
SourceMap._allow_markers=default;vm.variables.clear()
def deny(event,args):
    if event=='compile' and args[1]=='<unknown>' and args[0]==target:
        raise RuntimeError('selective auxiliary compile denied')
sys.addaudithook(deny)
try:vm.execute(source,'audit.bsl')
except RuntimeError as error:
    if str(error)!='selective auxiliary compile denied':raise AssertionError(str(error))
    if vm.variables:raise AssertionError(vm.variables)
else:raise AssertionError('selective compile authorization bypassed')
"""
        result=subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_default_compile_audit_stream_matches_unmarked_baseline(self):
        import subprocess,sys
        code="""
import sys
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_errors import SourceMap
source='T=New ValueTable;T.Columns.Add("N");For I=0 To 2 Do Row=T.Add();Row.N=I;EndDo;'
vm=Interpreter();vm.execute(source,'audit.bsl');seen=[]
def observe(event,args):
    if event=='compile':seen.append((args[0] if type(args[0]) is bytes else type(args[0]).__name__,args[1]))
sys.addaudithook(observe)
vm.execute(source,'audit.bsl');current=list(seen);seen.clear()
SourceMap._allow_markers=False
vm.execute(source,'audit.bsl')
if current!=seen:raise AssertionError('default audit stream differs from unmarked baseline')
"""
        result=subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_structural_identity_matches_dump_identity(self):
        snippets=('x+x','x + y','x[1]','x[True]','x[1.0]','x["1"]','x[b"1"]',
            'x[-0.0]','x[0.0]','f(x,y=1)','f(x,**y)','[x for x in y if x]',
            'lambda x:x+1','(x,y)','[x,y]','{x:y}','x.y','x[1:2:3]',
            'f"{x!r}"','x if y else z','not x','x is None','(x + x)')
        index=_StructureIndex();by_dump={};by_key={}
        for snippet in snippets:
            for node in ast.walk(ast.parse(snippet,mode='eval')):
                dump=ast.dump(node,include_attributes=False);key=index.key(node)
                self.assertEqual(by_dump.setdefault(dump,key),key)
                self.assertEqual(by_key.setdefault(key,dump),dump)
        node=ast.parse('x+x',mode='eval').body;key=index.key(node)
        node.lineno=999;node.col_offset=500
        self.assertEqual(index.key(ast.parse('x+x',mode='eval').body),key)
    def test_each_ast_node_indexed_once_and_cache_is_local(self):
        tree=ast.parse('f(x[0]+x[1], y=2)',mode='eval');index=_StructureIndex()
        first=index.key(tree);count=len(index.nodes)
        for _ in range(20):self.assertEqual(index.key(tree),first)
        self.assertEqual(len(index.nodes),count)
        self.assertEqual(len(_StructureIndex().nodes),0)
    def test_exact_bytecode_and_location_tables_on_real_modules(self):
        root=Path(__file__).resolve().parents[1]
        sources=[(root/path).read_text(encoding='utf-8') for path in (
            'integrational_tests/measurements/regex_family.bsl',
            'integrational_tests/tests/numbers.bsl','integrational_tests/tests/dates.bsl')]
        sources += ['Function F(Val X)\nTry Return X/0; Except Return 2;EndTry;EndFunction\nR=F(1);',
            '&AtServer\nFunction F(Val X) Return X+1;EndFunction\nR=F(2);']
        for source in sources:
            with self.subTest(source=source[:40]):
                direct=Interpreter().prepare(source,'mapping.bsl')
                with patch.object(SourceMap,'_allow_markers',False),patch.object(SourceMap,'compile',dump_compile):
                    reference=Interpreter().prepare(source,'mapping.bsl')
                self.assertEqual(signature(direct._plan.function.__code__),signature(reference._plan.function.__code__))
                if direct._exports and direct._exports.server_plan:
                    self.assertEqual(signature(direct._exports.server_plan.function.__code__),signature(reference._exports.server_plan.function.__code__))

    def test_collection_markers_preserve_exact_code_and_locations(self):
        prefixes=[
            'T=New ValueTable;T.Columns.Add("N");For I=0 To 3 Do Row=T.Add();Row.N=I;EndDo;',
            'T=New ValueList;For I=0 To 3 Do Item=T.Add(I);EndDo;',
            'Т=Новый ТаблицаЗначений;Т.Колонки.Добавить("Цена");Для Н=0 По 3 Цикл Стр=Т.Добавить();Стр.Цена=Н;КонецЦикла;',
            'T=New ValueList;For I=0 To 2 Do For J=0 To 2 Do T.Add(I*J);EndDo;EndDo;']
        suffixes=['', '\nTry\n X=1/0;\nExcept\n Text=ErrorDescription();\nEndTry;',
                  '\nA=New Array;A.Add(1);If A.Get(0)=1 Then Result=2;Else Result=3;EndIf;',
                  '\nX=New Structure("a",1);Y=X.a+X.a;']
        for prefix in prefixes:
            for suffix in suffixes:
                with self.subTest(prefix=prefix[:30],suffix=suffix[:30]):
                    with patch.object(SourceMap,'_allow_markers',True):
                        direct=Interpreter().prepare(prefix+suffix,'mixed.bsl')
                    self.assertIn('_source_location_marker',direct._plan.generated_source)
                    with patch.object(SourceMap,'_allow_markers',False),patch.object(SourceMap,'compile',dump_compile):
                        reference=Interpreter().prepare(prefix+suffix,'mixed.bsl')
                    self.assertEqual(signature(direct._plan.function.__code__),signature(reference._plan.function.__code__))
                    self.assertNotIn('_source_location_marker',direct._plan.function.__code__.co_names)

    def test_collection_markers_do_not_increase_arithmetic_nesting(self):
        for depth in (5,30,60):
            source='T=New ValueList;For I=0 To 1 Do T.Add('+('1+('*depth)+'1'+(')'*depth)+');EndDo;'
            with patch.object(SourceMap,'_allow_markers',True):direct=Interpreter().prepare(source)
            with patch.object(SourceMap,'_allow_markers',False):reference=Interpreter().prepare(source)
            self.assertEqual(signature(direct._plan.function.__code__),signature(reference._plan.function.__code__))

    def test_marker_metadata_not_retained_by_prepared_plan(self):
        import gc,weakref
        import yadinassi.execution.codegen.experimental_naked_errors as errors
        refs=[]
        def create():
            value=SourceMap();refs.append(weakref.ref(value));return value
        was_enabled=gc.isenabled();gc.disable()
        try:
            with patch.object(errors,'SourceMap',create):
                plan=Interpreter().prepare('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
            self.assertTrue(refs);self.assertTrue(all(ref() is None for ref in refs))
            self.assertNotIn('_source_location_marker',plan._plan.function.__globals__)
        finally:
            if was_enabled:gc.enable()

    def test_index_is_released_without_waiting_for_cyclic_gc(self):
        import gc,weakref
        import yadinassi.execution.codegen.experimental_naked_errors as errors
        refs=[]
        def create():
            value=_StructureIndex();refs.append(weakref.ref(value));return value
        was_enabled=gc.isenabled();gc.disable()
        try:
            with patch.object(SourceMap,'_use_markers',False),patch.object(errors,'_StructureIndex',create):
                Interpreter().prepare('Function F(Val X) Return X+1;EndFunction R=F(2);')
            self.assertTrue(refs)
            self.assertTrue(all(ref() is None for ref in refs))
        finally:
            if was_enabled:gc.enable()
