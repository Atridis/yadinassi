"""Owned candidate XML, gated by Designer import and exact redump verification.

This is a candidate, not a previously observed platform export. Failure to
preserve any supplied metadata is fatal; no widened activation is inferred.
"""
from pathlib import Path
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
ASSET_HASHES={'Document.xml': '483bb1f7ff2ff09ff72ceb3010b6b7ed3de658b140684e45e5b9b76c9ae1493f', 'InformationRegister.xml': 'c9da73ab0079abac97f43a8abd1897eb6b75e8d356d86cc7b588a7cdb93aec46', 'ObjectModule.bsl': '44a3bcaa8f7ed570673909121f1b215d2446e63b144f651e24fc4046fccf3de0'}

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

verify_redump=original.verify_redump
