"""Closed scalar session declarations for the explicit trusted application host."""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SessionParameterDefinition:
    identity: UUID
    name: str
    kind: str
    qualifiers: tuple = ()


def read_session_parameters(files, names, used, issues):
    from .configuration_xml import MD, _object, _props, _text, _name, _uuid, _type, _fail, _envelope_issues
    if len(names)>128 or len({n.casefold() for n in names})!=len(names):
        _fail('session parameter inventory')
    result=[]
    for name in names:
        path='SessionParameters/'+name+'.xml'
        if path not in files: _fail('missing session parameter XML')
        obj, namespaces, root=_object(files[path],'SessionParameter',include_root=True)
        _envelope_issues(root,obj,issues,name)
        if set(obj.attrib)!={'uuid'} or len(obj)!=1 or obj[0].tag!='{'+MD+'}Properties':
            _fail('session parameter envelope')
        if (obj.text or '').strip() or obj[0].attrib or (obj[0].text or '').strip() or (obj[0].tail or '').strip():
            _fail('session parameter envelope')
        props=_props(obj)
        if not {'{'+MD+'}Name','{'+MD+'}Type'} <= set(props) or any(k not in {'{'+MD+'}'+n for n in ('Name','Synonym','Comment','Type')} for k in props):
            _fail('unsupported session parameter property')
        for key,node in props.items():
            if node.attrib or (node.tail or '').strip(): _fail('session parameter property envelope')
            if key in ('{'+MD+'}Name','{'+MD+'}Comment') and len(node): _fail('session parameter scalar property')
        if _name(_text(props,'Name'))!=name: _fail('session parameter filename/name mismatch')
        identity=_uuid(obj.get('uuid'))
        if identity in used: _fail('duplicate metadata UUID')
        used.add(identity)
        kind,qualifiers,target=_type(props,namespaces,{})
        if kind not in ('boolean','string','number','datetime') or target is not None:
            _fail('unsupported session parameter type')
        # Descriptive synonym XML is still fully validated, never executable.
        synonym=props.get('{'+MD+'}Synonym')
        if synonym is not None:
            from .configuration_xml import V8
            if (synonym.text or '').strip(): _fail('session parameter synonym')
            seen=set()
            for item in synonym:
                if item.tag!='{'+V8+'}item' or item.attrib or len(item)!=2 or (item.text or '').strip() or (item.tail or '').strip():
                    _fail('session parameter synonym')
                if [x.tag for x in item]!=['{'+V8+'}lang','{'+V8+'}content'] or any(x.attrib or len(x) or (x.tail or '').strip() for x in item):
                    _fail('session parameter synonym')
                lang=item[0].text or '';content=item[1].text or ''
                if not lang or len(lang)>32 or lang in seen or len(content)>1024: _fail('session parameter synonym bounds')
                seen.add(lang)
        if len(_text(props,'Comment',''))>4096: _fail('session parameter comment bound')
        result.append(SessionParameterDefinition(identity,name,kind,qualifiers))
    return tuple(result)
