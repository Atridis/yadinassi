import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/native_1c_db_oracle'))
import copy
import unittest
from catalog_read_packet import batch
from catalog_read_packet import scalar_wire
class BatchTests(unittest.TestCase):
    def setUp(self):self.b=batch.fresh()
    def test_rows_order(self):
        rows=self.b.rows
        self.assertNotEqual([r[0] for r in rows], sorted(r[0] for r in rows))
        self.assertNotEqual([r[1] for r in rows], sorted(r[1] for r in rows))
        self.assertNotEqual([r[2] for r in rows], sorted(r[2] for r in rows))
        self.assertEqual(sum(r[-1] for r in rows),1)
    def test_fragments(self):
        arts,ids=batch.fragments(self.b)
        self.assertTrue(batch.verify_redump(self.b,arts,ids,arts))
        for replacement in (b'<DescriptionLength>7</DescriptionLength>', b'<DescriptionLength xmlns="wrong">8</DescriptionLength>'):
            bad=dict(arts);key=next(iter(bad));bad[key]=bad[key].replace(b'<DescriptionLength>8</DescriptionLength>',replacement)
            with self.assertRaises(ValueError):batch.validate_fragments(self.b,bad,ids)
        badids=copy.deepcopy(ids);badids[self.b.setup.names[0]]['PAYLOAD_UUID']=self.b.setup.record_ids[0]
        with self.assertRaises(ValueError):batch.validate_fragments(self.b,arts,badids)
    def test_case_blocks(self):
        for block in ('cursor','fields','lookup','row4'):
            text,cases=batch.render_block(self.b,block)
            self.assertEqual(len(cases),24);self.assertLess(len(text.encode()),16384)
            self.assertNotIn('Write()',text);self.assertNotIn('Delete()',text)
            self.assertEqual(len(set(key for key,_ in cases)),24)
        text,_=batch.render_block(self.b,'cursor');self.assertIn('S.Reset()',text)
    def test_setup_states(self):
        for state,n in [('empty',0),('one',1),('several',3),('deleted',3),('reused',3)]:
            text=batch.render_setup(self.b,state)
            self.assertEqual(text.count('Object = Manager.CreateItem()'),2*n)
            self.assertLess(text.index('Функция CRCount'),text.index('Сообщить("CR-C1:'))
            if state in ('deleted','reused'):
                self.assertLess(text.index('Ghost.Write()'),text.index('Object.Code = "10"'))
                self.assertIn('Ghost.Delete()',text)
            if state=='reused':self.assertIn('Reused.Write()',text)
    def test_parse(self):
        from yadinassi.syntax.parser import parse
        for state in batch.STATES:parse(batch.render_setup(self.b,state))
        for block in ("cursor","fields","lookup","row4"):parse(batch.render_block(self.b,block)[0])
    def test_capture_controls(self):
        raw=scalar_wire.C1+scalar_wire.C2+b''.join(f'CR-{i:02}: [action-error]\n'.encode() for i in range(1,25))
        with self.assertRaises(ValueError):batch.read_capture(raw,self.b)
    def test_fresh_preserved(self):
        text=batch.probe.render_fresh(self.b.setup)
        self.assertEqual(text.count('.GetRef();'),2)
if __name__=='__main__':unittest.main()
