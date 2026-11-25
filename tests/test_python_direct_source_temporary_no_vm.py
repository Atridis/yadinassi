"""Source temporary-storage semantics with lifetime VM dispatch poisoned."""
import unittest
import test_source_temporary_storage as existing


class SourceTemporaryNoVM(existing.SourceTemporaryTests):
    def test_same_side_structure_aliases(self):
        app = self.app('''Function Run() Export
            A=New Array; S=New Structure("Items",A);
            Address=PutToTempStorage(S,New UUID); A.Add(7);
            B=GetFromTempStorage(Address); B.Items.Add(8);
            Count=S.Items.Count(); DeleteFromTempStorage(Address);
            Return Count;
        EndFunction''')
        self.assertEqual(self.execute(app,'ServerAPI.Run()'), 2)
        self.assertEqual(app.temporary_storage._entries, {})

    def test_retained_mutation_is_remeasured_atomically(self):
        app = self.app('''Function Run() Export
            A=New Array; A.Add(1); Address=PutToTempStorage(A,New UUID);
            A.Add(A);
            Try Copy=GetFromTempStorage(Address); Except Return True; EndTry;
            Return False;
        EndFunction''')
        self.assertTrue(self.execute(app,'ServerAPI.Run()'))
        self.assertEqual(len(app.temporary_storage._entries),1)

    def test_native_closed_profile_replay(self):
        # The source-direct snapshot now admits bounded canonical typed maps too.
        import hashlib
        import json
        from pathlib import Path
        from yadinassi.types.errors import BSLError
        root=Path(__file__).resolve().parents[1]
        raw=(root/'tests/fixtures/native_temporary_storage_43056863128.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'0f475f9e8184890bdfa7f0d3e676970035586f7948365b0a1067275ba91486e7')
        source=(root/'scripts/temporary_storage_behavior/observe.bsl').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'a5d1cdce77f24f6801a55328812fc442c3978e5daae13fdebef807b355f520e7')
        declarations=source.decode().split('For CaseNo = 1 To 16 Do')[0]
        declarations+='\nFunction Run(Val CaseNo) Export Stage="read"; Return ObserveCase(CaseNo,Stage); EndFunction'
        app=self.app(declarations); expected=json.loads(raw)
        for n in range(1,17):
            with self.subTest(case=n):
                code=f'ServerAPI.Run({n})'
                if n == 11:
                    with self.assertRaises(BSLError):self.execute(app,code)
                elif n in (12,15):self.assertEqual(self.execute(app,code),'error')
                else:self.assertEqual(self.execute(app,code),expected[n-1])


if __name__ == '__main__':
    unittest.main()
