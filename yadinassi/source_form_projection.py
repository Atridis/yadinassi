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
            # A title is a bounded v8 language map, not arbitrary descendant
            # content. Canonical metadata identifiers and source bytes stay intact.
            try:
                if child.attrib or (child.text or '').strip() or len(child)>64:
                    raise ValueError('invalid localized title envelope')
                translations = {}; seen = set()
                for item in child:
                    if (item.tag != '{'+V8+'}item' or item.attrib
                            or (item.text or '').strip() or (item.tail or '').strip()
                            or len(item) != 2):
                        raise ValueError('invalid localized title item')
                    langs=item.findall('{'+V8+'}lang');texts=item.findall('{'+V8+'}content')
                    if len(langs)!=1 or len(texts)!=1:
                        raise ValueError('invalid localized title fields')
                    lang, content = langs[0], texts[0]
                    if any(n.attrib or len(n) or (n.tail or '').strip() for n in (lang,content)):
                        raise ValueError('invalid localized title value')
                    key=(lang.text or '').strip().casefold()
                    if not key or len(key)>32 or key in seen:
                        raise ValueError('ambiguous localized title language')
                    seen.add(key)
                    if content.text and content.text.strip():
                        translations[key]=content.text
                language='ru' if 'ru' in translations else next(iter(translations),'')
                if not language:
                    raise ValueError('no nonempty localized title')
                label=translations[language]
                child.clear();child.text=label[:1024]
                note(path,'Localized title: Russian' if language=='ru' else
                     'Localized title: Russian unavailable; fallback '+language)
                if len(label)>1024:
                    note(path,'Localized title truncated to 1024 characters')
            except ValueError as error:
                note(path,'Title unavailable: '+str(error));node.remove(child)
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
            main=node.find(L+'MainAttribute')
            if main is not None:
                # A false serialization flag is not an object/persistence grant.
                # Normalize only exact scalar false, leaving malformed/true
                # declarations unavailable rather than guessing their meaning.
                if main.attrib or len(main) or (main.tail or '').strip() or (main.text or '').strip() != 'false':
                    raise ValueError('main object attribute requires persistence host or valid false flag')
                node.remove(main)
            kind,_,_=_type({'{'+MD+'}Type':node.find(L+'Type')},namespaces,{})
            if kind not in ('string','number','boolean','datetime'):raise ValueError('non-scalar form data')
            if main is not None:note(path,'Explicit non-main scalar attribute retained')
        except (ValueError, TypeError) as error:
            note(path,'Attribute unavailable: '+str(error));attributes.remove(node);continue
        for value in node.findall('.//{'+V8+'}Type'):
            value.text='xs:'+{'string':'string','number':'decimal','boolean':'boolean','datetime':'dateTime'}[kind]
        retained.add(node.get('name').casefold())
    commands=root.find(L+'Commands'); command_names={}
    for node in _inventory(commands,{L+'Command'},64):
        path='Commands.'+node.get('name');trim(node,('Title','Action'),path);title(node,path)
        action=node.find(L+'Action')
        if action is None or not (action.text or '').strip():
            note(path,'Command unavailable: no supported action');commands.remove(node);continue
        command_names[node.get('name').casefold()]=node.get('name')
    supported={'InputField','LabelField','CheckBoxField','Button','UsualGroup','Pages','Page','CommandBar'}
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
            if kind == 'CommandBar':
                # Presentation only: retain explicit children, never synthesize
                # standard commands or infer database capabilities from Autofill.
                trim(node,('Title','Visible','Enabled','ReadOnly','ChildItems'),path)
                node.tag=L+'UsualGroup';kind='UsualGroup'
                ET.SubElement(node,L+'Group').text='Horizontal'
                ET.SubElement(node,L+'ShowTitle').text='false'
                note(path,'Explicit command bar projected as horizontal group; no automatic commands')
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
            # XML exports qualify declared form commands. This is an explicit
            # local command binding, not a standard/global command grant.
            if kind=='Button' and target is not None and not target.attrib and not len(target):
                parts=value.split('.')
                if (len(parts)==3 and [p.casefold() for p in parts[:2]]==['form','command']
                        and parts[2].casefold() in command_names):
                    value=command_names[parts[2].casefold()]
                    target.text=value
                    note(path,'Bound declared Form.Command: '+value)
            if value.casefold() not in (command_names if kind=='Button' else retained):
                note(path,'Control unavailable: unbound '+value);container.remove(node);continue
            events(node,{'onchange'},path)
    items(root.find(L+'ChildItems'))
    if omitted:
        diagnostics.append({'path':'Form','reason':'Additional unsupported features omitted: '+str(omitted)})
    root.set('xmlns:xs',XS)
    return SourceFormProjection(ET.tostring(root,encoding='utf-8'),tuple(diagnostics),sha256(raw).hexdigest())
