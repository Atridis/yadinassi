"""Explicit text/binary common templates, never a general file import grant."""
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True,slots=True)
class CommonTemplateDefinition:
    identity: UUID
    name: str
    kind: str
    content: bytes
    @property
    def path(self):
        suffix='txt' if self.kind=='TextDocument' else 'bin'
        return f'CommonTemplates/{self.name}/Ext/Template.{suffix}'

def read_common_templates(files,names,used,issues):
    from .configuration_xml import MD,_object,_props,_text,_name,_uuid,_fail,_envelope_issues
    if len(names)>128 or len({n.casefold() for n in names})!=len(names):_fail('common template inventory')
    result=[];total=0
    for name in names:
        path=f'CommonTemplates/{name}.xml'
        if path not in files:_fail('missing common template XML')
        obj,ns,root=_object(files[path],'CommonTemplate',include_root=True)
        _envelope_issues(root,obj,issues,name)
        if set(obj.attrib)!={'uuid'} or len(obj)!=1 or obj[0].tag!='{'+MD+'}Properties':_fail('common template envelope')
        if (obj.text or '').strip() or obj[0].attrib or (obj[0].text or '').strip() or (obj[0].tail or '').strip():_fail('common template envelope')
        props=_props(obj)
        if not {'{'+MD+'}Name','{'+MD+'}TemplateType'}<=set(props) or any(k not in {'{'+MD+'}'+n for n in ('Name','Synonym','Comment','TemplateType')} for k in props):_fail('common template properties')
        for key,node in props.items():
            if node.attrib or (node.tail or '').strip():_fail('common template property envelope')
            if key!='{'+MD+'}Synonym' and len(node):_fail('common template scalar property')
        synonym=props.get('{'+MD+'}Synonym')
        if synonym is not None:
            from .configuration_xml import V8
            if (synonym.text or '').strip():_fail('common template synonym')
            seen=set()
            for item in synonym:
                if item.tag!='{'+V8+'}item' or item.attrib or len(item)!=2 or (item.text or '').strip() or (item.tail or '').strip():_fail('common template synonym')
                if [n.tag for n in item]!=['{'+V8+'}lang','{'+V8+'}content'] or any(n.attrib or len(n) or (n.tail or '').strip() for n in item):_fail('common template synonym')
                lang=item[0].text or '';content=item[1].text or ''
                if not lang or len(lang)>32 or lang in seen or len(content)>1024:_fail('common template synonym bounds')
                seen.add(lang)
        if len(_text(props,'Comment',''))>4096:_fail('common template comment bound')
        if _name(_text(props,'Name'))!=name:_fail('common template filename/name mismatch')
        identity=_uuid(obj.get('uuid'))
        if identity in used:_fail('duplicate metadata UUID')
        used.add(identity);kind=_text(props,'TemplateType')
        if kind not in ('TextDocument','BinaryData'):_fail('unsupported common template kind')
        suffix='txt' if kind=='TextDocument' else 'bin';resource=f'CommonTemplates/{name}/Ext/Template.{suffix}'
        if resource not in files:_fail('missing common template resource')
        raw=files[resource];total+=len(raw)
        if len(raw)>1024*1024 or total>8*1024*1024:_fail('common template resource bound')
        if kind=='TextDocument':
            try:text=raw.decode('utf-8-sig')
            except UnicodeError:_fail('invalid common template text encoding')
            from .text_documents import BSLTextDocument
            doc=BSLTextDocument();doc.set_text(text.replace('\r\n','\n').replace('\r','\n'))
        result.append(CommonTemplateDefinition(identity,name,kind,raw))
    return tuple(result)
