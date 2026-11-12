"""Owned scalar session declarations and byte-preserved baseline permissions."""
from pathlib import Path
import hashlib
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
VALIDATION_MODE='owned-session-parameter-material-projection-v1'
ASSET_HASHES={'OwnedBoolean.xml': 'd13ff7e2630e864cf05c65107864ef44bf1a6633dc1bc70bc810970e1d7f2fc5', 'OwnedCalls.xml': 'e3e72c90dc41ec97c44f9cc5663b221b9604c2192c95c433912c830229604368', 'OwnedDate.xml': 'e82188d649b60d9f5b3d25309ac09ee55d5b58840dabc1a0be33ef3e7467da71', 'OwnedFailure.xml': '594ddbc9f4bb96a0a83320be45b495366b1dd46dc79204cbeddb64e12d9ef5d1', 'OwnedLazy.xml': '96854dab463060d3549e955dd3ec97719884758727fd2113296812c19a1c79b5', 'OwnedLinked.xml': 'a42217f147d64ae33b890b22710154ae10e92f6bce8bf4aaa8c8f9b3192d734e', 'OwnedMissing.xml': '827c620c530e9c6484a568637f31cb8222b2ad133a1b82f43e412ebc8f5ac206', 'OwnedMissingCalls.xml': '1c37cc25722dfea1f42307819de5c38981cbec3bab3ceb052b06eae16a9bcd28', 'OwnedNumber.xml': '164694f5d40c2e4be5d86c940faa97641f0b647a36cbb899191cfc08f9a5cd4b', 'OwnedStartup.xml': '55d05852efc493c63dbf1c171ccf8288f1407f10d8535666d6191d1612af2e05', 'OwnedStartupUndefined.xml': 'b03ed37805074e663131f2587ab9aa529f7e7461fafbdb6aff51b38bfd11fc0f', 'OwnedString.xml': '3811815105150c81a3cfc4230cf6a09b5982394ff0ab31e53bb8a5e672e26500', 'OwnedWitness.xml': 'f9a38db3b0402018908770405c5dc14275603722793f4022c6bd189de50fc2e6', 'SessionModule.bsl': 'bcd9500690f7c63c8d8149c9cb26bc9dff2f172cda0ead2f1599f4e341c5f0f2'}
PARAMETERS=('OwnedStartup', 'OwnedStartupUndefined', 'OwnedLazy', 'OwnedCalls', 'OwnedLinked', 'OwnedMissing', 'OwnedMissingCalls', 'OwnedBoolean', 'OwnedDate', 'OwnedNumber', 'OwnedString', 'OwnedFailure', 'OwnedWitness')

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
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:''.join('<'+p+'SessionParameter>'+name+'</'+p+'SessionParameter>' for name in PARAMETERS))
    rights=original.ROLE_FILES[1];rn=original.RIGHTS
    expected[rights]=original._append(files[rights],(rn+'}Rights',),lambda p:''.join('<'+p+'object><'+p+'name>SessionParameter.'+name+'</'+p+'name>'+''.join('<'+p+'right><'+p+'name>'+right+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>' for right in ('Get','Set'))+'</'+p+'object>' for name in PARAMETERS))
    for name in PARAMETERS:expected['SessionParameters/'+name+'.xml']=assets[name+'.xml']
    expected['Ext/SessionModule.bsl']=assets['SessionModule.bsl']
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
            label='session parameter' if name.startswith('SessionParameters/') else 'session module' if name=='Ext/SessionModule.bsl' else 'baseline'
            result.append(label+' differs')
    return result

def valid_diagnostic(value):
    return type(value) is list and len(value)<=12 and all(type(v) is str and v in ('inventory differs','session parameter differs','session module differs','baseline differs') for v in value)
