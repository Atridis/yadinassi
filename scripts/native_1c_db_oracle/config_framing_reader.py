"""One explicit CONFIG framing hypothesis; no root, extraction or applied state.

Independently implemented from pinned source facts. This module uses only stdlib
and the exact catalog sibling, never imports the interpreter, and retains no
source filenames, rows or values. Synthetic success is not native acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from filedb_catalog import (CatalogLimits, CatalogReader, CatalogUsage,
                            InvalidStructure, ResourceLimit, UnsupportedLayout)


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


@dataclass(frozen=True)
class ConfigFramingObservation:
    profile_id: str
    profile_sha256: str
    data_logical_bytes: int
    blob_logical_bytes: int
    slots: int
    active_slots: int
    empty_filenames: int
    nonempty_filenames: int
    max_filename_units: int
    usage: CatalogUsage
    target: str = field(default='CONFIG', init=False)
    capability: str = field(default='experimental_config_framing_observation', init=False)
    framing_validation: str = field(default='source_hypothesis_satisfied', init=False)
    filename_validation: str = field(default='bounded_utf16le_validated', init=False)
    root_identity: str = field(default='not_observed', init=False)
    native_acceptance: str = field(default='pending', init=False)


def _ascii_config(value):
    return len(value) == 6 and all(a == b or (97 <= ord(a) <= 122 and chr(ord(a)-32) == b)
                                  for a, b in zip(value, 'CONFIG'))


def _scalar(data, offset, length):
    data._validate_range(offset, length)
    # Logical callback, bytearray assembly and immutable copy reserved first.
    data._source.budget.charge('output_bytes', 3 * length)
    data._source.budget.charge('bytes_processed', length)
    return data._read_range(offset, length)


def observe_config_framing(read_at, file_size, *, profile,
                           limits=None, catalog_limits=None):
    """Read-only whole-table framing and filename-codec check, all or nothing.

    Dates, attributes, size, BLOB pointers and part numbers remain opaque. All
    filenames are validated, but none are selected, retained or returned. Free
    rows are unsupported, not silently skipped. No alternate profile is tried.
    """
    if type(profile) is not ConfigFramingProfile:
        raise ValueError('profile must be ConfigFramingProfile')
    if limits is not None and type(limits) is not ConfigFramingLimits:
        raise ValueError('limits must be ConfigFramingLimits')
    if catalog_limits is not None and type(catalog_limits) is not CatalogLimits:
        raise ValueError('catalog_limits must be CatalogLimits')
    limits = limits if limits is not None else ConfigFramingLimits()
    if profile.record_size > limits.max_record_bytes:
        raise ResourceLimit('config_record_bytes')
    reader = CatalogReader(read_at, file_size, limits=catalog_limits)
    catalog = reader.read_catalog()
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
    data = reader._open_table_data(selected)
    blob = reader._open_table_blob(selected)
    if data.info.logical_length % profile.record_size:
        raise InvalidStructure('config_record_length')
    slots = data.info.logical_length // profile.record_size
    if not slots:
        raise UnsupportedLayout('config_empty_data')
    if slots > limits.max_slots:
        raise ResourceLimit('config_slots')
    empty, maximum = 0, 0
    for slot in range(slots):
        base = slot * profile.record_size
        marker = _scalar(data, base, 1)
        if slot == 0:
            if marker != b'\x01':
                raise UnsupportedLayout('config_reserved_slot')
            continue
        if marker != b'\x00':
            raise UnsupportedLayout('config_nonreserved_slot')
        offset = base + profile.placements[0][0]
        units = int.from_bytes(_scalar(data, offset, 2), 'little')
        if units > 128:
            raise InvalidStructure('config_filename_length')
        # Conservative decoded Unicode representation reservation, including
        # temporary validation object. No string survives this iteration.
        reader._budget.charge('output_bytes', 128 + 4 * units)
        raw = _scalar(data, offset + 2, 2 * units)
        try:
            raw.decode('utf-16-le', errors='strict')
        except UnicodeDecodeError:
            raise UnsupportedLayout('config_filename_encoding') from None
        empty += units == 0
        maximum = max(maximum, units)
    reader._budget.charge('output_bytes', 4096)
    active = slots - 1
    return ConfigFramingObservation(profile.identifier, profile.recipe_sha256,
        data.info.logical_length, blob.info.logical_length, slots, active,
        empty, active - empty, maximum, reader.usage)


@dataclass(frozen=True)
class ConfigMarkerCensusProfile:
    """A separate diagnostic recipe, never a relaxed framing-success profile."""

    declarations: tuple[tuple[str, str, int, int, int, str], ...]
    recordlock: str
    format_item: int
    identifier: str = field(default='config_marker_census_8380_8192_v1', init=False)
    candidate_stride: int = field(init=False)
    recipe_sha256: str = field(init=False)

    def __post_init__(self):
        layout = ConfigFramingProfile(self.declarations, self.recordlock, self.format_item)
        object.__setattr__(self, 'candidate_stride', layout.record_size)
        raw = json.dumps(self.recipe(), ensure_ascii=True, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('ascii')
        object.__setattr__(self, 'recipe_sha256', hashlib.sha256(raw).hexdigest())

    def recipe(self):
        return {'identifier': self.identifier, 'declarations': self.declarations,
                'recordlock': self.recordlock, 'format_item': self.format_item,
                'candidate_stride': self.candidate_stride,
                'observation': 'first_and_later_zero_one_other_candidate_markers_v1',
                'selection': 'CONFIG_ascii_case_only_no_fallback_v1',
                'empty_data': 'unsupported', 'single_candidate': 'admitted',
                'framing': 'not_accepted', 'filename': 'not_read'}


@dataclass(frozen=True)
class ConfigMarkerCensusObservation:
    recipe_id: str
    recipe_sha256: str
    data_logical_bytes: int
    blob_logical_bytes: int
    candidate_slots: int
    first_marker_class: str
    later_zero_count: int
    later_one_count: int
    later_other_count: int
    usage: CatalogUsage
    candidate_stride: int = field(default=301, init=False)
    target: str = field(default='CONFIG', init=False)
    capability: str = field(default='experimental_config_marker_census', init=False)
    framing_validation: str = field(default='not_accepted', init=False)
    filename_validation: str = field(default='not_run', init=False)
    root_identity: str = field(default='not_observed', init=False)
    native_acceptance: str = field(default='pending', init=False)


def observe_config_marker_census(read_at, file_size, *, profile,
                                 limits=None, catalog_limits=None):
    """Count neutral marker classes at candidate boundaries; no row semantics.

    All candidates are counted, including first/nonzero/other markers. Neither
    active/removed/free status nor UTF16 filenames or free-list links are read
    or validated. This cannot turn the strict framing hypothesis into success.
    """
    if type(profile) is not ConfigMarkerCensusProfile:
        raise ValueError('profile must be ConfigMarkerCensusProfile')
    if limits is not None and type(limits) is not ConfigFramingLimits:
        raise ValueError('limits must be ConfigFramingLimits')
    if catalog_limits is not None and type(catalog_limits) is not CatalogLimits:
        raise ValueError('catalog_limits must be CatalogLimits')
    limits = limits if limits is not None else ConfigFramingLimits()
    if profile.candidate_stride > limits.max_record_bytes:
        raise ResourceLimit('config_record_bytes')
    reader = CatalogReader(read_at, file_size, limits=catalog_limits)
    catalog = reader.read_catalog()
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
    data = reader._open_table_data(selected)
    blob = reader._open_table_blob(selected)
    if data.info.logical_length % profile.candidate_stride:
        raise InvalidStructure('config_record_length')
    slots = data.info.logical_length // profile.candidate_stride
    if not slots:
        raise UnsupportedLayout('config_empty_data')
    if slots > limits.max_slots:
        raise ResourceLimit('config_slots')
    counts = {'zero': 0, 'one': 0, 'other': 0}
    first = None
    for slot in range(slots):
        marker = _scalar(data, slot * profile.candidate_stride, 1)
        marker_class = 'zero' if marker == b'\x00' else 'one' if marker == b'\x01' else 'other'
        if slot == 0:
            first = marker_class
        else:
            counts[marker_class] += 1
    reader._budget.charge('output_bytes', 4096)
    return ConfigMarkerCensusObservation(profile.identifier, profile.recipe_sha256,
        data.info.logical_length, blob.info.logical_length, slots, first,
        counts['zero'], counts['one'], counts['other'], reader.usage)


@dataclass(frozen=True)
class ConfigZeroMarkerFilenameProfile:
    """Separate field-only hypothesis; zero is not an active-file identity."""

    declarations: tuple[tuple[str, str, int, int, int, str], ...]
    recordlock: str
    format_item: int
    identifier: str = field(default='config_zero_marker_filename_8380_8192_v1', init=False)
    candidate_stride: int = field(init=False)
    filename_offset: int = field(init=False)
    filename_width: int = field(init=False)
    recipe_sha256: str = field(init=False)

    def __post_init__(self):
        layout = ConfigFramingProfile(self.declarations, self.recordlock, self.format_item)
        object.__setattr__(self, 'candidate_stride', layout.record_size)
        object.__setattr__(self, 'filename_offset', layout.placements[0][0])
        object.__setattr__(self, 'filename_width', layout.placements[0][1])
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
                'empty_data': 'unsupported', 'nonempty_witness': 'required',
                'framing': 'not_accepted'}


@dataclass(frozen=True)
class ConfigZeroMarkerFilenameObservation:
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
    usage: CatalogUsage
    candidate_stride: int = field(default=301, init=False)
    target: str = field(default='CONFIG', init=False)
    capability: str = field(default='experimental_config_zero_marker_filename', init=False)
    framing_validation: str = field(default='not_accepted', init=False)
    filename_validation: str = field(default='zero_marker_bounded_utf16le', init=False)
    root_identity: str = field(default='not_observed', init=False)
    native_acceptance: str = field(default='pending', init=False)


def observe_config_zero_marker_filenames(read_at, file_size, *, profile,
                                         limits=None, catalog_limits=None):
    """Validate only zero-marker filename fields, with a nonempty witness.

    First-slot payload and every nonzero candidate payload remain opaque. Every
    zero candidate is checked, even if its unread BLOB pointer might be empty.
    Thus this is not upstream file selection, a free-list model or whole-row
    framing. Names are never selected, normalized, retained or returned.
    """
    if type(profile) is not ConfigZeroMarkerFilenameProfile:
        raise ValueError('profile must be ConfigZeroMarkerFilenameProfile')
    if limits is not None and type(limits) is not ConfigFramingLimits:
        raise ValueError('limits must be ConfigFramingLimits')
    if catalog_limits is not None and type(catalog_limits) is not CatalogLimits:
        raise ValueError('catalog_limits must be CatalogLimits')
    limits = limits if limits is not None else ConfigFramingLimits()
    if profile.candidate_stride > limits.max_record_bytes:
        raise ResourceLimit('config_record_bytes')
    reader = CatalogReader(read_at, file_size, limits=catalog_limits)
    catalog = reader.read_catalog()
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
    data = reader._open_table_data(selected)
    blob = reader._open_table_blob(selected)
    if data.info.logical_length % profile.candidate_stride:
        raise InvalidStructure('config_record_length')
    slots = data.info.logical_length // profile.candidate_stride
    if not slots:
        raise UnsupportedLayout('config_empty_data')
    if slots > limits.max_slots:
        raise ResourceLimit('config_slots')
    zero, one, other, empty, maximum = 0, 0, 0, 0, 0
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
        units = int.from_bytes(_scalar(data, offset, 2), 'little')
        if units > 128:
            raise InvalidStructure('config_filename_length')
        reader._budget.charge('output_bytes', 128 + 4 * units)
        raw = _scalar(data, offset + 2, 2 * units)
        try:
            raw.decode('utf-16-le', errors='strict')
        except UnicodeDecodeError:
            raise UnsupportedLayout('config_filename_encoding') from None
        zero += 1
        empty += units == 0
        maximum = max(maximum, units)
    # No vacuous filename-decoding success. This is a local observation-witness
    # requirement, not a claim that native 1C rejects empty CONFIG filenames.
    if zero == empty:
        raise UnsupportedLayout('config_filename_no_nonempty_witness')
    reader._budget.charge('output_bytes', 4096)
    return ConfigZeroMarkerFilenameObservation(profile.identifier, profile.recipe_sha256,
        data.info.logical_length, blob.info.logical_length, slots, 'one',
        zero, one, other, zero, empty, zero - empty, maximum, reader.usage)
