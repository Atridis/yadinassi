"""Public collection behavior on the shared generator."""
import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError

class PrivateCollectionTests(unittest.TestCase):
    def test_table_multiple_columns_aliases_branches_and_partial_error(self):
        vm=Interpreter();self.addCleanup(vm.close)
        source='T=New ValueTable;Alias=T;T.Columns.Add("A");T.Columns.Add("B");For I=0 To 5 Do Row=Alias.Add();Row.A=I;If I<3 Then Row.B=I+1;Else Row.B=I+2;EndIf;EndDo;R=0;For I=0 To 5 Do R=R+T.Get(I).A+Alias.Get(I).B;EndDo;'
        plan=vm.prepare(source)
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(39))
        self.assertIs(vm.variables['t'],vm.variables['alias'])
        source='T=New ValueTable;T.Columns.Add("A");Row=T.Add();Row.A=7;R=Row.Missing;After=1;'
        with self.assertRaises(BSLRuntimeError):vm.execute(source)
        self.assertEqual(vm.variables['t'].get(D(0)).get_member('A'),D(7));self.assertNotIn('after',vm.variables)
    def test_list_direct_methods_and_native_payload(self):
        vm=Interpreter();self.addCleanup(vm.close)
        source='L=New ValueList;For I=0 To 7 Do Item=L.Add(I);Item.Value=I*2;EndDo;R=0;For I=0 To 7 Do R=R+L.Get(I).Value;EndDo;'
        plan=vm.prepare(source)
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(56))
