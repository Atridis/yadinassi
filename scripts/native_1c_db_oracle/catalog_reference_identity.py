"""Two controlled owned-IB identity measurements; never a runtime UUID codec.

The byte permutation is empirical and retained even when it differs from the
preregistered Tool1CD hypothesis. Readers receive neither UUIDs nor expectations.
"""
from __future__ import annotations

import hashlib
import re

import catalog_readonly_binding as base
import protocol as lifecycle
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES

SCHEMA = 39
CAPTURE_SCHEMA = 40
LANE = 'catalog-reference-identity-v1'
FAILURE_KIND = 'catalog_reference_identity_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/catalog_reference_identity.py'
READER_SOURCE = base.READER_SOURCE
CASES = ('distinct_a', 'distinct_b')
CASE_UUIDS = {'distinct_a': '00112233-4455-4677-8899-aabbccddeeff',
              'distinct_b': 'd3a17c09-e652-4b8f-95c0-2e74b836fa61'}
# Canonical UUID byte i is physical byte TOOL1CD[i], not Python bytes_le.
TOOL1CD = [12,13,14,15,10,11,8,9,0,1,2,3,4,5,6,7]
PROFILE_ID = 'owned_reference_measurement_v1'
PROFILE_DESCRIPTION = {'id': PROFILE_ID, 'base': base.PROFILE_SHA256,
    'cases': list(CASES), 'probe_states': 'NEFT', 'permutation': 'canonical_from_physical',
    'hypothesis_commit': 'd5e31816f4c9b11a445f73fc92d08803840ce599',
    'hypothesis_blob': '59ae49a5224a86a961d58f992edb1e0e5db73fb7',
    'hypothesis': TOOL1CD, 'acceptance': 'bijection_and_cross_image_case_agreement_not_hypothesis',
    'scope': 'owned_fresh_controlled_measurement_no_codec_or_live_write'}
PROFILE_SHA256 = hashlib.sha256(encode(PROFILE_DESCRIPTION)).hexdigest()
TARGETS, STAGES, FRAMINGS = base.TARGETS, base.STAGES, base.FRAMINGS
OPERATION = base.OPERATION
MAX_CAPTURE_BYTES = base.MAX_CAPTURE_BYTES
MAPPING_VERDICT, LAYOUT_VERDICT = base.MAPPING_VERDICT, base.LAYOUT_VERDICT
VERDICT = 'owned_reference_measurement_complete'
EXTRA_KEYS = base.EXTRA_KEYS | {'reference_case'}
DIAGNOSTICS = {key: set(value) for key,value in base.DIAGNOSTICS.items()}
DIAGNOSTICS['record_mismatch'].update(('reference_witness','reference_bytes','reference_permutation'))
metadata = base.metadata
build_identity_manifest = base.build_identity_manifest


class ReadbackFailure(base.OracleError):
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
            and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code, self.binding = category, code, None


def fail(code):
    raise ReadbackFailure('record_mismatch', code)


def reader_failure(error):
    classified = base.reader_failure(error)
    return ReadbackFailure(classified.category, classified.code)


def validate_permutation(value):
    require(type(value) is list and len(value) == 16
        and all(type(x) is int for x in value) and set(value) == set(range(16)))
    return value


def measure_permutation(actual_uuid, physical):
    """Private values enter only after completed reader and image verification."""
    if (type(actual_uuid) is not str
            or re.fullmatch('[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', actual_uuid) is None):
        fail('reference_witness')
    if type(physical) is not bytes or len(physical) != 16:
        fail('reference_bytes')
    canonical = bytes.fromhex(actual_uuid.replace('-', ''))
    if len(set(canonical)) != 16 or len(set(physical)) != 16 or set(canonical) != set(physical):
        fail('reference_permutation')
    return validate_permutation([physical.index(byte) for byte in canonical])


def compare_values(result, identifier, oracle, reader):
    try:
        return base.compare_values(result, identifier, oracle, reader)
    except base.ReadbackFailure as error:
        raise ReadbackFailure(error.category, error.code) from None


def measure_reference(result, identifier, oracle, actual_uuid):
    # The existing CONFIG and native DBNames comparator establishes this role.
    # No field index, offset, guessed table name or expected UUID enters reader.
    try:
        names = base._compare_mapping(result, oracle)
    except base.ReadbackFailure as error:
        raise ReadbackFailure(error.category, error.code) from None
    if identifier == 'baseline':
        if result.records.rows or actual_uuid is not None: fail('reference_witness')
        return None
    if len(result.records.rows) != 1 or actual_uuid is None: fail('reference_witness')
    values = {field.declaration.name: field.value for field in result.records.rows[0].fields}
    return measure_permutation(actual_uuid, values.get(names['reference']))


def empty_report(nonce, provenance, *, reference_case):
    require(type(reference_case) is str and reference_case in CASES, 'invalid_input')
    report = base.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, reference_case=reference_case)
    return report


def begin_capture(evidence, report, reader):
    capture, oracle, selector = base.begin_capture(evidence, report, reader)
    capture.update(schema=CAPTURE_SCHEMA, profile_id=PROFILE_ID, profile_sha256=PROFILE_SHA256,
        rendered_module_sha256=rendered_module_sha256(report['nonce'], report['reference_case']), installation=None)
    return capture, oracle, selector


def bind_state(identifier, evidence, report, origin_framing, observer_framing):
    return base.bind_state(identifier, evidence, report, origin_framing, observer_framing)


def rendered_module_sha256(nonce, case):
    from inject_metadata import _module, _matrix
    raw = _module('NativeOracleServer.bsl', nonce, '/tmp/onec-db-oracle/evidence', reference_case=case)
    raw = _matrix(True).server_module(raw, ValueError)
    return canonical_module_sha256(raw)


def canonical_module_sha256(raw):
    # Same text domain as verify_redump: UTF-8 BOM removed and universal LF.
    require(type(raw) is bytes and 0 < len(raw) <= 1048576, 'metadata_rejected')
    text = raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _validate_reference(value, identifier):
    exact(value, {'witness_sha256','before','after','before_present','after_present',
                  'permutation','hypothesis_match'})
    require(digest(value['witness_sha256']))
    present = identifier != 'baseline'
    for prefix in ('before','after'):
        codes = value[prefix]
        require(type(value[prefix+'_present']) is bool and value[prefix+'_present'] is present)
        require(type(codes) is str and len(codes) == 12 and all(c in 'EFT' for c in codes[:9]))
        require(all(c in 'EFT' for c in codes[9:]) if present else codes[9:] == 'NNN')
    if present:
        validate_permutation(value['permutation'])
        require(type(value['hypothesis_match']) is bool
                and value['hypothesis_match'] == (value['permutation'] == TOOL1CD))
    else:
        require(value['permutation'] is None and value['hypothesis_match'] is None)


def discard_capture(report, failure=None, *, final=False):
    if report.get('schema') != SCHEMA: return
    old = report.get('record_readback')
    report['record_readback'] = None
    for field, success in (('metadata_validation', metadata.METADATA_VERDICT),
            ('reader_validation', metadata.VERDICT), ('mapping_validation', MAPPING_VERDICT),
            ('layout_validation', LAYOUT_VERDICT), ('record_validation', VERDICT)):
        previous = report[field]
        report[field] = 'discarded' if previous in (success, 'discarded') else ('failed' if previous == 'failed' else 'not_run')
    if type(failure) is ReadbackFailure:
        old = {'schema': CAPTURE_SCHEMA, 'status': 'failed', 'category': failure.category, 'code': failure.code}
    cleanup = report['cleanup'] if final else {key: report['cleanup'][key]
        for key in ('native_processes_stopped','raw_files_removed')}
    if (all(value is True for value in cleanup.values()) and report.get('failure_kind') == FAILURE_KIND
            and report.get('failed_stage') in ('baseline','create','update') and type(old) is dict
            and set(old) == {'schema','status','category','code'} and old.get('schema') == CAPTURE_SCHEMA
            and old.get('status') == 'failed' and old.get('category') in DIAGNOSTICS
            and old.get('code') in DIAGNOSTICS[old['category']]):
        report['record_readback'] = old
        report['record_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report)
            and type(report.get('reference_case')) is str and report['reference_case'] in CASES
            and report['projection_mode'] == metadata.PROJECTION_MODE
            and report['comparison_policy'] == metadata.COMPARISON_POLICY
            and report['native_compatibility'] == 'not_claimed')
    from inputs import CATALOG_REFERENCE_SOURCE_FILES
    require(set(provenance['sources']) == set(CATALOG_REFERENCE_SOURCE_FILES)
            and MODULE_SOURCE in CATALOG_REFERENCE_SOURCE_FILES and READER_SOURCE in CATALOG_REFERENCE_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    success_values = {'metadata_validation': metadata.METADATA_VERDICT, 'reader_validation': metadata.VERDICT,
        'mapping_validation': MAPPING_VERDICT, 'layout_validation': LAYOUT_VERDICT, 'record_validation': VERDICT}
    for key, passed in success_values.items():
        require(report[key] in ('not_run','failed','discarded',passed))
    lifecycle_view = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    lifecycle_view.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] in ('baseline','create','update'))
        lifecycle_view['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        lifecycle_view['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(lifecycle_view), nonce=nonce, provenance=provenance, final=final)
    capture = report['record_readback']
    if capture is not None: require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    if report['status'] != 'ok':
        require(all(report[key] != passed for key, passed in success_values.items()))
        if capture is not None:
            require(report['failure_kind'] == FAILURE_KIND and report['record_validation'] == 'failed')
            exact(capture, {'schema','status','category','code'})
            require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'failed'
                    and type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                    and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
            required = report['cleanup'] if final else {key: report['cleanup'][key]
                for key in ('native_processes_stopped','raw_files_removed')}
            require(all(value is True for value in required.values()))
        return report
    require(all(report[key] == passed for key, passed in success_values.items()))
    exact(capture, {'schema','status','profile_id','profile_sha256','record_reader_source_sha256','audit','identity_manifest_sha256','catalog_count','attribute_count','states','rendered_module_sha256','installation'})
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'matched'
            and capture['profile_id'] == PROFILE_ID and capture['profile_sha256'] == PROFILE_SHA256
            and capture['record_reader_source_sha256'] == provenance['sources'][READER_SOURCE])
    require(capture['rendered_module_sha256'] == rendered_module_sha256(nonce, report['reference_case']), 'provenance_mismatch')
    installation = capture['installation']
    exact(installation, {'status','token','witness_sha256'})
    require(installation['status'] == 'succeeded' and digest(installation['witness_sha256'])
        and type(installation['token']) is str and re.fullmatch('[0-9a-f]{32}', installation['token']) is not None)
    measured = capture['audit']
    exact(measured, metadata.BINDING_KEYS)
    metadata._validate_binding(measured, report, nonce=nonce, provenance=provenance, final=final)
    require(digest(capture['identity_manifest_sha256'])
            and type(capture['catalog_count']) is int and capture['catalog_count']==3
            and type(capture['attribute_count']) is int and capture['attribute_count']==2)
    require(type(capture['states']) is list and len(capture['states']) == 3)
    for state, identifier in zip(capture['states'], TARGETS):
        require(type(state) is dict and 'reference' in state)
        base._validate_state({key:value for key,value in state.items() if key != 'reference'}, identifier, report)
        _validate_reference(state['reference'], identifier)
    require(capture['states'][1]['reference']['permutation'] == capture['states'][2]['reference']['permutation'])
    tokens = [measured['token']] + [state['observe_token'] for state in capture['states']]
    require(len(set(tokens + [installation['token']])) == 5)
    return report


def aggregate_reports(raw_a, raw_b, *, provenance):
    """Hash-bind two separately bounded reports; never embed their captures.

    Invocation order/fresh host roots are enforced by the dependent CI jobs and
    the host's A preflight. A report alone is not proof of that execution order.
    """
    reports = []
    for raw, case in zip((raw_a, raw_b), CASES):
        candidate = decode(raw)
        require(type(candidate) is dict and candidate.get('reference_case') == case)
        report = validate_report(raw, nonce=candidate.get('nonce'), provenance=provenance, final=True)
        require(report['accepted'] is True and all(value is True for value in report['cleanup'].values()))
        reports.append(report)
    a, b = reports
    require(a['nonce'] != b['nonce'] and a['provenance'] == b['provenance'], 'provenance_mismatch')
    permutation_a = a['record_readback']['states'][1]['reference']['permutation']
    permutation_b = b['record_readback']['states'][1]['reference']['permutation']
    # Retain both observed permutations if they disagree; no inferred codec.
    from contract import source_binding
    value = {'schema': 41, 'lane': LANE, 'status': 'measured',
        'commit': provenance['commit'], 'tree': provenance['tree'],
        'source_manifest_sha256': source_binding(provenance),
        'profile_sha256': PROFILE_SHA256, 'actual_version': a['provenance']['actual_version'],
        'cases': [{'case':case, 'report_sha256':hashlib.sha256(raw).hexdigest(),
                   'permutation':permutation, 'hypothesis_match':permutation == TOOL1CD}
                  for case,raw,permutation in zip(CASES,(raw_a,raw_b),(permutation_a,permutation_b))],
        'permutations_agree': permutation_a == permutation_b,
        'codec_approved': False, 'native_compatibility': 'not_claimed'}
    require(len(encode(value)) <= 2048, 'artifact_limit')
    return value
