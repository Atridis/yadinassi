"""Owned Designer package metadata for the explicit module runtime profile."""
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True, slots=True)
class ConfigurationXDTOPackage:
    identity: UUID
    name: str
    namespace: str
    content: bytes


def read_xdto_packages(files, names, used, issues):
    from .configuration_xml import (MD, _object, _props, _uuid, _text, _fail,
        _envelope_issues, _activation_properties)
    from .xdto_packages import load_packages, MAX_PACKAGES
    from .xdto_io import BSLXDTOFactory
    if len(names) > MAX_PACKAGES or len({n.casefold() for n in names}) != len(names):
        _fail('XDTO package inventory')
    result = []
    for name in names:
        path = f'XDTOPackages/{name}.xml'
        resource = f'XDTOPackages/{name}/Ext/Package.bin'
        if path not in files or resource not in files: _fail('missing XDTO package source')
        obj, _, root = _object(files[path], 'XDTOPackage', include_root=True)
        props = _props(obj); identity = _uuid(obj.get('uuid'))
        if identity in used: _fail('duplicate metadata UUID')
        used.add(identity)
        if _text(props, 'Name') != name: _fail('XDTO package filename/name mismatch')
        _envelope_issues(root, obj, issues, name)
        _activation_properties(obj, {'Name','Synonym','Comment','Namespace'}, issues, name)
        for key in ('Name','Namespace'):
            node=props.get('{'+MD+'}'+key)
            if node is not None and len(node):issues.append('unsupported XDTO scalar metadata:'+name+':'+key)
        if any(len(node) for node in obj.findall('{'+MD+'}ChildObjects')):
            issues.append('unsupported XDTO metadata child objects:'+name)
        result.append(ConfigurationXDTOPackage(identity,name,_text(props,'Namespace'),files[resource]))
    # Admission validates the whole closed graph before an application can activate it.
    load_packages(BSLXDTOFactory(), tuple(result))
    return tuple(result)
