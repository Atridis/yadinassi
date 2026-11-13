"""Loss-explicit presentation projection for experimental memory-only source UI.

Original source bytes are never modified. Unsupported data and controls remain
unavailable to BSL; this adapter never fabricates object persistence or values.
The strict owned/database form loader is deliberately not changed.
"""
from dataclasses import dataclass
from hashlib import sha256
import xml.etree.ElementTree as ET
from .configuration_xml import _parse, _type, MD, V8, XS
from .configuration_forms import L, _inventory
from .form_model import BSLClientApplicationForm


@dataclass(frozen=True)
class SourceFormProjection:
    xml: bytes
    diagnostics: tuple
    source_sha256: str


def project_source_form(raw):
    root, namespaces = _parse(raw)
    if root.tag != L+'Form' or set(root.attrib)-{'version'}:
        raise ValueError('unsupported form definition envelope')
    diagnostics = []
    omitted = 0
    def note(path, reason):
        nonlocal omitted
        if len(diagnostics) < 32:
            diagnostics.append({'path':path[:128], 'reason':reason[:256]})
        else:
            omitted += 1
    def trim(node, allowed, path):
        seen=set()
        for child in list(node):
            if child.tag in seen:raise ValueError('duplicate source form property')
            seen.add(child.tag)
            if child.tag not in {L+x for x in allowed}:
                note(path, 'Ignored unsupported property: '+child.tag.rsplit('}',1)[-1]);node.remove(child)
    def title(node, path):
        child=node.find(L+'Title')
        if child is not None and len(child):
            contents=child.findall('.//{'+V8+'}content')
            label=next((n.text for n in contents if n.text),'')
            if not label:
                note(path,'Unsupported structured title');node.remove(child)
            else:
                child.clear();child.text=label[:1024];note(path,'Localized title: first available translation')
    def events(node, allowed, path):
        child=node.find(L+'Events')
        if child is None:return
        for event in list(child):
            key=event.get('name','').casefold();key=BSLClientApplicationForm.EVENT_NAMES.get(key,key)
            if key not in allowed:
                note(path,'Event not executed: '+event.get('name',''));child.remove(event)
    trim(root,('Title','Attributes','ChildItems','Commands','Events'),'Form');title(root,'Form')
    events(root,set(BSLClientApplicationForm.EVENTS),'Form')
    attributes=root.find(L+'Attributes'); retained=set()
    for node in _inventory(attributes,{L+'Attribute'},128):
        path='Attributes.'+node.get('name')
        trim(node,('Type','Title','MainAttribute'),path);title(node,path)
        try:
            if node.find(L+'MainAttribute') is not None:raise ValueError('main object attribute requires persistence host')
            kind,_,_=_type({'{'+MD+'}Type':node.find(L+'Type')},namespaces,{})
            if kind not in ('string','number','boolean','datetime'):raise ValueError('non-scalar form data')
        except (ValueError, TypeError) as error:
            note(path,'Attribute unavailable: '+str(error));attributes.remove(node);continue
        for value in node.findall('.//{'+V8+'}Type'):
            value.text='xs:'+{'string':'string','number':'decimal','boolean':'boolean','datetime':'dateTime'}[kind]
        retained.add(node.get('name').casefold())
    commands=root.find(L+'Commands'); command_names=set()
    for node in _inventory(commands,{L+'Command'},64):
        path='Commands.'+node.get('name');trim(node,('Title','Action'),path);title(node,path)
        action=node.find(L+'Action')
        if action is None or not (action.text or '').strip():
            note(path,'Command unavailable: no supported action');commands.remove(node);continue
        command_names.add(node.get('name').casefold())
    supported={'InputField','LabelField','CheckBoxField','Button','UsualGroup','Pages','Page'}
    seen_names=set();seen_ids=set()
    def preflight(container, depth=0):
        if container is None:return
        if depth>8:raise ValueError('source form layout depth limit')
        for node in _inventory(container,{child.tag for child in container},128):
            key=node.get('name').casefold();identity=int(node.get('id'))
            if key in seen_names or identity in seen_ids:raise ValueError('duplicate source form item')
            seen_names.add(key);seen_ids.add(identity)
            if len(seen_names)>128:raise ValueError('source form item limit')
            children=node.findall(L+'ChildItems')
            if len(children)>1:raise ValueError('duplicate source child inventory')
            if children:preflight(children[0],depth+1)
    preflight(root.find(L+'ChildItems'))
    def items(container,parent_kind='',depth=0):
        if container is None:return
        for node in list(container):
            item_name=node.get('name','');kind=node.tag.removeprefix(L);path='Items.'+item_name
            if kind not in supported:
                note(path,'Control unavailable: '+kind);container.remove(node);continue
            if kind in ('UsualGroup','Pages','Page'):
                fields=('Title','Visible','Enabled','ReadOnly','ChildItems','PagesRepresentation','Group','ShowTitle')
            else:
                fields=('Title','Visible','Enabled','ReadOnly','CommandName') if kind=='Button' else ('Title','Visible','Enabled','ReadOnly','DataPath','Events')
            trim(node,fields,path);title(node,path)
            if kind in ('UsualGroup','Pages','Page'):
                items(node.find(L+'ChildItems'),kind,depth+1)
                if kind=='Pages' and not len(node.find(L+'ChildItems') or []):
                    note(path,'Empty unsupported pages removed');container.remove(node)
                continue
            target=node.find(L+('CommandName' if kind=='Button' else 'DataPath'))
            value=(target.text or '').strip() if target is not None else ''
            if value.casefold() not in (command_names if kind=='Button' else retained):
                note(path,'Control unavailable: unbound '+value);container.remove(node);continue
            events(node,{'onchange'},path)
    items(root.find(L+'ChildItems'))
    if omitted:
        diagnostics.append({'path':'Form','reason':'Additional unsupported features omitted: '+str(omitted)})
    root.set('xmlns:xs',XS)
    return SourceFormProjection(ET.tostring(root,encoding='utf-8'),tuple(diagnostics),sha256(raw).hexdigest())
