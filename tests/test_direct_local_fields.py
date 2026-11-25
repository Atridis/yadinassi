import ast
import unittest
from decimal import Decimal as D
from yadinassi import Interpreter


def native_field_reads(source, key):
    return sum(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == '_native_dict_get'
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == key
        for node in ast.walk(ast.parse(source))
    )


class LocalFieldsTests(unittest.TestCase):
    def test_local_value_function_has_no_operator_dispatch_or_per_iteration_check(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('Function Step(Val x) Return x+2;EndFunction '
                          'R=0;For I=1 To 4 Do R=R+Step(I);EndDo;R;')
        loop = next(n for n in ast.walk(ast.parse(plan._plan.generated_source)) if isinstance(n,ast.For))
        source = ast.unparse(loop)
        self.assertNotIn('_native_add', source)
        self.assertNotIn('_concatenate', source)
        self.assertNotIn('_context._check', source)
        self.assertEqual(vm.execute_prepared(plan), D(18))

    def test_unresolved_addition_follows_runtime_left_type(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('R=Left+Right;')
        # Native numbers.out observes string-left addition with a number.
        for left, right, expected in (('value: ', D(2), 'value: 2'),
                                       (D(40), D(2), D(42)),
                                       ('\ud83d', '\ude00', '😀')):
            with self.subTest(left=repr(left)):
                vm.variables.update(left=left, right=right)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'], expected)
        self.assertNotIn('_context._check', plan._plan.generated_source)

    def test_field_loop_uses_range_and_native_add_together(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('S=New Structure("Value",0);R=0;'
                          'For I=0 To 63 Do S.Value=I;R=R+S.Value;EndDo;R;')
        generated = plan._plan.generated_source
        self.assertIn(' in range(0, 64):', generated)
        self.assertIn('_structure_set_known(', generated)
        self.assertEqual(native_field_reads(generated, 'value'), 1)
        self.assertNotIn('_structure_get_known', generated)
        self.assertNotIn('_context.get_member', generated)
        self.assertNotIn('resolve_set_member', generated)
        self.assertNotIn('_dynamic_depth', generated)
        self.assertEqual(vm.execute_prepared(plan), D(2016))

    def prepare(self, source, configure=None):
        vm=Interpreter(allow_extensions=configure is not None);self.addCleanup(vm.close)
        if configure:configure(vm)
        plan=vm.prepare(source)
        return vm,plan,plan._plan.generated_source

    def test_structure_fields_and_numeric_ops_are_direct_in_arbitrary_loop(self):
        vm,plan,source=self.prepare('Bag=New Structure("Amount,Title",0,"a");For Tick=1 To 7 Do Bag.Amount=Bag.Amount+Tick*2;EndDo;R=Bag.Amount;Text=Bag.Title+"b";')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'],D(56));self.assertEqual(vm.variables['text'],'ab')
        self.assertNotIn('resolve_set_member',source)
        self.assertNotIn("_context.get_member",source)
        self.assertIn('_structure_set_known',source)
        self.assertEqual(native_field_reads(source, 'amount'), 2)
        self.assertEqual(native_field_reads(source, 'title'), 1)
        self.assertNotIn('_structure_get_known', source)
        loop=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,(ast.For,ast.While)))
        self.assertNotIn('_publish_module',ast.unparse(loop))
        self.assertNotIn('_reload_module',ast.unparse(loop))
        self.assertTrue(any(isinstance(n,ast.BinOp) and isinstance(n.op,ast.Add) for n in ast.walk(loop)))

    def test_alias_and_nested_fields_retain_types(self):
        vm,plan,source=self.prepare('Child=New Structure("N",3);S=New Structure("Child",Child);Alias=S;Alias.Child.N=Alias.Child.N+2;R=S.Child.N;')
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(5))
        self.assertNotIn('_context.get_member',source)

    def test_unknown_call_kills_old_facts_but_fresh_structure_recovers(self):
        def configure(vm):
            def mutate():vm.variables['s']['N']='changed'
            vm.register_function('Mutate',mutate)
        vm,plan,source=self.prepare('S=New Structure("N",1);Before=S.N+1;Mutate();After=S.N+"2";Fresh=New Structure("N",7);R=Fresh.N+1;',configure)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['before'],D(2))
        self.assertEqual(vm.variables['after'],'changed2');self.assertEqual(vm.variables['r'],D(8))
        self.assertIn("_context.get_member",source)
        self.assertEqual(native_field_reads(source, 'n'), 3)
        self.assertNotIn('_structure_get_known', source)

    def test_loop_alias_changes_do_not_leave_false_numeric_facts(self):
        vm,plan,_=self.prepare('S=New Structure("N",1);T=New Structure("N",1);For I=1 To 2 Do S=T;EndDo;T.N="x";R=S.N;')
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],'x')

    def test_loop_field_type_changes_are_not_specialized_from_first_iteration(self):
        vm,plan,source=self.prepare(
            'S=New Structure("N",1); '
            'For I=1 To 2 Do R=S.N+2; If I=1 Then First=R; EndIf; S.N="x"; EndDo;')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['first'],D(3))
        self.assertEqual(vm.variables['r'],'x2')
        self.assertIn('_context.get_member',source)

    def test_dynamic_operand_keeps_owner_revocation_boundary(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        vm,plan,_=self.prepare('S=New Structure("N",1);S.N=CloseOwner();After=1;',lambda vm:vm.register_function('CloseOwner',lambda:vm.close() or D(2)))
        with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        self.assertNotIn('after',vm.variables)

    def test_missing_fields_casefold_and_dynamic_concat(self):
        vm,plan,_=self.prepare('S=New Structure("MiXeD",2);S.mixed=S.MIXED+1;R=S.Mixed;')
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(3))
        with self.assertRaisesRegex(Exception,'Свойство структуры не найдено'):
            vm.execute('S=New Structure("N",1);R=S.Missing;')

    def test_known_string_number_uses_concat_not_native_add(self):
        vm,plan,source=self.prepare('S=New Structure("Text,N","x",2);R=S.Text+S.N;')
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],'x2')
        self.assertIn('_concatenate',source)
        self.assertNotIn('_native_add',source)

    def test_scalar_facts_recover_after_opaque_call(self):
        vm,plan,source=self.prepare('Host();A=3;B=4;R=A+B;',lambda vm:vm.register_function('Host',lambda:None))
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(7))
        self.assertNotIn('_native_add',source)
