import unittest
from decimal import Decimal as D
from yadinassi.collections.plain_value_table_runtime import BSLValueTable, _index
from yadinassi.collections.structures import BSLStructure
from yadinassi.collections.plain_table_storage import scalar_equal
from yadinassi.collections.value_table_group import _sum, _scalar_key


class PlainTableIntegerValuesTests(unittest.TestCase):
    def test_compiled_table_native_cells_and_later_bsl_access(self):
        from yadinassi import Interpreter
        from yadinassi.types.values import BSLType
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('T=New ValueTable;T.Columns.Add("N");'
                          'For i=0 To 2 Do Row=T.Add();Row.N=i+1;EndDo;'
                          'R=0;For i=0 To 2 Do R=R+T[i][0]+T.Get(i).Get(0);EndDo;'
                          'FastTotal=T.Total("N");')
        vm.execute_prepared(plan)
        table = vm.variables['t']
        self.assertEqual(vm.variables['r'], D(12))
        self.assertEqual(vm.variables['fasttotal'], D(6))
        self.assertIs(type(vm.variables['r']), D)
        self.assertIs(type(list.__getitem__(table.get(0), 0)), int)
        vm.execute('K=TypeOf(T[0][0]); S=T.Total("N");'
                   'For Each Cell In T[0] Do V=Cell;EndDo;')
        self.assertIs(vm.variables['k'], BSLType.NUMBER)
        self.assertEqual(vm.variables['s'], D(6))
        self.assertEqual(vm.variables['v'], D(1))
        self.assertIs(type(vm.variables['v']), D)

    def test_native_index_and_fractional_contract(self):
        self.assertEqual(_index(1, 3), 1)
        self.assertEqual(_index(D('1.9'), 3), 1)
        with self.assertRaises(TypeError): _index(True, 3)
        with self.assertRaises(IndexError): _index(-1, 3)
        table = BSLValueTable(); table.columns.add('N')
        row = table.add(); row.set_index(0, 7)
        self.assertEqual(table.get(0).get_index(0), 7)
        self.assertIs(type(row.get_member('N')), D)
        self.assertIs(type(row.get_index(0)), D)
        self.assertIs(type(list.__getitem__(row, 0)), int)

    def test_total_native_accumulator_public_decimal(self):
        table = BSLValueTable(); table.columns.add('N')
        for value in (2, 3, True, '4', None): table.add().set_member('N', value)
        result = table.total('N')
        self.assertIs(type(result), D); self.assertEqual(result, 5)
        table.add().set_member('N', D('0.5'))
        self.assertEqual(table.total('N'), D('5.5'))

    def test_iteration_snapshot_and_unload_do_not_export_python_int(self):
        from yadinassi.formats.storage.value_storage import BSLValueStorage
        table = BSLValueTable(); column = table.columns.add('N')
        row = table.add(); row.set(0, 7)
        for value in (next(iter(row)), row.cells[column], table.unload_column('N').items[0]):
            self.assertIs(type(value), D)
            self.assertEqual(value, 7)
        restored = BSLValueStorage(table).get()
        self.assertIs(type(restored.get(0).get(0)), D)
        self.assertEqual(restored.get(0).get(0), 7)

    def test_search_numeric_domain_and_mutation(self):
        table = BSLValueTable(); table.columns.add('N')
        for value in (True, 1, D(1), 2): table.add().set_member('N', value)
        for indexed in (False, True):
            if indexed: table.indexes.add('N')
            for key in (1, D(1)):
                self.assertEqual(table.find_rows(BSLStructure('N', key)).items, table.rows[1:3])
            self.assertEqual(table.find_rows(BSLStructure('N', True)).items, table.rows[:1])
        table.rows[1].set_index(0, 2)
        self.assertEqual(table.find_rows(BSLStructure('N', D(1))).items, table.rows[2:3])
        self.assertEqual(table.find_rows(BSLStructure('N', D(2))).items, [table.rows[1], table.rows[3]])

    def test_group_numeric_helpers(self):
        self.assertEqual(_scalar_key(1), _scalar_key(D(1)))
        self.assertNotEqual(_scalar_key(True), _scalar_key(1))
        self.assertEqual(_sum([1, 2, 3]), D(6))
        self.assertEqual(_sum([1, D('0.25'), 2]), D('3.25'))
        self.assertIs(type(_sum([1, 2])), D)
        self.assertTrue(scalar_equal(1, D(1)))
        self.assertFalse(scalar_equal(True, D(1)))
