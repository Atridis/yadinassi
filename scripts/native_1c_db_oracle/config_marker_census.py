"""Closed CONFIG marker census; diagnostic success never accepts framing.

One source-bound candidate stride is used on the existing owned baseline
postimage. Only neutral first/later marker classes and counts are projected.
Filenames, active/free semantics, free lists and BLOB contents are not read.
The strict framing profile and its failure evidence remain separate.
"""
from __future__ import annotations

import hashlib
import json

import comparison
import config_framing_reader as framing
import filedb_catalog as reader
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 12
CAPTURE_SCHEMA = 13
LANE = 'owned_config_marker_census_v1'
FAILURE_KIND = 'config_marker_census_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/config_marker_census.py'
FRAMING_READER_SOURCE = 'scripts/native_1c_db_oracle/config_framing_reader.py'
READER_SOURCE = comparison.READER_SOURCE
OPERATION = metadata.OPERATION
TARGET = 'CONFIG'
RECIPE_ID = 'config_marker_census_8380_8192_v1'
# Independently literal diagnostic recipe, never a captured marker expectation.
DECLARATIONS = (
    ('FILENAME', 'NVC', 0, 128, 0, 'CI'),
    ('CREATION', 'DT', 0, 0, 0, 'CS'),
    ('MODIFIED', 'DT', 0, 0, 0, 'CS'),
    ('ATTRIBUTES', 'N', 0, 5, 0, 'CS'),
    ('DATASIZE', 'N', 0, 20, 0, 'CS'),
    ('BINARYDATA', 'I', 0, 0, 0, 'CS'),
    ('PARTNO', 'N', 0, 10, 0, 'CS'),
)
RECIPE_DESCRIPTION = {'identifier': RECIPE_ID, 'declarations': DECLARATIONS,
    'recordlock': '0', 'format_item': 0, 'candidate_stride': 301,
    'observation': 'first_and_later_zero_one_other_candidate_markers_v1',
    'selection': 'CONFIG_ascii_case_only_no_fallback_v1',
    'empty_data': 'unsupported', 'single_candidate': 'admitted',
    'framing': 'not_accepted', 'filename': 'not_read'}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE_DESCRIPTION, ensure_ascii=True,
    sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
MAX_SLOTS = 4096
MARKER_CLASSES = ('zero', 'one', 'other')
MAX_PROJECTION_BYTES = 2048
MAX_CAPTURE_BYTES = 12288
VERDICT = 'config_marker_census_observed'
FRAMING_VALIDATION = 'not_accepted'
FILENAME_VALIDATION = 'not_run'
EXTRA_KEYS = {'config_marker_census', 'framing_validation', 'reader_validation', 'observation_validation',
    'extraction_validation', 'mapping_validation', 'layout_validation',
    'native_byte_equivalence', 'native_compatibility'}
BINDING_KEYS = metadata.BINDING_KEYS | {'policy_source_sha256', 'framing_reader_source_sha256'}
DIAGNOSTICS = {key: set(value) for key, value in comparison.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'].update(('missing_table_data_header', 'missing_table_blob_header',
    'config_table_missing', 'config_table_ambiguous', 'config_profile_mismatch',
    'config_empty_data'))
DIAGNOSTICS['structural_rejection'].update(('table_data_header_role', 'table_blob_header_role',
    'config_record_length'))
DIAGNOSTICS['resource_limit'].update(('config_record_bytes', 'config_slots'))


class ObservationFailure(OracleError):
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code


def fail(category, code):
    raise ObservationFailure(category, code)


def reader_failure(error):
    for kind, category in ((reader.UnsupportedLayout, 'unsupported_layout'),
            (reader.InvalidStructure, 'structural_rejection'), (reader.ResourceLimit, 'resource_limit'),
            (reader.UnsupportedSharing, 'unsupported_sharing_policy')):
        if type(error) is kind and type(error.code) is str and error.code in DIAGNOSTICS[category]:
            return ObservationFailure(category, error.code)
    classified = comparison.reader_failure(error)
    return ObservationFailure(classified.category, classified.code)


def validate_projection(value):
    exact(value, {'schema', 'target', 'recipe_id', 'recipe_sha256',
        'data_logical_bytes', 'blob_logical_bytes', 'candidate_stride', 'candidate_slots',
        'first_marker_class', 'later_zero_count', 'later_one_count', 'later_other_count',
        'framing_validation', 'filename_validation', 'root_identity'})
    require(type(value['schema']) is int and value['schema'] == 1)
    for key, expected in (('target', TARGET), ('recipe_id', RECIPE_ID),
            ('recipe_sha256', RECIPE_SHA256), ('framing_validation', FRAMING_VALIDATION),
            ('filename_validation', FILENAME_VALIDATION), ('root_identity', 'not_observed')):
        require(type(value[key]) is str and value[key] == expected)
    require(type(value['first_marker_class']) is str and value['first_marker_class'] in MARKER_CLASSES)
    require(type(value['candidate_stride']) is int and value['candidate_stride'] == 301
            and integer(value['candidate_slots'], MAX_SLOTS, 1)
            and all(integer(value[key], MAX_SLOTS-1)
                    for key in ('later_zero_count', 'later_one_count', 'later_other_count'))
            and integer(value['data_logical_bytes'], MAX_FILE_BYTES, 1)
            and integer(value['blob_logical_bytes'], MAX_FILE_BYTES))
    require(value['candidate_slots'] == 1 + value['later_zero_count']
            + value['later_one_count'] + value['later_other_count']
            and value['data_logical_bytes'] == 301 * value['candidate_slots'])
    require(len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def read_projection(read_at, file_size, *, limits):
    """Invoke the diagnostic core, not the strict framing-success function."""
    profile = framing.ConfigMarkerCensusProfile(DECLARATIONS, '0', 0)
    require(profile.identifier == RECIPE_ID and profile.recipe_sha256 == RECIPE_SHA256
            and profile.candidate_stride == 301, 'provenance_mismatch')
    result = framing.observe_config_marker_census(read_at, file_size, profile=profile,
        limits=framing.ConfigFramingLimits(max_slots=MAX_SLOTS, max_record_bytes=4096),
        catalog_limits=limits)
    require(type(result) is framing.ConfigMarkerCensusObservation
            and result.capability == 'experimental_config_marker_census'
            and result.native_acceptance == 'pending', 'unexpected_failure')
    # No arbitrary names, bytes, indices, pointers, native metadata or usage graph.
    return validate_projection({'schema': 1, 'target': result.target,
        'recipe_id': result.recipe_id, 'recipe_sha256': result.recipe_sha256,
        'data_logical_bytes': result.data_logical_bytes, 'blob_logical_bytes': result.blob_logical_bytes,
        'candidate_stride': result.candidate_stride, 'candidate_slots': result.candidate_slots,
        'first_marker_class': result.first_marker_class,
        'later_zero_count': result.later_zero_count, 'later_one_count': result.later_one_count,
        'later_other_count': result.later_other_count,
        'framing_validation': result.framing_validation,
        'filename_validation': result.filename_validation, 'root_identity': result.root_identity})


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, config_marker_census=None, framing_validation=FRAMING_VALIDATION,
        reader_validation='not_run', observation_validation='not_run',
        extraction_validation='not_run', mapping_validation='not_run', layout_validation='not_run',
        native_byte_equivalence='not_observed', native_compatibility='not_claimed')
    return report


def bind_capture(evidence, report):
    require(type(report.get('schema')) is int and report['schema'] == SCHEMA and report.get('lane') == LANE)
    exact(evidence, {'marker', 'origin', 'postimage', 'reader'})
    require(type(evidence['marker']) is dict and 'token' in evidence['marker'], 'invalid_marker')
    data = metadata.marker(encode(evidence['marker']), nonce=report['nonce'], token=evidence['marker']['token'])
    origin = evidence['origin']
    exact(origin, {'nonce', 'token', 'clone', 'bytes', 'sha256'})
    exact(evidence['postimage'], {'bytes', 'sha256'})
    require(origin['nonce'] == report['nonce'] and origin['token'] == data['token']
            and origin['clone'] == 'auditor', 'snapshot_changed')
    projection = validate_projection(evidence['reader'])
    capture = {'schema': CAPTURE_SCHEMA, 'status': VERDICT, 'operation': OPERATION,
        'nonce': report['nonce'], 'token': data['token'],
        'source_manifest_sha256': source_binding(report['provenance']),
        'reader_source_sha256': report['provenance']['sources'][READER_SOURCE],
        'policy_source_sha256': report['provenance']['sources'][MODULE_SOURCE],
        'framing_reader_source_sha256': report['provenance']['sources'][FRAMING_READER_SOURCE],
        'actual_version': data['actual_version'],
        'origin': {'snapshot': 'baseline', 'clone': 'auditor', 'bytes': origin['bytes'], 'sha256': origin['sha256']},
        'postimage': {'copy': 'auditor_frozen', 'binding': 'closed_post_audit_clone',
            'bytes': evidence['postimage']['bytes'], 'sha256': evidence['postimage']['sha256'],
            'storage_version': [8, 3, 8, 0], 'page_size': 8192}, 'reader': projection}
    _validate_binding(capture, report, nonce=report['nonce'], provenance=report['provenance'], cleanup=False)
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    return capture


def _validate_binding(capture, report, *, nonce, provenance, final=False, cleanup=True):
    metadata._validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final, cleanup=cleanup)
    require(capture['policy_source_sha256'] == provenance['sources'][MODULE_SOURCE]
            and digest(capture['policy_source_sha256'])
            and capture['framing_reader_source_sha256'] == provenance['sources'][FRAMING_READER_SOURCE]
            and digest(capture['framing_reader_source_sha256']))
    projection = validate_projection(capture['reader'])
    # Both selected files use disjoint physical ownership on this same image.
    require(projection['data_logical_bytes'] + projection['blob_logical_bytes']
            <= capture['postimage']['bytes'])


def discard_capture(report, failure=None, *, final=False):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA: return
    old = report.get('config_marker_census'); report['config_marker_census'] = None
    for key in ('reader_validation', 'observation_validation'):
        previous = report[key]
        report[key] = 'discarded' if previous in (VERDICT, 'discarded') else 'failed' if previous == 'failed' else 'not_run'
    if type(failure) is ObservationFailure:
        old = {'schema': CAPTURE_SCHEMA, 'status': 'failed', 'category': failure.category, 'code': failure.code}
    cleanup = report['cleanup'] if final else {key: report['cleanup'][key]
        for key in ('native_processes_stopped', 'raw_files_removed')}
    if (all(value is True for value in cleanup.values()) and report.get('status') == 'failed'
            and report.get('failure_kind') == FAILURE_KIND and report.get('failed_stage') == 'baseline'
            and type(old) is dict and set(old) == {'schema', 'status', 'category', 'code'}
            and type(old['schema']) is int and old['schema'] == CAPTURE_SCHEMA and old['status'] == 'failed'
            and type(old['category']) is str and old['category'] in DIAGNOSTICS
            and type(old['code']) is str and old['code'] in DIAGNOSTICS[old['category']]):
        report['config_marker_census'] = dict(old)
        report['reader_validation'] = report['observation_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report))
    require(report['framing_validation'] == FRAMING_VALIDATION
            and all(report[key] == 'not_run' for key in ('extraction_validation', 'mapping_validation', 'layout_validation'))
            and report['native_byte_equivalence'] == 'not_observed' and report['native_compatibility'] == 'not_claimed')
    require(all(report[key] in ('not_run', 'failed', 'discarded', VERDICT)
                for key in ('reader_validation', 'observation_validation')))
    require((report['reader_validation'], report['observation_validation']) in (
        ('not_run', 'not_run'), ('failed', 'not_run'), ('failed', 'failed'),
        ('discarded', 'discarded'), (VERDICT, VERDICT)))
    from inputs import CONFIG_MARKER_CENSUS_SOURCE_FILES
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(CONFIG_MARKER_CENSUS_SOURCE_FILES)
            and len(CONFIG_MARKER_CENSUS_SOURCE_FILES) == 23 and MODULE_SOURCE in CONFIG_MARKER_CENSUS_SOURCE_FILES
            and FRAMING_READER_SOURCE in CONFIG_MARKER_CENSUS_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND, 'record_readback_failed', 'params_observation_failed', 'params_extraction_failed',
        'dbnames_identity_failed', 'config_observation_failed', 'config_framing_failed'))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline'); base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['config_marker_census']
    if capture is not None: require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    if report['status'] != 'ok':
        require(all(report[key] != VERDICT for key in ('reader_validation', 'observation_validation')))
        if capture is not None:
            require(report['failure_kind'] == FAILURE_KIND and report['reader_validation'] == report['observation_validation'] == 'failed')
            exact(capture, {'schema', 'status', 'category', 'code'})
            require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'failed'
                    and type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                    and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
            required = report['cleanup'] if final else {key: report['cleanup'][key]
                for key in ('native_processes_stopped', 'raw_files_removed')}
            require(all(value is True for value in required.values()))
        return report
    require(report['reader_validation'] == report['observation_validation'] == VERDICT)
    exact(capture, {'schema', 'status', 'reader'} | BINDING_KEYS)
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == VERDICT)
    _validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final)
    return report
