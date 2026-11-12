"""Strict source-bound eight-group packet; observation, never parity acceptance."""
from pathlib import Path
import hashlib
import json
import re
PROFILE = 'polymorphic-recorder-observation-v1'
SCHEMA = 'native-1c-polymorphic-recorder-v1'
COUNT = 8
MAX_OUTPUT = 32768
MAX_VALUE = 2048
SOURCE_SHA256 = '22f0515106b3fd488068a30692e5b059207026c66bb83e9ed15478ded50a10b5'

def _nonce(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
        raise ValueError('nonce')

def source():
    path = Path(__file__).with_name('observe.bsl')
    if path.is_symlink():
        raise ValueError('source symlink')
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_OUTPUT or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('source changed')
    return raw

def program(setup, nonce):
    """Keep the acquisition signature; setup is unused by this owned observer."""
    _nonce(nonce)
    raw = source()
    marker = b'P=Setup();\n'
    if raw.count(marker) != 1:
        raise ValueError('source body boundary')
    declarations, statements = raw.split(marker)
    prefix = ('Procedure RecorderEmit(N,V)\n'
              'If StrLen(V)>2048 Then Raise "owned output bound"; EndIf;\n'
              'Message("PRQ|' + nonce + '|"+String(N)+"|"+V);\nEndProcedure\n').encode('ascii')
    return (prefix + declarations + ('Message("PRQ|' + nonce + '|entered");\n').encode('ascii')
            + marker + statements + ('Message("PRQ|' + nonce + '|completed");\n').encode('ascii'))

def canonical(values):
    if (type(values) is not list or len(values) != COUNT
            or any(type(v) is not str or not 0 < len(v) <= MAX_VALUE
                   or re.fullmatch(r'[A-Z0-9,:;|.-]+', v) is None for v in values)):
        raise ValueError('observations')
    return (json.dumps(values, separators=(',', ':')) + '\n').encode('ascii')

def parse_wire(raw, nonce):
    _nonce(nonce)
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_OUTPUT:
        raise ValueError('wire')
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError:
        raise ValueError('wire encoding') from None
    prefix = 'PRQ|' + nonce + '|'
    if len(lines) != COUNT + 2 or lines[0] != prefix + 'entered' or lines[-1] != prefix + 'completed':
        raise ValueError('markers')
    values = []
    for n, line in enumerate(lines[1:-1], 1):
        expected = prefix + str(n) + '|'
        if not line.startswith(expected):
            raise ValueError('order')
        values.append(line[len(expected):])
    canonical(values)
    return values

def normalized(raw, nonce):
    values = parse_wire(raw, nonce)
    return {'schema': SCHEMA, 'groups': values, 'measurement_complete': True,
            'runtime_parity_claimed': False, 'source_sha256': SOURCE_SHA256}


# Stage adapter intentionally has no raw per-case error messages. An ERR inside
# a measured query is a scalar observation; interrupted setup stays incomplete.
STAGE_SCHEMA = 'native-1c-polymorphic-recorder-stage-v1'
STAGES = ('setup', 'query')

def parse_attempt(raw, nonce):
    return list(map(list, enumerate(parse_wire(raw, nonce), 1))), []

def failure_details(result, nonce):
    _nonce(nonce)
    if (type(result) is not dict or set(result) != {'messages', 'error'}
            or type(result['error']) is not str or len(result['error']) > 16384
            or type(result['messages']) is not list or len(result['messages']) > COUNT + 2
            or any(type(m) is not str or len(m) > 8192 for m in result['messages'])):
        raise ValueError('failure envelope')
    # Deliberately export no error text, locations, payload, or nonce.
    return {'entered': bool(result['messages'] and result['messages'][0] == 'PRQ|' + nonce + '|entered'),
            'category': 'native_failure'}

def valid_failure_details(value):
    return (type(value) is dict and set(value) == {'entered', 'category'}
            and type(value['entered']) is bool and type(value['category']) is str
            and value['category'] == 'native_failure')

# The shared material fixture contains the same exact owned metadata identifiers.
# Reuse only the finite-vocabulary sanitizer, never its native observation route.
from inventory_reference_behavior.route import install_diagnostic, valid_install_diagnostic
