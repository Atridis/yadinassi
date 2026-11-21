"""Two genuine compilation events; still an explicit audit-contract experiment."""
import ast
import functools
import subprocess
import sys
import unittest
import types
from yadinassi import Interpreter
from yadinassi.execution.direct import python_direct
from unittest.mock import patch
from yadinassi.execution.codegen import experimental_direct_ast as direct


class WholeSourceResearchTests(unittest.TestCase):
    def test_pairwise_walk_counts_without_subtree_dump(self):
        counts={}
        with patch.object(ast,'dump',side_effect=AssertionError('no subtree dumps')),patch.object(python_direct,'_compile',direct.compile_module_whole_source):
            for shape in ('nested','wide'):
                for size in (8,16,32):
                    source='R='+'-'.join(['1']*size)+';' if shape=='nested' else ';'.join('X%d=%d'%(i,i) for i in range(size))+';'
                    vm=Interpreter();plan=vm.prepare(source);counts[shape,size]=plan._plan._research_roundtrip_visits;vm.close()
                self.assertLessEqual(counts[shape,32],2*counts[shape,16]+2)
                self.assertEqual(counts[shape,32]-counts[shape,16],2*(counts[shape,16]-counts[shape,8]))

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
        self.assertEqual(generated.count('_diagnostic_source'),2)
        vm.execute(source,'handlers.bsl')
        for name,line in (('first',3),('second',8)):
            description=vm.variables[name]
            self.assertTrue(description.startswith(f'handlers.bsl:{line}:8: '), description)
            self.assertIn('Деление на ноль', description)

    def test_changed_roundtrip_rejected_before_execution(self):
        real=ast.unparse
        def change(tree):return real(tree).replace("'x'","'z'")
        vm=Interpreter()
        with patch.object(ast,'unparse',change),patch.object(python_direct,'_compile',direct.compile_module_whole_source):
            with self.assertRaisesRegex(python_direct.PythonDirectUnsupported,'roundtrip changed'):vm.execute('X=1;')
        self.assertEqual(vm.variables,{})

    def test_changed_parse_tree_rejected_before_execution(self):
        real=ast.parse
        def change(*args,**kwargs):
            tree=real(*args,**kwargs)
            for node in ast.walk(tree):
                if type(node) is ast.Constant and node.value=='x':node.value='z'
            return tree
        vm=Interpreter()
        with patch.object(ast,'parse',change),patch.object(python_direct,'_compile',direct.compile_module_whole_source):
            with self.assertRaisesRegex(python_direct.PythonDirectUnsupported,'roundtrip changed'):vm.execute('X=1;')
        self.assertEqual(vm.variables,{})

    def test_code_positions_match_direct_ast_after_roundtrip(self):
        import builtins
        def signature(code):
            locations=tuple(code.co_positions()) if hasattr(code,'co_positions') else tuple(code.co_lines())
            return code.co_code,locations,tuple(signature(x) if type(x) is types.CodeType else x for x in code.co_consts)
        for source in ('R=1+2*3;', 'T=New ValueList;For I=0 To 3 Do T.Add(I);EndDo;R=T.Get(1).Value;',
                       'Function F(Val N) If N=0 Then Return 1;Else Return N*F(N-1);EndIf;EndFunction;R=F(3);'):
            outputs=[]
            for compiler,old_constants in ((direct.compile_module,True),(direct.compile_module,False),(direct.compile_module_whole_source,False)):
                captured=[]
                def record(tree,*args,**kwargs):
                    code=builtins.compile(tree,*args,**kwargs);captured.append(signature(code));return code
                vm=Interpreter()
                with patch.object(direct,'compile',record,create=True),patch.object(python_direct,'_compile',compiler):
                    if old_constants:
                        with patch.object(direct.Emitter,'const',lambda self,value,token:self.node(ast.Constant,token,value=value)):
                            vm.execute(source,'positions.bsl')
                    else:vm.execute(source,'positions.bsl')
                self.assertEqual(len(captured),1);outputs.append(captured[0]);vm.close()
            self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[1],outputs[2])

    def test_real_source_and_ast_denial_before_effects(self):
        for policy in ('source','ast','none','fragment','mutate'):
            script=r'''
import ast,sys
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.direct import python_direct
from yadinassi.execution.codegen import experimental_direct_ast as direct
policy=sys.argv[1];events=[]
def check(value):
    if not value:raise AssertionError('audit contract mismatch')
def hook(event,args):
    if event!='compile':return
    events.append((type(args[0]).__name__,args[1]))
    if policy=='mutate' and isinstance(args[0],ast.Module):
        for node in ast.walk(args[0]):
            if type(node) is ast.Constant and node.value=='x':node.value='changed'
    if ((policy=='source' and args[1]=='probe.bsl') or
        (policy=='ast' and isinstance(args[0],ast.Module)) or
        (policy=='fragment' and args[0]==b'_constants[0]')):
        raise RuntimeError('audit denied')
vm=Interpreter()
vm.execute('Warm=0;')
vm=Interpreter()
sys.addaudithook(hook)
with patch.object(python_direct,'_compile',direct.compile_module_whole_source):
    for _ in range(2):
        events.clear()
        try:vm.execute('X=1;Y=X+1;','probe.bsl')
        except RuntimeError as error:
            check(str(error)=='audit denied' and policy in ('source','ast'))
            check(not vm.variables)
        else:
            check(policy in ('none','fragment','mutate'))
            check(vm.variables['y']==2)
            if policy=='mutate':check('x' not in vm.variables and vm.variables['changed']==1)
        expected=[('bytes','probe.bsl')]
        if policy!='source':expected.append(('Module',None))
        check(events==expected)
'''
            with self.subTest(policy=policy):
                subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',script,policy],check=True)

class DefaultDirectCompileTests(unittest.TestCase):
    def setUp(self):
        self.vm=Interpreter()
        self.addCleanup(self.vm.close)

    def test_prepare_execute_eval_and_runtime_error_do_not_roundtrip(self):
        with patch.object(ast,'unparse',side_effect=AssertionError('no automatic unparse')):
            plan=self.vm.prepare('R=1;')
            self.assertEqual(plan._plan._research_roundtrip_visits,0)
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
        with patch.object(direct,'compile',create=True,side_effect=error) as compile_tree, \
             patch.object(direct,'_source_roundtrip',wraps=direct._source_roundtrip) as audit:
            with self.assertRaises(TypeError) as observed:
                self.vm.execute(source)
        self.assertIs(observed.exception,error)
        compile_tree.assert_called_once()
        audit.assert_called_once()
        self.assertEqual(self.vm.variables,{})

    def test_opted_in_public_python_extensions_keep_source_audit(self):
        vm=Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        with patch.object(direct,'_source_roundtrip',wraps=direct._source_roundtrip) as audit:
            vm.execute('R=1; Execute("R=R+1;"); R=Eval("R+2");')
        self.assertEqual(vm.variables['r'],4)
        self.assertEqual(audit.call_count,3)
