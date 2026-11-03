"""Closed server-side HTTP source adapter; dynamic data is only port/nonce/root."""
import hashlib
import re
from pathlib import Path
import native_1c_http_family_contract as contract

PROFILE = 'http-family-v1'
SCHEMA = 'native-1c-http-v1'
STAGE_SCHEMA = 'native-1c-http-stage-v1'
MAX_OUTPUT = 8192
SOURCE = 'scripts/HTTPFamily.bsl'


def valid_nonce(nonce):
    return type(nonce) is str and re.fullmatch('[0-9a-f]{32}', nonce) is not None


def source(raw):
    if (type(raw) is not bytes or len(raw) > MAX_OUTPUT or
            hashlib.sha256(raw).hexdigest() != contract.SOURCE_SHA256):
        raise ValueError('http_source_changed')
    raw.decode('utf-8')
    return raw


def program(raw, port, nonce):
    source(raw)
    if type(port) is not int or not 1024 <= port <= 65535 or not valid_nonce(nonce):
        raise ValueError('http_adapter_invalid')
    root = '/tmp/onec-smoke/stage3-' + nonce + '/fixture'
    tail = ('\nMessage("HTTP|' + nonce + '|entered");\n'
            'HTTPFamily(' + str(port) + ',"' + root + '");\n'
            'Message("HTTP|' + nonce + '|completed");\n').encode('ascii')
    result = raw + tail
    if len(result) > MAX_OUTPUT: raise ValueError('http_source_limit')
    return result


def parse_wire(raw, nonce):
    if type(raw) is not bytes or len(raw) > MAX_OUTPUT or not valid_nonce(nonce):
        raise ValueError('http_wire_invalid')
    first = ('HTTP|' + nonce + '|entered\n').encode('ascii')
    last = ('HTTP|' + nonce + '|completed\n').encode('ascii')
    if not raw.startswith(first) or not raw.endswith(last):
        raise ValueError('http_witness_invalid')
    canonical = raw[len(first):-len(last)]
    contract.validate_output(canonical)
    return canonical


def replay(raw, owned_root, port):
    """Local-only fixed-source replay; caller owns isolated server/temp directory."""
    source(raw)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('http_adapter_invalid')
    root = Path(owned_root)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or any(root.iterdir()):
        raise ValueError('http_fixture_invalid')
    # Path comes from the caller's owned TemporaryDirectory, never native output.
    literal = str(root).replace('"', '""')
    if '\n' in literal or '\r' in literal or '\0' in literal:
        raise ValueError('http_fixture_invalid')
    from yadinassi.runtime import Interpreter
    messages = []
    interpreter = Interpreter(messages.append, compilation_profile='managed-thick-file')
    interpreter.execute(raw.decode('utf-8') + '\nHTTPFamily(' + str(port) + ',"' + literal + '");\n')
    result = ('\n'.join(messages) + '\n').encode('utf-8')
    contract.validate_output(result)
    if any(root.iterdir()): raise ValueError('http_fixture_cleanup_failed')
    return result
