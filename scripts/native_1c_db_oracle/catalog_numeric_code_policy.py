"""Numeric Code acquisition policy; detached core mapping, no runtime admission."""
import copy
import hashlib
import re
from decimal import Decimal
from uuid import UUID
import protocol as core
import catalog_numeric_code_measurement as measurement
from contract import source_binding
from snapshots import MAX_FILE_BYTES
from protocol import require, exact, integer, digest, encode, decode
SCHEMA,CAPTURE_SCHEMA,AGGREGATE_SCHEMA=59,60,61
LANE='catalog-numeric-code-measurement-v1'
PROFILE_ID='numeric-code-measurement-v1'
MODULE_SOURCE='scripts/native_1c_db_oracle/catalog_numeric_code_policy.py'
MAX_CAPTURE_BYTES,MAX_AGGREGATE_BYTES=8192,2048
CASES=tuple(measurement.CASES)
TARGETS=('baseline','created','updated','applied')
STAGES=dict(zip(TARGETS,('baseline','create','update','apply_cf')))
EXTRA_KEYS={'numeric_case','numeric_code_measurement'}
OUTCOMES=('readback_matches','readback_differs','layout_unresolved')
PROFILE_SHA256=hashlib.sha256(encode({'id':PROFILE_ID,'cases':dict(measurement.CASES),
 'logical_tag':'observed_number','physical':'CONFIG-derived N(precision,0) after physical admission',
 'params_slot_policy':'closed_marker1_chain_v1','scope':'same-postimage witness; UUID must match if observed; Code and Description observational',
 'runtime_support':'not_claimed'})).hexdigest()
PHYSICAL_NUMBERS=('code_length','description_length','payload_length','field_count','record_size',
 'active_count','code_ordinal','code_offset','code_width','code_precision','code_scale','digit_count',
 'previous_ordinal','previous_offset','next_ordinal','next_offset','previous_displacement','next_displacement')
PHYSICAL_KEYS=set(PHYSICAL_NUMBERS)|{'status','runtime_support','descriptor_sha256','active_count_known','code_type'}

def _token(v):return type(v)is str and re.fullmatch('[0-9a-f]{32}',v)is not None

def _case(v):require(type(v)is str and v in CASES,'invalid_input')

def expected_logical(identifier):
 value=core.expected_logical(identifier)
 if value['code']is not None:value['code']='observed_number'
 return value

def validate_logical(value,identifier):
 exact(value,core.LOGICAL_KEYS);wanted=expected_logical(identifier)
 require(type(value['code'])is type(wanted['code']) and value['code']==wanted['code'],'logical_mismatch')
 view=copy.deepcopy(value)
 if view['code']is not None:view['code']='K1'
 core.validate_logical(view,identifier)

def marker(raw,*,nonce,token,operation,contract_version=3):
 value=decode(raw);require(type(value)is dict and 'code'in value and 'count'in value,'invalid_marker')
 expected='observed_number' if type(value['count'])is int and value['count']==1 else None
 require(type(value['code'])is type(expected) and value['code']==expected,'invalid_marker')
 view=copy.deepcopy(value)
 if expected is not None:view['code']='K1'
 core.marker(encode(view),nonce=nonce,token=token,operation=operation,contract_version=contract_version)
 return value

def _sources(provenance):
 from inputs import CATALOG_NUMERIC_CODE_SOURCE_FILES
 require(type(provenance)is dict and type(provenance.get('sources'))is dict
  and len(CATALOG_NUMERIC_CODE_SOURCE_FILES)==42 and set(provenance['sources'])==set(CATALOG_NUMERIC_CODE_SOURCE_FILES)
  and MODULE_SOURCE in provenance['sources'],'provenance_mismatch')
 require(provenance.get('image')==core.IMAGE and provenance.get('platform')=='linux/amd64'
  and provenance.get('locale')=='ru_RU.UTF-8' and provenance.get('timezone')=='Etc/UTC','provenance_mismatch')

def empty_report(nonce,provenance,*,numeric_case):
 _case(numeric_case);r=core.empty_report(nonce,provenance)
 r.update(schema=SCHEMA,lane=LANE,numeric_case=numeric_case,numeric_code_measurement={
  'schema':CAPTURE_SCHEMA,'profile_id':PROFILE_ID,'profile_sha256':PROFILE_SHA256,'runtime_support':'not_claimed','states':[]})
 return r

def discard_capture(report,final=False):
 if report.get('schema')==SCHEMA:report['numeric_code_measurement']=None

def _image(value):
 exact(value,{'bytes','sha256'});require(integer(value['bytes'],MAX_FILE_BYTES,1)and digest(value['sha256']))

def _physical(p,case,identifier):
 exact(p,PHYSICAL_KEYS)
 require(type(p['status'])is str and p['status']in('layout_observed','layout_unresolved')
  and p['runtime_support']=='not_claimed' and digest(p['descriptor_sha256'])
  and type(p['active_count_known'])is bool)
 require(all(integer(p[k],4096)for k in PHYSICAL_NUMBERS))
 require(p['code_length']==measurement.CASES[case][0] and p['description_length']==8
  and p['payload_length']==(64 if identifier=='applied' else 32) and p['field_count']<=16)
 if p['status']=='layout_unresolved':
  require(p['code_type']=='unresolved'and p['active_count_known']is False)
  require(all(p[k]==0 for k in PHYSICAL_NUMBERS if k not in('code_length','description_length','payload_length','field_count')))
 else:
  require(p['code_type']=='N'and p['active_count_known']is True and p['active_count']==1
   and p['field_count']==8 and p['code_ordinal']==4 and p['previous_ordinal']==3 and p['next_ordinal']==5
   and p['code_precision']==p['code_length']and p['code_scale']==0
   and p['code_width']==(p['code_precision']+2)//2 and 1<=p['digit_count']<=p['code_precision']
   and p['code_offset']-p['previous_offset']==p['previous_displacement']==16
   and p['next_offset']-p['code_offset']==p['next_displacement']==p['code_width']
   and p['next_offset']+18<=p['record_size'])

def _witness(w,report,token,identifier):
 exact(w,{'sha256','nonce','token','case','operation','present','code_length','description_length','payload_length','autonumbering'})
 require(digest(w['sha256'])and _token(w['nonce'])and w['nonce']==report['nonce']
  and _token(w['token'])and w['token']==token and w['case']==report['numeric_case']and w['operation']=='observe'
  and type(w['present'])is bool and w['present']is(identifier!='baseline')and w['autonumbering']is False)
 for k,v in [('code_length',measurement.CASES[report['numeric_case']][0]),('description_length',8),('payload_length',64 if identifier=='applied'else 32)]:
  require(type(w[k])is int and w[k]==v,'logical_mismatch')

def _comparison(q,w,report,identifier):
 exact(q,{'status','metadata_matches','code_verdict','uuid_verdict','description_verdict','physical','witness_sha256','runtime_support'})
 require(type(q['status'])is str and q['status']in OUTCOMES and q['metadata_matches']is True
  and q['runtime_support']=='not_claimed'and q['witness_sha256']==w['sha256'])
 _physical(q['physical'],report['numeric_case'],identifier)
 if q['physical']['status']=='layout_unresolved':
  require(q['status']=='layout_unresolved'and all(q[k]=='not_compared'for k in('code_verdict','uuid_verdict','description_verdict')))
 else:
  require(q['uuid_verdict']=='matches','logical_mismatch')
  require(all(type(q[k])is str and q[k]in('matches','differs')for k in('code_verdict','description_verdict')))
  expected='readback_matches'if q['code_verdict']==q['description_verdict']=='matches'else 'readback_differs'
  require(q['status']==expected)

def _state(value,identifier,report):
 exact(value,{'snapshot','observe_token','origin','postimage','witness','comparison'})
 require(value['snapshot']==identifier and _token(value['observe_token']))
 _image(value['origin']);_image(value['postimage'])
 snapshot=next((s for s in report['snapshots']if s['id']==identifier),None)
 require(snapshot is not None and value['origin']=={k:snapshot['physical'][k]for k in('bytes','sha256')},'snapshot_changed')
 _witness(value['witness'],report,value['observe_token'],identifier)
 if identifier=='baseline':require(value['comparison']is None)
 else:_comparison(value['comparison'],value['witness'],report,identifier)

def bind_state(evidence,report,observation,witness):
 exact(evidence,{'snapshot','token','origin','postimage','logical'});identifier=evidence['snapshot']
 require(type(identifier)is str and identifier in TARGETS,'invalid_input');_case(report['numeric_case'])
 snapshot=next((s for s in report['snapshots']if s['id']==identifier),None)
 require(snapshot is not None and evidence['logical']==snapshot['logical'],'snapshot_changed');validate_logical(evidence['logical'],identifier)
 require(type(witness)is measurement.NumericCodeWitness,'invalid_marker')
 present=identifier!='baseline'
 require(type(witness.present)is bool and witness.present is present and type(witness.actual_description)is str,'invalid_marker')
 try:units=len(witness.actual_description.encode('utf-16-le'))//2
 except UnicodeError:require(False,'invalid_marker')
 require(units<=measurement.MAX_DESCRIPTION_UNITS,'invalid_marker')
 if present:
  require(type(witness.actual_code)is Decimal and witness.actual_code.is_finite()
   and len(witness.actual_code.as_tuple().digits)<=measurement.MAX_NUMBER_TEXT
   and -measurement.MAX_NUMBER_TEXT<=witness.actual_code.as_tuple().exponent<=0
   and type(witness.actual_uuid)is UUID and witness.actual_uuid.int!=0,'invalid_marker')
 else:require(witness.actual_code is None and witness.actual_uuid is None and witness.actual_description=='','invalid_marker')
 require((observation is None)is(not present),'invalid_input')
 public={'sha256':witness.raw_sha256,'nonce':witness.nonce,'token':witness.token,'case':witness.case,
  'operation':witness.operation,'present':witness.present,'code_length':witness.code_length,
  'description_length':witness.description_length,'payload_length':witness.payload_length,'autonumbering':witness.autonumbering}
 _witness(public,report,evidence['token'],identifier)
 value={'snapshot':identifier,'observe_token':evidence['token'],'origin':copy.deepcopy(evidence['origin']),
  'postimage':copy.deepcopy(evidence['postimage']),'witness':public,
  'comparison':measurement.compare_readback(observation,witness,case=report['numeric_case'])if present else None}
 _state(value,identifier,report)
 capture=report['numeric_code_measurement'];require(type(capture)is dict and type(capture.get('states'))is list)
 require([s['snapshot']for s in capture['states']]==list(TARGETS[:TARGETS.index(identifier)])
  and evidence['token']not in[s['observe_token']for s in capture['states']],'stale_evidence')
 require(len(encode({**capture,'states':capture['states']+[value]}))<=MAX_CAPTURE_BYTES,'artifact_limit')
 return value

def validate_report(raw,*,nonce,provenance,final=False):
 report=decode(raw);require(type(report)is dict and EXTRA_KEYS<=set(report))
 require(type(report.get('schema'))is int and report['schema']==SCHEMA and report.get('lane')==LANE)
 _case(report['numeric_case']);_sources(provenance)
 view=copy.deepcopy(report)
 for k in EXTRA_KEYS:del view[k]
 view.update(schema=core.SCHEMA,lane=core.LANE)
 require(type(report.get('snapshots'))is list)
 for original,snapshot in zip(report['snapshots'],view['snapshots']):
  require(type(original)is dict and 'logical'in original and 'id'in original)
  validate_logical(original['logical'],original['id'])
  if snapshot['logical']['code']is not None:snapshot['logical']['code']='K1'
 core.validate_report(encode(view),nonce=nonce,provenance=provenance,final=final)
 capture=report['numeric_code_measurement']
 if report['status']=='failed':require(capture is None);return report
 exact(capture,{'schema','profile_id','profile_sha256','runtime_support','states'})
 require(type(capture['schema'])is int and capture['schema']==CAPTURE_SCHEMA and capture['profile_id']==PROFILE_ID
  and capture['profile_sha256']==PROFILE_SHA256 and capture['runtime_support']=='not_claimed')
 require(len(encode(capture))<=MAX_CAPTURE_BYTES,'artifact_limit')
 require(type(capture['states'])is list and len(capture['states'])==4)
 tokens=[]
 for identifier,state in zip(TARGETS,capture['states']):_state(state,identifier,report);tokens.append(state['observe_token'])
 require(len(set(tokens))==4)
 required=report['cleanup']if final else {k:report['cleanup'][k]for k in('native_processes_stopped','raw_files_removed')}
 require(all(v is True for v in required.values()))
 return report

def _outcome(report):
 values=[s['comparison']['status']for s in report['numeric_code_measurement']['states'][1:]]
 return next((v for v in('layout_unresolved','readback_differs')if v in values),'readback_matches')

def _aggregate_cases(reports,report_sha256s,provenance,run_id,run_attempt):
    require(type(reports) in (tuple,list) and len(reports)==2 and type(report_sha256s) in (tuple,list) and len(report_sha256s)==2)
    cases=[]
    for case,report,sha in zip(CASES,reports,report_sha256s):
        require(type(report) is dict and 'nonce' in report)
        validate_report(encode(report),nonce=report['nonce'],provenance=provenance,final=True)
        require(report['accepted'] is True and report['numeric_case']==case and digest(sha))
        cases.append({'case':case,'outcome':_outcome(report),'report_sha256':sha,
            'source_sha256':source_binding(provenance),'run_id':run_id,'run_attempt':run_attempt})
    require(reports[0]['nonce']!=reports[1]['nonce'])
    return cases


def build_aggregate(reports,report_sha256s,*,run_id,run_attempt):
    """Aggregate only independently validated finals; caller hashes exact raw files."""
    require(type(reports) in (tuple,list) and len(reports)==2 and type(reports[0]) is dict and 'provenance' in reports[0])
    provenance=reports[0]['provenance']
    cases=_aggregate_cases(reports,report_sha256s,provenance,run_id,run_attempt)
    result={'schema':AGGREGATE_SCHEMA,'lane':LANE,'accepted':True,'cases':cases}
    return validate_aggregate(encode(result),provenance=provenance,run_id=run_id,run_attempt=run_attempt,
        reports=reports,report_sha256s=report_sha256s)


def validate_aggregate(raw,*,provenance,run_id,run_attempt,reports,report_sha256s):
    """Require the actual final reports and externally recomputed raw-file hashes.

    A compact shape alone cannot establish lifecycle acceptance. Reports stay
    separate inputs and are never nested into this public aggregate.
    """
    require(type(raw) is bytes and len(raw)<=MAX_AGGREGATE_BYTES,'artifact_limit')
    _sources(provenance);require(integer(run_id,10**20-1,1) and integer(run_attempt,10**6,1))
    value=decode(raw);exact(value,{'schema','lane','accepted','cases'})
    require(type(value['schema']) is int and value['schema']==AGGREGATE_SCHEMA and value['lane']==LANE and value['accepted'] is True)
    require(type(value['cases']) is list and len(value['cases'])==2)
    for case,entry in zip(CASES,value['cases']):
        exact(entry,{'case','outcome','report_sha256','source_sha256','run_id','run_attempt'})
        require(entry['case']==case and type(entry['outcome']) is str and entry['outcome'] in OUTCOMES
            and digest(entry['report_sha256']) and entry['source_sha256']==source_binding(provenance)
            and type(entry['run_id']) is int and entry['run_id']==run_id
            and type(entry['run_attempt']) is int and entry['run_attempt']==run_attempt)
    require(value['cases']==_aggregate_cases(reports,report_sha256s,provenance,run_id,run_attempt))
    return value
