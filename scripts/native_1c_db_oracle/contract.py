"""Strict v3 shape-only envelope. This is not physical-reader acceptance.

Historical v2 reports are neither accepted nor upgraded by this module. The
unchanged v2 validator still checks every lifecycle fact inside a v3 report.
"""
from __future__ import annotations

import hashlib
import json
import re

import protocol as lifecycle
from protocol import decode, digest, encode, exact, integer, require

SCHEMA = 3
LANE = 'native-file-db-shape-contract-v3'
TARGET = 'Справочник.NativeOracleItems'
MAX_SHAPE_BYTES = 8192
MAX_TABLES = 16
MAX_COLUMNS = 32
MAX_TOTAL_COLUMNS = 64
MAX_TYPES = 8
MAX_TOTAL_TYPES = 128
MAX_TEXT = 64
MAX_TEXT_UNITS = 768
MAX_DEPTH = 3
MAX_ROWS = 256
MAX_CELLS = 4096
EXTRA_KEYS = {'storage_contract', 'reader_validation', 'native_compatibility'}


def source_binding(provenance):
    canonical = json.dumps(provenance['sources'], ensure_ascii=True, sort_keys=True,
                           separators=(',', ':'), allow_nan=False).encode('ascii')
    return hashlib.sha256(canonical).hexdigest()


def shape_text(value):
    # BMP-only strings give the same counted units in Python and native BSL.
    # Quotes/backslashes are allowed; the bound includes their JSON escapes.
    require(type(value) is str and len(value) >= 1, 'invalid_marker')
    require(len(value) <= MAX_TEXT, 'artifact_limit')
    require(all(32 <= ord(char) <= 0xffff and not 0xd800 <= ord(char) <= 0xdfff
                    for char in value), 'invalid_marker')
    return len(value)


def validate_shape(shape):
    exact(shape, {'schema', 'target', 'nesting', 'tables'})
    require(type(shape['schema']) is int and shape['schema'] == 1
            and shape['target'] == TARGET and shape['nesting'] == 'observed_value_tables_only', 'invalid_marker')
    tables = shape['tables']
    require(type(tables) is list and 1 <= len(tables) <= MAX_TABLES, 'artifact_limit')
    depths = []; total_columns = total_types = units = 0
    for position, table in enumerate(tables):
        exact(table, {'parent', 'via_column', 'columns'})
        if position == 0:
            require(table['parent'] is None and table['via_column'] is None, 'invalid_marker')
            depth = 0
        else:
            parent = table['parent']; column = table['via_column']
            require(integer(parent, position - 1) and
                    integer(column, len(tables[parent]['columns']) - 1), 'invalid_marker')
            depth = depths[parent] + 1
        require(depth <= MAX_DEPTH, 'artifact_limit'); depths.append(depth)
        columns = table['columns']
        require(type(columns) is list and 0 <= len(columns) <= MAX_COLUMNS, 'artifact_limit')
        total_columns += len(columns)
        require(total_columns <= MAX_TOTAL_COLUMNS, 'artifact_limit')
        names = set()
        for column in columns:
            exact(column, {'name', 'types'})
            units += shape_text(column['name'])
            require(column['name'] not in names, 'invalid_marker'); names.add(column['name'])
            types = column['types']
            require(type(types) is list and len(types) <= MAX_TYPES, 'artifact_limit')
            total_types += len(types)
            require(total_types <= MAX_TOTAL_TYPES, 'artifact_limit')
            for declared in types:
                units += shape_text(declared)
            require(len(set(types)) == len(types), 'invalid_marker')
            require(units <= MAX_TEXT_UNITS, 'artifact_limit')
    require(len(encode(shape)) <= MAX_SHAPE_BYTES, 'artifact_limit')
    return shape


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, storage_contract=None,
                  reader_validation='not_run', native_compatibility='not_claimed')
    return report


def bind_capture(data, report):
    """Called only after fresh completion and result validation of the audit clone."""
    require(data['operation'] == 'audit_contract' and data['nonce'] == report['nonce']
            and data['metadata_version'] == 1, 'invalid_marker')
    validate_shape(data['storage_shape'])
    baseline = report['snapshots'][0]
    require(baseline['id'] == 'baseline', 'invalid_marker')
    return {'schema': 1, 'status': 'shape_captured', 'operation': 'audit_contract',
        'nonce': report['nonce'], 'token': data['token'],
        'source_manifest_sha256': source_binding(report['provenance']),
        'snapshot': 'baseline', 'snapshot_sha256': baseline['physical']['sha256'],
        'actual_version': data['actual_version'], 'shape': data['storage_shape']}


def discard_capture(report):
    if report.get('schema') == SCHEMA:
        report['storage_contract'] = None


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require(type(report) is dict and type(report.get('schema')) is int
            and report['schema'] == SCHEMA and report.get('lane') == LANE)
    require(EXTRA_KEYS <= set(report) and report['reader_validation'] == 'not_run'
            and report['native_compatibility'] == 'not_claimed')
    # The exact source inventory is essential to the whole-report size proof.
    from inputs import LEGACY_V3_SOURCE_FILES
    require(type(provenance.get('sources')) is dict
            and set(provenance['sources']) == set(LEGACY_V3_SOURCE_FILES), 'provenance_mismatch')
    require(provenance.get('image') == lifecycle.IMAGE
            and provenance.get('platform') == 'linux/amd64'
            and provenance.get('locale') == 'ru_RU.UTF-8'
            and provenance.get('timezone') == 'Etc/UTC', 'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['storage_contract']
    if report['status'] != 'ok':
        require(capture is None)
        return report
    exact(capture, {'schema', 'status', 'operation', 'nonce', 'token',
        'source_manifest_sha256', 'snapshot', 'snapshot_sha256', 'actual_version', 'shape'})
    require(type(capture['schema']) is int and capture['schema'] == 1
            and capture['status'] == 'shape_captured' and capture['operation'] == 'audit_contract'
            and capture['nonce'] == nonce and type(capture['token']) is str
            and re.fullmatch('[0-9a-f]{32}', capture['token']) is not None)
    require(capture['source_manifest_sha256'] == source_binding(provenance)
            and digest(capture['source_manifest_sha256'])
            and capture['snapshot'] == 'baseline'
            and capture['snapshot_sha256'] == report['snapshots'][0]['physical']['sha256']
            and capture['actual_version'] == report['provenance']['actual_version'] == lifecycle.VERSION)
    required = report['cleanup'] if final else {key: report['cleanup'][key]
        for key in ('native_processes_stopped', 'raw_files_removed')}
    require(all(required.values()))
    validate_shape(capture['shape'])
    return report
