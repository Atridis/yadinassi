"""Synthetic closed PARAMS observations; never native/runtime evidence."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import params_slot_policy as p
import params_slot_observer as observer
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as lifecycle
NONCE='a'*32

def provenance():
    value=lifecycle.provenance();value['actual_version']=protocol.VERSION
    value['sources']={name:'c'*64 for name in inputs.CATALOG_PARAMS_SLOT_SOURCE_FILES}
    return value

def projection(outcome='terminated',marker='one'):
    return dict(recipe_id=observer.RECIPE_ID,recipe_sha256=observer.RECIPE_SHA256,
        data_logical_bytes=1204,blob_logical_bytes=1024,candidate_stride=301,candidate_slots=4,
        first_marker_class=marker,later_zero_count=1,later_one_count=1,later_other_count=1,
        filename_zero_count=1,filename_empty_count=0,filename_nonempty_count=1,
        dbnames_match_count=1,chain_outcome=outcome,linked_nonzero_count=1,
        unlinked_nonzero_count=1,runtime_support='not_claimed')

def evidence(report,identifier,index):
    snapshot=next(x for x in report['snapshots'] if x['id']==identifier)
    return dict(snapshot=identifier,token=str(index+1)*32,
        origin={k:snapshot['physical'][k]for k in ('bytes','sha256')},
        postimage={'bytes':65536,'sha256':'f'*64},logical=copy.deepcopy(snapshot['logical']))

def fixture(case='description8',nonce=NONCE,*,final=True,outcome='terminated'):
    report,_=lifecycle.fixture_report();base=p.empty_report(nonce,provenance(),description_case=case)
    for k in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):report[k]=base[k]
    for i,identifier in enumerate(p.TARGETS):
        report['params_slot_measurement']['states'].append(p.bind_state(evidence(report,identifier,i),report,projection(outcome)))
    if final:report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
    return report

def validate(report,final=True):return p.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=provenance(),final=final)

class ParamsSlotPolicyTests(unittest.TestCase):
    def test_all_hypothesis_outcomes_are_measurements_not_support(self):
        self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(56,57,58))
        self.assertEqual(len(inputs.CATALOG_PARAMS_SLOT_SOURCE_FILES),44)
        for case in p.CASES:
            for outcome in p.CHAIN_OUTCOMES:
                r=fixture(case,outcome=outcome);validate(r)
                self.assertEqual(r['params_slot_measurement']['runtime_support'],'not_claimed')
                for state in r['params_slot_measurement']['states']:
                    self.assertEqual(state['observation']['chain_outcome'],outcome)
                    self.assertGreater(state['observation']['unlinked_nonzero_count'],0)
        for marker in ('zero','one','other'):p.validate_projection(projection(marker=marker))
        validate(fixture(final=False),False)

    def test_projection_closed_arithmetic_types_recipe_and_privacy(self):
        source=projection()
        changes={'extra':'private','recipe_id':'other','recipe_sha256':'f'*64,'runtime_support':'accepted',
            'candidate_stride':True,'candidate_slots':4097,'data_logical_bytes':1203,'blob_logical_bytes':-1,
            'first_marker_class':'raw-byte','chain_outcome':'assumed_free','later_zero_count':2,
            'later_one_count':True,'later_other_count':-1,'filename_zero_count':0,'filename_empty_count':2,
            'filename_nonempty_count':0,'dbnames_match_count':2,'linked_nonzero_count':3,'unlinked_nonzero_count':0}
        for k,v in changes.items():
            with self.subTest(k=k),self.assertRaises(OracleError):p.validate_projection({**source,k:v})
        for key in source:
            bad=dict(source);del bad[key]
            with self.subTest(missing=key),self.assertRaises(OracleError):p.validate_projection(bad)
        for k in p.PROJECTION_COUNTS:
            with self.subTest(k=k),self.assertRaises(OracleError):p.validate_projection({**source,k:False})
        one=dict(source,candidate_slots=1,data_logical_bytes=301,**{k:0 for k in p.PROJECTION_COUNTS})
        p.validate_projection(one)
        for outcome in ('cycle','zero_marker_target'):
            with self.assertRaises(OracleError):p.validate_projection({**one,'chain_outcome':outcome})

    def test_bind_returns_without_append_and_detaches_mutable_inputs(self):
        r=fixture();r['params_slot_measurement']['states']=[];ev=evidence(r,'updated',0);ob=projection()
        state=p.bind_state(ev,r,ob);self.assertEqual(r['params_slot_measurement']['states'],[])
        ev['origin']['sha256']='0'*64;ob['chain_outcome']='cycle'
        self.assertNotEqual(state['origin']['sha256'],ev['origin']['sha256']);self.assertEqual(state['observation']['chain_outcome'],'terminated')
        for change in (dict(snapshot='created'),dict(token='bad'),dict(logical={}),dict(origin={'bytes':1,'sha256':'e'*64}),dict(postimage={'bytes':True,'sha256':'f'*64}),dict(private='secret')):
            with self.subTest(change=change),self.assertRaises(OracleError):p.bind_state({**evidence(r,'updated',0),**change},r,projection())
        with self.assertRaises(OracleError):p.bind_state(evidence(r,'applied',1),r,projection())

    def test_selected_logical_lengths_fit_same_postimage(self):
        report=fixture();state=report['params_slot_measurement']['states'][0]
        total=state['observation']['data_logical_bytes']+state['observation']['blob_logical_bytes']
        state['postimage']['bytes']=total;validate(report)
        state['postimage']['bytes']=total-1
        with self.assertRaises(OracleError):validate(report)
        report['params_slot_measurement']['states']=[]
        ev=evidence(report,'updated',0);ev['postimage']['bytes']=total-1
        with self.assertRaises(OracleError):p.bind_state(ev,report,projection())
        ev['postimage']['bytes']=total
        self.assertEqual(p.bind_state(ev,report,projection())['postimage']['bytes'],total)

    def test_stale_tokens_order_snapshot_and_root_closed(self):
        source=fixture()
        mutations=[(('params_slot_measurement','states',1,'observe_token'),'1'*32),
            (('params_slot_measurement','states',1,'snapshot'),'updated'),
            (('params_slot_measurement','states',0,'origin','sha256'),'e'*64),
            (('params_slot_measurement','schema'),True),(('params_slot_measurement','profile_sha256'),'e'*64),
            (('params_slot_measurement','runtime_support'),'claimed'),(('schema',),53),
            (('description_case',),'foreign'),(('private',),'secret'),(('description_failure',),{}),
            (('params_slot_measurement','states',0,'witness'),{'actual_uuid':'secret'})]
        for path,value in mutations:
            r=copy.deepcopy(source);node=r
            for k in path[:-1]:node=node[k]
            node[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
        for states in ([],source['params_slot_measurement']['states'][:1],list(reversed(source['params_slot_measurement']['states']))):
            r=copy.deepcopy(source);r['params_slot_measurement']['states']=states
            with self.assertRaises(OracleError):validate(r)

    def test_cleanup_provenance_wire_and_failed_capture(self):
        source=fixture()
        for key in source['cleanup']:
            r=copy.deepcopy(source);r['cleanup'][key]=False
            with self.subTest(key=key),self.assertRaises(OracleError):validate(r)
        for key in ('commit','tree','image'):
            r=copy.deepcopy(source);r['provenance'][key]='bad'
            with self.subTest(key=key),self.assertRaises(OracleError):validate(r)
        r=copy.deepcopy(source);r['provenance']['sources'].pop(next(iter(r['provenance']['sources'])))
        with self.assertRaises(OracleError):validate(r)
        for raw in (b'null',b'[]',b'NaN',b'\xff',b' '*32769,protocol.encode(source)[:-1]+b',"schema":56}'):
            with self.subTest(raw=raw[:15]),self.assertRaises(OracleError):p.validate_report(raw,nonce=NONCE,provenance=provenance(),final=True)
        r,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),description_case='description8')
        for k in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
        r['cleanup'].update(container_removed=True,private_staging_removed=True)
        with self.assertRaises(OracleError):validate(r)
        p.discard_capture(r,final=True);validate(r);self.assertIsNone(r['params_slot_measurement'])

    def test_aggregate_requires_two_actual_final_reports_and_digest_joins(self):
        reports=[fixture(case,nonce=n*32,outcome='cycle')for case,n in zip(p.CASES,('a','b'))]
        hashes=[hashlib.sha256(protocol.encode(r)).hexdigest()for r in reports]
        a=p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)
        self.assertEqual([x['outcome']for x in a['cases']],['measured','measured'])
        self.assertNotIn('reports',a)
        for key,value in [('accepted',False),('schema',55),('extra','secret')]:
            with self.subTest(key=key),self.assertRaises(OracleError):p.validate_aggregate(protocol.encode({**a,key:value}),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=hashes)
        for bad in ([hashes[1],hashes[0]],['e'*64,hashes[1]]):
            with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(a),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=bad)
        reports[1]['params_slot_measurement']['states'][0]['observation']['runtime_support']='claimed'
        with self.assertRaises(OracleError):p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)

if __name__=='__main__':unittest.main()
