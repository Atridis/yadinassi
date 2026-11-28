"""Local bounds supplement to the separately source-bound native16 replay."""
import unittest
from yadinassi import Interpreter
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.types.unique_identifiers import BSLUUID
from yadinassi.types.values import BSLArray, BSLType
from yadinassi.formats.storage.serialization import value_to_string_internal, value_from_string_internal

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

    def test_decoded_map_and_fixed_map_indexed_actuals_use_typed_live_slots(self):
        from yadinassi.collections.maps import BSLFixedMap, BSLMap

        source=f'''
            Var C, Calls;
            Function FixedKey()
                Calls=Calls+1;
                Return New УникальныйИдентификатор("{FIXED}");
            EndFunction
            Function Read(V)
                Return V;
            EndFunction
            Procedure Write(V, Val Replacement)
                V=Replacement;
            EndProcedure
            Procedure Forward(V, Val Replacement)
                Write(V,Replacement);
            EndProcedure
            Calls=0;
            FKey=New УникальныйИдентификатор("{FIXED}");
            ZKey=New УникальныйИдентификатор("{ZERO}");
            M=New Map;
            M.Insert(FKey,ZKey);
            M.Insert(ZKey,FKey);
            M.Insert("{FIXED}","string key");
            M.Insert(True,"boolean key");
            M.Insert(1,"number key");
            A=New Array; A.Add(M); A.Add(New FixedMap(M));
            C=ValueFromStringInternal(ValueToStringInternal(A));
            MutableRead=Read(C[0][FixedKey()]);
            FixedRead=Read(C[1][ZKey]);
            Forward(C[0][FixedKey()],"replaced");
            Forward(C[0][True],"changed boolean");
            Refused=False;
            Try Forward(C[1][FKey],"forbidden"); Except Refused=True; EndTry;
        '''
        for prepared in (False,True):
            with self.subTest(prepared=prepared):
                vm=Interpreter()
                self.addCleanup(vm.close)
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                mutable,fixed=vm.variables['c'].items
                self.assertIs(type(mutable),BSLMap)
                self.assertIs(type(fixed),BSLFixedMap)
                self.assertEqual((str(vm.variables['mutableread']),str(vm.variables['fixedread'])),(ZERO,FIXED))
                self.assertEqual(vm.variables['calls'],2)
                self.assertTrue(vm.variables['refused'])
                self.assertEqual(vm.execute('C[0][FKey]'),'replaced')
                self.assertEqual(vm.execute('C[0][True]'),'changed boolean')
                self.assertEqual(vm.execute('C[0][1]'),'number key')
                self.assertEqual(vm.execute(f'C[0]["{FIXED}"]'),'string key')
                self.assertEqual(str(vm.execute('C[1][FKey]')),ZERO)
                self.assertEqual(str(vm.execute('M[FKey]')),ZERO)

    def test_later_argument_mutation_is_visible_through_decoded_map_reference(self):
        source=f'''
            Var C, K, Calls;
            Function Lookup()
                Calls=Calls+1;
                Return New УникальныйИдентификатор("{FIXED}");
            EndFunction
            Function Update()
                C[0][K]="updated";
                Return 0;
            EndFunction
            Function Observe(V, Val Ignored)
                Return V;
            EndFunction
            Calls=0;
            K=New УникальныйИдентификатор("{FIXED}");
            M=New Map; M.Insert(K,"original"); A=New Array; A.Add(M);
            C=ValueFromStringInternal(ValueToStringInternal(A));
            R=Observe(C[0][Lookup()],Update());
            R
        '''
        vm=Interpreter()
        self.addCleanup(vm.close)
        self.assertEqual(vm.execute_prepared(vm.prepare(source)),'updated')
        self.assertEqual(vm.variables['calls'],1)
