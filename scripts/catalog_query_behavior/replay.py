"""Source-bound logical reference execution, NOT Designer XML import parity.

The native packet's full Designer properties are not yet activated by the
production importer. This deliberately separate authored minimal configuration
models the same catalog identity, Code8/Description64 and exact three typed fields. It never
normalizes or strips properties from a user/native configuration.
Hierarchy/owners, unique code and length policy, validation, hooks, data history
and the exact three-field schema are checked explicitly. Other presentation
and UI-choice defaults are outside these non-UI observations; their exact source
bytes are nevertheless pinned and the host requires full semantic redump equality.
"""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID,uuid5
from .fixture import load_saved, _xml, _signature
from . import packet

COMPARISON_SCOPE='owned-catalog-query-logical-reference-model'
METADATA_IMPORT_PARITY_CLAIMED=False



def require_behavior_profile(setup, raw):
    """Prove the finite properties used by these operations, not general import."""
    md='{http://v8.1c.ru/8.3/MDClasses}'
    xr='{http://v8.1c.ru/8.3/xcf/readable}'
    root,_=_xml(raw)
    def require(ok):
        if not ok:raise ValueError('CatalogQuery logical behavior profile mismatch')
    require(_signature(raw)==_signature(packet.render_xml(setup)))
    require(root.tag==md+'MetaDataObject' and len(root)==1)
    catalog=root[0];require(catalog.tag==md+'Catalog' and catalog.get('uuid')==setup.metadata_uuid)
    require([n.tag for n in catalog]==[md+'InternalInfo',md+'Properties',md+'ChildObjects'])
    props=catalog[1];children=catalog[2]
    require(len(children)==3 and not children.attrib and not (children.text or '').strip())
    for node,identity,name in zip(children,setup.field_ids,('Quantity','Active','Stamp')):
        require(node.tag==md+'Attribute' and node.attrib=={'uuid':identity} and len(node)==1)
        p=node[0];require(p.tag==md+'Properties')
        require(p.find(md+'Name').text==name)
        for key,value in (('FillChecking','DontCheck'),('FillFromFillingValue','false'),('Use','ForItem')):
            item=p.find(md+key);require(item is not None and not item.attrib and not len(item) and item.text==value)
    values={}
    for node in props:
        require(node.tag not in values);values[node.tag]=node
    expected={'Name':setup.name,'Hierarchical':'false','CodeType':'String','CodeLength':'8',
              'DescriptionLength':'64','CodeAllowedLength':'Variable','CodeSeries':'WholeCatalog',
              'CheckUnique':'true','Autonumbering':'false','DataLockControlMode':'Managed',
              'DataHistory':'DontUse','UpdateDataHistoryImmediatelyAfterWrite':'false',
              'ExecuteAfterWriteDataHistoryVersionProcessing':'false','PredefinedDataUpdate':'Auto'}
    for key,value in expected.items():
        node=values.get(md+key)
        require(node is not None and not node.attrib and not len(node) and node.text==value)
    owners=values.get(md+'Owners');require(owners is not None and not owners.attrib and not len(owners) and not (owners.text or '').strip())
    standard=values.get(md+'StandardAttributes');require(standard is not None)
    for name in ('Code','Description'):
        matches=[n for n in standard if n.tag==xr+'StandardAttribute' and n.get('name')==name]
        require(len(matches)==1)
        for field,value in (('FillChecking','DontCheck'),('FillFromFillingValue','false')):
            matches2=[n for n in matches[0] if n.tag==xr+field]
            require(len(matches2)==1 and not matches2[0].attrib and not len(matches2[0]) and matches2[0].text==value)
    # No object/manager module, predefined data or tabular parts are
    # installed: fixture.prepare adds ONLY this XML file and verifies inventory.
    forbidden={'ObjectModule','ManagerModule','PredefinedData','TabularSection'}
    require(not any(n.tag.rsplit('}',1)[-1] in forbidden for n in catalog.iter()))
    return True


def logical_model_files(setup):
    if type(setup) is not packet.Setup:raise ValueError('invalid logical model setup')
    setup.validate()
    require_behavior_profile(setup,packet.render_xml(setup))
    config_id=uuid5(UUID(setup.metadata_uuid),'owned-catalog-query-logical-reference-model')
    if str(config_id) in (setup.metadata_uuid,*setup.generated_ids,*setup.field_ids,*setup.record_ids):
        raise ValueError('logical configuration identity collision')
    md='http://v8.1c.ru/8.3/MDClasses'
    config=f'<MetaDataObject xmlns="{md}" version="2.20"><Configuration uuid="{config_id}"><Properties><Name>OwnedLogicalReferenceModel</Name></Properties><ChildObjects><Catalog>{setup.name}</Catalog></ChildObjects></Configuration></MetaDataObject>'
    types = (
        '<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>12</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>',
        '<v8:Type>xs:boolean</v8:Type>',
        '<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>')
    fields=''.join(f'<Attribute uuid="{identity}"><Properties><Name>{name}</Name><Type>{kind}</Type></Properties></Attribute>'
                   for identity,name,kind in zip(setup.field_ids,('Quantity','Active','Stamp'),types))
    catalog=f'<MetaDataObject xmlns="{md}" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema" version="2.20"><Catalog uuid="{setup.metadata_uuid}"><Properties><Name>{setup.name}</Name><Hierarchical>false</Hierarchical><CodeType>String</CodeType><CodeLength>8</CodeLength><DescriptionLength>64</DescriptionLength><CodeSeries>WholeCatalog</CodeSeries><CheckUnique>true</CheckUnique><Autonumbering>false</Autonumbering></Properties><ChildObjects>{fields}</ChildObjects></Catalog></MetaDataObject>'
    return {'Configuration.xml':config.encode('utf-8'),'Catalogs/'+setup.name+'.xml':catalog.encode('utf-8')}


def replay():
    from yadinassi import Interpreter
    from yadinassi.configuration_xml import import_configuration
    from yadinassi.database_context import SQLiteDBContext
    setup,assets=load_saved();rows=[]
    require_behavior_profile(setup,assets['generated/Catalog.xml'])
    def emit(number,value):
        if type(number) is not Decimal or number!=len(rows)+1 or len(rows)>=24:
            raise ValueError('invalid logical observation order')
        rows.append(value)
    with TemporaryDirectory(prefix='catalog-logical-reference-') as directory:
        context=SQLiteDBContext.create(Path(directory)/'application.sqlite',import_configuration(logical_model_files(setup)))
        try:
            runtime=Interpreter(database_context=context)
            runtime.register_function('CQEmit',emit)
            runtime.execute(assets['generated/observe.bsl'].decode('utf-8'))
            packet.validate_observations(rows)
        finally:context.close()
    # JSON wire Number representation, not a change to BSL Number semantics.
    rows[18]=int(rows[18])
    return rows
