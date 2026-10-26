"""Closed failure-only CONFIG/root delimiter diagnosis on one fresh witness.

No projection, key, payload, target lookup, relation or success capture exists.
A finite stage code neither accepts metadata nor identifies an earlier witness.
"""
from __future__ import annotations

import hashlib
import json

import comparison
import config_framing_reader as framing
import filedb_catalog as reader
import protocol as lifecycle
import record_observation as metadata
from protocol import decode, encode, exact, require
from snapshots import OracleError

SCHEMA = 21
CAPTURE_SCHEMA = 22
LANE = 'owned_config_root_diagnostic_v1'
FAILURE_KIND = 'config_root_diagnostic_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/config_root_diagnostic.py'
FRAMING_READER_SOURCE = 'scripts/native_1c_db_oracle/config_framing_reader.py'
READER_SOURCE = comparison.READER_SOURCE
OPERATION = metadata.OPERATION
TARGET = 'CONFIG'
RECIPE_ID = 'config_root_diagnostic_8380_8192_v1'
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
    'filename_offset': 1, 'filename_width': 258,
    'first_marker': 'one_reserved_opaque_v1',
    'later_selection': 'zero_validate_nonzero_opaque_v1',
    'filename': 'u16le_units_at_most_128_strict_utf16le_v1',
    'selection': 'CONFIG_ascii_case_only_no_fallback_v1',
    'binarydata_offset': 287, 'binarydata_width': 8, 'partno_offset': 295, 'partno_width': 6,
    'reference': 'u32le_start_length_both_positive_nonempty_name_v1',
    'locator': 'aligned_256_start_in_range_length_at_most_250_capacity_v1',
    'partno': 'positive_sign1_ten_decimal_digits_pad0_at_most_4095_v1',
    'empty_data': 'unsupported', 'selected_part_zero_witness': 'fixed_root_chain_only_no_all_selected_witness_v1',
    'framing': 'not_accepted',
    'source_commit': 'd5e31816f4c9b11a445f73fc92d08803840ce599',
    'chain_header': 'block256_next_u32le_at0_used_u16le_at4_payload_at6_v1',
    'chain_termination': 'follow_until_zero_even_after_declared_length_v1',
    'chain_length': 'exact_stored_length_stricter_local_hypothesis_v1',
    'zero_used': 'allowed_intermediate_and_terminal_bounded_hops_v1',
    'chain_ownership': 'visited_root_chain_only_no_sharing_stricter_local_hypothesis_v1',
    'phases': 'all_selected_guards_then_fixed_root_diagnostic_stop_v1',
    'assembly': 'one_private_fixed_buffer_and_returned_copy_no_export_v1',
    'chain_limits': (1048576, 4194304, 8192, 32768),
    'shared_limits': (100000, 67108864, 134217728, 100000, 1048576,
        1048576, 16777216, 4096, 65536, 262144, 64, 65536, 20, 262144, 33554432),
    'budget_policy': 'intersect_remaining_shared_no_reset_refund_or_raise_v1',
    'representation_weights': (512, 2, 128, 128, 3, 128),
    'image_bytes_ceiling': 67108864,
    'compression': 'selected_singlepart_ascii_name_rule_raw_deflate_v1', 'file_assembly': 'not_run',
    'root_identity': 'not_observed', 'applied_state': 'not_observed',
    'selected_name': 'printable_ascii_1_128_units_ascii_fold_unique_v1',
    'selected_parts': 'every_selected_part_zero_required_v1',
    'dynamic_names': 'reject_final_new_and_any_ascii_fold_dynupdate_marker_v1',
    'plain_names': ('dynamicallyupdated', 'sprscndinfo', 'dbnamesversion', 'siversions'),
    'plain_patterns': 'leading_left_brace_or_fo_version_substring_or_final_inf_pf_v1',
    'inflate': 'raw_minus15_eof_full_consumption_no_flush_no_fallback_v1',
    'content_limits': (4194304, 8388608, 4096, 16384),
    'inflate_chunks': (32768, 65536),
    'content_weights': (512, 8, 4, 256, 131072, 2, 2),
    'inflate_output_probe': 'min_chunk_remaining_plus_one_strictly_positive_v1',
    'content_assembly': 'plain_alias_or_reserved_final_immutable_decoded_copy_v1',
    'content_budget': 'identical_chain_budget_cumulative_poison_on_failure_v1',
    'positive_decoded_witness': 'not_claimed_diagnostic_failure_only_v1',
    'locator_selector': 'root',
    'locator_grammar': 'initial_utf8_bom_ws_lbrace_2_comma_bare_guid_rbrace_ws_eof_v1',
    'locator_whitespace': (32, 9, 13, 10),
    'locator_guid': 'ascii_hex_8_4_4_4_12_no_key_materialization_v1',
    'locator_limit': 1024,
    'locator_limit_stage': 'after_unchanged_content_decode_before_syntax_scan_v1',
    'diagnostic_resolution': 'not_run',
    'diagnostic_order': 'root_once_then_stop_no_target_or_remaining_reads_v1',
    'diagnostic_attempt': 'single_use_poison_shared_decoder_and_chains_on_any_stop_v1',
    'diagnostic_result': 'failed_nonaccepted_three_delimiter_classes_or_complete_stop_v1',
    'diagnostic_map_weights': (512, 8, 4, 32),
    'diagnostic_parser_weights': (1024, 4, 128, 512),
    'diagnostic_lookup_weights': (256, 128),
    'diagnostic_context_weights': (1024, 256, 128),
    'diagnostic_failure_weight': 4096}
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE_DESCRIPTION, ensure_ascii=True,
    sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
MAX_SLOTS = 4096
# Inherited ceilings are not increased, even though no success projection exists.
MAX_PROJECTION_BYTES = 2048
MAX_CAPTURE_BYTES = 12288
FRAMING_VALIDATION = 'not_accepted'
EXTRA_KEYS = {'config_root_diagnostic', 'framing_validation', 'reader_validation', 'observation_validation',
    'extraction_validation', 'decompression_validation', 'mapping_validation', 'layout_validation',
    'native_byte_equivalence', 'native_compatibility'}
DIAGNOSTICS = {key: set(value) for key, value in comparison.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'].update(('missing_table_data_header', 'missing_table_blob_header',
    'config_table_missing', 'config_table_ambiguous', 'config_profile_mismatch',
    'config_empty_data', 'config_reserved_slot', 'config_filename_encoding',
    'config_blob_capacity', 'config_partno_encoding', 'config_reference_no_part_zero_witness',
    'config_chain_no_part_zero_witness', 'config_content_name_policy',
    'config_content_dynamic_name', 'config_content_duplicate_name', 'config_content_nonzero_part',
    'config_content_no_positive_witness', 'config_root_missing_selected_root',
    'config_root_bom', 'config_root_tag'))
DIAGNOSTICS['structural_rejection'].update(('table_data_header_role', 'table_blob_header_role',
    'config_record_length', 'config_filename_length', 'config_blob_alignment', 'config_reference_bounds',
    'config_chain_failed_attempt', 'config_chain_reference', 'config_chain_cycle', 'config_chain_used',
    'config_chain_next', 'config_chain_length', 'config_content_failed_attempt',
    'config_content_input', 'config_content_invalid_deflate', 'config_content_trailing_data',
    'config_content_truncated_deflate', 'config_content_nonprogress',
    'config_root_open_brace', 'config_root_comma', 'config_root_close_brace', 'config_root_guid', 'config_root_trailing',
    'config_root_input', 'config_root_failed_attempt'))
DIAGNOSTICS['resource_limit'].update(('config_record_bytes', 'config_slots', 'config_partno_limit',
    'config_chain_bytes', 'config_chain_total_bytes', 'config_chain_hops', 'config_chain_total_hops',
    'config_chain_image_bytes', 'config_content_bytes', 'config_content_total_bytes',
    'config_content_inflate_calls', 'config_content_total_inflate_calls', 'config_root_input_bytes'))
DIAGNOSTICS['unsupported_sharing_policy'].add('config_chain_overlap')

DIAGNOSTICS['diagnostic_stop'] = {'config_root_diagnostic_complete'}


class ObservationFailure(OracleError):
    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code


def reader_failure(error):
    if (type(error) is framing._ConfigRootDiagnosticComplete
            and type(error.code) is str and error.code == 'config_root_diagnostic_complete'):
        return ObservationFailure('diagnostic_stop', 'config_root_diagnostic_complete')
    for kind, category in ((reader.UnsupportedLayout, 'unsupported_layout'),
            (reader.InvalidStructure, 'structural_rejection'), (reader.ResourceLimit, 'resource_limit'),
            (reader.UnsupportedSharing, 'unsupported_sharing_policy')):
        if type(error) is kind and type(error.code) is str and error.code in DIAGNOSTICS[category]:
            return ObservationFailure(category, error.code)
    classified = comparison.reader_failure(error)
    return ObservationFailure(classified.category, classified.code)


def read_projection(read_at, file_size, *, limits):
    """Inherited callback name only: this operation must never return a projection."""
    profile = framing.ConfigRootDiagnosticProfile(DECLARATIONS, '0', 0)
    require(profile.identifier == RECIPE_ID and profile.recipe_sha256 == RECIPE_SHA256
            and profile.candidate_stride == 301 and profile.filename_offset == 1
            and profile.filename_width == 258 and profile.binarydata_offset == 287
            and profile.binarydata_width == 8 and profile.partno_offset == 295
            and profile.partno_width == 6, 'provenance_mismatch')
    framing.observe_config_root_diagnostic(read_at, file_size, profile=profile,
        limits=framing.ConfigFramingLimits(max_slots=MAX_SLOTS, max_record_bytes=4096),
        chain_limits=framing.ConfigBlobChainLimits(),
        content_limits=framing.ConfigContentDecodeLimits(),
        root_limits=framing.ConfigRootReferenceLimits(), catalog_limits=limits)
    # A broken or replaced observer cannot make the inherited success path live.
    raise OracleError('unexpected_failure')


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, config_root_diagnostic=None,
        framing_validation=FRAMING_VALIDATION, reader_validation='not_run',
        observation_validation='not_run', extraction_validation='not_run',
        decompression_validation='not_run', mapping_validation='not_run', layout_validation='not_run',
        native_byte_equivalence='not_observed', native_compatibility='not_claimed')
    return report


def discard_capture(report, failure=None, *, final=False):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA:
        return
    old = report.get('config_root_diagnostic')
    report['config_root_diagnostic'] = None
    for key in ('reader_validation', 'observation_validation'):
        report[key] = 'failed' if report[key] == 'failed' else 'not_run'
    if type(failure) is ObservationFailure:
        old = {'schema': CAPTURE_SCHEMA, 'status': 'failed', 'category': failure.category, 'code': failure.code}
    # Container transport can prove only its two local gates. Final retained
    # evidence requires all four host+container cleanup gates, without exception.
    cleanup = report['cleanup'] if final else {key: report['cleanup'][key]
        for key in ('native_processes_stopped', 'raw_files_removed')}
    if (all(value is True for value in cleanup.values()) and report.get('status') == 'failed'
            and report.get('accepted') is False and report.get('failure_kind') == FAILURE_KIND
            and report.get('failed_stage') == 'baseline'
            and type(old) is dict and set(old) == {'schema', 'status', 'category', 'code'}
            and type(old['schema']) is int and old['schema'] == CAPTURE_SCHEMA and old['status'] == 'failed'
            and type(old['category']) is str and old['category'] in DIAGNOSTICS
            and type(old['code']) is str and old['code'] in DIAGNOSTICS[old['category']]):
        report['config_root_diagnostic'] = dict(old)
        report['reader_validation'] = report['observation_validation'] = 'failed'
    report['decompression_validation'] = report['observation_validation']


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int and report['schema'] == SCHEMA
            and report.get('lane') == LANE and EXTRA_KEYS <= set(report))
    require(report.get('status') == 'failed' and report.get('accepted') is False)
    require(report['framing_validation'] == FRAMING_VALIDATION
            and all(report[key] == 'not_run' for key in ('extraction_validation', 'mapping_validation', 'layout_validation'))
            and report['native_byte_equivalence'] == 'not_observed' and report['native_compatibility'] == 'not_claimed')
    require((report['reader_validation'], report['observation_validation']) in (
        ('not_run', 'not_run'), ('failed', 'not_run'), ('failed', 'failed')))
    require(report['decompression_validation'] == report['observation_validation'])
    from inputs import CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES
    require(type(provenance.get('sources')) is dict
            and set(provenance['sources']) == set(CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES)
            and len(CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES) == 23
            and MODULE_SOURCE in CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES
            and FRAMING_READER_SOURCE in CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND,
        'record_readback_failed', 'params_observation_failed', 'params_extraction_failed',
        'dbnames_identity_failed', 'config_observation_failed', 'config_framing_failed',
        'config_marker_census_failed', 'config_zero_marker_filename_failed',
        'config_entry_reference_failed', 'config_blob_chain_failed',
        'config_content_decode_failed', 'config_root_reference_failed'))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline')
        base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['config_root_diagnostic']
    if capture is not None:
        require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
        require(report['failure_kind'] == FAILURE_KIND
                and report['reader_validation'] == report['observation_validation'] == 'failed')
        exact(capture, {'schema', 'status', 'category', 'code'})
        require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA and capture['status'] == 'failed'
                and type(capture['category']) is str and capture['category'] in DIAGNOSTICS
                and type(capture['code']) is str and capture['code'] in DIAGNOSTICS[capture['category']])
        required = report['cleanup'] if final else {key: report['cleanup'][key]
            for key in ('native_processes_stopped', 'raw_files_removed')}
        require(all(value is True for value in required.values()))
    return report
