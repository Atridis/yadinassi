"""Closed owned internal UUID/key/Name/standard-property partial-prefix binding.

Exact length, nonzero UUID and no cross-chain sharing are local admission rules,
not complete native equivalence. No complete root/target grammar, full Catalog
schema or applied-state claim. Native evidence requires separate dedicated gates.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

import comparison
import config_framing_reader as framing
import filedb_catalog as reader
import protocol as lifecycle
import record_observation as metadata
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 31
CAPTURE_SCHEMA = 32
LANE = 'owned_config_catalog_identity_binding_v1'
FAILURE_KIND = 'config_catalog_identity_binding_failed'
MODULE_SOURCE = 'scripts/native_1c_db_oracle/config_catalog_identity_binding.py'
FRAMING_READER_SOURCE = 'scripts/native_1c_db_oracle/config_framing_reader.py'
READER_SOURCE = comparison.READER_SOURCE
OPERATION = metadata.OPERATION
TARGET = 'CONFIG'
RECIPE_ID = 'config_catalog_identity_8380_8192_v1'
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
    'empty_data': 'unsupported', 'selected_part_zero_witness': 'completely_read_positive_stored_chain_required',
    'framing': 'not_accepted',
    'source_commit': 'd5e31816f4c9b11a445f73fc92d08803840ce599',
    'chain_header': 'block256_next_u32le_at0_used_u16le_at4_payload_at6_v1',
    'chain_termination': 'follow_until_zero_even_after_declared_length_v1',
    'chain_length': 'exact_stored_length_stricter_local_hypothesis_v1',
    'zero_used': 'allowed_intermediate_and_terminal_bounded_hops_v1',
    'chain_ownership': 'table_blob_local_no_sharing_stricter_local_hypothesis_v1',
    'phases': 'all_selected_guards_root_then_target_then_remaining_once_v1',
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
    'positive_decoded_witness': 'one_complete_raw_stream_positive_output_required_v1',
    'reference_projection': 'config_root_bom_uint_bare_guid_prefix_v1',
    'root_selection': 'unique_ascii_folded_literal_root_same_CONFIG_v1',
    'target_selection': 'unique_ascii_folded_projected_guid_same_CONFIG_v1',
    'target_content': 'complete_positive_decoded_content_local_policy_v1',
    'root_document_validation': 'not_performed',
    'root_suffix_validation': 'not_performed',
    'projection_limits': (4194304, 1024, 2048),
    'projection_reservation': 'same_shared_budget_before_parse_no_refund_v1',
    'private_reference_weights': (256, 4, 256),
    'failure_policy': 'poison_chain_and_decoder_no_partial_result_v1'}
RECIPE_DESCRIPTION.update({
    'catalog_projection': 'declared_region_reference_prefix_v1',
    'catalog_target_suffix': 'not_performed',
    'catalog_limits': (4194304, 131072, 64, 16, 64, 256),
    'catalog_reservation': (3, 212992),
    'catalog_candidate': 'unique_nonzero_same_table_nonself_positive_v1',
    'catalog_source_commit': '6af0c0baab11f9d281ad42a3eb2269d5b113cde5'})
RECIPE_DESCRIPTION.update(catalog_name_projection='positional_name_prefix_1_9_1_2_v1',
    catalog_name_limits=(4194304, 131072, 64, 1024, 256),
    catalog_name_reservation=(4, 65536, 131072),
    catalog_name_binding='external_declared_key_and_name_to_verified_owned_xml_v1',
    catalog_name_suffix='not_performed', catalog_embedded_uuid='not_observed')
RECIPE_DESCRIPTION.update(catalog_standard_projection='positional_name_code_description_prefix_v1',
    catalog_standard_limits=(4194304, 131072, 64, 1024, 256, 2147483647),
    catalog_standard_reservation=(4, 131072, 262144),
    catalog_standard_binding='external_key_name_code_description_verified_xml_v1',
    catalog_standard_suffix='not_performed')
del RECIPE_DESCRIPTION['catalog_name_reservation']
RECIPE_DESCRIPTION.update(catalog_embedded_uuid='private_bound_to_declared_key_and_owned_xml_v1',
    catalog_identity_projection='positional_uuid_name_code_description_prefix_v1',
    catalog_identity_limits=(4194304, 131072, 64, 1024, 256, 2147483647),
    catalog_identity_reservation=(4, 131072, 262144),
    catalog_identity_binding='internal_uuid_external_key_name_code_description_verified_xml_v1',
    catalog_identity_suffix='not_performed',
    catalog_uuid_policy='bare_ascii_36_hex_hyphen_nonzero_lowercase_v1')
# Identity supersedes the standard projection; no extra parse or reservation.
for key in ('catalog_standard_projection', 'catalog_standard_limits', 'catalog_standard_reservation',
            'catalog_standard_binding', 'catalog_standard_suffix'):
    del RECIPE_DESCRIPTION[key]
RECIPE_SHA256 = hashlib.sha256(json.dumps(RECIPE_DESCRIPTION, ensure_ascii=True,
    sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
MAX_SLOTS = 4096
MAX_PROJECTION_BYTES = 2048
MAX_CAPTURE_BYTES = 12288
VERDICT = 'config_catalog_identity_binding_observed'
FRAMING_VALIDATION = 'not_accepted'
FILENAME_VALIDATION = 'zero_marker_bounded_utf16le'
LOCATOR_VALIDATION = 'selected_capacity_bounds_only'
PARTNO_VALIDATION = 'selected_canonical_bcd_0_4095'
CHAIN_VALIDATION = 'selected_zero_terminated_exact_stored_length'
TRANSPORT_VALIDATION = 'all_selected_stored_bytes_read'
COMPRESSION_VALIDATION = 'selected_singlepart_ascii_name_rule_raw_deflate_v1'
DECOMPRESSION_VERDICT = 'selected_singlepart_raw_deflate_observed'
MAX_CONTENT_BYTES = 4 * 1024 * 1024
MAX_TOTAL_CONTENT_BYTES = 8 * 1024 * 1024
MAX_INFLATE_CALLS = 4096
MAX_TOTAL_INFLATE_CALLS = 16384
MAX_CHAIN_BYTES = 1024 * 1024
MAX_TOTAL_STORED_BYTES = 4 * 1024 * 1024
MAX_CHAIN_HOPS = 8192
MAX_TOTAL_CHAIN_BLOCKS = 32768
EXTRA_KEYS = {'config_catalog_identity_binding', 'framing_validation', 'reader_validation', 'observation_validation',
    'extraction_validation', 'decompression_validation', 'mapping_validation', 'layout_validation',
    'native_byte_equivalence', 'native_compatibility'}
BINDING_KEYS = metadata.BINDING_KEYS | {'policy_source_sha256', 'framing_reader_source_sha256', 'identity_manifest_sha256'}
DIAGNOSTICS = {key: set(value) for key, value in comparison.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'].update(('missing_table_data_header', 'missing_table_blob_header',
    'config_table_missing', 'config_table_ambiguous', 'config_profile_mismatch',
    'config_empty_data', 'config_reserved_slot', 'config_filename_encoding',
    'config_blob_capacity', 'config_partno_encoding', 'config_reference_no_part_zero_witness',
    'config_chain_no_part_zero_witness', 'config_content_name_policy',
    'config_content_dynamic_name', 'config_content_duplicate_name', 'config_content_nonzero_part',
    'config_content_no_positive_witness', 'config_projection_root_missing',
    'config_projection_target_missing', 'config_projection_target_empty'))
DIAGNOSTICS['structural_rejection'].update(('table_data_header_role', 'table_blob_header_role',
    'config_record_length', 'config_filename_length', 'config_blob_alignment', 'config_reference_bounds',
    'config_chain_failed_attempt', 'config_chain_reference', 'config_chain_cycle', 'config_chain_used',
    'config_chain_next', 'config_chain_length', 'config_content_failed_attempt',
    'config_content_input', 'config_content_invalid_deflate', 'config_content_trailing_data',
    'config_content_truncated_deflate', 'config_content_nonprogress', 'config_projection_prefix'))
DIAGNOSTICS['resource_limit'].update(('config_record_bytes', 'config_slots', 'config_partno_limit',
    'config_chain_bytes', 'config_chain_total_bytes', 'config_chain_hops', 'config_chain_total_hops',
    'config_chain_image_bytes', 'config_content_bytes', 'config_content_total_bytes',
    'config_content_inflate_calls', 'config_content_total_inflate_calls',
    'config_projection_input_bytes', 'config_projection_prefix_bytes', 'config_projection_output_bytes'))
DIAGNOSTICS['unsupported_sharing_policy'].add('config_chain_overlap')



# Dedicated closed staged inventory; earlier modes do not acquire this parser.
from inputs import CONFIG_CATALOG_IDENTITY_SOURCE_FILES as CATALOG_SOURCE_FILES
DIAGNOSTICS['unsupported_layout'].update(('config_catalog_empty',
    'config_catalog_self_reference', 'config_catalog_reference_missing', 'config_catalog_content_empty',
    'config_catalog_owned_count'))
DIAGNOSTICS['structural_rejection'].update(('config_catalog_prefix', 'config_catalog_incomplete'))
DIAGNOSTICS['resource_limit'].update(('config_catalog_limits', 'config_catalog_name_limits'))
DIAGNOSTICS['structural_rejection'].update(('config_catalog_name_prefix', 'config_catalog_identity_prefix', 'config_catalog_standard_mismatch'))
DIAGNOSTICS['resource_limit'].add('config_catalog_identity_limits')
DIAGNOSTICS['structural_rejection'].add('config_catalog_uuid_mismatch')
DIAGNOSTICS['structural_rejection'].update(('config_catalog_manifest', 'config_catalog_key_mismatch',
    'config_catalog_name_mismatch', 'config_catalog_private_projection'))


def validate_owned_projection(value):
    """Readiness gate for known one-Catalog fixture, not general object identity evidence."""
    validate_projection(value)
    require(value['catalog_declared_count'] == value['catalog_resolved_count']
            == value['catalog_positive_count'] == 1)
    return value


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
        'validated_zero_count', 'empty_filenames', 'nonempty_filenames', 'max_filename_units',
        'selected_reference_count', 'reference_excluded_count', 'empty_name_excluded_count',
        'selected_part_zero_count', 'selected_part_nonzero_count',
        'locator_validation', 'partno_validation',
        'framing_validation', 'filename_validation', 'root_identity',
        'completed_chain_count', 'total_stored_bytes_read', 'total_chain_blocks',
        'maximum_chain_hops', 'multi_block_chain_count', 'zero_payload_block_count',
        'chain_validation', 'transport_validation', 'compression_validation', 'file_identity', 'applied_state',
        'plain_entry_count', 'deflate_entry_count', 'positive_decoded_entry_count',
        'plain_content_bytes', 'inflated_content_bytes', 'inflate_call_count',
        'projected_root_count', 'resolved_target_count', 'positive_target_count',
        'reference_validation', 'root_document_validation', 'root_suffix_validation',
        'catalog_collection_count', 'catalog_declared_count', 'catalog_resolved_count',
        'catalog_positive_count', 'catalog_validation', 'catalog_name_count', 'catalog_name_validation',
        'catalog_identity_validation'})
    require(type(value['schema']) is int and value['schema'] == 1)
    for key, expected in (('target', TARGET), ('recipe_id', RECIPE_ID),
            ('recipe_sha256', RECIPE_SHA256), ('framing_validation', FRAMING_VALIDATION),
            ('locator_validation', LOCATOR_VALIDATION), ('partno_validation', PARTNO_VALIDATION),
            ('filename_validation', FILENAME_VALIDATION), ('root_identity', 'not_observed'),
            ('first_marker_class', 'one'), ('chain_validation', CHAIN_VALIDATION),
            ('transport_validation', TRANSPORT_VALIDATION), ('compression_validation', COMPRESSION_VALIDATION),
            ('file_identity', 'not_observed'), ('applied_state', 'not_observed')):
        require(type(value[key]) is str and value[key] == expected)
    require(type(value['candidate_stride']) is int and value['candidate_stride'] == 301
            and integer(value['candidate_slots'], MAX_SLOTS, 2)
            and all(integer(value[key], MAX_SLOTS-1)
                    for key in ('later_zero_count', 'later_one_count', 'later_other_count', 'empty_filenames',
                                'reference_excluded_count', 'empty_name_excluded_count', 'selected_part_nonzero_count'))
            and integer(value['selected_reference_count'], MAX_SLOTS-1, 1)
            and integer(value['selected_part_zero_count'], MAX_SLOTS-1, 1)
            and integer(value['validated_zero_count'], MAX_SLOTS-1, 1)
            and integer(value['nonempty_filenames'], MAX_SLOTS-1, 1)
            and integer(value['max_filename_units'], 128, 1)
            and integer(value['data_logical_bytes'], MAX_FILE_BYTES, 1)
            and integer(value['blob_logical_bytes'], MAX_FILE_BYTES, 512)
            and value['blob_logical_bytes'] % 256 == 0)
    require(value['candidate_slots'] == 1 + value['later_zero_count']
            + value['later_one_count'] + value['later_other_count']
            and value['data_logical_bytes'] == 301 * value['candidate_slots']
            and value['validated_zero_count'] == value['later_zero_count']
            and value['validated_zero_count'] == value['empty_filenames'] + value['nonempty_filenames']
            and value['validated_zero_count'] == value['reference_excluded_count']
                + value['empty_name_excluded_count'] + value['selected_reference_count']
            and value['selected_reference_count'] == value['selected_part_zero_count']
                + value['selected_part_nonzero_count']
            and value['empty_name_excluded_count'] <= value['empty_filenames']
            and value['selected_reference_count'] <= value['nonempty_filenames'])
    require(integer(value['completed_chain_count'], MAX_SLOTS-1, 1)
            and integer(value['total_stored_bytes_read'], MAX_TOTAL_STORED_BYTES, 1)
            and integer(value['total_chain_blocks'], MAX_TOTAL_CHAIN_BLOCKS, 1)
            and integer(value['maximum_chain_hops'], MAX_CHAIN_HOPS, 1)
            and integer(value['multi_block_chain_count'], MAX_SLOTS-1)
            and integer(value['zero_payload_block_count'], MAX_TOTAL_CHAIN_BLOCKS))
    k, d, h, m, q, z = (value[key] for key in ('completed_chain_count', 'total_stored_bytes_read',
        'total_chain_blocks', 'maximum_chain_hops', 'multi_block_chain_count', 'zero_payload_block_count'))
    require(k == value['selected_reference_count'] and k <= h <= value['blob_logical_bytes']//256-1
            and m <= h and q <= k and z <= h-k
            and h-z <= d <= min(MAX_TOTAL_STORED_BYTES, k*MAX_CHAIN_BYTES, 250*(h-z)) and d >= k)
    if q == 0:
        require(h == k and m == 1)
    else:
        require(m >= 2 and k+q+m-2 <= h <= (k-q)+q*m)
    require(integer(value['plain_entry_count'], MAX_SLOTS-1)
            and integer(value['deflate_entry_count'], MAX_SLOTS-1, 1)
            and integer(value['positive_decoded_entry_count'], MAX_SLOTS-1, 1)
            and integer(value['plain_content_bytes'], MAX_TOTAL_STORED_BYTES)
            and integer(value['inflated_content_bytes'], MAX_TOTAL_CONTENT_BYTES, 1)
            and integer(value['inflate_call_count'], MAX_TOTAL_INFLATE_CALLS, 1))
    p, r, v, a, u, c = (value[key] for key in ('plain_entry_count', 'deflate_entry_count',
        'positive_decoded_entry_count', 'plain_content_bytes', 'inflated_content_bytes', 'inflate_call_count'))
    require(k == value['selected_part_zero_count'] and value['selected_part_nonzero_count'] == 0
            and p+r == k and 1 <= v <= r and r <= c <= min(MAX_TOTAL_INFLATE_CALLS, MAX_INFLATE_CALLS*r)
            and (p == 0) == (a == 0) and p <= a <= p*MAX_CHAIN_BYTES
            and r <= d-a <= r*MAX_CHAIN_BYTES
            and v <= u <= v*MAX_CONTENT_BYTES and a+u <= MAX_TOTAL_CONTENT_BYTES)
    for key in ('projected_root_count', 'resolved_target_count', 'positive_target_count'):
        require(type(value[key]) is int and value[key] == 1)
    # Both fixed root and GUID-name target are raw-DEFLATE under this name rule.
    # The shortest admitted prefix is 43 bytes; target content is positive.
    require(k >= 2 and r >= 2 and v >= 2 and u >= 44)
    require(value['reference_validation'] == 'partial_prefix_candidate_same_table'
            and type(value['reference_validation']) is str)
    for key in ('root_document_validation', 'root_suffix_validation'):
        require(type(value[key]) is str and value[key] == 'not_performed')
    require(integer(value['catalog_collection_count'], 64, 1)
            and all(integer(value[key], 256, 1) for key in
                ('catalog_declared_count', 'catalog_resolved_count', 'catalog_positive_count'))
            and value['catalog_declared_count'] == value['catalog_resolved_count'] == value['catalog_positive_count']
            and value['catalog_declared_count'] <= k-2
            and value['catalog_positive_count'] <= v-2
            and type(value['catalog_validation']) is str
            and value['catalog_validation'] == 'declared_references_positive')
    require(type(value['catalog_name_count']) is int and value['catalog_name_count'] == 1
            and type(value['catalog_name_validation']) is str
            and value['catalog_name_validation'] == 'owned_declared_key_name_matched')
    require(type(value['catalog_identity_validation']) is str
            and value['catalog_identity_validation'] == 'owned_uuid_code_description_matched')
    # Aggregate counters cannot prove each assembly, decode or per-entry byte cap. Those
    # facts remain bound to the independently pinned producer and frozen recipe.
    require(len(encode(value)) <= MAX_PROJECTION_BYTES, 'artifact_limit')
    return value


def read_projection(read_at, file_size, *, limits):
    """Invoke bounded private content decoding; no native byte equivalence or file identity."""
    profile = framing.ConfigCatalogIdentityProfile(DECLARATIONS, '0', 0)
    require(profile.identifier == RECIPE_ID and profile.recipe_sha256 == RECIPE_SHA256
            and profile.candidate_stride == 301 and profile.filename_offset == 1
            and profile.filename_width == 258 and profile.binarydata_offset == 287
            and profile.binarydata_width == 8 and profile.partno_offset == 295
            and profile.partno_width == 6, 'provenance_mismatch')
    result = framing.observe_config_catalog_identity(read_at, file_size, profile=profile,
        limits=framing.ConfigFramingLimits(max_slots=MAX_SLOTS, max_record_bytes=4096),
        chain_limits=framing.ConfigBlobChainLimits(),
        content_limits=framing.ConfigContentDecodeLimits(), catalog_limits=limits)
    require(type(result) is framing.ConfigCatalogIdentityObservation
            and result.capability == 'experimental_config_catalog_identity'
            and result.native_acceptance == 'pending', 'unexpected_failure')
    # No arbitrary names, bytes, indices, pointers, native metadata or usage graph.
    projection = {'schema': 1, 'target': result.target,
        'recipe_id': result.recipe_id, 'recipe_sha256': result.recipe_sha256,
        'data_logical_bytes': result.data_logical_bytes, 'blob_logical_bytes': result.blob_logical_bytes,
        'candidate_stride': result.candidate_stride, 'candidate_slots': result.candidate_slots,
        'first_marker_class': result.first_marker_class,
        'later_zero_count': result.later_zero_count, 'later_one_count': result.later_one_count,
        'later_other_count': result.later_other_count,
        'validated_zero_count': result.validated_zero_count,
        'empty_filenames': result.empty_filenames, 'nonempty_filenames': result.nonempty_filenames,
        'max_filename_units': result.max_filename_units,
        'selected_reference_count': result.selected_reference_count,
        'reference_excluded_count': result.reference_excluded_count,
        'empty_name_excluded_count': result.empty_name_excluded_count,
        'selected_part_zero_count': result.selected_part_zero_count,
        'selected_part_nonzero_count': result.selected_part_nonzero_count,
        'locator_validation': result.locator_validation, 'partno_validation': result.partno_validation,
        'framing_validation': result.framing_validation,
        'filename_validation': result.filename_validation, 'root_identity': result.root_identity,
        'completed_chain_count': result.completed_chain_count,
        'total_stored_bytes_read': result.total_stored_bytes_read,
        'total_chain_blocks': result.total_chain_blocks,
        'maximum_chain_hops': result.maximum_chain_hops,
        'multi_block_chain_count': result.multi_block_chain_count,
        'zero_payload_block_count': result.zero_payload_block_count,
        'chain_validation': result.chain_validation, 'transport_validation': result.transport_validation,
        'compression_validation': result.compression_validation,
        'file_identity': result.file_identity, 'applied_state': result.applied_state,
        'plain_entry_count': result.plain_entry_count, 'deflate_entry_count': result.deflate_entry_count,
        'positive_decoded_entry_count': result.positive_decoded_entry_count,
        'plain_content_bytes': result.plain_content_bytes,
        'inflated_content_bytes': result.inflated_content_bytes, 'inflate_call_count': result.inflate_call_count,
        'projected_root_count': result.projected_root_count,
        'resolved_target_count': result.resolved_target_count,
        'positive_target_count': result.positive_target_count,
        'reference_validation': result.reference_validation,
        'root_document_validation': result.root_document_validation,
        'root_suffix_validation': result.root_suffix_validation,
        'catalog_collection_count': result.catalog_collection_count,
        'catalog_declared_count': result.catalog_declared_count,
        'catalog_resolved_count': result.catalog_resolved_count,
        'catalog_positive_count': result.catalog_positive_count,
        'catalog_validation': result.catalog_validation}
    return _PrivateProjection(projection, result.private_fields)


def read_owned_projection(read_at, file_size, *, limits):
    """Frozen native-owned fixture route: exactly one, no supplied expected UUID."""
    private = read_projection(read_at, file_size, limits=limits)
    value = private.projection
    if not (value['catalog_declared_count'] == value['catalog_resolved_count']
            == value['catalog_positive_count'] == 1):
        raise ObservationFailure('unsupported_layout', 'config_catalog_owned_count')
    return private


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, config_catalog_identity_binding=None, framing_validation=FRAMING_VALIDATION,
        reader_validation='not_run', observation_validation='not_run',
        extraction_validation='not_run', decompression_validation='not_run', mapping_validation='not_run', layout_validation='not_run',
        native_byte_equivalence='not_observed', native_compatibility='not_claimed')
    return report


def bind_capture(evidence, report):
    require(type(report.get('schema')) is int and report['schema'] == SCHEMA and report.get('lane') == LANE)
    exact(evidence, {'marker', 'origin', 'postimage', 'reader', 'identity_manifest'})
    require(type(evidence['marker']) is dict and 'token' in evidence['marker'], 'invalid_marker')
    data = metadata.marker(encode(evidence['marker']), nonce=report['nonce'], token=evidence['marker']['token'])
    origin = evidence['origin']
    exact(origin, {'nonce', 'token', 'clone', 'bytes', 'sha256'})
    exact(evidence['postimage'], {'bytes', 'sha256'})
    require(origin['nonce'] == report['nonce'] and origin['token'] == data['token']
            and origin['clone'] == 'auditor', 'snapshot_changed')
    projection = compare_private(evidence['reader'], evidence['identity_manifest'], nonce=report['nonce'])
    capture = {'schema': CAPTURE_SCHEMA, 'status': VERDICT, 'operation': OPERATION,
        'nonce': report['nonce'], 'token': data['token'],
        'source_manifest_sha256': source_binding(report['provenance']),
        'reader_source_sha256': report['provenance']['sources'][READER_SOURCE],
        'policy_source_sha256': report['provenance']['sources'][MODULE_SOURCE],
        'framing_reader_source_sha256': report['provenance']['sources'][FRAMING_READER_SOURCE],
        'identity_manifest_sha256': manifest_digest(evidence['identity_manifest']),
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
    require(digest(capture['identity_manifest_sha256']))
    projection = validate_owned_projection(capture['reader'])
    # Both selected files use disjoint physical ownership on this same image.
    require(projection['data_logical_bytes'] + projection['blob_logical_bytes']
            <= capture['postimage']['bytes'])


def discard_capture(report, failure=None, *, final=False):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA: return
    old = report.get('config_catalog_identity_binding'); report['config_catalog_identity_binding'] = None
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
        report['config_catalog_identity_binding'] = dict(old)
        report['reader_validation'] = report['observation_validation'] = 'failed'
    report['decompression_validation'] = report['observation_validation']


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
    require(report['decompression_validation'] == (DECOMPRESSION_VERDICT
        if report['observation_validation'] == VERDICT else report['observation_validation']))
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(CATALOG_SOURCE_FILES)
            and len(CATALOG_SOURCE_FILES) == 26 and MODULE_SOURCE in CATALOG_SOURCE_FILES
            and FRAMING_READER_SOURCE in CATALOG_SOURCE_FILES, 'provenance_mismatch')
    require(provenance['image'] == lifecycle.IMAGE and provenance['platform'] == 'linux/amd64'
            and provenance['locale'] == 'ru_RU.UTF-8' and provenance['timezone'] == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] not in ('catalog_comparison_failed', metadata.FAILURE_KIND, 'record_readback_failed', 'params_observation_failed', 'params_extraction_failed',
        'dbnames_identity_failed', 'config_observation_failed', 'config_framing_failed',
        'config_marker_census_failed', 'config_zero_marker_filename_failed', 'config_entry_reference_failed', 'config_blob_chain_failed',
        'config_content_decode_failed', 'config_root_reference_failed', 'config_root_diagnostic_failed', 'config_catalog_observation_failed', 'config_catalog_name_binding_failed'))
    if report['failure_kind'] == FAILURE_KIND:
        require(report['failed_stage'] == 'baseline'); base['failure_kind'] = 'logical_mismatch'
    if 'failure_context' in report:
        base['failure_context'] = metadata._mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['config_catalog_identity_binding']
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


@dataclass(frozen=True)
class _IdentityManifest:
    """Private verified-redump facts; never serialize this object into a report."""
    nonce: str
    expected_sources_sha256: str
    catalog_sha256: str
    key: str
    name: str
    code_length: int
    code_type: int
    description_length: int


@dataclass(frozen=True)
class _PrivateProjection:
    projection: dict
    names: tuple


def _manifest_failure():
    return ObservationFailure('structural_rejection', 'config_catalog_manifest')


def validate_manifest(value, *, nonce):
    if (type(value) is not _IdentityManifest or value.nonce != nonce
            or type(nonce) is not str or re.fullmatch('[0-9a-f]{32}', nonce) is None
            or not digest(value.expected_sources_sha256) or not digest(value.catalog_sha256)
            or type(value.key) is not str
            or re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value.key) is None
            or value.key == '00000000-0000-0000-0000-000000000000'
            or type(value.name) is not str or not 1 <= len(value.name) <= 256
            or any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
                   or ord(char) == 0xFEFF for char in value.name)
            or len(value.name.encode('utf-8')) > 1024
            or type(value.code_length) is not int or not 0 <= value.code_length <= 2147483647
            or type(value.description_length) is not int or not 0 <= value.description_length <= 2147483647
            or type(value.code_type) is not int or value.code_type not in (0, 1)):
        raise _manifest_failure()
    return value


def manifest_digest(value):
    validate_manifest(value, nonce=value.nonce if type(value) is _IdentityManifest else None)
    return hashlib.sha256(encode({'nonce': value.nonce,
        'expected_sources_sha256': value.expected_sources_sha256,
        'catalog_sha256': value.catalog_sha256, 'key': value.key, 'name': value.name,
        'code_length': value.code_length, 'code_type': value.code_type,
        'description_length': value.description_length})).hexdigest()


def build_identity_manifest(expected, actual, *, nonce, version):
    """Only after successful native verify_redump; no new native command.

    Independently read expected and actual namespace-qualified direct Catalog
    paths. Verify canonical whole XML, source-tree stability and version1. Raw
    UUID/name/standard fields remain private and never reach the positional parser.
    """
    from inject_metadata import NS, FORMAT, _hashes, _inventory, _canonical, read_xml, DraftError
    if type(version) is not int or version != 1:
        raise _manifest_failure()
    ns = '{' + NS + '}'

    def identity(root):
        if root.tag != ns+'MetaDataObject' or root.attrib != {'version': FORMAT} or len(root) != 1:
            raise _manifest_failure()
        catalog = root[0]
        if catalog.tag != ns+'Catalog' or set(catalog.attrib) != {'uuid'}:
            raise _manifest_failure()
        properties = [child for child in catalog if child.tag == ns+'Properties']
        if len(properties) != 1:
            raise _manifest_failure()
        selected_tags = {'Name', 'CodeLength', 'CodeType', 'DescriptionLength'}
        if any(child.tag.rsplit('}', 1)[-1] in selected_tags
               and child.tag not in {ns+tag for tag in selected_tags} for child in properties[0]):
            raise _manifest_failure()
        names = [child for child in properties[0] if child.tag == ns+'Name']
        if len(names) != 1 or names[0].attrib or len(names[0]) or type(names[0].text) is not str:
            raise _manifest_failure()
        key = catalog.attrib['uuid']
        if type(key) is not str:
            raise _manifest_failure()
        def scalar(tag):
            nodes = [child for child in properties[0] if child.tag == ns+tag]
            if len(nodes) != 1 or nodes[0].attrib or len(nodes[0]) or type(nodes[0].text) is not str:
                raise _manifest_failure()
            return nodes[0].text

        def length(tag):
            text = scalar(tag)
            if re.fullmatch(r'0|[1-9][0-9]{0,9}', text) is None:
                raise _manifest_failure()
            value = int(text)
            if value > 2147483647:
                raise _manifest_failure()
            return value

        kind = scalar('CodeType')
        if kind not in ('Number', 'String'):
            raise _manifest_failure()
        return (key.lower(), names[0].text, length('CodeLength'),
                0 if kind == 'Number' else 1, length('DescriptionLength'))

    try:
        before = _hashes(expected)
        _inventory(actual)
        _, expected_xml = read_xml(expected/'Catalogs/NativeOracleItems.xml')
        _, actual_xml = read_xml(actual/'Catalogs/NativeOracleItems.xml')
        expected_identity, actual_identity = identity(expected_xml), identity(actual_xml)
        canonical = _canonical(actual_xml)
        if (expected_identity != actual_identity or canonical != _canonical(expected_xml)
                or before != _hashes(expected)):
            raise _manifest_failure()
        manifest = _IdentityManifest(nonce,
            hashlib.sha256(encode(dict(sorted(before.items())))).hexdigest(),
            hashlib.sha256(encode(canonical)).hexdigest(), *actual_identity)
        return validate_manifest(manifest, nonce=nonce)
    except (DraftError, ValueError, OSError):
        raise _manifest_failure() from None


def compare_private(private, manifest, *, nonce):
    """Expectation-free reader completes first; compare only its private result."""
    validate_manifest(manifest, nonce=nonce)
    if (type(private) is not _PrivateProjection or type(private.names) is not tuple
            or len(private.names) != 1 or type(private.names[0]) is not tuple
            or len(private.names[0]) != 2 or type(private.projection) is not dict):
        raise ObservationFailure('structural_rejection', 'config_catalog_private_projection')
    import config_catalog_name as standard_parser
    key, fields = private.names[0]
    if type(fields) is not standard_parser.CatalogIdentityPrefix:
        raise ObservationFailure('structural_rejection', 'config_catalog_private_projection')
    name = fields.name
    if type(fields.metadata_uuid) is not str or fields.metadata_uuid != key:
        raise ObservationFailure('structural_rejection', 'config_catalog_uuid_mismatch')
    if type(key) is not str or key != manifest.key:
        raise ObservationFailure('structural_rejection', 'config_catalog_key_mismatch')
    if type(name) is not str or name != manifest.name:
        raise ObservationFailure('structural_rejection', 'config_catalog_name_mismatch')
    if (type(fields.code_length) is not int or type(fields.code_type) is not int
            or type(fields.description_length) is not int
            or (fields.code_length, fields.code_type, fields.description_length)
                != (manifest.code_length, manifest.code_type, manifest.description_length)):
        raise ObservationFailure('structural_rejection', 'config_catalog_standard_mismatch')
    projection = dict(private.projection)
    projection.update(catalog_name_count=1, catalog_name_validation='owned_declared_key_name_matched',
        catalog_identity_validation='owned_uuid_code_description_matched')
    return validate_owned_projection(projection)
