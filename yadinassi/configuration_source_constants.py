"""Bounded scalar declarations for an explicitly created source constants store.

This parser grants neither catalog storage nor metadata activation. Unsupported
constants remain named errors. Value-manager code and write-time policies are
not silently bypassed by the direct Get/Set subset.
"""
from dataclasses import dataclass
from uuid import UUID
from .configuration_source import ConfigurationSource
from .configuration_source_metadata import SourceMetadataRoot
from .configuration_xml import MD, XSI, XS, V8, _object, _props, _type, _text, _qname


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
            kind, qualifiers = _constant_type(props, namespaces)
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


def _constant_type(props, namespaces):
    """Closed scalar union; reuse original nodes so namespace scopes stay exact."""
    from xml.etree.ElementTree import Element
    declaration = props.get('{' + MD + '}Type')
    if declaration is None:
        raise ValueError('missing constant type')
    if declaration.attrib or (declaration.text or '').strip() or any((n.tail or '').strip() for n in declaration):
        raise ValueError('unsupported constant type envelope')
    nodes = [n for n in declaration if n.tag == '{' + V8 + '}Type']
    if not 1 <= len(nodes) <= 6:
        raise ValueError('constant union type count bound')
    variants = []
    used = set()
    for node in nodes:
        if node.attrib or len(node):
            raise ValueError('unsupported constant type node')
        namespace, name = _qname(node, namespaces)
        qualifier = {'string':'StringQualifiers', 'decimal':'NumberQualifiers', 'dateTime':'DateQualifiers'}.get(name) if namespace == XS else None
        chosen = [n for n in declaration if qualifier and n.tag == '{' + V8 + '}' + qualifier]
        used.update(id(n) for n in chosen)
        special = {'ValueStorage':'value_storage', 'UUID':'uuid'}.get(name) if namespace == V8 else None
        if special:
            kind, qualifiers = special, ()
        else:
            wrapper = Element('{' + MD + '}Type')
            wrapper.extend([node, *chosen])
            kind, qualifiers, target = _type({**props, '{' + MD + '}Type':wrapper}, namespaces, {})
            if target is not None or kind not in ('string', 'number', 'boolean', 'datetime'):
                raise ValueError('unsupported source constant type')
        if any(k == kind for k, q in variants):
            raise ValueError('duplicate constant union type')
        variants.append((kind, qualifiers))
    if any(n not in nodes and id(n) not in used for n in declaration):
        raise ValueError('unsupported constant type component')
    if len(variants) == 1:
        return variants[0]
    return 'composite', tuple(sorted(variants))
