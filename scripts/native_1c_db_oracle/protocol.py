"""Finite public file-DB oracle protocol. No native bytes or text cross this boundary.

This module and synthetic fixture tests are not native evidence. Version 1 does
not parse a database header: 64 KiB byte windows are deliberately not pages.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from snapshots import MAX_FILE_BYTES, OracleError, validate_comparison, validate_pair

SCHEMA = 1
LANE = 'native-file-db-oracle-v1'
MAX_REPORT_BYTES = 32768
IMAGE = 'ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728'
VERSION = '8.3.27.1508'
STAGES = ('preflight', 'seed_v1', 'baseline', 'create', 'update', 'export_cf',
          'load_cf', 'apply_cf', 'dump_dt', 'delete', 'restore_dt', 'verify_restore', 'cleanup')
CHECKS = {
    'preflight': ('inputs_verified', 'isolated_runtime'),
    'seed_v1': ('metadata_reimported', 'two_users_verified'),
    'baseline': ('named_crud', 'admin_audit', 'empty_v1'),
    'create': ('matched_control', 'reopened_row', 'reference_preserved'),
    'update': ('matched_control', 'reopened_row', 'reference_preserved'),
    'export_cf': ('v1_exported', 'v2_exported', 'producer_only'),
    'load_cf': ('matched_control', 'designer_v2', 'runtime_v1', 'row_preserved'),
    'apply_cf': ('observational_before_after', 'runtime_v2', 'row_preserved'),
    'dump_dt': ('snapshot_before_export', 'auxiliary_only'),
    'delete': ('matched_control', 'physical_delete'),
    'restore_dt': ('distinct_destination', 'frozen_before_observation', 'no_update_after_restore'),
    'verify_restore': ('row_restored', 'reference_preserved', 'metadata_preserved', 'users_verified', 'original_still_deleted'),
    'cleanup': ('native_processes_stopped', 'raw_files_removed'),
}
SNAPSHOTS = ('baseline', 'create_control', 'created', 'update_control', 'updated',
             'load_control', 'loaded', 'applied',
             'delete_control', 'deleted', 'restored')
SNAPSHOT_STAGE = dict(zip(SNAPSHOTS, ('baseline','create','create','update','update',
    'load_cf','load_cf','apply_cf','delete','delete','restore_dt')))
COMPARISONS = {
    'create': ('baseline','create_control','created'),
    'update': ('created','update_control','updated'),
    'load_cf': ('updated','load_control','loaded'),
    'apply_cf': ('loaded',None,'applied'),
    'delete': ('applied','delete_control','deleted'),
}
ARTIFACTS = {'cf_v1': 'baseline', 'cf_v2': 'baseline', 'dt_updated': 'applied'}
FAILURES = frozenset({'none', 'invalid_input', 'provenance_mismatch', 'permission_mismatch',
    'unsupported_platform_command', 'process_failed', 'timeout', 'invalid_dump_result',
    'stale_evidence', 'artifact_missing', 'artifact_limit', 'invalid_marker',
    'logical_mismatch', 'snapshot_not_quiescent', 'snapshot_changed', 'invalid_header',
    'cleanup_unverified', 'metadata_rejected', 'version_mismatch', 'unexpected_failure',
    'registry_credentials_missing', 'container_unavailable', 'transport_invalid'})
# Seed launch diagnostics are a finite enum, never native text or numeric exit data.
SEED_OPERATIONS = ('create', 'dump_empty', 'import', 'apply', 'redump', 'bootstrap')
SEED_FAILURE_CATEGORIES = frozenset({'invalid_input', 'permission_mismatch',
    'process_failed', 'timeout', 'invalid_dump_result', 'stale_evidence',
    'artifact_missing', 'artifact_limit', 'invalid_marker', 'logical_mismatch',
    'snapshot_not_quiescent', 'snapshot_changed', 'metadata_rejected',
    'version_mismatch', 'unexpected_failure'})
SEED_FAILURES = frozenset('seed_' + operation + '_' + category
    for operation in SEED_OPERATIONS for category in SEED_FAILURE_CATEGORIES)
FAILURES = FAILURES | SEED_FAILURES
LOGICAL_KEYS = {'count','code','payload','amount','deletion_mark','same_reference',
    'payload_length','amount_digits','amount_scale','designer_version','applied_version',
    'user','role_verified','nonprivileged'}
MARKER_KEYS = {'schema','nonce','token','operation','status','actual_version','user',
    'role_verified','nonprivileged','metadata_version','count','code','payload','amount',
    'deletion_mark','same_reference','users_verified','payload_length','amount_digits','amount_scale'}


def require(value, kind='transport_invalid'):
    if not value:
        raise OracleError(kind)


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys))


def integer(value, maximum=MAX_FILE_BYTES, minimum=0):
    return type(value) is int and minimum <= value <= maximum


def digest(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def decode(raw: bytes):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_REPORT_BYTES)
    try:
        return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                          parse_constant=lambda _: require(False))
    except (ValueError, UnicodeError, RecursionError):
        raise OracleError('transport_invalid') from None


def encode(report):
    raw = json.dumps(report, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    require(len(raw) < MAX_REPORT_BYTES, 'artifact_limit')
    return raw


def physical(value):
    exact(value, {'bytes','sha256','header','page_analysis'})
    require(integer(value['bytes'], minimum=1) and digest(value['sha256']))
    require(value['header'] == 'unknown' and value['page_analysis'] == 'unsupported')


def expected_logical(identifier):
    require(identifier in SNAPSHOTS)
    empty = identifier in ('baseline','create_control','deleted')
    initial = identifier in ('created','update_control')
    applied = identifier in ('applied','delete_control','deleted','restored')
    pending = identifier == 'loaded'
    return {'count': 0 if empty else 1, 'code': None if empty else 'K1',
        'payload': None if empty else ('alpha' if initial else 'beta'),
        'amount': None if empty else ('1.25' if initial else '-2.50'),
        'deletion_mark': None if empty else False,
        'same_reference': False if identifier == 'deleted' else (None if empty else True),
        'payload_length': 64 if applied else 32, 'amount_digits':9,'amount_scale':2,
        'designer_version':2 if applied or pending else 1, 'applied_version':2 if applied else 1,
        'user':'NativeOracleCRUD', 'role_verified':True,'nonprivileged':True}


def validate_logical(value, identifier):
    exact(value, LOGICAL_KEYS)
    expected = expected_logical(identifier)
    require(all(type(value[key]) is type(wanted) and value[key] == wanted
                for key,wanted in expected.items()), 'logical_mismatch')


def marker(raw, *, nonce, token, operation):
    data = decode(raw)
    exact(data, MARKER_KEYS)
    require(data['schema'] == 1 and type(data['schema']) is int and data['nonce'] == nonce
            and data['token'] == token and data['operation'] == operation and data['status'] == 'ok', 'invalid_marker')
    require(data['actual_version'] == VERSION, 'version_mismatch')
    require(all(type(data[key]) is bool for key in ('role_verified','nonprivileged','users_verified')), 'invalid_marker')
    require(data['role_verified'] is True, 'permission_mismatch')
    if operation in ('bootstrap','audit'):
        require(data['user'] == ('' if operation == 'bootstrap' else 'NativeOracleSetup')
                and data['users_verified'] is True
                and data['nonprivileged'] is (operation == 'audit'), 'permission_mismatch')
        require(all(data[key] is None for key in ('count','code','payload','amount','deletion_mark','same_reference')), 'invalid_marker')
    else:
        require(operation in ('observe','create','update','delete') and data['user'] == 'NativeOracleCRUD'
                and data['nonprivileged'] is True and data['users_verified'] is False, 'permission_mismatch')
        require(integer(data['count'], 1) and data['code'] in (None,'K1')
                and data['payload'] in (None,'alpha','beta') and data['amount'] in (None,'1.25','-2.50')
                and (data['deletion_mark'] is None or type(data['deletion_mark']) is bool)
                and (data['same_reference'] is None or type(data['same_reference']) is bool), 'invalid_marker')
    require(type(data['metadata_version']) is int and data['metadata_version'] in (1,2), 'invalid_marker')
    require(type(data['payload_length']) is int and data['payload_length'] == 32 * data['metadata_version']
            and type(data['amount_digits']) is int and data['amount_digits'] == 9
            and type(data['amount_scale']) is int and data['amount_scale'] == 2, 'logical_mismatch')
    return data


def logical_from_marker(data, designer_version):
    return {key:data[key] for key in LOGICAL_KEYS - {'designer_version','applied_version'}} | {
        'designer_version':designer_version, 'applied_version':data['metadata_version']}


def empty_report(nonce, provenance):
    return {'schema':SCHEMA,'lane':LANE,'nonce':nonce,'status':'failed',
        'failed_stage':'preflight','failure_kind':'unexpected_failure','provenance':provenance,
        'stages':[{'id':stage,'status':'not_started','checks':{key:False for key in CHECKS[stage]}} for stage in STAGES],
        'snapshots':[], 'artifacts':[], 'comparisons':[],
        'cleanup':{'native_processes_stopped':False,'raw_files_removed':False,
                   'container_removed':False,'private_staging_removed':False},'accepted':False}


def validate_provenance(value, expected):
    exact(value, {'commit','tree','sources','image','platform','actual_version','locale','timezone'})
    require(all(type(value[key]) is str and re.fullmatch('[0-9a-f]{40}',value[key]) for key in ('commit','tree')))
    require(type(value['sources']) is dict and value['sources'] == expected['sources']
            and all(digest(item) for item in value['sources'].values()))
    require(all(value[key] == expected[key] for key in ('commit','tree','image','platform','locale','timezone')))
    require(value['actual_version'] in (None,VERSION))


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    exact(report, {'schema','lane','nonce','status','failed_stage','failure_kind','provenance',
        'stages','snapshots','artifacts','comparisons','cleanup','accepted'})
    require(type(report['schema']) is int and report['schema'] == SCHEMA and report['lane'] == LANE
            and report['nonce'] == nonce and re.fullmatch('[0-9a-f]{32}',nonce) is not None)
    validate_provenance(report['provenance'], provenance)
    require(report['status'] in ('ok','failed') and type(report['failure_kind']) is str
            and report['failure_kind'] in FAILURES)
    if report['failure_kind'] in SEED_FAILURES:
        require(report['status']=='failed' and report['failed_stage']=='seed_v1')
    require(type(report['accepted']) is bool)
    require(type(report['stages']) is list and len(report['stages']) == len(STAGES))
    failed = []
    stopped = False
    for stage, entry in zip(STAGES,report['stages']):
        exact(entry, {'id','status','checks'})
        require(entry['id'] == stage and entry['status'] in ('not_started','ok','failed'))
        exact(entry['checks'],CHECKS[stage])
        require(all(type(value) is bool for value in entry['checks'].values()))
        if entry['status'] == 'ok':
            require(all(entry['checks'].values()) and (not stopped or stage == 'cleanup'))
        elif entry['status'] == 'failed':
            failed.append(stage); stopped = True
        else:
            require(not any(entry['checks'].values())); stopped = True
    primary=[entry['status'] for entry in report['stages'][:-1]]
    if 'failed' in primary:
        position=primary.index('failed')
        require(primary == ['ok']*position + ['failed'] + ['not_started']*(len(primary)-position-1))
    else:
        require(primary == ['ok']*len(primary))
    require(type(report['snapshots']) is list and len(report['snapshots']) <= len(SNAPSHOTS))
    ids=[]
    for item in report['snapshots']:
        exact(item, {'id','physical','logical','quiescent','copy_verified'})
        require(item['id'] in SNAPSHOTS and item['id'] not in ids)
        ids.append(item['id'])
        physical(item['physical']); validate_logical(item['logical'],item['id'])
        require(item['quiescent'] is True and item['copy_verified'] is True)
    require(ids == list(SNAPSHOTS[:len(ids)]))
    stage_states={entry['id']:entry['status'] for entry in report['stages']}
    for identifier in ids:
        require(stage_states[SNAPSHOT_STAGE[identifier]] in ('ok','failed'))
    for identifier,owner in SNAPSHOT_STAGE.items():
        if stage_states[owner]=='ok': require(identifier in ids)
    require(type(report['comparisons']) is list and len(report['comparisons']) <= len(COMPARISONS))
    names=[]
    by_id={item['id']:item for item in report['snapshots']}
    for item in report['comparisons']:
        exact(item, {'id','kind','source','control','treatment','physical'})
        require(item['id'] in COMPARISONS and item['id'] not in names)
        names.append(item['id'])
        pair=COMPARISONS[item['id']]
        require(tuple(item[key] for key in ('source','control','treatment')) == pair
                and all(name in ids for name in pair if name is not None))
        if item['id']=='apply_cf':
            require(item['kind']=='observational' and item['control'] is None)
            validate_pair(item['physical'])
            require(tuple(item['physical'][key] for key in ('predecessor_bytes','treatment_bytes')) ==
                    tuple(by_id[name]['physical']['bytes'] for name in (pair[0],pair[2])))
        else:
            require(item['kind']=='matched_control')
            validate_comparison(item['physical'])
            require(tuple(item['physical'][key] for key in ('predecessor_bytes','control_bytes','treatment_bytes')) ==
                    tuple(by_id[name]['physical']['bytes'] for name in pair))
    require(names == list(COMPARISONS)[:len(names)])
    for name in names: require(stage_states[name] in ('ok','failed'))
    for name in COMPARISONS:
        if stage_states[name]=='ok': require(name in names)
    require(type(report['artifacts']) is list and len(report['artifacts']) <= 3)
    artifact_names=[]
    for item in report['artifacts']:
        exact(item, {'id','status','source','physical'})
        require(item['id'] in ARTIFACTS and item['id'] not in artifact_names
                and item['source'] == ARTIFACTS[item['id']] and item['source'] in ids and item['status'] == 'ok')
        artifact_names.append(item['id']); physical(item['physical'])
    require(artifact_names == [name for name in ARTIFACTS if name in artifact_names])
    exact(report['cleanup'],{'native_processes_stopped','raw_files_removed','container_removed','private_staging_removed'})
    require(all(type(value) is bool for value in report['cleanup'].values()))
    require(all(report['cleanup'][key] is report['stages'][-1]['checks'][key]
                for key in ('native_processes_stopped','raw_files_removed')))
    success = report['status'] == 'ok'
    if success:
        require(all(item['status']=='ok' for item in report['stages']) and report['failed_stage'] is None
                and report['failure_kind']=='none' and ids==list(SNAPSHOTS) and names==list(COMPARISONS)
                and artifact_names==list(ARTIFACTS) and report['provenance']['actual_version']==VERSION)
    else:
        require(report['failed_stage'] in STAGES and report['failure_kind'] != 'none'
                and report['failed_stage'] in failed and report['accepted'] is False)
        # Failure output never advertises a usable export, including partial success.
        require(not report['artifacts'])
    require(report['accepted'] is (success and final and all(report['cleanup'].values())))
    if not final:
        require(report['cleanup']['container_removed'] is False and report['cleanup']['private_staging_removed'] is False)
    return report
