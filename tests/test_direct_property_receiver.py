from contextlib import closing
from decimal import Decimal
import ast
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class DirectPropertyTests(unittest.TestCase):
    def test_structure_properties_are_python_subscripts(self):
        with closing(Interpreter()) as vm:
            plan = vm.prepare('S=New Structure("Value",1);S.Value=2;R=S.VALUE;')
            tree = ast.parse(plan._plan.generated_source)
            fields = [node for node in ast.walk(tree)
                      if isinstance(node, ast.Subscript)
                      and isinstance(node.slice, ast.Constant)
                      and node.slice.value.casefold() == 'value']
            self.assertEqual({type(node.ctx) for node in fields}, {ast.Load, ast.Store})
            self.assertNotIn('_GetField', plan._plan.generated_source)
            self.assertNotIn('_SetField', plan._plan.generated_source)
            vm.execute_prepared(plan)
            self.assertEqual(vm.variables['r'], 2)

    def test_unintegrated_receiver_does_not_run_python_field_hooks(self):
        calls = []

        class Foreign:
            @property
            def value(self):
                calls.append('property')

            def get_member(self, name):
                calls.append('get_member')

            def set_member(self, name, value):
                calls.append('set_member')

            def __getitem__(self, key):
                calls.append('getitem')

            def __setitem__(self, key, value):
                calls.append('setitem')

        with closing(Interpreter()) as vm:
            vm.variables['x'] = Foreign()
            for code in ('R=X.Value;', 'X.Value=1;'):
                with self.subTest(code=code), self.assertRaises(BoundaryViolation):
                    vm.execute(code)
        self.assertEqual(calls, [])

    def test_table_property_uses_row_qualification_and_index_updates(self):
        with closing(Interpreter()) as vm:
            vm.execute('T=New ValueTable;'
                       'C=T.Columns.Add("Amount",New TypeDescription("Number",New NumberQualifiers(5,1)));'
                       'R=T.Add();R.Amount=1.23;C.Title="Amount header";'
                       'T.Indexes.Add("Amount");'
                       'Old=T.FindRows(New Structure("Amount",1.2));'
                       'R.Amount=5.67;'
                       'Result=R.AMOUNT;Caption=C.Title;'
                       'NewMatch=T.FindRows(New Structure("Amount",5.7));')
            self.assertEqual(vm.variables['result'], Decimal('5.7'))
            self.assertEqual(vm.variables['caption'], 'Amount header')
            self.assertEqual(vm.variables['old'].items, [vm.variables['r']])
            self.assertEqual(vm.variables['newmatch'].items, [vm.variables['r']])
            self.assertEqual(vm.execute('T.FindRows(New Structure("Amount",1.2)).Count()'), 0)
            vm.variables['t']._bounded_slice_read = True
            with self.assertRaises(BSLError):
                vm.execute('R.Amount=9;')
            self.assertEqual(vm.variables['r'].get_member('Amount'), Decimal('5.7'))

    def test_readonly_pair_and_fixed_structure_reject_writes_in_except(self):
        with closing(Interpreter()) as vm:
            vm.execute('''S=New Structure("Amount",5);F=New FixedStructure(S);
                          For Each Pair In S Do
                              Try Pair.Value=8;Except PairRejected=True;EndTry;
                              PairAmount=Pair.Value;
                          EndDo;
                          Try F.Amount=8;Except FixedRejected=True;EndTry;
                          FixedAmount=F.Amount;''')
            self.assertTrue(vm.variables['pairrejected'])
            self.assertTrue(vm.variables['fixedrejected'])
            self.assertEqual((vm.variables['pairamount'], vm.variables['fixedamount']), (5, 5))

    def test_value_tree_named_properties_preserve_structure_and_cell_types(self):
        with closing(Interpreter()) as vm:
            vm.execute('''T=New ValueTree;
                          T.Columns.Add("Amount",New TypeDescription("Number",New NumberQualifiers(5,1)));
                          R=T.Rows.Add();C=R.Rows.Add();C.Amount=2.34;
                          Parent=C.Parent;Amount=C.Amount;Indexed=C[0];
                          Try C.Parent=Undefined;Except ParentRejected=True;EndTry;
                          R.Rows.Delete(C);
                          Try Deleted=C.Amount;Except DeletedRejected=True;EndTry;''')
            self.assertIs(vm.variables['parent'], vm.variables['r'])
            self.assertTrue(vm.variables['parentrejected'])
            self.assertTrue(vm.variables['deletedrejected'])
            self.assertEqual((vm.variables['amount'], vm.variables['indexed']),
                             (Decimal('2.3'), Decimal('2.3')))

    def test_qualifier_namespaces_and_value_metadata_are_readonly(self):
        with closing(Interpreter()) as vm:
            vm.execute('''Sign=ДопустимыйЗнак.Неотрицательный;
                          D=New TypeDescription("Number",New NumberQualifiers(5,2,Sign));
                          Digits=D.NumberQualifiers.Разрядность;
                          Named=D.КвалификаторыЧисла.AllowedSign=Sign;
                          Try D.NumberQualifiers.Дробь=3;Except Rejected=True;EndTry;''')
            self.assertEqual(vm.variables['digits'], 5)
            self.assertTrue(vm.variables['named'])
            self.assertTrue(vm.variables['rejected'])
