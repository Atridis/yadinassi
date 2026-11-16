"""Synthetic diagnostic tests; none is native evidence."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from xml_order_packet import measurement as m,packet
import native_1c_xml_order as runner

class MeasurementTests(unittest.TestCase):
    def files(self,uuid='11111111-1111-1111-1111-111111111111',value='same'):
        return {'Configuration.xml':f'<Configuration uuid="{uuid}"><Name>{value}</Name></Configuration>'.encode()}
    def test_strict_digest_includes_uuid(self):
        a=self.files();b=self.files('22222222-2222-2222-2222-222222222222')
        self.assertNotEqual(packet.redump_digest(a),packet.redump_digest(b))
        self.assertEqual(m.compare(m.fingerprint(a),m.fingerprint(b))['slots'][0]['category'],'projected_uuid_token_difference_only')
        self.assertFalse(m.fingerprint(a)['acceptance_use'])
    def test_uuid_mask_never_hides_non_uuid_change(self):
        a=self.files();b=self.files('22222222-2222-2222-2222-222222222222','changed')
        self.assertEqual(m.compare(m.fingerprint(a),m.fingerprint(b))['slots'][0]['category'],'other_or_mixed_difference')
    def test_fingerprint_deterministic_and_no_raw_values(self):
        a=self.files();a['Module.bsl']=b'// private text'
        self.assertEqual(m.fingerprint(a),m.fingerprint(dict(reversed(list(a.items())))))
        out=json.dumps(m.fingerprint(a));self.assertNotIn('private text',out);self.assertNotIn('11111111-',out);self.assertNotIn('Configuration.xml',out)
    def test_inventory_gate(self):
        a=self.files();b={**a,'New.xml':b'<x/>'}
        self.assertEqual(m.compare(m.fingerprint(a),m.fingerprint(b))['comparison'],'inventory_changed')
    def test_namespace_changes_not_ignored(self):
        a={'Form.xml':b'<r xmlns:p="urn:a" q="p:T"/>'};b={'Form.xml':b'<r xmlns:p="urn:b" q="p:T"/>'}
        self.assertEqual(m.compare(m.fingerprint(a),m.fingerprint(b))['slots'][0]['category'],'other_or_mixed_difference')
    def test_bounds_and_dtd(self):
        for files in ({},{'x.xml':b'x'*(m.MAX_BYTES+1)},{'x.xml':b'<!DOCTYPE x><x/>'}):
            with self.assertRaises(ValueError):m.fingerprint(files)
    def test_partial_trace_does_not_become_witness(self):
        for events in ([],['create'],['create','open_effect']):
            raw=json.dumps(dict(nonce='a'*32,events=events)).encode()
            self.assertIn(m.partial_trace(raw,'a'*32)['state'],('empty','partial_or_complete'))
            with self.assertRaises(ValueError):packet.witness(raw,'a'*32,'baseline')
        self.assertEqual(m.partial_trace(None,'a'*32)['state'],'missing')
        self.assertEqual(m.partial_trace(b'{"private":"secret"}','a'*32)['state'],'invalid')
    def test_self_comparison_and_timeout_labels(self):
        r=dict(status='collected',redump='d'*64,failure='none')
        self.assertEqual(runner.assessment({'baseline':r})['baseline'],'baseline_reference_only')
        other=dict(status='failed',redump='e'*64,failure='timeout')
        self.assertEqual(runner.assessment({'baseline':r,'handler_changed':other})['handler_changed'],'timeout_cause_unknown')

if __name__=='__main__':unittest.main()
