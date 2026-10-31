"""Disabled Code acquisition policy; detached core mapping, no runtime admission."""
import copy
import hashlib
import re
from decimal import Decimal
from uuid import UUID
import protocol as core
import catalog_zero_code_measurement as measurement
from contract import source_binding
from snapshots import MAX_FILE_BYTES
from protocol import require, exact, integer, digest, encode, decode
SCHEMA,CAPTURE_SCHEMA,AGGREGATE_SCHEMA=65,66,67
LANE='catalog-zero-code-measurement-v1'
PROFILE_ID='zero-code-measurement-v1'
MODULE_SOURCE='scripts/native_1c_db_oracle/catalog_zero_code_policy.py'
MAX_CAPTURE_BYTES,MAX_AGGREGATE_BYTES=8192,2048
CASES=tuple(measurement.CASES)
TARGETS=('baseline','created','updated','applied')
STAGES=dict(zip(TARGETS,('baseline','create','update','apply_cf')))
EXTRA_KEYS={'zero_case','zero_code_measurement'}
OUTCOMES=('readback_matches','readback_differs','layout_unresolved')
PROFILE_SHA256=hashlib.sha256(encode({'id':PROFILE_ID,'cases':dict(measurement.CASES),
 'logical_tag':'observed_no_code','physical':'CONFIG-derived disabled string Code; optional Description after physical admission',
 'params_slot_policy':'closed_marker1_chain_v1','scope':'same-postimage witness; UUID must match if observed; Code availability and Description observational',
 'runtime_support':'not_claimed'})).hexdigest()
PHYSICAL_NUMBERS=('code_length','description_length','payload_length','field_count','record_size',
 'code_field_count','description_field_count','active_count','first_attribute_offset')
PHYSICAL_KEYS=set(PHYSICAL_NUMBERS)|{'status','runtime_support','descriptor_sha256','active_count_known'}

def _token(v):return type(v)is str and re.fullmatch('[0-9a-f]{32}',v)is not None

def _case(v):require(type(v)is str and v in CASES,'invalid_input')

def expected_logical(identifier):
 value=core.expected_logical(identifier)
 if value['code']is not None:value['code']='observed_no_code'
 return value

def validate_logical(value,identifier):
 exact(value,core.LOGICAL_KEYS);wanted=expected_logical(identifier)
 require(type(value['code'])is type(wanted['code']) and value['code']==wanted['code'],'logical_mismatch')
 view=copy.deepcopy(value)
 if view['code']is not None:view['code']='K1'
 core.validate_logical(view,identifier)

def marker(raw,*,nonce,token,operation,contract_version=3):
 value=decode(raw);require(type(value)is dict and 'code'in value and 'count'in value,'invalid_marker')
 expected='observed_no_code' if type(value['count'])is int and value['count']==1 else None
 require(type(value['code'])is type(expected) and value['code']==expected,'invalid_marker')
 view=copy.deepcopy(value)
 if expected is not None:view['code']='K1'
 core.marker(encode(view),nonce=nonce,token=token,operation=operation,contract_version=contract_version)
 return value

def _sources(provenance):
 from inputs import CATALOG_ZERO_CODE_SOURCE_FILES
 require(type(provenance)is dict and type(provenance.get('sources'))is dict
  and len(CATALOG_ZERO_CODE_SOURCE_FILES)==42 and set(provenance['sources'])==set(CATALOG_ZERO_CODE_SOURCE_FILES)
  and MODULE_SOURCE in provenance['sources'],'provenance_mismatch')
 require(provenance.get('image')==core.IMAGE and provenance.get('platform')=='linux/amd64'
  and provenance.get('locale')=='ru_RU.UTF-8' and provenance.get('timezone')=='Etc/UTC','provenance_mismatch')

def empty_report(nonce,provenance,*,zero_case):
 _case(zero_case);r=core.empty_report(nonce,provenance)
 r.update(schema=SCHEMA,lane=LANE,zero_case=zero_case,zero_code_measurement={
  'schema':CAPTURE_SCHEMA,'profile_id':PROFILE_ID,'profile_sha256':PROFILE_SHA256,'runtime_support':'not_claimed','states':[]})
 return r

def discard_capture(report,final=False):
 report.pop('zero_bootstrap_failure',None)
 if report.get('schema')==SCHEMA:report['zero_code_measurement']=None

BOOTSTRAP_FAILURE_KEY='zero_bootstrap_failure'
BOOTSTRAP_LOG_STATES=('absent','empty','nonempty','unavailable')
BOOTSTRAP_FRONTIER_PHASES=frozenset(('dispatch','control','marker','metadata','serialize'))

def _diagnostic_keys(value,keys):
 require(type(value)is dict and len(value)==len(keys))
 require(all(type(key)is str for key in value))
 require(set(value)==set(keys))

def validate_bootstrap_failure(value):
 require(type(value)is dict and all(type(key)is str for key in dict.__iter__(value)))
 _diagnostic_keys(value,{'schema','nonce','token','bootstrap','result','completion','pending','out','console'} | ({'frontier'} if 'frontier'in value else set()) | ({'compile'} if 'compile'in value else set()))
 require(type(value['schema'])is int and value['schema']==1 and _token(value['nonce']) and _token(value['token']))
 for name in ('bootstrap','result','completion','pending'):
  allowed=('absent','invalid','valid_ok','valid_error')if name in ('completion','pending')else('absent','invalid','valid_ok')
  require(type(value[name])is str and value[name]in allowed)
 for name in ('out','console'):
  log=value[name];_diagnostic_keys(log,{'state','module_error','undefined_symbol','syntax_error'})
  require(type(log['state'])is str and log['state']in BOOTSTRAP_LOG_STATES)
  for key in ('module_error','undefined_symbol','syntax_error'):
   require(type(log[key])is bool and (log['state']=='nonempty' or log[key]is False))
 if 'frontier'in value:
  _diagnostic_keys(value['frontier'],set(measurement.FRONTIER_POINTS))
  for point,item in value['frontier'].items():validate_frontier_projection(item,point)
 if 'compile'in value:
  validate_compile_projection(value['compile'])
  require(value['bootstrap']=='valid_ok' and 'frontier'in value
   and value['frontier']['client_before_call']=={'state':'valid','status':'entered','phase':'dispatch'}
   and value['frontier']['server_enter']=={'state':'absent','status':None,'phase':None})
 return value


def validate_frontier_projection(value,point):
 _diagnostic_keys(value,{'state','status','phase'})
 require(type(value['state'])is str and value['state']in('absent','invalid','valid'))
 if value['state']!='valid':
  require(value['status']is None and value['phase']is None)
 elif point in ('client_before_call','server_enter','client_after_call'):
  status='returned' if point=='client_after_call' else 'entered'
  require(type(value['status'])is str and value['status']==status and type(value['phase'])is str and value['phase']=='dispatch')
 else:
  require(type(value['status'])is str and value['status']in('ok','error') and type(value['phase'])is str)
  require(value['phase']=='complete' if value['status']=='ok' else value['phase']in BOOTSTRAP_FRONTIER_PHASES)
 return value


def frontier_marker(raw,*,nonce,token,point):
 require(type(point)is str and point in measurement.FRONTIER_POINTS)
 value=decode(raw);_diagnostic_keys(value,{'schema','nonce','token','point','status','phase'})
 require(type(value['schema'])is int and value['schema']==1 and type(value['nonce'])is str and value['nonce']==nonce
  and type(value['token'])is str and value['token']==token and type(value['point'])is str and value['point']==point)
 return validate_frontier_projection({'state':'valid','status':value['status'],'phase':value['phase']},point)


def validate_compile_projection(value):
 _diagnostic_keys(value,{'state','result_code','log_state','issues','truncated'})
 require(type(value['state'])is str and value['state']in measurement.COMPILE_STATES)
 code=value['result_code'];require(code is None or type(code)is int and -1<=code<=255)
 require(type(value['log_state'])is str and value['log_state']in('absent','empty','nonempty','unavailable'))
 require(type(value['truncated'])is bool and type(value['issues'])is list and len(value['issues'])<=8)
 require(not value['truncated'] or len(value['issues'])==8)
 require(value['log_state']=='nonempty' or value['issues']==[] and value['truncated']is False)
 for issue in value['issues']:
  _diagnostic_keys(issue,{'module','line','column','category'})
  require(type(issue['module'])is str and issue['module']in measurement.COMPILE_MODULES
   and type(issue['category'])is str and issue['category']in measurement.COMPILE_CATEGORIES)
  for key in ('line','column'):require(type(issue[key])is int and 0<=issue[key]<=65535)
  require((issue['line']==0 and issue['column']==0)if issue['module']=='other'else(issue['line']>0 and issue['column']>0))
 require(len({(i['module'],i['line'],i['column'],i['category']) for i in value['issues']})==len(value['issues']))
 return value

def _bootstrap_failure_bound(report,value,final):
 require(value['nonce']==report.get('nonce'))
 require(report.get('schema')==SCHEMA and report.get('lane')==LANE and report.get('status')=='failed'
  and report.get('accepted')is False and report.get('failed_stage')=='seed_v1'
  and report.get('failure_kind')=='seed_bootstrap_timeout' and report.get('zero_code_measurement')is None
  and type(report.get('snapshots'))is list and report['snapshots']==[])
 context=report.get('failure_context')
 _diagnostic_keys(context,{'operation','site','bsl_phase','region','reason'})
 require(context=={'operation':'enterprise_bootstrap','site':'poll','bsl_phase':None,'region':None,'reason':None})
 cleanup=report.get('cleanup');require(type(cleanup)is dict)
 names=('native_processes_stopped','raw_files_removed','container_removed','private_staging_removed')if final else('native_processes_stopped','raw_files_removed')
 require(all(cleanup.get(k)is True for k in names))

def set_bootstrap_failure(report,value,final=False):
 """Retain bounded evidence only after cleanup; never change acceptance."""
 report.pop(BOOTSTRAP_FAILURE_KEY,None)
 try:
  validate_bootstrap_failure(value);_bootstrap_failure_bound(report,value,final)
 except core.OracleError:
  return False
 report[BOOTSTRAP_FAILURE_KEY]=copy.deepcopy(value)
 return True

def _image(value):
 exact(value,{'bytes','sha256'});require(integer(value['bytes'],MAX_FILE_BYTES,1)and digest(value['sha256']))

def _physical(p,case,identifier):
 exact(p,PHYSICAL_KEYS)
 require(type(p['status'])is str and p['status']in('layout_observed','layout_unresolved')
  and p['runtime_support']=='not_claimed' and digest(p['descriptor_sha256'])
  and type(p['active_count_known'])is bool)
 require(all(integer(p[k],4096)for k in PHYSICAL_NUMBERS))
 description=measurement.CASES[case]
 require(p['code_length']==0 and p['description_length']==description
  and p['payload_length']==(64 if identifier=='applied' else 32) and p['field_count']<=16
  and p['code_field_count']<=1 and p['description_field_count']<=1
  and p['code_field_count']+p['description_field_count']<=p['field_count'])
 if p['status']=='layout_unresolved':
  require(p['active_count_known']is False and p['active_count']==p['record_size']==p['first_attribute_offset']==0)
 else:
  offset=50+(2+2*description if description else 0)
  require(p['active_count_known']is True and p['active_count']==1
   and p['code_field_count']==0 and p['description_field_count']==bool(description)
   and p['field_count']==6+bool(description) and p['first_attribute_offset']==offset
   and p['record_size']==offset+2+2*p['payload_length']+5)

def _witness(w,report,token,identifier):
 require(type(w)is dict and all(type(key)is str for key in dict.__iter__(w)))
 exact(w,{'sha256','nonce','token','case','operation','present','code_length','description_length','payload_length','autonumbering','code_type','code_state'} | ({'code_is_empty'} if 'code_is_empty'in w else set()))
 require(digest(w['sha256'])and _token(w['nonce'])and w['nonce']==report['nonce']
  and _token(w['token'])and w['token']==token and w['case']==report['zero_case']and w['operation']=='observe'
  and w['code_type']=='string' and type(w['code_state'])is str
  and w['code_state'] in (('absent',) if identifier=='baseline' else ('unavailable','string','number','other'))
  and type(w['present'])is bool and w['present']is(identifier!='baseline')and w['autonumbering']is False)
 if 'code_is_empty'in w:
  require(type(w['code_is_empty'])is bool if w['code_state']=='string'else w['code_is_empty']is None)
 for k,v in [('code_length',0),('description_length',measurement.CASES[report['zero_case']]),('payload_length',64 if identifier=='applied'else 32)]:
  require(type(w[k])is int and w[k]==v,'logical_mismatch')

def _comparison(q,w,report,identifier):
 exact(q,{'schema','metadata_matches','code_availability','uuid_verdict','description_verdict','physical','witness_sha256'})
 require(type(q['schema'])is int and q['schema']==1 and q['metadata_matches']is True
  and q['witness_sha256']==w['sha256'] and q['code_availability']==w['code_state'])
 _physical(q['physical'],report['zero_case'],identifier)
 if q['physical']['status']=='layout_unresolved':
  require(q['uuid_verdict']==q['description_verdict']=='unresolved')
 else:
  require(q['uuid_verdict']=='matches','logical_mismatch')
  allowed=('not_applicable',) if measurement.CASES[report['zero_case']]==0 else ('matches','differs')
  require(type(q['description_verdict'])is str and q['description_verdict']in allowed)

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
 require(type(identifier)is str and identifier in TARGETS,'invalid_input');_case(report['zero_case'])
 snapshot=next((s for s in report['snapshots']if s['id']==identifier),None)
 require(snapshot is not None and evidence['logical']==snapshot['logical'],'snapshot_changed');validate_logical(evidence['logical'],identifier)
 require(type(witness)is measurement.ZeroCodeWitness,'invalid_marker')
 present=identifier!='baseline'
 require(type(witness.present)is bool and witness.present is present and type(witness.actual_description)is str,'invalid_marker')
 try:units=len(witness.actual_description.encode('utf-16-le'))//2
 except UnicodeError:require(False,'invalid_marker')
 require(units<=measurement.MAX_DESCRIPTION_UNITS,'invalid_marker')
 require(type(witness.code_state)is str and type(witness.code_type)is str,'invalid_marker')
 if present:
  require(type(witness.actual_uuid)is UUID and witness.actual_uuid.int!=0,'invalid_marker')
  if witness.code_state=='number':
   require(type(witness.actual_code)is Decimal and witness.actual_code.is_finite()
    and len(witness.actual_code.as_tuple().digits)<=measurement.MAX_NUMBER_TEXT
    and -measurement.MAX_NUMBER_TEXT<=witness.actual_code.as_tuple().exponent<=0,'invalid_marker')
  elif witness.code_state=='string':
   require(type(witness.actual_code)is str,'invalid_marker')
   try:require(len(witness.actual_code.encode('utf-16-le'))//2<=128,'invalid_marker')
   except UnicodeError:require(False,'invalid_marker')
  else:require(witness.actual_code is None,'invalid_marker')
 else:require(witness.actual_code is None and witness.actual_uuid is None and witness.actual_description=='','invalid_marker')
 if witness.description_length==0:require(witness.actual_description=='','invalid_marker')
 require((observation is None)is(not present),'invalid_input')
 public={'sha256':witness.raw_sha256,'nonce':witness.nonce,'token':witness.token,'case':witness.case,
  'operation':witness.operation,'present':witness.present,'code_length':witness.code_length,
  'description_length':witness.description_length,'payload_length':witness.payload_length,'autonumbering':witness.autonumbering,'code_type':witness.code_type,'code_state':witness.code_state,
  'code_is_empty':witness.actual_code=='' if witness.code_state=='string'else None}
 _witness(public,report,evidence['token'],identifier)
 value={'snapshot':identifier,'observe_token':evidence['token'],'origin':copy.deepcopy(evidence['origin']),
  'postimage':copy.deepcopy(evidence['postimage']),'witness':public,
  'comparison':measurement.compare_readback(observation,witness,case=report['zero_case'])if present else None}
 _state(value,identifier,report)
 capture=report['zero_code_measurement'];require(type(capture)is dict and type(capture.get('states'))is list)
 require([s['snapshot']for s in capture['states']]==list(TARGETS[:TARGETS.index(identifier)])
  and evidence['token']not in[s['observe_token']for s in capture['states']],'stale_evidence')
 require(len(encode({**capture,'states':capture['states']+[value]}))<=MAX_CAPTURE_BYTES,'artifact_limit')
 return value

def validate_report(raw,*,nonce,provenance,final=False):
 report=decode(raw);require(type(report)is dict and EXTRA_KEYS<=set(report))
 require(type(report.get('schema'))is int and report['schema']==SCHEMA and report.get('lane')==LANE)
 _case(report['zero_case']);_sources(provenance)
 if BOOTSTRAP_FAILURE_KEY in report:
  validate_bootstrap_failure(report[BOOTSTRAP_FAILURE_KEY]);_bootstrap_failure_bound(report,report[BOOTSTRAP_FAILURE_KEY],final)
 view=copy.deepcopy(report)
 view.pop(BOOTSTRAP_FAILURE_KEY,None)
 for k in EXTRA_KEYS:del view[k]
 view.update(schema=core.SCHEMA,lane=core.LANE)
 require(type(report.get('snapshots'))is list)
 for original,snapshot in zip(report['snapshots'],view['snapshots']):
  require(type(original)is dict and 'logical'in original and 'id'in original)
  validate_logical(original['logical'],original['id'])
  if snapshot['logical']['code']is not None:snapshot['logical']['code']='K1'
 core.validate_report(encode(view),nonce=nonce,provenance=provenance,final=final)
 capture=report['zero_code_measurement']
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
 values=[s['comparison']for s in report['zero_code_measurement']['states'][1:]]
 if any(v['physical']['status']=='layout_unresolved'for v in values):return 'layout_unresolved'
 return 'readback_differs'if any(v['description_verdict']=='differs'for v in values)else 'readback_matches'

def _aggregate_cases(reports,report_sha256s,provenance,run_id,run_attempt):
    require(type(reports) in (tuple,list) and len(reports)==2 and type(report_sha256s) in (tuple,list) and len(report_sha256s)==2)
    cases=[]
    for case,report,sha in zip(CASES,reports,report_sha256s):
        require(type(report) is dict and 'nonce' in report)
        validate_report(encode(report),nonce=report['nonce'],provenance=provenance,final=True)
        require(report['accepted'] is True and report['zero_case']==case and digest(sha))
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
