import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.collections.plain_value_table_runtime import BSLValueTable
from yadinassi.collections.value_tables import _adjust
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.types.type_qualifiers import BSLNumberQualifiers, BSLStringQualifiers

class TypedAssignmentTests(unittest.TestCase):
    def test_setters_defaults_and_existing_rows(self):
        t=BSLValueTable(); r=t.add()
        n=BSLTypeDescription('Number',BSLNumberQualifiers(D(2),D(0)))
        s=BSLTypeDescription('String',None,BSLStringQualifiers(D(3)))
        t.columns.add('N',n);t.columns.add('S',s)
        self.assertEqual(list(r),[D(0),''])
        for value in (D('8.6'),None,'bad'):
            r.set_member('N',value);r.set(D(1),'ABCD')
            self.assertEqual(list(r),[_adjust(n,value),'ABC'])
        self.assertEqual(list(t.add()),[D(0),''])
    def test_direct_and_prepared_typed_loop(self):
        source='''T=New ValueTable;T.Columns.Add("N",New TypeDescription("Number",New NumberQualifiers(2,0)));R=T.Add();For I=1 To 3 Do R.N=8.6;EndDo;V=R.N;'''
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual(vm.variables['v'],D(9))
    def test_untyped_identity_and_failed_write(self):
        t=BSLValueTable();t.columns.add('V');r=t.add();v=[]
        r.set_member('V',v);self.assertIs(r.get_member('V'),v)
        t._bounded_slice_read=True
        with self.assertRaises(ValueError):r.set_member('V',1)
        self.assertIs(r.get_member('V'),v)
    def test_failed_coercion_keeps_cell_and_index_epochs(self):
        from unittest.mock import patch
        t=BSLValueTable();t.columns.add('N',BSLTypeDescription('Number'));r=t.add()
        stamp=(t._storage.epoch,r.schema.data_epoch)
        for setter in (lambda:r.set_member('N',D(2)),lambda:r.set(D(0),D(2))):
            with patch('yadinassi.collections.plain_value_table_runtime._adjust',side_effect=ValueError('coercion')):
                with self.assertRaisesRegex(ValueError,'coercion'):setter()
            self.assertEqual(list(r),[D(0)])
            self.assertEqual((t._storage.epoch,r.schema.data_epoch),stamp)
    def test_typed_region_declines_but_untyped_remains_admitted(self):
        from yadinassi.execution.direct.python_direct_plain_tables import validate
        t=BSLValueTable();t.columns.add('N');t.add()
        self.assertTrue(validate(t,pure=True))
        t.columns._items[0].value_type=BSLTypeDescription('Number')
        self.assertFalse(validate(t,pure=True))
        self.assertTrue(validate(t))
