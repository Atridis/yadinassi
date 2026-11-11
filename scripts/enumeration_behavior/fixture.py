"""Owned Enum XML and material source projection; no runtime parity claim."""
from pathlib import Path
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
VALIDATION_MODE='owned-enumeration-material-projection-v1'
ASSET_HASHES={'Enum.xml': '0e7c9247b8850846640f32c6b05677b898366d8a721e5c5751efadc45155e717'}

def load_saved():
    import hashlib
    root=Path(__file__).parent;assets={}
    for name,digest in ASSET_HASHES.items():
        p=root/name
        if p.is_symlink():raise ValueError('fixture symlink')
        raw=p.read_bytes()
        if not 0<len(raw)<=MAX_FILE or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('fixture changed')
        assets[name]=raw
    return original.load_saved()[0],{**assets,'generated/observe.bsl':route.source()}

def prepare(files):
    setup,assets=load_saved();original._baseline(files,setup);expected=dict(files)
    md=original.MD;rights=original.RIGHTS
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:'<'+p+'Enum>OwnedStatus</'+p+'Enum>')
    def grants(p):
        return '<'+p+'object><'+p+'name>Enum.OwnedStatus</'+p+'name><'+p+'right><'+p+'name>Read</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right></'+p+'object>'
    expected[original.ROLE_FILES[1]]=original._append(files[original.ROLE_FILES[1]],(rights+'}Rights',),grants)
    expected['Enums/OwnedStatus.xml']=assets['Enum.xml']
    _files(expected);return setup,expected

def _owned_projection(raw):
    # Element order in EnumValues is semantic; original._signature sorts all
    # ChildObjects, so do not use that general canonicalizer for this object.
    root,_=original._xml(raw);md='{'+original.MD+'}'
    def one(node,name):
        found=node.findall(md+name);original._require(len(found)==1);return found[0]
    def sig(node):
        original._require(not (node.tail or '').strip())
        return node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),tuple(sig(c) for c in node)
    original._require(root.tag==md+'MetaDataObject' and len(root)==1)
    obj=one(root,'Enum');original._require(set(obj.attrib)=={'uuid'})
    original._require(len(obj)==3 and {c.tag for c in obj}=={md+'InternalInfo',md+'Properties',md+'ChildObjects'})
    props=one(obj,'Properties');children=one(obj,'ChildObjects');values=[]
    for child in children:
        original._require(child.tag==md+'EnumValue' and set(child.attrib)=={'uuid'} and len(child)==1)
        p=one(child,'Properties')
        original._require({c.tag for c in p}=={md+'Name',md+'Synonym',md+'Comment'} and len(p)==3)
        values.append((tuple(sorted(child.attrib.items())),sig(one(p,'Name')),sig(one(p,'Synonym')),sig(one(p,'Comment'))))
    original._require(len(values)==2 and len({v[0] for v in values})==2)
    return tuple(sorted(obj.attrib.items())),sig(one(props,'Name')),sig(one(props,'Synonym')),sig(one(props,'Comment')),tuple(values)

def verify_redump(expected,actual):
    _files(expected);_files(actual);original._require(set(expected)==set(actual))
    for path in expected:
        if path=='Enums/OwnedStatus.xml':original._require(_owned_projection(expected[path])==_owned_projection(actual[path]))
        else:original.verify_redump({path:expected[path]},{path:actual[path]})
    return True

def redump_diagnostic(expected, actual):
    """Bounded metadata-only differences; never a substitute for verification.

    Text/attribute values are exposed only for the two source-owned metadata
    objects and only as short ASCII tokens. No modules, logs or database rows.
    """
    import re
    import hashlib
    owned={'Enums/OwnedStatus.xml'}
    result=[]
    def token(value):
        if re.fullmatch(r'[A-Za-z0-9_.:{}/\-]{0,64}',value):return value
        return 'sha256:'+hashlib.sha256(value.encode()).hexdigest()[:16]
    def add(value):
        if len(result)<12:result.append(value[:120])
    def flattened(raw):
        root,_=original._xml(raw);out={}
        def visit(node,path):
            name=node.tag.rsplit('}',1)[-1];path=path+'/'+name
            out[path]=(token((node.text or '').strip()),tuple(sorted((token(k),token(v)) for k,v in node.attrib.items())))
            counts={}
            for child in node:
                name=child.tag.rsplit('}',1)[-1];counts[name]=counts.get(name,0)+1
                visit(child,path+'['+str(counts[name])+']')
        visit(root,'');return out
    for name in sorted(set(expected)|set(actual)):
        label=name if name in owned or name=='Configuration.xml' else 'file-sha256:'+hashlib.sha256(name.encode()).hexdigest()[:16]
        if name not in expected or name not in actual:
            add(label+(': added' if name not in expected else ': missing'));continue
        if name=='ConfigDumpInfo.xml':continue
        try:
            if name.endswith('.xml'):
                if original._signature(expected[name])==original._signature(actual[name]):continue
                add(label+': XML differs')
                if name in owned:
                    left,right=flattened(expected[name]),flattened(actual[name])
                    for key in sorted(set(left)|set(right)):
                        if left.get(key)!=right.get(key):
                            add(key.removeprefix('/MetaDataObject')+': '+str(left.get(key))+' -> '+str(right.get(key)))
            elif expected[name].decode('utf-8-sig').replace('\r\n','\n')!=actual[name].decode('utf-8-sig').replace('\r\n','\n'):
                add(label+': content differs')
        except (ValueError,UnicodeError):add(label+': invalid XML or encoding')
    return result


def valid_diagnostic(value):
    return (type(value) is list and len(value)<=12 and all(type(v) is str and
        len(v)<=120 and all(32<=ord(c)<=126 for c in v) for v in value))
