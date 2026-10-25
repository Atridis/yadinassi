"""Closed three-role DBNames identity hypothesis, not native byte equivalence.

The private reader completes one catalog and parses the extracted bytes before
it receives any expected identity or native name. XML identities were verified
after apply and at the existing baseline redump; the reviewed subsequent audit
is read-only. This does not claim a post-audit XML redump or CONFIGSAVE equality.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import re

import comparison
import filedb_catalog as reader
import filedb_dbnames as parser
import params_extraction as extraction
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import OracleError

SCHEMA = 9
CAPTURE_SCHEMA = 10
LANE = 'owned_dbnames_identity_validation_v1'
FAILURE_KIND = 'dbnames_identity_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/dbnames_identity.py'
PARSER_SOURCE = 'yadinassi/storage/filedb_dbnames.py'
READER_SOURCE = comparison.READER_SOURCE
EXTRACTOR_SOURCE = extraction.EXTRACTOR_SOURCE
OPERATION = metadata.OPERATION
TARGET = metadata.TARGET
PROFILE_ID = 'dbnames_utf8bom_counted_triples_v1'
PROFILE_DESCRIPTION = {'schema': 1, 'id': PROFILE_ID,
    'encoding': 'required_utf8_bom_strict', 'grammar': '{H,{N,{UUID,"Kind",ID},...}}',
    'whitespace': 'ascii_space_tab_cr_lf', 'eof': 'whitespace_only',
    'header_semantics': 'opaque', 'header_max': 2147483647, 'id_max': 2147483647,
    'count_max': 4096, 'integer_spelling': 'canonical_unsigned_decimal',
    'uuid': 'bare_ascii_8_4_4_4_12_case_preserved_lowercase_identity',
    'kind': 'quoted_ascii_[A-Za-z][A-Za-z0-9_]{0,31}',
    'root_arity': 2, 'entry_arity': 3, 'preserve_all_entries': True,
    'max_input_bytes': 8388608, 'max_entries': 4096, 'max_tokens': 65536,
    'max_depth': 4, 'max_scalar_bytes': 128, 'max_integer_digits': 10,
    'max_output_bytes': 16777216}
PROFILE_SHA256 = hashlib.sha256(encode(dict(sorted(PROFILE_DESCRIPTION.items())))).hexdigest()
ROLES = ('catalog', 'payload', 'amount')
ROLE_NAMES = ('NativeOracleItems', 'Payload', 'Amount')
ROLE_KINDS = ('Reference', 'Fld', 'Fld')
ZERO_UUID = '00000000-0000-0000-0000-000000000000'
IDENTITY_BASIS = 'verified_apply_and_baseline_redumps_then_read_only_audit'
MAX_ROWS_BYTES = 4096
MAX_OTHER_BYTES = 2048
MAX_PROJECTION_BYTES = 6144
MAX_CAPTURE_BYTES = 12288
MAX_MANIFEST_BYTES = 1024
VERDICT = 'owned_identity_names_matched'
EXTRA_KEYS = (extraction.EXTRA_KEYS - {'params_extraction'}) | {'dbnames_identity', 'record_validation'}
BINDING_KEYS = extraction.BINDING_KEYS | {'parser_source_sha256', 'image', 'platform',
    'locale', 'timezone', 'metadata_version', 'identity_basis', 'xml_manifest', 'xml_manifest_sha256'}
DIAGNOSTICS = {key: set(value) for key, value in extraction.DIAGNOSTICS.items()}
DIAGNOSTICS['identity_mismatch'] = {
    'xml_manifest_invalid', 'xml_identity_invalid', 'xml_identity_ambiguous',
    'xml_role_mismatch', 'xml_source_mismatch', 'xml_manifest_changed',
    'target_identity_missing', 'target_identity_ambiguous', 'target_kind_mismatch',
    'target_id_not_positive', 'duplicate_physical_target', 'native_role_mismatch',
    'native_role_missing', 'native_role_ambiguous', 'native_name_mismatch',
    'physical_table_missing', 'physical_table_ambiguous', 'physical_field_missing',
    'physical_field_ambiguous'}
# The pure parser has its own exception hierarchy. Only its exact classes and
# this closed literal inventory may be turned into public finite diagnostics.
PARSER_ERRORS = {
    'UnsupportedDBNamesProfile': ('unsupported_layout', {'dbnames_profile'}),
    'InvalidDBNames': ('structural_rejection', {
        'dbnames_input_type', 'dbnames_profile_type', 'dbnames_limits_type',
        'dbnames_limit', 'dbnames_utf8_bom', 'dbnames_utf8', 'dbnames_grammar',
        'dbnames_integer', 'dbnames_integer_range', 'dbnames_uuid', 'dbnames_kind',
        'dbnames_count_mismatch', 'dbnames_trailing'}),
    'DBNamesParseResourceLimit': ('resource_limit', {
        'dbnames_input_bytes', 'dbnames_entries', 'dbnames_tokens', 'dbnames_depth',
        'dbnames_scalar_bytes', 'dbnames_integer_digits', 'dbnames_output_bytes'})}
for _category, _codes in PARSER_ERRORS.values():
    DIAGNOSTICS[_category].update(_codes)


class ObservationFailure(OracleError):
    """A finite code only; raw bytes, names and UUIDs never enter failures."""
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code


def _fail(code):
    raise ObservationFailure('identity_mismatch', code)


def reader_failure(error):
    for name, (category, codes) in PARSER_ERRORS.items():
        if type(error) is getattr(parser, name) and type(error.code) is str and error.code in codes:
            return ObservationFailure(category, error.code)
    classified = extraction.reader_failure(error)
    return ObservationFailure(classified.category, classified.code)


def _uuid(value, *, canonical=False, nonzero=False):
    if (type(value) is not str or re.fullmatch(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', value) is None
            or (canonical and value != value.lower()) or (nonzero and value.lower() == ZERO_UUID)):
        _fail('xml_identity_invalid')
    return value.lower()


def validate_manifest(value, *, nonce):
    exact(value, {'schema', 'nonce', 'metadata_version', 'expected_sources_sha256', 'catalog_sha256', 'roles'})
    require(type(value['schema']) is int and value['schema'] == 1
            and type(value['metadata_version']) is int and value['metadata_version'] == 1
            and type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) is not None
            and value['nonce'] == nonce and digest(value['expected_sources_sha256'])
            and digest(value['catalog_sha256']))
    roles = value['roles']
    require(type(roles) is list and len(roles) == 3)
    seen = set()
    for role, item in zip(ROLES, roles):
        exact(item, {'role', 'uuid'})
        require(item['role'] == role)
        identity = _uuid(item['uuid'], canonical=True, nonzero=True)
        if identity in seen:
            _fail('xml_identity_ambiguous')
        seen.add(identity)
    require(len(encode(value)) <= MAX_MANIFEST_BYTES, 'artifact_limit')
    return value


def _xml_identities(root):
    """Exact qualified direct-child paths; never ordinal or generated-type UUIDs."""
    from inject_metadata import NS, FORMAT
    ns = '{' + NS + '}'
    def one(node, name):
        matches = [item for item in node if item.tag == ns + name]
        if len(matches) != 1:
            _fail('xml_role_mismatch')
        return matches[0]
    def name(node):
        leaf = one(one(node, 'Properties'), 'Name')
        if leaf.attrib or len(leaf) or type(leaf.text) is not str:
            _fail('xml_role_mismatch')
        return leaf.text
    if root.tag != ns + 'MetaDataObject' or root.attrib != {'version': FORMAT} or len(root) != 1:
        _fail('xml_role_mismatch')
    catalog = one(root, 'Catalog')
    if set(catalog.attrib) != {'uuid'} or name(catalog) != ROLE_NAMES[0]:
        _fail('xml_role_mismatch')
    children = one(catalog, 'ChildObjects')
    if children.attrib or len(children) != 2:
        _fail('xml_role_mismatch')
    identities = {'catalog': _uuid(catalog.attrib['uuid'], nonzero=True)}
    for attribute in children:
        if attribute.tag != ns + 'Attribute' or set(attribute.attrib) != {'uuid'}:
            _fail('xml_role_mismatch')
        logical = name(attribute)
        if logical not in ROLE_NAMES[1:]:
            _fail('xml_role_mismatch')
        role = ROLES[ROLE_NAMES.index(logical)]
        if role in identities:
            _fail('xml_identity_ambiguous')
        identities[role] = _uuid(attribute.attrib['uuid'], nonzero=True)
    if len(set(identities.values())) != 3:
        _fail('xml_identity_ambiguous')
    return [{'role': role, 'uuid': identities[role]} for role in ROLES]


def build_identity_manifest(expected, actual, *, nonce, version):
    """Called ONLY after the existing successful verify_redump(expected, actual).

    No native call or second verification lifecycle is introduced. Paths are
    already verified bounded trees; their inventory is rechecked before reads.
    The returned digest uses namespace-sensitive canonical Catalog XML, not raw
    attribute order. Its expected-source digest binds the complete v1 source.
    """
    from inject_metadata import _hashes, _inventory, _canonical, read_xml, DraftError
    if type(version) is not int or version != 1:
        _fail('xml_manifest_invalid')
    try:
        before = _hashes(expected)
        _inventory(actual)
        _, actual_xml = read_xml(actual / 'Catalogs/NativeOracleItems.xml')
        _, expected_xml = read_xml(expected / 'Catalogs/NativeOracleItems.xml')
        roles = _xml_identities(actual_xml)
        expected_roles = _xml_identities(expected_xml)
        canonical = _canonical(actual_xml)
        if roles != expected_roles or canonical != _canonical(expected_xml):
            _fail('xml_source_mismatch')
        if before != _hashes(expected):
            _fail('xml_source_mismatch')
        manifest = {'schema': 1, 'nonce': nonce, 'metadata_version': 1,
            'expected_sources_sha256': hashlib.sha256(encode(dict(sorted(before.items())))).hexdigest(),
            'catalog_sha256': hashlib.sha256(encode(canonical)).hexdigest(), 'roles': roles}
        return validate_manifest(manifest, nonce=nonce)
    except ObservationFailure:
        raise
    except (DraftError, ValueError, OSError):
        _fail('xml_manifest_invalid')


@dataclass(frozen=True)
class _ReaderEvidence:
    """Private immutable products; no payload or unowned identity is published."""
    index: object
    catalog: object
    transport: tuple
    budget: object


def read_projection(read_at, file_size, *, limits):
    """Complete one catalog, extract once and parse before receiving expectations."""
    module = extraction.load_reader(Path(reader.__file__).with_name('filedb_named_file.py'))
    profile = module.DBNamesProfile(extraction.DECLARATIONS, '0', 0)
    named_limits = module.NamedFileLimits(max_slots=4096, max_record_bytes=4096,
        max_packed_bytes=extraction.MAX_PACKED_BYTES, max_plain_bytes=extraction.MAX_PLAIN_BYTES,
        max_blob_visits=8192, max_inflate_calls=4096)
    owner = reader.CatalogReader(read_at, file_size, limits=limits)
    catalog = owner.read_catalog()
    result = module._read_dbnames_from_catalog(owner, catalog, profile=profile, limits=named_limits)
    require(type(result) is module.NamedFileBytes and result.target == extraction.TARGET
            and result.profile_id == extraction.PROFILE_ID and type(result.data) is bytes
            and result.capability == 'experimental_named_file_bytes'
            and result.native_acceptance == 'pending', 'unexpected_failure')
    parse_profile = parser.DBNamesParseProfile(PROFILE_ID)
    parse_limits = parser.DBNamesParseLimits()
    try:
        reservation = parser.reserve_dbnames_parse(result.data, profile=parse_profile, limits=parse_limits)
        owner._budget.charge('bytes_processed', reservation.bytes_processed + len(result.data))
        owner._budget.charge('output_bytes', reservation.output_bytes)
        # Finite transport/summary and three retained comparison rows are charged
        # before they can be constructed. Reservations are never refunded.
        owner._budget.charge('output_bytes', MAX_PROJECTION_BYTES)
        index = parser.parse_dbnames(result.data, profile=parse_profile, limits=parse_limits)
    except parser.DBNamesParseError as error:
        raise reader_failure(error) from None
    transport = extraction.validate_projection({'schema': 1, 'target': extraction.TARGET,
        'profile_id': extraction.PROFILE_ID, 'profile_sha256': extraction.PROFILE_SHA256,
        'packed_bytes': result.packed_bytes, 'packed_sha256': result.packed_sha256,
        'plain_bytes': len(result.data), 'plain_sha256': hashlib.sha256(result.data).hexdigest()})
    return _ReaderEvidence(index, catalog, tuple(transport.items()), owner._budget)


def _native_names(native):
    try:
        metadata.validate_native_projection(native)
    except metadata.ObservationFailure as error:
        raise ObservationFailure(error.category, error.code) from None
    table = native['table']
    if table['logical_name'] != TARGET or table['metadata_name'] != TARGET:
        _fail('native_role_mismatch')
    names = [table['storage_name']]
    roles = [table]
    for logical in ROLE_NAMES[1:]:
        path = TARGET + '.Реквизит.' + logical
        selected = [field for field in table['fields']
                    if field['logical_name'] == logical or field['metadata_name'] == path]
        if not selected:
            _fail('native_role_missing')
        if len(selected) != 1:
            _fail('native_role_ambiguous')
        field = selected[0]
        if field['logical_name'] != logical or field['metadata_name'] != path:
            _fail('native_role_mismatch')
        names.append(field['storage_name'])
        roles.append(field)
    if len(set(names[1:])) != 2:
        _fail('duplicate_physical_target')
    return names, roles


def compare_identity(evidence, manifest, native, *, nonce):
    """Join only verified XML UUIDs to the already complete ordered index."""
    require(type(evidence) is _ReaderEvidence and type(evidence.index) is parser.DBNamesIndex
            and type(evidence.catalog) is reader.PhysicalCatalog
            and type(evidence.budget) is reader._Budget, 'unexpected_failure')
    validate_manifest(manifest, nonce=nonce)
    index = evidence.index
    require(index.profile == PROFILE_ID and type(index.entries) is tuple
            and len(index.entries) == index.declared_count <= 4096, 'unexpected_failure')
    # Three UUID scans, three rival scans and two summary scans. This declared
    # work weight stays cumulative with extraction and parsing; no reset/refund.
    try:
        evidence.budget.charge('bytes_processed', len(index.entries) * 8 * 128
            + len(evidence.catalog.tables) * 128
            + sum(len(table.fields) for table in evidence.catalog.tables) * 3 * 128)
    except reader.CatalogError as error:
        raise reader_failure(error) from None
    selected = []
    for expectation, kind in zip(manifest['roles'], ROLE_KINDS):
        count, entry = 0, None
        for candidate in index.entries:
            if candidate.uuid == expectation['uuid']:
                count += 1; entry = candidate
        if not count:
            _fail('target_identity_missing')
        if count != 1:
            _fail('target_identity_ambiguous')
        if entry.kind != kind:
            _fail('target_kind_mismatch')
        if entry.id <= 0:
            _fail('target_id_not_positive')
        selected.append(entry)
    predicted_native = ['_Reference' + str(selected[0].id),
                        '_Fld' + str(selected[1].id), '_Fld' + str(selected[2].id)]
    predicted_physical = ['_Reference' + str(selected[0].id),
                          '_FLD' + str(selected[1].id), '_FLD' + str(selected[2].id)]
    if len(set(predicted_physical[1:])) != 2:
        _fail('duplicate_physical_target')
    # A rival UUID with the same mapped kind/ID is also an ambiguous physical
    # target, including opaque zero UUIDs. Preserve all entries until this check.
    for chosen in selected:
        if sum(entry.kind == chosen.kind and entry.id == chosen.id for entry in index.entries) != 1:
            _fail('duplicate_physical_target')
    names, native_roles = _native_names(native)
    if names != predicted_native:
        _fail('native_name_mismatch')
    count, table = 0, None
    for candidate in evidence.catalog.tables:
        if candidate.name == predicted_physical[0]:
            count += 1; table = candidate
    if not count:
        _fail('physical_table_missing')
    if count != 1:
        _fail('physical_table_ambiguous')
    physical = [table.name]
    for name in predicted_physical[1:]:
        count, field = 0, None
        for candidate in table.fields:
            if candidate.name == name:
                count += 1; field = candidate
        if not count:
            _fail('physical_field_missing')
        if count != 1:
            _fail('physical_field_ambiguous')
        physical.append(field.name)
    rows = []
    for position, (expectation, entry) in enumerate(zip(manifest['roles'], selected)):
        rows.append({'role': ROLES[position], 'expected_uuid': expectation['uuid'],
            'parsed_uuid': entry.uuid, 'raw_uuid': entry.raw_uuid, 'kind': entry.kind,
            'id': entry.id, 'ordinal': entry.ordinal,
            'logical_name': native_roles[position]['logical_name'],
            'metadata_name': native_roles[position]['metadata_name'],
            'predicted_native': predicted_native[position], 'native_name': names[position],
            'predicted_physical': predicted_physical[position], 'physical_name': physical[position],
            'uuid_equal': True, 'native_equal': True, 'physical_equal': True})
    projection = {'schema': 1, 'target': TARGET, 'profile_id': PROFILE_ID,
        'profile_sha256': PROFILE_SHA256, 'transport': dict(evidence.transport),
        'summary': {'root_arity': 2, 'entry_arity': 3, 'header_value': index.header_value,
            'declared_count': index.declared_count, 'entry_count': len(index.entries),
            'opaque_kind_count': sum(entry.kind not in ('Reference', 'Fld') for entry in index.entries),
            'zero_uuid_count': sum(entry.uuid == ZERO_UUID for entry in index.entries)}, 'rows': rows}
    return validate_projection(projection, manifest=manifest)


def validate_projection(value, *, manifest):
    require(type(manifest) is dict)
    validate_manifest(manifest, nonce=manifest.get('nonce'))
    exact(value, {'schema', 'target', 'profile_id', 'profile_sha256', 'transport', 'summary', 'rows'})
    require(type(value['schema']) is int and value['schema'] == 1 and value['target'] == TARGET
            and value['profile_id'] == PROFILE_ID and value['profile_sha256'] == PROFILE_SHA256)
    extraction.validate_projection(value['transport'])
    summary = value['summary']
    exact(summary, {'root_arity', 'entry_arity', 'header_value', 'declared_count',
                    'entry_count', 'opaque_kind_count', 'zero_uuid_count'})
    require(type(summary['root_arity']) is int and summary['root_arity'] == 2
            and type(summary['entry_arity']) is int and summary['entry_arity'] == 3
            and integer(summary['header_value'], 2147483647)
            and integer(summary['declared_count'], 4096, 3)
            and type(summary['entry_count']) is int and summary['entry_count'] == summary['declared_count']
            and integer(summary['opaque_kind_count'], summary['entry_count'] - 3)
            and integer(summary['zero_uuid_count'], summary['entry_count'] - 3))
    rows = value['rows']
    require(type(rows) is list and len(rows) == 3)
    ordinals = set(); fields = set()
    for position, row in enumerate(rows):
        exact(row, {'role', 'expected_uuid', 'parsed_uuid', 'raw_uuid', 'kind', 'id', 'ordinal',
            'logical_name', 'metadata_name', 'predicted_native', 'native_name', 'predicted_physical', 'physical_name',
            'uuid_equal', 'native_equal', 'physical_equal'})
        expected = manifest['roles'][position]['uuid']
        require(row['logical_name'] == (TARGET if position == 0 else ROLE_NAMES[position])
                and row['metadata_name'] == (TARGET if position == 0 else TARGET + '.Реквизит.' + ROLE_NAMES[position]))
        require(row['role'] == ROLES[position] and row['kind'] == ROLE_KINDS[position]
                and row['expected_uuid'] == row['parsed_uuid'] == expected
                and _uuid(row['raw_uuid']) == expected and integer(row['id'], 2147483647, 1)
                and integer(row['ordinal'], summary['entry_count'] - 1)
                and all(row[key] is True for key in ('uuid_equal', 'native_equal', 'physical_equal')))
        require(row['ordinal'] not in ordinals); ordinals.add(row['ordinal'])
        native = ('_Reference' if position == 0 else '_Fld') + str(row['id'])
        physical = ('_Reference' if position == 0 else '_FLD') + str(row['id'])
        require(row['predicted_native'] == row['native_name'] == native
                and row['predicted_physical'] == row['physical_name'] == physical)
        if position:
            require(physical not in fields); fields.add(physical)
    require(len(encode(rows)) <= MAX_ROWS_BYTES
            and len(encode({key: item for key, item in value.items() if key != 'rows'})) <= MAX_OTHER_BYTES
            and len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, dbnames_identity=None,
        reader_validation='not_run', extraction_validation='not_run', observation_validation='not_run',
        mapping_validation='not_run', layout_validation='not_run', record_validation='not_run',
        native_byte_equivalence='not_observed', native_compatibility='not_claimed')
    return report


def bind_capture(evidence, report):
    require(type(report.get('schema')) is int and report['schema'] == SCHEMA and report.get('lane') == LANE)
    exact(evidence, {'marker', 'origin', 'postimage', 'reader', 'identity_manifest'})
    require(type(evidence['marker']) is dict and 'token' in evidence['marker'], 'invalid_marker')
    try:
        data = metadata.marker(encode(evidence['marker']), nonce=report['nonce'], token=evidence['marker']['token'])
    except metadata.ObservationFailure as error:
        raise ObservationFailure(error.category, error.code) from None
    origin = evidence['origin']
    exact(origin, {'nonce', 'token', 'clone', 'bytes', 'sha256'})
    exact(evidence['postimage'], {'bytes', 'sha256'})
    require(origin['nonce'] == report['nonce'] and origin['token'] == data['token']
            and origin['clone'] == 'auditor', 'snapshot_changed')
    manifest = validate_manifest(evidence['identity_manifest'], nonce=report['nonce'])
    projection = compare_identity(evidence['reader'], manifest, data['record_metadata'], nonce=report['nonce'])
    provenance = report['provenance']
    capture = {'schema': CAPTURE_SCHEMA, 'status': VERDICT, 'operation': OPERATION,
        'nonce': report['nonce'], 'token': data['token'], 'source_manifest_sha256': source_binding(provenance),
        'reader_source_sha256': provenance['sources'][READER_SOURCE],
        'policy_source_sha256': provenance['sources'][MODULE_SOURCE],
        'extractor_source_sha256': provenance['sources'][EXTRACTOR_SOURCE],
        'parser_source_sha256': provenance['sources'][PARSER_SOURCE],
        'actual_version': data['actual_version'],
        'image': provenance['image'], 'platform': provenance['platform'],
        'locale': provenance['locale'], 'timezone': provenance['timezone'],
        'metadata_version': 1, 'identity_basis': IDENTITY_BASIS,
        'xml_manifest': manifest, 'xml_manifest_sha256': hashlib.sha256(encode(manifest)).hexdigest(),
        'origin': {'snapshot': 'baseline', 'clone': 'auditor', 'bytes': origin['bytes'], 'sha256': origin['sha256']},
        'postimage': {'copy': 'auditor_frozen', 'binding': 'closed_post_audit_clone',
            'bytes': evidence['postimage']['bytes'], 'sha256': evidence['postimage']['sha256'],
            'storage_version': [8, 3, 8, 0], 'page_size': 8192}, 'reader': projection}
    _validate_binding(capture, report, nonce=report['nonce'], provenance=provenance, cleanup=False)
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    return capture


def _validate_binding(capture, report, *, nonce, provenance, final=False, cleanup=True):
    metadata._validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final, cleanup=cleanup)
    require(capture['policy_source_sha256'] == provenance['sources'][MODULE_SOURCE]
            and digest(capture['policy_source_sha256'])
            and capture['extractor_source_sha256'] == provenance['sources'][EXTRACTOR_SOURCE]
            and digest(capture['extractor_source_sha256'])
            and capture['parser_source_sha256'] == provenance['sources'][PARSER_SOURCE]
            and digest(capture['parser_source_sha256'])
            and capture['image'] == provenance['image'] == lifecycle.IMAGE
            and capture['platform'] == provenance['platform'] == 'linux/amd64'
            and capture['locale'] == provenance['locale'] == 'ru_RU.UTF-8'
            and capture['timezone'] == provenance['timezone'] == 'Etc/UTC'
            and type(capture['metadata_version']) is int and capture['metadata_version'] == 1
            and capture['identity_basis'] == IDENTITY_BASIS)
    manifest = validate_manifest(capture['xml_manifest'], nonce=nonce)
    require(digest(capture['xml_manifest_sha256'])
            and capture['xml_manifest_sha256'] == hashlib.sha256(encode(manifest)).hexdigest())


def discard_capture(report, failure=None, *, final=False):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA:
        return
    old = report.get('dbnames_identity'); report['dbnames_identity'] = None
    for key, verdict in (('reader_validation', VERDICT), ('mapping_validation', VERDICT),
                          ('extraction_validation', extraction.VERDICT)):
        previous = report[key]
        report[key] = ('discarded' if previous in (verdict, 'discarded') else
                       'failed' if previous == 'failed' else 'not_run')
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
        report['dbnames_identity'] = dict(old)
        report['reader_validation'] = report['mapping_validation'] = report['extraction_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report))
    require(all(report[key] == 'not_run' for key in ('observation_validation', 'layout_validation', 'record_validation'))
            and report['native_byte_equivalence'] == 'not_observed' and report['native_compatibility'] == 'not_claimed')
    require(all(report[key] in ('not_run', 'failed', 'discarded', VERDICT)
                for key in ('reader_validation', 'mapping_validation'))
            and report['extraction_validation'] in ('not_run', 'failed', 'discarded', extraction.VERDICT))
    from inputs import IDENTITY_SOURCE_FILES
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(IDENTITY_SOURCE_FILES)
            and len(IDENTITY_SOURCE_FILES) == 26
            and all(name in IDENTITY_SOURCE_FILES for name in (MODULE_SOURCE, PARSER_SOURCE)), 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND,
        'record_readback_failed', 'params_observation_failed', extraction.FAILURE_KIND))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline'); base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['dbnames_identity']
    if capture is not None:
        require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    if report['status'] != 'ok':
        require(report['reader_validation'] != VERDICT and report['mapping_validation'] != VERDICT
                and report['extraction_validation'] != extraction.VERDICT)
        if capture is not None:
            require(report['failure_kind'] == FAILURE_KIND
                    and report['reader_validation'] == report['mapping_validation'] == report['extraction_validation'] == 'failed')
            exact(capture, {'schema', 'status', 'category', 'code'})
            require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'failed'
                    and type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                    and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
            required = report['cleanup'] if final else {key: report['cleanup'][key]
                for key in ('native_processes_stopped', 'raw_files_removed')}
            require(all(value is True for value in required.values()))
        return report
    require(report['reader_validation'] == report['mapping_validation'] == VERDICT
            and report['extraction_validation'] == extraction.VERDICT)
    exact(capture, {'schema', 'status', 'reader'} | BINDING_KEYS)
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == VERDICT)
    _validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final)
    validate_projection(capture['reader'], manifest=capture['xml_manifest'])
    return report
