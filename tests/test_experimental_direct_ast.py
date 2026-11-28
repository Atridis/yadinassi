"""Independent direct-codegen regressions; retired text oracle removed.

Broad language matrices live in the dedicated public direct-runtime suites.
These tests retain compile structure, source ownership, diagnostics and boundaries.
"""
import ast
import subprocess
import sys
import unittest
from decimal import Decimal
from yadinassi import Interpreter, BSLError
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse

class DirectASTResearchTests(unittest.TestCase):
    def test_prepared_owns_source_snapshot_but_reads_live_bindings(self):
        import gc,weakref
        from dataclasses import replace
        nodes=parse('X=1;\nY=1/0;','owned.bsl');ref=weakref.ref(nodes[0])
        vm=Interpreter(allow_extensions=True);plan=vm.prepare_program(nodes)
        nodes[0].value.value=Decimal(99)
        nodes[0].token=replace(nodes[0].token,source='changed.bsl',line=70)
        nodes.clear();gc.collect();self.assertIsNone(ref())
        with self.assertRaises(Exception) as caught:vm.execute_prepared(plan)
        self.assertEqual(vm.variables['x'],1)
        self.assertEqual((caught.exception.source,caught.exception.line),('owned.bsl',2))
        vm=Interpreter(allow_extensions=True);vm.variables['x']=Decimal(1);vm.register_function('Read',lambda:2)
        plan=vm.prepare('X=X+Read();X;')
        self.assertEqual(vm.execute_prepared(plan),3)
        vm.register_function('Read',lambda:3)
        self.assertEqual(vm.execute_prepared(plan),6)

    def test_conditional_local_declaration_is_lexical(self):
        for flag, expected in (('False', 3), ('True', 2)):
            source=('Var X;Function F(Val C) If C Then Var X;X=2;Else X=3;EndIf;'
                    'Return X;EndFunction;X=9;R=F('+flag+');')
            vm=Interpreter()
            self.addCleanup(vm.close)
            vm.execute(source)
            self.assertEqual(vm.variables, {'x': 9, 'r': expected})

    def test_default_ast_and_extension_filename_audit(self):
        self.child(r"""
import ast
import sys
from yadinassi import Interpreter
direct=Interpreter()
external=Interpreter(allow_extensions=True)
for vm in (direct,external):
    vm.execute('X=1;','warm.bsl');vm.variables.clear()
deny_ast=False
def deny(event,args):
    if event=='exec' and args[0].co_filename=='blocked.bsl':
        raise RuntimeError('filename denied')
    if event=='compile' and deny_ast and isinstance(args[0],ast.Module):
        raise RuntimeError('AST denied')
sys.addaudithook(deny)
for vm in (direct,external):
    try:vm.execute('X=1;','blocked.bsl')
    except RuntimeError as error:
        if str(error)!='filename denied' or vm.variables:raise AssertionError('bad filename denial')
    else:raise AssertionError('compiler filename gate absent')
deny_ast=True
try:direct.execute('X=1;','direct.bsl')
except RuntimeError as error:
    if str(error)!='AST denied' or direct.variables:raise AssertionError('bad AST denial')
else:raise AssertionError('bare AST gate absent')
""")

    def test_lowering_counts_linear_for_wide_and_nested_inputs(self):
        for shape in ('nested', 'wide'):
            counts=[]
            for size in (8,16,32):
                source=('R='+'-'.join(['1']*size)+';' if shape=='nested'
                        else ';'.join('X%d=%d'%(i,i) for i in range(size))+';')
                vm=Interpreter()
                self.addCleanup(vm.close)
                plan=vm.prepare(source)
                counts.append(sum(1 for _ in ast.walk(ast.parse(plan._plan.generated_source))))
            self.assertGreater(counts[1],counts[0])
            self.assertLessEqual(counts[2],2*counts[1]+2)

    def test_no_research_caps_and_unsupported_fail_before_effects(self):
        vm=Interpreter();vm.execute('R='+'-'.join(['1']*100)+';')
        self.assertEqual(vm.variables['r'],-98)
        vm=Interpreter();vm.execute('\n'*50000+'X=1;')
        self.assertEqual(vm.variables['x'],1)
        vm.execute('X=1;'*3500)
        self.assertEqual(vm.variables['x'],1)
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
        for source,expected in cases:
            with self.subTest(source=source):
                vm=Interpreter();self.addCleanup(vm.close)
                vm.execute(source)
                for name,value in expected.items():self.assertEqual(vm.variables[name],value)

    def test_errors_have_independent_source_position_and_partial_state(self):
        for rhs in ('1/0','Missing'):
            vm=Interpreter();self.addCleanup(vm.close)
            with self.subTest(rhs=rhs):
                with self.assertRaises(BSLError) as caught:vm.execute('X=1;\nY='+rhs+';','probe.bsl')
            self.assertEqual(caught.exception.source,'probe.bsl');self.assertEqual(caught.exception.line,2)
            self.assertEqual(vm.variables,{'x':Decimal(1)})

    def test_owner_close_before_following_effect(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);vm.register_function('Stop',vm.close)
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
        events=[]
        def trace(frame,event,arg):
            if event=='exception' and frame.f_code.co_filename=='trace.bsl':events.append(frame.f_lineno)
            return trace
        old=sys.gettrace();sys.settrace(trace)
        try:
            with self.assertRaises(BSLError):Interpreter().execute('X=1;\nY=1/0;','trace.bsl')
        finally:sys.settrace(old)
        self.assertTrue(events);self.assertTrue(all(line==2 for line in events))

    def test_constant_fold_source_visitation(self):
        class Out:
            def __init__(self):
                self.messages=[]
            def __call__(self, message):
                self.messages.append(message)
        output=Out()
        vm=Interpreter(output=output)
        self.addCleanup(vm.close)
        source='If True Then Message("a"+1);Else Message("b"+2);EndIf;'
        plan=vm.prepare(source)
        self.assertEqual(output.messages,[])
        self.assertIn("'a'",plan._plan.generated_source)
        self.assertIn("'b'",plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual(output.messages,['a1'])

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

    def test_forwarded_host_reference_reads_only_when_requested(self):
        from yadinassi.types.values import HostFunction, Reference

        for call in ('Host(A, Later());', 'Procedure F(A) Host(A, Later()); EndProcedure; F(A);'):
            with self.subTest(call=call):
                vm = Interpreter(allow_extensions=True)
                self.addCleanup(vm.close)
                values = [Decimal(1)]
                events = []

                def getter():
                    events.append('get')
                    return values[0]

                def later():
                    events.append('later')
                    values[0] = Decimal(2)

                def host(ref, ignored):
                    events.append('host')
                    events.append(ref.get())
                    ref.set(Decimal(3))
                    events.append(ref.get())

                vm.variables['a'] = Reference(getter, lambda value: values.__setitem__(0, value))
                vm.register_function('Later', later)
                vm.functions['host'] = HostFunction(
                    'Host', host, reference_parameters=(0,), returns_value=False)
                vm.execute(call)
                self.assertEqual(events, ['later', 'host', 'get', Decimal(2), 'get', Decimal(3)])
                self.assertEqual(values[0], Decimal(3))
