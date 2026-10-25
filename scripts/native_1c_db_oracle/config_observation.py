"""Finite CONFIG declaration observation; no storage-profile or root inference.

No rows, filenames, BLOB payloads, stride hypotheses or decompression results.
Only logical table-data byte zero is classified; it is not a record boundary.
The native marker is validated but none of its metadata names are projected.
"""
from __future__ import annotations

import re

import comparison
import filedb_catalog as reader
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 10
CAPTURE_SCHEMA = 11
LANE = 'owned_config_transport_observation_v1'
FAILURE_KIND = 'config_observation_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/config_observation.py'
READER_SOURCE = comparison.READER_SOURCE
OPERATION = metadata.OPERATION
TARGET = 'CONFIG'
FIELD_NAMES = ('FILENAME', 'CREATION', 'MODIFIED', 'ATTRIBUTES', 'DATASIZE', 'BINARYDATA', 'PARTNO')
MAX_TOKEN = 8
MAX_INTEGER = 65535
MAX_PROJECTION_BYTES = 2048
MAX_CAPTURE_BYTES = 12288
FORMAT_CLASSES = ('integer_zero', 'integer_nonzero', 'string_zero', 'string_other', 'list', 'other')
BYTE_CLASSES = ('zero', 'one', 'other', 'unavailable')
VERDICT = 'config_declarations_captured'
EXTRA_KEYS = {'config_observation', 'reader_validation', 'observation_validation',
    'extraction_validation', 'mapping_validation', 'layout_validation',
    'native_byte_equivalence', 'native_compatibility'}
BINDING_KEYS = metadata.BINDING_KEYS | {'policy_source_sha256'}
DIAGNOSTICS = {key: set(value) for key, value in comparison.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'].update(('declaration_token', 'declaration_integer',
    'missing_table_data_header', 'missing_table_blob_header'))
DIAGNOSTICS['structural_rejection'].update(('invalid_declaration', 'table_data_header_role',
    'table_blob_header_role', 'internal_length'))


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


def _key(value):
    return ''.join(chr(ord(char) - 32) if 'a' <= char <= 'z' else char for char in value)


def _fixed_name(value, expected):
    require(type(value) is str and len(value) == len(expected) and _key(value) == expected, 'invalid_marker')


def _token(value):
    # Absence is observed, never interpreted as a type/lock/case policy.
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_]{0,8}', value) is None:
        fail('unsupported_layout', 'declaration_token')


def format_class(value):
    if type(value) is int: return 'integer_zero' if value == 0 else 'integer_nonzero'
    if type(value) is str: return 'string_zero' if value == '0' else 'string_other'
    return 'list' if type(value) is tuple else 'other'


def validate_projection(value):
    exact(value, {'schema', 'target', 'table', 'framing_validation', 'root_identity'})
    require(value['framing_validation'] == 'not_observed' and value['root_identity'] == 'not_observed')
    require(type(value['schema']) is int and value['schema'] == 1 and value['target'] == TARGET)
    table = value['table']
    exact(table, {'name', 'record_lock_token', 'format_class', 'fields',
        'data_logical_bytes', 'blob_logical_bytes', 'table_data_initial_byte'})
    _fixed_name(table['name'], TARGET); _token(table['record_lock_token'])
    require(type(table['format_class']) is str and table['format_class'] in FORMAT_CLASSES)
    fields = table['fields']
    require(type(fields) is list and len(fields) in (6, 7), 'invalid_marker')
    for field, name in zip(fields, FIELD_NAMES):
        exact(field, {'name', 'type_token', 'nullability', 'length', 'precision', 'case_token'})
        _fixed_name(field['name'], name)
        _token(field['type_token']); _token(field['case_token'])
        if not all(integer(field[key], MAX_INTEGER) for key in ('nullability', 'length', 'precision')):
            fail('unsupported_layout', 'declaration_integer')
    if not all(integer(table[key], MAX_FILE_BYTES) for key in ('data_logical_bytes', 'blob_logical_bytes')):
        fail('structural_rejection', 'internal_length')
    first = table['table_data_initial_byte']
    require(type(first) is str and first in BYTE_CLASSES
            and (first == 'unavailable') == (table['data_logical_bytes'] == 0))
    require(len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def read_projection(read_at, file_size, *, limits):
    """One completed catalog and two identity-bound files share every budget."""
    source = reader.CatalogReader(read_at, file_size, limits=limits)
    catalog = source.read_catalog()
    matches = [table for table in catalog.tables if _key(table.name) == TARGET]
    if not matches: fail('name_mismatch', 'missing_table')
    if len(matches) != 1: fail('name_mismatch', 'duplicate_table')
    selected = matches[0]
    fields = [{'name': field.name, 'type_token': field.type_name, 'nullability': field.null_marker,
        'length': field.declared_length, 'precision': field.precision, 'case_token': field.case_marker}
        for field in selected.fields] if len(selected.fields) in (6, 7) else []
    projection = {'schema': 1, 'target': TARGET, 'framing_validation': 'not_observed',
        'root_identity': 'not_observed', 'table': {'name': selected.name,
        'record_lock_token': selected.recordlock, 'format_class': format_class(selected.format_item),
        'fields': fields, 'data_logical_bytes': 0, 'blob_logical_bytes': 0,
        'table_data_initial_byte': 'unavailable'}}
    # Reject unknown declarations before either selected internal-file access.
    validate_projection(projection)
    data = source._open_table_data(selected)
    blob = source._open_table_blob(selected)
    table = projection['table']
    table.update(data_logical_bytes=data.info.logical_length, blob_logical_bytes=blob.info.logical_length)
    if not all(integer(table[key], MAX_FILE_BYTES) for key in ('data_logical_bytes', 'blob_logical_bytes')):
        fail('structural_rejection', 'internal_length')
    if data.info.logical_length:
        first = data.read_range(0, 1)
        table['table_data_initial_byte'] = {b'\x00': 'zero', b'\x01': 'one'}.get(first, 'other')
    return validate_projection(projection)


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, config_observation=None,
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
            and digest(capture['policy_source_sha256']))


def discard_capture(report, failure=None, *, final=False):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA: return
    old = report.get('config_observation'); report['config_observation'] = None
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
        report['config_observation'] = dict(old)
        report['reader_validation'] = report['observation_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report))
    require(all(report[key] == 'not_run' for key in ('extraction_validation', 'mapping_validation', 'layout_validation'))
            and report['native_byte_equivalence'] == 'not_observed' and report['native_compatibility'] == 'not_claimed')
    require(all(report[key] in ('not_run', 'failed', 'discarded', VERDICT)
                for key in ('reader_validation', 'observation_validation')))
    from inputs import CONFIG_SOURCE_FILES
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(CONFIG_SOURCE_FILES)
            and len(CONFIG_SOURCE_FILES) == 22 and MODULE_SOURCE in CONFIG_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND, 'record_readback_failed', 'params_observation_failed', 'params_extraction_failed',
        'dbnames_identity_failed'))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline'); base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['config_observation']
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
    validate_projection(capture['reader'])
    return report
