"""Offline authored derivative, never staged as an arbitrary XML importer.

Preserve native wrappers from the checked-in accumulation and catalog fixtures;
use the repository demo's complete section/attribute wrappers as candidate input.
Only an actual Designer install plus material redump can admit these candidates.
The Stock declaration retains the accumulation source's MPL-2.0 attribution.
"""
from pathlib import Path
import re
from uuid import UUID, uuid5
ROOT=Path(__file__).resolve().parents[2]
NAMESPACE=UUID('d6e493c6-8f80-5a6a-a703-3cf6688c8bf3')

def identity(name):return str(uuid5(NAMESPACE,name))
def remap(text,owner):
    return re.sub(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',lambda m:identity(owner+':'+m[0]),text)
def field(name,target,owner,template):
    text=re.sub(r'<Name>.*?</Name>','<Name>'+name+'</Name>',template,count=1,flags=re.S)
    text=re.sub(r'<Synonym>.*?</Synonym>','<Synonym/>',text,flags=re.S)
    text=re.sub(r'<Type>.*?</Type>','<Type><v8:Type>cfg:CatalogRef.'+target+'</v8:Type></Type>',text,count=1,flags=re.S)
    return remap(text,owner+':'+name)
def derive():
    files={}
    catalog=(ROOT/'scripts/catalog_object_behavior/generated/Catalog.xml').read_text(encoding='utf-8-sig')
    for name in ('Products','Warehouses'):
        files[name+'.xml']=remap(catalog.replace('OwnedCatalog4f4ccaa9',name),name).encode()
    demo=(ROOT/'tests/fixtures/demo_cf/source/Catalogs/Номенклатура.xml').read_text(encoding='utf-8-sig')
    section=re.search(r'<TabularSection .*?</TabularSection>',demo,re.S)[0]
    template=re.search(r'<Attribute .*?</Attribute>',section,re.S)[0]
    doc=(ROOT/'scripts/accumulation_register_behavior/Document.xml').read_text()
    for name in ('Receipt','Issue'):
        line=field('Product','Products',name+':Lines',template)
        for numeric,scale in (('Quantity',3),('Amount',2)):
            part=field(numeric,'Products',name+':Lines',template)
            part=re.sub(r'<Type>.*?</Type>','<Type><v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>10</v8:Digits><v8:FractionDigits>'+str(scale)+'</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers></Type>',part,count=1,flags=re.S)
            line+=part
        # Section generation is explicit and owned; no runtime broadening.
        sec=section.replace('CatalogTabularSection','DocumentTabularSection').replace('Номенклатура.Склады',name+'.Lines')
        sec=re.sub(r'<Name>.*?</Name>','<Name>Lines</Name>',sec,count=1,flags=re.S)
        sec=re.sub(r'<Synonym>.*?</Synonym>','<Synonym/>',sec,flags=re.S)
        sec=re.sub(r'\s*<Use>ForItem</Use>','',sec)
        sec=re.sub(r'<ChildObjects>.*?</ChildObjects>','<ChildObjects>'+line+'</ChildObjects>',sec,flags=re.S)
        sec=remap(sec,name+':Lines')
        attrs=field('Warehouse','Warehouses',name,template)+sec
        text=doc.replace('OwnedAccumulationDoc',name).replace('OwnedAccumulationRows','Stock')
        text=text.replace('<MetaDataObject ', '<MetaDataObject xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" ',1)
        text=text.replace('<ChildObjects></ChildObjects>','<ChildObjects>'+attrs+'</ChildObjects>')
        files[name+'.xml']=remap(text,name).encode()
    register=(ROOT/'scripts/accumulation_register_behavior/AccumulationRegister.xml').read_text(encoding='utf-8-sig')
    register=register.replace('OwnedAccumulationRows','Stock').replace('See public_source/vanessa_add/', 'See ../accumulation_register_behavior/public_source/vanessa_add/')
    if 'xmlns:cfg=' not in register:
        register=register.replace('<MetaDataObject ','<MetaDataObject xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" ',1)
    for old,name,target in [('Item','Product','Products'),('Warehouse','Warehouse','Warehouses')]:
        pattern=r'<Dimension [^>]*>.*?</Dimension>'
        matches=[m for m in re.finditer(pattern,register,re.S) if '<Name>'+old+'</Name>' in m[0]]
        if len(matches)!=1:raise ValueError('dimension')
        m=matches[0];block=m[0].replace('<Name>'+old+'</Name>','<Name>'+name+'</Name>')
        block=re.sub(r'<Type>.*?</Type>','<Type><v8:Type>cfg:CatalogRef.'+target+'</v8:Type></Type>',block,count=1,flags=re.S)
        register=register[:m.start()]+block+register[m.end():]
    files['Stock.xml']=remap(register,'Stock').encode()
    return files
if __name__=='__main__':
    for name,raw in derive().items():Path(__file__).with_name(name).write_bytes(raw)
