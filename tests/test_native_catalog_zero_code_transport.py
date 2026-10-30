"""Mock native process only; exercise the real private sidecar transport boundary."""
import hashlib
import json
from unittest import mock
import unittest
import test_native_1c_db_oracle_stage as old
import catalog_zero_code_measurement as witness
import protocol


class NumericCodeTransportTests(unittest.TestCase):
    def setUp(self):
        old.CommandCompletionBoundaryTests.setUp(self)
        self.native.zero_case='zero8'
        import catalog_zero_code_policy
        self.native.description_policy=catalog_zero_code_policy

    def launch(self, fault=None):
        def process(*args,**kwargs):
            control=json.loads((self.native.evidence/'control.json').read_text(encoding='utf-8'))
            completion={**control,'status':'error' if fault=='completion' else 'ok',
                        'phase':'reference_uuid' if fault=='completion' else 'complete'}
            (self.native.evidence/'completion.json').write_bytes(protocol.encode(completion))
            result={**control,'status':'ok','actual_version':protocol.VERSION,'user':'NativeOracleCRUD',
                    'role_verified':True,'nonprivileged':True,'users_verified':False,'metadata_version':1,
                    'count':1,'code':'observed_no_code','payload':'alpha','amount':'1.25','deletion_mark':False,
                    'same_reference':True,'payload_length':32,'amount_digits':9,'amount_scale':2}
            if fault=='result':result['count']=False
            (self.native.evidence/'result.json').write_bytes(protocol.encode(result))
            data={**control,'schema':1,'case':'zero8','present':True,'code_type':'string','code_state':'unavailable','actual_code':'',
                  'actual_uuid':'11111111-2222-3333-4444-555555555555','actual_description':'Name ',
                  'code_length':0,'description_length':8,'payload_length':32,'autonumbering':False}
            if fault=='case':data['case']='zero0'
            if fault=='token':data['token']='f'*32
            if fault=='type':data['code_type']=False
            raw=protocol.encode(data);self.raw=raw
            path=self.native.evidence/'zero-code-observation.json'
            if fault=='missing':return
            if fault=='symlink':
                target=self.root/'outside-marker';target.write_bytes(raw);path.symlink_to(target)
            else:path.write_bytes(b'{' if fault=='malformed' else raw)
        return mock.patch.object(self.native,'process',side_effect=process)

    def test_success_binds_digest_token_after_strict_main_marker(self):
        with self.launch():self.native.enterprise(self.db,'create',token='b'*32)
        value=self.native.description_witness
        self.assertEqual((value.actual_description,value.token),('Name ','b'*32))
        self.assertEqual(value.raw_sha256,hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(list(self.native.evidence.iterdir()),[])

    def test_missing_malformed_swapped_and_failed_markers_never_save_witness(self):
        for fault in ('missing','malformed','case','token','result','completion','symlink','type'):
            with self.subTest(fault=fault),self.launch(fault),self.assertRaises(Exception):
                self.native.enterprise(self.db,'create',token='b'*32)
            self.assertIsNone(self.native.description_witness)
            self.assertEqual(list(self.native.evidence.iterdir()),[])
            if fault=='symlink':self.assertTrue((self.root/'outside-marker').is_file())

    def test_preexisting_private_sidecar_is_rejected_before_native_process(self):
        path=self.native.evidence/'zero-code-observation.json';path.write_bytes(b'{}')
        with mock.patch.object(self.native,'process') as process,self.assertRaises(Exception):
            self.native.enterprise(self.db,'observe',token='b'*32)
        process.assert_not_called()

if __name__=='__main__':unittest.main()
