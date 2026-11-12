"""Two exact owned resources; baseline security and modules remain unchanged."""
from pathlib import Path
import hashlib
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
VALIDATION_MODE='owned-common-template-load-update-observation-v1'
ASSET_HASHES={'OwnedText.xml': 'fb920c988a4405717b013757d8f12d51f264741a93a83e9eb6420e56d971b63e', 'OwnedBinary.xml': '23966752349b7133a78d709df4582dc70b80b14eeb1fbb0c8e834f3d51a2198d', 'OwnedText.txt': '1abc2f4e5f576401bff64a30328d79d9a466c38bbc6ff4e80c702860465f3bdb', 'OwnedBinary.bin': '3d1f57c984978ef98a18378c8166c1cb8ede02c03eeb6aee7e2f121dfeee3e56'}
RESOURCES={
    'CommonTemplates/OwnedText/Ext/Template.txt':'OwnedText.txt',
    'CommonTemplates/OwnedBinary/Ext/Template.bin':'OwnedBinary.bin',
}


def _files(files):
    """Extend baseline admission for exactly two source-pinned resource bytes."""
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
    original._require(not any(path.startswith('CommonTemplates/') for path in files))
    original._require(type(bootstrap_module) is bytes and 0<len(bootstrap_module)<=MAX_FILE)
    original._require(files['Ext/SessionModule.bsl'].decode('utf-8-sig').replace('\r\n','\n')==bootstrap_module.decode('utf-8-sig').replace('\r\n','\n'))
    expected=dict(files);md=original.MD
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:''.join('<'+p+'CommonTemplate>'+name+'</'+p+'CommonTemplate>' for name in ('OwnedText','OwnedBinary')))
    for name in ('OwnedText','OwnedBinary'):
        expected['CommonTemplates/'+name+'.xml']=assets[name+'.xml']
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
