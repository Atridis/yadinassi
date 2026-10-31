"""Same bounded compiler/marker projection with 24 fixed setup witness phases."""
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
    'saved-xml-profile','saved-fragments','configuration-bound','baseline-catalogs',
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
            actual_sha256=hashlib.sha256(raw).hexdigest(),identity='unverified',namespaces=None,differences=[])
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
        exact(row,('index','expected_sha256','actual_sha256','identity','namespaces','differences'))
        index=row['index'];require(type(index) is int and previous<index<len(expected));previous=index
        require(row['expected_sha256']==hashlib.sha256(expected[index]).hexdigest() and digest(row['actual_sha256']))
        require(row['identity'] in ('verified','unverified'))
        ns=row['namespaces'];diff=row['differences']
        require(type(diff) is list and len(diff)<=16)
        if row['identity']=='unverified':require(ns is None and not diff);continue
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
