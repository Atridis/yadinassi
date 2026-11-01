"""Bounded CONFIG transport for the single-Catalog offline runtime reader.

Extracted from the accepted owned-profile observer. All-selected entry decoding,
resource charges, partial grammar and closed layout admission remain unchanged.
This does not establish applied configuration state or live-file consistency.
Historical observation protocols keep their separate source-pinned implementation.
"""
from __future__ import annotations
from dataclasses import dataclass, field, fields as _dataclass_fields
import hashlib
import json
from .filedb_catalog import (CatalogLimits, CatalogReader, CatalogUsage,
                            InvalidStructure, ResourceLimit, UnsupportedLayout,
                            UnsupportedSharing)
from . import config_catalog_attributes as attribute_projector


DECLARATIONS = (
    ('FILENAME', 'NVC', 0, 128, 0, 'CI'),
    ('CREATION', 'DT', 0, 0, 0, 'CS'),
    ('MODIFIED', 'DT', 0, 0, 0, 'CS'),
    ('ATTRIBUTES', 'N', 0, 5, 0, 'CS'),
    ('DATASIZE', 'N', 0, 20, 0, 'CS'),
    ('BINARYDATA', 'I', 0, 0, 0, 'CS'),
    ('PARTNO', 'N', 0, 10, 0, 'CS'),
)

@dataclass(frozen=True)
class ConfigFramingProfile:
    """Required exact declarations/lock/format, not inferred from source data."""

    declarations: tuple[tuple[str, str, int, int, int, str], ...]
    recordlock: str
    format_item: int
    identifier: str = field(default='config_framing_8380_8192_v1', init=False)
    record_size: int = field(init=False)
    placements: tuple[tuple[int, int], ...] = field(init=False)
    recipe_sha256: str = field(init=False)

    def __post_init__(self):
        if type(self.recordlock) is not str or self.recordlock != '0':
            raise ValueError('CONFIG framing requires explicit recordlock zero')
        if type(self.format_item) is not int or self.format_item != 0:
            raise ValueError('CONFIG framing requires explicit integer-zero format')
        if type(self.declarations) is not tuple or len(self.declarations) != 7:
            raise ValueError('invalid CONFIG framing declarations')
        for item in self.declarations:
            if (type(item) is not tuple or len(item) != 6 or any(type(v) is not t
                    for v, t in zip(item, (str, str, int, int, int, str)))):
                raise ValueError('invalid CONFIG framing declaration primitive')
        if self.declarations != DECLARATIONS:
            raise ValueError('unsupported CONFIG framing declarations')
        widths = (2 + 2 * 128, 7, 7, (5 + 2) // 2, (20 + 2) // 2, 8, (10 + 2) // 2)
        cursor, placements = 1, []
        for width in widths:
            placements.append((cursor, width))
            cursor += width
        object.__setattr__(self, 'record_size', cursor)
        object.__setattr__(self, 'placements', tuple(placements))
        raw = json.dumps(self.recipe(), ensure_ascii=True, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('ascii')
        object.__setattr__(self, 'recipe_sha256', hashlib.sha256(raw).hexdigest())

    def recipe(self):
        """New fixed structure each time; no mutable shared profile state."""
        return {'identifier': self.identifier, 'declarations': self.declarations,
                'recordlock': self.recordlock, 'format_item': self.format_item,
                'record_size': self.record_size, 'placements': self.placements,
                'framing': 'reserved_one_remaining_zero_no_hidden_version_v1',
                'filename': 'u16le_units_at_most_128_strict_utf16le_v1',
                'selection': 'CONFIG_ascii_case_only_no_fallback_v1',
                'empty_data': 'unsupported', 'reserved_only': 'admitted'}

@dataclass(frozen=True)
class ConfigFramingLimits:
    """Policy ceilings may be lowered, never widened."""

    max_slots: int = 4096
    max_record_bytes: int = 4096

    def __post_init__(self):
        for value in (self.max_slots, self.max_record_bytes):
            if type(value) is not int or not 1 <= value <= 4096:
                raise ValueError('invalid CONFIG framing limit')

def _ascii_config(value):
    return len(value) == 6 and all(a == b or (97 <= ord(a) <= 122 and chr(ord(a)-32) == b)
                                  for a, b in zip(value, 'CONFIG'))

def _scalar(data, offset, length):
    data._validate_range(offset, length)
    # Logical callback, bytearray assembly and immutable copy reserved first.
    data._source.budget.charge('output_bytes', 3 * length)
    data._source.budget.charge('bytes_processed', length)
    return data._read_range(offset, length)

def _config_partno(raw):
    """Canonical bounded numeric hypothesis, deliberately not native ToIntDef."""
    if len(raw) != 6 or raw[0] >> 4 != 1 or raw[-1] & 15:
        raise UnsupportedLayout('config_partno_encoding')
    value = 0
    for index in range(1, 11):
        digit = (raw[index // 2] >> (4 if index % 2 == 0 else 0)) & 15
        if digit > 9:
            raise UnsupportedLayout('config_partno_encoding')
        value = value * 10 + digit
    if value > 4095:
        raise ResourceLimit('config_partno_limit')
    return value

@dataclass(frozen=True)
class ConfigEntryReferenceProfile:
    """Bounded selected-reference prerequisites, not a file or chain reader."""

    declarations: tuple[tuple[str, str, int, int, int, str], ...]
    recordlock: str
    format_item: int
    identifier: str = field(default='config_entry_reference_8380_8192_v1', init=False)
    candidate_stride: int = field(init=False)
    filename_offset: int = field(init=False)
    filename_width: int = field(init=False)
    binarydata_offset: int = field(init=False)
    binarydata_width: int = field(init=False)
    partno_offset: int = field(init=False)
    partno_width: int = field(init=False)
    recipe_sha256: str = field(init=False)

    def __post_init__(self):
        layout = ConfigFramingProfile(self.declarations, self.recordlock, self.format_item)
        object.__setattr__(self, 'candidate_stride', layout.record_size)
        object.__setattr__(self, 'filename_offset', layout.placements[0][0])
        object.__setattr__(self, 'filename_width', layout.placements[0][1])
        object.__setattr__(self, 'binarydata_offset', layout.placements[5][0])
        object.__setattr__(self, 'binarydata_width', layout.placements[5][1])
        object.__setattr__(self, 'partno_offset', layout.placements[6][0])
        object.__setattr__(self, 'partno_width', layout.placements[6][1])
        raw = json.dumps(self.recipe(), ensure_ascii=True, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('ascii')
        object.__setattr__(self, 'recipe_sha256', hashlib.sha256(raw).hexdigest())

    def recipe(self):
        return {'identifier': self.identifier, 'declarations': self.declarations,
                'recordlock': self.recordlock, 'format_item': self.format_item,
                'candidate_stride': self.candidate_stride,
                'filename_offset': self.filename_offset, 'filename_width': self.filename_width,
                'first_marker': 'one_reserved_opaque_v1',
                'later_selection': 'zero_validate_nonzero_opaque_v1',
                'filename': 'u16le_units_at_most_128_strict_utf16le_v1',
                'selection': 'CONFIG_ascii_case_only_no_fallback_v1',
                'binarydata_offset': self.binarydata_offset, 'binarydata_width': self.binarydata_width,
                'partno_offset': self.partno_offset, 'partno_width': self.partno_width,
                'reference': 'u32le_start_length_both_positive_nonempty_name_v1',
                'locator': 'aligned_256_start_in_range_length_at_most_250_capacity_v1',
                'partno': 'positive_sign1_ten_decimal_digits_pad0_at_most_4095_v1',
                'empty_data': 'unsupported', 'selected_part_zero_witness': 'required',
                'framing': 'not_accepted'}

@dataclass(frozen=True)
class ConfigEntryReferenceObservation:
    recipe_id: str
    recipe_sha256: str
    data_logical_bytes: int
    blob_logical_bytes: int
    candidate_slots: int
    first_marker_class: str
    later_zero_count: int
    later_one_count: int
    later_other_count: int
    validated_zero_count: int
    empty_filenames: int
    nonempty_filenames: int
    max_filename_units: int
    selected_reference_count: int
    reference_excluded_count: int
    empty_name_excluded_count: int
    selected_part_zero_count: int
    selected_part_nonzero_count: int
    usage: CatalogUsage
    candidate_stride: int = field(default=301, init=False)
    target: str = field(default='CONFIG', init=False)
    capability: str = field(default='experimental_config_entry_reference', init=False)
    framing_validation: str = field(default='not_accepted', init=False)
    filename_validation: str = field(default='zero_marker_bounded_utf16le', init=False)
    locator_validation: str = field(default='selected_capacity_bounds_only', init=False)
    partno_validation: str = field(default='selected_canonical_bcd_0_4095', init=False)
    root_identity: str = field(default='not_observed', init=False)
    native_acceptance: str = field(default='pending', init=False)

@dataclass(frozen=True)
class ConfigBlobChainProfile(ConfigEntryReferenceProfile):
    """Exact transport hypothesis, not file assembly or native byte equivalence."""

    identifier: str = field(default='config_blob_chain_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update({
            'source_commit': 'd5e31816f4c9b11a445f73fc92d08803840ce599',
            'chain_header': 'block256_next_u32le_at0_used_u16le_at4_payload_at6_v1',
            'chain_termination': 'follow_until_zero_even_after_declared_length_v1',
            'chain_length': 'exact_stored_length_stricter_local_hypothesis_v1',
            'zero_used': 'allowed_intermediate_and_terminal_bounded_hops_v1',
            'chain_ownership': 'table_blob_local_no_sharing_stricter_local_hypothesis_v1',
            'phases': 'all_entry_prerequisites_then_all_selected_chains_v1',
            'assembly': 'one_private_fixed_buffer_and_returned_copy_no_export_v1',
            'chain_limits': (1048576, 4194304, 8192, 32768),
            'shared_limits': (100000, 67108864, 134217728, 100000, 1048576,
                1048576, 16777216, 4096, 65536, 262144, 64, 65536, 20,
                262144, 33554432),
            'budget_policy': 'intersect_remaining_shared_no_reset_refund_or_raise_v1',
            'representation_weights': (192, 2, 128, 128, 3, 128),
            'image_bytes_ceiling': 67108864,
            'selected_part_zero_witness': 'completely_read_positive_stored_chain_required',
            'compression': 'not_classified', 'file_assembly': 'not_run',
            'root_identity': 'not_observed', 'applied_state': 'not_observed',
        })
        return result

@dataclass(frozen=True)
class ConfigBlobChainLimits:
    """Additional conjunctive gates; never replace the shared catalog budgets."""

    max_chain_bytes: int = 1048576
    max_total_bytes: int = 4194304
    max_chain_hops: int = 8192
    max_total_hops: int = 32768

    def __post_init__(self):
        for name, ceiling in (('max_chain_bytes', 1048576), ('max_total_bytes', 4194304),
                              ('max_chain_hops', 8192), ('max_total_hops', 32768)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError('invalid CONFIG chain limit')

@dataclass(frozen=True)
class ConfigBlobChainObservation(ConfigEntryReferenceObservation):
    completed_chain_count: int
    total_stored_bytes_read: int
    total_chain_blocks: int
    maximum_chain_hops: int
    multi_block_chain_count: int
    zero_payload_block_count: int
    capability: str = field(default='experimental_config_blob_chain', init=False)
    chain_validation: str = field(default='selected_zero_terminated_exact_stored_length', init=False)
    transport_validation: str = field(default='all_selected_stored_bytes_read', init=False)
    compression_validation: str = field(default='not_classified', init=False)
    file_identity: str = field(default='not_observed', init=False)
    applied_state: str = field(default='not_observed', init=False)

class _ConfigBlobChains:
    """Single-attempt private exact stored-byte primitive on one opened mapping.

    Root-catalog logical block numbers do not participate in this owner set.
    Failure poisons this primitive; charges and ownership are never refunded.
    The returned private bytes are for internal consumers, not observation output.
    """

    def __init__(self, blob, limits):
        if type(limits) is not ConfigBlobChainLimits:
            raise ValueError('chain_limits must be ConfigBlobChainLimits')
        if blob.info.logical_length % 256:
            raise InvalidStructure('config_blob_alignment')
        self.blocks = blob.info.logical_length // 256
        if self.blocks < 2:
            raise UnsupportedLayout('config_blob_capacity')
        self.blob, self.limits = blob, limits
        self.budget = blob._source.budget
        self.budget.charge('output_bytes', 512)
        self.owners = set()
        self.total_bytes = self.total_hops = 0
        self.failed = False

    def read(self, start, length):
        if self.failed:
            raise InvalidStructure('config_chain_failed_attempt')
        # Set before any check/allocation/read: a failed read cannot be retried.
        self.failed = True
        if (type(start) is not int or type(length) is not int or
                not 1 <= start < self.blocks or length < 1):
            raise InvalidStructure('config_chain_reference')
        if length > self.limits.max_chain_bytes:
            raise ResourceLimit('config_chain_bytes')
        if length > self.limits.max_total_bytes - self.total_bytes:
            raise ResourceLimit('config_chain_total_bytes')
        self.total_bytes += length
        self.budget.charge('total_blob_bytes', length)
        # Both the fixed assembly and eventual immutable result are reserved.
        self.budget.charge('output_bytes', 2 * length + 256)
        self.budget.charge('bytes_processed', 2 * length)
        output = bytearray(length)
        visited = set()
        current, written, hops, zero_used = start, 0, 0, 0
        while current:
            if type(current) is not int or not 1 <= current < self.blocks:
                raise InvalidStructure('config_chain_reference')
            if hops == self.limits.max_chain_hops:
                raise ResourceLimit('config_chain_hops')
            if self.total_hops == self.limits.max_total_hops:
                raise ResourceLimit('config_chain_total_hops')
            hops += 1
            self.total_hops += 1
            self.budget.charge('blob_visits', 1)
            self.budget.charge('bytes_processed', 1)
            if current in visited:
                raise InvalidStructure('config_chain_cycle')
            if current in self.owners:
                raise UnsupportedSharing('config_chain_overlap')
            self.budget.charge('output_bytes', 128)
            visited.add(current)
            self.budget.charge('output_bytes', 128)
            self.owners.add(current)
            header = _scalar(self.blob, 256 * current, 6)
            self.budget.charge('output_bytes', 128)
            self.budget.charge('bytes_processed', 6)
            following = int.from_bytes(header[:4], 'little')
            used = int.from_bytes(header[4:6], 'little')
            if used > 250:
                raise InvalidStructure('config_chain_used')
            if following and not 1 <= following < self.blocks:
                raise InvalidStructure('config_chain_next')
            if used > length - written:
                raise InvalidStructure('config_chain_length')
            if used:
                payload = _scalar(self.blob, 256 * current + 6, used)
                output[written:written + used] = payload
                del payload
            else:
                zero_used += 1
            written += used
            # Reaching the declared length does NOT terminate traversal.
            current = following
        if written != length:
            raise InvalidStructure('config_chain_length')
        result = bytes(output)
        self.failed = False
        return result, hops, zero_used

@dataclass(frozen=True)
class ConfigContentDecodeProfile(ConfigBlobChainProfile):
    """Narrow source-informed classification, not native file identity/equivalence."""

    identifier: str = field(default='config_content_decode_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update({
            'phases': 'all_selected_name_part_guards_then_exact_chain_content_v1',
            'selected_name': 'printable_ascii_1_128_units_ascii_fold_unique_v1',
            'selected_parts': 'every_selected_part_zero_required_v1',
            'dynamic_names': 'reject_final_new_and_any_ascii_fold_dynupdate_marker_v1',
            'plain_names': ('dynamicallyupdated', 'sprscndinfo', 'dbnamesversion', 'siversions'),
            'plain_patterns': 'leading_left_brace_or_fo_version_substring_or_final_inf_pf_v1',
            'compression': 'selected_singlepart_ascii_name_rule_raw_deflate_v1',
            'inflate': 'raw_minus15_eof_full_consumption_no_flush_no_fallback_v1',
            'content_limits': (4194304, 8388608, 4096, 16384),
            'inflate_chunks': (32768, 65536),
            # New key/tuple base replaces the old reference-only 192 weight.
            'representation_weights': (512, 2, 128, 128, 3, 128),
            'content_weights': (512, 8, 4, 256, 131072, 2, 2),
            'inflate_output_probe': 'min_chunk_remaining_plus_one_strictly_positive_v1',
            'content_assembly': 'plain_alias_or_reserved_final_immutable_decoded_copy_v1',
            'content_budget': 'identical_chain_budget_cumulative_poison_on_failure_v1',
            'positive_decoded_witness': 'one_complete_raw_stream_positive_output_required_v1',
        })
        return result

@dataclass(frozen=True)
class ConfigContentDecodeLimits:
    """Conjunctive local ceilings, not native content maxima or new allowances."""

    max_content_bytes: int = 4194304
    max_total_content_bytes: int = 8388608
    max_inflate_calls: int = 4096
    max_total_inflate_calls: int = 16384

    def __post_init__(self):
        for name, ceiling in (('max_content_bytes', 4194304),
                ('max_total_content_bytes', 8388608), ('max_inflate_calls', 4096),
                ('max_total_inflate_calls', 16384)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError('invalid CONFIG content limit')

@dataclass(frozen=True)
class ConfigContentDecodeObservation(ConfigBlobChainObservation):
    plain_entry_count: int
    deflate_entry_count: int
    positive_decoded_entry_count: int
    plain_content_bytes: int
    inflated_content_bytes: int
    inflate_call_count: int
    capability: str = field(default='experimental_config_content_decode', init=False)
    compression_validation: str = field(
        default='selected_singlepart_ascii_name_rule_raw_deflate_v1', init=False)

def _config_content_name(name, units, budget, keys):
    """Private ASCII key/class only; no path operations, trimming or normalization."""
    budget.charge('output_bytes', 512 + 8 * units)
    budget.charge('bytes_processed', 4 * units)
    if not 1 <= units <= 128 or len(name) != units or any(not 32 <= ord(c) <= 126 for c in name):
        raise UnsupportedLayout('config_content_name_policy')
    key = ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in name)
    extension = key.rpartition('.')[2] if '.' in key else ''
    if extension == 'new' or '_dynupdate_' in key:
        raise UnsupportedLayout('config_content_dynamic_name')
    if key in keys:
        raise UnsupportedLayout('config_content_duplicate_name')
    keys.add(key)
    if key in ('dynamicallyupdated', 'sprscndinfo', 'dbnamesversion', 'siversions'):
        return 'plain'
    if key.startswith('{') or 'fo_version' in key or extension in ('inf', 'pf'):
        return 'plain'
    return 'raw_deflate'

class _ConfigContentDecoder:
    """Single operation's bounded content seam on the identical chain budget.

    Failed decode poisons both this context and its chain primitive, even though
    the exact stored-byte read completed. Counters/charges are never refunded.
    Private buffers are never exposed by the public observer or its policy.
    """

    def __init__(self, chains, limits):
        if type(chains) is not _ConfigBlobChains:
            raise ValueError('chains must be _ConfigBlobChains')
        if type(limits) is not ConfigContentDecodeLimits:
            raise ValueError('content_limits must be ConfigContentDecodeLimits')
        self.chains, self.limits, self.budget = chains, limits, chains.budget
        self.budget.charge('output_bytes', 256)
        self.total_content_bytes = self.total_calls = 0
        self.failed = False

    def _remaining(self, produced):
        return min(self.limits.max_content_bytes - produced,
                   self.limits.max_total_content_bytes - self.total_content_bytes)

    def _accept(self, length, produced):
        if length > self.limits.max_content_bytes - produced:
            raise ResourceLimit('config_content_bytes')
        if length > self.limits.max_total_content_bytes - self.total_content_bytes:
            raise ResourceLimit('config_content_total_bytes')
        self.total_content_bytes += length

    def decode(self, stored, content_class):
        if self.failed or self.chains.failed:
            raise InvalidStructure('config_content_failed_attempt')
        self.failed = self.chains.failed = True
        if (type(stored) is not bytes or not stored or type(content_class) is not str
                or content_class not in ('plain', 'raw_deflate')):
            raise InvalidStructure('config_content_input')
        if content_class == 'plain':
            self._accept(len(stored), 0)
            result = stored  # Borrow the already reserved immutable chain buffer.
        else:
            result = self._inflate(stored)
        self.failed = self.chains.failed = False
        return result

    def _inflate(self, stored):
        # Import is lazy: earlier observation modes acquire no eager zlib import.
        # This weight is an explicit policy, not a native-zlib heap measurement.
        self.budget.charge('output_bytes', 131072)
        import zlib
        try:
            decoder = zlib.decompressobj(wbits=-15)
        except zlib.error:
            raise InvalidStructure('config_content_invalid_deflate') from None
        output = bytearray()
        cursor = produced = calls = 0
        pending = b''
        while True:
            if not pending and cursor < len(stored):
                end = min(cursor + 32768, len(stored))
                self.budget.charge('output_bytes', end - cursor)
                self.budget.charge('bytes_processed', end - cursor)
                pending = stored[cursor:end]
                cursor = end
            if calls == self.limits.max_inflate_calls:
                raise ResourceLimit('config_content_inflate_calls')
            if self.total_calls == self.limits.max_total_inflate_calls:
                raise ResourceLimit('config_content_total_inflate_calls')
            calls += 1
            self.total_calls += 1
            maximum = min(65536, self._remaining(produced) + 1)
            # Nonnegative remaining follows only from _accept; never max_length=0.
            self.budget.charge('output_bytes', 2 * maximum + 2 * len(pending))
            self.budget.charge('bytes_processed', len(pending) + maximum)
            before = len(pending)
            try:
                chunk = decoder.decompress(pending, max_length=maximum)
            except zlib.error:
                raise InvalidStructure('config_content_invalid_deflate') from None
            self._accept(len(chunk), produced)
            produced += len(chunk)
            output.extend(chunk)
            consumed = before - len(decoder.unconsumed_tail)
            pending = decoder.unconsumed_tail
            if decoder.eof:
                if decoder.unused_data or pending or cursor != len(stored):
                    raise InvalidStructure('config_content_trailing_data')
                break
            if not chunk and consumed == 0:
                if not pending and cursor == len(stored):
                    raise InvalidStructure('config_content_truncated_deflate')
                raise InvalidStructure('config_content_nonprogress')
            del chunk
        self.budget.charge('output_bytes', produced)
        self.budget.charge('bytes_processed', produced)
        return bytes(output)

@dataclass(frozen=True)
class ConfigRootReferenceProjectionProfile(ConfigContentDecodeProfile):
    identifier: str = field(default='config_root_reference_projection_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update({
            'phases': 'all_selected_guards_root_then_target_then_remaining_once_v1',
            'reference_projection': 'config_root_bom_uint_bare_guid_prefix_v1',
            'root_selection': 'unique_ascii_folded_literal_root_same_CONFIG_v1',
            'target_selection': 'unique_ascii_folded_projected_guid_same_CONFIG_v1',
            'target_content': 'complete_positive_decoded_content_local_policy_v1',
            'root_document_validation': 'not_performed',
            'root_suffix_validation': 'not_performed',
            'projection_limits': (4194304, 1024, 2048),
            'projection_reservation': 'same_shared_budget_before_parse_no_refund_v1',
            'private_reference_weights': (256, 4, 256),
            'failure_policy': 'poison_chain_and_decoder_no_partial_result_v1',
        })
        return result

@dataclass(frozen=True)
class ConfigRootReferenceProjectionObservation(ConfigContentDecodeObservation):
    projected_root_count: int
    resolved_target_count: int
    positive_target_count: int
    capability: str = field(default='experimental_config_root_reference_projection', init=False)
    reference_validation: str = field(default='partial_prefix_candidate_same_table', init=False)
    root_document_validation: str = field(default='not_performed', init=False)
    root_suffix_validation: str = field(default='not_performed', init=False)

@dataclass(frozen=True)
class ConfigCatalogReferenceProfile(ConfigRootReferenceProjectionProfile):
    identifier: str = field(default='config_catalog_references_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update({
            'catalog_projection': 'declared_region_reference_prefix_v1',
            'catalog_target_suffix': 'not_performed',
            'catalog_limits': (4194304, 131072, 64, 16, 64, 256),
            'catalog_reservation': (3, 212992),
            'catalog_candidate': 'unique_nonzero_same_table_nonself_positive_v1',
            'catalog_source_commit': '6af0c0baab11f9d281ad42a3eb2269d5b113cde5',
        })
        return result

@dataclass(frozen=True)
class ConfigCatalogReferenceObservation(ConfigRootReferenceProjectionObservation):
    catalog_collection_count: int
    catalog_declared_count: int
    catalog_resolved_count: int
    catalog_positive_count: int
    capability: str = field(default='experimental_config_catalog_references', init=False)
    catalog_validation: str = field(default='declared_references_positive', init=False)

@dataclass(frozen=True)
class ConfigCatalogNameProfile(ConfigCatalogReferenceProfile):
    identifier: str = field(default='config_catalog_names_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update(catalog_name_projection='positional_name_prefix_1_9_1_2_v1',
            catalog_name_limits=(4194304, 131072, 64, 1024, 256),
            catalog_name_reservation=(4, 65536, 131072),
            catalog_name_binding='external_declared_key_and_name_to_verified_owned_xml_v1',
            catalog_name_suffix='not_performed', catalog_embedded_uuid='not_observed')
        return result

@dataclass(frozen=True)
class ConfigCatalogNameObservation(ConfigCatalogReferenceObservation):
    private_names: tuple[tuple[str, str], ...]
    capability: str = field(default='experimental_config_catalog_names', init=False)

@dataclass(frozen=True)
class ConfigCatalogStandardProfile(ConfigCatalogNameProfile):
    identifier: str = field(default='config_catalog_standard_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update(catalog_standard_projection='positional_name_code_description_prefix_v1',
            catalog_standard_limits=(4194304, 131072, 64, 1024, 256, 2147483647),
            catalog_standard_reservation=(4, 131072, 262144),
            catalog_standard_binding='external_key_name_code_description_verified_xml_v1',
            catalog_standard_suffix='not_performed')
        # The standard parser includes Name in one pass, not a second Name parse.
        del result['catalog_name_reservation']
        return result

@dataclass(frozen=True)
class ConfigCatalogStandardObservation(ConfigCatalogReferenceObservation):
    private_fields: tuple
    capability: str = field(default='experimental_config_catalog_standard', init=False)

@dataclass(frozen=True)
class ConfigCatalogIdentityProfile(ConfigCatalogStandardProfile):
    identifier: str = field(default='config_catalog_identity_8380_8192_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update(catalog_embedded_uuid='private_bound_to_declared_key_and_owned_xml_v1',
            catalog_identity_projection='positional_uuid_name_code_description_prefix_v1',
            catalog_identity_limits=(4194304, 131072, 64, 1024, 256, 2147483647),
            catalog_identity_reservation=(4, 131072, 262144),
            catalog_identity_binding='internal_uuid_external_key_name_code_description_verified_xml_v1',
            catalog_identity_suffix='not_performed',
            catalog_uuid_policy='bare_ascii_36_hex_hyphen_nonzero_lowercase_v1')
        for key in ('catalog_standard_projection', 'catalog_standard_limits', 'catalog_standard_reservation',
                    'catalog_standard_binding', 'catalog_standard_suffix'):
            del result[key]
        return result

@dataclass(frozen=True)
class ConfigCatalogIdentityObservation(ConfigCatalogReferenceObservation):
    private_fields: tuple
    capability: str = field(default='experimental_config_catalog_identity', init=False)

@dataclass(frozen=True)
class ConfigCatalogAttributeProfile(ConfigCatalogIdentityProfile):
    identifier: str = field(default='config_catalog_attribute_reader_v1', init=False)

    def recipe(self):
        result = super().recipe()
        result.update(catalog_attribute_projection='config_catalog_attributes_single_primitive_v1',
            catalog_attribute_limits=(4194304, 131072, 64, 1024, 256, 64, 2147483647),
            catalog_attribute_reservation=(8, 262144),
            catalog_attribute_traversal='same_decoded_bytes_two_parsers_shared_budget_v1',
            catalog_attribute_binding='complete_collections_uuid_name_type_verified_xml_v1')
        return result

@dataclass(frozen=True)
class ConfigCatalogAttributeObservation(ConfigCatalogReferenceObservation):
    private_fields: tuple
    capability: str = field(default='experimental_config_catalog_attributes', init=False)

def load_catalog_attribute_projector():
    return attribute_projector


def _observe_catalog_attributes_from_graph(handle, *, profile,
        limits=None, chain_limits=None, content_limits=None,
        reference_limits=None, identity_limits=None, linked=False, documents=False, information_registers=False):
    """Read complete bounded attributes inside the caller's CONFIG graph stage.

    No native/XML oracle values enter this same-reader path.
    """
    from .filedb_catalog import _BindingHandle
    if type(handle) is not _BindingHandle:
        raise ValueError('CONFIG requires a binding handle')
    try:
        handle._check()
        reader = handle._graph.reader
        return _observe_catalog_prefix(None, reader.header.file_size,
            profile=profile, limits=limits, chain_limits=chain_limits,
            content_limits=content_limits, catalog_limits=reader._budget.limits,
            reference_limits=reference_limits, name_limits=identity_limits,
            standard=True, identity=True, attributes=True, _binding_handle=handle, linked=linked, documents=documents, information_registers=information_registers)
    except BaseException:
        handle._graph.failed = True
        raise

def _observe_catalog_prefix(read_at, file_size, *, profile, limits,
                            chain_limits, content_limits, catalog_limits, reference_limits, name_limits, standard, identity=False, attributes=False, _binding_handle=None, linked=False, documents=False, information_registers=False):
    """Resolve partial Catalog declarations on one private CONFIG resource graph.

    Every selected entry is validated and decoded exactly once before return.
    No complete root grammar, suffix validity or applied state is established.
    Identity mode additionally projects an unverified internal UUID; all private
    results require the separate independent comparator.
    """
    if (type(information_registers) is not bool or information_registers and
            (documents or not (attributes and identity and linked))):
        raise ValueError('information-register projection requires separate linked identity profile')
    if type(documents) is not bool or documents and not (attributes and identity and linked):
        raise ValueError('document projection requires the linked identity profile')
    expected_profile = (ConfigCatalogAttributeProfile if attributes else ConfigCatalogIdentityProfile if identity else
                        ConfigCatalogStandardProfile if standard else ConfigCatalogNameProfile)
    if type(profile) is not expected_profile:
        raise ValueError('profile must be ' + expected_profile.__name__)
    if limits is not None and type(limits) is not ConfigFramingLimits:
        raise ValueError('limits must be ConfigFramingLimits')
    if chain_limits is not None and type(chain_limits) is not ConfigBlobChainLimits:
        raise ValueError('chain_limits must be ConfigBlobChainLimits')
    if content_limits is not None and type(content_limits) is not ConfigContentDecodeLimits:
        raise ValueError('content_limits must be ConfigContentDecodeLimits')
    if catalog_limits is not None and type(catalog_limits) is not CatalogLimits:
        raise ValueError('catalog_limits must be CatalogLimits')
    defaults = CatalogLimits()
    catalog_limits = catalog_limits if catalog_limits is not None else defaults
    if any(getattr(catalog_limits, item.name) > getattr(defaults, item.name)
           for item in _dataclass_fields(CatalogLimits)):
        raise ValueError('CONFIG chain shared limits may only be lowered')
    if type(file_size) is not int or file_size < 0:
        raise ValueError('file_size must be a nonnegative exact integer')
    if file_size > 67108864:
        raise ResourceLimit('config_chain_image_bytes')
    limits = limits if limits is not None else ConfigFramingLimits()
    chain_limits = chain_limits if chain_limits is not None else ConfigBlobChainLimits()
    content_limits = content_limits if content_limits is not None else ConfigContentDecodeLimits()
    if profile.candidate_stride > limits.max_record_bytes:
        raise ResourceLimit('config_record_bytes')
    if _binding_handle is None:
        reader = CatalogReader(read_at, file_size, limits=catalog_limits)
        catalog = reader.read_catalog()
        opener = reader
    else:
        from .filedb_catalog import _BindingHandle
        if type(_binding_handle) is not _BindingHandle or _binding_handle.role != 'config':
            raise ValueError('CONFIG requires its identity-bound graph handle')
        _binding_handle._check()
        reader = _binding_handle._graph.reader
        catalog = _binding_handle._graph.catalog
        if reader.header.file_size != file_size or reader._budget.limits != catalog_limits:
            raise ValueError('CONFIG binding size or budget mismatch')
        opener = _binding_handle
    selected = None
    for table in catalog.tables:
        if _ascii_config(table.name):
            if selected is not None:
                raise UnsupportedLayout('config_table_ambiguous')
            selected = table
    if selected is None:
        raise UnsupportedLayout('config_table_missing')
    if (type(selected.format_item) is not int or selected.format_item != profile.format_item
            or selected.recordlock != profile.recordlock
            or len(selected.fields) != len(profile.declarations)
            or any(item.raw != wanted for item, wanted in zip(selected.fields, profile.declarations))):
        raise UnsupportedLayout('config_profile_mismatch')
    data = opener._open_table_data(selected)
    blob = opener._open_table_blob(selected)
    if data.info.logical_length % profile.candidate_stride:
        raise InvalidStructure('config_record_length')
    slots = data.info.logical_length // profile.candidate_stride
    if not slots:
        raise UnsupportedLayout('config_empty_data')
    if slots > limits.max_slots:
        raise ResourceLimit('config_slots')
    if blob.info.logical_length % 256:
        raise InvalidStructure('config_blob_alignment')
    blocks = blob.info.logical_length // 256
    if blocks < 2:
        raise UnsupportedLayout('config_blob_capacity')
    capacity = min(2**32 - 1, 250 * (blocks - 1))
    zero, one, other, empty, maximum = 0, 0, 0, 0, 0
    selected_count, reference_excluded, name_excluded, part_zero, part_nonzero = 0, 0, 0, 0, 0
    reader._budget.charge('output_bytes', 512)
    references, keys = {}, set()
    for slot in range(slots):
        base = slot * profile.candidate_stride
        marker = _scalar(data, base, 1)
        if slot == 0:
            if marker != b'\x01':
                raise UnsupportedLayout('config_reserved_slot')
            continue
        if marker != b'\x00':
            if marker == b'\x01':
                one += 1
            else:
                other += 1
            continue
        offset = base + profile.filename_offset
        reader._budget.charge('output_bytes', 128)
        units = int.from_bytes(_scalar(data, offset, 2), 'little')
        if units > 128:
            raise InvalidStructure('config_filename_length')
        reader._budget.charge('output_bytes', 128 + 4 * units)
        raw = _scalar(data, offset + 2, 2 * units)
        try:
            name = raw.decode('utf-16-le', errors='strict')
        except UnicodeDecodeError:
            raise UnsupportedLayout('config_filename_encoding') from None
        del raw
        zero += 1
        empty += units == 0
        maximum = max(maximum, units)
        reference = _scalar(data, base + profile.binarydata_offset, profile.binarydata_width)
        reader._budget.charge('output_bytes', 128)
        start = int.from_bytes(reference[:4], 'little')
        length = int.from_bytes(reference[4:], 'little')
        if start == 0 or length == 0:
            reference_excluded += 1
            del name
            continue
        if units == 0:
            name_excluded += 1
            del name
            continue
        if start >= blocks or length > capacity:
            raise InvalidStructure('config_reference_bounds')
        reader._budget.charge('output_bytes', 128)
        reader._budget.charge('bytes_processed', 10)
        part = _config_partno(_scalar(data, base + profile.partno_offset, profile.partno_width))
        if part != 0:
            raise UnsupportedLayout('config_content_nonzero_part')
        content_class = _config_content_name(name, units, reader._budget, keys)
        # Reserve the additional folded key and dictionary association before
        # allocation; the older classification reservation is not reused/refunded.
        reader._budget.charge('output_bytes', 256 + 4 * units)
        reader._budget.charge('bytes_processed', units)
        key = ''.join(chr(ord(c) + 32) if 'A' <= c <= 'Z' else c for c in name)
        del name
        references[key] = (start, length, content_class)
        selected_count += 1
        part_zero += part == 0
        part_nonzero += part != 0
    if not part_zero:
        raise UnsupportedLayout('config_reference_no_part_zero_witness')
    del keys
    chains = _ConfigBlobChains(blob, chain_limits)
    decoder = _ConfigContentDecoder(chains, content_limits)
    plain_count = deflate_count = positive_count = plain_bytes = inflated_bytes = 0
    completed = total_bytes = total_hops = max_hops = multi = zero_used = completed_part_zero = 0
    def decode_entry(reference):
        nonlocal plain_count, deflate_count, positive_count, plain_bytes, inflated_bytes
        nonlocal completed, total_bytes, total_hops, max_hops, multi, zero_used, completed_part_zero
        start, length, content_class = reference
        payload, hops, zeros = chains.read(start, length)
        content = decoder.decode(payload, content_class)
        # Count only completed chain/content pairs; retain no bytes between them.
        if content_class == 'plain':
            plain_count += 1
            plain_bytes += len(content)
        else:
            deflate_count += 1
            positive_count += bool(content)
            inflated_bytes += len(content)
        total_bytes += len(payload)
        del payload
        completed += 1
        total_hops += hops
        max_hops = max(max_hops, hops)
        multi += hops > 1
        zero_used += zeros
        completed_part_zero += 1
        return content

    try:
        if 'root' not in references:
            raise UnsupportedLayout('config_projection_root_missing')
        root_content = decode_entry(references['root'])
        # Flat staging imports only the reviewed stdlib projector; no interpreter.
        from . import config_root_projection as projector
        reader._budget.charge('output_bytes', 256)
        p_profile = projector.RootProjectionProfile(projector.PROFILE_IDENTIFIER)
        p_limits = projector.RootProjectionLimits()
        try:
            reservation = projector.reserve_root_projection(root_content, profile=p_profile, limits=p_limits)
            reader._budget.charge('output_bytes', reservation.output_bytes)
            reader._budget.charge('bytes_processed', reservation.bytes_processed)
            projected = projector.project_root_reference_prefix(root_content, profile=p_profile, limits=p_limits)
        except projector.RootProjectionError as error:
            if error.code in ('input_bytes', 'prefix_bytes', 'output_bytes'):
                raise ResourceLimit('config_projection_' + error.code) from None
            raise InvalidStructure('config_projection_prefix') from None
        target_key = projected.reference
        del root_content, projected, reservation, p_profile, p_limits
        if target_key not in references:
            raise UnsupportedLayout('config_projection_target_missing')
        target_content = decode_entry(references[target_key])
        if not target_content:
            raise UnsupportedLayout('config_projection_target_empty')
        from . import config_catalog_references as catalog_projector
        try:
            candidates = catalog_projector.project_catalog_references(
                target_content, budget=reader._budget, limits=reference_limits)
        except catalog_projector.CatalogReferenceError as error:
            if error.code in catalog_projector.RESOURCE_CODES:
                raise ResourceLimit('config_catalog_limits') from None
            raise InvalidStructure('config_catalog_prefix') from None
        candidate_keys = set(candidates.references)
        document_keys = set()
        register_keys = set()
        catalog_collections = candidates.collection_count
        if documents:
            from . import config_document_metadata as document_projector
            try:
                document_refs = document_projector.project_document_references(
                    target_content, budget=reader._budget, limits=reference_limits)
            except catalog_projector.CatalogReferenceError as error:
                if error.code in catalog_projector.RESOURCE_CODES:
                    raise ResourceLimit('config_document_limits') from None
                raise InvalidStructure('config_document_prefix') from None
            document_keys = set(document_refs.references)
            if candidate_keys.intersection(document_keys):
                raise InvalidStructure('config_document_identity_overlap')
            candidate_keys.update(document_keys)
            if len(candidate_keys) > (reference_limits or catalog_projector.CatalogReferenceLimits()).max_references:
                raise ResourceLimit('config_document_limits')
        if information_registers:
            from . import config_information_register_metadata as register_projector
            try:
                register_refs = register_projector.project_information_register_references(
                    target_content, budget=reader._budget, limits=reference_limits)
            except catalog_projector.CatalogReferenceError as error:
                if error.code in catalog_projector.RESOURCE_CODES:
                    raise ResourceLimit('config_information_register_limits') from None
                raise InvalidStructure('config_information_register_prefix') from None
            register_keys = set(register_refs.references)
            if candidate_keys.intersection(register_keys):
                raise InvalidStructure('config_information_register_identity_overlap')
            candidate_keys.update(register_keys)
            if len(candidate_keys) > (reference_limits or catalog_projector.CatalogReferenceLimits()).max_references:
                raise ResourceLimit('config_information_register_limits')
        del target_content
        catalog_declared = len(candidate_keys)
        del candidates
        if not catalog_declared:
            raise UnsupportedLayout('config_catalog_empty')
        for key in candidate_keys:
            if key == 'root' or key == target_key:
                raise UnsupportedLayout('config_catalog_self_reference')
            if key not in references:
                raise UnsupportedLayout('config_catalog_reference_missing')
        # Fixed reservation for at most256 private pairs or standard records.
        reader._budget.charge('output_bytes', 262144 if standard else 131072)
        private_names = []
        catalog_resolved = catalog_positive = 0
        for key, reference in references.items():
            if key != 'root' and key != target_key:
                content = decode_entry(reference)
                if key in candidate_keys:
                    if not content:
                        raise UnsupportedLayout('config_catalog_content_empty')
                    if information_registers and key in register_keys:
                        try:
                            projected_register = register_projector.project_information_register_metadata(
                                content, budget=reader._budget)
                        except register_projector.a.CatalogAttributeError as error:
                            if error.code in ('input_bytes', 'tokens', 'depth', 'name_bytes', 'name_chars', 'attribute_limit', 'integer_bound'):
                                raise ResourceLimit('config_information_register_limits') from None
                            raise UnsupportedLayout('config_information_register_profile') from None
                        private_names.append((key, *projected_register))
                        catalog_resolved += 1
                        catalog_positive += 1
                        del projected_register, content
                        continue
                    if documents and key in document_keys:
                        from . import config_document_metadata as document_projector
                        try:
                            named, projected_attributes = document_projector.project_document_metadata(
                                content, budget=reader._budget)
                        except document_projector.attrs.CatalogAttributeError as error:
                            if error.code in ('input_bytes', 'tokens', 'depth', 'name_bytes', 'name_chars', 'attribute_limit', 'integer_bound'):
                                raise ResourceLimit('config_document_limits') from None
                            raise UnsupportedLayout('config_document_profile') from None
                        private_names.append((key, named, projected_attributes))
                        catalog_resolved += 1
                        catalog_positive += 1
                        del named, projected_attributes, content
                        continue
                    from . import config_catalog_name as name_projector
                    try:
                        project = (name_projector.project_catalog_identity_prefix if identity else
                                   name_projector.project_catalog_standard_prefix if standard else
                                   name_projector.project_catalog_name_prefix)
                        named = project(content, budget=reader._budget, limits=name_limits)
                    except name_projector.CatalogNameError as error:
                        if error.code in ('input_bytes', 'tokens', 'depth', 'name_bytes', 'name_chars'):
                            raise ResourceLimit('config_catalog_identity_limits' if identity else 'config_catalog_standard_limits' if standard else 'config_catalog_name_limits') from None
                        raise InvalidStructure('config_catalog_identity_prefix' if identity else 'config_catalog_standard_prefix' if standard else 'config_catalog_name_prefix') from None
                    if attributes:
                        attribute_projector = load_catalog_attribute_projector()
                        try:
                            attribute_project = (attribute_projector.project_linked_catalog_attributes if linked
                                                 else attribute_projector.project_catalog_attributes)
                            projected_attributes = attribute_project(content, budget=reader._budget)
                        except attribute_projector.CatalogAttributeError as error:
                            if error.code in ('input_bytes', 'tokens', 'depth', 'name_bytes',
                                              'name_chars', 'attribute_limit', 'integer_bound'):
                                raise ResourceLimit('config_catalog_attribute_limits') from None
                            raise InvalidStructure('config_catalog_attribute_prefix') from None
                        private_names.append((key, named, projected_attributes))
                        del projected_attributes
                    else:
                        private_names.append((key, named) if standard else (key, named.name))
                    del named
                    catalog_resolved += 1
                    catalog_positive += 1
                del content
        del target_key, candidate_keys
        if catalog_declared != catalog_resolved or catalog_resolved != catalog_positive:
            raise InvalidStructure('config_catalog_incomplete')
    except BaseException:
        # This context cannot be reused after projection, selection or content
        # failure. Charges and ownership remain cumulative; no partial result.
        decoder.failed = chains.failed = True
        raise
    try:
        if not completed_part_zero:
            raise UnsupportedLayout('config_chain_no_part_zero_witness')
        if not positive_count:
            raise UnsupportedLayout('config_content_no_positive_witness')
        reader._budget.charge('output_bytes', 4096)
        if information_registers:
            return register_projector.InformationRegisterConfigSnapshot(
                tuple(row for row in private_names if row[0] in register_keys),
                tuple(row for row in private_names if row[0] not in register_keys))
        if documents:
            return document_projector.DocumentConfigSnapshot(
                tuple(row for row in private_names if row[0] in document_keys),
                tuple(row for row in private_names if row[0] not in document_keys))
        observation = (ConfigCatalogAttributeObservation if attributes else ConfigCatalogIdentityObservation if identity else
                       ConfigCatalogStandardObservation if standard else ConfigCatalogNameObservation)
        return observation(profile.identifier, profile.recipe_sha256,
            data.info.logical_length, blob.info.logical_length, slots, 'one',
            zero, one, other, zero, empty, zero - empty, maximum,
            selected_count, reference_excluded, name_excluded, part_zero, part_nonzero,
            reader.usage, completed, total_bytes, total_hops, max_hops, multi, zero_used,
            plain_count, deflate_count, positive_count, plain_bytes, inflated_bytes, decoder.total_calls,
            1, 1, 1, catalog_collections, catalog_declared, catalog_resolved, catalog_positive, tuple(private_names))
    except BaseException:
        decoder.failed = chains.failed = True
        raise
