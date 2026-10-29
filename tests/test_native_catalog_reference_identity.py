"""Synthetic identity measurements are not native results or runtime codecs."""
import copy
import hashlib
import unittest

import test_native_1c_db_oracle_catalog_readonly_policy as old
import catalog_reference_identity as p
import inputs
import protocol
from contract import source_binding


def fixture(case='distinct_a', nonce=None, permutation=None):
    report,oracle=old.fixture()
    nonce=nonce or report['nonce']
    report.update(schema=p.SCHEMA,lane=p.LANE,reference_case=case,nonce=nonce,record_validation=p.VERDICT)
    report['provenance']['sources']={key:'c'*64 for key in inputs.CATALOG_REFERENCE_SOURCE_FILES}
    capture=report['record_readback']
    capture.update(schema=p.CAPTURE_SCHEMA,profile_id=p.PROFILE_ID,profile_sha256=p.PROFILE_SHA256,
        rendered_module_sha256=p.rendered_module_sha256(nonce,case),
        installation={'status':'succeeded','token':'e'*32,'witness_sha256':'e'*64})
    capture['audit']['nonce']=nonce
    capture['audit']['source_manifest_sha256']=source_binding(report['provenance'])
    for state in capture['states']:
        present=state['snapshot']!='baseline'
        perm=list(p.TOOL1CD if permutation is None else permutation) if present else None
        state['reference']={'witness_sha256':'b'*64,'before':'EFT'*4 if present else 'EFT'*3+'NNN',
            'after':'TFE'*4 if present else 'TFE'*3+'NNN', 'before_present':present,'after_present':present,
            'permutation':perm,'hypothesis_match':perm==p.TOOL1CD if present else None}
    return report


def validate(report):
    return p.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=report['provenance'],final=True)


class ReferenceIdentityTests(unittest.TestCase):
    def test_valid_unexpected_mapping_is_retained(self):
        report=fixture(permutation=list(range(16)))
        self.assertFalse(validate(report)['record_readback']['states'][1]['reference']['hypothesis_match'])

    def test_two_distinct_patterns_measure_same_non_hypothesis_bijection(self):
        permutation=list(reversed(range(16)))
        for value in p.CASE_UUIDS.values():
            canonical=bytes.fromhex(value.replace('-',''))
            physical=bytes(canonical[permutation.index(i)] for i in range(16))
            self.assertEqual(p.measure_permutation(value,physical),permutation)

    def test_ambiguous_wrong_type_and_noncanonical_private_values(self):
        uuid=p.CASE_UUIDS['distinct_a'];raw=bytes.fromhex(uuid.replace('-',''))
        for value,data in ((uuid,raw[:-1]),(uuid,bytearray(raw)),(uuid,bytes(16)),(uuid.upper(),raw)):
            with self.subTest(value=value,data=type(data)),self.assertRaises(p.ReadbackFailure):
                p.measure_permutation(value,data)
        for indexes in ([False]+list(range(1,16)),list(range(15))+[14],tuple(range(16))):
            with self.assertRaises(Exception):p.validate_permutation(indexes)

    def test_each_bound_field_and_cross_state_agreement(self):
        for field,value in (('profile_sha256','d'*64),('rendered_module_sha256','d'*64)):
            report=fixture();report['record_readback'][field]=value
            with self.assertRaises(Exception):validate(report)
        report=fixture();report['record_readback']['audit']['source_manifest_sha256']='d'*64
        with self.assertRaises(Exception):validate(report)
        report=fixture();report['record_readback']['states'][2]['reference']['permutation']=list(range(16))
        report['record_readback']['states'][2]['reference']['hypothesis_match']=False
        with self.assertRaises(Exception):validate(report)
        report=fixture();report['reference_case']='distinct_b'
        with self.assertRaises(Exception):validate(report)

    def test_empty_predicates_are_observations_not_prescribed_answers(self):
        for code in 'EFT':
            report=fixture()
            for state in report['record_readback']['states']:
                present=state['reference']['after_present']
                state['reference']['after']=code*12 if present else code*9+'NNN'
            validate(report)

    def test_aggregate_distinct_cases_nonces_and_cleanup(self):
        a=fixture();b=fixture('distinct_b',nonce='b'*32)
        raw_a,raw_b=protocol.encode(a),protocol.encode(b)
        result=p.aggregate_reports(raw_a,raw_b,provenance=a['provenance'])
        self.assertTrue(result['permutations_agree']);self.assertFalse(result['codec_approved'])
        self.assertEqual(result['cases'][0]['report_sha256'],hashlib.sha256(raw_a).hexdigest())
        for bad in (fixture('distinct_b'),fixture('distinct_a',nonce='b'*32)):
            with self.assertRaises(Exception):p.aggregate_reports(raw_a,protocol.encode(bad),provenance=a['provenance'])
        b['cleanup']['private_staging_removed']=False
        with self.assertRaises(Exception):p.aggregate_reports(raw_a,protocol.encode(b),provenance=a['provenance'])

    def test_aggregate_keeps_valid_disagreement_and_rejects_identity_drift(self):
        a=fixture();b=fixture('distinct_b',nonce='b'*32,permutation=list(range(16)))
        raw_a=protocol.encode(a)
        result=p.aggregate_reports(raw_a,protocol.encode(b),provenance=a['provenance'])
        self.assertFalse(result['permutations_agree'])
        self.assertEqual(result['cases'][1]['permutation'],list(range(16)))
        for field,value in (('commit','f'*40),('actual_version','other')):
            changed=copy.deepcopy(b);changed['provenance'][field]=value
            with self.assertRaises(Exception):p.aggregate_reports(raw_a,protocol.encode(changed),provenance=a['provenance'])
        changed=fixture();changed['record_readback']['installation']['token']=changed['record_readback']['states'][1]['observe_token']
        with self.assertRaises(Exception):validate(changed)

    def test_public_capture_never_exports_actual_uuid(self):
        raw=protocol.encode(fixture()['record_readback'])
        for value in p.CASE_UUIDS.values():self.assertNotIn(value.encode(),raw)

if __name__=='__main__':unittest.main()
