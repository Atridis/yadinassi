import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.plain_value_table_runtime import BSLValueTable
from yadinassi.structures import BSLStructure, fill_property_values

class DirectTablePropertyTransfer(unittest.TestCase):
    def table(self):
        t=BSLValueTable();t.columns.add('K');r=t.add();r.set_member('K',D(1));return t,r
    def test_host_copy_invalidates_lazy_index_without_coercion(self):
        t,r=self.table();t.indexes.add('K')
        self.assertEqual(t.find_rows(BSLStructure('K',D(1))).items,[r])
        fill_property_values(r,BSLStructure('K',D('9.876')))
        self.assertEqual(r.get_member('K'),D('9.876'))
        self.assertEqual(t.find_rows(BSLStructure('K',D(1))).items,[])
        self.assertEqual(t.find_rows(BSLStructure('K',D('9.876'))).items,[r])
    def test_default_bsl_row_copy_updates_warmed_index(self):
        source='''T=New ValueTable;T.Columns.Add("K");R=T.Add();R.K=1;
T.Indexes.Add("K");Before=T.FindRows(New Structure("K",1)).Count();
S=New ValueTable;S.Columns.Add("K");SR=S.Add();SR.K=7;
ЗаполнитьЗначенияСвойств(R,SR);
OldCount=T.FindRows(New Structure("K",1)).Count();
Found=T.FindRows(New Structure("K",7));NewCount=Found.Count();Found[0].K=8;
Live=R.K;'''
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual(tuple(vm.variables[k] for k in ('before','oldcount','newcount','live')),(1,0,1,8))
    def test_readonly_detached_and_foreign_owner(self):
        t,r=self.table();t._bounded_slice_read=True
        target=BSLStructure('K');fill_property_values(target,r);self.assertEqual(target.get('K'),D(1))
        with self.assertRaises(ValueError):fill_property_values(r,BSLStructure('K',D(2)))
        t._bounded_slice_read=False;t.delete(r)
        with self.assertRaises(ValueError):fill_property_values(r,BSLStructure('K',D(2)))
        t,r=self.table();r._owner=object()
        with self.assertRaises(ValueError):fill_property_values(r,BSLStructure('K',D(2)))
    def test_index_cache_is_not_consumed(self):
        t,r=self.table();t.indexes.add('K');t._search.cache=object()
        fill_property_values(r,BSLStructure('K',D(2)))
        self.assertEqual(r.get_member('K'),D(2))
    def test_direct_structure_object_endpoint_stays_closed(self):
        from yadinassi.python_direct_fill import fill
        from yadinassi.experimental_naked_structure import new_structure
        t,r=self.table()
        with self.assertRaises(TypeError):fill(r,new_structure('K',D(2)))
        self.assertEqual(r.get_member('K'),D(1))
