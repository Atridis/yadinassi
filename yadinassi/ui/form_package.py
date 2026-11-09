"""Fixed local package loader for trusted replicated form applications.

The renderer cannot pick a package, path, source, database, endpoint or signature.
Each process reads only its side's two fixed UTF-8 files at startup.
"""
from dataclasses import dataclass
from pathlib import Path

from ..form_model import BSLFormAttribute, name
from ..form_runtime import MAX_SOURCE
from ..form_tables import FormTableSchema, FormTableColumn, MAX_TABLES, MAX_TABLE_COLUMNS
from ..invocation import InvocationBinding, _decode_scalar
from ..type_descriptions import BSLTypeDescription
from .protocol import decode_document, MAX_LINE_BYTES, bounded_text

PACKAGE_PROTOCOL = 'yadinassi-form-app/0'
TABLE_PACKAGE_PROTOCOL = 'yadinassi-form-app/1'
OBJECT_PACKAGE_PROTOCOL = 'yadinassi-form-app/2'


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
    discard_commands: tuple = ()
    dirty_attribute: str = ''


@dataclass(frozen=True)
class ServerPackage:
    source: str
    handlers: tuple
    endpoints: dict
    lifecycle: dict
    attributes: tuple
    initial_values: dict
    tables: tuple = ()
    application: str | None = None


def load_client(directory):
    manifest = decode_document(_read(directory, 'client.json', MAX_LINE_BYTES))
    protocol = manifest.get('protocol') if type(manifest) is dict else None
    _keys(manifest, 'protocol handlers bindings' + (' discardCommands dirtyAttribute' if protocol == OBJECT_PACKAGE_PROTOCOL else ''))
    if protocol not in (PACKAGE_PROTOCOL, TABLE_PACKAGE_PROTOCOL, OBJECT_PACKAGE_PROTOCOL):
        raise ValueError('invalid form package version')
    source = _read(directory, 'client.bsl', MAX_SOURCE).decode('utf-8')
    handlers = _bindings(manifest['handlers'], handler=True)
    policies = []
    for row in _list(manifest.get('discardCommands', []), 64):
        _keys(row, 'command handler')
        command, handler = name(row['command']), name(row['handler'])
        if command.casefold() in {c.casefold() for c, _ in policies} or not any(
                h.name.casefold() == handler.casefold() and len(h.parameters) == 1 for h in handlers):
            raise ValueError('invalid discard command binding')
        policies.append((command, handler))
    dirty = name(manifest['dirtyAttribute']) if protocol == OBJECT_PACKAGE_PROTOCOL else ''
    return ClientPackage(source, handlers, _bindings(manifest['bindings']), tuple(policies), dirty)


def load_server(directory, *, owned_choices=False):
    manifest = decode_document(_read(directory, 'server.json', MAX_LINE_BYTES))
    protocol = manifest.get('protocol') if type(manifest) is dict else None
    _keys(manifest, 'protocol handlers endpoints lifecycle attributes' +
          (' tables' if protocol in (TABLE_PACKAGE_PROTOCOL, OBJECT_PACKAGE_PROTOCOL) else '') +
          (' application' if protocol == OBJECT_PACKAGE_PROTOCOL else ''))
    if protocol not in (PACKAGE_PROTOCOL, TABLE_PACKAGE_PROTOCOL, OBJECT_PACKAGE_PROTOCOL) or type(manifest['lifecycle']) is not dict:
        raise ValueError('invalid form package version or lifecycle')
    application = manifest.get('application')
    if protocol == OBJECT_PACKAGE_PROTOCOL and application not in (
            'orders-workbench/1', 'reference-orders/1', 'catalog-choice/1'):
        raise ValueError('unknown trusted form application')
    if application in ('reference-orders/1', 'catalog-choice/1') and not owned_choices:
        raise ValueError('owned choice application requires its workspace broker')
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
    tables = []
    for row in _list(manifest.get('tables', []), MAX_TABLES):
        _keys(row, 'name title columns')
        key = name(row['name'])
        if key.casefold() in names:
            raise ValueError('duplicate form table name')
        names.add(key.casefold())
        columns = []
        for column in _list(row['columns'], MAX_TABLE_COLUMNS):
            _keys(column, 'name type title readOnly')
            if column['type'] not in ('String', 'Number', 'Boolean', 'Date'):
                raise ValueError('invalid form table column type')
            columns.append(FormTableColumn(column['name'], BSLTypeDescription(column['type']),
                bounded_text(column['title'], 1024), column['readOnly']))
        tables.append(FormTableSchema(key, tuple(columns), bounded_text(row['title'], 1024)))
    return ServerPackage(source, _bindings(manifest['handlers'], handler=True), endpoints,
        dict(manifest['lifecycle']), tuple(attributes), initial, tuple(tables), application)
