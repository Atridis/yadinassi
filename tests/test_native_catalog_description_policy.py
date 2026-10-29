"""Synthetic acquisition policy, not native Description/runtime compatibility."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_description_policy as p
import catalog_description_measurement as measurement
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as lifecycle
import test_native_catalog_description_physical as physical

NONCE='a'*32


def provenance():
    value=lifecycle.provenance();value['actual_version']=protocol.VERSION
    value['sources']={name:'c'*64 for name in inputs.CATALOG_DESCRIPTION_SOURCE_FILES}
    return value


def witness(case='description8',nonce=NONCE,token='1'*32,value='',present=False,operation='observe'):
    raw=json.dumps(dict(schema=2,nonce=nonce,token=token,case=case,operation=operation,
        present=present,actual_description=value),ensure_ascii=True,separators=(',',':')).encode()
    return measurement.validate_witness(raw,nonce=nonce,token=token,case=case,operation=operation)


def evidence(report,identifier,index):
    snapshot=next(x for x in report['snapshots'] if x['id']==identifier)
    return dict(snapshot=identifier,token=str(index+1)*32,
        origin={k:snapshot['physical'][k] for k in ('bytes','sha256')},
        postimage={'bytes':65536,'sha256':'f'*64},logical=copy.deepcopy(snapshot['logical']))


def fixture(case='description8',nonce=NONCE,*,final=True,outcome='readback_matches',empty=False):
    report,_=lifecycle.fixture_report()
    base=p.empty_report(nonce,provenance(),description_case=case)
    for k in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):report[k]=base[k]
    length,created,updated=measurement.CASES[case]
    for i,identifier in enumerate(p.TARGETS):
        ev=evidence(report,identifier,i);value='' if i==0 or empty else (created if i==1 else updated)
        w=witness(case,nonce,ev['token'],value,i!=0)
        if i==0:observation=None
        else:
            actual=('Q' if outcome=='case_metadata_mismatch' else value) if outcome!='readback_differs' else 'other'
            kw={}
            if outcome=='layout_unresolved':kw['edit']=lambda fields:[*fields[:5],('_OTHER','NVC',0,length,0,'CI'),*fields[6:]]
            source_length=8 if outcome=='case_metadata_mismatch' and length==17 else length
            observation=physical.read(physical.source(source_length,actual,**kw))
        report['description_measurement']['states'].append(p.bind_state(identifier,ev,observation,w,report))
    if final:report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
    return report


def validate(report,final=True):
    return p.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=provenance(),final=final)


class DescriptionPolicyTests(unittest.TestCase):
    def test_exact_source_closure_lifecycle_and_private_projection(self):
        self.assertEqual(len(inputs.CATALOG_DESCRIPTION_SOURCE_FILES),41)
        self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(50,51,52))
        for case in p.CASES:
            report=fixture(case);self.assertEqual(validate(report),report)
            raw=protocol.encode(report['description_measurement'])
            for secret in ('NativeOracleItems','_DESCRIPTION',*measurement.CASES[case][1:]):
                self.assertNotIn(secret.encode('utf-8'),raw)
            self.assertNotIn('record_readback',report)
            self.assertTrue(report['accepted'])
            self.assertTrue(all(s['comparison']['native_compatibility']=='not_claimed' for s in report['description_measurement']['states'][1:]))
        validate(fixture(final=False),False)

    def test_present_empty_and_absent_baseline_remain_distinct(self):
        report=fixture(empty=True);validate(report)
        states=report['description_measurement']['states'];self.assertFalse(states[0]['witness']['present'])
        for state in states[1:]:
            self.assertTrue(state['witness']['present']);self.assertEqual(state['witness']['utf16_units'],0)
            self.assertEqual(state['comparison']['status'],'readback_matches')
        bad=copy.deepcopy(report);bad['description_measurement']['states'][1]['witness']['present']=False
        with self.assertRaises(OracleError):validate(bad)

    def test_difference_unresolved_and_metadata_mismatch_are_observations(self):
        for outcome in ('readback_differs','layout_unresolved','case_metadata_mismatch'):
            report=fixture('description17',outcome=outcome);validate(report)
            self.assertTrue(report['accepted'])
            self.assertEqual([s['comparison']['status'] for s in report['description_measurement']['states'][1:]],[outcome]*2)

    def test_bind_requires_same_observe_nonce_case_token_and_presence_without_append(self):
        report=fixture();report['description_measurement']['states']=[]
        ev=evidence(report,'baseline',0);good=witness(token=ev['token'])
        result=p.bind_state('baseline',ev,None,good,report)
        self.assertEqual(report['description_measurement']['states'],[])
        self.assertEqual(result['snapshot'],'baseline')
        changes=(dict(nonce='b'*32),dict(token='b'*32),dict(case='description17'),dict(operation='create'),
                 dict(present=True),dict(raw_sha256='bad'),dict(utf16_units=True),dict(actual_description='secret'))
        for change in changes:
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):
                p.bind_state('baseline',ev,None,replace(good,**change),report)
        for change in (dict(snapshot='created'),dict(token='bad'),dict(logical={}),dict(origin={'bytes':65536,'sha256':'f'*64}),dict(extra=True)):
            with self.subTest(change=change),self.assertRaises(OracleError):p.bind_state('baseline',{**ev,**change},None,good,report)
        with self.assertRaises(OracleError):p.bind_state('baseline',ev,physical.read(),good,report)

    def test_closed_fields_types_stale_joins_and_core_gates(self):
        source=fixture();mutations=[
            lambda r:r.update(schema=True),lambda r:r.update(extra=1),lambda r:r.update(record_readback={}),
            lambda r:r.update(description_case='unknown'),lambda r:r['provenance']['sources'].pop(next(iter(r['provenance']['sources']))),
            lambda r:r['description_measurement'].update(schema=True),lambda r:r['description_measurement'].update(profile_sha256='f'*64),
            lambda r:r['description_measurement'].update(extra=True),lambda r:r['description_measurement']['states'].reverse(),
            lambda r:r['description_measurement']['states'].pop(),lambda r:r['stages'][3]['checks'].update(reopened_row=False),
            lambda r:r['snapshots'][2]['logical'].update(count=2),lambda r:r['provenance'].update(actual_version='8.0'),
        ]
        paths=[(('witness','nonce'),'b'*32),(('witness','token'),'b'*32),(('witness','case'),'description17'),
            (('witness','operation'),'create'),(('witness','present'),False),(('witness','utf16_units'),True),
            (('origin','sha256'),'e'*64),(('origin','bytes'),True),(('postimage','bytes'),0),
            (('comparison','status'),'readback_matches_raw'),(('comparison','metadata_matches'),False),
            (('comparison','witness_sha256'),'e'*64),(('comparison','native_compatibility'),'supported'),
            (('comparison','count_evidence'),'not_distinguished'),(('comparison','physical','description_width'),999),
            (('comparison','physical','unicode_scalars'),True),(('comparison','physical','raw'),'secret')]
        for path,value in paths:
            def mutate(r,path=path,value=value):
                node=r['description_measurement']['states'][1]
                for k in path[:-1]:node=node[k]
                node[path[-1]]=value
            mutations.append(mutate)
        for edit in mutations:
            report=copy.deepcopy(source);edit(report)
            with self.subTest(edit=mutations.index(edit)),self.assertRaises(OracleError):validate(report)
        report=copy.deepcopy(source);s=report['description_measurement']['states'][2];s['observe_token']=s['witness']['token']='2'*32
        with self.assertRaises(OracleError):validate(report)

    def test_duplicate_malformed_wire_never_admitted(self):
        report=fixture();raw=protocol.encode(report)
        for bad in (raw[:-1]+b',"schema":50}',b'[]',b'null',b'NaN',b'\xff',b' '*32769,raw[:-2]):
            with self.assertRaises(OracleError):p.validate_report(bad,nonce=NONCE,provenance=provenance(),final=True)

    def test_cleanup_and_failure_always_scrub_capture(self):
        for key in fixture()['cleanup']:
            report=fixture();report['cleanup'][key]=False
            if key in report['stages'][-1]['checks']:
                report['stages'][-1]['checks'][key]=False;report['stages'][-1]['status']='failed'
            report.update(status='failed',failed_stage='cleanup',failure_kind='cleanup_unverified',accepted=False,artifacts=[])
            with self.assertRaises(OracleError):validate(report)
            p.discard_capture(report,final=True);self.assertIsNone(report['description_measurement'])
            # Host teardown failure does not pretend a previously successful
            # cleanup stage failed; the lifecycle core decides that shape.
            if key in report['stages'][-1]['checks']:validate(report)
        report,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),description_case='description8')
        for k in ('schema','lane','provenance',*p.EXTRA_KEYS):report[k]=base[k]
        p.discard_capture(report);p.validate_report(protocol.encode(report),nonce=NONCE,provenance=provenance())

    def test_compact_aggregate_is_not_nested_and_binds_each_final(self):
        reports=[fixture(),fixture('description17','b'*32,outcome='layout_unresolved')]
        digests=[hashlib.sha256(protocol.encode(r)+b'\n').hexdigest() for r in reports]
        value=p.build_aggregate(reports,digests,run_id=123,run_attempt=1)
        self.assertLess(len(protocol.encode(value)),2048)
        self.assertEqual([x['outcome'] for x in value['cases']],['readback_matches','layout_unresolved'])
        self.assertTrue(value['accepted']);self.assertNotIn('reports',value)
        for path,new in [(('schema',),True),(('cases',0,'report_sha256'),'e'*64),(('cases',1,'case'),'description8'),
                         (('cases',0,'source_sha256'),'f'*64),(('cases',0,'run_id'),True),(('cases',0,'run_attempt'),2),
                         (('cases',0,'outcome'),'supported'),(('extra',),{})]:
            bad=copy.deepcopy(value);node=bad
            for k in path[:-1]:node=node[k]
            node[path[-1]]=new
            with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(bad),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=digests)
        for broken in ([reports[0],reports[0]], [reports[0],fixture('description17','b'*32,final=False)]):
            with self.assertRaises(OracleError):p.build_aggregate(broken,digests,run_id=123,run_attempt=1)
        bad=copy.deepcopy(reports);bad[1]['stages'][1]['checks']['two_users_verified']=False
        with self.assertRaises(OracleError):p.build_aggregate(bad,digests,run_id=123,run_attempt=1)

if __name__=='__main__':unittest.main()
