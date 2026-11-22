"""Compare prepared direct AST and explicit whole-source position mapping."""
import ast
from contextlib import closing
from pathlib import Path
from types import CodeType
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi import runtime
from yadinassi.execution.codegen import experimental_direct_ast as direct
from yadinassi.execution.codegen.experimental_naked_errors import _StructureIndex
from yadinassi.execution.direct import python_direct


def signature(code):
    return (code.co_code,code.co_names,code.co_varnames,code.co_freevars,code.co_cellvars,
        code.co_argcount,code.co_kwonlyargcount,code.co_flags,code.co_firstlineno,
        code.co_linetable if hasattr(code,'co_linetable') else code.co_lnotab,getattr(code,'co_exceptiontable',None),
        tuple(code.co_positions()) if hasattr(code,'co_positions') else tuple(code.co_lines()),
        tuple(signature(value) if isinstance(value,CodeType) else value for value in code.co_consts))


class SourceMapStructureTests(unittest.TestCase):
    def test_real_compile_audit_streams(self):
        self._check_audit_subprocess("observe")

    def test_real_compile_audit_denial_before_effects(self):
        # See also WholeSourceResearchTests.test_real_source_and_ast_denial_before_effects
        # for the explicit route's AST denial and mutation controls.
        for mode in ("default-ast", "explicit-source"):
            with self.subTest(mode=mode):
                self._check_audit_subprocess(mode)

    def _check_audit_subprocess(self, mode):
        import subprocess
        import sys

        script = """
import ast
import sys
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen import experimental_direct_ast as direct
from yadinassi.execution.direct import python_direct

source = 'T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo; R=T.Count();'
vm = Interpreter()
vm.execute(source, 'warm.bsl')
seen = []
mode = sys.argv[1]

def check(value):
    if not value:
        raise AssertionError((mode, seen))

def hook(event, args):
    if event != 'compile':
        return
    seen.append((type(args[0]).__name__, args[1]))
    if ((mode == 'default-ast' and type(args[0]) is ast.Module) or
        (mode == 'explicit-source' and type(args[0]) is bytes and args[1] == 'audit.bsl')):
        raise RuntimeError('compile denied')

sys.addaudithook(hook)
for explicit in ([False, True] if mode == 'observe' else [mode == 'explicit-source']):
    seen.clear()
    vm.variables.clear()
    try:
        if explicit:
            with patch.object(python_direct, '_compile', direct.compile_module_whole_source):
                plan = vm.prepare(source, 'audit.bsl')
        else:
            plan = vm.prepare(source, 'audit.bsl')
    except RuntimeError as error:
        check(mode != 'observe' and str(error) == 'compile denied')
        check(not vm.variables)
    else:
        check(mode == 'observe')
        check(not vm.variables)
    expected = [('Module', None)]
    if explicit:
        expected = [('bytes', 'audit.bsl')] + ([] if mode == 'explicit-source' else expected)
    check(seen == expected)
    if mode == 'observe':
        vm.execute_prepared(plan)
        check(vm.variables['r'] == 3)
"""
        flags = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
        result = subprocess.run([sys.executable, *flags, "-c", script, mode],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def _compare(self, source, filename, *, execute=False):
        with closing(Interpreter()) as default_vm, closing(Interpreter()) as explicit_vm:
            default = default_vm.prepare(source, filename)
            with patch.object(python_direct, "_compile", direct.compile_module_whole_source):
                explicit = explicit_vm.prepare(source, filename)
            self.assertEqual(default._plan._research_roundtrip_visits, 0)
            self.assertGreater(explicit._plan._research_roundtrip_visits, 0)
            self.assertEqual(signature(default._plan.function.__code__),
                             signature(explicit._plan.function.__code__))
            if default._exports and default._exports.server_plan:
                self.assertEqual(signature(default._exports.server_plan.function.__code__),
                                 signature(explicit._exports.server_plan.function.__code__))
            if execute:
                default_vm.execute_prepared(default)
                explicit_vm.execute_prepared(explicit)
                return default_vm.variables.copy(), explicit_vm.variables.copy()

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
                self._compare(source, 'mapping.bsl')

    def test_collection_roundtrip_preserves_exact_code_locations_and_results(self):
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
                    states = self._compare(prefix+suffix, 'mixed.bsl', execute=True)
                    for state in states:
                        collection = state['т'] if prefix.startswith('Т') else state['t']
                        if 'For J=' in prefix:
                            expected = (0, 0, 0, 0, 1, 2, 0, 2, 4)
                        else:
                            expected = (0, 1, 2, 3)
                        self.assertEqual(collection.count(), len(expected))
                        self.assertEqual(tuple(collection.get(i)[0] for i in range(len(expected))), expected)
                        if suffix.startswith('\nTry'):
                            self.assertTrue(state['text'].startswith('mixed.bsl:3:5: '), state['text'])
                        elif suffix.startswith('\nA='):
                            self.assertEqual(state['result'], 2)
                        elif suffix.startswith('\nX='):
                            self.assertEqual(state['y'], 2)
                    if 'text' in states[0]:
                        self.assertEqual(states[0]['text'], states[1]['text'])

    def test_whole_source_roundtrip_preserves_arithmetic_nesting(self):
        for depth in (5,30,60):
            source='T=New ValueList;For I=0 To 1 Do T.Add('+('1+('*depth)+'1'+(')'*depth)+');EndDo;'
            self._compare(source, 'nested.bsl')

    def test_parser_nodes_are_released_while_prepared_snapshot_is_live(self):
        import weakref

        refs = []
        parse = runtime.parse

        def record(*args, **kwargs):
            nodes = parse(*args, **kwargs)
            refs.extend(weakref.ref(node) for node in nodes)
            return nodes

        with closing(Interpreter()) as vm:
            with patch.object(runtime, 'parse', record):
                plan = vm.prepare('T=New ValueList;For I=0 To 2 Do T.Add(I);EndDo;')
            self.assertTrue(refs)
            self.assertTrue(all(ref() is None for ref in refs))
            self.assertIsNotNone(plan._plan._generated_tree)
            vm.execute_prepared(plan)
            self.assertEqual(vm.variables['t'].count(), 3)

    def test_generated_ast_is_released_after_first_display(self):
        import gc
        import weakref

        was_enabled = gc.isenabled()
        gc.disable()
        try:
            with closing(Interpreter()) as vm:
                # A routine module can also hold a separate export-plan copy.
                plan = vm.prepare('R=1+2;')
                ref = weakref.ref(plan._plan._generated_tree)
                self.assertIsNotNone(ref())
                displayed = plan._plan.generated_source
                self.assertIn('naked_module', displayed)
                self.assertIsNone(ref())
                with patch.object(ast, 'unparse', side_effect=AssertionError('already displayed')):
                    self.assertEqual(plan._plan.generated_source, displayed)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'], 3)
        finally:
            if was_enabled:
                gc.enable()
