"""Lazy, atomic source-owned XDTO binding. Never resolve an external schema."""
from weakref import ref
from .configuration_xml import MD, _object, _props, _text
from .configuration_xdto import ConfigurationXDTOPackage
from .xdto_io import BSLXDTOFactory
from .xdto_packages import load_packages, MAX_PACKAGES, NS, _attrs, _uri
from .xdto_schema import _xml_tree, MAX_SCHEMA_BYTES
from .xdto_values import XS


class SourceXDTOPackages:
    def __init__(self, application):
        self._application = ref(application)
        self.factory = BSLXDTOFactory()
        self.factory._source_packages_loader = self.load
        self._loaded = set()
        self._bytes = 0
        self._inventory = None

    def _definitions(self, application):
        if self._inventory is not None:
            return self._inventory
        result = {}; failures = []; ambiguous = set()
        entries = [item for item in application.source.metadata if item.family == 'XDTOPackage']
        if len(entries) > 256:
            raise ValueError('source XDTO: package inventory exceeds 256')
        for item in entries:
            try:
                obj, _ = _object(application.files[item.path], 'XDTOPackage')
                props = _props(obj)
                namespace = _uri(_text(props, 'Namespace'))
                if namespace == XS or namespace in result:
                    ambiguous.add(namespace)
                    raise ValueError('duplicate or reserved namespace')
                result[namespace] = item
            except ValueError:
                failures.append(item.name)
        self._inventory = result, failures, ambiguous
        return self._inventory

    def load(self, namespace):
        application = self._application()
        if application is None:
            raise ValueError('source XDTO: source application unavailable')
        application.require_open()
        # Primitive lookups do not activate unrelated metadata.
        if namespace == XS:
            return
        inventory, failures, ambiguous = self._definitions(application)
        if namespace is None and failures:
            raise ValueError('source XDTO: invalid namespace metadata: ' + ', '.join(failures))
        if namespace in ambiguous:
            raise ValueError('source XDTO: ambiguous package namespace: ' + namespace)
        if namespace is not None and namespace not in inventory:
            return
        pending = {}; active = set()
        def collect(uri):
            if uri == XS or uri in self._loaded or uri in pending:
                return
            if uri in active:
                raise ValueError('source XDTO: cyclic package imports')
            if uri not in inventory:
                raise ValueError('source XDTO: imported namespace is not declared: ' + uri)
            if len(active) + len(pending) + len(self._loaded) >= MAX_PACKAGES:
                raise ValueError('source XDTO: loaded package count exceeds supported limit')
            if uri in ambiguous:
                raise ValueError('source XDTO: ambiguous package namespace: ' + uri)
            item = inventory[uri]
            if item.path != 'XDTOPackages/' + item.name + '.xml':
                raise ValueError('source XDTO: unexpected metadata path')
            obj, _ = _object(application.files[item.path], 'XDTOPackage')
            props = _props(obj)
            if (_text(props, 'Name') != item.name or len(obj) != 1
                    or set(obj.attrib) != {'uuid'}
                    or set(props) - {'{' + MD + '}' + key for key in ('Name','Synonym','Comment','Namespace')}
                    or any(len(props['{' + MD + '}' + key]) for key in ('Name','Namespace'))):
                raise ValueError('source XDTO: unsupported package metadata: ' + item.name)
            resource = 'XDTOPackages/' + item.name + '/Ext/Package.bin'
            raw = application.files.get(resource)
            if raw is None:
                raise ValueError('source XDTO: missing package resource: ' + resource)
            if len(raw) + self._bytes + sum(len(d.content) for d in pending.values()) > MAX_SCHEMA_BYTES:
                raise ValueError('source XDTO: package bytes exceed supported limit')
            node = _xml_tree(raw)
            _attrs(node, 'package', {'targetNamespace','elementFormDefault','attributeFormDefault'})
            active.add(uri)
            for child in node['children']:
                if child['name'] == 'import':
                    attrs = _attrs(child, 'import', {'namespace'})
                    collect(_uri(attrs.get('namespace')))
            active.remove(uri)
            pending[uri] = ConfigurationXDTOPackage(item.identity, item.name, uri, raw)
        for uri in (inventory if namespace is None else (namespace,)):
            collect(uri)
        if not pending:
            return
        added_bytes = sum(len(d.content) for d in pending.values())
        if self._bytes + added_bytes > MAX_SCHEMA_BYTES:
            raise ValueError('source XDTO: package bytes exceed supported limit')
        # Existing descriptors retain identity; only newly allocated descriptors
        # are modified by the loader. No failed candidate can escape to callers.
        candidate = BSLXDTOFactory()
        candidate._types = dict(self.factory._types)
        candidate._roots = dict(self.factory._roots)
        candidate._packages = self.factory._packages
        load_packages(candidate, tuple(pending.values()), allow_existing_dependencies=True)
        for key, kind in candidate._types.items():
            if key not in self.factory._types:
                kind._factory = self.factory
        self.factory._types = candidate._types
        self.factory._roots = candidate._roots
        self.factory._packages = candidate._packages
        self._loaded.update(pending)
        self._bytes += added_bytes
