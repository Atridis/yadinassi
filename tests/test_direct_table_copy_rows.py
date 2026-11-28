from decimal import Decimal
import unittest

from yadinassi import Interpreter


class DirectTableCopyRowsTests(unittest.TestCase):
    def vm(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        return vm

    def test_projection_omits_rows_and_copies_all_rows(self):
        vm = self.vm()
        vm.execute('T=New ValueTable; T.Columns.Add("Name"); T.Columns.Add("Amount"); '
                   'A=T.Add(); A.Name="one"; A.Amount=2; '
                   'B=T.Add(); B.Name="two"; B.Amount=3; T.Indexes.Add("Amount");')
        plan = vm.prepare('Full=T.Copy(); Projected=T.Скопировать(, "Amount");')
        vm.execute_prepared(plan)
        code = plan._plan.generated_source
        self.assertIn("t._bsl_value_copy()", code)
        self.assertIn("t._bsl_value_copy_columns_only(columns='Amount')", code)
        full = vm.variables['full']
        projected = vm.variables['projected']
        self.assertEqual([tuple(row) for row in projected.rows], [(Decimal(2),), (Decimal(3),)])
        self.assertEqual(list(full.indexes.items), [(1,)])
        self.assertEqual(list(projected.indexes.items), [])

    def test_explicit_native_array_copies_compatible_rows_in_order(self):
        source = '''
            T=New ValueTable; T.Columns.Add("Name");
            T.Columns.Add("Amount", New TypeDescription("Number"));
            Own=T.Add(); Own.Name="own"; Own.Amount=1;
            T.Indexes.Add("Name");
            Other=New ValueTable; Other.Columns.Add("Name");
            Other.Columns.Add("Amount", New TypeDescription("Number"));
            Foreign=Other.Add(); Foreign.Name="foreign"; Foreign.Amount=7;
            Selected=New Array; Selected.Add(Foreign); Selected.Add(Own); Selected.Add(Foreign);
            Result=T.Copy(Selected); Projected=T.Скопировать(Selected, "Amount,Name");
            Foreign.Amount=21; Result[0].Amount=9;
        '''
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = self.vm()
                if prepared:
                    vm.execute_prepared(vm.prepare(source))
                else:
                    vm.execute(source)
                state = vm.variables
                result, projected = state['result'], state['projected']
                self.assertEqual([tuple(row) for row in result.rows],
                                 [('foreign', Decimal(9)), ('own', Decimal(1)), ('foreign', Decimal(7))])
                self.assertEqual([tuple(row) for row in projected.rows],
                                 [(Decimal(7), 'foreign'), (Decimal(1), 'own'), (Decimal(7), 'foreign')])
                self.assertEqual(list(result.indexes.items), [(0,)])
                self.assertIs(result.rows[0].owner(), result)
                self.assertIsNot(result.rows[0], result.rows[2])
                self.assertEqual(state['foreign'].get_member('Amount'), Decimal(21))
                self.assertEqual(len(state['t'].rows), 1)

    def test_explicit_selection_rejects_deleted_or_different_schema(self):
        vm = self.vm()
        vm.execute('''
            T=New ValueTable; T.Columns.Add("A"); T.Columns.Add("B"); Own=T.Add(); Own.A=1;
            Other=New ValueTable; Other.Columns.Add("B"); Other.Columns.Add("A"); Different=Other.Add();
            Dead=T.Add(); T.Delete(Dead); Rows=New Array; Rows.Add(Different);
            Failures=0;
            Try C=T.Copy(Rows); Except Failures=Failures+1; EndTry;
            Rows.Set(0, Dead);
            Try C=T.Copy(Rows); Except Failures=Failures+1; EndTry;
            Typed=New ValueTable; Typed.Columns.Add("A", New TypeDescription("Number"));
            Typed.Columns.Add("B"); Rows.Set(0, Typed.Add());
            Try C=T.Copy(Rows); Except Failures=Failures+1; EndTry;
        ''')
        self.assertEqual(vm.variables['failures'], Decimal(3))
        self.assertNotIn('c', vm.variables)
        self.assertEqual(len(vm.variables['t'].rows), 1)
        self.assertEqual(vm.variables['own'].get_member('A'), Decimal(1))

    def test_explicit_selection_does_not_export_a_foreign_bounded_row(self):
        vm = self.vm()
        vm.execute('''
            T=New ValueTable; T.Columns.Add("A");
            Source=New ValueTable; Source.Columns.Add("A"); Row=Source.Add(); Row.A=1;
            Rows=New Array; Rows.Add(Row);
        ''')
        vm.variables['source']._bounded_slice_read = True
        with self.assertRaisesRegex(ValueError, 'foreign bounded row'):
            vm.variables['t'].copy(vm.variables['rows'])
        self.assertEqual(vm.variables['row'].get_member('A'), Decimal(1))

    def test_own_and_foreign_rows_use_the_same_target_conversion(self):
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = self.vm()
                vm.execute('''
                    T=New ValueTable; T.Columns.Add("N", New TypeDescription("Number"));
                    Own=T.Add(); T.FillValues("7", "N");
                    U=New ValueTable; U.Columns.Add("N", New TypeDescription("Number"));
                    Foreign=U.Add(); U.FillValues("7", "N");
                    Rows=New Array; Rows.Add(Own); Rows.Add(Foreign);
                ''')
                copy = 'Result=T.Copy(Rows);'
                if prepared:
                    vm.execute_prepared(vm.prepare(copy))
                else:
                    vm.execute(copy)
                self.assertEqual(vm.variables['own'].get_member('N'), '7')
                self.assertEqual(vm.variables['foreign'].get_member('N'), '7')
                for row in vm.variables['result'].rows:
                    value = row.get_member('N')
                    self.assertIs(type(value), Decimal)
                    self.assertEqual(value, Decimal(7))

    def test_zero_column_selection_does_not_copy_deleted_rows(self):
        vm = self.vm()
        vm.execute('''
            T=New ValueTable; Live=T.Add(); Dead=T.Add(); T.Delete(Dead);
            Rows=New Array; Rows.Add(Live); Result=T.Copy(Rows);
            Rows.Set(0, Dead);
            Try DeletedCopy=T.Copy(Rows); Except Denied=True; EndTry;
        ''')
        self.assertEqual(vm.variables['result'].count(), Decimal(1))
        self.assertIs(vm.variables['denied'], True)
        self.assertNotIn('deletedcopy', vm.variables)
