"""Closed CONFIG/DBNames-derived owned Catalog binding and six readbacks.

Raw metadata, descriptors and rows never become transport values.

The format integer-zero restriction is an explicit experimental hypothesis,
not a format-version interpretation. See docs/native-record-readback.md.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import types
from dataclasses import dataclass
import config_catalog_attribute_binding as attributes_policy
from decimal import Decimal

import comparison
import filedb_catalog
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 37
LANE = 'owned_catalog_readonly_binding_v1'
CAPTURE_SCHEMA = 38
FAILURE_KIND = 'catalog_readonly_binding_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/catalog_readonly_binding.py'
READER_SOURCE = 'scripts/native_1c_db_oracle/catalog_binding_reader.py'
TARGETS = ('baseline', 'created', 'updated')
STAGES = {'baseline': 'baseline', 'created': 'create', 'updated': 'update'}
MAPPING_VERDICT = 'owned_config_dbnames_fields_match'
LAYOUT_VERDICT = 'owned_config_derived_layout_match'
VERDICT = 'owned_bound_empty_create_update_match'
STATE_VERDICT = 'origin_and_observer_values_match'
MAX_CAPTURE_BYTES = 12288
PROFILE_ID = 'owned_config_dbnames_rows_v1'
PROFILE_DESCRIPTION = {'id': PROFILE_ID,
    'core': 'selector_only_one_reader_config_params_records_per_image',
    'schema': 'derived_CONFIG_UUID_qualifiers_then_DBNAMES_then_exact_physical_comparison',
    'owned_shape': 'StringCode_noDescription_variableString_signedNumber',
    'coverage': 'current_owned_fixture_only_not_general_qualifier_ranges',
    'readbacks': 'baseline_created_updated_origin_and_observer',
    'independent_oracle': 'complete_canonical_XML_and_native_metadata_after_finished_reader',
    'public_values': 'finite_verdicts_counts_hashes_only',
    'layout': 'RVfirst_status1_min5_NVC2plus2n_Nhalfprecisionrounded',
    'numeric_admission': 'sign01_digits09_even_precision_zero_padding'}
PROFILE_SHA256 = hashlib.sha256(encode(PROFILE_DESCRIPTION)).hexdigest()
ROLE_LABELS = (('reference','Ссылка',''),('version','ВерсияДанных',''),
    ('deletion_mark','ПометкаУдаления',''),('predefined','ИмяПредопределенныхДанных',''),
    ('code','Код',''),('payload','Payload',metadata.TARGET+'.Реквизит.Payload'),
    ('amount','Amount',metadata.TARGET+'.Реквизит.Amount'))
OPERATION = metadata.OPERATION
build_identity_manifest = attributes_policy.build_identity_manifest

EXTRA_KEYS = (metadata.EXTRA_KEYS - {'record_observation'}) | {'record_readback'}
FRAMINGS = ('empty_zero_length', 'empty_reserved', 'reserved_and_active')
DIAGNOSTICS = {key: set(value) for key, value in attributes_policy.DIAGNOSTICS.items()}
DIAGNOSTICS.setdefault('mapping_mismatch', set()).add('owned_mapping_profile')
DIAGNOSTICS.setdefault('record_mismatch', set()).update(('active_count', 'mapped_values', 'record_result'))
DIAGNOSTICS['unsupported_layout'].update(('format_integer_nonzero', 'format_string_zero',
    'format_string_other', 'format_list', 'format_other', 'selected_table_count',
    'recordlock_mismatch', 'declaration_mismatch', 'boolean_encoding', 'string_encoding',
    'decimal_sign', 'decimal_digit', 'decimal_padding', 'reserved_slot_marker', 'nonreserved_free_slot',
    'missing_table_data_header'))
DIAGNOSTICS['structural_rejection'].update(('record_file_length', 'string_length', 'table_data_header_role'))
DIAGNOSTICS['resource_limit'].update(('record_fields', 'record_bytes', 'record_slots', 'active_records'))
DIAGNOSTICS['structural_rejection'].update(('binding_rejected', 'dbnames_rejected', 'binding_core_failed',
    'binding_catalog_identity','binding_dbnames_invalid','binding_graph_state','binding_reader_sources',
    'binding_catalog_selector','binding_limits'))
DIAGNOSTICS['unsupported_layout'].update(('binding_catalog_missing','binding_catalog_ambiguous',
    'binding_dbnames_profile','binding_metadata_profile','binding_catalog_selector'))
DIAGNOSTICS['resource_limit'].add('binding_dbnames_limits')


class ReadbackFailure(OracleError):
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code
        self.binding = None


def fail(category, code):
    raise ReadbackFailure(category, code)


@dataclass(frozen=True)
class _PrivateOracle:
    metadata: dict
    manifest: object
    nonce: str


def _key(name):
    return ''.join(chr(ord(c)-32) if 'a' <= c <= 'z' else c for c in name)


def _compare_configuration(result, oracle):
    """Compare full completed private CONFIG result; never modify parser inputs."""
    manifest = attributes_policy.validate_manifest(oracle.manifest, nonce=oracle.nonce)
    fields = result.config_observation.private_fields
    if type(fields) is not tuple or len(fields) != 3:
        fail('mapping_mismatch', 'owned_mapping_profile')
    expected = {x.key:x for x in manifest.catalogs}
    seen = set()
    for key, identity, attributes in fields:
        if key in seen or key not in expected or identity.metadata_uuid != key:
            fail('mapping_mismatch', 'owned_mapping_profile')
        seen.add(key); wanted = expected[key]
        if ((identity.name,identity.code_length,identity.code_type,identity.description_length)
                != (wanted.name,wanted.code_length,wanted.code_type,wanted.description_length)):
            fail('mapping_mismatch', 'owned_mapping_profile')
        actual = tuple((x.metadata_uuid,x.name,x.type_token,x.qualifiers) for x in attributes.attributes)
        attributes_policy._validate_attributes(actual)
        if {x[0]:x[1:] for x in actual} != {x[0]:x[1:] for x in wanted.attributes}:
            fail('mapping_mismatch', 'owned_mapping_profile')
    selected = [x for x in fields if x[1].name == 'NativeOracleItems']
    if (len(selected) != 1 or result.identity != selected[0][1]
            or result.attributes != selected[0][2]
            or result.binding.metadata_uuid != result.identity.metadata_uuid
            or result.binding.name != result.identity.name):
        fail('mapping_mismatch', 'owned_mapping_profile')


def _compare_mapping(result, oracle):
    native, physical = oracle.metadata['native'], oracle.metadata['reader']
    metadata.validate_names_bijection(native,physical)
    nt,pt=native['table'],physical['table']; compiled=result.binding
    if (nt['logical_name'] != metadata.TARGET or nt['metadata_name'] != metadata.TARGET
            or compiled.table_name != nt['storage_name'] or compiled.table_name != pt['name']
            or pt['record_lock_token'] != compiled.recordlock or len(pt['fields']) != 7
            or len(nt['fields']) != 7 or len(compiled.declarations) != 7):
        fail('mapping_mismatch','owned_mapping_profile')
    by_identity={}
    for field in nt['fields']:
        key=(field['logical_name'],field['metadata_name'])
        if key in by_identity or field['type_text'] != '':fail('mapping_mismatch','owned_mapping_profile')
        by_identity[key]=field['storage_name']
    names={}
    for observed,wanted,(role,logical,path) in zip(pt['fields'],compiled.declarations,ROLE_LABELS):
        declaration=tuple(observed[k] for k in ('name','type_token','nullability','length','precision','case_token'))
        if (declaration != wanted or (logical,path) not in by_identity
                or _key(by_identity[(logical,path)]) != wanted[0]):
            fail('mapping_mismatch','owned_mapping_profile')
        names[role]=wanted[0]
    # Role labels belong exclusively to this owned comparator, not the compiler.
    if tuple(x.name for x in compiled.attributes) != ('Payload','Amount'):
        fail('mapping_mismatch','owned_mapping_profile')
    return names


def reader_failure(error):
    if type(error) is filedb_catalog.UnsupportedLayout and error.code in DIAGNOSTICS['unsupported_layout']:
        return ReadbackFailure('unsupported_layout', error.code)
    if type(error) is filedb_catalog.InvalidStructure and error.code in DIAGNOSTICS['structural_rejection']:
        return ReadbackFailure('structural_rejection', error.code)
    if type(error) is filedb_catalog.ResourceLimit and error.code in DIAGNOSTICS['resource_limit']:
        return ReadbackFailure('resource_limit', error.code)
    classified = comparison.reader_failure(error)
    return ReadbackFailure(classified.category, classified.code)


def compare_values(result, identifier, oracle, reader):
    require(identifier in TARGETS, 'invalid_input')
    if (type(oracle) is not _PrivateOracle
            or type(result) is not reader.CatalogBindingReadResult):
        fail('record_mismatch','record_result')
    try:
        _compare_configuration(result,oracle)
        names=_compare_mapping(result,oracle)
    except (attributes_policy.ObservationFailure, metadata.ObservationFailure, comparison.ComparisonFailure) as error:
        raise ReadbackFailure(error.category,error.code) from None
    rows=result.records
    if rows.record_size != result.binding.record_size or rows.framing not in FRAMINGS:
        fail('record_mismatch','record_result')
    expected=lifecycle.expected_logical(identifier)
    if len(rows.rows) != expected['count']:fail('record_mismatch','active_count')
    if not rows.rows:
        if rows.framing not in FRAMINGS[:2]:fail('record_mismatch','record_result')
        return rows.framing
    if rows.framing != 'reserved_and_active':fail('record_mismatch','record_result')
    values={x.declaration.name:x.value for x in rows.rows[0].fields}
    scale=result.binding.attributes[1].qualifiers[1]
    for role in ('code','payload','amount','deletion_mark'):
        wanted=Decimal(expected[role]) if role=='amount' else expected[role]
        value=values.get(names[role])
        if type(value) is not type(wanted) or value != wanted:fail('record_mismatch','mapped_values')
        if role=='amount' and value.as_tuple().exponent != -scale:fail('record_mismatch','mapped_values')
    return rows.framing


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
    exact(evidence, {'marker','origin','postimage','reader','identity_manifest'})
    manifest=attributes_policy.validate_manifest(evidence['identity_manifest'],nonce=report['nonce'])
    measured=metadata.bind_capture({k:v for k,v in evidence.items() if k!='identity_manifest'},_metadata_view(report))
    capture={'schema':CAPTURE_SCHEMA,'status':'matched','profile_id':PROFILE_ID,
        'profile_sha256':PROFILE_SHA256,
        'record_reader_source_sha256':report['provenance']['sources'][READER_SOURCE],
        'audit':{k:measured[k] for k in metadata.BINDING_KEYS},
        'identity_manifest_sha256':attributes_policy.manifest_digest(manifest),
        'catalog_count':3,'attribute_count':2,'states':[]}
    return capture,_PrivateOracle(measured,manifest,report['nonce']),'NativeOracleItems'


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
        'verdict': STATE_VERDICT, 'binding_verdict': MAPPING_VERDICT}


def _validate_state(value, identifier, report):
    exact(value, {'snapshot','origin_sha256','observe_token','observer_bytes','observer_sha256',
                  'origin_framing','observer_framing','verdict','binding_verdict'})
    physical = next(item['physical'] for item in report['snapshots'] if item['id'] == identifier)
    require(value['snapshot'] == identifier and value['origin_sha256'] == physical['sha256']
            and digest(value['origin_sha256']) and digest(value['observer_sha256'])
            and integer(value['observer_bytes'], MAX_FILE_BYTES, 3*8192)
            and value['observer_bytes'] % 8192 == 0 and type(value['observe_token']) is str
            and len(value['observe_token']) == 32 and all(c in '0123456789abcdef' for c in value['observe_token'])
            and value['verdict'] == STATE_VERDICT and value['binding_verdict'] == MAPPING_VERDICT)
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
    from inputs import CATALOG_BINDING_SOURCE_FILES
    require(set(provenance['sources']) == set(CATALOG_BINDING_SOURCE_FILES)
            and MODULE_SOURCE in CATALOG_BINDING_SOURCE_FILES and READER_SOURCE in CATALOG_BINDING_SOURCE_FILES, 'provenance_mismatch')
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
    exact(capture, {'schema','status','profile_id','profile_sha256','record_reader_source_sha256','audit','identity_manifest_sha256','catalog_count','attribute_count','states'})
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'matched'
            and capture['profile_id'] == PROFILE_ID and capture['profile_sha256'] == PROFILE_SHA256
            and capture['record_reader_source_sha256'] == provenance['sources'][READER_SOURCE])
    measured = capture['audit']
    exact(measured, metadata.BINDING_KEYS)
    metadata._validate_binding(measured, report, nonce=nonce, provenance=provenance, final=final)
    require(digest(capture['identity_manifest_sha256'])
            and type(capture['catalog_count']) is int and capture['catalog_count']==3
            and type(capture['attribute_count']) is int and capture['attribute_count']==2)
    require(type(capture['states']) is list and len(capture['states']) == 3)
    for state, identifier in zip(capture['states'], TARGETS): _validate_state(state, identifier, report)
    tokens = [measured['token']] + [state['observe_token'] for state in capture['states']]
    require(len(set(tokens)) == 4)
    return report
