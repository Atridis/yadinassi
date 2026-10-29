"""Closed Description acquisition evidence; never runtime/native support admission.

Private actual strings stay in the reader/witness comparison. Lifecycle, source
identity and cleanup remain the unchanged protocol's responsibility.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
import protocol as core
import catalog_description_measurement as measurement
from contract import source_binding
from snapshots import MAX_FILE_BYTES
from protocol import require, exact, integer, digest, encode, decode

SCHEMA, CAPTURE_SCHEMA, AGGREGATE_SCHEMA = 50, 51, 52
LANE = 'catalog-description-measurement-v1'
PROFILE_ID = 'description-v1'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/catalog_description_policy.py'
MAX_CAPTURE_BYTES, MAX_AGGREGATE_BYTES = 8192, 2048
CASES = tuple(measurement.CASES)
TARGETS = ('baseline', 'created', 'updated')
STAGES = dict(zip(TARGETS, ('baseline', 'create', 'update')))
EXTRA_KEYS = {'description_case', 'description_measurement'}
PROFILE_SHA256 = hashlib.sha256(encode({'id':PROFILE_ID,
    'seeds_sha256':hashlib.sha256(encode(dict(measurement.CASES))).hexdigest(),
    'layout':'CONFIG-derived widths; one NVC _DESCRIPTION after _CODE; otherwise unresolved',
    'scope':'frozen same-postimage reader and observe witness; absent baseline; present targets',
    'acceptance':'core lifecycle and cleanup; differences are observations, never compatibility'})).hexdigest()
OUTCOMES = ('readback_matches','readback_differs','layout_unresolved','case_metadata_mismatch')
PHYSICAL_NUMBERS = ('description_length','payload_length','field_count','record_size',
    'active_count','description_ordinal','description_offset','description_width',
    'used_utf16_units','unicode_scalars','trailing_spaces','previous_ordinal',
    'next_ordinal','previous_offset','next_offset','previous_displacement','next_displacement')
PHYSICAL_KEYS = set(PHYSICAL_NUMBERS) | {'status','descriptor_sha256','active_count_known',
    'utf16_count_matches','description_type','value_sha256'}


def _token(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{32}',value) is not None


def _case(value):
    require(type(value) is str and value in CASES, 'invalid_input')


def _sources(provenance):
    from inputs import CATALOG_DESCRIPTION_SOURCE_FILES
    require(type(provenance) is dict and type(provenance.get('sources')) is dict
        and len(CATALOG_DESCRIPTION_SOURCE_FILES)==41
        and set(provenance['sources'])==set(CATALOG_DESCRIPTION_SOURCE_FILES)
        and MODULE_SOURCE in provenance['sources'], 'provenance_mismatch')
    require(provenance.get('image')==core.IMAGE and provenance.get('platform')=='linux/amd64'
        and provenance.get('locale')=='ru_RU.UTF-8' and provenance.get('timezone')=='Etc/UTC', 'provenance_mismatch')


def empty_report(nonce, provenance, *, description_case):
    _case(description_case)
    report=core.empty_report(nonce,provenance)
    report.update(schema=SCHEMA,lane=LANE,description_case=description_case,
        description_measurement={'schema':CAPTURE_SCHEMA,'profile_id':PROFILE_ID,
            'profile_sha256':PROFILE_SHA256,'states':[]})
    return report


def discard_capture(report, final=False):
    """No usable partial observation survives lifecycle/cleanup failure."""
    if report.get('schema')==SCHEMA:
        report['description_measurement']=None


def _image(value):
    exact(value,{'bytes','sha256'})
    require(integer(value['bytes'],MAX_FILE_BYTES,1) and digest(value['sha256']))


def _physical(value):
    exact(value,PHYSICAL_KEYS)
    require(value['status'] in ('layout_observed','layout_unresolved')
        and digest(value['descriptor_sha256']) and digest(value['value_sha256']))
    require(all(integer(value[n],MAX_FILE_BYTES) for n in PHYSICAL_NUMBERS))
    require(type(value['active_count_known']) is bool and type(value['utf16_count_matches']) is bool)
    require(value['description_type'] in ('NVC','absent','unresolved'))
    if value['status']=='layout_unresolved':
        require(value['description_type']=='unresolved' and value['active_count_known'] is False
            and value['active_count']==0 and value['utf16_count_matches'] is False
            and value['value_sha256']=='0'*64)
        require(all(value[k]==0 for k in PHYSICAL_NUMBERS if k not in
            ('description_length','payload_length','field_count','record_size')))
    else:
        require(value['active_count_known'] is True and value['active_count']==1)
        if value['description_length']:
            require(value['description_type']=='NVC' and value['description_ordinal']==5
                and value['previous_ordinal']==4 and value['next_ordinal']==6
                and value['description_width']==2+2*value['description_length']
                and value['next_offset']==value['description_offset']+value['description_width']
                and value['next_displacement']==value['description_width']
                and value['previous_displacement']==0
                and value['used_utf16_units']<=value['description_length']
                and value['unicode_scalars']<=value['used_utf16_units']
                and value['trailing_spaces']<=value['unicode_scalars']
                and value['description_offset']+value['description_width']<=value['record_size'])
        else:
            require(value['description_type']=='absent' and value['value_sha256']=='0'*64
                and value['utf16_count_matches'] is False)
            require(all(value[k]==0 for k in PHYSICAL_NUMBERS if k not in
                ('description_length','payload_length','field_count','record_size','active_count')))


def _witness(value, report, token, present):
    exact(value,{'sha256','nonce','token','case','operation','present','utf16_units','scalar_count','trailing_spaces'})
    require(digest(value['sha256']) and value['nonce']==report['nonce']
        and _token(value['nonce']) and value['token']==token and _token(token)
        and value['case']==report['description_case'] and value['operation']=='observe'
        and type(value['present']) is bool and value['present'] is present)
    require(integer(value['utf16_units'],measurement.MAX_ACTUAL_UNITS)
        and integer(value['scalar_count'],value['utf16_units'])
        and integer(value['trailing_spaces'],value['scalar_count']))
    if not present:
        require(value['utf16_units']==value['scalar_count']==value['trailing_spaces']==0)


def _comparison(value,witness,case):
    exact(value,{'status','metadata_matches','physical','witness_sha256','native_utf16_units',
        'native_unicode_scalars','native_trailing_spaces','count_evidence','native_compatibility'})
    require(type(value['status']) is str and value['status'] in OUTCOMES
        and type(value['metadata_matches']) is bool and value['native_compatibility']=='not_claimed')
    _physical(value['physical']);p=value['physical']
    require(value['metadata_matches'] is (p['description_length']==measurement.CASES[case][0]))
    require(value['witness_sha256']==witness['sha256'])
    for target,source in (('native_utf16_units','utf16_units'),('native_unicode_scalars','scalar_count'),('native_trailing_spaces','trailing_spaces')):
        require(type(value[target]) is int and value[target]==witness[source])
    if not value['metadata_matches']:
        require(value['status']=='case_metadata_mismatch')
    elif p['status']=='layout_unresolved':
        require(value['status']=='layout_unresolved')
    else:
        require(value['status'] in ('readback_matches','readback_differs'))
    supplementary=(value['status']=='readback_matches' and witness['utf16_units']>witness['scalar_count'] and p['utf16_count_matches'])
    require(value['count_evidence']==('supplementary_utf16_units_observed' if supplementary else 'not_distinguished'))
    if value['status']=='readback_matches':
        require(p['unicode_scalars']==witness['scalar_count'] and p['trailing_spaces']==witness['trailing_spaces'])
        if p['utf16_count_matches']:require(p['used_utf16_units']==witness['utf16_units'])


def _state(value, identifier, report):
    exact(value,{'snapshot','observe_token','origin','postimage','witness','comparison'})
    require(value['snapshot']==identifier and _token(value['observe_token']))
    _image(value['origin']);_image(value['postimage'])
    snapshot=next((s for s in report['snapshots'] if s['id']==identifier),None)
    require(snapshot is not None and value['origin']=={k:snapshot['physical'][k] for k in ('bytes','sha256')},'snapshot_changed')
    _witness(value['witness'],report,value['observe_token'],identifier!='baseline')
    if identifier=='baseline':require(value['comparison'] is None)
    else:_comparison(value['comparison'],value['witness'],report['description_case'])


def bind_state(identifier,evidence,observation,witness,report):
    """Bind already completed independent readback and private observe witness."""
    require(type(identifier) is str and identifier in TARGETS,'invalid_input')
    _case(report['description_case']);exact(evidence,{'snapshot','token','origin','postimage','logical'})
    expected=next((s for s in report['snapshots'] if s['id']==identifier),None)
    require(expected is not None and evidence['snapshot']==identifier and evidence['logical']==expected['logical'],'snapshot_changed')
    require(type(witness) is measurement.DescriptionWitness,'invalid_marker')
    require(type(witness.actual_description) is str and type(witness.present) is bool,'invalid_marker')
    try:units=len(witness.actual_description.encode('utf-16-le'))//2
    except UnicodeError:require(False,'invalid_marker')
    require(type(witness.utf16_units) is int and witness.utf16_units==units<=measurement.MAX_ACTUAL_UNITS
        and type(witness.scalar_count) is int and witness.scalar_count==len(witness.actual_description)
        and type(witness.trailing_spaces) is int and witness.trailing_spaces==len(witness.actual_description)-len(witness.actual_description.rstrip(' ')), 'invalid_marker')
    present=identifier!='baseline'
    require(witness.present is present and (present or witness.actual_description==''),'invalid_marker')
    require((observation is None) is (not present),'invalid_input')
    value={'snapshot':identifier,'observe_token':evidence['token'],
        'origin':copy.deepcopy(evidence['origin']),'postimage':copy.deepcopy(evidence['postimage']),
        'witness':{'sha256':witness.raw_sha256,'nonce':witness.nonce,'token':witness.token,
            'case':witness.case,'operation':witness.operation,'present':witness.present,
            'utf16_units':witness.utf16_units,'scalar_count':witness.scalar_count,'trailing_spaces':witness.trailing_spaces},
        'comparison':measurement.compare_readback(observation,witness,case=report['description_case']) if present else None}
    _state(value,identifier,report)
    capture=report['description_measurement'];require(type(capture) is dict and type(capture.get('states')) is list)
    require([s['snapshot'] for s in capture['states']]==list(TARGETS[:TARGETS.index(identifier)])
        and evidence['token'] not in [s['observe_token'] for s in capture['states']],'stale_evidence')
    require(len(encode({**capture,'states':capture['states']+[value]}))<=MAX_CAPTURE_BYTES,'artifact_limit')
    return value


def validate_report(raw, *, nonce, provenance, final=False):
    report=decode(raw);require(type(report) is dict and EXTRA_KEYS<=set(report))
    require(type(report.get('schema')) is int and report['schema']==SCHEMA and report.get('lane')==LANE)
    _case(report['description_case']);_sources(provenance)
    view=copy.deepcopy(report)
    for key in EXTRA_KEYS:del view[key]
    view.update(schema=core.SCHEMA,lane=core.LANE)
    core.validate_report(encode(view),nonce=nonce,provenance=provenance,final=final)
    capture=report['description_measurement']
    if report['status']=='failed':
        require(capture is None)
        return report
    exact(capture,{'schema','profile_id','profile_sha256','states'})
    require(type(capture['schema']) is int and capture['schema']==CAPTURE_SCHEMA
        and capture['profile_id']==PROFILE_ID and capture['profile_sha256']==PROFILE_SHA256)
    require(len(encode(capture))<=MAX_CAPTURE_BYTES,'artifact_limit')
    require(type(capture['states']) is list and len(capture['states'])==len(TARGETS))
    tokens=[]
    for identifier,state in zip(TARGETS,capture['states']):
        _state(state,identifier,report);tokens.append(state['observe_token'])
    require(len(set(tokens))==len(tokens))
    required=report['cleanup'] if final else {k:report['cleanup'][k] for k in ('native_processes_stopped','raw_files_removed')}
    require(all(v is True for v in required.values()))
    return report


def _outcome(report):
    states=report['description_measurement']['states']
    values=[state['comparison']['status'] for state in states[1:]]
    return next((v for v in ('case_metadata_mismatch','layout_unresolved','readback_differs') if v in values),'readback_matches')


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
