"""Read source-session types without activating unsupported declarations.

The existing closed scalar parser remains the authority for scalar qualifiers.
FixedMap and FixedStructure use exact v8 singleton declarations. Unknown declarations
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
            node = props.get('{' + MD + '}Type')
            if (node is None or node.attrib or len(node) != 1
                    or node[0].tag != '{' + V8 + '}Type' or node[0].attrib or len(node[0])
                    or _qname(node[0], namespaces) not in ((V8, 'FixedMap'), (V8, 'FixedStructure'))):
                raise ValueError('only scalar, FixedMap and FixedStructure declarations are available')
            kind = {'FixedMap': 'fixed_map', 'FixedStructure': 'fixed_structure'}[_qname(node[0], namespaces)[1]]
            definitions.append(SessionParameterDefinition(item.identity, item.name, kind))
        except ValueError as error:
            unsupported[item.name.casefold()] = str(error)
    return tuple(definitions), unsupported
