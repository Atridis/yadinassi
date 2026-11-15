"""One exact owned XDTO package and nonprivileged common module; baseline security unchanged."""
from pathlib import Path
import hashlib
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
VALIDATION_MODE='owned-configuration-xdto-load-update-observation-v1'
ASSET_HASHES={'OwnedRecords.xml': '756c13cb6d55f9b15a58c44d390c815bc9f1bac32f2c103040eb5255da39402c', 'Package.bin': '930cc2c632f1c1f07df6616ea581cf470241a56b941182427cd144b64040efcb', 'OwnedXDTOBridge.xml': '13e5f3d11bc77fd47c05b2cb5118f3cc0e89221969439374841ed0c2a92faae5', 'Module.bsl': 'fdfd3a383ed3a2dc361b0aa3219e380fc2b5b9822ec62467957277012dc391a1'}
RESOURCES={'XDTOPackages/OwnedRecords/Ext/Package.bin':'Package.bin'}


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
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:'<'+p+'XDTOPackage>OwnedRecords</'+p+'XDTOPackage><'+p+'CommonModule>OwnedXDTOBridge</'+p+'CommonModule>')
    expected['XDTOPackages/OwnedRecords.xml']=assets['OwnedRecords.xml']
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
