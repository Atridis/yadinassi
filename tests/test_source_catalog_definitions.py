"""Closed catalog activation is per-object, not source-import rejection."""
import unittest
from uuid import uuid5, NAMESPACE_URL
from test_configuration_source_runtime import source
from yadinassi.configuration_source import import_source
from yadinassi.source_catalog_definitions import source_catalog_definitions, catalog_definition_record

MD='http://v8.1c.ru/8.3/MDClasses'
BASE='<Name>Items</Name><CodeType>String</CodeType><CodeLength>9</CodeLength><DescriptionLength>64</DescriptionLength><Hierarchical>false</Hierarchical><Autonumbering>false</Autonumbering><CheckUnique>true</CheckUnique><CodeSeries>WholeCatalog</CodeSeries>'

def config(props=BASE,children='',extra=None):
    raw=('<MetaDataObject xmlns="'+MD+'" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema"><Catalog uuid="00000000-0000-0000-0000-000000000002"><Properties>'+props+'</Properties><ChildObjects>'+children+'</ChildObjects></Catalog></MetaDataObject>').encode()
    files={f.path:f.content for f in source().files};files['Catalogs/Items.xml']=raw
    files.update(extra or {})
    return import_source(files)

def attribute(name='Flag',kind='<v8:Type>xs:boolean</v8:Type>',extras=''):
    return '<Attribute uuid="'+str(uuid5(NAMESPACE_URL,name))+'"><Properties><Name>'+name+'</Name><Type>'+kind+'</Type>'+extras+'</Properties></Attribute>'

class SourceCatalogDefinitionTests(unittest.TestCase):
    def reject(self,**kwargs):
        defs,errors=source_catalog_definitions(config(**kwargs));self.assertNotIn('items',defs);self.assertIn('items',errors)
    def test_scalar_fields(self):
        defs,errors=source_catalog_definitions(config(children=attribute()));self.assertFalse(errors)
        self.assertEqual([f.name for f in defs['items'].fields],['Code','Description','DeletionMark','Flag'])
    def test_canonical_stable(self):
        a,_=source_catalog_definitions(config());b,_=source_catalog_definitions(config())
        self.assertEqual(catalog_definition_record(a['items']),catalog_definition_record(b['items']))
    def test_autonumbering(self):self.reject(props=BASE.replace('<Autonumbering>false','<Autonumbering>true'))
    def test_hierarchy(self):self.reject(props=BASE.replace('<Hierarchical>false','<Hierarchical>true'))
    def test_owners(self):self.reject(props=BASE+'<Owners><Item>x</Item></Owners>')
    def test_sections(self):self.reject(children='<TabularSection/>')
    def test_object_module(self):self.reject(extra={'Catalogs/Items/Ext/ObjectModule.bsl':b'Procedure BeforeWrite() EndProcedure'})
    def test_manager_module_inert(self):
        defs,_=source_catalog_definitions(config(extra={'Catalogs/Items/Ext/ManagerModule.bsl':b'broken?'}));self.assertIn('items',defs)
    def test_history(self):self.reject(props=BASE+'<DataHistory>Use</DataHistory>')
    def test_fillcheck(self):self.reject(children=attribute(extras='<FillChecking>ShowError</FillChecking>'))
    def test_unknown_property(self):self.reject(props=BASE+'<FutureBehavior>true</FutureBehavior>')
    def test_reserved_name(self):self.reject(children=attribute('Код'))
    def test_duplicate_field(self):self.reject(children=attribute()+attribute())
    def test_missing_code_length(self):self.reject(props=BASE.replace('<CodeLength>9</CodeLength>',''))
    def test_structured_qualifier(self):self.reject(props=BASE.replace('<CodeLength>','<CodeLength x="1">'))
    def test_missing_policy(self):self.reject(props=BASE.replace('<Autonumbering>false</Autonumbering>',''))
    def test_non_scalar(self):self.reject(children=attribute(kind='<v8:Type>v8:UUID</v8:Type>'))
    def test_zero_description_unsupported(self):self.reject(props=BASE.replace('<DescriptionLength>64','<DescriptionLength>0'))
