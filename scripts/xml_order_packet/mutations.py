import io, re
from xml.parsers import expat
import xml.etree.ElementTree as ET

def nodes(raw):
    # Expat is used only for byte offsets; never serialize an XML tree.
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('DTD')
    parser=expat.ParserCreate(); stack=[]; result=[]
    def start(name,attrs):
        at=parser.CurrentByteIndex
        match=re.match(rb'<(?:[^>"\']|"[^"]*"|\'[^\']*\')*>',raw[at:])
        if not match: raise ValueError('start tag')
        n=dict(name=name,attrs=attrs,start=at,head=at+match.end(),children=[])
        if stack: stack[-1]['children'].append(n)
        stack.append(n);result.append(n)
    def end(name):
        n=stack.pop(); n['end']=n['head'] if raw[n['head']-2:n['head']]==b'/>' else raw.index(b'>',parser.CurrentByteIndex)+1
    parser.StartElementHandler=start;parser.EndElementHandler=end;parser.Parse(raw,True)
    return result

def parent(raw,name):
    found=[n for n in nodes(raw) if n['name']==name]
    if len(found)!=1: raise ValueError('ambiguous parent')
    return found[0]

def rearrange(raw,name,duplicate=False):
    n=parent(raw,name); children=n['children']
    keys=[c['attrs'].get('name') if name in ('Events','ChildItems') else c['name'] for c in children]
    if len(children)<2 or len(keys)!=len(set(keys)):raise ValueError('not unique')
    a,b=children[:2]; x=raw[a['start']:a['end']];y=raw[b['start']:b['end']]
    return raw[:a['start']]+(x+x if duplicate else y)+raw[a['end']:b['start']]+(y if duplicate else x)+raw[b['end']:]

def attributes(raw):
    n=next(n for n in nodes(raw) if len(n['attrs'])>=2 and not any(k.startswith('xmlns') for k in n['attrs']))
    head=raw[n['start']:n['head']]
    tokens=list(re.finditer(rb'\s+[^\s=<>]+\s*=\s*(?:"[^"]*"|\'[^\']*\')',head))
    a,b=tokens[:2]
    changed=head[:a.start()]+b.group()+head[a.end():b.start()]+a.group()+head[b.end():]
    return raw[:n['start']]+changed+raw[n['head']:]

def projection(raw,allow=False):
    # Scope per element (including unused bindings), exact text/QName spelling.
    stream=ET.iterparse(io.BytesIO(raw),events=('start','end','start-ns')); scopes={};stack=[];pending=[]
    for event,n in stream:
        if event=='start-ns':pending.append(n)
        elif event=='start':
            scope=dict(stack[-1]) if stack else {};scope.update(pending);pending=[];scopes[id(n)]=tuple(sorted(scope.items()));stack.append(scope)
        else:stack.pop()
    def visit(n):
        children=list(n); local=n.tag.split('}')[-1]
        if allow and local in ('Properties','Events'):
            keys=[c.get('name') if local=='Events' else c.tag for c in children]
            if len(keys)!=len(set(keys)):raise ValueError('duplicate')
            children=[c for _,c in sorted(zip(keys,children),key=lambda pair:pair[0])]
        text=n.text or '';tail=n.tail or ''
        if len(n) and not text.strip(' \t\r\n'):text=''
        if not tail.strip(' \t\r\n'):tail=''
        return n.tag,tuple(sorted(n.attrib.items())),scopes[id(n)],text,tuple(visit(c) for c in children),tail
    return visit(stream.root)
