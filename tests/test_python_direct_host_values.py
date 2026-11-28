"""Detached public result protocols retain identity and database boundaries."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.formats.regex.regex_functions import BSLRegexResult
from yadinassi.types.values import BSLArray, BSLFixedArray
import test_python_direct_database as database_fixture


class DirectHostValuesTests(unittest.TestCase):
    def test_builtin_split_array_methods_index_and_iteration(self):
        vm=Interpreter()
        vm.execute('A=StrSplit("a,b",","); B=A; B[0]="changed"; N=A.Count(); S=""; For Each V In A Do S=S+V; EndDo; R=A.Get(0);')
        self.assertIs(vm.variables['a'],vm.variables['b'])
        self.assertIs(type(vm.variables['a']),BSLArray)
        self.assertEqual((vm.variables['n'],vm.variables['s'],vm.variables['r']),(2,'changedb','changed'))

    def test_fixed_host_array_reads_and_readonly_write(self):
        source=BSLArray();source.add(Decimal(3));source.add(Decimal(4))
        fixed=BSLFixedArray(source)
        vm=Interpreter(allow_extensions=True);vm.register_function('Values',lambda:fixed)
        vm.execute('A=Values(); S=0; For Each V In A Do S=S+V; EndDo; R=A[1]; Try A[0]=9; Except Readonly=True; EndTry;')
        self.assertIs(vm.variables['a'],fixed)
        self.assertEqual((vm.variables['s'],vm.variables['r'],vm.variables['readonly']),(7,4,True))
        self.assertEqual(fixed.items,(Decimal(3),Decimal(4)))

    def test_fixed_array_snapshots_plain_arrays_from_earlier_commands(self):
        from yadinassi.execution.direct.python_direct_plain_array import PlainArray
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Outer=New Array;')
        vm.execute('Inner=New Array;')
        vm.execute('Inner.Add(7);Outer.Add(Inner);')
        self.assertIs(type(vm.variables['outer']),PlainArray)
        self.assertIs(type(vm.variables['inner']),PlainArray)
        with patch.object(PlainArray,'__iter__',side_effect=AssertionError('dynamic iteration')):
            vm.execute('Snapshot=New FixedArray(Outer);')
        vm.execute('Inner[0]=8;Outer.Add(9);')
        self.assertEqual(vm.execute('Snapshot.Count()'),1)
        self.assertEqual(vm.execute('Snapshot.Get(0).Get(0)'),7)
        self.assertEqual(vm.execute('Outer.Count()'),2)

        class ForeignArray(PlainArray):
            def __iter__(self):
                raise AssertionError('foreign iteration')
        vm.variables['foreign'] = ForeignArray([Decimal(1)])
        with self.assertRaisesRegex(BSLRuntimeError,'ожидает массив'):
            vm.execute('New FixedArray(Foreign)')

    def test_host_array_indexes_keep_canonical_bounds_and_type_checks(self):
        # Real 1C StrSplit-produced arrays have the same access rules as
        # New Array (native run 45467963783, 8.3.27.1508).
        vm=Interpreter()
        self.addCleanup(vm.close)
        letters=('a','b')
        reset=vm.prepare('A=StrSplit("a,b",",");')
        cases=(('-1',None,None),('-0.5',None,0),('0.5',0,0),
               ('1.9',1,1),('True',None,1),('2',None,None))
        for index,bracket,method in cases:
            operations=((f'A[{index}]',bracket,False),
                        (f'A.Get({index})',method,False),
                        (f'A.Получить({index})',method,False),
                        (f'A[{index}]="written";',bracket,True),
                        (f'A.Set({index},"written");',method,True),
                        (f'A.Установить({index},"written");',method,True))
            for expression,position,write in operations:
                with self.subTest(expression=expression):
                    vm.execute_prepared(reset)
                    expected=list(letters)
                    if position is None:
                        with self.assertRaises(BSLRuntimeError):
                            vm.execute(expression)
                    elif write:
                        vm.execute(expression)
                        expected[position]='written'
                    else:
                        self.assertEqual(vm.execute(expression),letters[position])
                    self.assertEqual(vm.variables['a'].items,expected)

    def test_get_aliases_preserve_nested_identity_and_live_mutations(self):
        nested=BSLArray();nested.add(Decimal(3))
        array=BSLArray();array.add(nested)
        for value in (array,BSLFixedArray(array)):
            vm=Interpreter();vm.variables['a']=value
            vm.execute('B=A.Get(0);C=A.ПОЛУЧИТЬ(0);Try B[0]=9;Except Readonly=True;EndTry;R=C.Get(0);')
            self.assertIs(vm.variables['b'],value.items[0]);self.assertIs(vm.variables['c'],value.items[0])
            if type(value) is BSLArray:
                self.assertIs(value.items[0],nested);self.assertEqual(vm.variables['r'],9)
                self.assertNotIn('readonly',vm.variables)
            else:
                self.assertTrue(vm.variables['readonly']);self.assertEqual(vm.variables['r'],3)

    def test_get_checks_runtime_after_argument_evaluation(self):
        vm=Interpreter(allow_extensions=True);array=BSLArray();array.add(Decimal(7));vm.variables['a']=array
        vm.register_function('Close',lambda:vm.close() or Decimal(0))
        with self.assertRaises(BoundaryViolation):vm.execute('A.Get(Close());')
        self.assertEqual(array.items,[Decimal(7)])

    def test_regex_groups_are_independent_arrays_and_readonly_values(self):
        vm=Interpreter()
        vm.execute('R=StrFindByRegularExpression("ab","(a)(b)"); A=R.GetGroups(); G=A[0]; A.Clear(); N=R.GetGroups().Count(); Try G.Value="bad"; Except Readonly=True; EndTry; V=G.Value;')
        self.assertEqual((vm.variables['n'],vm.variables['readonly'],vm.variables['v']),(2,True,'a'))

    def test_subclasses_private_members_and_arbitrary_receivers_reject(self):
        class ArraySubclass(BSLArray): pass
        class ResultSubclass(BSLRegexResult): pass
        for value,expression in ((ArraySubclass(),'A.Count()'),(ResultSubclass('a',1,1,()),'A.Value'),(object(),'A.Anything')):
            vm=Interpreter();vm.variables['a']=value
            with self.subTest(value=type(value).__name__), self.assertRaises(BoundaryViolation):vm.execute(expression)
        for expression in ('A.items','A._groups','A.__class__'):
            vm=Interpreter();vm.execute('A=StrFindByRegularExpression("a","(a)");')
            with self.subTest(expression=expression),self.assertRaises(BSLRuntimeError):vm.execute(expression)

    def test_owner_close_during_array_method_is_checked(self):
        vm=Interpreter()
        class Item:
            def __eq__(self,other):vm.close();return False
        array=BSLArray();array.add(Item());vm.variables['a']=array;vm.variables['needle']=Item()
        with self.assertRaises(BoundaryViolation):vm.execute('A.Find(needle);')


class DirectHostArrayDatabaseTests(unittest.TestCase):
    setUp=database_fixture.DirectDatabaseTests.setUp

    def test_array_does_not_grant_foreign_catalog_receiver(self):
        other=Interpreter(database_context=self.context);self.addCleanup(other.close)
        other.execute('A=Catalogs.Склады.CreateItem(); A.Description="kept";')
        foreign=other.variables['a'];array=BSLArray();array.add(foreign)
        self.vm.variables['values']=array
        with self.assertRaises(BoundaryViolation):self.vm.execute('Values[0].Description="bad";')
        self.assertEqual(foreign.get_member('Description'),'kept')
