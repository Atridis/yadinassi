"""Native Array contract repairs, retaining direct representation and budgets."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.types import values
from yadinassi.syntax.parser import parse
from yadinassi.types.values import BSLFixedArray
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_resources import bounded_array
from yadinassi.execution.direct.python_direct_plain_array import PlainArray

class DirectArrayContractTests(unittest.TestCase):
    def test_fixed_copy_routes_nested_aliases_and_no_vm_dispatch(self):
        source='''A=New Array; Child=New Array; Child.Add(7);
S=New Structure("N",1); A.Add(Child); A.Add(Child); A.Add(S);
F=New FixedArray(A); B=New Array(F); B[0][0]=9; S.N=2;'''
        for route in ('source','ast','prepared'):
            with self.subTest(route=route):
                vm=Interpreter()
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
                b=vm.variables['b'];a=vm.variables['a'];f=vm.variables['f']
                self.assertIs(type(b),list);self.assertIs(type(b[0]),list)
                self.assertIsNot(b[0],b[1]);self.assertEqual(b[0],[9]);self.assertEqual(b[1],[7])
                self.assertEqual(a[0],[7]);self.assertEqual(f.items[0].items,(7,))
                self.assertIs(b[2],a[2]);self.assertEqual(vm.execute('B[2].N'),2)

    def test_copy_budget_depth_cycle_and_corrupt_storage_before_publication(self):
        vm=Interpreter();vm.execute('A=New Array; A.Add(1); F=New FixedArray(A); Saved=7;')
        with patch.object(values,'_MAX_ARRAY_CONSTRUCTION',0):
            with self.assertRaises(BSLError):vm.execute('Saved=New Array(F)')
        self.assertEqual(vm.variables['saved'],7)
        f=vm.variables['f']
        for items in ([1],(f,)):
            f.items=items
            with self.assertRaises((TypeError,ValueError)):bounded_array(f)
        f.items=()
        with self.assertRaises(ValueError):bounded_array(f,max_dimensions=0)
        child=object.__new__(BSLFixedArray);child.items=(1,)
        f.items=(child,child)
        with self.assertRaises(ValueError):bounded_array(f,max_slots=5)
        self.assertEqual(bounded_array(f,max_slots=6),[[1],[1]])
        with self.assertRaises(ValueError):bounded_array(f,max_dimensions=1)

    def test_exact_fixed_type_only_and_no_foreign_iteration(self):
        class Foreign:
            def __iter__(self):raise AssertionError('foreign iterator')
        class Child(BSLFixedArray):
            def __getattribute__(self,name):raise AssertionError('subclass access')
        for item in (Foreign(),object.__new__(Child),(),[]):
            vm=Interpreter();vm.variables['x']=item
            with self.assertRaises(BSLError):vm.execute('New Array(X)')

    def test_omissions_are_not_undefined_and_do_not_publish_mutation(self):
        for call in ('A.Add(,)','A.Insert(0,)','A.Insert(,1)','A.Set(0,)','A.Delete(0,)'):
            vm=Interpreter()
            vm.execute('A=New Array; A.Add("kept"); Caught=False;')
            vm.execute('Try '+call+'; Except Caught=True; EndTry;')
            self.assertTrue(vm.variables['caught'])
            self.assertEqual(vm.execute('A.Count()'),1);self.assertEqual(vm.execute('A[0]'),'kept')

    def test_omission_does_not_evaluate_arguments(self):
        for call in ('A.Insert(Effect(),)', 'A.Set(,Effect())'):
            events=[];vm=Interpreter(allow_extensions=True)
            vm.register_function('Effect',lambda:events.append('effect') or 0)
            vm.execute('A=New Array; A.Add(7);')
            with self.assertRaises(BSLError):vm.execute(call)
            self.assertEqual(events,[]);self.assertEqual(vm.execute('A[0]'),7)
            vm.execute('A.Insert(0,9);');self.assertEqual(vm.execute('A.Count()'),2)

    def test_insert_uses_both_canonical_array_representations(self):
        for constructor, kind in (('New Array', PlainArray), ('New Array(1)', list)):
            for prepared in (False, True):
                with self.subTest(kind=kind, prepared=prepared):
                    vm=Interpreter(allow_extensions=True)
                    self.addCleanup(vm.close)
                    events=[]
                    vm.register_function('Position', lambda: events.append('position') or Decimal(0))
                    vm.register_function('Payload', lambda: events.append('payload') or 'first')
                    vm.execute('A='+constructor+'; A[0]=7;' if kind is list else 'A='+constructor+'; A.Add(7);')
                    storage=vm.variables['a']
                    self.assertIs(type(storage), kind)
                    def execute(source):
                        if prepared:
                            return vm.execute_prepared(vm.prepare(source))
                        return vm.execute(source)
                    execute('A.Insert(Position(),Payload()); A.Вставить(3);')
                    self.assertIs(vm.variables['a'], storage)
                    self.assertEqual(list(storage), ['first',7,None,None])
                    self.assertEqual(events, ['position','payload'])
                    with patch.object(values, '_MAX_INSERT_GROWTH', 1):
                        with self.assertRaisesRegex(BSLError, 'предел роста'):
                            execute('A.Insert(5,9);')
                    self.assertEqual(list(storage), ['first',7,None,None])

    def test_fixed_copy_rejects_extra_dimension_and_nested_subclass(self):
        vm=Interpreter();vm.execute('F=New FixedArray(New Array);')
        with self.assertRaises(BSLError):vm.execute('New Array(F,2)')
        class Child(BSLFixedArray):pass
        child=object.__new__(Child);child.items=()
        vm.variables['f'].items=(child,)
        with self.assertRaises(BSLError):vm.execute('New Array(F)')

    def test_late_owner_revocation_still_prevents_fixed_copy(self):
        vm=Interpreter(allow_extensions=True);vm.execute('F=New FixedArray(New Array); Saved=7;')
        def close():vm.close();return vm.variables['f']
        vm.register_function('CloseOwner',close)
        with self.assertRaises(BoundaryViolation):vm.execute('Saved=New Array(CloseOwner())')
        self.assertEqual(vm.variables['saved'],7)
