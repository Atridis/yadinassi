"""Closed finite CONFIG framing/filename observation, never native compatibility.

One explicit source-derived hypothesis is checked on the existing frozen owned
baseline postimage. Native marker metadata names never affect table selection,
framing or filename validation. No source filename or BLOB content is projected.
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

SCHEMA = 11
CAPTURE_SCHEMA = 12
LANE = 'owned_config_framing_observation_v1'
FAILURE_KIND = 'config_framing_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/config_framing.py'
FRAMING_READER_SOURCE = 'scripts/native_1c_db_oracle/config_framing_reader.py'
READER_SOURCE = comparison.READER_SOURCE
OPERATION = metadata.OPERATION
TARGET = 'CONFIG'
PROFILE_ID = 'config_framing_8380_8192_v1'
# Independently literal profile, not a descriptor echo or imported core constant.
DECLARATIONS = (
    ('FILENAME', 'NVC', 0, 128, 0, 'CI'),
    ('CREATION', 'DT', 0, 0, 0, 'CS'),
    ('MODIFIED', 'DT', 0, 0, 0, 'CS'),
    ('ATTRIBUTES', 'N', 0, 5, 0, 'CS'),
    ('DATASIZE', 'N', 0, 20, 0, 'CS'),
    ('BINARYDATA', 'I', 0, 0, 0, 'CS'),
    ('PARTNO', 'N', 0, 10, 0, 'CS'),
)
PROFILE_DESCRIPTION = {'identifier': PROFILE_ID, 'declarations': DECLARATIONS,
    'recordlock': '0', 'format_item': 0, 'record_size': 301,
    'placements': ((1,258),(259,7),(266,7),(273,3),(276,11),(287,8),(295,6)),
    'framing': 'reserved_one_remaining_zero_no_hidden_version_v1',
    'filename': 'u16le_units_at_most_128_strict_utf16le_v1',
    'selection': 'CONFIG_ascii_case_only_no_fallback_v1',
    'empty_data': 'unsupported', 'reserved_only': 'admitted'}
PROFILE_SHA256 = hashlib.sha256(json.dumps(PROFILE_DESCRIPTION, ensure_ascii=True,
    sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
MAX_SLOTS = 4096
MAX_FILENAME_UNITS = 128
MAX_PROJECTION_BYTES = 2048
MAX_CAPTURE_BYTES = 12288
VERDICT = 'config_framing_observed'
FRAMING_VALIDATION = 'source_hypothesis_satisfied'
FILENAME_VALIDATION = 'bounded_utf16le_validated'
EXTRA_KEYS = {'config_framing', 'reader_validation', 'observation_validation',
    'extraction_validation', 'mapping_validation', 'layout_validation',
    'native_byte_equivalence', 'native_compatibility'}
BINDING_KEYS = metadata.BINDING_KEYS | {'policy_source_sha256', 'framing_reader_source_sha256'}
DIAGNOSTICS = {key: set(value) for key, value in comparison.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'].update(('missing_table_data_header', 'missing_table_blob_header',
    'config_table_missing', 'config_table_ambiguous', 'config_profile_mismatch',
    'config_empty_data', 'config_reserved_slot', 'config_nonreserved_slot',
    'config_filename_encoding'))
DIAGNOSTICS['structural_rejection'].update(('table_data_header_role', 'table_blob_header_role',
    'config_record_length', 'config_filename_length'))
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
    exact(value, {'schema', 'target', 'profile_id', 'profile_sha256',
        'data_logical_bytes', 'blob_logical_bytes', 'slots', 'active_slots',
        'empty_filenames', 'nonempty_filenames', 'max_filename_units',
        'framing_validation', 'filename_validation', 'root_identity'})
    require(type(value['schema']) is int and value['schema'] == 1)
    for key, expected in (('target', TARGET), ('profile_id', PROFILE_ID),
            ('profile_sha256', PROFILE_SHA256), ('framing_validation', FRAMING_VALIDATION),
            ('filename_validation', FILENAME_VALIDATION), ('root_identity', 'not_observed')):
        require(type(value[key]) is str and value[key] == expected)
    require(integer(value['slots'], MAX_SLOTS, 1)
            and all(integer(value[key], MAX_SLOTS-1)
                    for key in ('active_slots', 'empty_filenames', 'nonempty_filenames'))
            and integer(value['max_filename_units'], MAX_FILENAME_UNITS)
            and integer(value['data_logical_bytes'], MAX_FILE_BYTES, 1)
            and integer(value['blob_logical_bytes'], MAX_FILE_BYTES))
    require(value['slots'] == value['active_slots'] + 1
            and value['active_slots'] == value['empty_filenames'] + value['nonempty_filenames']
            and value['data_logical_bytes'] == 301 * value['slots']
            and (value['max_filename_units'] == 0) == (value['nonempty_filenames'] == 0))
    require(len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def read_projection(read_at, file_size, *, limits):
    """Invoke the actual core with independent literals and one catalog budget."""
    profile = framing.ConfigFramingProfile(DECLARATIONS, '0', 0)
    require(profile.identifier == PROFILE_ID and profile.recipe_sha256 == PROFILE_SHA256
            and profile.record_size == 301
            and profile.placements == PROFILE_DESCRIPTION['placements'], 'provenance_mismatch')
    result = framing.observe_config_framing(read_at, file_size, profile=profile,
        limits=framing.ConfigFramingLimits(max_slots=MAX_SLOTS, max_record_bytes=4096),
        catalog_limits=limits)
    require(type(result) is framing.ConfigFramingObservation
            and result.capability == 'experimental_config_framing_observation'
            and result.native_acceptance == 'pending', 'unexpected_failure')
    # No arbitrary source names, bytes, pointers, native metadata or usage graph.
    return validate_projection({'schema': 1, 'target': result.target,
        'profile_id': result.profile_id, 'profile_sha256': result.profile_sha256,
        'data_logical_bytes': result.data_logical_bytes, 'blob_logical_bytes': result.blob_logical_bytes,
        'slots': result.slots, 'active_slots': result.active_slots,
        'empty_filenames': result.empty_filenames, 'nonempty_filenames': result.nonempty_filenames,
        'max_filename_units': result.max_filename_units,
        'framing_validation': result.framing_validation,
        'filename_validation': result.filename_validation, 'root_identity': result.root_identity})


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, config_framing=None,
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
    old = report.get('config_framing'); report['config_framing'] = None
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
        report['config_framing'] = dict(old)
        report['reader_validation'] = report['observation_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report))
    require(all(report[key] == 'not_run' for key in ('extraction_validation', 'mapping_validation', 'layout_validation'))
            and report['native_byte_equivalence'] == 'not_observed' and report['native_compatibility'] == 'not_claimed')
    require(all(report[key] in ('not_run', 'failed', 'discarded', VERDICT)
                for key in ('reader_validation', 'observation_validation')))
    require((report['reader_validation'], report['observation_validation']) in (
        ('not_run', 'not_run'), ('failed', 'not_run'), ('failed', 'failed'),
        ('discarded', 'discarded'), (VERDICT, VERDICT)))
    from inputs import CONFIG_FRAMING_SOURCE_FILES
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(CONFIG_FRAMING_SOURCE_FILES)
            and len(CONFIG_FRAMING_SOURCE_FILES) == 23 and MODULE_SOURCE in CONFIG_FRAMING_SOURCE_FILES
            and FRAMING_READER_SOURCE in CONFIG_FRAMING_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND, 'record_readback_failed', 'params_observation_failed', 'params_extraction_failed',
        'dbnames_identity_failed', 'config_observation_failed'))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline'); base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['config_framing']
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
