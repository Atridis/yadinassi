"""Closed Designer XDTO package loader; no external schemas or URI resolution."""
from .xdto_values import (XS, MAX_TYPES, MAX_PROPERTIES, MAX_DEPTH, BSLXDTOValueType,
    BSLXDTOObjectType, BSLXDTOProperty, BSLXDTOPropertyCollection,
    BSLXDTOPackage, BSLXDTOPackageCollection)
from .xdto_schema import _xml_tree, _identifier, _boolean, MAX_SCHEMA_BYTES

NS = 'http://v8.1c.ru/8.1/xdto'
MAX_PACKAGES = 8


def _attrs(node, name, allowed):
    if node['uri'] != NS or node['name'] != name or node['text'].strip():
        raise ValueError('XDTO package: unsupported declaration')
    if any(uri or key not in allowed for uri, key in node['attrs']):
        raise ValueError('XDTO package: unsupported attribute')
    return {key: value for (_, key), value in node['attrs'].items()}


def _uri(value):
    if type(value) is not str or not value or len(value) > 1024 or value != value.strip():
        raise ValueError('XDTO package: invalid namespace')
    return value


def _bound(value, upper=False):
    if upper and value == '-1': return -1
    if not value or len(value) > 4 or not value.isascii() or not value.isdigit():
        raise ValueError('XDTO package: invalid bound')
    result = int(value)
    if result > 4096: raise ValueError('XDTO package: bound exceeded')
    return result


def _acyclic(edges):
    depths = {}
    def visit(key, active):
        if key in active or len(active) > MAX_DEPTH:
            raise ValueError('XDTO package: cyclic or deep model')
        if key in depths:
            return depths[key]
        depth = max((1 + visit(target, active | {key})
                     for target in edges.get(key, ())), default=0)
        if depth > MAX_DEPTH:
            raise ValueError('XDTO package: cyclic or deep model')
        depths[key] = depth
        return depth
    for key in edges:
        visit(key, set())


def load_packages(factory, definitions, *, allow_existing_dependencies=False):
    """Construct into a fresh unpublished factory; definitions carry owned bytes."""
    if not isinstance(definitions, tuple) or len(definitions) > MAX_PACKAGES:
        raise ValueError('XDTO package: package count')
    existing = {p._uri for p in factory._packages._items} if allow_existing_dependencies else set()
    packages = {}; declarations = []; edges = {}; total = 0
    for definition in definitions:
        raw = definition.content
        total += len(raw)
        if total > MAX_SCHEMA_BYTES: raise ValueError('XDTO package: total size')
        node = _xml_tree(raw)
        attrs = _attrs(node, 'package', {'targetNamespace', 'elementFormDefault', 'attributeFormDefault'})
        uri = _uri(attrs.get('targetNamespace'))
        if uri == XS or uri != definition.namespace or uri in packages or uri in existing:
            raise ValueError('XDTO package: namespace mismatch or duplicate')
        element = attrs.get('elementFormDefault', 'Qualified')
        attribute = attrs.get('attributeFormDefault', 'Unqualified')
        if element not in ('Qualified', 'Unqualified') or attribute not in ('Qualified', 'Unqualified'):
            raise ValueError('XDTO package: unsupported qualification')
        imports = set(); items = []
        for child in node['children']:
            if child['name'] == 'import':
                a = _attrs(child, 'import', {'namespace'})
                dep = _uri(a.get('namespace'))
                if child['children'] or dep in imports or dep == uri: raise ValueError('XDTO package: invalid import')
                imports.add(dep)
            else:
                tag = child['name']
                a = _attrs(child, tag, {'name', 'base', 'variety'} if tag == 'valueType' else {'name'})
                if tag not in ('valueType', 'objectType'): raise ValueError('XDTO package: unsupported type')
                name = _identifier(a.get('name', ''))
                key = (uri, name)
                if key in factory._types or len(factory._types) >= MAX_TYPES: raise ValueError('XDTO package: duplicate or excess type')
                kind = BSLXDTOValueType(factory, name, uri) if tag == 'valueType' else BSLXDTOObjectType(factory, name, uri)
                factory._types[key] = kind; items.append(kind)
                declarations.append((uri, child, a, kind))
        packages[uri] = (items, element == 'Qualified', attribute == 'Qualified', imports)
        edges[uri] = imports - {XS}
    for uri, (_, _, _, imports) in packages.items():
        if any(dep != XS and dep not in packages and dep not in existing for dep in imports):
            raise ValueError('XDTO package: imported namespace not supplied')
    _acyclic(edges)
    def resolve(uri, node, value):
        if type(value) is not str or not value or len(value) > 256 or value.count(':') > 1:
            raise ValueError('XDTO package: invalid type reference')
        prefix, sep, name = value.partition(':')
        if not sep: name = prefix; prefix = ''
        target = node['context'].get(prefix)
        if target not in (uri, XS) and target not in packages[uri][3]:
            raise ValueError('XDTO package: undeclared namespace dependency')
        kind = factory._types.get((target, name))
        if kind is None: raise ValueError('XDTO package: unknown type')
        return kind
    # Direct atomic aliases only. Chained restrictions/facets are deliberately closed.
    for uri, node, attrs, kind in declarations:
        if type(kind) is BSLXDTOValueType:
            base = resolve(uri, node, attrs.get('base'))
            if attrs.get('variety') != 'Atomic' or node['children'] or type(base) is not BSLXDTOValueType or base._uri != XS:
                raise ValueError('XDTO package: unsupported scalar alias')
            kind._base = base
    object_edges = {}
    for uri, node, attrs, kind in declarations:
        if type(kind) is not BSLXDTOObjectType: continue
        props = []; seen = set(); deps = set()
        for child in node['children']:
            a = _attrs(child, 'property', {'name','type','lowerBound','upperBound','nillable','form'})
            if child['children']: raise ValueError('XDTO package: nested property content')
            name = _identifier(a.get('name', ''))
            if name in seen or len(props) >= MAX_PROPERTIES: raise ValueError('XDTO package: duplicate or excess property')
            seen.add(name); target = resolve(uri, child, a.get('type'))
            lower = _bound(a.get('lowerBound', '1')); upper = _bound(a.get('upperBound', '1'), True)
            if upper == 0 or (upper != -1 and lower > upper): raise ValueError('XDTO package: invalid cardinality')
            form = a.get('form', 'Element')
            if form not in ('Element', 'Attribute'): raise ValueError('XDTO package: unsupported property form')
            attribute = form == 'Attribute'; nil = _boolean(a.get('nillable','false'))
            if attribute and (upper != 1 or nil or type(target) is BSLXDTOObjectType): raise ValueError('XDTO package: invalid attribute')
            qualified = packages[uri][2 if attribute else 1]
            props.append(BSLXDTOProperty(kind, name, target, uri if qualified else '', lower, upper, nil, attribute))
            if type(target) is BSLXDTOObjectType: deps.add((target._uri,target._name))
        kind._properties = BSLXDTOPropertyCollection(props)
        object_edges[uri,kind._name] = deps
    if allow_existing_dependencies:
        object_edges = {key: {(prop._type._uri, prop._type._name)
            for prop in kind._properties._items if type(prop._type) is BSLXDTOObjectType}
            for key, kind in factory._types.items() if type(kind) is BSLXDTOObjectType}
    _acyclic(object_edges)
    result = list(factory._packages._items)
    for uri, (types, element, attribute, _) in packages.items():
        package = BSLXDTOPackage(uri, types); package._element_qualified = element; package._attribute_qualified = attribute
        result.append(package)
    factory._packages = BSLXDTOPackageCollection(result)
    return factory
