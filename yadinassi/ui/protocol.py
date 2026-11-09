"""Unstable yadinassi-ui/0: bounded JSON-RPC requests and exact scalar values.

This is a host/renderer codec, NOT BSL client/server serialization or XDTO.
Only the small headless catalog browser contract is admitted in this revision.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
from uuid import UUID

from ..dates import BSLDate
from ..values import NULL

PROTOCOL = 'yadinassi-ui/0'
MAX_LINE_BYTES = 131072
MAX_STRING_BYTES = 8192
MAX_NODES = 8192
MAX_DEPTH = 16
MAX_COUNTER = 2147483647
MAX_PAGE = 64
_UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z')


class UIError(ValueError):
    """Finite public diagnostic; never carries paths, row bytes or host errors."""
    CODES = frozenset(('invalid_json', 'message_limit', 'invalid_message',
        'invalid_value', 'unsupported_value', 'method_not_found', 'version', 'sequence', 'handshake',
        'stale_revision', 'closed', 'busy', 'request_limit', 'metadata_unavailable',
        'catalog_unavailable', 'catalog_identity', 'catalog_not_found',
        'record_not_found', 'reference_field', 'empty_reference', 'page',
        'write_unsupported', 'internal_error'))

    def __init__(self, code):
        if type(code) is not str or code not in self.CODES:
            raise ValueError('invalid UI diagnostic')
        self.code = code
        super().__init__(code)


def uuid_text(value, *, nonzero=False):
    if (type(value) is not str or _UUID.fullmatch(value) is None
            or nonzero and UUID(value).int == 0):
        raise UIError('invalid_value')
    return value


def bounded_text(value, maximum=MAX_STRING_BYTES):
    if type(value) is not str:
        raise UIError('invalid_value')
    try:
        if len(value) > maximum or len(value.encode('utf-8')) > maximum:
            raise UIError('message_limit')
    except UnicodeError:
        raise UIError('invalid_value') from None
    return value


@dataclass(frozen=True, slots=True)
class CatalogRef:
    """Wire identity only; the owning browser resolves it against its metadata."""
    catalog: str
    record: str

    def __post_init__(self):
        uuid_text(self.catalog, nonzero=True)
        uuid_text(self.record)


def encode_value(value):
    if value is None:
        return {'type': 'Undefined'}
    if value is NULL:
        return {'type': 'Null'}
    if type(value) is str:
        return {'type': 'String', 'value': bounded_text(value)}
    if type(value) is bool:
        return {'type': 'Boolean', 'value': value}
    if type(value) is Decimal:
        # Bound host coefficient storage before as_tuple copies it. The wire
        # decoder separately bounds input text before constructing a Decimal.
        if value.__sizeof__() > 512 or not value.is_finite():
            raise UIError('unsupported_value')
        parts = value.as_tuple()
        if len(parts.digits) > 128 or abs(parts.exponent) > 4096:
            raise UIError('unsupported_value')
        return {'type': 'Number', 'value': str(value)}
    if type(value) is BSLDate:
        if value.boundary:
            raise UIError('unsupported_value')
        # Decimal ticks retain subsecond precision and never use JS Date/UTC.
        return {'type': 'Date', 'ticks': str(value.ticks)}
    if type(value) is CatalogRef:
        return {'type': 'CatalogRef', 'catalog': value.catalog, 'record': value.record}
    raise UIError('unsupported_value')


def decode_value(value):
    if type(value) is not dict or type(value.get('type')) is not str:
        raise UIError('invalid_value')
    kind = value['type']
    if kind in ('Undefined', 'Null') and set(value) == {'type'}:
        return None if kind == 'Undefined' else NULL
    if kind == 'CatalogRef' and set(value) == {'type', 'catalog', 'record'}:
        return CatalogRef(value['catalog'], value['record'])
    if kind == 'Date' and set(value) == {'type', 'ticks'}:
        text = value['ticks']
        if (type(text) is not str or len(text) > 19 or
                re.fullmatch(r'0|[1-9][0-9]*', text) is None):
            raise UIError('invalid_value')
        try:
            return BSLDate(int(text))
        except ValueError:
            raise UIError('invalid_value') from None
    if set(value) != {'type', 'value'}:
        raise UIError('invalid_value')
    data = value['value']
    if kind == 'String':
        return bounded_text(data)
    if kind == 'Boolean' and type(data) is bool:
        return data
    if kind == 'Number' and type(data) is str and len(data) <= 144:
        try:
            number = Decimal(data)
            if encode_value(number)['value'] == data:
                return number
        except (InvalidOperation, ValueError, KeyError):
            pass
    raise UIError('invalid_value')


def _shape(value):
    remaining = MAX_NODES
    strings = 0
    active = set()

    def visit(item, depth):
        nonlocal remaining, strings
        remaining -= 1
        if remaining < 0 or depth > MAX_DEPTH:
            raise UIError('message_limit')
        if type(item) is str:
            bounded_text(item)
            strings += len(item.encode('utf-8'))
            if strings > MAX_LINE_BYTES:
                raise UIError('message_limit')
        elif item is None or type(item) is bool:
            pass
        elif type(item) is int:
            if not -MAX_COUNTER <= item <= MAX_COUNTER:
                raise UIError('invalid_message')
        elif type(item) in (dict, list):
            identity = id(item)
            if identity in active:
                raise UIError('invalid_message')
            active.add(identity)
            try:
                if type(item) is dict:
                    for key, child in item.items():
                        if type(key) is not str:
                            raise UIError('invalid_message')
                        visit(key, depth + 1)
                        visit(child, depth + 1)
                else:
                    for child in item:
                        visit(child, depth + 1)
            finally:
                active.remove(identity)
        else:
            raise UIError('invalid_message')
    visit(value, 1)


def encode_line(message):
    _shape(message)
    raw = (json.dumps(message, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False) + '\n').encode('utf-8')
    if len(raw) > MAX_LINE_BYTES:
        raise UIError('message_limit')
    return raw


def decode_line(raw):
    """Decode one finite NDJSON transport frame."""
    return _decode_json(raw, framed=True)


def decode_document(raw):
    """Decode a bounded local JSON document, allowing formatting whitespace."""
    return _decode_json(raw, framed=False)


def _decode_json(raw, *, framed):
    if type(raw) is not bytes:
        raise UIError('invalid_json')
    if len(raw) > MAX_LINE_BYTES:
        raise UIError('message_limit')
    # Count container depth before json.loads can recurse on attacker input.
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                raise UIError('message_limit')
        elif byte in (93, 125):
            depth -= 1
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise UIError('invalid_json')
            result[key] = item
        return result
    def reject(_):
        raise UIError('invalid_json')
    def integer(text):
        if len(text) > 11:
            raise UIError('invalid_json')
        return int(text)
    try:
        # Exactly one NDJSON frame. Embedded newlines must be JSON escapes.
        body = raw[:-1] if raw.endswith(b'\n') else raw
        if framed and (b'\n' in body or b'\r' in body):
            raise UIError('invalid_json')
        value = json.loads(body.decode('utf-8'), object_pairs_hook=pairs,
                           parse_int=integer, parse_float=reject, parse_constant=reject)
    except (UnicodeError, ValueError, RecursionError) as error:
        if type(error) is UIError:
            raise
        raise UIError('invalid_json') from None
    _shape(value)
    return value


def counter(value, *, positive=False):
    if type(value) is not int or not int(positive) <= value <= MAX_COUNTER:
        raise UIError('invalid_message')
    return value


def validate_request(message):
    _shape(message)
    if (type(message) is not dict or set(message) != {'jsonrpc', 'id', 'method', 'params'}
            or message['jsonrpc'] != '2.0' or type(message['method']) is not str
            or type(message['params']) is not dict):
        raise UIError('invalid_message')
    counter(message['id'], positive=True)
    params = message['params']
    if message['method'] == 'ui.hello':
        if set(params) != {'protocol'} or type(params['protocol']) is not str:
            raise UIError('invalid_message')
    elif message['method'] == 'ui.snapshot':
        if params:
            raise UIError('invalid_message')
    elif message['method'] == 'ui.event':
        fields = {'selectCatalog': {'catalog'}, 'openCard': {'reference'},
                  'followReference': {'field'}, 'page': {'offset', 'limit'}, 'close': set()}
        event = params.get('event')
        if type(event) is not str or event not in fields:
            raise UIError('invalid_message')
        if set(params) != {'formId', 'baseRevision', 'event'} | fields[event]:
            raise UIError('invalid_message')
        if params['formId'] != 'catalog-browser':
            raise UIError('invalid_message')
        counter(params['baseRevision'])
        if event == 'selectCatalog':
            uuid_text(params['catalog'], nonzero=True)
        elif event == 'openCard':
            if type(decode_value(params['reference'])) is not CatalogRef:
                raise UIError('invalid_value')
        elif event == 'followReference':
            if not bounded_text(params['field'], 1024):
                raise UIError('invalid_value')
        elif event == 'page':
            counter(params['offset'])
            if type(params['limit']) is not int or not 1 <= params['limit'] <= MAX_PAGE:
                raise UIError('page')
    else:
        raise UIError('method_not_found')
    return message


def error_response(request_id, code):
    UIError(code)
    rpc_code = {'invalid_json': -32700, 'invalid_message': -32600,
                'method_not_found': -32601}.get(code, -32000)
    data = {'reason': code}
    if code in ('metadata_unavailable', 'catalog_unavailable'):
        data['capability'] = 'not-established'
        data['guidance'] = 'Check selected database and supported schema; rejection does not establish corruption.'
    return {'jsonrpc': '2.0', 'id': request_id, 'error': {
        'code': rpc_code, 'message': 'Request rejected', 'data': data}}
