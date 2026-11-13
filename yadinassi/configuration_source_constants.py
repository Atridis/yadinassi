"""Bounded scalar declarations for an explicitly created source constants store.

This parser grants neither catalog storage nor metadata activation. Unsupported
constants remain named errors. Value-manager code and write-time policies are
not silently bypassed by the direct Get/Set subset.
"""
from dataclasses import dataclass
from uuid import UUID
from .configuration_source import ConfigurationSource
from .configuration_source_metadata import SourceMetadataRoot
from .configuration_xml import MD, XSI, _object, _props, _type, _text


@dataclass(frozen=True, slots=True)
class ScalarConstantDefinition:
    identity: UUID
    name: str
    kind: str
    qualifiers: tuple
    write_blockers: tuple[str, ...] = ()


def source_constant_definitions(source):
    if type(source) is not ConfigurationSource:
        raise TypeError('admitted ConfigurationSource required')
    declared = SourceMetadataRoot(source).get_member('Constants')
    names = tuple(item.get_member('Name') for item in declared)
    if len(names) > 1024:
        raise ValueError('source constant count bound')
    files = {item.path: item.content for item in source.files}
    inventory = {item.path: item for item in source.metadata}
    result, unsupported = [], {}
    for name in names:
        path = 'Constants/' + name + '.xml'
        try:
            obj, namespaces = _object(files[path], 'Constant')
            props = _props(obj)
            kind, qualifiers, target = _type(props, namespaces, {})
            if target is not None or kind not in ('string', 'number', 'boolean', 'datetime'):
                raise ValueError('only scalar constants are supported')
            blockers = []
            prefix = 'Constants/' + name + '/'
            if any(p.startswith(prefix) and p.lower().endswith('.bsl') and raw.strip()
                   for p, raw in files.items()):
                blockers.append('constant module execution is not supported')
            if _text(props, 'DataHistory', 'DontUse') != 'DontUse':
                blockers.append('constant data history is not supported')
            if _text(props, 'FillChecking', 'DontCheck') != 'DontCheck':
                blockers.append('constant fill checking is not supported')
            for key in ('ExecuteAfterWriteDataHistoryVersionProcessing', 'UpdateDataHistoryImmediatelyAfterWrite'):
                if _text(props, key, 'false') != 'false':
                    blockers.append('constant history processing is not supported')
            for key in ('MinValue', 'MaxValue'):
                node = props.get('{' + MD + '}' + key)
                if node is not None and not (
                        node.attrib == {'{' + XSI + '}nil': 'true'}
                        and not len(node) and not (node.text or '').strip()):
                    blockers.append('constant value limit is not supported')
            result.append(ScalarConstantDefinition(inventory[path].identity, name, kind,
                                                   qualifiers, tuple(blockers)))
        except (ValueError, KeyError) as error:
            unsupported[name.casefold()] = str(error)
    return tuple(result), unsupported, names
