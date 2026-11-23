import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from tests.recovered_bare_fixture import Interpreter as BareInterpreter
from yadinassi.collections.plain_value_table_runtime import BSLValueTable
from yadinassi.collections.structures import BSLStructure
from yadinassi.types.unique_identifiers import BSLUUID

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
        self.assertEqual(t.find_rows(BSLStructure('K',Decimal(1))).items,t.rows[1:])
        self.assertEqual(t.find_rows(BSLStructure('K',True)).items,t.rows[:1])
        self.assertEqual(t.find_rows(BSLStructure()).items,[])
        with self.assertRaises(ValueError):t.find_rows(BSLStructure('Missing',1))
        with self.assertRaises(TypeError):t.find_rows({'K':1})
        class Opaque:
            def __eq__(self,other):raise AssertionError('foreign equality')
        t.rows[0].set_member('K',Opaque())
        with self.assertRaises(NotImplementedError):t.find_rows(BSLStructure('K',1))
    def test_uuid_find_and_lazy_index_keep_type_value_and_current_order(self):
        t=BSLValueTable();t.columns.add('K')
        spelling='11111111-2222-4333-8444-abcdefabcdef'
        uuid=BSLUUID(spelling);other=BSLUUID('aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee')
        for value in (spelling,uuid,other,BSLUUID(spelling.upper())):
            t.add().set_member('K',value)
        text_row,first,unrelated,last=t.rows
        wanted=BSLUUID(spelling);query=BSLStructure('K',wanted)
        def no_callback(*args):raise AssertionError('UUID Python protocol must not run')
        with patch.object(BSLUUID,'__eq__',no_callback),patch.object(BSLUUID,'__hash__',no_callback):
            self.assertIs(t.find(wanted,'K'),first)
            self.assertEqual(tuple(map(id,t.find_rows(query).items)),(id(first),id(last)))
            t.indexes.add('K')
            self.assertEqual(t._search.builds,0)
            self.assertEqual(tuple(map(id,t.find_rows(query).items)),(id(first),id(last)))
            self.assertEqual(t._search.builds,1)
            self.assertIs(t.find(spelling,'K'),text_row)
            self.assertIs(t.find(other,'K'),unrelated)
            self.assertEqual(t._search.builds,1)
            first.set_member('K',BSLUUID(spelling))
            self.assertEqual(tuple(map(id,t.find_rows(query).items)),(id(last),id(first)))
            self.assertIs(t.find(uuid,'K'),last)
            self.assertEqual(t._search.builds,2)

    def test_malformed_and_foreign_uuid_protocols_never_execute(self):
        exact='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
        good=BSLUUID(exact)
        class HostText(str):
            def lower(self):raise AssertionError('host text callback')
            def __eq__(self,other):raise AssertionError('host text callback')
        class ForeignUUID(BSLUUID):
            def __eq__(self,other):raise AssertionError('foreign UUID equality')
            def __hash__(self):raise AssertionError('foreign UUID hashing')
        bad=object.__new__(BSLUUID)
        object.__setattr__(bad,'text',HostText(exact))
        uninitialized=object.__new__(BSLUUID)
        for value,err in ((bad,TypeError),(uninitialized,TypeError),
                          (ForeignUUID(exact),NotImplementedError)):
            for indexed in (False,True):
                with self.subTest(kind=type(value),indexed=indexed):
                    t=BSLValueTable(); t.columns.add('K')
                    first=t.add();first.set_member('K',good)
                    t.add().set_member('K',value)
                    if indexed:t.indexes.add('K')
                    # A later invalid cell cannot preempt an earlier match.
                    self.assertIs(t.find(BSLUUID(exact),'K'),first)
                    with self.assertRaises(err):t.find_rows(BSLStructure('K',good))
                    with self.assertRaises(err):t.find(value,'K')

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
        deleted_key=t.indexes.add('K');still_indexed=t.indexes.add('V')
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
        # Removing a key column shortens the public definition rather than
        # deleting its handle. An empty definition is not a search index.
        self.assertEqual(t.indexes.count(),2)
        self.assertIs(t.indexes.get_index(0),deleted_key)
        self.assertIs(t.indexes.get_index(1),still_indexed)
        self.assertEqual((list(deleted_key),list(still_indexed)),([],['V']))
        self.assertEqual(t._search.declarations,{(0,)})
        self.assertFalse(t._search.cache)
        hits=t.find_rows(BSLStructure('V','x')).items
        self.assertEqual(len(hits),len(t.rows))
        for actual,row in zip(hits,t.rows):
            self.assertIs(actual,row)
        self.assertEqual(tuple(t._search.cache),((0,),))
        t.indexes.delete(deleted_key)
        self.assertEqual(t.indexes.count(),1)
        self.assertIs(t.indexes.get_index(0),still_indexed)

    def test_native_index_definitions_survive_column_removal(self):
        from pathlib import Path
        from tests.native_observations import extract_payload

        root=Path(__file__).resolve().parents[1]
        source=(root/'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        archive=(root/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        outputs=[]
        vm=Interpreter(outputs.append)
        self.addCleanup(vm.close)
        vm.execute(source.split('#Область МассивыИСтруктуры',1)[0])
        for name in ('indexes.column-delete','indexes.columns-clear'):
            with self.subTest(name=name):
                code,=(line for line in source.splitlines()
                       if line.startswith(f'НаблюдатьТаблицы("{name}",'))
                outputs.clear()
                vm.execute_prepared(vm.prepare(code))
                self.assertEqual(len(outputs),1)
                self.assertEqual(extract_payload(outputs[0],'table.'+name),
                                 extract_payload(archive,'table.'+name))
    def test_bare_index_numeric_equality_and_epoch(self):
        from yadinassi.execution.codegen.native_bare_table import BareTable
        from yadinassi.execution.codegen.native_bare_collections import BareStructure
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
        from yadinassi.collections.plain_table_search import _Entry
        t=BSLValueTable();t.columns.add('K');t.add().set_member('K',1);t.indexes.add('K')
        f=BSLStructure('K',1);t.find_rows(f)
        entry=t._search.cache[(0,)]
        key=((Decimal,1),)
        self.assertEqual(entry.buckets[key],(0,))
        with self.assertRaises(TypeError):entry.buckets[key]=(0,)
        class Foreign:
            def __index__(self):raise AssertionError('foreign index hook')
        t._search.cache[(0,)]=_Entry(entry.epoch,MappingProxyType({key:(Foreign(),)}))
        with self.assertRaises(ValueError):t.find_rows(f)
        t._search.cache[(0,)]=_Entry(entry.epoch,MappingProxyType({key:(9,)}))
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
