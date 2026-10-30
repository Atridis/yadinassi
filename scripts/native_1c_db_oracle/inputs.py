"""Exact reviewed source manifest and bounded read-only staging checks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

from protocol import IMAGE, decode, exact, require
from snapshots import OracleError

LEGACY_V3_SOURCE_FILES = {
    'yadinassi/storage/filedb.py':'filedb.py',
    'scripts/native_1c_db_oracle.py':'host.py',
    **{f'scripts/native_1c_db_oracle/{name}':name for name in (
        'probe.sh','run.py','contract.py','protocol.py','snapshots.py','inject_metadata.py','inputs.py',
        'metadata/Catalog.xml','metadata/CommonModule.xml','metadata/Role.xml',
        'metadata/SetupRights.xml','metadata/CRUDRights.xml',
        'modules/SessionModule.bsl','modules/ManagedApplicationModule.bsl','modules/NativeOracleServer.bsl')},
    'scripts/native_1c_bootstrap/inject_modules.py':'inject_modules.py',
}
# Historical v3 inventories remain exactly 18 entries; current v4 stages both
# the standalone parser and the versioned comparison orchestration.
SOURCE_FILES = {**LEGACY_V3_SOURCE_FILES,
    'yadinassi/storage/filedb_catalog.py': 'filedb_catalog.py',
    'scripts/native_1c_db_oracle/comparison.py': 'comparison.py'}
# The default inventory remains exactly 20 files. The explicit observation
# mode alone stages this additional module; old execution never imports it.
RECORD_SOURCE_FILES = {**SOURCE_FILES,
    'scripts/native_1c_db_oracle/record_observation.py': 'record_observation.py'}
RECORD_LANE = 'owned_record_metadata_observation_v1'
# Readback is a distinct, explicitly selected 23-file lane. Neither older
# inventory acquires the row decoder or readback validation policy.
ROW_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'yadinassi/storage/filedb_records.py': 'filedb_records.py',
    'scripts/native_1c_db_oracle/record_validation.py': 'record_validation.py'}
ROW_LANE = 'owned_record_readback_v1'
# Phase A uses unchanged native metadata markers, never the row decoder.
PARAMS_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/params_observation.py': 'params_observation.py'}
CONFIG_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_observation.py': 'config_observation.py'}
CONFIG_LANE = 'owned_config_transport_observation_v1'
# Framing is separately selected; older inventories do not acquire its core/policy.
CONFIG_FRAMING_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_framing.py': 'config_framing.py'}
CONFIG_FRAMING_LANE = 'owned_config_framing_observation_v1'
# Diagnostic census replaces the policy member, not the older source inventories.
CONFIG_MARKER_CENSUS_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_marker_census.py': 'config_marker_census.py'}
CONFIG_MARKER_CENSUS_LANE = 'owned_config_marker_census_v1'
# Field-only observer replaces only its policy member; older modes remain closed.
CONFIG_ZERO_MARKER_FILENAME_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_zero_marker_filename.py': 'config_zero_marker_filename.py'}
CONFIG_ZERO_MARKER_FILENAME_LANE = 'owned_config_zero_marker_filename_v1'
# Entry prerequisites replace only the policy; every older inventory stays closed.
CONFIG_ENTRY_REFERENCE_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_entry_reference.py': 'config_entry_reference.py'}
CONFIG_ENTRY_REFERENCE_LANE = 'owned_config_entry_reference_v1'
# Exact stored-byte chain lane replaces the policy, never extending old inventories.
CONFIG_BLOB_CHAIN_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_blob_chain.py': 'config_blob_chain.py'}
CONFIG_BLOB_CHAIN_LANE = 'owned_config_blob_chain_v1'
# Content decode uses the same closed dependencies with its distinct policy.
CONFIG_CONTENT_DECODE_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_content_decode.py': 'config_content_decode.py'}
CONFIG_CONTENT_DECODE_LANE = 'owned_config_content_decode_v1'
# The partial-reference lane alone stages its explicit prefix projector.
CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_root_reference_projection.py': 'config_root_reference_projection.py',
    'yadinassi/storage/config_root_projection.py': 'config_root_projection.py'}
CONFIG_ROOT_REFERENCE_PROJECTION_LANE = 'owned_config_root_reference_projection_v1'
# Catalog declarations add one private parser; all earlier inventories stay closed.
CONFIG_CATALOG_OBSERVATION_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_catalog_observation.py': 'config_catalog_observation.py',
    'yadinassi/storage/config_root_projection.py': 'config_root_projection.py',
    'yadinassi/storage/config_catalog_references.py': 'config_catalog_references.py'}
CONFIG_CATALOG_OBSERVATION_LANE = 'owned_config_catalog_observation_v1'
# New independent name-binding lane; old inventories remain exact.
CONFIG_CATALOG_NAME_SOURCE_FILES = {**RECORD_SOURCE_FILES,
    'scripts/native_1c_db_oracle/config_framing_reader.py': 'config_framing_reader.py',
    'scripts/native_1c_db_oracle/config_catalog_name_binding.py': 'config_catalog_name_binding.py',
    'yadinassi/storage/config_root_projection.py': 'config_root_projection.py',
    'yadinassi/storage/config_catalog_references.py': 'config_catalog_references.py',
    'yadinassi/storage/config_catalog_name.py': 'config_catalog_name.py'}
CONFIG_CATALOG_NAME_LANE = 'owned_config_catalog_name_binding_v1'
CONFIG_CATALOG_STANDARD_SOURCE_FILES = {key: value for key, value in CONFIG_CATALOG_NAME_SOURCE_FILES.items()
    if key != 'scripts/native_1c_db_oracle/config_catalog_name_binding.py'}
CONFIG_CATALOG_STANDARD_SOURCE_FILES['scripts/native_1c_db_oracle/config_catalog_standard_binding.py'] = 'config_catalog_standard_binding.py'
CONFIG_CATALOG_STANDARD_LANE = 'owned_config_catalog_standard_binding_v1'
CONFIG_CATALOG_IDENTITY_SOURCE_FILES = {key: value for key, value in CONFIG_CATALOG_STANDARD_SOURCE_FILES.items()
    if key != 'scripts/native_1c_db_oracle/config_catalog_standard_binding.py'}
CONFIG_CATALOG_IDENTITY_SOURCE_FILES['scripts/native_1c_db_oracle/config_catalog_identity_binding.py'] = 'config_catalog_identity_binding.py'
CONFIG_CATALOG_IDENTITY_LANE = 'owned_config_catalog_identity_binding_v1'
# Fixed three-Catalog matrix, never arbitrary fixture parameters.
CONFIG_CATALOG_FIELD_MATRIX_SOURCE_FILES = {key: value for key, value in CONFIG_CATALOG_IDENTITY_SOURCE_FILES.items()
    if key != 'scripts/native_1c_db_oracle/config_catalog_identity_binding.py'}
CONFIG_CATALOG_FIELD_MATRIX_SOURCE_FILES.update({
    'scripts/native_1c_db_oracle/config_catalog_field_matrix.py': 'config_catalog_field_matrix.py',
    'scripts/native_1c_db_oracle/catalog_field_matrix.py': 'catalog_field_matrix.py'})
CONFIG_CATALOG_FIELD_MATRIX_LANE = 'owned_config_catalog_field_matrix_v1'
# Attribute projection is separately selected; historical inventories stay exact.
CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES = {key: value for key, value in CONFIG_CATALOG_FIELD_MATRIX_SOURCE_FILES.items()
    if key != 'scripts/native_1c_db_oracle/config_catalog_field_matrix.py'}
CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES.update({
    'scripts/native_1c_db_oracle/config_catalog_attribute_binding.py': 'config_catalog_attribute_binding.py',
    'yadinassi/storage/config_catalog_attributes.py': 'config_catalog_attributes.py'})
CONFIG_CATALOG_ATTRIBUTE_LANE = 'owned_config_catalog_attribute_binding_v1'
# Three-role binding is a distinct explicit lane, never an older inventory alias.
CATALOG_BINDING_SOURCE_FILES = {**CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES,
    **{f'yadinassi/storage/{name}.py': f'{name}.py' for name in (
        'filedb_named_file', 'filedb_dbnames', 'filedb_records',
        'config_catalog_binding', 'config_catalog_records',
        'config_catalog_transport', 'catalog_reader')},
    'scripts/native_1c_db_oracle/catalog_binding_reader.py': 'catalog_binding_reader.py',
    'scripts/native_1c_db_oracle/catalog_readonly_binding.py': 'catalog_readonly_binding.py'}
CATALOG_BINDING_LANE = 'owned_catalog_readonly_binding_v1'



PARAMS_LANE = 'owned_params_transport_observation_v1'
# Extraction is a separate lane; no older inventory acquires its reader/policy.
EXTRACTION_SOURCE_FILES = {**PARAMS_SOURCE_FILES,
    'yadinassi/storage/filedb_named_file.py': 'filedb_named_file.py',
    'scripts/native_1c_db_oracle/params_extraction.py': 'params_extraction.py'}
EXTRACTION_LANE = 'owned_params_dbnames_extraction_v1'
# Identity validation is explicit; earlier inventories never acquire its parser.
IDENTITY_SOURCE_FILES = {**EXTRACTION_SOURCE_FILES,
    'yadinassi/storage/filedb_dbnames.py': 'filedb_dbnames.py',
    'scripts/native_1c_db_oracle/dbnames_identity.py': 'dbnames_identity.py'}
IDENTITY_LANE = 'owned_dbnames_identity_validation_v1'
CATALOG_REFERENCE_SOURCE_FILES = {**CATALOG_BINDING_SOURCE_FILES,
    'scripts/native_1c_db_oracle/catalog_reference_identity.py': 'catalog_reference_identity.py',
    'scripts/native_1c_db_oracle/catalog_reference_native.py': 'catalog_reference_native.py',
    'scripts/native_1c_db_oracle/modules/CatalogReferenceObservation.bsl': 'modules/CatalogReferenceObservation.bsl'}
CATALOG_REFERENCE_LANE = 'catalog-reference-identity-v1'
CATALOG_CODEC_SOURCE_FILES = {**CATALOG_REFERENCE_SOURCE_FILES,
    'scripts/native_1c_db_oracle/catalog_reference_codec.py': 'catalog_reference_codec.py',
    'yadinassi/storage/catalog_reference_uuid.py': 'catalog_reference_uuid.py'}
CATALOG_CODEC_LANE = 'catalog-reference-codec-v1'
CATALOG_ROWS_SOURCE_FILES = {**CATALOG_CODEC_SOURCE_FILES,
    'scripts/native_1c_db_oracle/catalog_reference_rows.py': 'catalog_reference_rows.py'}
CATALOG_ROWS_LANE = 'catalog-reference-rows-v1'
CATALOG_DESCRIPTION_SOURCE_FILES = {**CATALOG_BINDING_SOURCE_FILES,
    **{f'scripts/native_1c_db_oracle/{name}': name for name in (
        'catalog_description_measurement.py', 'catalog_description_physical.py',
        'catalog_description_policy.py', 'modules/CatalogDescriptionObservation.bsl')}}
CATALOG_DESCRIPTION_LANE = 'catalog-description-measurement-v1'
CATALOG_DESCRIPTION_ROWS_SOURCE_FILES = {key:value for key,value in CATALOG_DESCRIPTION_SOURCE_FILES.items()
    if key != 'scripts/native_1c_db_oracle/catalog_description_policy.py'}
CATALOG_DESCRIPTION_ROWS_SOURCE_FILES.update({
    'scripts/native_1c_db_oracle/catalog_description_rows.py':'catalog_description_rows.py',
    'yadinassi/storage/catalog_reference_uuid.py':'catalog_reference_uuid.py'})
CATALOG_DESCRIPTION_ROWS_LANE = 'catalog-description-rows-v1'
CATALOG_PARAMS_SLOT_SOURCE_FILES = {**CATALOG_DESCRIPTION_ROWS_SOURCE_FILES,
    **{f'scripts/native_1c_db_oracle/{name}': name for name in ('params_slot_observer.py','params_slot_policy.py')}}
CATALOG_PARAMS_SLOT_LANE = 'catalog-params-slot-measurement-v1'
MAX_SOURCE=1048576


def inventory(record_metadata=False, *, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False):
    require(type(record_metadata) is bool and type(record_reader) is bool
            and type(params_transport) is bool and type(params_extraction) is bool
            and type(dbnames_identity) is bool and type(config_transport) is bool and type(config_framing) is bool and type(config_marker_census) is bool and type(config_zero_marker_filename) is bool and type(config_entry_reference) is bool and type(config_blob_chain) is bool and type(config_content_decode) is bool and type(config_root_reference_projection) is bool and type(config_catalog_observation) is bool and type(config_catalog_name_binding) is bool and type(config_catalog_standard_binding) is bool and type(config_catalog_identity_binding) is bool and type(config_catalog_field_matrix) is bool and type(config_catalog_attribute_binding) is bool and type(catalog_readonly_binding) is bool
            and sum((record_metadata, record_reader, params_transport, params_extraction, dbnames_identity, config_transport, config_framing, config_marker_census, config_zero_marker_filename, config_entry_reference, config_blob_chain, config_content_decode, config_root_reference_projection, config_catalog_observation, config_catalog_name_binding, config_catalog_standard_binding, config_catalog_identity_binding, config_catalog_field_matrix, config_catalog_attribute_binding, catalog_readonly_binding, reference_case is not None, description_case is not None)) <= 1, 'invalid_input')
    require(reference_case is None or type(reference_case) is str and reference_case in ('distinct_a','distinct_b'), 'invalid_input')
    require(type(reference_codec) is bool and (not reference_codec or reference_case is not None), 'invalid_input')
    require(type(reference_rows) is bool and (not reference_rows or reference_case is not None)
            and not (reference_rows and reference_codec), 'invalid_input')
    require(description_case is None or type(description_case) is str and description_case in ('description8','description17'), 'invalid_input')
    require(type(description_rows) is bool and (not description_rows or description_case is not None), 'invalid_input')
    require(type(params_slots) is bool and (not params_slots or description_case is not None)
            and not (params_slots and description_rows), 'invalid_input')
    if params_slots: return CATALOG_PARAMS_SLOT_SOURCE_FILES
    if description_rows: return CATALOG_DESCRIPTION_ROWS_SOURCE_FILES
    if description_case is not None: return CATALOG_DESCRIPTION_SOURCE_FILES
    if reference_rows: return CATALOG_ROWS_SOURCE_FILES
    if reference_codec: return CATALOG_CODEC_SOURCE_FILES
    if reference_case is not None: return CATALOG_REFERENCE_SOURCE_FILES
    if catalog_readonly_binding: return CATALOG_BINDING_SOURCE_FILES
    if config_catalog_attribute_binding: return CONFIG_CATALOG_ATTRIBUTE_SOURCE_FILES
    if config_catalog_field_matrix: return CONFIG_CATALOG_FIELD_MATRIX_SOURCE_FILES
    if config_catalog_identity_binding: return CONFIG_CATALOG_IDENTITY_SOURCE_FILES
    if config_catalog_standard_binding: return CONFIG_CATALOG_STANDARD_SOURCE_FILES
    if config_catalog_name_binding: return CONFIG_CATALOG_NAME_SOURCE_FILES
    if config_catalog_observation: return CONFIG_CATALOG_OBSERVATION_SOURCE_FILES
    if config_root_reference_projection: return CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES
    if config_content_decode: return CONFIG_CONTENT_DECODE_SOURCE_FILES
    if config_blob_chain: return CONFIG_BLOB_CHAIN_SOURCE_FILES
    if config_entry_reference: return CONFIG_ENTRY_REFERENCE_SOURCE_FILES
    if config_zero_marker_filename: return CONFIG_ZERO_MARKER_FILENAME_SOURCE_FILES
    if config_marker_census: return CONFIG_MARKER_CENSUS_SOURCE_FILES
    if config_framing: return CONFIG_FRAMING_SOURCE_FILES
    if config_transport: return CONFIG_SOURCE_FILES
    if dbnames_identity: return IDENTITY_SOURCE_FILES
    if params_extraction: return EXTRACTION_SOURCE_FILES
    if params_transport: return PARAMS_SOURCE_FILES
    if record_reader: return ROW_SOURCE_FILES
    return RECORD_SOURCE_FILES if record_metadata else SOURCE_FILES


def read_source(path):
    try:
        info=path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<info.st_size<=MAX_SOURCE,'invalid_input')
        fd=os.open(path,os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        with os.fdopen(fd,'rb') as stream:
            start=os.fstat(stream.fileno())
            require((start.st_dev,start.st_ino)==(info.st_dev,info.st_ino),'invalid_input')
            raw=stream.read(MAX_SOURCE+1); end=os.fstat(stream.fileno())
        require(0<len(raw)<=MAX_SOURCE and (start.st_size,start.st_mtime_ns,start.st_ctime_ns)==
            (end.st_size,end.st_mtime_ns,end.st_ctime_ns),'invalid_input')
        return raw
    except OSError:
        raise OracleError('invalid_input') from None


def source_hashes(root, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False):
    files=inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots)
    require(root.is_dir() and not root.is_symlink(),'invalid_input')
    result={}
    for relative in files:
        path=root/relative
        require(not any(parent.is_symlink() for parent in path.parents if parent!=root),'invalid_input')
        result[relative]=hashlib.sha256(read_source(path)).hexdigest()
    return result


def staged_hashes(root, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False):
    files=inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots)
    allowed=set(files.values()) | {'invocation.json'}
    directories={parent.as_posix() for name in allowed for parent in Path(name).parents if str(parent)!='.'}
    actual=set()
    for path in root.rglob('*'):
        relative=path.relative_to(root).as_posix()
        require(not path.is_symlink(),'invalid_input')
        if path.is_dir(): require(relative in directories,'invalid_input')
        else:
            require(relative in allowed,'invalid_input'); read_source(path); actual.add(relative)
    require(actual==allowed,'invalid_input')
    return {source:hashlib.sha256(read_source(root/target)).hexdigest() for source,target in files.items()}


def stage_inputs(root, destination, nonce, provenance, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False):
    files=inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots)
    require(not destination.exists() and not destination.is_symlink(),'stale_evidence')
    destination.mkdir(mode=0o755)
    for source,target in files.items():
        path=destination/target; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(read_source(root/source)); path.chmod(0o444)
    invocation={'schema':1,'nonce':nonce,'provenance':provenance}
    if description_case is not None:
        invocation.update(schema=29 if params_slots else 28 if description_rows else 27, lane=CATALOG_PARAMS_SLOT_LANE if params_slots else CATALOG_DESCRIPTION_ROWS_LANE if description_rows else CATALOG_DESCRIPTION_LANE, description_case=description_case)
    elif reference_case is not None:
        invocation.update(schema=26 if reference_rows else 25 if reference_codec else 24,
            lane=CATALOG_ROWS_LANE if reference_rows else CATALOG_CODEC_LANE if reference_codec else CATALOG_REFERENCE_LANE, reference_case=reference_case)
    elif catalog_readonly_binding:
        invocation.update(schema=23, lane=CATALOG_BINDING_LANE)
    elif config_catalog_attribute_binding:
        invocation.update(schema=22, lane=CONFIG_CATALOG_ATTRIBUTE_LANE)
    elif config_catalog_field_matrix:
        invocation.update(schema=21, lane=CONFIG_CATALOG_FIELD_MATRIX_LANE)
    elif config_catalog_identity_binding:
        invocation.update(schema=20, lane=CONFIG_CATALOG_IDENTITY_LANE)
    elif config_catalog_standard_binding:
        invocation.update(schema=19, lane=CONFIG_CATALOG_STANDARD_LANE)
    elif config_catalog_name_binding:
        invocation.update(schema=18, lane=CONFIG_CATALOG_NAME_LANE)
    elif config_catalog_observation:
        invocation.update(schema=17, lane=CONFIG_CATALOG_OBSERVATION_LANE)
    elif config_root_reference_projection:
        invocation.update(schema=16, lane=CONFIG_ROOT_REFERENCE_PROJECTION_LANE)
    elif config_content_decode:
        invocation.update(schema=13, lane=CONFIG_CONTENT_DECODE_LANE)
    elif config_blob_chain:
        invocation.update(schema=12, lane=CONFIG_BLOB_CHAIN_LANE)
    elif config_entry_reference:
        invocation.update(schema=11, lane=CONFIG_ENTRY_REFERENCE_LANE)
    elif config_zero_marker_filename:
        invocation.update(schema=10, lane=CONFIG_ZERO_MARKER_FILENAME_LANE)
    elif config_marker_census:
        invocation.update(schema=9, lane=CONFIG_MARKER_CENSUS_LANE)
    elif config_framing:
        invocation.update(schema=8, lane=CONFIG_FRAMING_LANE)
    elif config_transport:
        invocation.update(schema=7, lane=CONFIG_LANE)
    elif dbnames_identity:
        invocation.update(schema=6, lane=IDENTITY_LANE)
    elif params_extraction:
        invocation.update(schema=5, lane=EXTRACTION_LANE)
    elif params_transport:
        invocation.update(schema=4, lane=PARAMS_LANE)
    elif record_reader:
        invocation.update(schema=3, lane=ROW_LANE)
    elif record_metadata:
        invocation.update(schema=2, lane=RECORD_LANE)
    (destination/'invocation.json').write_text(json.dumps(invocation,separators=(',',':')),encoding='ascii')
    (destination/'invocation.json').chmod(0o444)
    for path in destination.rglob('*'):
        if path.is_dir(): path.chmod(0o555)
    destination.chmod(0o555)
    require(staged_hashes(destination,record_metadata=record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots)
            ==provenance['sources'],'provenance_mismatch')


def verify_inputs(root,nonce, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False):
    inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots)
    require(root.is_dir() and not root.is_symlink(),'invalid_input')
    data=decode(read_source(root/'invocation.json'))
    exact(data,{'schema','nonce','provenance'} | ({'description_case','lane'} if description_case is not None else set()) | ({'reference_case','lane'} if reference_case is not None else set()) | ({'lane'} if record_metadata or record_reader or params_transport or params_extraction or dbnames_identity or config_transport or config_framing or config_marker_census or config_zero_marker_filename or config_entry_reference or config_blob_chain or config_content_decode or config_root_reference_projection or config_catalog_observation or config_catalog_name_binding or config_catalog_standard_binding or config_catalog_identity_binding or config_catalog_field_matrix or config_catalog_attribute_binding or catalog_readonly_binding else set()))
    require(type(data['schema']) is int and data['schema']==(29 if params_slots else 28 if description_rows else 27 if description_case is not None else 26 if reference_rows else 25 if reference_codec else 24 if reference_case is not None else 23 if catalog_readonly_binding else 22 if config_catalog_attribute_binding else 21 if config_catalog_field_matrix else 20 if config_catalog_identity_binding else 19 if config_catalog_standard_binding else 18 if config_catalog_name_binding else 17 if config_catalog_observation else 16 if config_root_reference_projection else 13 if config_content_decode else 12 if config_blob_chain else 11 if config_entry_reference else 10 if config_zero_marker_filename else 9 if config_marker_census else 8 if config_framing else 7 if config_transport else 6 if dbnames_identity else 5 if params_extraction else 4 if params_transport else 3 if record_reader else 2 if record_metadata else 1)
            and data['nonce']==nonce,'provenance_mismatch')
    if description_case is not None: require(data['lane']==(CATALOG_PARAMS_SLOT_LANE if params_slots else CATALOG_DESCRIPTION_ROWS_LANE if description_rows else CATALOG_DESCRIPTION_LANE) and data['description_case']==description_case,'provenance_mismatch')
    elif reference_case is not None: require(data['lane']==(CATALOG_ROWS_LANE if reference_rows else CATALOG_CODEC_LANE if reference_codec else CATALOG_REFERENCE_LANE) and data['reference_case']==reference_case,'provenance_mismatch')
    elif catalog_readonly_binding: require(data['lane']==CATALOG_BINDING_LANE,'provenance_mismatch')
    elif config_catalog_attribute_binding: require(data['lane']==CONFIG_CATALOG_ATTRIBUTE_LANE,'provenance_mismatch')
    elif config_catalog_field_matrix: require(data['lane']==CONFIG_CATALOG_FIELD_MATRIX_LANE,'provenance_mismatch')
    elif config_catalog_identity_binding: require(data['lane']==CONFIG_CATALOG_IDENTITY_LANE,'provenance_mismatch')
    elif config_catalog_standard_binding: require(data['lane']==CONFIG_CATALOG_STANDARD_LANE,'provenance_mismatch')
    elif config_catalog_name_binding: require(data['lane']==CONFIG_CATALOG_NAME_LANE,'provenance_mismatch')
    elif config_catalog_observation: require(data['lane']==CONFIG_CATALOG_OBSERVATION_LANE,'provenance_mismatch')
    elif config_root_reference_projection: require(data['lane']==CONFIG_ROOT_REFERENCE_PROJECTION_LANE,'provenance_mismatch')
    elif config_content_decode: require(data['lane']==CONFIG_CONTENT_DECODE_LANE,'provenance_mismatch')
    elif config_blob_chain: require(data['lane']==CONFIG_BLOB_CHAIN_LANE,'provenance_mismatch')
    elif config_entry_reference: require(data['lane']==CONFIG_ENTRY_REFERENCE_LANE,'provenance_mismatch')
    elif config_zero_marker_filename: require(data['lane']==CONFIG_ZERO_MARKER_FILENAME_LANE,'provenance_mismatch')
    elif config_marker_census: require(data['lane']==CONFIG_MARKER_CENSUS_LANE,'provenance_mismatch')
    elif config_framing: require(data['lane']==CONFIG_FRAMING_LANE,'provenance_mismatch')
    elif config_transport: require(data['lane']==CONFIG_LANE,'provenance_mismatch')
    elif dbnames_identity: require(data['lane']==IDENTITY_LANE,'provenance_mismatch')
    elif params_extraction: require(data['lane']==EXTRACTION_LANE,'provenance_mismatch')
    elif params_transport: require(data['lane']==PARAMS_LANE,'provenance_mismatch')
    elif record_reader: require(data['lane']==ROW_LANE,'provenance_mismatch')
    elif record_metadata: require(data['lane']==RECORD_LANE,'provenance_mismatch')
    provenance=data['provenance']
    from protocol import validate_provenance
    validate_provenance(provenance,provenance)
    require(provenance['image']==IMAGE and provenance['platform']=='linux/amd64'
            and provenance['locale']=='ru_RU.UTF-8' and provenance['timezone']=='Etc/UTC'
            and provenance['actual_version'] is None,'provenance_mismatch')
    require(staged_hashes(root,record_metadata=record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots)
            ==provenance['sources'],'provenance_mismatch')
    return provenance
