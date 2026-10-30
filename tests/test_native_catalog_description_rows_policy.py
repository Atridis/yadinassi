"""Synthetic source-bound typed rows parity; not fresh native execution."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_description_rows as p
import catalog_description_measurement as measurement
import catalog_description_physical as physical_reader
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as lifecycle
import test_native_catalog_description_physical as physical

NONCE='a'*32
NATIVE_UUID='52525252-5252-5252-5252-525252525252'

def provenance():
    value=lifecycle.provenance();value['actual_version']=protocol.VERSION
    value['sources']={name:'c'*64 for name in inputs.CATALOG_DESCRIPTION_ROWS_SOURCE_FILES}
    return value

def witness(case='description8',nonce=NONCE,token='1'*32,value='',present=False,actual_uuid=None):
    raw=json.dumps(dict(schema=3,nonce=nonce,token=token,case=case,operation='observe',
        present=present,actual_description=value,actual_uuid=(NATIVE_UUID if present else '') if actual_uuid is None else actual_uuid),ensure_ascii=True,separators=(',',':')).encode()
    return measurement.validate_witness(raw,nonce=nonce,token=token,case=case,operation='observe',rows=True)

def evidence(report,identifier,index):
    snapshot=next(x for x in report['snapshots'] if x['id']==identifier)
    return dict(snapshot=identifier,token=str(index+1)*32,origin={k:snapshot['physical'][k] for k in ('bytes','sha256')},postimage={'bytes':65536,'sha256':'f'*64},logical=copy.deepcopy(snapshot['logical']))

def observation(length,text,payload=32):
    value=physical.source(length,text,payload)
    return physical_reader.read_description_rows(value.read_at,value.size,catalog_name='NativeOracleItems')

def fixture(case='description8',nonce=NONCE,*,final=True,empty=False):
    report,_=lifecycle.fixture_report();base=p.empty_report(nonce,provenance(),description_case=case)
    for k in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):report[k]=base[k]
    length,created,updated=measurement.CASES[case]
    for i,identifier in enumerate(p.TARGETS):
        ev=evidence(report,identifier,i);value='' if i==0 or empty else created if i==1 else updated
        w=witness(case,nonce,ev['token'],value,i!=0)
        ob,typed=(None,None) if i==0 else observation(length,value,64 if identifier=='applied' else 32)
        report['description_measurement']['states'].append(p.bind_state(identifier,ev,ob,w,report,typed_uuid=typed))
    if final:report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
    return report

def validate(report,final=True):
    return p.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=provenance(),final=final)

class DescriptionRowsPolicyTests(unittest.TestCase):
    def test_four_actual_public_api_states_and_closed_inventory(self):
        self.assertEqual(len(inputs.CATALOG_DESCRIPTION_ROWS_SOURCE_FILES),42)
        self.assertNotIn('scripts/native_1c_db_oracle/catalog_description_policy.py',provenance()['sources'])
        self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(53,54,55))
        self.assertEqual(p.STAGES['applied'],'apply_cf')
        for case in p.CASES:
            r=fixture(case);validate(r);states=r['description_measurement']['states']
            self.assertEqual([s['snapshot'] for s in states],list(p.TARGETS))
            self.assertEqual([s['typed_uuid_verdict'] for s in states],['not_applicable','matches','matches','matches'])
            self.assertEqual([s['comparison']['physical']['payload_length'] for s in states[1:]],[32,32,64])
            self.assertEqual(states[3]['comparison']['physical']['record_size']-states[2]['comparison']['physical']['record_size'],64)
            raw=protocol.encode(r['description_measurement'])
            for secret in (NATIVE_UUID,'actual_uuid','actual_description','NativeOracleItems',*measurement.CASES[case][1:]):self.assertNotIn(secret.encode(),raw)
        validate(fixture(final=False),False)

    def test_present_empty_distinct_from_absent(self):
        r=fixture(empty=True);validate(r)
        self.assertFalse(r['description_measurement']['states'][0]['witness']['present'])
        for s in r['description_measurement']['states'][1:]:
            self.assertTrue(s['witness']['present']);self.assertEqual(s['comparison']['native_utf16_units'],0)

    def test_bind_returns_without_append_and_rejects_old_private_schema(self):
        r=fixture();r['description_measurement']['states']=[];ev=evidence(r,'baseline',0);w=witness(token=ev['token'])
        self.assertEqual(p.bind_state('baseline',ev,None,w,r)['typed_uuid_verdict'],'not_applicable');self.assertEqual(r['description_measurement']['states'],[])
        for change in (dict(schema=2),dict(schema=True),dict(actual_uuid=NATIVE_UUID),dict(nonce='e'*32),dict(token='e'*32),dict(case='description17'),dict(operation='create'),dict(utf16_units=True),dict(present=True)):
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):p.bind_state('baseline',ev,None,replace(w,**change),r)
        with self.assertRaises(OracleError):p.bind_state('baseline',ev,None,w,r,typed_uuid=UUID(NATIVE_UUID))

    def test_actual_typed_uuid_not_seed_or_string_and_description_mismatch_fail(self):
        r=fixture();r['description_measurement']['states']=r['description_measurement']['states'][:1]
        ev=evidence(r,'created',1);text=measurement.CASES['description8'][1];w=witness(token=ev['token'],value=text,present=True);ob,typed=observation(8,text)
        self.assertEqual(typed,UUID(NATIVE_UUID))
        for wrong in (None,NATIVE_UUID,UUID(int=0),UUID(int=1)):
            with self.subTest(wrong=wrong),self.assertRaises(OracleError):p.bind_state('created',ev,ob,w,r,typed_uuid=wrong)
        for change in (dict(actual_uuid='bad'),dict(actual_uuid=str(UUID(int=0))),dict(actual_uuid='{'+NATIVE_UUID+'}'),dict(actual_uuid=' '+NATIVE_UUID),dict(actual_uuid='AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'),dict(actual_description='other',utf16_units=5,scalar_count=5,trailing_spaces=0)):
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):p.bind_state('created',ev,ob,replace(w,**change),r,typed_uuid=typed)
        unresolved=replace(ob,status='layout_unresolved',records=None,placements=(),record_size=0)
        with self.assertRaises(OracleError):p.bind_state('created',ev,unresolved,w,r,typed_uuid=typed)
        wrong,typed=observation(17,text)
        with self.assertRaises(OracleError):p.bind_state('created',ev,wrong,w,r,typed_uuid=typed)

    def test_applied_qualifier_and_stale_identity_order_fail_closed(self):
        r=fixture();r['description_measurement']['states']=r['description_measurement']['states'][:3]
        ev=evidence(r,'applied',3);text=measurement.CASES['description8'][2];w=witness(token=ev['token'],value=text,present=True);ob,typed=observation(8,text,32)
        with self.assertRaises(OracleError):p.bind_state('applied',ev,ob,w,r,typed_uuid=typed)
        ob,typed=observation(8,text,64)
        for change in (dict(logical={}),dict(snapshot='updated'),dict(origin={'bytes':65536,'sha256':'e'*64}),dict(extra=True)):
            with self.assertRaises(OracleError):p.bind_state('applied',{**ev,**change},ob,w,r,typed_uuid=typed)
        r['description_measurement']['states']=r['description_measurement']['states'][:2]
        with self.assertRaises(OracleError):p.bind_state('applied',ev,ob,w,r,typed_uuid=typed)

    def test_serialized_closed_types_parity_cleanup_and_full_lifecycle(self):
        source=fixture();mutations=[(('schema',),True),(('extra',),1),(('stages',3,'status'),'not_started'),(('description_measurement','profile_sha256'),'e'*64),(('description_measurement','states'),source['description_measurement']['states'][:3])]
        for i in range(4):
            prefix=('description_measurement','states',i)
            for path,val in [(('witness','nonce'),'e'*32),(('witness','token'),'e'*32),(('origin','sha256'),'e'*64),(('postimage','bytes'),True),(('typed_uuid_verdict',),'differs' if i else 'matches'),(('witness','schema'),3)]:mutations.append((prefix+path,val))
            if i:
                for path,val in [(('status',),'readback_differs'),(('metadata_matches',),False),(('physical','payload_length'),32 if i==3 else 64),(('physical','description_width'),999)]:mutations.append((prefix+('comparison',)+path,val))
        for k in source['cleanup']:mutations.append((('cleanup',k),False))
        for path,value in mutations:
            r=copy.deepcopy(source);node=r
            for k in path[:-1]:node=node[k]
            node[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
        r=copy.deepcopy(source);s=r['description_measurement']['states'][3];s['observe_token']=s['witness']['token']='3'*32
        with self.assertRaises(OracleError):validate(r)

    def test_failed_lifecycle_scrubs_capture(self):
        r,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),description_case='description8')
        for k in ('schema','lane','provenance',*p.EXTRA_KEYS):r[k]=base[k]
        with self.assertRaises(OracleError):validate(r,False)
        p.discard_capture(r);self.assertIsNone(r['description_measurement']);validate(r,False)

    def test_wire_and_compact_aggregate_require_actual_final_reports(self):
        r=fixture();raw=protocol.encode(r)
        for bad in (raw[:-1]+b',"schema":53}',b'null',b'[]',b'NaN',b'\xff',b' '*32769):
            with self.assertRaises(OracleError):p.validate_report(bad,nonce=NONCE,provenance=provenance(),final=True)
        reports=[r,fixture('description17','b'*32)];hashes=[hashlib.sha256(protocol.encode(x)+b'\n').hexdigest() for x in reports]
        aggregate=p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)
        self.assertNotIn('reports',aggregate);self.assertEqual([x['outcome'] for x in aggregate['cases']],['readback_matches']*2)
        aggregate['cases'][0]['report_sha256']='e'*64
        with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(aggregate),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=hashes)
        reports[1]['description_measurement']['states'][3]['typed_uuid_verdict']='differs'
        with self.assertRaises(OracleError):p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)


def failure_fixture(*,final=True):
    r=fixture(final=final)
    r.update(status='failed',failed_stage='apply_cf',failure_kind='unexpected_failure',accepted=False,artifacts=[])
    r['snapshots']=r['snapshots'][:8];r['comparisons']=r['comparisons'][:3]
    for stage in r['stages'][7:-1]:
        stage['status']='failed' if stage['id']=='apply_cf' else 'not_started'
        stage['checks']={k:False for k in stage['checks']}
    p.discard_capture(r)
    return r

class DescriptionDiagnosticTests(unittest.TestCase):
    def test_exact_existing_domain_and_special_finite_classes(self):
        self.assertEqual(sum(len(v) for k,v in p.DIAGNOSTICS.items() if k not in ('adapter','parity','unclassified','builtin')),232)
        count=0
        for cls,category in p._READER_CATEGORIES.items():
            for code in p.DIAGNOSTICS[category]:
                d=p.diagnostic_for(cls(code),snapshot='applied',phase='public_reader')
                self.assertEqual((d['category'],d['code'],d['phase']),(category,code,'public_reader'));count+=1
        self.assertGreater(count,150)
        for code in ('metadata_profile','one_active_row'):
            d=p.diagnostic_for(p.DescriptionAdapterError(code),snapshot='applied',phase='public_reader')
            self.assertEqual((d['category'],d['code'],d['phase']),('adapter',code,'adapter'))
        for code in ('metadata','description','typed_uuid'):
            error=p.DescriptionParityError(code);self.assertEqual(error.kind,'transport_invalid')
            d=p.diagnostic_for(error,snapshot='applied',phase='comparison')
            self.assertEqual((d['category'],d['code'],d['phase']),('parity',code,'comparison'))
            self.assertEqual(p.wrap_failure(error,snapshot='applied',phase='comparison').kind,'transport_invalid')

    def test_no_error_text_properties_subclasses_or_hostile_code_hooks(self):
        called=[]
        class Hostile(p._catalog_errors.UnsupportedLayout):
            def __getattribute__(self,name):called.append(name);raise AssertionError('private hook')
            def __str__(self):called.append('str');raise AssertionError('private str')
            def __repr__(self):called.append('repr');raise AssertionError('private repr')
        class HostileText(str):
            def __hash__(self):called.append('hash');raise AssertionError('private hash')
            def __eq__(self,other):called.append('eq');raise AssertionError('private eq')
        class HostileDict(dict):
            def get(self,*args):called.append('get');raise AssertionError('private get')
        error=p._catalog_errors.UnsupportedLayout('declaration_mismatch')
        error.__dict__=HostileDict(code='declaration_mismatch')
        for error in (Hostile('secret'),TypeError('private path and data'),
                      p._catalog_errors.UnsupportedLayout('private'),p._catalog_errors.UnsupportedLayout(HostileText('declaration_mismatch')),error):
            d=p.diagnostic_for(error,snapshot='applied',phase='public_reader')
            self.assertEqual((d['category'],d['code']),('unclassified','unknown_exception'))
            self.assertEqual(p.wrap_failure(error,snapshot='applied',phase='public_reader').kind,'unexpected_failure')
        self.assertEqual(called,[])

    def test_runtime_additions_are_closed_and_old_domain_preserved(self):
        original=p._binding_diagnostics.DIAGNOSTICS
        self.assertEqual(sum(map(len,original.values())),193)
        self.assertEqual(sum(map(len,p._RUNTIME_DIAGNOSTICS.values())),39)
        self.assertEqual(sum(map(len,p.DIAGNOSTICS.values())),239)
        for category,codes in original.items():
            self.assertLessEqual(codes,p.DIAGNOSTICS[category])
        for category,codes in p._RUNTIME_DIAGNOSTICS.items():
            self.assertFalse(set(codes)&set(original[category]))
        for cls,category in p._READER_CATEGORIES.items():
            for code in p._RUNTIME_DIAGNOSTICS.get(category,()):
                diagnostic=p.diagnostic_for(cls(code),snapshot='applied',phase='public_reader')
                report=failure_fixture();self.assertTrue(p.set_failure(report,diagnostic,final=True));validate(report)
                for wrong in (code+'_private','transport_unknown','config_projection_unknown'):
                    self.assertEqual(p.diagnostic_for(cls(wrong),snapshot='applied',phase='public_reader')['category'],'unclassified')

    def test_closed_chain_codes_remain_finite_reader_failures(self):
        for code in ('dbnames_chain_reference','dbnames_chain_cycle','dbnames_chain_zero_target','dbnames_chain_unlinked'):
            error=p._catalog_errors.UnsupportedLayout(code)
            value=p.diagnostic_for(error,snapshot='applied',phase='public_reader')
            self.assertEqual((value['category'],value['code']),('unsupported_layout',code))
            report=failure_fixture();self.assertTrue(p.set_failure(report,value,final=True));validate(report)
            self.assertIsNone(report['description_measurement']);self.assertFalse(report['accepted'])
            for phase in ('comparison','postimage','cleanup'):
                self.assertEqual(p.diagnostic_for(error,snapshot='applied',phase=phase)['category'],'unclassified')
            self.assertEqual(p.diagnostic_for(p._catalog_errors.UnsupportedLayout(code+'_private'),snapshot='applied',phase='public_reader')['category'],'unclassified')

    def test_exact_value_error_only_without_private_object_access(self):
        called=[]
        class Private:
            def __str__(self):called.append('str');raise AssertionError
            def __repr__(self):called.append('repr');raise AssertionError
        class Derived(ValueError):
            def __getattribute__(self,name):called.append(name);raise AssertionError
        error=ValueError(Private());error.code=Private()
        diagnostic=p.diagnostic_for(error,snapshot='applied',phase='public_reader')
        self.assertEqual(diagnostic,dict(snapshot='applied',phase='public_reader',category='builtin',code='value_error'))
        report=failure_fixture();self.assertTrue(p.set_failure(report,diagnostic,final=True));validate(report)
        self.assertEqual(p.wrap_failure(error,snapshot='applied',phase='public_reader').kind,'unexpected_failure')
        for phase in p.PHASES:
            if phase!='public_reader':self.assertEqual(p.diagnostic_for(error,snapshot='applied',phase=phase)['category'],'unclassified')
        for other in (Derived(Private()),TypeError(Private()),RuntimeError(Private()),KeyError(Private())):
            self.assertEqual(p.diagnostic_for(other,snapshot='applied',phase='public_reader')['category'],'unclassified')
        for phase in ('postimage','comparison','cleanup','adapter'):
            with self.assertRaises(OracleError):p._diagnostic(dict(diagnostic,phase=phase))
        with self.assertRaises(OracleError):p._diagnostic(dict(diagnostic,snapshot='baseline'))
        self.assertEqual(called,[])

    def test_attribute_dictionary_keys_never_invoke_foreign_hooks(self):
        called=[]
        class Collision:
            def __init__(self,target):self.target=target
            def __hash__(self):return hash(self.target)
            def __eq__(self,other):called.append('eq');raise AssertionError('private equality')
        class Text(str):
            def __hash__(self):called.append('hash');raise AssertionError('private hash')
            def __eq__(self,other):called.append('eq');raise AssertionError('private equality')
        class Dictionary(dict):
            def __iter__(self):called.append('iter');raise AssertionError('private iter')
            def __len__(self):called.append('len');raise AssertionError('private len')
            def get(self,*args):called.append('get');raise AssertionError('private get')
        factories=(lambda:p._catalog_errors.UnsupportedLayout('dbnames_chain_cycle'),
            lambda:p.DescriptionAdapterError('one_active_row'),
            lambda:p.DescriptionParityError('metadata'),lambda:OracleError('transport_invalid'))
        for factory in factories:
            for target in ('code','kind'):
                for fields in ({Collision(target):'secret'},Dictionary(code='metadata',kind='transport_invalid'),
                               {str(i):None for i in range(9)}):
                    error=factory();error.__dict__=fields
                    for phase in p.PHASES:
                        value=p.diagnostic_for(error,snapshot='applied',phase=phase)
                        self.assertEqual(value['category'],'unclassified')
                        self.assertEqual(p.wrap_failure(error,snapshot='applied',phase=phase).kind,'unexpected_failure')
        error=p._catalog_errors.UnsupportedLayout('dbnames_chain_cycle')
        error.__dict__={'code':'dbnames_chain_cycle',**{str(i):None for i in range(7)}}
        self.assertEqual(p.diagnostic_for(error,snapshot='applied',phase='public_reader')['code'],'dbnames_chain_cycle')
        # A string subclass can be inserted without its hook via an inherited
        # hash implementation; classification must reject by exact type first.
        class Key(str):
            def __eq__(self,other):called.append('keyeq');raise AssertionError
            __hash__=str.__hash__
        error.__dict__={Key('code'):'dbnames_chain_cycle'}
        self.assertEqual(p.diagnostic_for(error,snapshot='applied',phase='public_reader')['category'],'unclassified')
        self.assertEqual(called,[])

    def test_trusted_context_and_notes_fit_eight_attribute_limit(self):
        errors=[p._catalog_errors.UnsupportedLayout('dbnames_chain_cycle'),
            p.DescriptionAdapterError('one_active_row'),p.DescriptionParityError('metadata'),OracleError('transport_invalid')]
        for error in errors:
            error.failure_context={'operation':'inventory'}
            error.failure_context_stage='apply_cf'
            error.add_note('private note never read')
            self.assertLessEqual(len(error.__dict__),5)
            fields=dict(error.__dict__)
            for index in range(8-len(fields)):fields['extra_'+str(index)]=None
            error.__dict__=fields
            if type(error) is OracleError:
                self.assertEqual(p.wrap_failure(error,snapshot='applied',phase='public_reader').kind,'transport_invalid')
            else:
                phase='comparison' if type(error) is p.DescriptionParityError else 'public_reader'
                self.assertNotEqual(p.diagnostic_for(error,snapshot='applied',phase=phase)['category'],'unclassified')
            fields['ninth']=None
            self.assertEqual(p.diagnostic_for(error,snapshot='applied',phase='public_reader')['category'],'unclassified')
            self.assertEqual(p.wrap_failure(error,snapshot='applied',phase='public_reader').kind,'unexpected_failure')

    def test_recipe_binds_closed_marker1_profile_and_rejects_prior_hash(self):
        self.assertEqual(p.PROFILE_DESCRIPTION['params_slot_policy'],'closed_marker1_chain_v1')
        prior=dict(p.PROFILE_DESCRIPTION);del prior['params_slot_policy']
        prior_hash=hashlib.sha256(protocol.encode(prior)).hexdigest()
        self.assertNotEqual(prior_hash,p.PROFILE_SHA256)
        report=fixture();report['description_measurement']['profile_sha256']=prior_hash
        with self.assertRaises(OracleError):validate(report)

    def test_unknown_metaclass_hash_and_equality_never_run(self):
        called=[]
        class HostileMeta(type):
            def __hash__(cls):called.append('class hash');raise AssertionError('private hash')
            def __eq__(cls,other):called.append('class eq');raise AssertionError('private eq')
        class Unknown(Exception,metaclass=HostileMeta):pass
        for phase in p.PHASES:
            error=Unknown()
            d=p.diagnostic_for(error,snapshot='applied',phase=phase)
            self.assertEqual((d['category'],d['code']),('unclassified','unknown_exception'))
            self.assertEqual(p.wrap_failure(error,snapshot='applied',phase=phase).kind,'unexpected_failure')
        self.assertEqual(called,[])

    def test_reader_codes_only_after_reader_phase_not_superseding_integrity(self):
        for phase in ('origin','postimage','cleanup','adapter','comparison'):
            d=p.diagnostic_for(p._catalog_errors.UnsupportedLayout('declaration_mismatch'),snapshot='applied',phase=phase)
            self.assertEqual((d['phase'],d['category'],d['code']),(phase,'unclassified','unknown_exception'))
        for error,phase in ((p.DescriptionAdapterError('one_active_row'),'postimage'),(p.DescriptionParityError('metadata'),'public_reader')):
            self.assertEqual(p.diagnostic_for(error,snapshot='applied',phase=phase)['category'],'unclassified')
        for phase in ('bad',None,True):
            with self.assertRaises(OracleError):p.diagnostic_for(ValueError(),snapshot='applied',phase=phase)

    def test_failure_only_last_snapshot_stage_and_cleanup_binding(self):
        r=failure_fixture();d=p.diagnostic_for(p._catalog_errors.UnsupportedLayout('declaration_mismatch'),snapshot='applied',phase='public_reader')
        self.assertTrue(p.set_failure(r,d,final=True));validate(r)
        self.assertIsNone(r['description_measurement']);self.assertFalse(r['accepted'])
        native=failure_fixture(final=False);self.assertTrue(p.set_failure(native,d));validate(native,False)
        with self.assertRaises(OracleError):validate(native,True)
        for key in r['cleanup']:
            bad=copy.deepcopy(r);bad['cleanup'][key]=False
            self.assertFalse(p.set_failure(bad,d,final=True));self.assertNotIn('description_failure',bad)
        for changes in (dict(snapshot='updated'),dict(phase='postimage'),dict(code='private'),dict(extra='secret')):
            bad=copy.deepcopy(r);bad['description_failure']={**d,**changes}
            with self.assertRaises(OracleError):validate(bad)
        bad=fixture();bad['description_failure']=d
        with self.assertRaises(OracleError):validate(bad)
        self.assertFalse(p.set_failure(bad,d,final=True));self.assertNotIn('description_failure',bad)
        for final in (False,True):
            bad=copy.deepcopy(r);p.discard_capture(bad,final=final)
            self.assertIsNone(bad['description_measurement']);self.assertNotIn('description_failure',bad)

    def test_baseline_cannot_claim_unexecuted_reader_adapter_or_parity(self):
        for category,code,phase in (('unsupported_layout','declaration_mismatch','public_reader'),
                ('adapter','one_active_row','adapter'),('parity','metadata','comparison'),
                ('unclassified','unknown_exception','public_reader'),('unclassified','unknown_exception','cleanup')):
            with self.assertRaises(OracleError):p._diagnostic(dict(snapshot='baseline',phase=phase,category=category,code=code))
        for phase in ('postimage','comparison'):
            p._diagnostic(dict(snapshot='baseline',phase=phase,category='unclassified',code='unknown_exception'))

    def test_parity_bind_codes_are_fixed_without_changing_failure_kind(self):
        r=fixture();r['description_measurement']['states']=r['description_measurement']['states'][:1]
        ev=evidence(r,'created',1);text=measurement.CASES['description8'][1];w=witness(token=ev['token'],value=text,present=True)
        for code,length,value,typed in (('metadata',17,text,UUID(NATIVE_UUID)),('description',8,'other',UUID(NATIVE_UUID)),('typed_uuid',8,text,UUID(int=1))):
            ob,_=observation(length,value)
            with self.assertRaises(p.DescriptionParityError) as caught:p.bind_state('created',ev,ob,w,r,typed_uuid=typed)
            self.assertEqual(caught.exception.code,code);self.assertEqual(caught.exception.kind,'transport_invalid')

if __name__=='__main__':unittest.main()
