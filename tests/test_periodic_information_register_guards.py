"""Temporal API/CONFIG guards using actual native content in synthetic transport."""
import copy,tempfile,unittest
from pathlib import Path
import test_periodic_information_register_native_replay as replay
from yadinassi import Interpreter
from yadinassi.database_context import FileDBContext
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage.config_information_register_metadata import project_information_register_metadata
from yadinassi.storage.config_catalog_attributes import CatalogAttributeError

class PeriodicRegisterGuards(unittest.TestCase):
    def raw(self,repeat=1):
        state=next(s for s in replay.CAPTURE['states'] if s['repeat']==repeat)
        uid=state['physical']['objects'][0]['metadata_uuid']
        return bytes.fromhex(next(f['raw_hex'] for f in replay.CAPTURE['configs'][str(repeat)] if f['filename']==uid))
    def parse(self,raw):return project_information_register_metadata(raw,budget=c._Budget(c.CatalogLimits()))
    def test_bare_second_profile_only_and_old_nonperiodic_retained(self):
        for repeat in (1,2):
            raw=self.raw(repeat);identity,*_=self.parse(raw);self.assertEqual(identity.periodicity,5)
            # Position18 has an independently observed zero-UUID pair prefix.
            prefix=b'00000000-0000-0000-0000-000000000000,00000000-0000-0000-0000-000000000000,5,'
            self.assertEqual(raw.count(prefix),1)
            for value in (b'"5"',b'1',b'2',b'3',b'4',b'6',b'-1'):
                bad=raw.replace(prefix,prefix[:-2]+value+b',')
                with self.subTest(value=value),self.assertRaises(CatalogAttributeError):self.parse(bad)
            old=raw.replace(prefix,prefix[:-2]+b'0,');self.assertEqual(self.parse(old)[0].periodicity,0)
    def test_period_member_collision_refused_before_row_admission(self):
        from yadinassi.storage.information_register_reader import read_information_register_rows
        state=next(s for s in replay.CAPTURE['states'] if s['state']=='filled')
        configs=copy.deepcopy(replay.CAPTURE['configs'][str(state['repeat'])])
        uid=state['physical']['objects'][0]['metadata_uuid']
        entry=next(x for x in configs if x['filename']==uid)
        raw=bytes.fromhex(entry['raw_hex']);self.assertIn(b'"Note"',raw)
        entry['raw_hex']=raw.replace(b'"Note"',b'"Period"').hex()
        image=replay.image(state,configs=configs)
        with self.assertRaises(c.InvalidStructure):
            read_information_register_rows(image.read_at,image.size,register_name=state['physical']['objects'][0]['name'])

    def execute(self,repeat,code):
        state=next(s for s in replay.CAPTURE['states'] if s['repeat']==repeat and s['state']=='filled')
        image=replay.image(state);name=state['physical']['objects'][0]['name'];lines=[]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();path=root/'1Cv8.1CD';before=image.read_at(0,image.size);path.write_bytes(before)
            vm=Interpreter(output=lines.append,database_context=FileDBContext(root))
            try:vm.execute('M=InformationRegisters.'+name+'; D=Date(2024,2,29,12,0,1); S=M.Select(); S.Next(); P=S.Product; K=New Structure("Product,Variant",P,1); '+code)
            finally:vm.close()
            self.assertEqual(path.read_bytes(),before)
        return lines
    def test_temporal_keys_range_modes_and_readonly_boundaries(self):
        bad=('M.Get(K)','M.GetLast("bad",K)','M.GetFirst(D,New Structure("Product",P))',
             'M.GetLast(D,New Structure("Product,Variant",P,-1))','M.Select(D,D,New Structure("Variant",1))',
             'M.Select(D,D,New Structure("Product",P),"unmeasured")','M.SliceLast(D,New Structure("Variant",1))',
             'M.GetLast(New Boundary(D),K)','S.Reset()','S.Period=D','M.CreateRecordManager()')
        code=''.join('Try '+x+'; Message("bad"); Except Message("closed"); EndTry; ' for x in bad)
        code+='G=M.GetLast(D,K); G.Price=999; Message(M.GetLast(D,K).Price=20); '
        code+='E=M.Select(D,D,New Structure("Product",P)); Message(E.Next()); Message(E.Next()); Message(Not E.Next()); Message(Not E.Next()); '
        for repeat in (1,2):self.assertEqual(self.execute(repeat,code),['closed']*len(bad)+['Да']*5)
    def test_slice_keyed_rows_localized_period_and_unmeasured_schema_fence(self):
        code='T=M.SliceLast(D); Message(T.Count()=3); R=T.FindRows(K); Message(R.Count()=1); Message(R[0].Price=20); Message(R[0].Период=D); Message(R[0].Note="middle"); '
        bad=('R[0].Period','T.Columns[1].ValueType','T.Columns[0].Title','T.Columns.Add("X")',
             'T.Add()','T.Copy()','T.Sort("Price")','T.Indexes','R[0].Price=999','R[0][0]=D',
             'T.Columns[0].Name="X"','ValueToStringInternal(T)')
        code+=''.join('Try '+x+'; Message("bad"); Except Message("closed"); EndTry; ' for x in bad)
        code+='Message(M.SliceLast(D,K)[0].Price=20); Message(M.SliceFirst(D,K)[0].Период=D); '
        for repeat in (1,2):self.assertEqual(self.execute(repeat,code),['Да']*5+['closed']*len(bad)+['Да']*2)
    def test_regular_value_table_schema_and_mutation_unchanged(self):
        lines=[];vm=Interpreter(output=lines.append)
        try:vm.execute('T=New ValueTable; T.Columns.Add("N"); T.Add().N=7; Message(T.Columns[0].ValueType.Types().Count()); Message(T[0].N); T.Copy(); T.Clear(); Message(T.Count());')
        finally:vm.close()
        self.assertEqual(lines,['0','7','0'])
if __name__=='__main__':unittest.main()
