"""Finite Copy observer diagnostics; never raw error text or semantic answers.

Pass the exact source-bound Copy contract's validate_payload callable. This keeps
host and staged imports explicit without importing arbitrary paths or modules.
"""
MAX_OUTPUT = 8192
CASE_COUNT = 9
CALIBRATION_CODES = 'IARMDE'
OBSERVER_STAGES = 'BIOM'
DIAGNOSTIC_CATEGORIES = (
    'invalid_type', 'output_limit', 'encoding', 'record_count', 'calibration',
    'record_shape', 'observer_b', 'observer_i', 'observer_o', 'observer_m',
    'payload_contract',
)
CASE_CATEGORIES = ('record_shape', 'observer_b', 'observer_i', 'observer_o',
                   'observer_m', 'payload_contract')
GLOBAL_CATEGORIES = ('invalid_type', 'output_limit', 'encoding', 'record_count')
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
        if len(payload) == 2 and payload[:1] == b'X' and chr(payload[1]) in OBSERVER_STAGES:
            return result('observer_' + chr(payload[1]).lower(), case)
        try:
            validate_payload(payload, case)
        except observation_error:
            return result('payload_contract', case)
    return None
