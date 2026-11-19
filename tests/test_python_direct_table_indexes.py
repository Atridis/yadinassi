import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.collections.value_tables import BSLValueTable,BSLCollectionIndex,BSLCollectionIndexes
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectTableIndexTests(unittest.TestCase):
    def test_source_ast_prepared_public_protocol(self):
        source='T=New ValueTable;T.Columns.Add("Key");I=T.Indexes.Add("Key");N=T.Indexes.Count();S="";For Each X In T.Indexes Do For Each Name In X Do S=S+Name;EndDo;EndDo;R=T.Indexes[0][0];'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['n'],1);self.assertEqual(vm.variables['s'],'Key');self.assertEqual(vm.variables['r'],'Key')

    def test_foreign_deleted_and_readonly_operations(self):
        vm=Interpreter();vm.execute('A=New ValueTable;A.Columns.Add("Key");B=New ValueTable;B.Columns.Add("Key");I=A.Indexes.Add("Key");J=B.Indexes.Add("Key");')
        for source in ('A.Indexes.Delete(J)','A.Indexes[0]=J','I[0]="Other"'):
            vm.execute('Caught=False;Try '+source+';Except Caught=True;EndTry;');self.assertTrue(vm.variables['caught'])
        vm.execute('A.Indexes.Delete(I);R=I[0];')
        self.assertEqual(vm.variables['r'],'Key')
        vm.execute('Try A.Indexes.Delete(I);Except Caught=True;EndTry;');self.assertTrue(vm.variables['caught'])
        self.assertEqual(vm.execute('B.Indexes.Count()'),1)

    def test_noncanonical_owners_and_subclasses(self):
        class Table(BSLValueTable):pass
        class Indexes(BSLCollectionIndexes):pass
        values=[Table().indexes,Indexes(BSLValueTable())]
        table=BSLValueTable();table.columns.add('Key');index=table.indexes.add('Key');index.table=object();values.append(index)
        for value in values:
            vm=Interpreter();vm.variables['bad']=value
            with self.assertRaises(BoundaryViolation):vm.execute('Bad[0];')

    def test_bound_receiver_rechecked_after_arguments(self):
        vm=Interpreter();vm.execute('T=New ValueTable;T.Columns.Add("Key");I=T.Indexes;')
        def mutate():vm.variables['i'].table=object();return 'Key'
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('I.Add(Mutate());')
        self.assertEqual(vm.variables['t'].indexes.items,[])

    def test_budget_failure_is_atomic(self):
        vm=Interpreter();vm.execute('T=New ValueTable;T.Columns.Add("Key");T.Indexes.Add("Key");')
        with patch('yadinassi.collections.value_tables._MAX_INDEXES',1):
            vm.execute('Try T.Indexes.Add("Key");Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught']);self.assertEqual(vm.execute('T.Indexes.Count()'),1)

    def test_unconstructible_aliases_and_no_private_access(self):
        for name in ('CollectionIndex','CollectionIndexes','ИндексКоллекции','ИндексыКоллекции'):
            vm=Interpreter();seen=[];vm.register_function('Effect',lambda:seen.append(1))
            vm.execute('Try New '+name+'(Effect());Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(seen,[])
        vm=Interpreter();vm.execute('T=New ValueTable;T.Columns.Add("Key");I=T.Indexes.Add("Key");')
        for text in ('I.table','I._buckets','T.Indexes.items'):
            with self.assertRaises(Exception):vm.execute(text)

    def test_bounded_slice_child_cannot_bypass_table_policy(self):
        table=BSLValueTable();table.columns.add('Key');index=table.indexes.add('Key');table._bounded_slice_read=True
        vm=Interpreter();vm.variables.update(indexes=table.indexes,index=index)
        for source in ('Indexes.Add("Key")','Indexes[0]','Index[0]','For Each X In Indexes Do EndDo;'):
            with self.assertRaises(BoundaryViolation):vm.execute(source)
        self.assertEqual(len(table.indexes.items),1)
        table._bounded_slice_read=False
        def restrict():table._bounded_slice_read=True;return 'Key'
        vm.register_function('Restrict',restrict)
        with self.assertRaises(BoundaryViolation):vm.execute('Indexes.Add(Restrict());')
        self.assertEqual(len(table.indexes.items),1)
