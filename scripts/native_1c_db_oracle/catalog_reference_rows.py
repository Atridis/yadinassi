"""Closed native witness verification of the opt-in runtime Catalog row API.

Typed projection is checked independently of the existing raw/codec verdicts.
Native UUIDs never enter the reader; this policy runs after completed image reads.
"""
from __future__ import annotations

import copy
import hashlib
from uuid import UUID

import catalog_reference_codec as codec
from protocol import decode, encode, require

SCHEMA, CAPTURE_SCHEMA = 45, 46
LANE = 'catalog-reference-rows-v1'
PROFILE_ID = 'rows-v1'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/catalog_reference_rows.py'
READER_SOURCE = 'yadinassi/storage/catalog_reader.py'
CODEC_SOURCE = codec.CODEC_SOURCE
VERDICT = 'rows_verified'
PROFILE_SHA256 = hashlib.sha256(encode({'id': PROFILE_ID,
    'codec': codec.PROFILE_SHA256, 'reader_source': READER_SOURCE,
    'coverage': 'created,updated/origin,observer/typed_uuid',
    'acceptance': 'exact_typed_result_physical_identity_and_actual_native_uuid'})).hexdigest()
TARGETS, STAGES, FRAMINGS = codec.TARGETS, codec.STAGES, codec.FRAMINGS
OPERATION, MAX_CAPTURE_BYTES = codec.OPERATION, codec.MAX_CAPTURE_BYTES
MAPPING_VERDICT, LAYOUT_VERDICT = codec.MAPPING_VERDICT, codec.LAYOUT_VERDICT
FAILURE_KIND = codec.FAILURE_KIND
metadata = codec.metadata
build_identity_manifest = codec.build_identity_manifest
ReadbackFailure = codec.ReadbackFailure
reader_failure = codec.reader_failure
fail = codec.fail
compare_values = codec.compare_values
measure_reference = codec.measure_reference
verify_reference = codec.verify_reference
bind_state = codec.bind_state
rendered_module_sha256 = codec.rendered_module_sha256
canonical_module_sha256 = codec.canonical_module_sha256
_validate_reference = codec._validate_reference
TOOL1CD, CASES = codec.TOOL1CD, codec.CASES


def admit_rows(result, reader):
    """Keep only an exact-type raw view of the same completed runtime result."""
    try:
        return reader._raw_rows_view(result)
    except reader.catalog_module.CatalogError as error:
        raise reader_failure(error) from None


def verify_projection(result, identifier, actual_uuid):
    # admit_rows has already established count/order/physical object identity.
    if identifier == 'baseline':
        if result.rows or result.records.rows or actual_uuid is not None:
            fail('reference_bytes')
        return 'N'
    if identifier not in TARGETS or len(result.rows) != 1:
        fail('reference_bytes')
    # Requiring the actual committed witness, not the requested case UUID.
    try:
        expected = UUID(actual_uuid)
    except (ValueError, TypeError, AttributeError):
        fail('reference_witness')
    if type(result.rows[0].reference_uuid) is not UUID or result.rows[0].reference_uuid != expected:
        fail('reference_bytes')
    return 'T'


def empty_report(nonce, provenance, *, reference_case):
    report = codec.empty_report(nonce, provenance, reference_case=reference_case)
    report.update(schema=SCHEMA, lane=LANE)
    return report


def begin_capture(evidence, report, reader):
    capture, oracle, selector = codec.begin_capture(evidence, report, reader)
    capture.update(schema=CAPTURE_SCHEMA, profile_id=PROFILE_ID,
                   profile_sha256=PROFILE_SHA256)
    return capture, oracle, selector


def _codec_view(report):
    view = copy.deepcopy(report)
    view.update(schema=codec.SCHEMA, lane=codec.LANE)
    if view['record_validation'] == VERDICT:
        view['record_validation'] = codec.VERDICT
    capture = view['record_readback']
    if capture is not None:
        capture['schema'] = codec.CAPTURE_SCHEMA
        if capture.get('status') == 'matched':
            capture.update(profile_id=codec.PROFILE_ID, profile_sha256=codec.PROFILE_SHA256)
            for state in capture['states']:
                del state['projection']
    return view


def discard_capture(report, failure=None, *, final=False):
    if report.get('schema') != SCHEMA:
        return
    report['schema'] = codec.SCHEMA
    capture = report.get('record_readback')
    if type(capture) is dict:
        capture['schema'] = codec.CAPTURE_SCHEMA
    if report.get('record_validation') == VERDICT:
        report['record_validation'] = codec.VERDICT
    codec.discard_capture(report, failure, final=final)
    report['schema'] = SCHEMA
    if type(report.get('record_readback')) is dict:
        report['record_readback']['schema'] = CAPTURE_SCHEMA


def validate_report(raw, *, nonce, provenance, final=False):
    from inputs import CATALOG_ROWS_SOURCE_FILES
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int
            and report['schema'] == SCHEMA and report.get('lane') == LANE)
    require(set(provenance['sources']) == set(CATALOG_ROWS_SOURCE_FILES), 'provenance_mismatch')
    require(report.get('record_validation') in ('not_run', 'failed', 'discarded', VERDICT))
    capture = report.get('record_readback')
    if capture is not None:
        require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
        require(type(capture) is dict and type(capture.get('schema')) is int
                and capture['schema'] == CAPTURE_SCHEMA)
        if capture.get('status') == 'matched':
            require(capture.get('profile_id') == PROFILE_ID
                    and capture.get('profile_sha256') == PROFILE_SHA256)
            states = capture.get('states')
            require(type(states) is list and len(states) == 3)
            for state, identifier in zip(states, TARGETS):
                require(type(state) is dict and state.get('snapshot') == identifier)
                require(type(state.get('projection')) is str
                        and state['projection'] == ('NN' if identifier == 'baseline' else 'TT'))
    codec._validate_report(encode(_codec_view(report)), nonce=nonce, provenance=provenance,
                           final=final, rows_profile=True)
    return report


def aggregate_reports(raw_a, raw_b, *, provenance):
    from contract import source_binding
    reports = []
    for raw, case in zip((raw_a, raw_b), CASES):
        value = decode(raw)
        report = validate_report(raw, nonce=value.get('nonce'), provenance=provenance, final=True)
        require(report['reference_case'] == case and report['accepted'] is True
                and all(value is True for value in report['cleanup'].values()))
        reports.append(report)
    require(reports[0]['nonce'] != reports[1]['nonce']
            and reports[0]['provenance'] == reports[1]['provenance'], 'provenance_mismatch')
    value = {'schema': 47, 'lane': LANE, 'status': 'verified',
        'commit': provenance['commit'], 'tree': provenance['tree'],
        'source_manifest_sha256': source_binding(provenance),
        'profile_sha256': PROFILE_SHA256,
        'reader_source_sha256': provenance['sources'][READER_SOURCE],
        'codec_source_sha256': provenance['sources'][CODEC_SOURCE],
        'actual_version': reports[0]['provenance']['actual_version'],
        'cases': [{'case': case, 'report_sha256': hashlib.sha256(raw).hexdigest()}
                  for case, raw in zip(CASES, (raw_a, raw_b))],
        'rows_verified': True, 'codec_verified': True,
        'projected_comparisons': 8, 'codec_comparisons': 16,
        'native_compatibility': 'not_claimed'}
    require(len(encode(value)) <= 2048, 'artifact_limit')
    return value
