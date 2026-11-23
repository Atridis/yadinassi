import cProfile
import unittest
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError

class NamespaceTests(unittest.TestCase):
    def run_case(self, source, expected):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);events=[]
        vm.register_function('Get', lambda: lambda: events.append('unauthorized'))
        vm.execute(source)
        self.assertEqual(vm.variables['r'], expected)
        self.assertEqual(events, [])

    def test_assignment_does_not_replace_function(self):
        for assignment in ('7', 'Get()'):
            self.run_case('Function F() Return 1;EndFunction F=' + assignment + ';r=F();', 1)

    def test_local_variable_does_not_replace_function(self):
        self.run_case('Function F() Return 1;EndFunction Function G() F=7;Return F();EndFunction r=G();', 1)

    def test_variable_value_still_accessible(self):
        self.run_case('Function F() Return 1;EndFunction F=7;r=F+F();', 8)

    def test_prepared_value_lookup_distinguishes_live_routine_from_storage(self):
        vm=Interpreter();self.addCleanup(vm.close)
        prepared=vm.prepare('F;')
        with self.assertRaisesRegex(BSLRuntimeError, 'не определена: F'):
            vm.execute_prepared(prepared)
        vm.execute('Function F() Return 1; EndFunction')
        with self.assertRaisesRegex(BSLRuntimeError, 'необходимо вызвать: F'):
            vm.execute_prepared(prepared)
        vm.execute('F=7;')
        profile=cProfile.Profile()
        self.assertEqual(profile.runcall(vm.execute_prepared, prepared), 7)
        self.assertFalse(any(getattr(entry.code, 'co_name', '') == 'missing_value'
                             for entry in profile.getstats()))
        self.assertEqual(vm.execute('F()'), 1)
        del vm.variables['f']
        with self.assertRaisesRegex(BSLRuntimeError, 'необходимо вызвать: F'):
            vm.execute_prepared(prepared)

    def test_recursion(self):
        self.run_case('Function F(Val n) If n=0 Then Return 0;EndIf;Return F(n-1)+1;EndFunction r=F(10);', 10)

    def test_function_value_is_not_exposed(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaisesRegex(BSLRuntimeError, 'Процедуру или функцию необходимо вызвать: F'):
            vm.execute('Function F() Return 1;EndFunction r=F;')

    def test_procedure_value_and_invalid_arity_precede_effects(self):
        for source in ('Procedure F(x) EndProcedure r=F(Host());', 'Procedure F() EndProcedure F(Host());', 'Procedure F(x,y) EndProcedure F(Host());'):
            with self.subTest(source=source):
                vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);events=[]
                vm.register_function('Host', lambda: events.append('arg'))
                with self.assertRaises(BSLRuntimeError): vm.execute(source)
                self.assertEqual(events, [])

    def test_grouped_routine_preserves_reference(self):
        self.run_case('Procedure F(x) x=7;EndProcedure r=0;((F))(r);',7)

    def test_grouped_routine_and_actual_alias_shared_prepared_storage(self):
        source=('Procedure F(A, B) A=7; B=B+1; EndProcedure '
                'R=0; ((F))(((R)), (R));')
        for extensions in (False,True):
            with self.subTest(allow_extensions=extensions):
                vm=Interpreter(allow_extensions=extensions)
                self.addCleanup(vm.close)
                plan=vm.prepare(source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'],8)

    def test_grouped_val_call_does_not_box_module_slot(self):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare('Function F(Val X) Return X; EndFunction R=7; Result=((F))((R));')
        names=plan._plan.function.__code__.co_names
        self.assertNotIn('_NativeCell',names)
        self.assertNotIn('_adapt_native_cell',names)
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['result']),(7,7))
