"""Source-owned reference inventory, installed and materially redumped before use.

The native fixture is not the authored runtime grant. Every user field and its
reference target survives projection; Designer-added passive defaults do not
establish semantics. Unknown executable files/fields and module drift fail.
"""
from pathlib import Path
import hashlib
from catalog_object_behavior import fixture as original
from . import route
MAX_FILE=original.MAX_FILE
MAX_TOTAL=original.MAX_TOTAL
_files=original._files
ASSET_HASHES = {'Issue.xml': '5dc13896512f1e4bd13a5330fc25f8f237d106dc6e99156c4ca1b25294bda411', 'IssueModule.bsl': '51d1231843b06360c0a77c73fb40a961d5fb6a67a1bd3f257505c2561e304c31', 'Products.xml': '0933538d8eabc91365067675daa835879f235bf98dae48053d6880c3a5024a75', 'Receipt.xml': '061b30f4310c17f5b2c2d9fd571cacea8528e1afa28ad6f97fce43b199b28601', 'ReceiptModule.bsl': 'ee0baf274a8788c263406d5d7a21628da643e087ae5d73d41554d2beda06dd39', 'States.xml': '2b080e1e003c14407e5d1962224de589c70755f87af711fca2ebc6517f923fb5', 'Stock.xml': '2ab01f7e8a25e15f185a0ba1d928f5ebd53b3fa66ee6c5ce2fd7eef8720c54b4', 'Units.xml': '1eaabc285e570e81cd61220bdf9fd6145fe571e60032e7ddc4d3da62cee5cf09', 'Warehouses.xml': '7203c1da33387bc0c0e4a0dab68fc7b32a2d5d83ae44d1a4dbd150772ee26b3d'} # filled by the offline source preparation, never at runtime
OBJECTS={'Catalogs/Products.xml':('Catalog','Products.xml'),
         'Catalogs/Warehouses.xml':('Catalog','Warehouses.xml'),
         'Documents/Receipt.xml':('Document','Receipt.xml'),
         'Documents/Issue.xml':('Document','Issue.xml'),
         'AccumulationRegisters/Stock.xml':('AccumulationRegister','Stock.xml'),
         'Enums/Units.xml':('Enum','Units.xml'), 'Enums/States.xml':('Enum','States.xml')}
MODULES={'Documents/Receipt/Ext/ObjectModule.bsl':'ReceiptModule.bsl',
         'Documents/Issue/Ext/ObjectModule.bsl':'IssueModule.bsl'}
VALIDATION_MODE='owned-inventory-enum-relational-material-projection-v1'

def load_saved():
    assets={};root=Path(__file__).parent
    for name,digest in ASSET_HASHES.items():
        path=root/name
        if path.is_symlink():raise ValueError('fixture symlink')
        raw=path.read_bytes()
        if not 0<len(raw)<=MAX_FILE or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('fixture changed')
        assets[name]=raw
    return original.load_saved()[0],{**assets,'generated/observe.bsl':route.source()}

def prepare(files):
    setup,assets=load_saved();original._baseline(files,setup);expected=dict(files)
    def declarations(p):
        return ''.join('<'+p+kind+'>'+name+'</'+p+kind+'>' for kind,name in
            [('Catalog','Products'),('Catalog','Warehouses'),('Document','Receipt'),('Document','Issue'),('AccumulationRegister','Stock'),('Enum','Units'),('Enum','States')])
    expected['Configuration.xml']=original._append(files['Configuration.xml'],
        (original.MD+'}MetaDataObject',original.MD+'}Configuration',original.MD+'}ChildObjects'),declarations)
    def grants(p):
        result=''
        for name,allowed in [('Catalog.Products',('Read','Insert','Update')),('Catalog.Warehouses',('Read','Insert','Update')),
                ('Document.Receipt',('Read','Insert','Update','Posting','UndoPosting')),('Document.Issue',('Read','Insert','Update','Posting','UndoPosting')),
                ('AccumulationRegister.Stock',('Read','Update'))]:
            result+='<'+p+'object><'+p+'name>'+name+'</'+p+'name>'+''.join('<'+p+'right><'+p+'name>'+r+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>' for r in allowed)+'</'+p+'object>'
        return result
    expected[original.ROLE_FILES[1]]=original._append(files[original.ROLE_FILES[1]],(original.RIGHTS+'}Rights',),grants)
    for path,(_,asset) in OBJECTS.items():expected[path]=assets[asset]
    for path,asset in MODULES.items():expected[path]=assets[asset]
    _files(expected);return setup,expected

def _owned_projection(raw,kind):
    if kind == "Enum": return _enum_projection(raw)
    root=original._signature(raw);md='{'+original.MD+'}'
    def one(node,name):
        items=[v for v in node[3] if v[0]==md+name]
        original._require(len(items)==1);return items[0]
    original._require(root[0]==md+'MetaDataObject' and len(root[3])==1)
    obj=one(root,kind);props=one(obj,'Properties')
    original._require(set(c[0] for c in obj[3])=={md+'InternalInfo',md+'Properties',md+'ChildObjects'})
    required={'Catalog':('Name','Hierarchical','CodeType','CodeLength','DescriptionLength','CodeAllowedLength','CodeSeries','CheckUnique','Autonumbering','DataLockControlMode'),
        'Document':('Name','NumberType','NumberLength','NumberAllowedLength','NumberPeriodicity','CheckUnique','Autonumbering','Posting','RealTimePosting','RegisterRecordsDeletion','RegisterRecordsWritingOnPost','RegisterRecords','PostInPrivilegedMode','UnpostInPrivilegedMode','DataLockControlMode'),
        'AccumulationRegister':('Name','RegisterType','DataLockControlMode','EnableTotalsSplitting')}[kind]
    def fields(children,section=False):
        out=[]
        for f in children[3]:
            k=f[0].removeprefix(md)
            allowed={'Dimension','Resource','Attribute'} if kind=='AccumulationRegister' else {'Attribute'} if section or kind=='Catalog' else {'Attribute','TabularSection'}
            original._require(k in allowed)
            fp=one(f,'Properties')
            if k=='TabularSection':
                original._require(set(v[0] for v in f[3])=={md+'InternalInfo',md+'Properties',md+'ChildObjects'})
                out.append((f[0],f[1],one(fp,'Name'),fields(one(f,'ChildObjects'),True)))
            else:
                original._require(len(f[3])==1)
                out.append((f[0],f[1],one(fp,'Name'),one(fp,'Type'),one(fp,'UseInTotals') if k=='Dimension' else None))
        original._require(len(out)==len(set((v[0],v[1]) for v in out)))
        return tuple(sorted(out))
    return obj[0],obj[1],tuple(one(props,k) for k in required),fields(one(obj,'ChildObjects'))

def _enum_projection(raw):
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
        if path in OBJECTS:
            kind=OBJECTS[path][0]
            original._require(_owned_projection(expected[path],kind)==_owned_projection(actual[path],kind))
        else:original.verify_redump({path:expected[path]},{path:actual[path]})
    return True

def redump_diagnostic(expected,actual):
    # Paths are owned, finite; arbitrary native values/metadata are not exposed.
    result=[]
    for path in sorted(set(expected)|set(actual)):
        if path=='ConfigDumpInfo.xml':continue
        label=path if path in OBJECTS or path in MODULES or path=='Configuration.xml' else 'unowned-file'
        if path not in expected or path not in actual:result.append(label+': inventory differs');continue
        try:
            if path in OBJECTS:
                kind=OBJECTS[path][0];different=_owned_projection(expected[path],kind)!=_owned_projection(actual[path],kind)
            else:
                original.verify_redump({path:expected[path]},{path:actual[path]});different=False
        except (ValueError,UnicodeError):different=True
        if different:result.append(label+': material source differs')
    return result[:12]

def valid_diagnostic(value):
    return type(value) is list and len(value)<=12 and all(type(v) is str and len(v)<=120 and all(32<=ord(c)<=126 for c in v) for v in value)
