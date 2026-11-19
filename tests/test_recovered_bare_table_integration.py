import unittest
from recovered_bare_fixture import Interpreter
from yadinassi.execution.codegen.native_bare_table import BareTable, BareRow, BareColumn

class RecoveredBareTableIntegration(unittest.TestCase):
    def test_both_routes_and_russian_member_names(self):
        source='Т=Новый ТаблицаЗначений; Т.Колонки.Добавить("N"); Для Счетчик=0 По 7 Цикл Р=Т.Добавить(); Р.N=Счетчик; КонецЦикла; С=0; Для Каждого Р Из Т Цикл С=С+Р.N; КонецЦикла; К=Т.Колонки.Получить(0); Имя=К.Имя; В=Р.Владелец();'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared: vm.execute_prepared(vm.prepare(source))
            else: vm.execute(source)
            self.assertIs(type(vm.variables['т']),BareTable)
            self.assertIs(type(vm.variables['р']),BareRow)
            self.assertIs(type(vm.variables['к']),BareColumn)
            self.assertEqual(vm.variables['с'],28)
            self.assertEqual(vm.variables['имя'],'n')
            self.assertIs(vm.variables['в'],vm.variables['т'])
    def test_discarded_add_does_not_create_descriptor(self):
        from unittest.mock import patch
        import yadinassi.execution.codegen.native_bare_table as table
        vm=Interpreter(); p=vm.prepare('T=New ValueTable; T.Columns.Add("N"); X=0;')
        self.assertIn('.add_column(',p.generated_source)
        with patch.object(table,'BareColumns',side_effect=AssertionError('eager columns')):
            vm.execute_prepared(p)
        self.assertEqual(vm.variables['t'].schema,{'n':0})
    def test_copy_and_indexed_row_data(self):
        vm=Interpreter(); vm.execute('T=New ValueTable; T.Columns.Add("N"); R=T.Add(); R[0]=7; C=T.Copy(); C.Get(0).N=9; A=T.Get(0).N; B=C.Total("N");')
        self.assertEqual((vm.variables['a'],vm.variables['b']),(7,9))
