"""Local bounds supplement to the separately source-bound native16 replay."""
import unittest
from yadinassi import Interpreter
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.values import BSLArray, BSLType
from yadinassi.serialization import value_to_string_internal, value_from_string_internal

FIXED='11111111-2222-4333-8444-555555555555'
ZERO='00000000-0000-0000-0000-000000000000'

class UUIDTypedPipelineCandidateTests(unittest.TestCase):
    def test_singleton_copy_array_and_closed_qualifiers(self):
        d=BSLTypeDescription('УникальныйИдентификатор')
        a=BSLArray(); a.items=[BSLType.UUID]
        for source in (d,a):
            self.assertEqual(BSLTypeDescription(source).types,(BSLType.UUID,))
            with self.assertRaises(ValueError): BSLTypeDescription(source,None)
        with self.assertRaises(ValueError): BSLTypeDescription('UUID,String')
        with self.assertRaises(ValueError): value_to_string_internal(d)
    def test_table_copy_load_fill_and_conversion(self):
        vm=Interpreter(lambda _:None)
        vm.execute('T=New ValueTable; T.Columns.Add("U",New TypeDescription("УникальныйИдентификатор")); R=T.Add();')
        self.assertEqual(str(vm.execute('R.U')),ZERO)
        vm.execute(f'R.U=New УникальныйИдентификатор("{FIXED}"); C=T.Copy();')
        self.assertEqual(str(vm.execute('C[0].U')),FIXED)
        vm.execute('T.Indexes.Add("U");')
        self.assertEqual(vm.execute(f'T.FindRows(New Structure("U",New УникальныйИдентификатор("{FIXED.upper()}"))).Count()'),1)
        vm.execute(f'R.U="{FIXED}";')
        self.assertEqual(str(vm.execute('R.U')),ZERO)
        self.assertEqual(vm.execute(f'T.FindRows(New Structure("U",New УникальныйИдентификатор("{FIXED}"))).Count()'),0)
        self.assertEqual(vm.execute(f'T.FindRows(New Structure("U",New УникальныйИдентификатор("{ZERO}"))).Count()'),1)
        vm.execute(f'T.FillValues(New УникальныйИдентификатор("{FIXED}"),"U"); A=T.UnloadColumn("U"); C.LoadColumn(A,"U");')
        self.assertEqual(str(vm.execute('C[0].U')),FIXED)
    def test_tree_copy(self):
        vm=Interpreter(lambda _:None)
        vm.execute(f'T=New ValueTree; T.Columns.Add("U",New TypeDescription("УникальныйИдентификатор")); R=T.Rows.Add(); R.Rows.Add().U=New УникальныйИдентификатор("{FIXED}"); C=T.Copy();')
        self.assertEqual(str(vm.execute('C.Rows[0].U')),ZERO)
        self.assertEqual(str(vm.execute('C.Rows[0].Rows[0].U')),FIXED)
    def test_nested_scalar_codec_but_not_descriptor_or_nested_type(self):
        a=BSLArray(); a.items=[BSLUUID(FIXED),BSLUUID(ZERO)]
        restored=value_from_string_internal(value_to_string_internal(a))
        self.assertEqual([str(x) for x in restored.items],[FIXED,ZERO])
        self.assertIs(value_from_string_internal(value_to_string_internal(BSLType.UUID)),BSLType.UUID)
        a.items=[BSLType.UUID]
        with self.assertRaises(ValueError): value_to_string_internal(a)
        with self.assertRaises(ValueError): value_from_string_internal('{"#",51e7a0d2-530b-11d4-b98a-008048da3034,{1,{"T",fc01b5df-97fe-449b-83d4-218a090e681e}}}')
