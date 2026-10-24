"""Schema-4 exact filtered name comparison, never general native compatibility.

The parser receives no native names. Only its completed immutable catalog is
projected here, and no raw descriptor or unrelated table escapes this module.
Historical v2/v3 envelopes are not accepted or upgraded.
"""
from __future__ import annotations

import re

import filedb_catalog as reader
import protocol as lifecycle
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 4
LANE = 'native-file-db-catalog-compare-v4'
TARGET = 'Справочник.NativeOracleItems'
MAX_TABLES = 4
MAX_FIELDS = 32
MAX_TOTAL_FIELDS = 64
MAX_TEXT = 64
MAX_TEXT_UNITS = 512
MAX_PROJECTION_BYTES = 4096
MAX_CAPTURE_BYTES = 12288
VERDICT = 'filtered_table_field_names_match'
READER_SOURCE = 'yadinassi/storage/filedb_catalog.py'
EXTRA_KEYS = {'storage_contract', 'reader_validation', 'native_compatibility'}

# Exact exception classes and exact finite codes, not isinstance or exception
# strings. Changes to the standalone reader must update this reviewed inventory.
READER_ERRORS = {
    reader.UnsupportedLayout: ('unsupported_layout', frozenset({
        'free_object_header', 'fat_level', 'backslash_quote_escape',
        'descriptor_token', 'descriptor_section', 'descriptor_shape',
        'recordlock_shape', 'files_shape', 'field_shape', 'field_attributes',
        'storage_version', 'page_size'})),
    reader.UnsupportedSharing: ('unsupported_sharing_policy', frozenset({
        'physical_page_role_overlap', 'logical_blob_chain_overlap', 'duplicate_description_id'})),
    reader.InvalidStructure: ('structural_rejection', frozenset({
        'physical_read_range', 'inexact_read', 'physical_page_reference',
        'object_signature', 'internal_file_addressing_capacity', 'logical_read_range',
        'unaligned_blob_store', 'blob_block_reference', 'blob_chain_cycle',
        'blob_payload_length', 'blob_next_reference', 'blob_start_reference',
        'descriptor_unexpected_end', 'descriptor_unclosed_list', 'descriptor_delimiter',
        'descriptor_utf8', 'descriptor_unclosed_string', 'descriptor_expected_value',
        'file_signature', 'file_geometry', 'missing_root_page', 'catalog_header_length',
        'locale_terminator', 'locale_utf8', 'negative_table_count', 'catalog_table_array',
        'description_blob_reference'})),
    reader.ResourceLimit: ('resource_limit', frozenset({
        'page_reads', 'read_bytes', 'bytes_processed', 'blob_visits', 'total_blob_bytes',
        'tables', 'fields', 'tokens', 'output_bytes', 'mapping_pages', 'blob_chain_bytes',
        'tree_depth', 'string_bytes', 'integer_digits'})),
    reader.SourceIOError: ('io_or_change', frozenset({'read_failed', 'read_result_type', 'file_io_failed'})),
    reader.ChangedDuringRead: ('io_or_change', frozenset({'source_changed'})),
    reader.NotRegularFile: ('io_or_change', frozenset({'not_regular_file'})),
}
DIAGNOSTICS = {category: set() for category, _ in READER_ERRORS.values()}
for _category, _codes in READER_ERRORS.values():
    DIAGNOSTICS[_category].update(_codes)
DIAGNOSTICS['name_mismatch'] = {'missing_table', 'duplicate_table', 'duplicate_field', 'field_names_differ'}
DIAGNOSTICS['resource_limit'].update({'projection_limit'})
DIAGNOSTICS['structural_rejection'].update({'invalid_projection'})
DIAGNOSTICS['io_or_change'].update({'snapshot_changed', 'snapshot_not_quiescent',
    'artifact_missing', 'invalid_input', 'origin_changed', 'postimage_changed'})
DIAGNOSTICS = {category: frozenset(codes) for category, codes in DIAGNOSTICS.items()}


class ComparisonFailure(OracleError):
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        # Like the existing scoped wrappers, Controller assigns the report-only
        # kind. Keep snapshots.OracleError's foundational enum unchanged.
        super().__init__('logical_mismatch')
        self.category, self.code = category, code


def reader_failure(error):
    pair = READER_ERRORS.get(type(error))
    require(pair is not None and type(error.code) is str and error.code in pair[1],
            'unexpected_failure')
    return ComparisonFailure(pair[0], error.code)


def text_units(value):
    require(type(value) is str and len(value) > 0, 'invalid_marker')
    require(len(value) <= MAX_TEXT, 'artifact_limit')
    require(all(32 <= ord(char) <= 0xffff and char.isprintable()
                for char in value), 'invalid_marker')
    return len(value)


def validate_projection(value):
    exact(value, {'schema', 'target', 'tables'})
    require(type(value['schema']) is int and value['schema'] == 1
            and value['target'] == TARGET, 'invalid_marker')
    tables = value['tables']
    require(type(tables) is list and 1 <= len(tables) <= MAX_TABLES, 'artifact_limit')
    names = set(); total = units = 0
    for table in tables:
        exact(table, {'name', 'fields'})
        units += text_units(table['name'])
        require(table['name'] not in names, 'invalid_marker'); names.add(table['name'])
        fields = table['fields']
        require(type(fields) is list and 1 <= len(fields) <= MAX_FIELDS, 'artifact_limit')
        total += len(fields)
        require(total <= MAX_TOTAL_FIELDS, 'artifact_limit')
        field_names = set()
        for name in fields:
            units += text_units(name)
            require(name not in field_names, 'invalid_marker'); field_names.add(name)
            require(units <= MAX_TEXT_UNITS, 'artifact_limit')
    require(len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def canonical_projection(value):
    validate_projection(value)
    return {'schema': 1, 'target': TARGET, 'tables': sorted(
        ({'name': table['name'], 'fields': sorted(table['fields'])} for table in value['tables']),
        key=lambda table: table['name'])}


def project_catalog(catalog, native):
    """Called only after complete parse. Native values select, never guide parsing."""
    native = canonical_projection(native)
    selected = []; total_fields = 0
    for expected in native['tables']:
        # Count matches before dict/set construction; never silently deduplicate.
        matches = [table for table in catalog.tables if table.name == expected['name']]
        if not matches: raise ComparisonFailure('name_mismatch', 'missing_table')
        if len(matches) != 1: raise ComparisonFailure('name_mismatch', 'duplicate_table')
        table = matches[0]
        if not table.fields: raise ComparisonFailure('name_mismatch', 'field_names_differ')
        total_fields += len(table.fields)
        if len(table.fields) > MAX_FIELDS or total_fields > MAX_TOTAL_FIELDS:
            raise ComparisonFailure('resource_limit', 'projection_limit')
        fields = []
        for field in table.fields:
            if field.name in fields: raise ComparisonFailure('name_mismatch', 'duplicate_field')
            fields.append(field.name)
        selected.append({'name': table.name, 'fields': fields})
    try:
        actual = canonical_projection({'schema': 1, 'target': TARGET, 'tables': selected})
    except OracleError as error:
        raise ComparisonFailure('resource_limit' if error.kind == 'artifact_limit' else 'structural_rejection',
                                'projection_limit' if error.kind == 'artifact_limit' else 'invalid_projection') from None
    if actual != native: raise ComparisonFailure('name_mismatch', 'field_names_differ')
    return native, actual


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, storage_contract=None,
                  reader_validation='not_run', native_compatibility='not_claimed')
    return report


def bind_capture(evidence, report):
    data = evidence['marker']
    lifecycle.marker(encode(data), nonce=report['nonce'], token=data['token'],
                     operation='audit_contract', contract_version=SCHEMA)
    baseline = report['snapshots'][0]
    origin = evidence['origin']
    require(baseline['id'] == 'baseline' and origin['nonce'] == report['nonce']
            and origin['token'] == data['token'] and origin['clone'] == 'auditor'
            and origin['bytes'] == baseline['physical']['bytes']
            and origin['sha256'] == baseline['physical']['sha256'], 'snapshot_changed')
    capture = {'schema': 1, 'status': 'matched', 'operation': 'audit_contract',
        'nonce': report['nonce'], 'token': data['token'],
        'source_manifest_sha256': source_binding(report['provenance']),
        'reader_source_sha256': report['provenance']['sources'][READER_SOURCE],
        'actual_version': data['actual_version'],
        'origin': {'snapshot': 'baseline', 'clone': 'auditor', 'bytes': origin['bytes'],
                   'sha256': origin['sha256']},
        'postimage': {'copy': 'auditor_frozen', 'binding': 'closed_post_audit_clone',
                      'bytes': evidence['postimage']['bytes'], 'sha256': evidence['postimage']['sha256'],
                      'storage_version': [8, 3, 8, 0], 'page_size': 8192},
        'native': canonical_projection(data['storage_names']),
        'reader': canonical_projection(evidence['reader'])}
    require(capture['native'] == capture['reader'], 'logical_mismatch')
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    return capture


def discard_capture(report, failure=None):
    if report.get('schema') != SCHEMA: return
    previous = report.get('reader_validation', 'not_run')
    old = report.get('storage_contract')
    report['storage_contract'] = None
    report['reader_validation'] = ('discarded' if previous in (VERDICT, 'discarded')
                                   else 'failed' if previous == 'failed' else 'not_run')
    if type(failure) is ComparisonFailure:
        report['storage_contract'] = {'schema': 1, 'status': 'failed',
            'category': failure.category, 'code': failure.code}
        report['reader_validation'] = 'failed'
    elif (report.get('status') == 'failed' and report.get('failure_kind') == 'catalog_comparison_failed'
          and report.get('failed_stage') == 'baseline' and previous == 'failed'
          and type(old) is dict and set(old) == {'schema', 'status', 'category', 'code'}
          and type(old['schema']) is int and old['schema'] == 1 and old['status'] == 'failed'
          and type(old['category']) is str and old['category'] in DIAGNOSTICS
          and type(old['code']) is str and old['code'] in DIAGNOSTICS[old['category']]):
        # A host cleanup failure can preserve a validated primary finite failure,
        # never successful projections or any text from the reader exception.
        report['storage_contract'] = old


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int
            and report['schema'] == SCHEMA and report.get('lane') == LANE)
    require(EXTRA_KEYS <= set(report) and report['native_compatibility'] == 'not_claimed'
            and report['reader_validation'] in ('not_run', 'failed', 'discarded', VERDICT))
    from inputs import SOURCE_FILES
    require(type(provenance.get('sources')) is dict
            and set(provenance['sources']) == set(SOURCE_FILES), 'provenance_mismatch')
    require(provenance.get('image') == lifecycle.IMAGE and provenance.get('platform') == 'linux/amd64'
            and provenance.get('locale') == 'ru_RU.UTF-8' and provenance.get('timezone') == 'Etc/UTC',
            'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['storage_contract']
    if capture is not None:
        require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    if report['failure_kind'] == 'catalog_comparison_failed':
        require(report['status'] == 'failed' and report['failed_stage'] == 'baseline'
                and [item['id'] for item in report['snapshots']] == ['baseline']
                and report['reader_validation'] == 'failed' and capture is not None)
    if report['status'] != 'ok':
        require(report['reader_validation'] != VERDICT)
        if capture is None:
            require(report['reader_validation'] in ('not_run', 'failed', 'discarded'))
            return report
        exact(capture, {'schema', 'status', 'category', 'code'})
        require(type(capture['schema']) is int and capture['schema'] == 1
                and capture['status'] == 'failed' and report['reader_validation'] == 'failed'
                and report['failed_stage'] == 'baseline' and report['failure_kind'] == 'catalog_comparison_failed')
        require(type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
        return report
    require(report['reader_validation'] == VERDICT)
    exact(capture, {'schema', 'status', 'operation', 'nonce', 'token', 'source_manifest_sha256',
        'reader_source_sha256', 'actual_version', 'origin', 'postimage', 'native', 'reader'})
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    require(type(capture['schema']) is int and capture['schema'] == 1 and capture['status'] == 'matched'
            and capture['operation'] == 'audit_contract' and capture['nonce'] == nonce
            and type(capture['token']) is str and re.fullmatch('[0-9a-f]{32}', capture['token']) is not None)
    require(capture['source_manifest_sha256'] == source_binding(provenance)
            and digest(capture['source_manifest_sha256'])
            and capture['reader_source_sha256'] == provenance['sources'][READER_SOURCE]
            and digest(capture['reader_source_sha256'])
            and capture['actual_version'] == report['provenance']['actual_version'] == lifecycle.VERSION)
    origin = capture['origin']; postimage = capture['postimage']
    exact(origin, {'snapshot', 'clone', 'bytes', 'sha256'})
    exact(postimage, {'copy', 'binding', 'bytes', 'sha256', 'storage_version', 'page_size'})
    baseline = report['snapshots'][0]['physical']
    require(origin['snapshot'] == 'baseline' and origin['clone'] == 'auditor'
            and integer(origin['bytes'], minimum=1) and origin['bytes'] == baseline['bytes']
            and digest(origin['sha256']) and origin['sha256'] == baseline['sha256'])
    require(postimage['copy'] == 'auditor_frozen' and postimage['binding'] == 'closed_post_audit_clone'
            and integer(postimage['bytes'], MAX_FILE_BYTES, 3 * 8192)
            and postimage['bytes'] % 8192 == 0 and digest(postimage['sha256'])
            and type(postimage['storage_version']) is list and len(postimage['storage_version']) == 4
            and all(type(part) is int for part in postimage['storage_version'])
            and postimage['storage_version'] == [8, 3, 8, 0]
            and type(postimage['page_size']) is int and postimage['page_size'] == 8192)
    required = report['cleanup'] if final else {key: report['cleanup'][key]
        for key in ('native_processes_stopped', 'raw_files_removed')}
    require(all(required.values()))
    require(capture['native'] == canonical_projection(capture['native'])
            and capture['reader'] == canonical_projection(capture['reader'])
            and capture['native'] == capture['reader'])
    return report
