import unittest
from decimal import Decimal
from yadinassi import Interpreter
from tests.recovered_bare_fixture import Interpreter as BareInterpreter
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

class LazyFindRows(unittest.TestCase):
    def test_declared_lazy_and_supported_mutations(self):
        t=BSLValueTable();t.columns.add('K');t.columns.add('V')
        for k in (1,1,2):
            r=t.add();r.set_member('K',Decimal(k));r.set_member('V','x')
        t.indexes.add('K');t.indexes.add('V')
        query=lambda:t.find_rows(BSLStructure('K',Decimal(1))).items
        self.assertEqual(t._search.builds,0)
        self.assertEqual(len(query()),2);self.assertEqual(t._search.builds,1)
        self.assertEqual(len(query()),2);self.assertEqual(t._search.builds,1)
        r=t.rows[0];r.set(0,Decimal(2));self.assertEqual(query(),[t.rows[1]])
        r.set_index('K',Decimal(1));self.assertEqual(len(query()),2)
        r.cells={t.columns.get(0):Decimal(2),t.columns.get(1):'x'}
        self.assertEqual(query(),[t.rows[1]])
        t.fill_values(Decimal(1),'K');self.assertEqual(query(),t.rows)
        t.move(0,2);self.assertTrue(all(a is b for a,b in zip(query(),t.rows)))
        t.delete(0);self.assertEqual(len(query()),2)
        t.clear();self.assertEqual(query(),[])
        self.assertEqual(len(t._search.cache),1) # unrelated V index stays unbuilt
    def test_both_compilers_declaration_and_live_mutation(self):
        source=SOURCE.replace('Н=Т.НайтиСтроки','Т.Индексы.Добавить("Склад,Товар");Н=Т.НайтиСтроки')
        source+=' Повтор=Т.НайтиСтроки(Новый Структура("Склад,Товар","А","Х")).Количество();'
        for cls in (Interpreter,BareInterpreter):
            vm=cls();vm.execute_prepared(vm.prepare(source));self.assertEqual(vm.variables['повтор'],1)
    def test_readonly_indexes_and_opaque_shortcircuit(self):
        t=BSLValueTable();t.columns.add('K');t.columns.add('V');r=t.add()
        r.set_member('K',False);r.set_member('V',object())
        t.indexes.add('K,V')
        self.assertEqual(t.find_rows(BSLStructure('K,V',True,1)).items,[])
        t._bounded_slice_read=True
        with self.assertRaises(ValueError):t.indexes.add('K')
        with self.assertRaises(ValueError):t.indexes.clear()
    def test_schema_and_order_after_warmed_miss(self):
        t=BSLValueTable()
        for name in ('Unused','K','V'):t.columns.add(name)
        for k in (2,1,1):
            r=t.add();r.set_member('K',Decimal(k));r.set_member('V','x')
        t.indexes.add('K');t.indexes.add('V')
        self.assertEqual(t.find_rows(BSLStructure('K',Decimal(9))).items,[])
        t.rows[0].set_member('K',Decimal(9))
        self.assertIs(t.find_rows(BSLStructure('K',Decimal(9))).items[0],t.rows[0])
        t.columns.rename(t.columns.find('K'),'Renamed')
        self.assertEqual(len(t.find_rows(BSLStructure('Renamed',Decimal(1))).items),2)
        t.columns.delete('Unused')
        self.assertEqual(len(t.find_rows(BSLStructure('Renamed',Decimal(1))).items),2)
        t.sort('Renamed DESC')
        matches=t.find_rows(BSLStructure('Renamed',Decimal(1))).items
        self.assertTrue(all(a is b for a,b in zip(matches,t.rows[1:])))
        t.columns.delete('Renamed')
        self.assertEqual(t.indexes.count(),1)
    def test_bare_index_numeric_equality_and_epoch(self):
        from yadinassi.native_bare_table import BareTable
        from yadinassi.native_bare_collections import BareStructure
        t=BareTable();t.add_column('K')
        for value in (True,1,Decimal(1)):t.add()[0]=value
        t.indexes.add('K')
        self.assertEqual(len(t.find_rows(BareStructure('K',1))),3)
        self.assertEqual(t.indexes.search.builds,1)
        t.get(0).set_index(0,2)
        self.assertEqual(len(t.find_rows(BareStructure('K',1))),2)
        t.sort('K');self.assertEqual(len(t.find_rows(BareStructure('K',1))),2)
    def test_cached_position_integrity_and_immutable_buckets(self):
        from types import MappingProxyType
        from yadinassi.plain_table_search import _Entry
        t=BSLValueTable();t.columns.add('K');t.add().set_member('K',1);t.indexes.add('K')
        f=BSLStructure('K',1);t.find_rows(f)
        entry=t._search.cache[(0,)]
        with self.assertRaises(TypeError):entry.buckets[((int,1),)]=(0,)
        class Foreign:
            def __index__(self):raise AssertionError('foreign index hook')
        t._search.cache[(0,)]=_Entry(entry.epoch,MappingProxyType({((int,1),):(Foreign(),)}))
        with self.assertRaises(ValueError):t.find_rows(f)
        t._search.cache[(0,)]=_Entry(entry.epoch,MappingProxyType({((int,1),):(9,)}))
        with self.assertRaises(ValueError):t.find_rows(f)
    def test_retained_slot_accounting(self):
        t=BSLValueTable();t.columns.add('K');t.columns.add('V')
        for i in range(3):
            row=t.add();row.set_member('K',i);row.set_member('V',i)
        t.indexes.add('K');t.indexes.add('V')
        t.find_rows(BSLStructure('K',1));t.find_rows(BSLStructure('V',1))
        self.assertEqual([e.row_slots for e in t._search.cache.values()],[3,3])
        t.rows[0].set_member('K',object())
        with self.assertRaises(NotImplementedError):t.find_rows(BSLStructure('K',9))
        self.assertEqual(t._search.cache[(0,)].row_slots,0)
        self.assertEqual(t._search.cache[(1,)].row_slots,3)
