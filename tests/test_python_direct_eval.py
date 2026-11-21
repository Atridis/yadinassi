import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import UnsupportedNakedSyntax

class DirectEvalTests(unittest.TestCase):
    def test_source_ast_prepared_live_locals_and_module(self):
        from yadinassi.syntax.parser import parse
        source='Var M;M=2;Function F(A) B=4;Return Eval("A+B+M");EndFunction R=F(3);'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['r'],9)

    def test_live_byref_and_aliasing(self):
        vm=Interpreter();vm.execute('Function Change(X) X=X+1;Return X;EndFunction Function F() X=4;A=New Array;A.Add(2);R=Вычислить("Change(X)");Eval("A.Set(0,3)");Return X+A[0];EndFunction R=F();')
        self.assertEqual(vm.variables['r'],8)

    def test_complete_parse_and_unknown_constructor_before_effects(self):
        for text in ('Effect();Effect()','Effect() garbage','Effect()+New UnknownConstructor'):
            vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1) or 1)
            try:vm.execute('Eval("'+text+'");')
            except Exception:pass
            else:self.fail('invalid expression accepted')
            self.assertEqual(effects,[])

    def test_custom_override_and_argument_mutation(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Eval',lambda text:'custom')
        self.assertEqual(vm.execute('Eval("1+2");'),'custom')
        vm=Interpreter(allow_extensions=True);original=vm.functions['eval'];effects=[]
        def mutate():original.function=lambda text:effects.append(text);return '1'
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('Eval(Mutate());')
        self.assertEqual(effects,[])

    def test_revocation_and_retained_reference(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Close',lambda:vm.close() or '1')
        with self.assertRaises(BoundaryViolation):vm.execute('Eval(Close());')
        vm=Interpreter(allow_extensions=True);refs=[]
        vm.register_function('Capture',lambda x:refs.append(x) or 1)
        vm.functions['capture'].reference_parameters=frozenset((0,))
        vm.execute('X=2;Eval("Capture(X)");')
        with self.assertRaises(BoundaryViolation):refs[0].get()

    def test_arity_omission_and_limits(self):
        for text in ('Eval()','Eval(Effect(),Effect())','Eval(,)'):
            vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1))
            vm.execute('Try '+text+';Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(effects,[])
        vm=Interpreter();self.assertEqual(vm.execute('Eval(12)'),Decimal(12))
        vm.execute('Try Eval(Undefined);Except Caught=True;EndTry;');self.assertTrue(vm.variables['caught'])
        vm=Interpreter();vm.variables['s']='1'*65537
        vm.execute('Try Eval(S);Except Caught=True;EndTry;');self.assertTrue(vm.variables['caught'])
        vm=Interpreter();vm.execute('S="Eval(S)";Try Eval(S);Except Caught=True;EndTry;R=Eval("1");')
        self.assertTrue(vm.variables['caught']);self.assertEqual(vm.variables['r'],1)

    def test_diagnostic_context_preserves_description(self):
        vm=Interpreter();vm.execute('Try X=1/0;Except R=Eval("ErrorDescription()");S=ErrorDescription();EndTry;')
        self.assertIn('Деление на ноль',vm.variables['r']);self.assertEqual(vm.variables['r'],vm.variables['s'])
        vm=Interpreter();vm.execute('Function H() Try Raise "inner";Except EndTry;Return 1;EndFunction Try Raise "outer";Except Eval("H()");R=ErrorDescription();EndTry;')
        self.assertEqual(vm.variables['r'],'')

    def test_server_and_nocontext_local_scope(self):
        for directive in ('AtServer','AtServerNoContext','AtClientAtServerNoContext'):
            vm=Interpreter(compilation_profile='managed-thick-file')
            vm.execute('&'+directive+'\nFunction F(Val A) B=4;Return Eval("A+B");EndFunction R=F(3);')
            self.assertEqual(vm.variables['r'],7)

    def test_depth_shared_across_dual_calls(self):
        vm=Interpreter(compilation_profile='managed-thick-file')
        vm.execute('&AtClientAtServerNoContext\nFunction D(Val N) If N=0 Then Return 0;EndIf;Return Eval("D(N-1)");EndFunction Try R=Eval("D(20)");Except Caught=True;EndTry;S=Eval("D(2)");')
        self.assertTrue(vm.variables['caught']);self.assertEqual(vm.variables['s'],0)

class EvalPreparationReuseTests(unittest.TestCase):
    def test_reuse_preparation_not_values(self):
        from yadinassi.syntax import parser
        with patch.object(parser,'parse_expression',wraps=parser.parse_expression) as parse:
            vm=Interpreter();vm.execute('Function F() S=0;For I=1 To 20 Do S=Eval("S+1");EndDo;Return S;EndFunction R=F();')
        self.assertEqual(vm.variables['r'],20);self.assertEqual(parse.call_count,1)

    def test_cached_constructor_readmission_before_effects(self):
        from yadinassi import BSLError
        vm=Interpreter(allow_extensions=True);seen=[];vm.register_function('Effect',lambda x:seen.append(x))
        vm.register_function('Change',lambda:vm.register_type('Array',lambda:[]))
        with self.assertRaises(BSLError):vm.execute('Eval("Effect(New Array)");Change();Eval("Effect(New Array)");')
        self.assertEqual(len(seen),1)

    def test_entry_and_text_eviction_and_activation_isolation(self):
        from yadinassi.syntax import parser
        for expressions in ([str(i) for i in range(17)]+['0'],['1'+(' '*33000),'2'+(' '*33000),'1'+(' '*33000)]):
            vm=Interpreter();vm.variables['expressions']=expressions
            with patch.object(parser,'parse_expression',wraps=parser.parse_expression) as parse:
                vm.execute('For Each E In expressions Do R=Eval(E);EndDo;')
                self.assertEqual(parse.call_count,len(expressions))
                vm.execute('R=Eval("0");');self.assertEqual(parse.call_count,len(expressions)+1)

    def test_limits_are_checked_after_warmup(self):
        from yadinassi import BSLError
        vm=Interpreter(allow_extensions=True)
        with patch('yadinassi.runtime.EVAL_MAX_SOURCE',65536):
            def shrink():
                import yadinassi.runtime as runtime
                runtime.EVAL_MAX_SOURCE=1
            vm.register_function('Shrink',shrink)
            with self.assertRaisesRegex(BSLError,'предел текста'):vm.execute('S=0;S=Eval("S+1");Shrink();S=Eval("S+1");')
        self.assertEqual(vm.variables['s'],1)

    def test_retained_units_do_not_retain_owner_or_scope(self):
        import gc,weakref
        import yadinassi.execution.direct.python_direct_execute as fragments
        units=[];refs=[];original=fragments.FragmentScope.__init__
        def track(scope,*args):
            original(scope,*args);refs.extend((weakref.ref(scope),weakref.ref(scope.context)))
            units.extend(scope.context._eval_units.values())
        vm=Interpreter();ref=weakref.ref(vm)
        with patch.object(fragments.FragmentScope,'__init__',track):vm.execute('S=0;For I=1 To 3 Do S=Eval("S+1");EndDo;')
        vm.close();del vm;gc.collect()
        self.assertTrue(units);self.assertIsNone(ref());self.assertTrue(all(r() is None for r in refs))

    def test_cached_calls_reject_partial_persistent_replacement(self):
        from yadinassi import BSLError
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.execute('Function F() Return 1;EndFunction Function G() Return F();EndFunction')
        replacement=Interpreter();replacement.execute('Function F() Return 9;EndFunction')
        vm.register_function('Change',lambda:vm._direct_routine_modules.__setitem__('f',replacement._direct_routine_modules['f']))
        vm.register_function('Effect',lambda:seen.append('effect') or 0)
        with self.assertRaisesRegex(BSLError,'partially replaced'):
            vm.execute('R=Eval("Effect()+G()");Change();R=Eval("Effect()+G()");')
        self.assertEqual(seen,['effect'])
