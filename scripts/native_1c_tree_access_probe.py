"""Closed TC-P grammar. Valid evidence shape is not wrapper identity success."""
CASE_NAMES = (
    'number_equal', 'number_unequal', 'string_equal', 'string_unequal',
    'tree_alias', 'tree_distinct', 'array_alias', 'array_distinct',
    'row_alias', 'row_repeated', 'row_distinct',
    'root_rows_alias', 'root_rows_repeated', 'root_rows_distinct',
    'child_rows_alias', 'child_rows_repeated', 'child_rows_distinct',
    'columns_alias', 'columns_repeated', 'columns_distinct',
    'column_alias', 'column_repeated', 'column_distinct',
)
CASE_COUNT = 23
SCALAR_CONTROLS = b'TFTF'
PREFIX = b'TC-P: ['
SUFFIX = b']\n'
MAX_RECORD_BYTES = 32


class ProbeError(ValueError):
    pass


def parse_payload(payload):
    if type(payload) is not bytes:
        raise ProbeError('tree_access_probe_invalid')
    if payload == b'B':
        return {'setup': 'failed', 'outcomes': (), 'scalar_controls_valid': None}
    if len(payload) != CASE_COUNT or any(c not in b'TFEA' for c in payload):
        raise ProbeError('tree_access_probe_invalid')
    return {'setup': 'ok', 'outcomes': tuple(payload.decode('ascii')),
            'scalar_controls_valid': payload[:4] == SCALAR_CONTROLS}


def parse_record(raw):
    if (type(raw) is not bytes or len(raw) > MAX_RECORD_BYTES
            or not raw.startswith(PREFIX) or not raw.endswith(SUFFIX)):
        raise ProbeError('tree_access_probe_invalid')
    return parse_payload(raw[len(PREFIX):-len(SUFFIX)])


def scalar_controls_valid(record):
    """False for observed bad controls/setup, raises only for malformed records."""
    return parse_record(record)['scalar_controls_valid'] is True


def split_capture(raw):
    """Strict full capture framing; main semantics are validated separately."""
    if (type(raw) is not bytes or not 0 < len(raw) <= 8192
            or any(c != 10 and not 32 <= c <= 126 for c in raw)):
        raise ProbeError('tree_access_probe_invalid')
    lines = raw.splitlines(keepends=True)
    if len(lines) != 11:
        raise ProbeError('tree_access_probe_invalid')
    parse_record(lines[0])
    for i, line in enumerate(lines[1:]):
        prefix = b'TC-C2: [' if i == 0 else f'TC-{i}: ['.encode('ascii')
        if not line.startswith(prefix) or not line.endswith(b']\n'):
            raise ProbeError('tree_access_probe_invalid')
    return lines[0], b''.join(lines[1:])


def witness(raw, site, nonce, source_sha256, module_sha256):
    import hashlib
    record, main = split_capture(raw)
    value = dict(schema='native-1c-tree-access-probe-v1', site=site, nonce=nonce,
                 source_sha256=source_sha256, module_sha256=module_sha256,
                 capture_sha256=hashlib.sha256(raw).hexdigest(), capture_size=len(raw),
                 message_count=11, main_sha256=hashlib.sha256(main).hexdigest(),
                 main_size=len(main), record=record.decode('ascii'),
                 controls_valid=scalar_controls_valid(record))
    validate_witness(value, site, nonce, source_sha256, module_sha256)
    return value


def validate_witness(value, site, nonce, source_sha256, module_sha256):
    import re
    keys = {'schema','site','nonce','source_sha256','module_sha256','capture_sha256',
            'capture_size','message_count','main_sha256','main_size','record','controls_valid'}
    def need(ok):
        if not ok:
            raise ProbeError('tree_access_probe_invalid')
    need(type(value) is dict and set(value) == keys)
    need(type(site) is str and site in ('server','client') and value['site'] == site)
    need(type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) is not None and value['nonce'] == nonce)
    need(value['schema'] == 'native-1c-tree-access-probe-v1')
    for key in ('source_sha256','module_sha256','capture_sha256','main_sha256'):
        need(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]) is not None)
    need(value['source_sha256'] == source_sha256 and value['module_sha256'] == module_sha256)
    need(type(value['record']) is str)
    try:
        record = value['record'].encode('ascii')
    except UnicodeEncodeError:
        raise ProbeError('tree_access_probe_invalid') from None
    controls = scalar_controls_valid(record)
    need(type(value['controls_valid']) is bool and value['controls_valid'] == controls)
    need(type(value['message_count']) is int and value['message_count'] == 11)
    need(type(value['main_size']) is int and 0 < value['main_size'] <= 8192 - len(record))
    need(type(value['capture_size']) is int and value['capture_size'] == value['main_size'] + len(record))
    return value
