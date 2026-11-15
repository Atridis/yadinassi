"""One exact owned XDTO package and nonprivileged common module; baseline security unchanged."""
from pathlib import Path
import hashlib
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
VALIDATION_MODE='owned-configuration-xdto-linked-load-update-observation-v1'
ASSET_HASHES={'OwnedRecords.xml': '756c13cb6d55f9b15a58c44d390c815bc9f1bac32f2c103040eb5255da39402c', 'Package.bin': '6f925b63d221d8c523ef70b134e443228ba1fa330275e8fa24208e318a5049c5', 'OwnedEnvelope.xml': '315861e7134b2df874e8f2837eae2336a45dcffd0752f89c1218f04ef41eacbe', 'Envelope.bin': 'fb2a111a593831d83845dda0c144a1eac9c07b52d97f033f79f462c0a10bdfed', 'OwnedXDTOBridge.xml': '13e5f3d11bc77fd47c05b2cb5118f3cc0e89221969439374841ed0c2a92faae5', 'Module.bsl': '88bb2ece8aa6d3b97c7089630c7f16c481c4faeeebcc45605d210121628b233a'}
RESOURCES={'XDTOPackages/OwnedRecords/Ext/Package.bin':'Package.bin','XDTOPackages/OwnedEnvelope/Ext/Package.bin':'Envelope.bin'}


def _files(files):
    """Extend baseline admission for the exact source-pinned XDTO package bytes."""
    original._require(type(files) is dict and 1<=len(files)<=256)
    metadata={}
    _,assets=load_saved()
    total=0;folded=set()
    for path,raw in files.items():
        original._require(type(path) is str and path.casefold() not in folded)
        folded.add(path.casefold())
        original._require(type(raw) is bytes and len(raw)<=MAX_FILE)
        total+=len(raw);original._require(total<=MAX_TOTAL)
        if path in RESOURCES:
            original._require(raw==assets[RESOURCES[path]])
        else:
            metadata[path]=raw
    original._files(metadata)
    return files


def load_saved():
    assets={}
    for name,digest in ASSET_HASHES.items():
        path=Path(__file__).parent/name
        original._require(not path.is_symlink())
        raw=path.read_bytes()
        original._require(0<len(raw)<=MAX_FILE and hashlib.sha256(raw).hexdigest()==digest)
        assets[name]=raw
    return original.load_saved()[0],{**assets,'generated/observe.bsl':route.source()}


def prepare(files,*,bootstrap_module=None):
    setup,assets=load_saved()
    original._baseline(files,setup)
    original._require(not any(path.startswith(('XDTOPackages/','CommonModules/')) for path in files))
    original._require(type(bootstrap_module) is bytes and 0<len(bootstrap_module)<=MAX_FILE)
    original._require(files['Ext/SessionModule.bsl'].decode('utf-8-sig').replace('\r\n','\n')==bootstrap_module.decode('utf-8-sig').replace('\r\n','\n'))
    expected=dict(files);md=original.MD
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:'<'+p+'XDTOPackage>OwnedRecords</'+p+'XDTOPackage><'+p+'XDTOPackage>OwnedEnvelope</'+p+'XDTOPackage><'+p+'CommonModule>OwnedXDTOBridge</'+p+'CommonModule>')
    expected['XDTOPackages/OwnedRecords.xml']=assets['OwnedRecords.xml']
    expected['XDTOPackages/OwnedEnvelope.xml']=assets['OwnedEnvelope.xml']
    expected['CommonModules/OwnedXDTOBridge.xml']=assets['OwnedXDTOBridge.xml']
    expected['CommonModules/OwnedXDTOBridge/Ext/Module.bsl']=assets['Module.bsl']
    for path,name in RESOURCES.items():expected[path]=assets[name]
    used=set()
    for name,raw in expected.items():
        if name.endswith('.xml'):
            root,_=original._xml(raw)
            for node in root.iter():
                if 'uuid' in node.attrib:
                    value=original._uuid(node.attrib['uuid'])
                    original._require(value not in used);used.add(value)
    _files(expected)
    return setup,expected


def verify_prepared(expected,actual):
    """Check our still-owned prepared inputs, not a Designer redump."""
    _files(expected);_files(actual)
    original._require(expected==actual)
    return True


def valid_diagnostic(value):
    # Kept for the shared host report envelope, not a redump acceptance gate.
    return type(value) is list and not value
