import unittest
from decimal import Decimal
from yadinassi import Interpreter
from recovered_bare_fixture import Interpreter as BareInterpreter
from yadinassi.plain_value_table_runtime import BSLValueTable
from yadinassi.structures import BSLStructure

SOURCE = '''Т=Новый ТаблицаЗначений;
Т.Колонки.Добавить("Склад");Т.Колонки.Добавить("Товар");
Р=Т.Добавить();Р.Склад="А";Р.Товар="Х";
Р=Т.Добавить();Р.Склад="Б";Р.Товар="Х";
Р=Т.Добавить();Р.Склад="А";Р.Товар="Х";
Н=Т.НайтиСтроки(Новый Структура("Товар,Склад","Х","А"));
К=Н.Количество();Н[0].Товар="Изменен";
П=Т.Получить(0).Товар;
Е=Т.НайтиСтроки(Новый Структура).Количество();'''

class LinearFindRows(unittest.TestCase):
    def test_both_compilers_and_prepared(self):
        for cls in (Interpreter, BareInterpreter):
            for prepared in (False, True):
                with self.subTest(compiler=cls.__module__, prepared=prepared):
                    vm=cls()
                    if prepared: vm.execute_prepared(vm.prepare(SOURCE))
                    else: vm.execute(SOURCE)
                    self.assertEqual(vm.variables['к'], 2)
                    self.assertEqual(vm.variables['е'], 0)
                    self.assertEqual(vm.variables['п'], 'Изменен')
                    rows=vm.variables['т'].rows
                    found=vm.variables['н']
                    actual=found.items if hasattr(found,'items') else list(found)
                    self.assertIs(actual[0],rows[0]); self.assertIs(actual[1],rows[2])
    def test_exact_default_equality_and_errors(self):
        t=BSLValueTable();t.columns.add('K')
        for value in (True,1,Decimal(1)):
            t.add().set_member('K',value)
        self.assertIs(t.find_rows(BSLStructure('K',Decimal(1))).items[0],t.rows[2])
        self.assertEqual(t.find_rows(BSLStructure()).items,[])
        with self.assertRaises(ValueError):t.find_rows(BSLStructure('Missing',1))
        with self.assertRaises(TypeError):t.find_rows({'K':1})
        class Opaque:
            def __eq__(self,other):raise AssertionError('foreign equality')
        t.rows[0].set_member('K',Opaque())
        with self.assertRaises(NotImplementedError):t.find_rows(BSLStructure('K',1))
    def test_bad_field_compiled(self):
        for cls in (Interpreter,BareInterpreter):
            with self.subTest(compiler=cls.__module__):
                with self.assertRaises(Exception):cls().execute('T=New ValueTable; R=T.FindRows(New Structure("Missing",1));')
