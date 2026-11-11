"""Closed configuration enumeration declarations; no storage or code execution.

EnumRef fields, native type GUIDs and manager modules are not admitted here.
The application binds these immutable declarations to its own runtime family.
"""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EnumValueDefinition:
    identity: UUID
    name: str
    synonyms: tuple[tuple[str, str], ...] = ()
    comment: str = ''


@dataclass(frozen=True, slots=True)
class EnumDefinition:
    identity: UUID
    name: str
    values: tuple[EnumValueDefinition, ...]
    synonyms: tuple[tuple[str, str], ...] = ()
    comment: str = ''


def read_enumerations(files, names, used, issues):
    from .configuration_xml import (MD, V8, _activation_properties, _envelope_issues,
                                    _fail, _name, _object, _props, _text, _uuid)
    if len(names) > 128 or len({n.casefold() for n in names}) != len(names):
        _fail('enumeration inventory')

    def description(props):
        result=[]
        synonym=props.get('{'+MD+'}Synonym')
        if synonym is not None:
            for item in synonym:
                if item.tag != '{'+V8+'}item' or item.attrib or len(item) != 2:
                    _fail('enumeration synonym shape')
                lang=item.find('{'+V8+'}lang');text=item.find('{'+V8+'}content')
                if lang is None or text is None or len(lang) or len(text) or lang.attrib or text.attrib:
                    _fail('enumeration synonym shape')
                key=lang.text or '';value=text.text or ''
                if not key or len(key)>32 or len(value)>1024 or key in {k for k,_ in result}:
                    _fail('enumeration synonym bounds')
                result.append((key,value))
        comment=_text(props,'Comment','')
        if len(comment)>4096: _fail('enumeration comment bound')
        return tuple(result),comment

    def validate_object(obj, owner, *, children):
        allowed={'{'+MD+'}Properties'}
        if children: allowed.add('{'+MD+'}ChildObjects')
        if set(obj.attrib)!={'uuid'} or (obj.text or '').strip(): _fail('enumeration envelope')
        if len({n.tag for n in obj})!=len(obj): _fail('enumeration duplicate container')
        for node in obj:
            if node.tag not in allowed or node.attrib or (node.text or '').strip() or (node.tail or '').strip():
                _fail('unsupported enumeration component')
        props=_props(obj)
        for tag,node in props.items():
            if tag not in {'{'+MD+'}Name','{'+MD+'}Synonym','{'+MD+'}Comment'} or node.attrib or (node.tail or '').strip():
                _fail('unsupported enumeration property')
            if tag!='{'+MD+'}Synonym' and len(node): _fail('enumeration scalar property')

    result=[];total=0
    for name in names:
        path='Enums/'+name+'.xml'
        if path not in files: _fail('missing enumeration XML')
        obj,_,root=_object(files[path],'Enum',include_root=True);props=_props(obj)
        if _name(_text(props,'Name')) != name: _fail('enumeration filename/name mismatch')
        identity=_uuid(obj.get('uuid'))
        if identity in used: _fail('duplicate metadata UUID')
        used.add(identity)
        _envelope_issues(root,obj,issues,name)
        validate_object(obj, name, children=True)
        values=[];children=obj.find('{'+MD+'}ChildObjects')
        if children is not None:
            for item in children:
                if item.tag != '{'+MD+'}EnumValue' or set(item.attrib) != {'uuid'}:
                    _fail('unsupported enumeration child')
                value_id=_uuid(item.get('uuid'))
                if value_id in used: _fail('duplicate metadata UUID')
                used.add(value_id);p=_props(item);value_name=_name(_text(p,'Name'))
                if any(n.tag != '{'+MD+'}Properties' for n in item): _fail('enumeration value envelope')
                validate_object(item, name+'.'+value_name, children=False)
                synonyms,comment=description(p)
                values.append(EnumValueDefinition(value_id,value_name,synonyms,comment))
        if len(values)>512 or len({v.name.casefold() for v in values}) != len(values):
            _fail('enumeration value inventory')
        total+=len(values)
        if total>4096: _fail('enumeration total value inventory')
        synonyms,comment=description(props)
        result.append(EnumDefinition(identity,name,tuple(values),synonyms,comment))
    return tuple(result)
