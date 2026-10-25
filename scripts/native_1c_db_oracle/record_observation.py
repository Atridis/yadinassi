"""Finite owned-fixture metadata/declaration observation, never row acceptance.

The complete catalog is parsed independently before its single selected table
is projected. Declaration order is preserved, not interpreted as offsets;
native type text and all logical names remain uninterpreted observations.
Historical marker/report validators are reused on strictly checked copies and
remain closed to this operation and its payload.
"""
from __future__ import annotations

import re
from bisect import bisect_right

import comparison
import protocol as lifecycle
from contract import source_binding
from protocol import decode, digest, encode, exact, integer, require
from snapshots import MAX_FILE_BYTES, OracleError

SCHEMA = 5
LANE = 'owned_record_metadata_observation_v1'
CAPTURE_SCHEMA = 6
OPERATION = 'audit_record_metadata'
FAILURE_KIND = 'record_observation_failed'
PROJECTION_MODE = 'dbms_names_true'
COMPARISON_POLICY = 'exact_tables_ascii_fields_v1'
TARGET = 'Справочник.NativeOracleItems'
VERDICT = comparison.VERDICT
METADATA_VERDICT = 'metadata_projection_captured'
MAX_FIELDS = 16
MAX_TEXT = 64
MAX_TEXT_UNITS = 768
MAX_TOKEN = 8
MAX_INTEGER = 65535
MAX_NATIVE_BYTES = 6144
MAX_PHYSICAL_BYTES = 4096
MAX_CAPTURE_BYTES = 12288
READER_SOURCE = comparison.READER_SOURCE
MODULE_SOURCE = 'scripts/native_1c_db_oracle/record_observation.py'

# Frozen Unicode 15.0.0 printable BMP intervals, shared with the native helper.
# Do not silently widen observation syntax when the host Unicode version changes.
PRINTABLE_BMP_RANGES = (
    (32, 126), (161, 172), (174, 887), (890, 895), (900, 906), (908, 908),
    (910, 929), (931, 1327), (1329, 1366), (1369, 1418), (1421, 1423), (1425, 1479),
    (1488, 1514), (1519, 1524), (1542, 1563), (1565, 1756), (1758, 1805), (1808, 1866),
    (1869, 1969), (1984, 2042), (2045, 2093), (2096, 2110), (2112, 2139), (2142, 2142),
    (2144, 2154), (2160, 2190), (2200, 2273), (2275, 2435), (2437, 2444), (2447, 2448),
    (2451, 2472), (2474, 2480), (2482, 2482), (2486, 2489), (2492, 2500), (2503, 2504),
    (2507, 2510), (2519, 2519), (2524, 2525), (2527, 2531), (2534, 2558), (2561, 2563),
    (2565, 2570), (2575, 2576), (2579, 2600), (2602, 2608), (2610, 2611), (2613, 2614),
    (2616, 2617), (2620, 2620), (2622, 2626), (2631, 2632), (2635, 2637), (2641, 2641),
    (2649, 2652), (2654, 2654), (2662, 2678), (2689, 2691), (2693, 2701), (2703, 2705),
    (2707, 2728), (2730, 2736), (2738, 2739), (2741, 2745), (2748, 2757), (2759, 2761),
    (2763, 2765), (2768, 2768), (2784, 2787), (2790, 2801), (2809, 2815), (2817, 2819),
    (2821, 2828), (2831, 2832), (2835, 2856), (2858, 2864), (2866, 2867), (2869, 2873),
    (2876, 2884), (2887, 2888), (2891, 2893), (2901, 2903), (2908, 2909), (2911, 2915),
    (2918, 2935), (2946, 2947), (2949, 2954), (2958, 2960), (2962, 2965), (2969, 2970),
    (2972, 2972), (2974, 2975), (2979, 2980), (2984, 2986), (2990, 3001), (3006, 3010),
    (3014, 3016), (3018, 3021), (3024, 3024), (3031, 3031), (3046, 3066), (3072, 3084),
    (3086, 3088), (3090, 3112), (3114, 3129), (3132, 3140), (3142, 3144), (3146, 3149),
    (3157, 3158), (3160, 3162), (3165, 3165), (3168, 3171), (3174, 3183), (3191, 3212),
    (3214, 3216), (3218, 3240), (3242, 3251), (3253, 3257), (3260, 3268), (3270, 3272),
    (3274, 3277), (3285, 3286), (3293, 3294), (3296, 3299), (3302, 3311), (3313, 3315),
    (3328, 3340), (3342, 3344), (3346, 3396), (3398, 3400), (3402, 3407), (3412, 3427),
    (3430, 3455), (3457, 3459), (3461, 3478), (3482, 3505), (3507, 3515), (3517, 3517),
    (3520, 3526), (3530, 3530), (3535, 3540), (3542, 3542), (3544, 3551), (3558, 3567),
    (3570, 3572), (3585, 3642), (3647, 3675), (3713, 3714), (3716, 3716), (3718, 3722),
    (3724, 3747), (3749, 3749), (3751, 3773), (3776, 3780), (3782, 3782), (3784, 3790),
    (3792, 3801), (3804, 3807), (3840, 3911), (3913, 3948), (3953, 3991), (3993, 4028),
    (4030, 4044), (4046, 4058), (4096, 4293), (4295, 4295), (4301, 4301), (4304, 4680),
    (4682, 4685), (4688, 4694), (4696, 4696), (4698, 4701), (4704, 4744), (4746, 4749),
    (4752, 4784), (4786, 4789), (4792, 4798), (4800, 4800), (4802, 4805), (4808, 4822),
    (4824, 4880), (4882, 4885), (4888, 4954), (4957, 4988), (4992, 5017), (5024, 5109),
    (5112, 5117), (5120, 5759), (5761, 5788), (5792, 5880), (5888, 5909), (5919, 5942),
    (5952, 5971), (5984, 5996), (5998, 6000), (6002, 6003), (6016, 6109), (6112, 6121),
    (6128, 6137), (6144, 6157), (6159, 6169), (6176, 6264), (6272, 6314), (6320, 6389),
    (6400, 6430), (6432, 6443), (6448, 6459), (6464, 6464), (6468, 6509), (6512, 6516),
    (6528, 6571), (6576, 6601), (6608, 6618), (6622, 6683), (6686, 6750), (6752, 6780),
    (6783, 6793), (6800, 6809), (6816, 6829), (6832, 6862), (6912, 6988), (6992, 7038),
    (7040, 7155), (7164, 7223), (7227, 7241), (7245, 7304), (7312, 7354), (7357, 7367),
    (7376, 7418), (7424, 7957), (7960, 7965), (7968, 8005), (8008, 8013), (8016, 8023),
    (8025, 8025), (8027, 8027), (8029, 8029), (8031, 8061), (8064, 8116), (8118, 8132),
    (8134, 8147), (8150, 8155), (8157, 8175), (8178, 8180), (8182, 8190), (8208, 8231),
    (8240, 8286), (8304, 8305), (8308, 8334), (8336, 8348), (8352, 8384), (8400, 8432),
    (8448, 8587), (8592, 9254), (9280, 9290), (9312, 11123), (11126, 11157), (11159, 11507),
    (11513, 11557), (11559, 11559), (11565, 11565), (11568, 11623), (11631, 11632), (11647, 11670),
    (11680, 11686), (11688, 11694), (11696, 11702), (11704, 11710), (11712, 11718), (11720, 11726),
    (11728, 11734), (11736, 11742), (11744, 11869), (11904, 11929), (11931, 12019), (12032, 12245),
    (12272, 12283), (12289, 12351), (12353, 12438), (12441, 12543), (12549, 12591), (12593, 12686),
    (12688, 12771), (12784, 12830), (12832, 42124), (42128, 42182), (42192, 42539), (42560, 42743),
    (42752, 42954), (42960, 42961), (42963, 42963), (42965, 42969), (42994, 43052), (43056, 43065),
    (43072, 43127), (43136, 43205), (43214, 43225), (43232, 43347), (43359, 43388), (43392, 43469),
    (43471, 43481), (43486, 43518), (43520, 43574), (43584, 43597), (43600, 43609), (43612, 43714),
    (43739, 43766), (43777, 43782), (43785, 43790), (43793, 43798), (43808, 43814), (43816, 43822),
    (43824, 43883), (43888, 44013), (44016, 44025), (44032, 55203), (55216, 55238), (55243, 55291),
    (63744, 64109), (64112, 64217), (64256, 64262), (64275, 64279), (64285, 64310), (64312, 64316),
    (64318, 64318), (64320, 64321), (64323, 64324), (64326, 64450), (64467, 64911), (64914, 64967),
    (64975, 64975), (65008, 65049), (65056, 65106), (65108, 65126), (65128, 65131), (65136, 65140),
    (65142, 65276), (65281, 65470), (65474, 65479), (65482, 65487), (65490, 65495), (65498, 65500),
    (65504, 65510), (65512, 65518), (65532, 65533),
)
PRINTABLE_BMP_BOUNDARIES = tuple(endpoint for lower, upper in PRINTABLE_BMP_RANGES
    for endpoint in (lower, upper + 1))
EXTRA_KEYS = {'projection_mode', 'comparison_policy', 'record_observation',
    'reader_validation', 'metadata_validation', 'mapping_validation',
    'layout_validation', 'record_validation', 'native_compatibility'}
BINDING_KEYS = comparison.BINDING_KEYS
RECORD_PHASES = frozenset(('record_call', 'record_scan', 'record_limit'))
PHASES = frozenset(('marker', 'metadata', 'identity', 'serialize')) | RECORD_PHASES
PHASE_MAP = dict(zip(('record_call', 'record_scan', 'record_limit'),
                    ('contract_call', 'contract_scan', 'contract_limit')))
DIAGNOSTICS = {key: frozenset(value) for key, value in comparison.DIAGNOSTICS.items()}
DIAGNOSTICS['unsupported_layout'] |= {'declaration_token', 'declaration_integer'}
DIAGNOSTICS['structural_rejection'] |= {'invalid_declaration'}


class ObservationFailure(OracleError):
    """Reviewed finite error only; never carries a raw marker or reader object."""

    def __init__(self, category, code):
        require(type(category) is str and category in DIAGNOSTICS
                and type(code) is str and code in DIAGNOSTICS[category], 'unexpected_failure')
        super().__init__('logical_mismatch')
        self.category, self.code = category, code


def reader_failure(error):
    classified = comparison.reader_failure(error)
    return ObservationFailure(classified.category, classified.code)


def text_units(value, *, storage=False):
    require(type(value) is str, 'invalid_marker')
    require(len(value) <= MAX_TEXT, 'artifact_limit')
    require(all(bisect_right(PRINTABLE_BMP_BOUNDARIES, ord(char)) % 2 == 1
                for char in value), 'invalid_marker')
    if storage:
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', value) is not None, 'invalid_marker')
    return len(value)


def field_keys(names):
    """ASCII-only ephemeral keys; neither original projection is normalized."""
    raw = set(); keys = set()
    for name in names:
        text_units(name, storage=True)
        if name in raw:
            raise ObservationFailure('name_mismatch', 'duplicate_field')
        raw.add(name)
        key = ''.join(chr(ord(char) - 32) if 'a' <= char <= 'z' else char for char in name)
        if key in keys:
            raise ObservationFailure('name_mismatch', 'ascii_field_key_collision')
        keys.add(key)
    return tuple(sorted(keys))


def validate_native_projection(value):
    exact(value, {'schema', 'target', 'table'})
    require(type(value['schema']) is int and value['schema'] == 1
            and value['target'] == TARGET, 'invalid_marker')
    table = value['table']
    exact(table, {'storage_name', 'logical_name', 'metadata_name', 'fields'})
    fields = table['fields']
    require(type(fields) is list and 1 <= len(fields) <= MAX_FIELDS, 'artifact_limit')
    units = text_units(table['storage_name'], storage=True)
    units += text_units(table['logical_name']) + text_units(table['metadata_name'])
    for field in fields:
        exact(field, {'storage_name', 'logical_name', 'metadata_name', 'type_text'})
        units += text_units(field['storage_name'], storage=True)
        for key in ('logical_name', 'metadata_name', 'type_text'):
            units += text_units(field[key])
        require(units <= MAX_TEXT_UNITS, 'artifact_limit')
    field_keys([field['storage_name'] for field in fields])
    require(len(encode(value)) <= MAX_NATIVE_BYTES, 'artifact_limit')
    return value


def declaration_token(value):
    # Empty tokens are observed absence, not an inferred type/lock/case policy.
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9_]{0,8}', value) is None:
        raise ObservationFailure('unsupported_layout', 'declaration_token')
    return len(value)


def validate_physical_projection(value):
    exact(value, {'schema', 'target', 'table'})
    require(type(value['schema']) is int and value['schema'] == 1
            and value['target'] == TARGET, 'invalid_marker')
    table = value['table']
    exact(table, {'name', 'record_lock_token', 'fields'})
    fields = table['fields']
    require(type(fields) is list and 1 <= len(fields) <= MAX_FIELDS, 'artifact_limit')
    units = text_units(table['name'], storage=True) + declaration_token(table['record_lock_token'])
    for field in fields:
        exact(field, {'name', 'type_token', 'nullability', 'length', 'precision', 'case_token'})
        units += text_units(field['name'], storage=True)
        units += declaration_token(field['type_token']) + declaration_token(field['case_token'])
        if not all(integer(field[key], MAX_INTEGER) for key in ('nullability', 'length', 'precision')):
            raise ObservationFailure('unsupported_layout', 'declaration_integer')
        require(units <= MAX_TEXT_UNITS, 'artifact_limit')
    field_keys([field['name'] for field in fields])
    require(len(encode(value)) <= MAX_PHYSICAL_BYTES, 'artifact_limit')
    return value


def validate_names_bijection(native, physical):
    validate_native_projection(native)
    validate_physical_projection(physical)
    if native['table']['storage_name'] != physical['table']['name']:
        raise ObservationFailure('name_mismatch', 'missing_table')
    left = field_keys([field['storage_name'] for field in native['table']['fields']])
    right = field_keys([field['name'] for field in physical['table']['fields']])
    if left != right:
        raise ObservationFailure('name_mismatch', 'field_names_differ')


def project_catalog(catalog, native):
    """Project only completed reader output, never Files, indexes, AST or rows."""
    validate_native_projection(native)
    try:
        tables = catalog.tables
        require(type(tables) is tuple and len(tables) <= comparison.CENSUS_LIMITS.max_tables,
                'artifact_limit')
        selected = None; matches = 0
        for table in tables:
            if table.name == native['table']['storage_name']:
                matches += 1; selected = table
        if not matches:
            raise ObservationFailure('name_mismatch', 'missing_table')
        if matches != 1:
            raise ObservationFailure('name_mismatch', 'duplicate_table')
        fields = selected.fields
        require(type(fields) is tuple, 'invalid_marker')
        if not fields:
            raise ObservationFailure('name_mismatch', 'field_names_differ')
        require(len(fields) <= MAX_FIELDS, 'artifact_limit')
        # Validate each scalar before constructing the complete bounded output.
        units = text_units(selected.name, storage=True) + declaration_token(selected.recordlock)
        projected = []
        for field in fields:
            name, type_token, case_token = field.name, field.type_name, field.case_marker
            units += text_units(name, storage=True)
            units += declaration_token(type_token) + declaration_token(case_token)
            require(units <= MAX_TEXT_UNITS, 'artifact_limit')
            numbers = (field.null_marker, field.declared_length, field.precision)
            if not all(integer(item, MAX_INTEGER) for item in numbers):
                raise ObservationFailure('unsupported_layout', 'declaration_integer')
            projected.append({'name': name, 'type_token': type_token,
                'nullability': numbers[0], 'length': numbers[1], 'precision': numbers[2],
                'case_token': case_token})
        physical = {'schema': 1, 'target': TARGET, 'table': {'name': selected.name,
                    'record_lock_token': selected.recordlock, 'fields': projected}}
        validate_names_bijection(native, physical)
        return native, physical
    except ObservationFailure:
        raise
    except OracleError as error:
        raise ObservationFailure('resource_limit' if error.kind == 'artifact_limit' else 'structural_rejection',
            'projection_limit' if error.kind == 'artifact_limit' else 'invalid_declaration') from None


def marker(raw, *, nonce, token, operation=OPERATION):
    require(operation == OPERATION and type(nonce) is str and type(token) is str
            and re.fullmatch('[0-9a-f]{32}', nonce) is not None
            and re.fullmatch('[0-9a-f]{32}', token) is not None, 'invalid_marker')
    data = decode(raw)
    exact(data, lifecycle.MARKER_KEYS | {'record_metadata'})
    require(data['operation'] == OPERATION, 'invalid_marker')
    base = {key: value for key, value in data.items() if key != 'record_metadata'}
    base['operation'] = 'audit'
    lifecycle.marker(encode(base), nonce=nonce, token=token, operation='audit')
    require(data['metadata_version'] == 1, 'logical_mismatch')
    validate_native_projection(data['record_metadata'])
    return data


def completion_marker(raw, *, nonce, token, operation=OPERATION):
    if operation != OPERATION:
        return lifecycle.completion_marker(raw, nonce=nonce, token=token, operation=operation)
    require(type(raw) is bytes and 0 < len(raw) <= 4096, 'invalid_marker')
    data = decode(raw)
    exact(data, {'schema', 'nonce', 'token', 'operation', 'phase', 'status'})
    require(type(data['operation']) is str and data['operation'] in (OPERATION, 'dispatch'), 'invalid_marker')
    require(type(data['phase']) is str and (data['phase'] == 'complete' or data['phase'] in
            (PHASES if data['operation'] == OPERATION else lifecycle.BSL_OPERATION_PHASES['dispatch'])),
            'invalid_marker')
    mapped = dict(data)
    if mapped['operation'] == OPERATION:
        mapped['operation'] = 'audit_contract'
    mapped['phase'] = PHASE_MAP.get(mapped['phase'], mapped['phase'])
    lifecycle.completion_marker(encode(mapped), nonce=nonce, token=token, operation='audit_contract')
    return data


def _mapped_failure_context(value, stage):
    require(type(value) is dict)
    mapped = dict(value)
    if value.get('operation') == 'enterprise_' + OPERATION:
        phase = value.get('bsl_phase')
        require(phase is None or (type(phase) is str and phase in
                PHASES | lifecycle.BSL_OPERATION_PHASES['dispatch']))
        mapped['operation'] = 'enterprise_audit_contract'
        mapped['bsl_phase'] = PHASE_MAP.get(phase, phase)
    else:
        require(value.get('operation') != 'enterprise_audit_contract')
    lifecycle.validate_failure_context(mapped, stage)
    return mapped


def validate_failure_context(value, stage):
    _mapped_failure_context(value, stage)
    return value


def require_observation_policy(report):
    require(type(report) is dict and type(report.get('schema')) is int
            and report['schema'] == SCHEMA and report.get('lane') == LANE
            and report.get('projection_mode') == PROJECTION_MODE
            and report.get('comparison_policy') == COMPARISON_POLICY)


def empty_report(nonce, provenance):
    report = lifecycle.empty_report(nonce, provenance)
    report.update(schema=SCHEMA, lane=LANE, projection_mode=PROJECTION_MODE,
        comparison_policy=COMPARISON_POLICY, record_observation=None,
        reader_validation='not_run', metadata_validation='not_run',
        mapping_validation='not_run', layout_validation='not_run',
        record_validation='not_run', native_compatibility='not_claimed')
    return report


def _validate_binding(capture, report, *, nonce, provenance, final=False, cleanup=True):
    require(capture['operation'] == OPERATION and capture['nonce'] == nonce
            and type(capture['token']) is str and re.fullmatch('[0-9a-f]{32}', capture['token']) is not None)
    require(capture['source_manifest_sha256'] == source_binding(provenance)
            and digest(capture['source_manifest_sha256'])
            and capture['reader_source_sha256'] == provenance['sources'][READER_SOURCE]
            and digest(capture['reader_source_sha256'])
            and capture['actual_version'] == report['provenance']['actual_version'] == lifecycle.VERSION)
    origin = capture['origin']; postimage = capture['postimage']
    exact(origin, {'snapshot', 'clone', 'bytes', 'sha256'})
    exact(postimage, {'copy', 'binding', 'bytes', 'sha256', 'storage_version', 'page_size'})
    require(type(report['snapshots']) is list and report['snapshots']
            and report['snapshots'][0]['id'] == 'baseline', 'snapshot_changed')
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
    if cleanup:
        required = report['cleanup'] if final else {key: report['cleanup'][key]
            for key in ('native_processes_stopped', 'raw_files_removed')}
        require(all(value is True for value in required.values()))


def bind_capture(evidence, report):
    require_observation_policy(report)
    exact(evidence, {'marker', 'origin', 'postimage', 'reader'})
    require(type(evidence['marker']) is dict and 'token' in evidence['marker'], 'invalid_marker')
    data = marker(encode(evidence['marker']), nonce=report['nonce'], token=evidence['marker']['token'])
    require(type(report['snapshots']) is list and report['snapshots']
            and report['snapshots'][0]['id'] == 'baseline', 'snapshot_changed')
    baseline = report['snapshots'][0]['physical']; origin = evidence['origin']
    exact(origin, {'nonce', 'token', 'clone', 'bytes', 'sha256'})
    exact(evidence['postimage'], {'bytes', 'sha256'})
    require(origin['nonce'] == report['nonce'] and origin['token'] == data['token']
            and origin['clone'] == 'auditor' and type(origin['bytes']) is int
            and origin['bytes'] == baseline['bytes'] and origin['sha256'] == baseline['sha256'], 'snapshot_changed')
    native = validate_native_projection(data['record_metadata'])
    physical = validate_physical_projection(evidence['reader'])
    validate_names_bijection(native, physical)
    capture = {'schema': CAPTURE_SCHEMA, 'status': METADATA_VERDICT, 'projection_mode': PROJECTION_MODE,
        'comparison_policy': COMPARISON_POLICY, 'operation': OPERATION,
        'nonce': report['nonce'], 'token': data['token'],
        'source_manifest_sha256': source_binding(report['provenance']),
        'reader_source_sha256': report['provenance']['sources'][READER_SOURCE],
        'actual_version': data['actual_version'],
        'origin': {'snapshot': 'baseline', 'clone': 'auditor', 'bytes': origin['bytes'], 'sha256': origin['sha256']},
        'postimage': {'copy': 'auditor_frozen', 'binding': 'closed_post_audit_clone',
            'bytes': evidence['postimage']['bytes'], 'sha256': evidence['postimage']['sha256'],
            'storage_version': [8, 3, 8, 0], 'page_size': 8192},
        'native': native, 'reader': physical}
    _validate_binding(capture, report, nonce=report['nonce'], provenance=report['provenance'], cleanup=False)
    require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    return capture


def discard_capture(report, failure=None):
    if type(report.get('schema')) is not int or report['schema'] != SCHEMA:
        return
    previous = report.get('metadata_validation', 'not_run')
    previous_reader = report.get('reader_validation', 'not_run')
    old = report.get('record_observation')
    report['record_observation'] = None
    report['metadata_validation'] = ('discarded' if previous in (METADATA_VERDICT, 'discarded')
                                     else 'failed' if previous == 'failed' else 'not_run')
    report['reader_validation'] = ('discarded' if previous_reader in (VERDICT, 'discarded')
                                   else 'failed' if previous_reader == 'failed' else 'not_run')
    report.update(layout_validation='not_run', mapping_validation='not_run',
                  record_validation='not_run', native_compatibility='not_claimed')
    if type(failure) in (ObservationFailure, comparison.ComparisonFailure):
        old = {'schema': CAPTURE_SCHEMA, 'status': 'failed', 'category': failure.category, 'code': failure.code}
    if (report.get('status') == 'failed' and report.get('failure_kind') == FAILURE_KIND
            and report.get('failed_stage') == 'baseline' and type(old) is dict
            and set(old) == {'schema', 'status', 'category', 'code'}
            and type(old['schema']) is int and old['schema'] == CAPTURE_SCHEMA
            and old['status'] == 'failed' and type(old['category']) is str and old['category'] in DIAGNOSTICS
            and type(old['code']) is str and old['code'] in DIAGNOSTICS[old['category']]):
        report['record_observation'] = dict(old)
        report['metadata_validation'] = report['reader_validation'] = 'failed'


def validate_report(raw, *, nonce, provenance, final=False):
    report = decode(raw)
    require_observation_policy(report)
    require(EXTRA_KEYS <= set(report) and report['native_compatibility'] == 'not_claimed'
            and report['mapping_validation'] == 'not_run' and report['record_validation'] == 'not_run'
            and report['layout_validation'] in ('not_run', 'declarations_only')
            and report['metadata_validation'] in ('not_run', 'failed', 'discarded', METADATA_VERDICT)
            and report['reader_validation'] in ('not_run', 'failed', 'discarded', VERDICT))
    from inputs import RECORD_SOURCE_FILES
    require(type(provenance.get('sources')) is dict and set(provenance['sources']) == set(RECORD_SOURCE_FILES)
            and len(RECORD_SOURCE_FILES) == 21 and MODULE_SOURCE in RECORD_SOURCE_FILES, 'provenance_mismatch')
    require(provenance.get('image') == lifecycle.IMAGE and provenance.get('platform') == 'linux/amd64'
            and provenance.get('locale') == 'ru_RU.UTF-8' and provenance.get('timezone') == 'Etc/UTC',
            'provenance_mismatch')
    base = {key: value for key, value in report.items() if key not in EXTRA_KEYS}
    base.update(schema=lifecycle.SCHEMA, lane=lifecycle.LANE)
    require(report['failure_kind'] != 'catalog_comparison_failed')
    if report['failure_kind'] == FAILURE_KIND:
        base['failure_kind'] = 'catalog_comparison_failed'
    if 'failure_context' in report:
        base['failure_context'] = _mapped_failure_context(report['failure_context'], report['failed_stage'])
    lifecycle.validate_report(encode(base), nonce=nonce, provenance=provenance, final=final)
    capture = report['record_observation']
    if capture is not None:
        require(len(encode(capture)) <= MAX_CAPTURE_BYTES, 'artifact_limit')
    if report['status'] != 'ok':
        require(report['metadata_validation'] != METADATA_VERDICT and report['reader_validation'] != VERDICT
                and report['layout_validation'] == 'not_run')
        if report['failure_kind'] == FAILURE_KIND:
            require(report['failed_stage'] == 'baseline'
                    and [item['id'] for item in report['snapshots']] == ['baseline']
                    and report['metadata_validation'] == report['reader_validation'] == 'failed')
            exact(capture, {'schema', 'status', 'category', 'code'})
            require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA
                    and capture['status'] == 'failed' and type(capture['category']) is str
                    and capture['category'] in DIAGNOSTICS and type(capture['code']) is str
                    and capture['code'] in DIAGNOSTICS[capture['category']])
        else:
            require(capture is None)
        return report
    require(report['metadata_validation'] == METADATA_VERDICT and report['reader_validation'] == VERDICT
            and report['layout_validation'] == 'declarations_only')
    exact(capture, {'schema', 'status', 'projection_mode', 'comparison_policy', 'native', 'reader'} | BINDING_KEYS)
    require(type(capture['schema']) is int and capture['schema'] == CAPTURE_SCHEMA
            and capture['status'] == METADATA_VERDICT and capture['projection_mode'] == PROJECTION_MODE
            and capture['comparison_policy'] == COMPARISON_POLICY)
    _validate_binding(capture, report, nonce=nonce, provenance=provenance, final=final)
    validate_names_bijection(capture['native'], capture['reader'])
    return report
