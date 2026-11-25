"""One real Python AST compile; generated source is a diagnostic view only."""
import ast
import subprocess
import sys
import unittest
import types
from yadinassi import Interpreter
from unittest.mock import patch
from yadinassi.execution.codegen import direct_emitter as direct


class WholeSourceResearchTests(unittest.TestCase):
    def test_linear_ast_size_without_subtree_dump_or_unparse(self):
        counts={}
        from builtins import compile as compile_python

        def record(tree,*args,**kwargs):
            counts[shape,size]=sum(1 for node in ast.walk(tree))
            return compile_python(tree,*args,**kwargs)

        with patch.object(ast,'dump',side_effect=AssertionError('no subtree dumps')), \
             patch.object(ast,'unparse',side_effect=AssertionError('diagnostic only')), \
             patch.object(direct,'compile',record,create=True):
            vm=Interpreter()
            self.addCleanup(vm.close)
            for shape in ('nested','wide'):
                for size in (8,16,32):
                    source='R='+'-'.join(['1']*size)+';' if shape=='nested' else ';'.join('X%d=%d'%(i,i) for i in range(size))+';'
                    vm.prepare(source)
                self.assertLessEqual(counts[shape,32],2*counts[shape,16]+2)
                self.assertLessEqual(counts[shape,32]-counts[shape,16],2*(counts[shape,16]-counts[shape,8])+2)

    def test_handlers_use_one_module_source_for_diagnostics(self):
        source=(
            '// source-only marker\n'
            'Try\n'
            '    R=1/0;\n'
            'Except\n'
            '    First=ErrorDescription();\n'
            'EndTry;\n'
            'Try\n'
            '    R=2/0;\n'
            'Except\n'
            '    Second=ErrorDescription();\n'
            'EndTry;'
        )
        vm=Interpreter()
        self.addCleanup(vm.close)
        plan=vm.prepare(source,'handlers.bsl')
        generated=plan._plan.generated_source
        self.assertNotIn('source-only marker',generated)
        self.assertEqual(generated.count('_Source'),2)
        vm.execute(source,'handlers.bsl')
        for name,line in (('first',3),('second',8)):
            description=vm.variables[name]
            self.assertTrue(description.startswith(f'handlers.bsl:{line}:8: '), description)
            self.assertIn('Деление на ноль', description)

    def test_changed_display_cannot_change_execution(self):
        real=ast.unparse
        def change(tree):return real(tree).replace('x = 1','z = 1')
        vm=Interpreter()
        self.addCleanup(vm.close)
        plan=vm.prepare('X=1;')
        with patch.object(ast,'unparse',change):
            self.assertIn('z = 1',plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables,{'x':1})

    def test_python_source_parse_is_not_used_by_execution(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        with patch.object(ast,'parse',side_effect=AssertionError('do not reparse Python')):
            vm.execute('X=1;')
        self.assertEqual(vm.variables,{'x':1})

    def test_code_positions_do_not_change_when_display_is_requested(self):
        import builtins
        def signature(code):
            locations=tuple(code.co_positions()) if hasattr(code,'co_positions') else tuple(code.co_lines())
            return code.co_code,locations,tuple(signature(x) if type(x) is types.CodeType else x for x in code.co_consts)
        for source in ('R=1+2*3;', 'T=New ValueList;For I=0 To 3 Do T.Add(I);EndDo;R=T.Get(1).Value;',
                       'Function F(Val N) If N=0 Then Return 1;Else Return N*F(N-1);EndIf;EndFunction;R=F(3);'):
            captured=[]
            def record(tree,*args,**kwargs):
                code=builtins.compile(tree,*args,**kwargs);captured.append(code);return code
            vm=Interpreter()
            self.addCleanup(vm.close)
            with patch.object(direct,'compile',record,create=True):
                plan=vm.prepare(source,'positions.bsl')
                self.assertEqual(len(captured),1)
                before=signature(captured[0])
                self.assertIn('def naked_module(',plan._plan.generated_source)
                self.assertEqual(signature(captured[0]),before)
                vm.execute_prepared(plan)
                self.assertEqual(len(captured),1)

    def test_real_ast_audit_denial_is_before_effects(self):
        script="""
import ast,sys
from yadinassi import Interpreter
policy=sys.argv[1];events=[];output=[]
def check(value):
    if not value:raise AssertionError(('audit contract mismatch',policy,events))
def hook(event,args):
    if event!='compile':return
    events.append((type(args[0]).__name__,args[1]))
    if policy=='deny' and isinstance(args[0],ast.Module):
        raise RuntimeError('audit denied')
Interpreter().execute('Warm=0;')
vm=Interpreter(output.append)
sys.addaudithook(hook)
try:
    plan=vm.prepare('Message("effect");X=1;Y=X+1;','probe.bsl')
except RuntimeError as error:
    check(str(error)=='audit denied' and policy=='deny')
    check(not vm.variables and not output)
else:
    check(policy=='allow')
    check(not vm.variables and not output)
    check(plan._plan.generated_source)
    vm.execute_prepared(plan)
    check(vm.variables['y']==2 and output==['effect'])
check(events==[('Module',None)])
"""
        flags=['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []
        for policy in ('deny','allow'):
            with self.subTest(policy=policy):
                subprocess.run([sys.executable,*flags,'-c',script,policy],check=True)

class DefaultDirectCompileTests(unittest.TestCase):
    def setUp(self):
        self.vm=Interpreter()
        self.addCleanup(self.vm.close)

    def test_prepare_execute_eval_and_runtime_error_do_not_roundtrip(self):
        with patch.object(ast,'unparse',side_effect=AssertionError('no automatic unparse')):
            plan=self.vm.prepare('R=1;')
            self.assertIsNotNone(plan._plan._generated_tree)
            self.vm.execute_prepared(plan)
            self.vm.execute('Execute("R=R+1;"); R=Eval("R+2");')
            self.assertEqual(self.vm.variables['r'],4)
            with self.assertRaisesRegex(Exception,'failed.bsl:2:4'):
                self.vm.execute('R=3;\nR=1/0;','failed.bsl')
        self.assertIn('naked_module',plan._plan.generated_source)
        with patch.object(ast,'unparse',side_effect=AssertionError('cached')):
            self.assertIn('naked_module',plan._plan.generated_source)

    def test_compiler_failure_diagnoses_once_without_replay(self):
        source='R=1;'
        error=TypeError('synthetic invalid generated AST')
        with patch.object(direct,'compile',create=True,side_effect=error) as compile_tree:
            with self.assertRaises(TypeError) as observed:
                self.vm.execute(source)
        self.assertIs(observed.exception,error)
        compile_tree.assert_called_once()
        self.assertEqual(self.vm.variables,{})

    def test_opted_in_extensions_also_use_only_direct_ast(self):
        vm=Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        with patch.object(ast,'unparse',side_effect=AssertionError('diagnostic only')):
            vm.execute('R=1; Execute("R=R+1;"); R=Eval("R+2");')
        self.assertEqual(vm.variables['r'],4)
