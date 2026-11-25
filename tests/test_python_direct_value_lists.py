"""Direct ValueList call and reference contracts; no VM dispatch."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem

class DirectValueListTests(unittest.TestCase):
    def test_source_ast_prepared_and_persistent_references(self):
        source='L=New ValueList;I=L.Add(10,"old",True);Procedure SetField(X) X=27;EndProcedure SetField(I.Value);R=L[0].Value;'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
                self.assertEqual(vm.variables['r'],27)
                vm.execute('SetField(I.Presentation);')
                self.assertEqual(vm.execute('I.Presentation'),'27')

    def test_native_integer_values_positions_and_bulk_load_share_storage_rules(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('''
            L=New ValueList; First=L.Add(7,4,1); L.Insert(0,9);
            R=L[1].Value; P=First.Presentation; C=First.Check;
            L.Move(0,1); Last=L.Get(1).Value;
            A=New Array; A.Add(8); A.Add(3); L.LoadValues(A);
            L[0].Value=6; L.FillChecks(1); Loaded=L.FindByValue(6).Check;
        ''')
        for name,value in dict(r=7,p='4',c=True,last=9,loaded=True).items():
            self.assertEqual(vm.variables[name],value)
        self.assertEqual(vm.execute('L[1].Value'),3)

    def test_rejection_precedes_all_argument_effects(self):
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Effect',lambda:seen.append(1) or Decimal(0))
        vm.execute('L=New ValueList;L.Add(1);')
        for code in ('X=L.Delete(Effect())','X=L.Clear()','L.Insert(,Effect())','L.Get(,Effect())','L.FillChecks(,Effect())'):
            vm.execute('Caught=False;Try '+code+';Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught'],code)
            self.assertEqual(seen,[]);self.assertEqual(vm.execute('L.Count()'),1)
        vm.register_function('Receiver',lambda:seen.append(2) or vm.variables['l'])
        vm.execute('Try Receiver().Add(,Effect());Except Caught=True;EndTry;')
        self.assertEqual(seen,[])

    def test_named_holes_defaults_and_explicit_values(self):
        vm=Interpreter();vm.execute('L=New СписокЗначений;A=L.Добавить(,,);B=L.Вставить(0,,"b",True);Try C=L.Add(Undefined,Undefined,Undefined);Except Caught=True;EndTry;')
        self.assertIsNone(vm.execute('A.Value'));self.assertEqual(vm.execute('A.Presentation'),'')
        self.assertIs(vm.execute('A.Check'),False);self.assertIs(vm.execute('B.Check'),True)
        self.assertTrue(vm.variables['caught']);self.assertEqual(vm.execute('L.Count()'),2)

    def test_readonly_slot_and_private_or_noncanonical_receivers(self):
        vm=Interpreter(allow_extensions=True);vm.execute('L=New ValueList;I=L.Add(1);Procedure Change(X,Y) X=2;EndProcedure')
        seen=[];vm.register_function('Effect',lambda:seen.append(1))
        with self.assertRaises(BoundaryViolation):vm.execute('Change(L.ValueType,Effect());')
        self.assertEqual(seen,[])
        for text in ('L.items','I._owner_ref','For Each X In I Do EndDo;'):
            with self.assertRaises((BSLError,BoundaryViolation)):vm.execute(text)
        class Item(BSLValueListItem):pass
        bad=object.__new__(Item);vm.variables['bad']=bad
        with self.assertRaises(BoundaryViolation):vm.execute('Change(Bad.Value,Effect());')
        self.assertEqual(seen,[])

    def test_mutated_owner_rechecked_after_arguments(self):
        vm=Interpreter(allow_extensions=True);vm.execute('L=New ValueList;I=L.Add(1);')
        def mutate():
            vm.variables['i']._owner_ref=lambda:object()
            return Decimal(4)
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('I.Value=Mutate();')
        self.assertEqual(vm.variables['l'].get(Decimal(0)).value,Decimal(1))

    def test_nonconstructible_item_and_readonly_index(self):
        vm=Interpreter();vm.execute('L=New ValueList;')
        for name in ('ValueListItem','ЭлементСпискаЗначений'):
            vm.execute('Caught=False;Try New '+name+';Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught'])
        vm.execute('L.Add(1);Try L[0]=2;Except Caught=True;EndTry;')
        self.assertEqual(vm.execute('L[0].Value'),1)

    def test_existing_named_table_column_omissions(self):
        vm=Interpreter();vm.execute('T=New ValueTable;C=T.Columns.Add("A",,"Header");R=C.Title;')
        self.assertEqual(vm.variables['r'],'Header')

    def test_retained_field_reference_rejects_closed_runtime(self):
        vm=Interpreter(allow_extensions=True);captured=[]
        vm.register_function('Capture',lambda reference:captured.append(reference))
        vm.functions['capture'].reference_parameters=frozenset({0})
        vm.execute('L=New ValueList;I=L.Add(1);Capture(I.Value);')
        self.assertEqual(len(captured),1)
        item=vm.variables['i'];vm.close()
        for operation in (captured[0].get,lambda:captured[0].set(9)):
            with self.assertRaises(BoundaryViolation):operation()
        self.assertEqual(item.value,1)
