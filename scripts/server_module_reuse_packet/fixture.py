"""Add exactly four owned server common modules to the verified disposable baseline."""
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL

def prepare(files, bootstrap_module):
    setup=original.load_saved()[0]
    original._baseline(files,setup)
    original._require(not any(p.startswith('CommonModules/') for p in files))
    original._require(route.normalized(files['Ext/SessionModule.bsl'])==route.normalized(bootstrap_module))
    expected=dict(files);md=original.MD
    expected['Configuration.xml']=original._append(files['Configuration.xml'],(md+'}MetaDataObject',md+'}Configuration',md+'}ChildObjects'),lambda p:'<'+p+'CommonModule>ServerSession</'+p+'CommonModule><'+p+'CommonModule>ServerRequest</'+p+'CommonModule><'+p+'CommonModule>CachedServerCall</'+p+'CommonModule><'+p+'CommonModule>ServerInspector</'+p+'CommonModule>')
    expected.update({p:raw for p,raw in route.sources().items() if p.startswith('CommonModules/')})
    original._files(expected)
    used=set()
    for path,raw in expected.items():
        if path.endswith('.xml'):
            root,_=original._xml(raw)
            for node in root.iter():
                if 'uuid' in node.attrib:
                    value=original._uuid(node.attrib['uuid'])
                    original._require(value not in used);used.add(value)
    return expected
