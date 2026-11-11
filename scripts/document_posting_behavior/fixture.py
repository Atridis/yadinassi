"""Owned candidate XML, gated by Designer and material semantic projection.

Designer-added UI defaults are not a parity target. Identities, field types,
posting controls, recorder linkage and handler bytes remain authoritative.
"""
from pathlib import Path
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
ASSET_HASHES={'Document.xml': '483bb1f7ff2ff09ff72ceb3010b6b7ed3de658b140684e45e5b9b76c9ae1493f', 'InformationRegister.xml': 'c9da73ab0079abac97f43a8abd1897eb6b75e8d356d86cc7b588a7cdb93aec46', 'ObjectModule.bsl': '5aa22423943c61f4da3ab3bf5f660035aa3652a0748776e9720bd9d1c25b3270'}

def load_saved():
    import hashlib
    root=Path(__file__).parent;assets={}
    for name,digest in ASSET_HASHES.items():
        p=root/name
        if p.is_symlink():raise ValueError('fixture symlink')
        raw=p.read_bytes()
        if len(raw)>MAX_FILE or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('fixture changed')
        assets[name]=raw
    return original.load_saved()[0],{**assets,'generated/observe.bsl':route.source()}

def prepare(files):
    setup,assets=load_saved();original._baseline(files,setup);expected=dict(files)
    md=original.MD;rights=original.RIGHTS
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:'<'+p+'Document>OwnedPostingDoc</'+p+'Document><'+p+'InformationRegister>OwnedPostingRows</'+p+'InformationRegister>')
    def grants(p):
        result=''
        for name,allowed in [('Document.OwnedPostingDoc',('Read','Insert','Update','Posting','UndoPosting')),('InformationRegister.OwnedPostingRows',('Read','Update'))]:
            result+='<'+p+'object><'+p+'name>'+name+'</'+p+'name>'+''.join('<'+p+'right><'+p+'name>'+right+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>' for right in allowed)+'</'+p+'object>'
        return result
    expected[original.ROLE_FILES[1]]=original._append(files[original.ROLE_FILES[1]],(rights+'}Rights',),grants)
    expected['Documents/OwnedPostingDoc.xml']=assets['Document.xml']
    expected['Documents/OwnedPostingDoc/Ext/ObjectModule.bsl']=assets['ObjectModule.bsl']
    expected['InformationRegisters/OwnedPostingRows.xml']=assets['InformationRegister.xml']
    _files(expected);return setup,expected

OWNED_XML = {'Documents/OwnedPostingDoc.xml': 'Document',
             'InformationRegisters/OwnedPostingRows.xml': 'InformationRegister'}
VALIDATION_MODE = 'owned-metadata-semantic-projection-v1'


def _owned_projection(raw, kind):
    root=original._signature(raw)
    md='{'+original.MD+'}'
    def one(node, name):
        values=[c for c in node[3] if c[0]==md+name]
        original._require(len(values)==1)
        return values[0]
    original._require(root[0]==md+'MetaDataObject' and len(root[3])==1)
    obj=one(root,kind)
    original._require(set(c[0] for c in obj[3])=={md+'InternalInfo',md+'Properties',md+'ChildObjects'})
    props=one(obj,'Properties')
    required=(('Name','NumberType','NumberLength','NumberAllowedLength','NumberPeriodicity',
        'CheckUnique','Autonumbering','Posting','RealTimePosting','RegisterRecordsDeletion',
        'RegisterRecordsWritingOnPost','RegisterRecords','PostInPrivilegedMode',
        'UnpostInPrivilegedMode','DataLockControlMode') if kind=='Document' else
        ('Name','InformationRegisterPeriodicity','WriteMode','DataLockControlMode',
         'EnableTotalsSliceFirst','EnableTotalsSliceLast'))
    selected=tuple(one(props,key) for key in required)
    children=one(obj,'ChildObjects');fields=[]
    for field in children[3]:
        original._require(kind=='InformationRegister' and field[0] in (md+'Dimension',md+'Resource'))
        original._require(len(field[3])==1 and field[3][0][0]==md+'Properties')
        fp=field[3][0]
        fields.append((field[0],field[1],one(fp,'Name'),one(fp,'Type')))
    original._require(len(fields)==len(set((v[0],v[1]) for v in fields)))
    return obj[0],obj[1],selected,tuple(sorted(fields))


def verify_redump(expected, actual):
    # Designer-generated UI defaults and generated type bookkeeping do not
    # establish posting semantics. Validate the measurement's material inputs;
    # unknown executable files, changed handlers and extra user fields still fail.
    _files(expected);_files(actual);original._require(set(expected)==set(actual))
    for path in expected:
        if path in OWNED_XML:
            original._require(_owned_projection(expected[path],OWNED_XML[path])==
                              _owned_projection(actual[path],OWNED_XML[path]))
        else:original.verify_redump({path:expected[path]},{path:actual[path]})
    return True


def redump_diagnostic(expected, actual):
    """Bounded metadata-only differences; never a substitute for verification.

    Text/attribute values are exposed only for the two source-owned metadata
    objects and only as short ASCII tokens. No modules, logs or database rows.
    """
    import re
    import hashlib
    owned={'Documents/OwnedPostingDoc.xml','InformationRegisters/OwnedPostingRows.xml'}
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
