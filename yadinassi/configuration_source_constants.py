"""Bounded scalar declarations for an explicitly created source constants store.

This parser grants neither catalog storage nor metadata activation. Unsupported
constants remain named errors. Value-manager code and write-time policies are
not silently bypassed by the direct Get/Set subset.
"""
from dataclasses import dataclass, field
from uuid import UUID
from .configuration_source import ConfigurationSource
from .configuration_source_metadata import SourceMetadataRoot
from .configuration_xml import MD, XSI, XS, CFG, V8, _object, _props, _type, _text, _qname


@dataclass(frozen=True, slots=True)
class ScalarConstantDefinition:
    identity: UUID
    name: str
    kind: str
    qualifiers: tuple
    write_blockers: tuple[str, ...] = ()
    enum_namespace: object = field(default=None, compare=False, repr=False)
    type_dependencies: tuple = ()
    reference_scope: object = field(default=None, compare=False, repr=False)


def source_constant_definitions(source, *, enum_namespace=None, reference_scope=None):
    if type(source) is not ConfigurationSource:
        raise TypeError('admitted ConfigurationSource required')
    from .configuration_source_enums import source_enum_definitions
    from .enumerations import BSLEnumerations
    enums, enum_errors, _ = source_enum_definitions(source)
    if enum_namespace is None:
        enum_namespace = BSLEnumerations(enums, unsupported=enum_errors)
    elif (type(enum_namespace) is not BSLEnumerations
          or tuple(m._definition for m in enum_namespace.metadata) != enums
          or enum_namespace._unsupported != enum_errors):
        raise ValueError('constant enumeration namespace/source mismatch')
    from .source_references import SourceReferences
    if reference_scope is None:
        reference_scope = SourceReferences(source, SourceMetadataRoot(source))
    elif type(reference_scope) is not SourceReferences or reference_scope.source != source:
        raise ValueError("constant reference scope/source mismatch")
    from .source_defined_types import SourceDefinedTypes
    defined_types = SourceDefinedTypes(source)
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
            resolved, resolved_namespaces, dependencies = defined_types.resolve(props, namespaces)
            kind, qualifiers = _constant_type(resolved, resolved_namespaces, enum_namespace, reference_scope)
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
                                                   qualifiers, tuple(blockers), enum_namespace, dependencies, reference_scope))
        except (ValueError, KeyError) as error:
            unsupported[name.casefold()] = str(error)
    return tuple(result), unsupported, names


def _constant_type(props, namespaces, enum_namespace, reference_scope):
    """Closed scalar union; reuse original nodes so namespace scopes stay exact."""
    from xml.etree.ElementTree import Element
    declaration = props.get('{' + MD + '}Type')
    if declaration is None:
        raise ValueError('missing constant type')
    if declaration.attrib or (declaration.text or '').strip() or any((n.tail or '').strip() for n in declaration):
        raise ValueError('unsupported constant type envelope')
    nodes = [n for n in declaration if n.tag == '{' + V8 + '}Type']
    if not 1 <= len(nodes) <= 32:
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
        if namespace == CFG and name.startswith('EnumRef.'):
            manager = enum_namespace.get_member(name[len('EnumRef.'):])
            definition = manager._metadata._definition
            kind = 'enum_ref'
            qualifiers = (str(definition.identity), definition.name,
                          tuple(str(v.identity) for v in definition.values))
        elif namespace == CFG and name.startswith(('CatalogRef.', 'DocumentRef.')):
            family, target_name = name.split('.', 1)
            family = family[:-3]
            entry, _, _ = reference_scope.definition(family, target_name)
            kind, qualifiers = 'object_ref', (family, str(entry.identity), entry.name)
        elif special:
            kind, qualifiers = special, ()
        else:
            wrapper = Element('{' + MD + '}Type')
            wrapper.extend([node, *chosen])
            kind, qualifiers, target = _source_scalar_type(props, namespaces, wrapper)
            if target is not None or kind not in ('string', 'number', 'boolean', 'datetime'):
                raise ValueError('unsupported source constant type')
        if any(k == kind and (kind not in ('enum_ref', 'object_ref') or (q[0] == qualifiers[0] if kind == 'enum_ref' else q[:2] == qualifiers[:2])) for k, q in variants):
            raise ValueError('duplicate constant union type')
        variants.append((kind, qualifiers))
    if any(n not in nodes and id(n) not in used for n in declaration):
        raise ValueError('unsupported constant type component')
    if len(variants) == 1:
        return variants[0]
    return 'composite', tuple(sorted(variants))


def _source_scalar_type(props, namespaces, wrapper):
    """Reuse closed scalar envelope checks, extending only known scalar qualifier forms.

    This admits metadata; runtime still refuses conversions/padding/truncation.
    """
    from copy import deepcopy
    fixed = False
    fraction = None
    for index, node in enumerate(tuple(wrapper)):
        if node.tag == '{' + V8 + '}StringQualifiers':
            allowed = node.find('{' + V8 + '}AllowedLength')
            if allowed is not None and (allowed.text or '').strip() == 'Fixed':
                cloned = deepcopy(node)
                cloned.find('{' + V8 + '}AllowedLength').text = 'Variable'
                wrapper[index] = cloned
                fixed = True
        elif node.tag == '{' + V8 + '}DateQualifiers':
            part = node.find('{' + V8 + '}DateFractions')
            if part is not None and (part.text or '').strip() in ('Date', 'Time'):
                fraction = (part.text or '').strip()
                cloned = deepcopy(node)
                cloned.find('{' + V8 + '}DateFractions').text = 'DateTime'
                wrapper[index] = cloned
    kind, qualifiers, target = _type({**props, '{' + MD + '}Type':wrapper}, namespaces, {},
                                     source_unbounded_string=True)
    if fixed:
        if kind != 'string' or qualifiers[0] == 0:
            raise ValueError('fixed string requires a positive length')
        qualifiers = (qualifiers[0], 'Fixed')
    if fraction is not None:
        if kind != 'datetime':
            raise ValueError('date fraction requires Date')
        qualifiers = (fraction,)
    return kind, qualifiers, target
