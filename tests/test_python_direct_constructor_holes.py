"""Native direct collection constructors reject unsupported syntactic holes."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,BSLError
from yadinassi.syntax.parser import parse
from yadinassi.python_direct import PythonDirectUnsupported

class DirectConstructorHolesTests(unittest.TestCase):
    def test_all_constructors_positions_reject_before_effects(self):
        for backend in ('python-direct',):
            for constructor in ('Array','Массив','Map','Соответствие','Structure','Структура'):
                for arguments in (',Effect()', 'Effect(),', 'Effect(),,Effect()', ','):
                    vm=Interpreter(execution_backend=backend);seen=[]
                    vm.register_function('Effect',lambda:seen.append('effect') or 1)
                    with self.subTest(backend=backend,constructor=constructor,args=arguments),self.assertRaisesRegex(BSLError,'Пропуск аргументов'):
                        vm.execute('New '+constructor+'('+arguments+');')
                    self.assertEqual(seen,[])

    def test_source_ast_prepared_execute_eval_runtime_rejection_no_vm(self):
        for route in ('source','ast','prepared','execute','eval'):
            vm=Interpreter();seen=[];vm.register_function('Effect',lambda:seen.append('effect') or 1)
            code='New Array(,Effect());'
            with self.subTest(route=route),patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')),self.assertRaisesRegex(BSLError,'Пропуск аргументов'):
                if route=='source':vm.execute(code)
                elif route=='ast':vm.execute_program(parse(code))
                elif route=='prepared':vm.execute_prepared(vm.prepare(code))
                elif route=='execute':vm.execute('Execute("'+code+'");')
                else:vm.execute('Eval("New Array(,Effect())");')
            self.assertEqual(seen,[])

    def test_explicit_undefined_is_evaluated_not_a_hole(self):
        for backend in ('python-direct',):
            for constructor in ('Array','Map','Structure'):
                vm=Interpreter(execution_backend=backend);seen=[]
                vm.register_function('Effect',lambda:seen.append('effect') or 1)
                with self.subTest(backend=backend,constructor=constructor),self.assertRaises(BSLError):
                    vm.execute('New '+constructor+'(Undefined,Effect());')
                self.assertEqual(seen,['effect'])
            vm.execute('S=New Structure("X",Undefined);');self.assertIsNone(vm.execute('S.X'))
            with self.assertRaisesRegex(BSLError,'Пропуск аргументов'):vm.execute('New Structure("X",);')

    def test_dead_branch_and_catchable_reached_error(self):
        vm=Interpreter();seen=[];vm.register_function('Effect',lambda:seen.append('effect'))
        vm.execute('If False Then New Array(,Effect());EndIf;Try New Map(,Effect());Except Caught=True;EndTry;')
        self.assertIs(vm.variables['caught'],True);self.assertEqual(seen,[])
        plan=vm.prepare('Try New Structure(,Effect());Except Caught=True;EndTry;')
        for _ in range(2):vm.execute_prepared(plan)
        self.assertEqual(seen,[])

    def test_registered_overrides_remain_rejected_without_host_effects(self):
        for constructor in ('Array','Map','Structure'):
            vm=Interpreter();seen=[]
            vm.register_type(constructor,lambda *args:seen.append(args))
            vm.register_function('Effect',lambda:seen.append('effect'))
            for arguments in ('1',',Effect()'):
                with self.subTest(constructor=constructor,args=arguments),self.assertRaises(PythonDirectUnsupported):
                    vm.execute('New '+constructor+'('+arguments+');')
            self.assertEqual(seen,[])


    def test_dynamic_constructor_explicit_parameter_array_unchanged(self):
        vm=Interpreter();vm.execute('Args=New Array;Args.Add("X");Args.Add(Undefined);S=New("Structure",Args);')
        self.assertIsNone(vm.execute('S.X'))
        vm.execute('Args=New Array;Args.Add(2);A=New("Array",Args);')
        self.assertEqual(vm.execute('A.Count()'),2)
        with self.assertRaises(PythonDirectUnsupported):vm.execute('New Unknown(,1);')

if __name__=='__main__':unittest.main()
