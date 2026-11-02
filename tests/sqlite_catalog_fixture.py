"""Authored official-XML-shaped catalog configuration, no native binary evidence."""
from uuid import uuid4

def configuration_files():
    config,category,product=[str(uuid4()) for _ in range(3)]
    prefix='<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" version="2.20">'
    result={'Configuration.xml':(prefix+f'<Configuration uuid="{config}"><Properties><Name>OwnedApplication</Name></Properties><ChildObjects><Catalog>Categories</Catalog><Catalog>Products</Catalog></ChildObjects></Configuration></MetaDataObject>').encode()}
    types=[('Text','<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>32</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'),
        ('Amount','<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>12</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'),
        ('Active','<v8:Type>xs:boolean</v8:Type>'),
        ('Stamp','<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>'),
        ('Category','<v8:Type>cfg:CatalogRef.Categories</v8:Type>')]
    for name,identity in [('Categories',category),('Products',product)]:
        fields='' if name=='Categories' else ''.join(f'<Attribute uuid="{uuid4()}"><Properties><Name>{n}</Name><Type>{t}</Type></Properties></Attribute>' for n,t in types)
        result[f'Catalogs/{name}.xml']=(prefix+f'<Catalog uuid="{identity}"><Properties><Name>{name}</Name><Hierarchical>false</Hierarchical><CodeType>String</CodeType><CodeLength>8</CodeLength><DescriptionLength>64</DescriptionLength><CheckUnique>true</CheckUnique><Autonumbering>false</Autonumbering></Properties><ChildObjects>{fields}</ChildObjects></Catalog></MetaDataObject>').encode()
    result['Catalogs/Products/Ext/ObjectModule.bsl']='// Stored UTF-8 source: товар\n'.encode()
    return result
