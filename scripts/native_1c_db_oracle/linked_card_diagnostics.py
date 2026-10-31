"""Same bounded compiler/marker projection with 24 fixed setup witness phases."""
import re
import catalog_read_diagnostics as base
from protocol import require
PHASES=base.PHASES+tuple(f'setup-witness-{i:02}' for i in range(13,25))


def validate(value):
    phase=value.get('phase')
    require(phase is None or phase in PHASES)
    projected=dict(value)
    if phase not in base.PHASES and phase is not None:projected['phase']='setup'
    base.validate(projected)


def collect(backend,database,previous):
    projected=None if previous is None else dict(previous)
    phase=None if previous is None else previous['phase']
    require(phase is None or phase in PHASES)
    if projected is not None and phase not in base.PHASES:projected['phase']='setup'
    result=base.collect(backend,database,projected)
    if previous is not None:result['phase']=phase
    validate(result)
    return result

# Install diagnostics are fixed schema observations, never exception/log text.
INSTALL_STAGES=('prepare','extend','instrument','import','apply','redump','inventory',
                'fragments','mapping','xml-compare','module-compare','audit')
INSTALL_CATEGORIES=('saved-xml-bound','saved-namespace-profile','saved-xml',
    'saved-xml-profile','redump-profile','redump-qname','redump-xml','saved-fragments','configuration-bound','baseline-catalogs',
    'rights-bound','rights-profile','other-value-error','import-error',
    'filesystem-error','oracle-error','unexpected')
DIFF_KINDS=('tag','attributes','text','child-count','missing','added')


def install_failure(stage,error,saved,redumped):
    import hashlib,io,xml.etree.ElementTree as ET
    from linked_card_packet.linked import NAMESPACES
    from protocol import OracleError
    require(stage in INSTALL_STAGES)
    if isinstance(error,OracleError):category='oracle-error'
    elif isinstance(error,ImportError):category='import-error'
    elif isinstance(error,OSError):category='filesystem-error'
    elif isinstance(error,ValueError):category=str(error) if str(error) in INSTALL_CATEGORIES else 'other-value-error'
    else:category='unexpected'
    result=dict(stage=stage,category=category,catalogs=[])
    md='{http://v8.1c.ru/8.3/MDClasses}'
    for index,(name,expected) in enumerate(saved.items()):
        if name not in redumped:continue
        raw=redumped[name]
        row=dict(index=index,expected_sha256=hashlib.sha256(expected).hexdigest(),
            actual_sha256=hashlib.sha256(raw).hexdigest(),identity='unverified',namespaces=None,differences=[],fill_values=[])
        result['catalogs'].append(row)
        if len(raw)>65536 or b'<!' in raw:continue
        try:
            left=ET.fromstring(expected);right=ET.fromstring(raw)
            a=left.find(md+'Catalog');b=right.find(md+'Catalog')
            if a is None or b is None or a.get('uuid')!=b.get('uuid') or a.findtext(md+'Properties/'+md+'Name')!=b.findtext(md+'Properties/'+md+'Name'):continue
            bindings=[pair for _,pair in ET.iterparse(io.BytesIO(raw),events=('start-ns',))]
        except (ET.ParseError,ValueError):continue
        if len(bindings)>512:continue
        row['identity']='verified'
        row['fill_values']=_fill_values(expected,raw)
        row['namespaces']=dict(count=len(bindings),known_uri_only=all(uri in NAMESPACES.values() for _,uri in bindings),bindings_equal=dict(bindings)==NAMESPACES)
        # Paths contain only source-owned expected tag names or fixed 'other'.
        known={node.tag for node in left.iter()};out=row['differences']
        def tag(node):return node.tag.split('}')[-1] if node.tag in known else 'other'
        def walk(a,b,path,depth):
            if len(out)>=16 or depth>12:return
            def add(kind):
                if len(out)<16:out.append(dict(path=path,kind=kind))
            if a.tag!=b.tag:add('tag')
            if a.attrib!=b.attrib:add('attributes')
            if (a.text or '').strip()!=(b.text or '').strip():add('text')
            if len(a)!=len(b):add('child-count')
            # Align property tags so one inserted native default does not hide
            # behind sixteen shifted-sibling differences. Repeated declarations
            # still pair by occurrence, retaining their measured order.
            keys=list(dict.fromkeys(n.tag for n in list(a)+list(b)))[:64]
            for key in keys:
                aa=[n for n in a if n.tag==key];bb=[n for n in b if n.tag==key]
                for i in range(min(max(len(aa),len(bb)),64)):
                    if len(out)>=16:break
                    node=aa[i] if i<len(aa) else bb[i]
                    child_path=path+'/'+tag(node)+'['+str(i)+']'
                    if i>=len(aa):out.append(dict(path=child_path,kind='added'))
                    elif i>=len(bb):out.append(dict(path=child_path,kind='missing'))
                    else:walk(aa[i],bb[i],child_path,depth+1)
        walk(left,right,tag(left),0)
    validate_install_failure(result,saved)
    return result


def validate_install_failure(value,saved):
    import hashlib,re,xml.etree.ElementTree as ET
    from protocol import exact,digest
    exact(value,('stage','category','catalogs'))
    require(value['stage'] in INSTALL_STAGES and value['category'] in INSTALL_CATEGORIES)
    rows=value['catalogs'];require(type(rows) is list and len(rows)<=2)
    expected=list(saved.values());previous=-1
    for row in rows:
        exact(row,('index','expected_sha256','actual_sha256','identity','namespaces','differences','fill_values'))
        index=row['index'];require(type(index) is int and previous<index<len(expected));previous=index
        require(row['expected_sha256']==hashlib.sha256(expected[index]).hexdigest() and digest(row['actual_sha256']))
        require(row['identity'] in ('verified','unverified'))
        ns=row['namespaces'];diff=row['differences']
        require(type(diff) is list and len(diff)<=16)
        if row['identity']=='unverified':require(ns is None and not diff and row['fill_values']==[]);continue
        _validate_fill_values(row['fill_values'],expected[index])
        exact(ns,('count','known_uri_only','bindings_equal'))
        require(type(ns['count']) is int and 0<=ns['count']<=512 and type(ns['known_uri_only']) is bool and type(ns['bindings_equal']) is bool)
        tags={n.tag.split('}')[-1] for n in ET.fromstring(expected[index]).iter()}|{'other'}
        for item in diff:
            exact(item,('path','kind'));require(item['kind'] in DIFF_KINDS and type(item['path']) is str and len(item['path'])<=1024)
            parts=item['path'].split('/');require(1<=len(parts)<=14)
            for part in parts:
                m=re.fullmatch(r'([A-Za-z][A-Za-z0-9]*)(?:\[([0-9]{1,2})\])?',part)
                require(m is not None and m[1] in tags and (m[2] is None or int(m[2])<64))
    return value


def _fill_values(expected,raw):
    """Bounded synthetic defaults only, never ordinary catalog record values."""
    import io,xml.etree.ElementTree as ET
    md='{http://v8.1c.ru/8.3/MDClasses}';xsi='{http://www.w3.org/2001/XMLSchema-instance}'
    pending=[];stack=[];scopes={}
    parser=ET.iterparse(io.BytesIO(raw),events=('start-ns','start','end'))
    for event,item in parser:
        if event=='start-ns':pending.append(item)
        elif event=='start':
            scope=dict(stack[-1]) if stack else {};scope.update(pending);pending=[]
            stack.append(scope);scopes[id(item)]=scope
        else:stack.pop()
    left=ET.fromstring(expected);right=parser.root
    a=left.find(md+'Catalog');b=right.find(md+'Catalog')
    source=a.findall(md+'ChildObjects/'+md+'Attribute');actual=b.findall(md+'ChildObjects/'+md+'Attribute');out=[]
    for index,attr in enumerate(source):
        props=attr.find(md+'Properties')
        if props.find(md+'FillValue') is not None or index>=len(actual):continue
        other=actual[index];otherprops=other.find(md+'Properties')
        if other.get('uuid')!=attr.get('uuid') or otherprops is None or otherprops.findtext(md+'Name')!=props.findtext(md+'Name'):continue
        nodes=otherprops.findall(md+'FillValue')
        if len(nodes)!=1:continue
        node=nodes[0];text=(node.text or '').strip();scope=scopes[id(node)]
        if len(text)>128 or not text.isascii() or any(ord(c)<32 for c in text):continue
        if set(node.attrib)-{xsi+'type',xsi+'nil'} or len(node):continue
        lexical=node.get(xsi+'type');namespace=local=None
        if lexical is not None:
            pieces=lexical.split(':')
            if len(pieces)==1:namespace=scope.get('');local=pieces[0]
            elif len(pieces)==2:namespace=scope.get(pieces[0]);local=pieces[1]
            if namespace is None or len(namespace)>256 or local is None or not re.fullmatch('[A-Za-z_][A-Za-z_0-9.]*',local) or len(local)>128:continue
        nil=node.get(xsi+'nil')
        if nil not in (None,'true','false','0','1'):continue
        out.append(dict(attribute_index=index,attribute_uuid=attr.get('uuid'),type_namespace=namespace,type_local=local,nil=nil,text=text))
    return out


def _validate_fill_values(rows,expected):
    import xml.etree.ElementTree as ET
    from protocol import exact
    md='{http://v8.1c.ru/8.3/MDClasses}'
    attrs=ET.fromstring(expected).findall(md+'Catalog/'+md+'ChildObjects/'+md+'Attribute')
    require(type(rows) is list and len(rows)<=3);previous=-1
    for row in rows:
        exact(row,('attribute_index','attribute_uuid','type_namespace','type_local','nil','text'))
        i=row['attribute_index'];require(type(i) is int and previous<i<len(attrs));previous=i
        attr=attrs[i];require(row['attribute_uuid']==attr.get('uuid') and attr.find(md+'Properties/'+md+'FillValue') is None)
        ns,local=row['type_namespace'],row['type_local']
        require((ns is None and local is None) or (type(ns) is str and len(ns)<=256 and type(local) is str and len(local)<=128 and re.fullmatch('[A-Za-z_][A-Za-z_0-9.]*',local) is not None))
        require(row['nil'] in (None,'true','false','0','1') and type(row['text']) is str and len(row['text'])<=128 and row['text'].isascii() and all(ord(c)>=32 for c in row['text']))
