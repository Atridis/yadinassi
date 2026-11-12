"""Owned String64 constant declaration and byte-preserved baseline permissions."""
from pathlib import Path
import hashlib
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
VALIDATION_MODE='owned-constant-string-material-projection-v1'
ASSET_HASHES={'OwnedString.xml': 'a8df6e3791fbe3adf6e14500aa51bcc49dd0bb6054ec463c82acca30675961d5'}
PARAMETERS=('OwnedString',)

def load_saved():
    assets={}
    for name,digest in ASSET_HASHES.items():
        path=Path(__file__).parent/name
        original._require(not path.is_symlink())
        raw=path.read_bytes()
        original._require(0<len(raw)<=MAX_FILE and hashlib.sha256(raw).hexdigest()==digest)
        assets[name]=raw
    return original.load_saved()[0],{**assets,'generated/observe.bsl':route.source()}

def prepare(files, *, bootstrap_module=None):
    setup,assets=load_saved();original._baseline(files,setup);expected=dict(files)
    original._require(type(bootstrap_module) is bytes and 0<len(bootstrap_module)<=MAX_FILE)
    original._require('Ext/SessionModule.bsl' in files)
    original._require(files['Ext/SessionModule.bsl'].decode('utf-8-sig').replace('\r\n','\n') == bootstrap_module.decode('utf-8-sig').replace('\r\n','\n'))
    md=original.MD
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:''.join('<'+p+'Constant>'+name+'</'+p+'Constant>' for name in PARAMETERS))
    rights=original.ROLE_FILES[1];rn=original.RIGHTS
    expected[rights]=original._append(files[rights],(rn+'}Rights',),lambda p:''.join('<'+p+'object><'+p+'name>Constant.'+name+'</'+p+'name>'+''.join('<'+p+'right><'+p+'name>'+right+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>' for right in ('Read','Update'))+'</'+p+'object>' for name in PARAMETERS))
    for name in PARAMETERS:expected['Constants/'+name+'.xml']=assets[name+'.xml']
    used=set()
    for name,raw in expected.items():
        if name.endswith('.xml'):
            root,_=original._xml(raw)
            for node in root.iter():
                if 'uuid' in node.attrib:
                    value=original._uuid(node.attrib['uuid']);original._require(value not in used);used.add(value)
    _files(expected);return setup,expected

def verify_redump(expected,actual):
    _files(expected);_files(actual);original._require(set(expected)==set(actual))
    # Scalar declaration Name/UUID/type/qualifiers and module text are all material.
    # Existing verifier canonicalizes namespace prefixes/whitespace/ChildObjects order.
    for name in expected:original.verify_redump({name:expected[name]},{name:actual[name]})
    return True

def redump_diagnostic(expected,actual):
    # Only finite labels; never raw platform text or arbitrary metadata names.
    result=[]
    for name in sorted(set(expected)|set(actual)):
        if len(result)==12:break
        if name not in expected or name not in actual:result.append('inventory differs');continue
        try:original.verify_redump({name:expected[name]},{name:actual[name]})
        except ValueError:
            label='session parameter' if name.startswith('Constants/') else 'session module' if name=='Ext/SessionModule.bsl' else 'baseline'
            result.append(label+' differs')
    return result

def valid_diagnostic(value):
    return type(value) is list and len(value)<=12 and all(type(v) is str and v in ('inventory differs','session parameter differs','session module differs','baseline differs') for v in value)
