"""Closed owned-v1 row lane. Raw records never become transport values.

The format integer-zero restriction is an explicit experimental hypothesis,
not a format-version interpretation. See docs/native-record-readback.md.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import types
from decimal import Decimal

import comparison
import filedb_catalog
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 6
LANE = 'owned_record_readback_v1'
CAPTURE_SCHEMA = 7
FAILURE_KIND = 'record_readback_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/record_validation.py'
READER_SOURCE = 'yadinassi/storage/filedb_records.py'
TARGETS = ('baseline', 'created', 'updated')
STAGES = {'baseline': 'baseline', 'created': 'create', 'updated': 'update'}
MAPPING_VERDICT = 'owned_logical_field_mapping_match'
LAYOUT_VERDICT = 'owned_v1_fixed_layout_match'
VERDICT = 'owned_v1_empty_create_update_match'
STATE_VERDICT = 'origin_and_observer_four_fields_match'
MAX_CAPTURE_BYTES = 12288
PROFILE_ID = 'owned_v1_rv16_nvc_bcd127_intzero_v1'
# Source facts, not copied implementation. The skipped second descriptor node
# has UNKNOWN semantics in the pinned source; no type/domain check exists there.
FORMAT_SOURCE = 'https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L188-L190'
FORMAT_SOURCE_SHA256 = '420c5df09444c0af5a9736ce2c0523a1f070e451d458cf5cb620cbc6d2dfdcff'
ROLE_VECTOR = (
    ('reference', 'Ссылка', '', ('B', 0, 16, 0, 'CS')),
    ('version', 'ВерсияДанных', '', ('RV', 0, 0, 0, 'CS')),
    ('deletion_mark', 'ПометкаУдаления', '', ('L', 0, 0, 0, 'CS')),
    ('predefined', 'ИмяПредопределенныхДанных', '', ('B', 0, 16, 0, 'CS')),
    ('code', 'Код', '', ('NVC', 0, 2, 0, 'CI')),
    ('payload', 'Payload', metadata.TARGET + '.Реквизит.Payload', ('NVC', 0, 32, 0, 'CI')),
    ('amount', 'Amount', metadata.TARGET + '.Реквизит.Amount', ('N', 0, 9, 2, 'CS')),
)
PROFILE_DESCRIPTION = {'id': PROFILE_ID, 'format_admission': 'exact_integer_zero_unknown_semantics',
    'format_source': FORMAT_SOURCE, 'format_source_sha256': FORMAT_SOURCE_SHA256,
    'recordlock': '0', 'roles': ROLE_VECTOR,
    'offsets': [17, 1, 33, 34, 50, 56, 122], 'widths': [16, 16, 1, 16, 6, 66, 5],
    'record_size': 127, 'reserved_marker': 1, 'active_marker': 0,
    'nonreserved_free_slots': 'unsupported', 'string_codec': 'u16le_length_utf16le',
    'decimal_codec': 'sign0negative1positive_nine_bcd_digits_scale2',
    'empty': ['valid_data_header_zero_length', 'reserved_slot_only']}
PROFILE_SHA256 = hashlib.sha256(encode(PROFILE_DESCRIPTION)).hexdigest()
EXTRA_KEYS = (metadata.EXTRA_KEYS - {'record_observation'}) | {'record_readback'}
FRAMINGS = ('empty_zero_length', 'empty_reserved', 'reserved_and_active')
DIAGNOSTICS = {key: set(value) for key, value in metadata.DIAGNOSTICS.items()}
DIAGNOSTICS.setdefault('mapping_mismatch', set()).add('owned_mapping_profile')
DIAGNOSTICS.setdefault('record_mismatch', set()).update(('active_count', 'mapped_values', 'record_result'))
DIAGNOSTICS['unsupported_layout'].update(('format_integer_nonzero', 'format_string_zero',
    'format_string_other', 'format_list', 'format_other', 'selected_table_count',
    'recordlock_mismatch', 'declaration_mismatch', 'boolean_encoding', 'string_encoding',
    'decimal_sign', 'decimal_digit', 'reserved_slot_marker', 'nonreserved_free_slot',
    'missing_table_data_header'))
DIAGNOSTICS['structural_rejection'].update(('record_file_length', 'string_length', 'table_data_header_role'))
DIAGNOSTICS['resource_limit'].update(('record_fields', 'record_bytes', 'record_slots', 'active_records'))


class ReadbackFailure(OracleError):
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code
        self.binding = None


def fail(category, code):
    raise ReadbackFailure(category, code)


def load_reader(path):
    """Load pinned sibling sources without importing yadinassi or its runtime."""
    name = '_owned_record_storage'
    package = types.ModuleType(name); package.__path__ = []
    sys.modules[name] = package
    sys.modules[name + '.filedb_catalog'] = filedb_catalog
    spec = importlib.util.spec_from_file_location(name + '.filedb_records', path)
    require(spec is not None and spec.loader is not None, 'provenance_mismatch')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _key(name):
    return ''.join(chr(ord(c)-32) if 'a' <= c <= 'z' else c for c in name)


def mapping_profile(capture, reader=None):
    """Bind labels first; expected declaration/format values are literal facts."""
    native, physical = capture['native'], capture['reader']
    metadata.validate_names_bijection(native, physical)
    nt, pt = native['table'], physical['table']
    if (nt['logical_name'] != metadata.TARGET or nt['metadata_name'] != metadata.TARGET
            or len(nt['fields']) != 7 or len(pt['fields']) != 7 or pt['record_lock_token'] != '0'):
        fail('mapping_mismatch', 'owned_mapping_profile')
    by_identity = {}
    for field in nt['fields']:
        identity = (field['logical_name'], field['metadata_name'])
        if identity in by_identity or field['type_text'] != '':
            fail('mapping_mismatch', 'owned_mapping_profile')
        by_identity[identity] = field['storage_name']
    names = {}; declarations = []
    for physical_field, (role, logical, path, expected) in zip(pt['fields'], ROLE_VECTOR):
        if (logical, path) not in by_identity:
            fail('mapping_mismatch', 'owned_mapping_profile')
        name = physical_field['name']
        observed = tuple(physical_field[key] for key in ('type_token','nullability','length','precision','case_token'))
        if _key(by_identity[(logical, path)]) != _key(name) or observed != expected:
            fail('mapping_mismatch', 'owned_mapping_profile')
        names[role] = name
        declarations.append((name, *expected))
    if reader is None:
        return names, tuple(declarations)
    profile = reader.RecordProfile(table_name=pt['name'], declarations=tuple(declarations),
                                   recordlock='0', format_item=0)
    require(profile.record_size == 127 and tuple(x.offset for x in profile.placements)
            == (17,1,33,34,50,56,122), 'unexpected_failure')
    return names, profile


def reader_failure(error):
    if type(error) is filedb_catalog.UnsupportedLayout and error.code in DIAGNOSTICS['unsupported_layout']:
        return ReadbackFailure('unsupported_layout', error.code)
    if type(error) is filedb_catalog.InvalidStructure and error.code in DIAGNOSTICS['structural_rejection']:
        return ReadbackFailure('structural_rejection', error.code)
    if type(error) is filedb_catalog.ResourceLimit and error.code in DIAGNOSTICS['resource_limit']:
        return ReadbackFailure('resource_limit', error.code)
    classified = comparison.reader_failure(error)
    return ReadbackFailure(classified.category, classified.code)


def compare_values(result, identifier, names, reader):
    require(identifier in TARGETS, 'invalid_input')
    if type(result) is not reader.PhysicalRecords or result.record_size != 127 or result.framing not in FRAMINGS:
        fail('record_mismatch', 'record_result')
    expected = lifecycle.expected_logical(identifier)
    if len(result.rows) != expected['count']:
        fail('record_mismatch', 'active_count')
    if not result.rows:
        if result.framing not in FRAMINGS[:2]: fail('record_mismatch', 'record_result')
        return result.framing
    if result.framing != 'reserved_and_active': fail('record_mismatch', 'record_result')
    values = {field.declaration.name: field.value for field in result.rows[0].fields}
    for role in ('code', 'payload', 'amount', 'deletion_mark'):
        wanted = Decimal(expected[role]) if role == 'amount' else expected[role]
        value = values.get(names[role])
        if type(value) is not type(wanted) or value != wanted:
            fail('record_mismatch', 'mapped_values')
        if role == 'amount' and value.as_tuple().exponent != -2:
            fail('record_mismatch', 'mapped_values')
    return result.framing


def empty_report(nonce, provenance):
    report = metadata.empty_report(nonce, provenance)
    del report['record_observation']
    report.update(schema=SCHEMA, lane=LANE, record_readback=None)
    return report


def _metadata_view(report):
    value = dict(report)
    value.update(schema=metadata.SCHEMA, lane=metadata.LANE)
    return value


def begin_capture(evidence, report, reader):
    measured = metadata.bind_capture(evidence, _metadata_view(report))
    names, profile = mapping_profile(measured, reader)
    capture = {'schema': CAPTURE_SCHEMA, 'status': 'matched', 'profile_id': PROFILE_ID,
        'profile_sha256': PROFILE_SHA256,
        'record_reader_source_sha256': report['provenance']['sources'][READER_SOURCE],
        'metadata': measured, 'states': []}
    return capture, names, profile


def bind_state(identifier, evidence, report, origin_framing, observer_framing):
    require(identifier in TARGETS and origin_framing in FRAMINGS and observer_framing in FRAMINGS, 'invalid_input')
    exact(evidence, {'snapshot','token','origin','postimage','logical'})
    expected = next((item for item in report['snapshots'] if item['id'] == identifier), None)
    require(expected is not None and evidence['snapshot'] == identifier
            and evidence['logical'] == expected['logical'], 'snapshot_changed')
    for summary in (evidence['origin'], evidence['postimage']):
        exact(summary, {'bytes','sha256'})
        require(integer(summary['bytes'], MAX_FILE_BYTES, 3*8192) and digest(summary['sha256']), 'snapshot_changed')
    require(evidence['origin'] == {key: expected['physical'][key] for key in ('bytes','sha256')}, 'snapshot_changed')
    require(type(evidence['token']) is str and len(evidence['token']) == 32
            and all(c in '0123456789abcdef' for c in evidence['token']), 'invalid_marker')
    return {'snapshot': identifier, 'origin_sha256': evidence['origin']['sha256'],
        'observe_token': evidence['token'], 'observer_bytes': evidence['postimage']['bytes'],
        'observer_sha256': evidence['postimage']['sha256'],
        'origin_framing': origin_framing, 'observer_framing': observer_framing,
        'verdict': STATE_VERDICT}


def _validate_state(value, identifier, report):
    exact(value, {'snapshot','origin_sha256','observe_token','observer_bytes','observer_sha256',
                  'origin_framing','observer_framing','verdict'})
    physical = next(item['physical'] for item in report['snapshots'] if item['id'] == identifier)
    require(value['snapshot'] == identifier and value['origin_sha256'] == physical['sha256']
            and digest(value['origin_sha256']) and digest(value['observer_sha256'])
            and integer(value['observer_bytes'], MAX_FILE_BYTES, 3*8192)
            and value['observer_bytes'] % 8192 == 0 and type(value['observe_token']) is str
            and len(value['observe_token']) == 32 and all(c in '0123456789abcdef' for c in value['observe_token'])
            and value['verdict'] == STATE_VERDICT)
    allowed = FRAMINGS[:2] if identifier == 'baseline' else FRAMINGS[2:]
    require(value['origin_framing'] in allowed and value['observer_framing'] in allowed)


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
            and report['projection_mode'] == metadata.PROJECTION_MODE
            and report['comparison_policy'] == metadata.COMPARISON_POLICY
            and report['native_compatibility'] == 'not_claimed')
    from inputs import ROW_SOURCE_FILES
    require(set(provenance['sources']) == set(ROW_SOURCE_FILES) and len(ROW_SOURCE_FILES) == 23
            and MODULE_SOURCE in ROW_SOURCE_FILES and READER_SOURCE in ROW_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    success_values = {'metadata_validation': metadata.METADATA_VERDICT, 'reader_validation': metadata.VERDICT,
        'mapping_validation': MAPPING_VERDICT, 'layout_validation': LAYOUT_VERDICT, 'record_validation': VERDICT}
    for key, passed in success_values.items():
        require(report[key] in ('not_run','failed','discarded',passed))
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] in ('baseline','create','update'))
        base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
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
    exact(capture, {'schema','status','profile_id','profile_sha256','record_reader_source_sha256','metadata','states'})
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'matched'
            and capture['profile_id'] == PROFILE_ID and capture['profile_sha256'] == PROFILE_SHA256
            and capture['record_reader_source_sha256'] == provenance['sources'][READER_SOURCE])
    measured = capture['metadata']
    exact(measured, {'schema','status','projection_mode','comparison_policy','native','reader'} | metadata.BINDING_KEYS)
    require(type(measured['schema']) is int and measured['schema'] == metadata.CAPTURE_SCHEMA
            and measured['status'] == metadata.METADATA_VERDICT and measured['projection_mode'] == metadata.PROJECTION_MODE
            and measured['comparison_policy'] == metadata.COMPARISON_POLICY)
    metadata._validate_binding(measured, report, nonce=nonce, provenance=provenance, final=final)
    mapping_profile(measured)
    require(type(capture['states']) is list and len(capture['states']) == 3)
    for state, identifier in zip(capture['states'], TARGETS): _validate_state(state, identifier, report)
    tokens = [measured['token']] + [state['observe_token'] for state in capture['states']]
    require(len(set(tokens)) == 4)
    return report
