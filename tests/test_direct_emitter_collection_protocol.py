"""The single emitter uses compatible storage through collection boundaries."""
import unittest
from decimal import Decimal

from yadinassi import Interpreter, BSLError
from yadinassi.collections.structures import BSLKeyAndValue
from yadinassi.types.values import BSLArray


class DirectEmitterCollectionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.addCleanup(self.vm.close)

    def test_map_pairs_preserve_bsl_key_identity_when_retained(self):
        vm = self.vm
        vm.execute('M=New Map; M.Insert(True, "bool"); M.Insert(1, "number"); '
                   'A=New Array; For Each P In M Do A.Add(P); EndDo;')
        self.assertIs(type(vm.variables['a'][0]), BSLKeyAndValue)
        self.assertIsNot(vm.variables['a'][0], vm.variables['a'][1])
        self.assertIs(vm.execute('A[0].Ключ'), True)
        self.assertEqual(vm.execute('A[1].Key'), Decimal(1))
        self.assertEqual(vm.execute('A[0].Значение'), 'bool')
        self.assertEqual(vm.execute('A[1].Value'), 'number')
        self.assertEqual(list(vm.variables['m']), [True, 1])

    def test_map_loop_publishes_last_pair_without_touching_empty_slot(self):
        vm = self.vm
        vm.execute('M=New Map; M.Insert("only", 42); '
                   'P=Undefined; For Each P In M Do Break; EndDo; Kept=P; '
                   'M.Clear(); For Each P In M Do EndDo;')
        pair = vm.variables['p']
        self.assertIs(pair, vm.variables['kept'])
        self.assertIs(type(pair), BSLKeyAndValue)
        self.assertEqual(vm.execute('P.Key'), 'only')
        self.assertEqual(vm.execute('P.Value'), 42)

    def test_structure_keeps_original_spelling_and_fixed_snapshot(self):
        vm = self.vm
        vm.execute('S=New Structure("Name", 1); F=New FixedStructure(S); '
                   'S.Name=2; For Each P In F Do K=P.Key; V=P.Value; EndDo;')
        self.assertEqual(vm.variables['k'], 'Name')
        self.assertEqual(vm.variables['v'], 1)
        self.assertEqual(vm.execute('F.Name'), 1)
        self.assertEqual(vm.execute('S.Name'), 2)
        self.assertFalse(vm.execute('(S=New Structure("Name", 2))'))

    def test_table_brackets_share_schema_and_typed_setter(self):
        vm = self.vm
        vm.execute('T=New ValueTable; T.Columns.Add("N",New TypeDescription("Number")); '
                   'T.Add(); T[0]["n"]=7; T[0][0]=T[0]["N"]+2;')
        self.assertEqual(vm.execute('T[0].N'), 9)
        self.assertEqual(vm.execute('T.Columns["N"].Name'), 'N')
        with self.assertRaises(BSLError):
            vm.execute('T[0][-1]')
        with self.assertRaises(BSLError):
            vm.execute('T[0] = Undefined;')

    def test_deserialized_array_can_use_native_brackets(self):
        vm = self.vm
        vm.variables['payload'] = BSLArray()
        vm.variables['payload'].add(Decimal(5))
        vm.execute('S=New Structure("a", Payload); S.a[0]=6;')
        self.assertEqual(vm.execute('S.a[0]'), 6)
        self.assertEqual(vm.execute('(New FixedArray(S.a))[0]'), 6)
        with self.assertRaises(BSLError):
            vm.execute('S.a[-1]')
