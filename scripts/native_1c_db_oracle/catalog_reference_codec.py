"""Separate source-pinned verification of real private UUID/physical witnesses.

The original identity measurement continues to accept unexpected permutations.
This profile requires the runtime codec to match each independently read image.
"""
from __future__ import annotations

import copy
import hashlib
from uuid import UUID

import catalog_reference_identity as measurement
from protocol import decode, encode, exact, require

SCHEMA, CAPTURE_SCHEMA = 42, 43
LANE = 'catalog-reference-codec-v1'
PROFILE_ID = 'codec-v1'
CODEC_SOURCE = 'yadinassi/storage/catalog_reference_uuid.py'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/catalog_reference_codec.py'
VERDICT = 'codec_verified'
FAILURE_KIND = measurement.FAILURE_KIND
PROFILE_SHA256 = hashlib.sha256(encode({'id': PROFILE_ID,
    'measurement': measurement.PROFILE_SHA256, 'codec_source': CODEC_SOURCE,
    'coverage': 'created,updated/origin,observer/decode,encode',
    'acceptance': 'actual_native_uuid_and_independently_read_physical_bytes'})).hexdigest()
# The existing lifecycle operates on this explicit policy interface.
TARGETS, STAGES, FRAMINGS = measurement.TARGETS, measurement.STAGES, measurement.FRAMINGS
OPERATION = measurement.OPERATION
MAX_CAPTURE_BYTES = 8192  # New schema only; full admitted structure is bounded below this.
MAPPING_VERDICT, LAYOUT_VERDICT = measurement.MAPPING_VERDICT, measurement.LAYOUT_VERDICT
metadata = measurement.metadata
build_identity_manifest = measurement.build_identity_manifest
ReadbackFailure = measurement.ReadbackFailure
reader_failure = measurement.reader_failure
fail = measurement.fail
compare_values = measurement.compare_values
measure_reference = measurement.measure_reference
bind_state = measurement.bind_state
rendered_module_sha256 = measurement.rendered_module_sha256
_validate_reference = measurement._validate_reference
TOOL1CD, CASES = measurement.TOOL1CD, measurement.CASES


def verify_reference(result, identifier, oracle, actual_uuid):
    """Called only after image admission, reader completion and digest checks."""
    # Revalidate the native witness/mapping/row boundary, never manufacture p
    # from the measured permutation or the requested UUID.
    measurement.measure_reference(result, identifier, oracle, actual_uuid)
    if identifier == 'baseline':
        return 'NN'
    names = measurement.base._compare_mapping(result, oracle)
    values = {field.declaration.name: field.value
              for field in result.records.rows[0].fields}
    physical = values[names['reference']]
    # Deliberately lazy: neither reader initialization nor baseline imports codec.
    from catalog_reference_uuid import (decode_catalog_reference_uuid,
                                        encode_catalog_reference_uuid)
    value = UUID(actual_uuid)
    decoded = decode_catalog_reference_uuid(physical)
    encoded = encode_catalog_reference_uuid(value)
    # Evaluate both directions against independent witness, not only roundtrip.
    return ('T' if type(decoded) is UUID and decoded == value else 'F') + (
            'T' if type(encoded) is bytes and encoded == physical else 'F')


def empty_report(nonce, provenance, *, reference_case):
    report = measurement.empty_report(nonce, provenance, reference_case=reference_case)
    report.update(schema=SCHEMA, lane=LANE)
    return report


def begin_capture(evidence, report, reader):
    capture, oracle, selector = measurement.begin_capture(evidence, report, reader)
    capture.update(schema=CAPTURE_SCHEMA, profile_id=PROFILE_ID,
                   profile_sha256=PROFILE_SHA256)
    return capture, oracle, selector


def _measurement_view(report):
    """Private structural projection after new-profile fields are validated."""
    view = copy.deepcopy(report)
    view.update(schema=measurement.SCHEMA, lane=measurement.LANE)
    if view['record_validation'] == VERDICT:
        view['record_validation'] = measurement.VERDICT
    capture = view['record_readback']
    if capture is not None:
        capture['schema'] = measurement.CAPTURE_SCHEMA
        if capture.get('status') == 'matched':
            capture.update(profile_id=measurement.PROFILE_ID,
                           profile_sha256=measurement.PROFILE_SHA256)
            for state in capture['states']:
                del state['codec']
    return view


def discard_capture(report, failure=None, *, final=False):
    if report.get('schema') != SCHEMA:
        return
    # Failure cleanup can run with a partial capture. It must not need success
    # projection or assume complete codec coverage.
    report['schema'] = measurement.SCHEMA
    capture = report.get('record_readback')
    if type(capture) is dict:
        capture['schema'] = measurement.CAPTURE_SCHEMA
    if report.get('record_validation') == VERDICT:
        report['record_validation'] = measurement.VERDICT
    measurement.discard_capture(report, failure, final=final)
    report['schema'] = SCHEMA
    if type(report.get('record_readback')) is dict:
        report['record_readback']['schema'] = CAPTURE_SCHEMA


def validate_report(raw, *, nonce, provenance, final=False):
    from inputs import CATALOG_CODEC_SOURCE_FILES
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int
            and report['schema'] == SCHEMA and report.get('lane') == LANE)
    require(set(provenance['sources']) == set(CATALOG_CODEC_SOURCE_FILES)
            and CODEC_SOURCE in provenance['sources'] and MODULE_SOURCE in provenance['sources'],
            'provenance_mismatch')
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
                # Fixed order: origin decode/encode, observer decode/encode.
                require(type(state.get('codec')) is str
                        and state['codec'] == ('NNNN' if identifier == 'baseline' else 'TTTT'))
                if identifier != 'baseline':
                    reference = state.get('reference')
                    require(type(reference) is dict
                            and reference.get('permutation') == TOOL1CD
                            and reference.get('hypothesis_match') is True)
    view = _measurement_view(report)
    measurement._validate_report(encode(view), nonce=nonce, provenance=provenance,
                                 final=final, source_files=CATALOG_CODEC_SOURCE_FILES)
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
    value = {'schema': 44, 'lane': LANE, 'status': 'verified',
        'commit': provenance['commit'], 'tree': provenance['tree'],
        'source_manifest_sha256': source_binding(provenance),
        'profile_sha256': PROFILE_SHA256,
        'codec_source_sha256': provenance['sources'][CODEC_SOURCE],
        'actual_version': reports[0]['provenance']['actual_version'],
        'cases': [{'case': case, 'report_sha256': hashlib.sha256(raw).hexdigest()}
                  for case, raw in zip(CASES, (raw_a, raw_b))],
        'codec_verified': True, 'native_compatibility': 'not_claimed'}
    require(len(encode(value)) <= 2048, 'artifact_limit')
    return value
