"""Finite Copy observer diagnostics; never raw error text or semantic answers.

Pass the exact source-bound Copy contract's validate_payload callable. This keeps
host and staged imports explicit without importing arbitrary paths or modules.
"""
MAX_OUTPUT = 8192
CASE_COUNT = 9
CALIBRATION_CODES = 'IARMDE'
OBSERVER_STAGES = 'BIOM'
CASE5_STEPS = tuple(f'{i:02}' for i in range(1, 19))
IDENTITY_CATEGORIES = tuple('identity_' + stage.lower() for stage in OBSERVER_STAGES)
CASE5_CATEGORIES = tuple('case5_step' + step + suffix for step in CASE5_STEPS for suffix in ('', '_identity'))
DETAIL_REASONS = {'G01': 'registry_62', 'G02': 'registry_over62', 'G03': 'number_bound', 'G04': 'word_vocabulary', 'G05': 'cell_shape', 'G06': 'inner_array_shape', 'G07': 'flatten_row_limit', 'G08': 'result_type', 'G09': 'column_limit', 'G10': 'column_type', 'G11': 'types_count', 'G12': 'date_qualifier', 'G13': 'collection_parent', 'G14': 'root_parent', 'G15': 'exception_result', 'S01': 'snapshot_01', 'S02': 'snapshot_02', 'S03': 'snapshot_03', 'S04': 'snapshot_04', 'S05': 'snapshot_05', 'S06': 'snapshot_06', 'S07': 'snapshot_07', 'S08': 'snapshot_08', 'S09': 'snapshot_09', 'S10': 'snapshot_10', 'S11': 'snapshot_11', 'S12': 'snapshot_12', 'S13': 'snapshot_13', 'S14': 'snapshot_14', 'S15': 'snapshot_15', 'S16': 'snapshot_16', 'S17': 'snapshot_17', 'S18': 'snapshot_18', 'S19': 'snapshot_19', 'S20': 'snapshot_20', 'S21': 'snapshot_21', 'S22': 'snapshot_22', 'S23': 'snapshot_23', 'S24': 'snapshot_24', 'S25': 'snapshot_25', 'S26': 'snapshot_26', 'S27': 'snapshot_27', 'S28': 'snapshot_28', 'S29': 'snapshot_29', 'S30': 'snapshot_30', 'S31': 'snapshot_31', 'S32': 'snapshot_32', 'S33': 'snapshot_33', 'S34': 'snapshot_34', 'S35': 'snapshot_35', 'F01': 'flatten_01', 'F02': 'flatten_02', 'F03': 'flatten_03'}
DETAIL_CATEGORIES = tuple('detail_' + stage.lower() + '_' + reason for stage in OBSERVER_STAGES for reason in DETAIL_REASONS.values())
CASE5_CATEGORIES += tuple('case5_step' + step + '_' + reason for step in CASE5_STEPS for reason in DETAIL_REASONS.values())
DIAGNOSTIC_CATEGORIES = (
    'access_probe', 'invalid_type', 'output_limit', 'encoding', 'record_count', 'calibration',
    'record_shape', 'observer_b', 'observer_i', 'observer_o', 'observer_m',
    'payload_contract',
) + IDENTITY_CATEGORIES + CASE5_CATEGORIES + DETAIL_CATEGORIES
CASE_CATEGORIES = ('record_shape', 'observer_b', 'observer_i', 'observer_o',
                   'observer_m', 'payload_contract') + IDENTITY_CATEGORIES + CASE5_CATEGORIES + DETAIL_CATEGORIES
GLOBAL_CATEGORIES = ('access_probe', 'invalid_type', 'output_limit', 'encoding', 'record_count')
# Client message characters; LF is framing, not inside a captured message.
MESSAGE_CHARACTERS = frozenset('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz -.:[]_/')


class DiagnosticError(ValueError):
    pass


def validate_diagnostic(value):
    if value is None:
        return
    if type(value) is not dict or set(value) != {'site', 'case', 'category', 'calibration'}:
        raise DiagnosticError('tree_copy_diagnostic_invalid')
    site, case, category, calibration = (value[k] for k in ('site', 'case', 'category', 'calibration'))
    valid = (type(site) is str and site in ('server', 'client')
             and type(category) is str and category in DIAGNOSTIC_CATEGORIES
             and (case is None or type(case) is int and 0 <= case <= CASE_COUNT)
             and (calibration is None or type(calibration) is str
                  and len(calibration) == 1 and calibration in CALIBRATION_CODES))
    if not valid:
        raise DiagnosticError('tree_copy_diagnostic_invalid')
    if ((category in GLOBAL_CATEGORIES and case is not None)
            or (category == 'calibration' and case != 0)
            or (category in CASE_CATEGORIES and (type(case) is not int or not 1 <= case <= CASE_COUNT))
            or (category in CASE5_CATEGORIES and case != 5)
            or (category != 'calibration' and calibration is not None)):
        raise DiagnosticError('tree_copy_diagnostic_invalid')


def observation_diagnostic(raw, site, validate_payload, observation_error):
    """Return None only for a well-formed complete observation.

    observation_error must be the exact source-bound contract's ObservationError
    class. Unexpected programmer/system exceptions are intentionally not hidden.
    """
    if type(site) is not str or site not in ('server', 'client'):
        raise DiagnosticError('tree_copy_diagnostic_invalid')

    def result(category, case=None, calibration=None):
        value = {'site': site, 'case': case, 'category': category, 'calibration': calibration}
        validate_diagnostic(value)
        return value

    if type(raw) is not bytes:
        return result('invalid_type')
    if len(raw) > MAX_OUTPUT:
        return result('output_limit')
    if any(c != 10 and chr(c) not in MESSAGE_CHARACTERS for c in raw):
        return result('encoding')
    lines = raw.splitlines(keepends=True)
    if len(lines) != CASE_COUNT + 1:
        return result('record_count')
    if lines[0] != b'TC-C: [-]\n':
        code = None
        if (len(lines[0]) == 10 and lines[0].startswith(b'TC-C: [')
                and lines[0].endswith(b']\n')
                and chr(lines[0][7]) in CALIBRATION_CODES):
            code = chr(lines[0][7])
        return result('calibration', 0, code)
    for case, line in enumerate(lines[1:], 1):
        prefix = f'TC-{case}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n'):
            return result('record_shape', case)
        payload = line[len(prefix):-2]
        if payload.startswith(b'XM') and len(payload) >= 7:
            step, code = payload[2:4].decode('ascii'), payload[4:].decode('ascii')
            if case == 5 and step in CASE5_STEPS and code in DETAIL_REASONS:
                return result('case5_step' + step + '_' + DETAIL_REASONS[code], case)
        if len(payload) >= 5 and payload[:1] == b'X' and chr(payload[1]) in OBSERVER_STAGES:
            code = payload[2:].decode('ascii')
            if code in DETAIL_REASONS:
                return result('detail_' + chr(payload[1]).lower() + '_' + DETAIL_REASONS[code], case)
        if case == 5 and payload in {('XM' + step + suffix).encode() for step in CASE5_STEPS for suffix in ('', 'I')}:
            return result('case5_step' + payload[2:4].decode() + ('_identity' if payload.endswith(b'I') else ''), case)
        if len(payload) == 3 and payload[:1] == b'X' and payload[-1:] == b'I' and chr(payload[1]) in OBSERVER_STAGES:
            return result('identity_' + chr(payload[1]).lower(), case)
        if len(payload) == 2 and payload[:1] == b'X' and chr(payload[1]) in OBSERVER_STAGES:
            return result('observer_' + chr(payload[1]).lower(), case)
        try:
            validate_payload(payload, case)
        except observation_error:
            return result('payload_contract', case)
    return None
