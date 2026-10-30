"""Finite PARAMS slot hypothesis measurements; never runtime support admission."""
from __future__ import annotations
import copy
import hashlib
import re
import protocol as core
import params_slot_observer as observer
from contract import source_binding
from snapshots import MAX_FILE_BYTES
from protocol import require, exact, integer, digest, encode, decode
SCHEMA, CAPTURE_SCHEMA, AGGREGATE_SCHEMA = 56, 57, 58
LANE = 'catalog-params-slot-measurement-v1'
PROFILE_ID = 'params-slot-measurement-v1'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/params_slot_policy.py'
MAX_CAPTURE_BYTES, MAX_AGGREGATE_BYTES = 8192, 2048
CASES = ('description8','description17')
TARGETS = ('updated','applied')
STAGES = {'updated':'update','applied':'apply_cf'}
EXTRA_KEYS = {'description_case','params_slot_measurement'}
OUTCOMES = ('measured',)
CHAIN_OUTCOMES = ('terminated','out_of_range','cycle','zero_marker_target')
PROJECTION_COUNTS = ('later_zero_count','later_one_count','later_other_count',
    'filename_zero_count','filename_empty_count','filename_nonempty_count',
    'dbnames_match_count','linked_nonzero_count','unlinked_nonzero_count')
PROJECTION_KEYS = set(PROJECTION_COUNTS) | {'recipe_id','recipe_sha256',
    'data_logical_bytes','blob_logical_bytes','candidate_stride','candidate_slots',
    'first_marker_class','chain_outcome','runtime_support'}
PROFILE_SHA256 = hashlib.sha256(encode({'id':PROFILE_ID,'recipe_id':observer.RECIPE_ID,
    'recipe_sha256':observer.RECIPE_SHA256,'targets':TARGETS,
    'scope':'same-postimage independent PARAMS measurement; no public typed read or witness selector',
    'runtime_support':'not_claimed'})).hexdigest()

def _token(value):return type(value) is str and re.fullmatch('[0-9a-f]{32}',value) is not None

def _case(value):require(type(value) is str and value in CASES,'invalid_input')

def _sources(provenance):
    from inputs import CATALOG_PARAMS_SLOT_SOURCE_FILES
    require(type(provenance) is dict and type(provenance.get('sources')) is dict
        and len(CATALOG_PARAMS_SLOT_SOURCE_FILES)==44
        and set(provenance['sources'])==set(CATALOG_PARAMS_SLOT_SOURCE_FILES)
        and MODULE_SOURCE in provenance['sources'],'provenance_mismatch')
    require(provenance.get('image')==core.IMAGE and provenance.get('platform')=='linux/amd64'
        and provenance.get('locale')=='ru_RU.UTF-8' and provenance.get('timezone')=='Etc/UTC','provenance_mismatch')

def empty_report(nonce,provenance,*,description_case):
    _case(description_case)
    report=core.empty_report(nonce,provenance)
    report.update(schema=SCHEMA,lane=LANE,description_case=description_case,
        params_slot_measurement={'schema':CAPTURE_SCHEMA,'profile_id':PROFILE_ID,
        'profile_sha256':PROFILE_SHA256,'runtime_support':'not_claimed','states':[]})
    return report

def discard_capture(report,final=False):
    if report.get('schema')==SCHEMA:report['params_slot_measurement']=None

def _image(value):
    exact(value,{'bytes','sha256'})
    require(integer(value['bytes'],MAX_FILE_BYTES,1) and digest(value['sha256']))

def validate_projection(value):
    exact(value,PROJECTION_KEYS)
    require(value['recipe_id']==observer.RECIPE_ID and value['recipe_sha256']==observer.RECIPE_SHA256
        and value['runtime_support']=='not_claimed')
    require(integer(value['candidate_slots'],observer.MAX_SLOTS,1)
        and type(value['candidate_stride']) is int and value['candidate_stride']==301)
    require(integer(value['data_logical_bytes'],MAX_FILE_BYTES,1)
        and value['data_logical_bytes']==value['candidate_stride']*value['candidate_slots']
        and integer(value['blob_logical_bytes'],MAX_FILE_BYTES))
    require(type(value['first_marker_class']) is str and value['first_marker_class'] in ('zero','one','other')
        and type(value['chain_outcome']) is str and value['chain_outcome'] in CHAIN_OUTCOMES)
    require(all(integer(value[k],value['candidate_slots']-1) for k in PROJECTION_COUNTS))
    require(value['later_zero_count']+value['later_one_count']+value['later_other_count']==value['candidate_slots']-1
        and value['filename_zero_count']==value['later_zero_count']
        and value['filename_empty_count']+value['filename_nonempty_count']==value['filename_zero_count']
        and value['dbnames_match_count']<=value['filename_nonempty_count']
        and value['linked_nonzero_count']+value['unlinked_nonzero_count']==value['later_one_count']+value['later_other_count'])
    if value['chain_outcome']=='cycle':require(value['linked_nonzero_count']>=1)
    if value['chain_outcome']=='zero_marker_target':require(value['later_zero_count']>=1)
    return value

def _state(value,identifier,report):
    exact(value,{'snapshot','observe_token','origin','postimage','observation'})
    require(value['snapshot']==identifier and _token(value['observe_token']))
    _image(value['origin']);_image(value['postimage'])
    snapshot=next((s for s in report['snapshots'] if s['id']==identifier),None)
    require(snapshot is not None and value['origin']=={k:snapshot['physical'][k] for k in ('bytes','sha256')},'snapshot_changed')
    validate_projection(value['observation'])
    require(value['observation']['data_logical_bytes']+value['observation']['blob_logical_bytes']<=value['postimage']['bytes'],'snapshot_changed')

def bind_state(evidence,report,projection):
    exact(evidence,{'snapshot','token','origin','postimage','logical'})
    identifier=evidence['snapshot'];require(type(identifier) is str and identifier in TARGETS,'invalid_input')
    _case(report['description_case'])
    snapshot=next((s for s in report['snapshots'] if s['id']==identifier),None)
    require(snapshot is not None and evidence['logical']==snapshot['logical'],'snapshot_changed')
    validate_projection(projection)
    value={'snapshot':identifier,'observe_token':evidence['token'],'origin':copy.deepcopy(evidence['origin']),
        'postimage':copy.deepcopy(evidence['postimage']),'observation':copy.deepcopy(projection)}
    _state(value,identifier,report)
    capture=report['params_slot_measurement'];require(type(capture) is dict and type(capture.get('states')) is list)
    require([s['snapshot'] for s in capture['states']]==list(TARGETS[:TARGETS.index(identifier)])
        and evidence['token'] not in [s['observe_token'] for s in capture['states']],'stale_evidence')
    require(len(encode({**capture,'states':capture['states']+[value]}))<=MAX_CAPTURE_BYTES,'artifact_limit')
    return value

def validate_report(raw,*,nonce,provenance,final=False):
    report=decode(raw);require(type(report) is dict and EXTRA_KEYS<=set(report))
    require(type(report.get('schema')) is int and report['schema']==SCHEMA and report.get('lane')==LANE)
    _case(report['description_case']);_sources(provenance)
    view=copy.deepcopy(report)
    for key in EXTRA_KEYS:del view[key]
    view.update(schema=core.SCHEMA,lane=core.LANE)
    core.validate_report(encode(view),nonce=nonce,provenance=provenance,final=final)
    capture=report['params_slot_measurement']
    if report['status']=='failed':
        require(capture is None);return report
    exact(capture,{'schema','profile_id','profile_sha256','runtime_support','states'})
    require(type(capture['schema']) is int and capture['schema']==CAPTURE_SCHEMA
        and capture['profile_id']==PROFILE_ID and capture['profile_sha256']==PROFILE_SHA256
        and capture['runtime_support']=='not_claimed')
    require(len(encode(capture))<=MAX_CAPTURE_BYTES,'artifact_limit')
    require(type(capture['states']) is list and len(capture['states'])==len(TARGETS))
    tokens=[]
    for identifier,state in zip(TARGETS,capture['states']):
        _state(state,identifier,report);tokens.append(state['observe_token'])
    require(len(set(tokens))==len(tokens))
    required=report['cleanup'] if final else {k:report['cleanup'][k] for k in ('native_processes_stopped','raw_files_removed')}
    require(all(v is True for v in required.values()))
    return report

def _outcome(report):return 'measured'

def _aggregate_cases(reports,report_sha256s,provenance,run_id,run_attempt):
    require(type(reports) in (tuple,list) and len(reports)==2 and type(report_sha256s) in (tuple,list) and len(report_sha256s)==2)
    cases=[]
    for case,report,sha in zip(CASES,reports,report_sha256s):
        require(type(report) is dict and 'nonce' in report)
        validate_report(encode(report),nonce=report['nonce'],provenance=provenance,final=True)
        require(report['accepted'] is True and report['description_case']==case and digest(sha))
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
