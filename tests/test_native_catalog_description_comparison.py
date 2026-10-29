"""Post-admission synthetic comparison and standalone projection bounds only."""
import json
import unittest
from dataclasses import replace
import test_native_catalog_description_physical as physical
import catalog_description_measurement as m

class DescriptionComparisonTests(unittest.TestCase):
    def witness(self,value,case):
        raw=json.dumps(dict(schema=2,present=True,nonce='a'*32,token='b'*32,case=case,
            operation='create',actual_description=value)).encode()
        return m.validate_witness(raw,nonce='a'*32,token='b'*32,case=case,operation='create')

    def test_actual_equality_separate_from_case_binding(self):
        observed=physical.read()
        out=m.compare_readback(observed,self.witness('AБ😀xy  ','description8'),case='description8')
        self.assertEqual(out['status'],'readback_matches')
        self.assertEqual(out['count_evidence'],'supplementary_utf16_units_observed')
        out=m.compare_readback(observed,self.witness('unexpected','description8'),case='description8')
        self.assertEqual(out['status'],'readback_differs')
        self.assertEqual(out['count_evidence'],'not_distinguished')
        out=m.compare_readback(observed,self.witness('AБ😀xy  ','description17'),case='description17')
        self.assertEqual(out['status'],'case_metadata_mismatch')
        with self.assertRaises(ValueError):
            m.compare_readback(observed,self.witness('AБ😀xy  ','description17'),case='description8')

    def test_short_value_not_count_proof(self):
        out=m.compare_readback(physical.read(physical.source(text='Я ')),self.witness('Я ','description8'),case='description8')
        self.assertEqual(out['status'],'readback_matches')
        self.assertEqual(out['count_evidence'],'not_distinguished')

    def test_unresolved_never_promoted_by_matching_witness(self):
        observed=physical.read(physical.source(edit=lambda ds:[*ds[:5],('_OTHER','NVC',0,8,0,'CI'),*ds[6:]]))
        out=m.compare_readback(observed,self.witness('AБ😀xy  ','description8'),case='description8')
        self.assertEqual(out['status'],'layout_unresolved')

    def test_standalone_independent_maxima_not_full_report_proof(self):
        observed=physical.read()
        out=m.compare_readback(observed,self.witness('x'*128,'description8'),case='description8')
        # Every public numeric domain bounded below 2**31; decimal upper bound
        # reserved independently, never by relying on correlations between keys.
        def maximize(v):
            if type(v) is dict:return {k:maximize(x) for k,x in v.items()}
            if type(v) is int:return 2147483647
            if type(v) is bool:return False
            return v
        maximum=maximize(out)
        maximum.update(status='case_metadata_mismatch',count_evidence='supplementary_utf16_units_observed')
        maximum['physical'].update(status='layout_unresolved',description_type='unresolved')
        encoded=json.dumps(maximum,ensure_ascii=True,separators=(',',':')).encode()+b'\n'
        self.assertEqual(len(encoded),1134)
        self.assertLess(len(encoded),2048)
        self.assertLess(2*len(encoded)+2*m.WITNESS_LIMIT,m.CAPTURE_LIMIT)
        for raw in ('NativeOracleItems','_DESCRIPTION','AБ','x'*128):
            self.assertNotIn(raw,encoded.decode())
        self.assertEqual(out['native_compatibility'],'not_claimed')

if __name__=='__main__':unittest.main()
