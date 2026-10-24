"""Schema-4 exact filtered name comparison, never general native compatibility.

The parser receives no native names. Only its completed immutable catalog is
projected here. The active bound missing-table rejection exports a complete
counts-only census, never names, fields or raw descriptors. Schema-2 name
inventories remain supported only for historical local fixtures.
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
MAX_DIAGNOSTIC_TABLES = 64
MAX_DIAGNOSTIC_CHARACTERS = 2048
NAME_SCOPE = 'own_synthetic_disposable_database'
# Existing reader defaults, not new or enlarged parser limits.
CENSUS_LIMITS = reader.CatalogLimits()
MAX_CENSUS_TABLES = CENSUS_LIMITS.max_tables
MAX_CENSUS_NAME_BYTES = CENSUS_LIMITS.max_string_bytes
MAX_CENSUS_BLOB_BYTES = CENSUS_LIMITS.max_total_blob_bytes
MAX_NAME_CAPTURE_SKELETON_BYTES = 2048
# Worst-case JSON surrogate-pair cost per character, quotes/commas per name,
# and the independently bounded skeleton. Observation only, never allocation.
MAX_HYPOTHETICAL_NAME_CAPTURE_BYTES = (12 * (MAX_CENSUS_BLOB_BYTES + MAX_TABLES * MAX_TEXT)
    + 3 * (MAX_CENSUS_TABLES + MAX_TABLES) + MAX_NAME_CAPTURE_SKELETON_BYTES)
POLICY_FLAGS = ('reader_table_limit', 'name_character_limit', 'native_identifier',
                'reader_identifier', 'capture_byte_limit')
BINDING_KEYS = {'operation', 'nonce', 'token', 'source_manifest_sha256',
    'reader_source_sha256', 'actual_version', 'origin', 'postimage'}
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
DIAGNOSTICS['resource_limit'].update({'projection_limit', 'diagnostic_limit'})
DIAGNOSTICS['unsupported_layout'].update({'diagnostic_identifier'})
DIAGNOSTICS['structural_rejection'].update({'invalid_projection'})
DIAGNOSTICS['io_or_change'].update({'snapshot_changed', 'snapshot_not_quiescent',
    'artifact_missing', 'invalid_input', 'origin_changed', 'postimage_changed'})
DIAGNOSTICS = {category: frozenset(codes) for category, codes in DIAGNOSTICS.items()}


class ComparisonFailure(OracleError):
    def __init__(self, category, code, *, capture=None):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        # Like the existing scoped wrappers, Controller assigns the report-only
        # kind. Keep snapshots.OracleError's foundational enum unchanged.
        super().__init__('logical_mismatch')
        self.category, self.code = category, code
        # Only a sanitized, bound capture may be attached, never a catalog or
        # native marker. It is independently checked again before release.
        self.capture = capture


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


def capture_binding(evidence, *, nonce, provenance, baseline):
    data = evidence['marker']
    lifecycle.marker(encode(data), nonce=nonce, token=data['token'],
                     operation='audit_contract', contract_version=SCHEMA)
    origin = evidence['origin']
    # origin.token was pinned to the fresh launch token before ENTERPRISE. The
    # native result parser also checks that token, not merely its hexadecimal form.
    require(origin['nonce'] == nonce and origin['token'] == data['token']
            and origin['clone'] == 'auditor' and origin['bytes'] == baseline['bytes']
            and origin['sha256'] == baseline['sha256'], 'snapshot_changed')
    return {'operation': 'audit_contract', 'nonce': nonce, 'token': data['token'],
        'source_manifest_sha256': source_binding(provenance),
        'reader_source_sha256': provenance['sources'][READER_SOURCE],
        'actual_version': data['actual_version'],
        'origin': {'snapshot': 'baseline', 'clone': 'auditor', 'bytes': origin['bytes'],
                   'sha256': origin['sha256']},
        'postimage': {'copy': 'auditor_frozen', 'binding': 'closed_post_audit_clone',
                      'bytes': evidence['postimage']['bytes'], 'sha256': evidence['postimage']['sha256'],
                      'storage_version': [8, 3, 8, 0], 'page_size': 8192}}


def bind_capture(evidence, report):
    require(report['snapshots'][0]['id'] == 'baseline', 'snapshot_changed')
    capture = {'schema': 1, 'status': 'matched', **capture_binding(evidence,
        nonce=report['nonce'], provenance=report['provenance'],
        baseline=report['snapshots'][0]['physical']),
        'native': canonical_projection(evidence['marker']['storage_names']),
        'reader': canonical_projection(evidence['reader'])}
    require(capture['native'] == capture['reader'], 'logical_mismatch')
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    return capture


def name_diagnostic(catalog, native):
    """Complete names only, after a real parse and exact missing-table rejection."""
    native_tables = native['tables']
    if not 1 <= len(native_tables) <= MAX_TABLES or len(catalog.tables) > MAX_DIAGNOSTIC_TABLES:
        raise ComparisonFailure('resource_limit', 'diagnostic_limit')
    if not integer(catalog.usage.tables, MAX_DIAGNOSTIC_TABLES) or catalog.usage.tables != len(catalog.tables):
        raise ComparisonFailure('structural_rejection', 'invalid_projection')
    names = [table['name'] for table in native_tables]
    parsed = [table.name for table in catalog.tables]
    units = 0
    for name in names + parsed:
        if type(name) is not str or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name) is None:
            raise ComparisonFailure('unsupported_layout', 'diagnostic_identifier')
        units += len(name)
        if units > MAX_DIAGNOSTIC_CHARACTERS:
            raise ComparisonFailure('resource_limit', 'diagnostic_limit')
    value = {'target': TARGET, 'scope': NAME_SCOPE, 'status': 'complete',
        'native_tables': sorted(names), 'reader_tables': sorted(parsed),
        'native_table_count': len(names), 'reader_table_count': len(parsed),
        'parser_table_count': catalog.usage.tables}
    validate_name_diagnostic(value)
    return value


def validate_name_diagnostic(value):
    exact(value, {'target', 'scope', 'status', 'native_tables', 'reader_tables',
                  'native_table_count', 'reader_table_count', 'parser_table_count'})
    require(value['target'] == TARGET and value['scope'] == NAME_SCOPE and value['status'] == 'complete')
    native = value['native_tables']; parsed = value['reader_tables']
    require(type(native) is list and 1 <= len(native) <= MAX_TABLES
            and type(parsed) is list and len(parsed) <= MAX_DIAGNOSTIC_TABLES, 'artifact_limit')
    require(integer(value['native_table_count'], MAX_TABLES, 1)
            and value['native_table_count'] == len(native)
            and integer(value['reader_table_count'], MAX_DIAGNOSTIC_TABLES)
            and value['reader_table_count'] == len(parsed)
            and integer(value['parser_table_count'], MAX_DIAGNOSTIC_TABLES)
            and value['parser_table_count'] == len(parsed))
    require(all(type(name) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', name) is not None
                for name in native + parsed))
    require(sum(map(len, native + parsed)) <= MAX_DIAGNOSTIC_CHARACTERS, 'artifact_limit')
    require(native == sorted(native) and len(set(native)) == len(native) and parsed == sorted(parsed))
    # Follow the same sorted lookup order as project_catalog: an earlier
    # duplicate selected table would reject before a later missing table.
    # Unselected/later duplicates remain observations, never deduplicated.
    for name in native:
        count = parsed.count(name)
        if count == 0:
            break
        require(count == 1)
    else:
        require(False)
    return value


def census_add(left, right, maximum):
    """Checked arithmetic also rejects bools; never retain partial diagnostics."""
    if not integer(left, maximum) or not integer(right, maximum) or left > maximum - right:
        raise ComparisonFailure('resource_limit', 'diagnostic_limit')
    return left + right


def name_wire_metrics(name, *, native=False, before_scan=None):
    """One bounded scan: strict UTF-8 bytes, exact ensure_ascii JSON bytes, grammar.

    Match protocol.encode without allocating an encoded name. Native marker
    strings are printable BMP; reader strings originate from strict UTF-8.
    Controls/quotes/astral reader names are observations, not new identifiers.
    """
    if type(name) is not str:
        raise ComparisonFailure('structural_rejection', 'invalid_projection')
    limit = MAX_TEXT if native else MAX_CENSUS_NAME_BYTES
    if len(name) > limit:
        raise ComparisonFailure('resource_limit', 'diagnostic_limit')
    if native and not name:
        raise ComparisonFailure('structural_rejection', 'invalid_projection')
    valid = 1 <= len(name) <= MAX_TEXT
    utf8 = 0; wire = 2  # JSON string quotes.
    for index, char in enumerate(name):
        if before_scan is not None and index % 1024 == 0:
            before_scan()
        code = ord(char)
        if 0xd800 <= code <= 0xdfff or (native and (not 32 <= code <= 0xffff or not char.isprintable())):
            raise ComparisonFailure('structural_rejection', 'invalid_projection')
        utf8 += 1 if code < 0x80 else 2 if code < 0x800 else 3 if code <= 0xffff else 4
        if utf8 > limit * (3 if native else 1):
            raise ComparisonFailure('resource_limit', 'diagnostic_limit')
        if char in ('"', '\\', '\b', '\f', '\n', '\r', '\t'):
            wire += 2
        else:
            wire += 1 if 32 <= code < 127 else 6 if code <= 0xffff else 12
        allowed = char == '_' or 'A' <= char <= 'Z' or 'a' <= char <= 'z'
        if not allowed and not (index > 0 and '0' <= char <= '9'):
            valid = False
    if before_scan is not None:
        before_scan()
    return utf8, wire, not valid


def hypothetical_name_capture_base(binding, native_count, reader_count, parser_count):
    """Only fixed-size empty arrays are serialized; item order cannot affect size."""
    skeleton = {'schema': 2, 'status': 'failed', 'category': 'name_mismatch', 'code': 'missing_table',
        **binding, 'name_diagnostic': {'target': TARGET, 'scope': NAME_SCOPE, 'status': 'complete',
            'native_tables': [], 'reader_tables': [], 'native_table_count': native_count,
            'reader_table_count': reader_count, 'parser_table_count': parser_count}}
    size = len(encode(skeleton))
    require(size <= MAX_NAME_CAPTURE_SKELETON_BYTES, 'artifact_limit')
    return size + max(0, native_count - 1) + max(0, reader_count - 1)


def census_policy_flags(value):
    conditions = (value['reader_table_count'] > MAX_DIAGNOSTIC_TABLES,
        value['total_name_characters'] > MAX_DIAGNOSTIC_CHARACTERS,
        value['native_invalid_identifier_count'] > 0, value['reader_invalid_identifier_count'] > 0,
        value['hypothetical_name_capture_bytes'] > MAX_CAPTURE_BYTES)
    return [flag for flag, present in zip(POLICY_FLAGS, conditions) if present]


def name_census(catalog, native, binding, *, before_scan=None):
    """Complete counts after the real parse/missing-table trigger; no name copies.

    Check containers/counters before traversal, and character budgets before each
    string scan. Even malformed synthetic objects cannot request unbounded work.
    """
    tables = getattr(catalog, 'tables', None); usage = getattr(catalog, 'usage', None)
    selected = native.get('tables') if type(native) is dict else None
    if type(tables) is not tuple or type(selected) is not list:
        raise ComparisonFailure('structural_rejection', 'invalid_projection')
    count = len(tables); native_count = len(selected)
    if not 1 <= native_count <= MAX_TABLES or count > MAX_CENSUS_TABLES:
        raise ComparisonFailure('resource_limit', 'diagnostic_limit')
    parser_count = getattr(usage, 'tables', None); blob_bytes = getattr(usage, 'total_blob_bytes', None)
    if (not integer(parser_count, MAX_CENSUS_TABLES) or parser_count != count
            or not integer(blob_bytes, MAX_CENSUS_BLOB_BYTES)):
        raise ComparisonFailure('structural_rejection', 'invalid_projection')
    if before_scan is not None:
        before_scan()
    size = hypothetical_name_capture_base(binding, native_count, count, parser_count)
    value = {'target': TARGET, 'scope': NAME_SCOPE, 'status': 'complete_counts_only',
        'trigger_category': 'name_mismatch', 'trigger_code': 'missing_table',
        'native_table_count': native_count, 'reader_table_count': count, 'parser_table_count': parser_count}
    for side, collection in (('native', selected), ('reader', tables)):
        characters = maximum = invalid = utf8 = 0
        for table in collection:
            name = table.get('name') if side == 'native' and type(table) is dict else (
                getattr(table, 'name', None) if side == 'reader' else None)
            if type(name) is not str:
                raise ComparisonFailure('structural_rejection', 'invalid_projection')
            bound = MAX_TABLES * MAX_TEXT if side == 'native' else blob_bytes
            characters = census_add(characters, len(name), bound)
            name_utf8, name_wire, name_invalid = name_wire_metrics(name, native=side == 'native', before_scan=before_scan)
            utf8 = census_add(utf8, name_utf8, MAX_TABLES * MAX_TEXT * 3 if side == 'native' else blob_bytes)
            maximum = max(maximum, len(name)); invalid += name_invalid
            size = census_add(size, name_wire, MAX_HYPOTHETICAL_NAME_CAPTURE_BYTES)
        value[side + '_name_characters'] = characters
        value[side + '_max_name_characters'] = maximum
        value[side + '_invalid_identifier_count'] = invalid
    value['total_name_characters'] = census_add(value['native_name_characters'],
        value['reader_name_characters'], MAX_CENSUS_BLOB_BYTES + MAX_TABLES * MAX_TEXT)
    value['hypothetical_name_capture_bytes'] = size
    value['policy_flags'] = census_policy_flags(value)
    validate_name_census(value, binding)
    return value


def validate_name_census(value, binding):
    # Syntax checks recompute only derivable constraints/flags. Private name
    # contents, exact escaped size, and the actual missing-table trigger still
    # require the pinned producer flow and archive digest/provenance, not these
    # self-reported counters (just like producer-only token/postimage claims).
    exact(value, {'target', 'scope', 'status', 'trigger_category', 'trigger_code',
        'native_table_count', 'reader_table_count', 'parser_table_count',
        'native_name_characters', 'reader_name_characters', 'total_name_characters',
        'native_max_name_characters', 'reader_max_name_characters',
        'native_invalid_identifier_count', 'reader_invalid_identifier_count',
        'hypothetical_name_capture_bytes', 'policy_flags'})
    require(value['target'] == TARGET and value['scope'] == NAME_SCOPE
            and value['status'] == 'complete_counts_only'
            and value['trigger_category'] == 'name_mismatch' and value['trigger_code'] == 'missing_table')
    native_count = value['native_table_count']; reader_count = value['reader_table_count']
    require(integer(native_count, MAX_TABLES, 1) and integer(reader_count, MAX_CENSUS_TABLES)
            and integer(value['parser_table_count'], MAX_CENSUS_TABLES)
            and value['parser_table_count'] == reader_count)
    for side, count, limit in (('native', native_count, MAX_TEXT),
                               ('reader', reader_count, MAX_CENSUS_NAME_BYTES)):
        characters = value[side + '_name_characters']; maximum = value[side + '_max_name_characters']
        invalid = value[side + '_invalid_identifier_count']
        require(integer(characters, min(count * limit, MAX_CENSUS_BLOB_BYTES))
                and integer(maximum, limit) and integer(invalid, count))
        require(maximum <= characters <= count * maximum)
        valid = count - invalid
        # Valid identifiers occupy 1..min(64, observed maximum) characters;
        # invalid reader names may occupy 0..maximum. At least one name must
        # attain that maximum, which determines the exact lower bound below.
        require(characters <= valid * min(MAX_TEXT, maximum) + invalid * maximum)
        if not count:
            require(characters == maximum == invalid == 0)
        elif side == 'native':
            require(maximum >= 1 and characters >= maximum + count - 1)
        elif maximum == 0:
            require(characters == 0 and invalid == count)
        elif maximum > MAX_TEXT:
            require(invalid > 0 and characters >= maximum + valid)
        else:
            require(characters >= maximum + max(valid - 1, 0))
    native_chars = value['native_name_characters']; reader_chars = value['reader_name_characters']
    require(integer(value['total_name_characters'], MAX_CENSUS_BLOB_BYTES + MAX_TABLES * MAX_TEXT)
            and value['total_name_characters'] == native_chars + reader_chars)
    size = value['hypothetical_name_capture_bytes']
    require(integer(size, MAX_HYPOTHETICAL_NAME_CAPTURE_BYTES))
    base = hypothetical_name_capture_base(binding, native_count, reader_count, reader_count)
    minimum = base + 2 * (native_count + reader_count) + native_chars + reader_chars
    maximum = base + 2 * (native_count + reader_count)
    maximum += native_chars * (6 if value['native_invalid_identifier_count'] else 1)
    maximum += reader_chars * (12 if value['reader_invalid_identifier_count'] else 1)
    require(minimum <= size <= maximum)
    require(type(value['policy_flags']) is list and value['policy_flags'] == census_policy_flags(value))
    return value


def missing_table_failure(catalog, evidence, *, nonce, provenance, baseline, before_scan=None):
    # Validate bounded native collections/strings before capture_binding encodes
    # the already producer-validated marker. Reader names are never encoded.
    validate_projection(evidence['marker']['storage_names'])
    binding = capture_binding(evidence, nonce=nonce, provenance=provenance, baseline=baseline)
    census = name_census(catalog, evidence['marker']['storage_names'], binding, before_scan=before_scan)
    capture = {'schema': 3, 'status': 'failed', 'category': 'name_mismatch', 'code': 'missing_table',
        **binding, 'name_census': census}
    try:
        require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    except OracleError as error:
        if error.kind == 'artifact_limit':
            raise ComparisonFailure('resource_limit', 'diagnostic_limit') from None
        raise
    return ComparisonFailure('name_mismatch', 'missing_table', capture=capture)


def validate_binding(capture, report, *, nonce, provenance, final=False):
    # Token and postimage values are producer-bound before construction. Offline
    # validation checks their format/geometry, not independent authenticity of
    # a replaced valid digest; no duplicate self-assertion supplies such proof.
    require(capture['operation'] == 'audit_contract' and capture['nonce'] == nonce
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


def validate_failure_capture(capture, report, *, nonce, provenance, final=False):
    require(type(capture) is dict and type(capture.get('schema')) is int and capture['schema'] in (2, 3))
    payload = 'name_diagnostic' if capture['schema'] == 2 else 'name_census'
    exact(capture, {'schema', 'status', 'category', 'code', payload} | BINDING_KEYS)
    require(type(capture['schema']) is int and capture['schema'] in (2, 3)
            and capture['status'] == 'failed' and capture['category'] == 'name_mismatch'
            and capture['code'] == 'missing_table' and report['status'] == 'failed'
            and report['failure_kind'] == 'catalog_comparison_failed'
            and report['failed_stage'] == 'baseline' and report['reader_validation'] == 'failed'
            and [item['id'] for item in report['snapshots']] == ['baseline'])
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final)
    if capture['schema'] == 2:
        validate_name_diagnostic(capture['name_diagnostic'])
    else:
        validate_name_census(capture['name_census'], {key: capture[key] for key in BINDING_KEYS})


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
        if failure.capture is not None:
            try:
                validate_failure_capture(failure.capture, report, nonce=report['nonce'],
                                         provenance=report['provenance'])
                require((failure.category, failure.code) == ('name_mismatch', 'missing_table'))
            except OracleError:
                pass  # Failed cleanup or binding never releases diagnostic data.
            else:
                report['storage_contract'] = failure.capture
    elif (report.get('status') == 'failed' and report.get('failure_kind') == 'catalog_comparison_failed'
          and report.get('failed_stage') == 'baseline' and previous == 'failed'
          and type(old) is dict and type(old.get('schema')) is int
          and ((old['schema'] == 1 and set(old) == {'schema', 'status', 'category', 'code'})
               or (old['schema'] == 2 and set(old) == {'schema', 'status', 'category', 'code',
                                                       'name_diagnostic'} | BINDING_KEYS)
               or (old['schema'] == 3 and set(old) == {'schema', 'status', 'category', 'code',
                                                       'name_census'} | BINDING_KEYS))
          and old['status'] == 'failed'
          and type(old['category']) is str and old['category'] in DIAGNOSTICS
          and type(old['code']) is str and old['code'] in DIAGNOSTICS[old['category']]):
        # Host cleanup failure strips the complete bound diagnostic back to the
        # original finite rejection, never retaining names or binding claims.
        report['storage_contract'] = {key: old[key] for key in ('status', 'category', 'code')}
        report['storage_contract']['schema'] = 1


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
        if type(capture) is dict and type(capture.get('schema')) is int and capture['schema'] in (2, 3):
            validate_failure_capture(capture, report, nonce=nonce, provenance=provenance, final=final)
            return report
        exact(capture, {'schema', 'status', 'category', 'code'})
        require(type(capture['schema']) is int and capture['schema'] == 1
                and capture['status'] == 'failed' and report['reader_validation'] == 'failed'
                and report['failed_stage'] == 'baseline' and report['failure_kind'] == 'catalog_comparison_failed')
        require(type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
        return report
    require(report['reader_validation'] == VERDICT)
    exact(capture, {'schema', 'status', 'native', 'reader'} | BINDING_KEYS)
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    require(type(capture['schema']) is int and capture['schema'] == 1 and capture['status'] == 'matched')
    validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final)
    require(capture['native'] == canonical_projection(capture['native'])
            and capture['reader'] == canonical_projection(capture['reader'])
            and capture['native'] == capture['reader'])
    return report
