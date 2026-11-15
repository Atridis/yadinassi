"""Read-only enum identities from preserved source, without activation grants.

Presentation/forms/generated-type properties stay in the source snapshot. They
are not runtime behavior or authority to access storage. Unsupported individual
enums remain named failures rather than preventing unrelated source startup.
"""
from collections import Counter

from .configuration_source import ConfigurationSource
from .configuration_source_metadata import SourceMetadataRoot
from .configuration_enumerations import EnumDefinition, EnumValueDefinition
from .configuration_xml import MD, V8, _object, _props, _text, _name, _uuid


def _description(props):
    synonyms = []
    node = props.get('{' + MD + '}Synonym')
    if node is not None:
        if node.attrib or (node.text or '').strip() or len(node) > 128:
            raise ValueError('enumeration synonym shape')
        for item in node:
            if item.tag != '{' + V8 + '}item' or item.attrib or len(item) != 2:
                raise ValueError('enumeration synonym shape')
            lang = item.find('{' + V8 + '}lang')
            text = item.find('{' + V8 + '}content')
            if lang is None or text is None or len(lang) or len(text) or lang.attrib or text.attrib:
                raise ValueError('enumeration synonym shape')
            key, value = lang.text or '', text.text or ''
            if not key or len(key) > 32 or len(value) > 1024 or key in {k for k, _ in synonyms}:
                raise ValueError('enumeration synonym bounds')
            synonyms.append((key, value))
    comment = _text(props, 'Comment', '')
    if len(comment) > 4096:
        raise ValueError('enumeration comment bound')
    return tuple(synonyms), comment


def source_enum_definitions(source):
    """Return (supported definitions, casefolded errors, declared names)."""
    if type(source) is not ConfigurationSource:
        raise TypeError('admitted ConfigurationSource required')
    names = tuple(item.get_member('Name') for item in SourceMetadataRoot(source).get_member('Enums'))
    if len(names) > 1024:
        raise ValueError('source enumeration count bound')
    files = {item.path: item.content for item in source.files}
    candidates, unsupported = [], {}
    identities = Counter(item.identity for item in source.metadata)
    for name in names:
        try:
            obj, _ = _object(files['Enums/' + name + '.xml'], 'Enum')
            props = _props(obj)
            if _name(_text(props, 'Name')) != name:
                raise ValueError('enumeration filename/name mismatch')
            identity = _uuid(obj.get('uuid'))
            values = []
            children = obj.find('{' + MD + '}ChildObjects')
            if children is not None:
                if children.attrib or (children.text or '').strip():
                    raise ValueError('enumeration child envelope')
                for item in children:
                    # These are source references, not executable value definitions.
                    if item.tag in ('{' + MD + '}Form', '{' + MD + '}Command'):
                        continue
                    if item.tag != '{' + MD + '}EnumValue' or set(item.attrib) != {'uuid'}:
                        raise ValueError('unsupported enumeration child')
                    if len(item) != 1 or item[0].tag != '{' + MD + '}Properties':
                        raise ValueError('enumeration value envelope')
                    p = _props(item)
                    value_id = _uuid(item.get('uuid'))
                    synonyms, comment = _description(p)
                    values.append(EnumValueDefinition(value_id, _name(_text(p, 'Name')), synonyms, comment))
                if len(values) > 512 or len({v.name.casefold() for v in values}) != len(values):
                    raise ValueError('enumeration value inventory')
            synonyms, comment = _description(props)
            definition = EnumDefinition(identity, name, tuple(values), synonyms, comment)
            candidates.append(definition)
            identities.update(v.identity for v in values)
        except (ValueError, KeyError) as error:
            unsupported[name.casefold()] = str(error)
    result = []
    for definition in candidates:
        if any(identities[v.identity] != 1 for v in definition.values):
            unsupported[definition.name.casefold()] = 'duplicate enumeration value UUID'
        else:
            result.append(definition)
    return tuple(result), unsupported, names
