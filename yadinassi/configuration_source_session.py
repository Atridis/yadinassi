"""Read source-session types without activating unsupported declarations.

The existing closed scalar parser remains the authority for scalar qualifiers.
Immutable value types and bounded unions use explicit v8 declarations. Unknown declarations
are retained as named runtime errors, not guessed defaults or database columns.
"""
from .configuration_session_parameters import SessionParameterDefinition, read_session_parameters
from .configuration_xml import MD, V8, _object, _props, _qname


def source_session_definitions(source):
    files = {entry.path: entry.content for entry in source.files}
    definitions = []
    unsupported = {}
    for item in source.metadata:
        if item.family != 'SessionParameter':
            continue
        if item.path != 'SessionParameters/' + item.name + '.xml':
            unsupported[item.name.casefold()] = 'unexpected declaration path'
            continue
        try:
            definitions.extend(read_session_parameters(files, [item.name], set(), [], source_unbounded_string=True))
            continue
        except ValueError:
            pass
        try:
            obj, namespaces = _object(files[item.path], 'SessionParameter')
            props = _props(obj)
            allowed = {'Name', 'Synonym', 'Comment', 'Type'}
            if set(props) - {'{' + MD + '}' + name for name in allowed}:
                raise ValueError('unsupported properties')
            if len(obj) != 1 or set(obj.attrib) != {'uuid'}:
                raise ValueError('unsupported declaration envelope')
            definitions.append(_source_definition(item, props, namespaces))
        except ValueError as error:
            from .configuration_diagnostics import ImportRefusal
            unsupported[item.name.casefold()] = (error.diagnostic.text()
                if type(error) is ImportRefusal else str(error))
    return tuple(definitions), unsupported


_SOURCE_TYPES = {
    'FixedMap': 'fixed_map', 'FixedStructure': 'fixed_structure',
    'FixedArray': 'fixed_array', 'UUID': 'uuid',
    'ValueStorage': 'value_storage', 'TypeDescription': 'type_description',
}


def _source_definition(item, props, namespaces):
    import xml.etree.ElementTree as ET
    from .configuration_xml import _type, XS
    node = props.get('{' + MD + '}Type')
    if (node is None or node.attrib or (node.text or '').strip()
            or any((child.tail or '').strip() for child in node)):
        raise ValueError('unsupported session type envelope')
    types = [child for child in node if child.tag == '{' + V8 + '}Type']
    if not 1 <= len(types) <= 16:
        raise ValueError('source session type inventory must contain 1 to 16 types')
    qualifiers = {'StringQualifiers', 'NumberQualifiers', 'DateQualifiers'}
    if any(child.tag not in {'{' + V8 + '}Type', *('{' + V8 + '}' + q for q in qualifiers)} for child in node):
        raise ValueError('unsupported source session qualifier')
    parts = []; seen = set(); used_qualifiers = set()
    for child in types:
        if child.attrib or len(child):
            raise ValueError('unsupported session type declaration')
        qname = _qname(child, namespaces)
        if qname in seen:
            raise ValueError('duplicate source session type')
        seen.add(qname)
        if qname[0] == V8 and qname[1] in _SOURCE_TYPES:
            kind, limits = _SOURCE_TYPES[qname[1]], ()
        else:
            qualifier = {'string':'StringQualifiers', 'decimal':'NumberQualifiers',
                         'dateTime':'DateQualifiers'}.get(qname[1]) if qname[0] == XS else None
            # QName bindings belong to the original element identities.
            # _type is read-only; retain those nodes in the temporary view.
            singleton = ET.Element('{' + MD + '}Type')
            singleton.append(child)
            if qualifier:
                used_qualifiers.add(qualifier)
                for candidate in node:
                    if candidate.tag == '{' + V8 + '}' + qualifier:
                        singleton.append(candidate)
            kind, limits, target = _type({'{' + MD + '}Type': singleton}, namespaces, {}, source_unbounded_string=True)
            if target is not None or kind not in ('boolean', 'string', 'number', 'datetime'):
                raise ValueError('unsupported source session type')
        parts.append((kind, limits))
    if any(child.tag != '{' + V8 + '}Type' and child.tag.rsplit('}',1)[-1] not in used_qualifiers for child in node):
        raise ValueError('qualifier without matching source session type')
    if len(parts) == 1:
        kind, limits = parts[0]
    else:
        kind, limits = 'source_union', tuple(parts)
    return SessionParameterDefinition(item.identity, item.name, kind, limits)
