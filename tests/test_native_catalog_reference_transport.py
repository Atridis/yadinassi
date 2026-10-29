"""Mock native process only; exercise the real private sidecar transport boundary."""
import hashlib
import json
from unittest import mock
import unittest
import test_native_1c_db_oracle_stage as old
import catalog_reference_native as witness
import protocol


class ReferenceTransportTests(unittest.TestCase):
    def setUp(self):
        old.CommandCompletionBoundaryTests.setUp(self)
        self.native.reference_case='distinct_a'

    def launch(self, fault=None):
        def process(*args,**kwargs):
            control=json.loads((self.native.evidence/'control.json').read_text())
            completion={**control,'status':'error' if fault=='completion' else 'ok',
                        'phase':'reference_uuid' if fault=='completion' else 'complete'}
            (self.native.evidence/'completion.json').write_bytes(protocol.encode(completion))
            result={**control,'status':'ok','actual_version':protocol.VERSION,'user':'NativeOracleCRUD',
                    'role_verified':True,'nonprivileged':True,'users_verified':False,'metadata_version':1,
                    'count':1,'code':'K1','payload':'alpha','amount':'1.25','deletion_mark':False,
                    'same_reference':True,'payload_length':32,'amount_digits':9,'amount_scale':2}
            if fault=='result':result['count']=False
            (self.native.evidence/'result.json').write_bytes(protocol.encode(result))
            data={**control,'status':'ok','case':'distinct_a','before_present':False,'after_present':True,
                'before':'EFT'*3+'NNN','after':'TFE'*4,'actual_uuid':witness.CASES['distinct_a']}
            if fault=='case':data['case']='distinct_b'
            if fault=='token':data['token']='f'*32
            raw=protocol.encode(data);self.raw=raw
            path=self.native.evidence/'reference-observation.json'
            if fault=='missing':return
            if fault=='symlink':
                target=self.root/'outside-marker';target.write_bytes(raw);path.symlink_to(target)
            else:path.write_bytes(b'{' if fault=='malformed' else raw)
        return mock.patch.object(self.native,'process',side_effect=process)

    def test_success_binds_digest_token_after_strict_main_marker(self):
        with self.launch():self.native.enterprise(self.db,'create',token='b'*32)
        value,digest,token=self.native.reference_witness
        self.assertEqual((value.status,token),('ok','b'*32))
        self.assertEqual(digest,hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.native.reference_installation,self.native.reference_witness)
        self.assertEqual(list(self.native.evidence.iterdir()),[])

    def test_missing_malformed_swapped_and_failed_markers_never_save_witness(self):
        for fault in ('missing','malformed','case','token','result','completion','symlink'):
            with self.subTest(fault=fault),self.launch(fault),self.assertRaises(Exception):
                self.native.enterprise(self.db,'create',token='b'*32)
            self.assertIsNone(self.native.reference_witness)
            self.assertIsNone(self.native.reference_installation)
            self.assertEqual(list(self.native.evidence.iterdir()),[])
            if fault=='symlink':self.assertTrue((self.root/'outside-marker').is_file())

if __name__=='__main__':unittest.main()
