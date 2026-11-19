"""Independent direct-codegen regressions; retired text oracle removed.

Broad language matrices live in the dedicated public direct-runtime suites.
These tests retain compile structure, source ownership, diagnostics and boundaries.
"""
import subprocess
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.execution.direct import python_direct
from yadinassi.execution.codegen import experimental_direct_ast as direct
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse

class DirectASTResearchTests(unittest.TestCase):
    def test_prepared_owns_source_snapshot_but_reads_live_bindings(self):
        import gc,weakref
        from dataclasses import replace
        nodes=parse('X=1;\nY=1/0;','owned.bsl');ref=weakref.ref(nodes[0])
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter(allow_extensions=True);plan=vm.prepare_program(nodes)
        nodes[0].value.value=Decimal(99)
        nodes[0].token=replace(nodes[0].token,source='changed.bsl',line=70)
        nodes.clear();gc.collect();self.assertIsNone(ref())
        with self.assertRaises(Exception) as caught:vm.execute_prepared(plan)
        self.assertEqual(vm.variables['x'],1)
        self.assertEqual((caught.exception.source,caught.exception.line),('owned.bsl',2))
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter(allow_extensions=True);vm.variables['x']=Decimal(1);vm.register_function('Read',lambda:2)
            plan=vm.prepare('X=X+Read();X;')
        self.assertEqual(vm.execute_prepared(plan),3)
        vm.register_function('Read',lambda:3)
        self.assertEqual(vm.execute_prepared(plan),6)

    def test_conditional_local_declaration_shadow_rejected_before_effects(self):
        for flag in ('False','True'):
            source='Var X;Function F(Val C) If C Then Var X;X=2;Else X=3;EndIf;Return X;EndFunction;X=9;R=F('+flag+');'
            for compiler in (direct.compile_module,direct.compile_module_whole_source):
                vm=Interpreter()
                with patch.object(python_direct,'_compile',compiler):
                    with self.assertRaisesRegex(PythonDirectUnsupported,'conditional local Var shadowing module storage'):vm.execute(source)
                self.assertEqual(vm.variables,{})

    def test_one_real_compile_per_call_and_actual_audit_denial(self):
        self.child(r'''
import ast,sys
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.direct import python_direct
from yadinassi.execution.codegen.experimental_direct_ast import compile_module
python_direct._compile=compile_module
vm=Interpreter();vm.execute('X=1;','audit.bsl');events=[]
def observe(event,args):
    if event=='compile':events.append(args)
sys.addaudithook(observe)
for _ in range(2):
    events.clear();vm.execute('X=1;','audit.bsl')
    if len(events)!=1 or not isinstance(events[0][0],ast.Module):raise AssertionError('not one actual AST compile')
vm.variables.clear()
def deny(event,args):
    if event=='compile' and isinstance(args[0],ast.Module):raise RuntimeError('executable AST denied')
sys.addaudithook(deny)
try:vm.execute('X=1;','audit.bsl')
except RuntimeError as error:
    if str(error)!='executable AST denied' or vm.variables:raise AssertionError('denial after effects')
else:raise AssertionError('compiler policy bypassed')
''')

    def test_filename_only_audit_policy_is_an_explicit_migration_blocker(self):
        # Pure AST alone lacks the filename gate retained by the default source lane.
        self.child(r"""
import sys
from yadinassi import Interpreter
from yadinassi.execution.direct import python_direct
from yadinassi.execution.codegen.experimental_direct_ast import compile_module
vm=Interpreter();vm.execute('X=1;','warm.bsl');vm.variables.clear()
def deny_filename(event,args):
    if event=='compile' and args[1]=='blocked.bsl':raise RuntimeError('filename denied')
sys.addaudithook(deny_filename)
try:vm.execute('X=1;','blocked.bsl')
except RuntimeError:
    if vm.variables:raise AssertionError('baseline effects before denial')
else:raise AssertionError('baseline filename gate absent')
python_direct._compile=compile_module
vm.execute('X=1;','blocked.bsl')
if vm.variables.get('x')!=1:raise AssertionError('expected migration incompatibility not demonstrated')
""")

    def test_lowering_counts_linear_for_wide_and_nested_inputs(self):
        counters={}
        with patch.object(python_direct,'_compile',direct.compile_module):
            for shape in ('nested','wide'):
                for size in (8,16,32):
                    source='R='+'-'.join(['1']*size)+';' if shape=='nested' else ';'.join('X%d=%d'%(i,i) for i in range(size))+';'
                    plan=Interpreter().prepare(source)
                    counters[shape,size]=plan._plan._research_lowering_counts
                a=counters[shape,16];b=counters[shape,32]
                self.assertLessEqual(b[1],2*a[1]+2)
                self.assertLessEqual(b[2],2*a[2]+2)
        self.counters=counters

    def test_no_research_caps_and_unsupported_fail_before_effects(self):
        with patch.object(python_direct,'_compile',direct.compile_module):
            vm=Interpreter();vm.execute('R='+'-'.join(['1']*100)+';')
            self.assertEqual(vm.variables['r'],-98)
            vm=Interpreter();vm.execute('\n'*50000+'X=1;')
            self.assertEqual(vm.variables['x'],1)
            self.assertGreater(direct._bounds(parse('X=1;'*3500))[0],10000)
            vm=Interpreter()
            with self.assertRaises(PythonDirectUnsupported):vm.execute('X=1;A=New UnsupportedResearchConstructor;')
            self.assertEqual(vm.variables,{})

    def child(self,code):
        result=subprocess.run([sys.executable,*(['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []),'-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_independent_scalar_and_control_values(self):
        cases=[
            ('X=0;For I=0 To 10 Do X=X+I;EndDo;R=X;',{'x':55,'r':55,'i':11}),
            ('X=0;While X<3 Do X=X+1;EndDo;',{'x':3}),
            ('X=0;For I=0 To 9 Do If I=2 Then Continue;EndIf;If I=5 Then Break;EndIf;X=X+I;EndDo;',{'x':8,'i':5}),
            ('Var X;X=1;R=(X+2)*3-4;',{'x':1,'r':5}),
            ('X=True AND False OR True;Y=NOT 0;',{'x':True,'y':True}),
            ('X=?(True,2,1/0);',{'x':2}),
            ('Function F(Val N) If N=0 Then Return 1;Else Return N*F(N-1);EndIf;EndFunction R=F(5);',{'r':120}),
        ]
        for compiler in (direct.compile_module,direct.compile_module_whole_source):
            for source,expected in cases:
                with self.subTest(source=source,compiler=compiler.__name__):
                    vm=Interpreter();self.addCleanup(vm.close)
                    with patch.object(python_direct,'_compile',compiler):vm.execute(source)
                    for name,value in expected.items():self.assertEqual(vm.variables[name],value)

    def test_errors_have_independent_source_position_and_partial_state(self):
        for compiler in (direct.compile_module,direct.compile_module_whole_source):
            for rhs in ('1/0','Missing'):
                vm=Interpreter();self.addCleanup(vm.close)
                with self.subTest(rhs=rhs),patch.object(python_direct,'_compile',compiler):
                    with self.assertRaises(BSLError) as caught:vm.execute('X=1;\nY='+rhs+';','probe.bsl')
                self.assertEqual(caught.exception.source,'probe.bsl');self.assertEqual(caught.exception.line,2)
                self.assertEqual(vm.variables,{'x':Decimal(1)})

    def test_owner_close_before_following_effect(self):
        for compiler in (direct.compile_module,direct.compile_module_whole_source):
            vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);vm.register_function('Stop',vm.close)
            with patch.object(python_direct,'_compile',compiler):
                with self.assertRaises(BoundaryViolation):vm.execute('X=1;Stop();Y=2;')
            self.assertEqual(vm.variables.get('x'),1);self.assertNotIn('y',vm.variables)

    def test_policy_replacement_before_following_effect(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        vm.register_function('Stop',lambda:setattr(vm,'_configuration_runtime',object()))
        with self.assertRaises(BoundaryViolation):vm.execute('X=1;Stop();Y=2;')
        self.assertEqual(vm.variables.get('x'),1);self.assertNotIn('y',vm.variables)

    def test_persistent_routine_error_keeps_definition_location(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('Function F(Val N) Try Return 1/N;Except Raise "persisted";EndTry;EndFunction;','definition.bsl')
        vm.execute('Try R=F(0);Except E=ErrorInfo();EndTry;','caller.bsl')
        info=vm.variables['e']
        self.assertEqual(info.description,'persisted');self.assertEqual(info.module_name,'definition.bsl');self.assertEqual(info.line_number,1)
        vm.execute_prepared(vm.prepare('R=F(2);','prepared-caller.bsl'))
        self.assertEqual(vm.variables['r'],Decimal('0.5'))

    def test_procedure_value_and_malformed_loop_controls(self):
        from yadinassi.syntax import ast as bsl
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
        vm.register_function('P',lambda:seen.append('called'),returns_value=False)
        vm.execute('P();');self.assertEqual(seen,['called'])
        with self.assertRaises(BSLError):vm.execute('X=P();')
        self.assertEqual(seen,['called']);self.assertNotIn('x',vm.variables)
        for kind in (bsl.Break,bsl.Continue):
            nodes=parse('X=1;');nodes.append(kind(nodes[0].token));vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
            with self.assertRaisesRegex(PythonDirectUnsupported,'outside a loop'):vm.execute_program(nodes)
            self.assertEqual(vm.variables,{})

    def test_native_exception_trace_has_bsl_line(self):
        for compiler in (direct.compile_module,direct.compile_module_whole_source):
            events=[]
            def trace(frame,event,arg):
                if event=='exception' and frame.f_code.co_filename=='trace.bsl':events.append(frame.f_lineno)
                return trace
            old=sys.gettrace();sys.settrace(trace)
            try:
                with patch.object(python_direct,'_compile',compiler):
                    with self.assertRaises(BSLError):Interpreter().execute('X=1;\nY=1/0;','trace.bsl')
            finally:sys.settrace(old)
            self.assertTrue(events);self.assertTrue(all(line==2 for line in events))

    def test_constant_fold_source_visitation(self):
        from yadinassi.execution.codegen import experimental_naked_scalar_semantics as scalar
        original=scalar.concatenate
        for source in ('If True Then X="a"+1;Else X="b"+2;EndIf;', 'While ("a"+1) Do X="b"+2;EndDo;', 'Try X="a"+1;Except X="b"+2;EndTry;'):
            for compiler in (direct.compile_module,direct.compile_module_whole_source):
                seen=[]
                def observe(left,right):seen.append(left);return original(left,right)
                with patch.object(scalar,'concatenate',observe),patch.object(python_direct,'_compile',compiler):Interpreter().prepare(source)
                self.assertEqual(seen,['a','b'])

    def test_operator_temporary_finalizer_and_close(self):
        # Exact operand-temporary lifetime was an implementation-only comparison
        # against the retired text emitter. Require one release and fatal close,
        # not an invented native-BSL destructor schedule.
        for source in ('X=Make()+1;Y=2;','A=1;X=A+Make();Y=2;'):
            for close in (False,True):
                with self.subTest(source=source,close=close):
                    vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
                    class Value:
                        def __add__(self,other):return 7
                        def __radd__(self,other):return 7
                        def __del__(self):
                            seen.append('released')
                            if close:vm.close()
                    vm.register_function('Make',Value)
                    if close:
                        with self.assertRaises(BoundaryViolation):vm.execute(source)
                    else:
                        vm.execute(source);self.assertEqual(vm.variables['x'],7);self.assertEqual(vm.variables['y'],2)
                    self.assertEqual(seen,['released'])

    def test_index_key_finalizer_released_once(self):
        for close in (False,True):
            vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);vm.variables['d']={'k':Decimal(9)};seen=[]
            class Key(str):
                def __del__(self):
                    seen.append('released')
                    if close:vm.close()
            vm.register_function('Make',lambda:Key('k'))
            if close:
                with self.assertRaises(BoundaryViolation):vm.execute('X=D[Make()];Y=2;')
            else:
                vm.execute('X=D[Make()];Y=2;');self.assertEqual(vm.variables['x'],9);self.assertEqual(vm.variables['y'],2)
            self.assertEqual(seen,['released'])

    def test_host_reference_getter_errors_and_revocation(self):
        from yadinassi.types.values import HostFunction,Reference
        for mode in ('raise','close','normal'):
            vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);events=[]
            def get():
                events.append('get')
                if mode=='raise':raise ValueError('getter failed')
                if mode=='close':vm.close()
                return Decimal(2)
            vm.variables['a']=Reference(get,lambda value:events.append(('set',value)))
            vm.functions['host']=HostFunction('Host',lambda ref:events.append(('called',ref.get())),reference_parameters=(0,),returns_value=False)
            source='Procedure F(A)\n Host(A);\nEndProcedure;\nTry F(A);Except E=ErrorInfo();EndTry;Y=2;'
            if mode=='close':
                with self.assertRaises(BoundaryViolation):vm.execute(source,'getter.bsl')
                self.assertNotIn('y',vm.variables);self.assertNotIn('e',vm.variables)
            else:
                vm.execute(source,'getter.bsl');self.assertEqual(vm.variables['y'],2)
                if mode=='raise':
                    self.assertIn('e',vm.variables)
                    self.assertIn('getter failed',vm.variables['e'].description)
            self.assertEqual(events,['get',('called',Decimal(2))] if mode=='normal' else ['get'])
