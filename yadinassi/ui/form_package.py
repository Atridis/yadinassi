"""Fixed local package loader for trusted replicated form applications.

The renderer cannot pick a package, path, source, database, endpoint or signature.
Each process reads only its side's two fixed UTF-8 files at startup.
"""
from dataclasses import dataclass
from pathlib import Path

from ..form_model import BSLFormAttribute, name
from ..form_runtime import MAX_SOURCE
from ..invocation import InvocationBinding, _decode_scalar
from ..type_descriptions import BSLTypeDescription
from .protocol import decode_document, MAX_LINE_BYTES, bounded_text

PACKAGE_PROTOCOL = 'yadinassi-form-app/0'


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError('invalid form package')


def _list(value, limit):
    if type(value) is not list or len(value) > limit:
        raise ValueError('invalid form package inventory')
    return value


def _read(directory, filename, limit):
    # Finite local host inputs, never names received through the UI/replica wire.
    with (Path(directory) / filename).open('rb') as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError('invalid form package file')
    return raw


def _binding(row, *, handler=False):
    _keys(row, 'name endpoint parameters isFunction')
    _list(row['parameters'], 32)
    if handler and row['isFunction'] is not False:
        raise ValueError('client handlers must be procedures')
    return InvocationBinding(row['name'], row['endpoint'], tuple(row['parameters']), row['isFunction'])


def _bindings(rows, *, handler=False):
    values = tuple(_binding(row, handler=handler) for row in _list(rows, 64))
    if len({v.endpoint for v in values}) != len(values) or len({v.name.casefold() for v in values}) != len(values):
        raise ValueError('duplicate form package binding')
    return values


@dataclass(frozen=True)
class ClientPackage:
    source: str
    handlers: tuple
    bindings: tuple


@dataclass(frozen=True)
class ServerPackage:
    source: str
    handlers: tuple
    endpoints: dict
    lifecycle: dict
    attributes: tuple
    initial_values: dict


def load_client(directory):
    manifest = decode_document(_read(directory, 'client.json', MAX_LINE_BYTES))
    _keys(manifest, 'protocol handlers bindings')
    if manifest['protocol'] != PACKAGE_PROTOCOL:
        raise ValueError('invalid form package version')
    source = _read(directory, 'client.bsl', MAX_SOURCE).decode('utf-8')
    return ClientPackage(source, _bindings(manifest['handlers'], handler=True), _bindings(manifest['bindings']))


def load_server(directory):
    manifest = decode_document(_read(directory, 'server.json', MAX_LINE_BYTES))
    _keys(manifest, 'protocol handlers endpoints lifecycle attributes')
    if manifest['protocol'] != PACKAGE_PROTOCOL or type(manifest['lifecycle']) is not dict:
        raise ValueError('invalid form package version or lifecycle')
    source = _read(directory, 'server.bsl', MAX_SOURCE).decode('utf-8')
    endpoints = {}
    for row in _list(manifest['endpoints'], 64):
        _keys(row, 'endpoint routine')
        endpoint = row['endpoint']
        if type(endpoint) is not int or not 1 <= endpoint <= 64 or endpoint in endpoints:
            raise ValueError('invalid form endpoint')
        endpoints[endpoint] = name(row['routine'])
    attributes = []; initial = {}; names = set()
    for row in _list(manifest['attributes'], 128):
        _keys(row, 'name type title value')
        key = name(row['name'])
        if key.casefold() in names or row['type'] not in ('String', 'Number', 'Boolean', 'Date'):
            raise ValueError('invalid form attribute')
        names.add(key.casefold())
        attributes.append(BSLFormAttribute(key, BSLTypeDescription(row['type']),
            title=bounded_text(row['title'], 1024)))
        initial[key] = _decode_scalar(row['value'])
    return ServerPackage(source, _bindings(manifest['handlers'], handler=True), endpoints,
        dict(manifest['lifecycle']), tuple(attributes), initial)
