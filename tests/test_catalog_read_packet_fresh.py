import sys,unittest,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/native_1c_db_oracle'))
from catalog_read_packet import probe,scalar_wire as wire
from yadinassi.syntax.parser import parse
from yadinassi import Interpreter

def capture(s,first=None,second=None,fail=False):
    values=[s.names[0],s.record_ids[0],first or str(uuid.uuid4()),second or str(uuid.uuid4()),False,False,True,True,True,True,True,True]
    lines=[]
    for i,v in enumerate(values,1):
        scalar=('B1' if v else 'B0') if type(v) is bool else 'S'+str(len(v))+':'+''.join(f'{ord(c):04x}' for c in v)
        lines.append(f'CR-{i:02}: ['+('action-error' if fail and i==3 else 'ok|'+scalar)+']\n')
    return wire.C1+wire.C2+''.join(lines).encode()

class Fresh(unittest.TestCase):
    def test_fresh_parses_and_fails_unimplemented(self):
        s=probe.fresh_setup();src=probe.render_fresh(s);parse(src)
        self.assertEqual(src.count('.GetRef();'),2)
        out=[];Interpreter(out.append).execute(src)
        raw=('\n'.join(out)+'\n').encode()
        result=probe.assess_fresh(raw,s)
        self.assertFalse(result['accepted']);self.assertEqual(result['raw'],raw)
        self.assertTrue(any(r['status']=='action-error' for r in result['records']))
    def test_constant_fake_rejected_even_if_relations_lie(self):
        s=probe.fresh_setup();u=str(uuid.uuid4());r=probe.assess_fresh(capture(s,u,u),s)
        self.assertFalse(r['accepted']);self.assertIn('constant-fresh-uuid',r['reasons'])
    def test_failure_preserved(self):
        s=probe.fresh_setup();raw=capture(s,fail=True);r=probe.assess_fresh(raw,s)
        self.assertFalse(r['accepted']);self.assertEqual(r['raw'],raw)
        self.assertEqual(r['records'][2]['status'],'action-error')
    def test_different_native_captures_not_byte_equal(self):
        s=probe.fresh_setup();a,b=capture(s),capture(s)
        self.assertNotEqual(a,b)
        self.assertTrue(probe.assess_fresh(a,s)['accepted']);self.assertTrue(probe.assess_fresh(b,s)['accepted'])
    def test_known_uuid_substitution_rejected(self):
        s=probe.fresh_setup()
        for value in s.record_ids+s.metadata_ids+('00000000-0000-0000-0000-000000000000',):
            self.assertFalse(probe.assess_fresh(capture(s,first=value),s)['accepted'])
    def test_bound(self):
        raw=wire.C1+wire.C2+b''.join(f'CR-{i:02}: [ok|S64:{"0000"*64}]\n'.encode() for i in range(1,13))
        self.assertEqual(len(raw),3326);self.assertLess(len(raw),8192)
        self.assertEqual(len(wire.validate_output(raw,case_count=12)),12)
        with self.assertRaises(ValueError):wire.validate_output(raw)

if __name__=='__main__':unittest.main()
