"""Closed owned PARAMS/DBNames extraction lane, not native byte equivalence.

One reviewed literal profile is rechecked by the actual reader on its own
hardened frozen postimage. Native metadata names never select or decode rows.
Only identifiers, counts and digests leave the reader; no payload is projected.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import types

import comparison
import filedb_catalog as reader
import params_observation as phase_a
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 8
CAPTURE_SCHEMA = 9
LANE = 'owned_params_dbnames_extraction_v1'
FAILURE_KIND = 'params_extraction_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/params_extraction.py'
READER_SOURCE = comparison.READER_SOURCE
EXTRACTOR_SOURCE = 'yadinassi/storage/filedb_named_file.py'
OPERATION = metadata.OPERATION
TARGET = 'PARAMS/DBNames'
PROFILE_ID = 'params_dbnames_8380_8192_v1'
# Independently accepted Phase-A declarations; never derive this from input.
DECLARATIONS = (
    ('FILENAME', 'NVC', 0, 128, 0, 'CI'),
    ('CREATION', 'DT', 0, 0, 0, 'CS'),
    ('MODIFIED', 'DT', 0, 0, 0, 'CS'),
    ('ATTRIBUTES', 'N', 0, 5, 0, 'CS'),
    ('DATASIZE', 'N', 0, 20, 0, 'CS'),
    ('BINARYDATA', 'I', 0, 0, 0, 'CS'),
    ('PARTNO', 'N', 0, 10, 0, 'CS'),
)
PROFILE_DESCRIPTION = {'schema': 1, 'id': PROFILE_ID, 'target': TARGET,
    'framing_policy': 'status_then_declared_no_version_v1',
    'codec_policy': 'nvc128_u32le_bcd_positive_padzero_rawdeflate_v1',
    'declarations': DECLARATIONS, 'recordlock': '0', 'format_item': 0,
    'format_admission': 'exact_integer_zero_unknown_semantics',
    'offsets': [1, 259, 266, 273, 276, 287, 295], 'widths': [258, 7, 7, 3, 11, 8, 6],
    'record_size': 301, 'hidden_version': False, 'reserved_marker': 1, 'active_marker': 0,
    'nonreserved_free_slots': 'unsupported', 'filename': 'u16le_length_utf16le_strict_ascii_target',
    'selected_numeric': 'sign1_high_first_digits_zero_padding', 'part': 0,
    'blob_reference': 'u32le_start_u32le_exact_packed_length', 'compression': 'single_raw_deflate'}
PROFILE_SHA256 = hashlib.sha256(encode(dict(sorted(PROFILE_DESCRIPTION.items())))).hexdigest()
MAX_PACKED_BYTES = 1024 * 1024
MAX_PLAIN_BYTES = 8 * 1024 * 1024
MAX_PROJECTION_BYTES = 1024
MAX_CAPTURE_BYTES = 12288
VERDICT = 'extraction_observed'
EXTRA_KEYS = (phase_a.EXTRA_KEYS - {'params_observation'}) | {'params_extraction'}
BINDING_KEYS = metadata.BINDING_KEYS | {'policy_source_sha256', 'extractor_source_sha256'}
DIAGNOSTICS = {key: set(value) for key, value in phase_a.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'].update(('dbnames_table_missing', 'dbnames_table_ambiguous',
    'dbnames_profile_mismatch', 'dbnames_reserved_slot', 'dbnames_nonreserved_slot',
    'dbnames_filename_encoding', 'dbnames_numeric_sign', 'dbnames_numeric_digit',
    'dbnames_numeric_padding', 'dbnames_part'))
DIAGNOSTICS['structural_rejection'].update(('dbnames_record_length', 'dbnames_filename_length',
    'dbnames_reference', 'dbnames_size', 'dbnames_size_mismatch', 'dbnames_not_found',
    'dbnames_duplicate', 'blob_declared_length', 'deflate_truncated', 'deflate_invalid',
    'deflate_trailing', 'deflate_nonprogress'))
DIAGNOSTICS['resource_limit'].update(('dbnames_record_bytes', 'dbnames_slots',
    'transport_blob_bytes', 'transport_inflate_input_bytes', 'transport_plain_bytes',
    'transport_blob_visits', 'transport_inflate_calls'))


class ObservationFailure(OracleError):
    """Exact finite extraction failure, using the unchanged baseline adapter."""
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code


def reader_failure(error):
    for kind, category in ((reader.UnsupportedLayout, 'unsupported_layout'),
            (reader.InvalidStructure, 'structural_rejection'), (reader.ResourceLimit, 'resource_limit'),
            (reader.UnsupportedSharing, 'unsupported_sharing_policy')):
        if type(error) is kind and type(error.code) is str and error.code in DIAGNOSTICS[category]:
            return ObservationFailure(category, error.code)
    classified = comparison.reader_failure(error)
    return ObservationFailure(classified.category, classified.code)


def load_reader(path):
    """Only the exact catalog sibling and stdlib; no yadinassi package import."""
    name = '_owned_dbnames_storage'
    package = types.ModuleType(name); package.__path__ = []
    sys.modules[name] = package
    sys.modules[name + '.filedb_catalog'] = reader
    spec = importlib.util.spec_from_file_location(name + '.filedb_named_file', path)
    require(spec is not None and spec.loader is not None, 'provenance_mismatch')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_projection(value):
    exact(value, {'schema', 'target', 'profile_id', 'profile_sha256',
        'packed_bytes', 'packed_sha256', 'plain_bytes', 'plain_sha256'})
    require(type(value['schema']) is int and value['schema'] == 1
            and value['target'] == TARGET and value['profile_id'] == PROFILE_ID
            and value['profile_sha256'] == PROFILE_SHA256)
    require(integer(value['packed_bytes'], MAX_PACKED_BYTES, 1)
            and integer(value['plain_bytes'], MAX_PLAIN_BYTES)
            and digest(value['packed_sha256']) and digest(value['plain_sha256']))
    require(len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def read_projection(read_at, file_size, *, limits):
    """A single reader owns catalog, row scan, BLOB and decompression budgets."""
    module = load_reader(Path(reader.__file__).with_name('filedb_named_file.py'))
    profile = module.DBNamesProfile(declarations=DECLARATIONS, recordlock='0', format_item=0)
    require(profile.identifier == PROFILE_ID, 'provenance_mismatch')
    named_limits = module.NamedFileLimits(max_slots=4096, max_record_bytes=4096,
        max_packed_bytes=MAX_PACKED_BYTES, max_plain_bytes=MAX_PLAIN_BYTES,
        max_blob_visits=8192, max_inflate_calls=4096)
    result = module.read_dbnames(read_at, file_size, profile=profile, limits=named_limits, catalog_limits=limits)
    require(type(result) is module.NamedFileBytes and result.target == TARGET
            and result.profile_id == PROFILE_ID and type(result.data) is bytes
            and len(result.data) <= MAX_PLAIN_BYTES
            and result.capability == 'experimental_named_file_bytes'
            and result.native_acceptance == 'pending', 'unexpected_failure')
    # No expected native digest/count exists. These describe only actual bytes.
    return validate_projection({'schema': 1, 'target': TARGET, 'profile_id': PROFILE_ID,
        'profile_sha256': PROFILE_SHA256, 'packed_bytes': result.packed_bytes,
        'packed_sha256': result.packed_sha256, 'plain_bytes': len(result.data),
        'plain_sha256': hashlib.sha256(result.data).hexdigest()})


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, params_extraction=None,
        reader_validation='not_run', extraction_validation='not_run',
        observation_validation='not_run', mapping_validation='not_run', layout_validation='not_run',
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
        'extractor_source_sha256': report['provenance']['sources'][EXTRACTOR_SOURCE],
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
            and capture['extractor_source_sha256'] == provenance['sources'][EXTRACTOR_SOURCE]
            and digest(capture['extractor_source_sha256']))


def discard_capture(report, failure=None, *, final=False):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA: return
    old = report.get('params_extraction'); report['params_extraction'] = None
    for key in ('reader_validation', 'extraction_validation'):
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
        report['params_extraction'] = dict(old)
        report['reader_validation'] = report['extraction_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report))
    require(all(report[key] == 'not_run' for key in ('observation_validation', 'mapping_validation', 'layout_validation'))
            and report['native_byte_equivalence'] == 'not_observed' and report['native_compatibility'] == 'not_claimed')
    require(all(report[key] in ('not_run', 'failed', 'discarded', VERDICT)
                for key in ('reader_validation', 'extraction_validation')))
    from inputs import EXTRACTION_SOURCE_FILES
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(EXTRACTION_SOURCE_FILES)
            and len(EXTRACTION_SOURCE_FILES) == 24 and MODULE_SOURCE in EXTRACTION_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND, 'record_readback_failed', 'params_observation_failed'))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline'); base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['params_extraction']
    if capture is not None: require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    if report['status'] != 'ok':
        require(all(report[key] != VERDICT for key in ('reader_validation', 'extraction_validation')))
        if capture is not None:
            require(report['failure_kind'] == FAILURE_KIND and report['reader_validation'] == report['extraction_validation'] == 'failed')
            exact(capture, {'schema', 'status', 'category', 'code'})
            require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'failed'
                    and type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                    and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
            required = report['cleanup'] if final else {key: report['cleanup'][key]
                for key in ('native_processes_stopped', 'raw_files_removed')}
            require(all(value is True for value in required.values()))
        return report
    require(report['reader_validation'] == report['extraction_validation'] == VERDICT)
    exact(capture, {'schema', 'status', 'reader'} | BINDING_KEYS)
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == VERDICT)
    _validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final)
    validate_projection(capture['reader'])
    return report
