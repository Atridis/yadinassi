import unittest
from decimal import Decimal
from yadinassi.xml_type_bridge import BSLXMLDataType, xml_type, xml_type_of, from_xml_type, XS, DATA
from yadinassi.values import BSLType
from yadinassi.type_values import type_of, type_by_name
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.dates import BSLDate
from yadinassi.runtime import Interpreter


class XMLTypeBridgeTests(unittest.TestCase):
    def test_primitive_forward(self):
        for kind,name in ((BSLType.STRING,'string'),(BSLType.BOOLEAN,'boolean'),(BSLType.NUMBER,'decimal'),(BSLType.DATE,'dateTime')):
            with self.subTest(kind=kind):self.assertEqual(xml_type(kind),BSLXMLDataType(name,XS))

    def test_uuid_uses_legacy_not_xdto_core_namespace(self):
        self.assertEqual(xml_type(BSLType.UUID),BSLXMLDataType('UUID',DATA))
        self.assertIsNone(from_xml_type('UUID','http://v8.1c.ru/8.1/data/core'))

    def test_reverse_descriptor(self):
        for kind in (BSLType.STRING,BSLType.BOOLEAN,BSLType.NUMBER,BSLType.DATE,BSLType.UUID):
            self.assertIs(from_xml_type(xml_type(kind)),kind)

    def test_reverse_pair(self):
        self.assertIs(from_xml_type('decimal',XS),BSLType.NUMBER)

    def test_case_and_namespace_are_exact(self):
        for name,uri in (('String',XS),('string',XS+'/'),('string',''),('string','urn:unrelated')):
            self.assertIsNone(from_xml_type(name,uri))

    def test_unknown_type_is_undefined(self):
        self.assertIsNone(from_xml_type('Unsupported','urn:external.invalid'))

    def test_boolean_not_number(self):
        self.assertEqual(xml_type_of(True).type_name,'boolean')
        self.assertEqual(xml_type_of(Decimal(1)).type_name,'decimal')

    def test_string_value_not_type_name(self):
        self.assertEqual(xml_type_of('Number').type_name,'string')
        with self.assertRaises(TypeError):xml_type('Number')

    def test_read_only_properties_and_aliases(self):
        value=xml_type(BSLType.STRING)
        self.assertEqual(value.get_member('ИмяТипа'),'string')
        self.assertEqual(value.get_member('NamespaceURI'),XS)
        with self.assertRaises(Exception):value.type_name='wrong'
        with self.assertRaises(Exception):value.set_member('TypeName','wrong')

    def test_type_identity(self):
        self.assertIs(type_of(xml_type(BSLType.STRING)),BSLType.XML_DATA_TYPE)
        self.assertIs(type_by_name('XMLDataType'),BSLType.XML_DATA_TYPE)
        self.assertIs(type_by_name('ТипДанныхXML'),BSLType.XML_DATA_TYPE)

    def test_no_implicit_constructor_conversions(self):
        for name,uri in ((1,XS),('string',None),(False,True)):
            with self.assertRaises(TypeError):BSLXMLDataType(name,uri)

    def test_constructor_bounds(self):
        with self.assertRaises(ValueError):BSLXMLDataType('x'*1025,XS)
        with self.assertRaises(ValueError):BSLXMLDataType('string','x'*4097)

    def test_wrong_reverse_arity_and_types(self):
        for args in ((xml_type(BSLType.STRING),XS),('string',),(None,),('string',None)):
            with self.assertRaises(TypeError):from_xml_type(*args)

    def test_unsupported_platform_type_not_silent(self):
        with self.assertRaisesRegex(ValueError,'не поддержано'):xml_type(BSLType.ARRAY)

    def test_host_object_hooks_not_called(self):
        class Host:
            def __str__(self):raise AssertionError('host hook')
            def __hash__(self):raise AssertionError('host hook')
        with self.assertRaises(TypeError):xml_type(Host())
        with self.assertRaises(TypeError):from_xml_type(Host())
        with self.assertRaises(TypeError):xml_type_of(Host())

    def test_interpreter_russian_english_and_roundtrip(self):
        out=[];interpreter=Interpreter(output=out.append);self.addCleanup(interpreter.close)
        interpreter.execute('T=XMLType(Type("Number")); Message(T.TypeName); Message(T.NamespaceURI); K=ИзXMLТипа(T); Message(XMLValue(K, XMLString(12))); Message(ТипЗнч(T)=Тип("ТипДанныхXML"));')
        self.assertEqual(out,['decimal',XS,'12','Да'])

    def test_constructor_and_dynamic_new(self):
        out=[];interpreter=Interpreter(output=out.append);self.addCleanup(interpreter.close)
        interpreter.execute('A=New Array; A.Add("string"); A.Add("http://www.w3.org/2001/XMLSchema"); T=New(Type("XMLDataType"),A); Message(FromXMLType(T)=Type("String"));')
        self.assertEqual(out,['Да'])

    def test_existing_non_scalar_descriptors(self):
        for kind,name,uri in ((BSLType.BINARY_DATA,'base64Binary',XS),(BSLType.NULL,'Null',DATA),
                              (BSLType.VALUE_STORAGE,'ValueStorage',DATA),(BSLType.TYPE,'Type',DATA),
                              (BSLType.TYPE_DESCRIPTION,'TypeDescription',DATA)):
            with self.subTest(kind=kind):
                self.assertEqual(xml_type(kind),BSLXMLDataType(name,uri))
                self.assertIs(from_xml_type(name,uri),kind)

    def test_actual_metadata_descriptors(self):
        from uuid import UUID
        from yadinassi.catalog_types import BSLCatalogType
        from yadinassi.document_types import BSLDocumentType
        from yadinassi.enum_types import BSLEnumType
        for cls,prefix,families in ((BSLCatalogType,'Catalog',('ref','object')),(BSLDocumentType,'Document',('ref','object')),(BSLEnumType,'Enum',('ref',))):
            for family in families:
                kind=cls(UUID(int=1),'Items',object(),family)
                descriptor=xml_type(kind)
                self.assertEqual(descriptor,BSLXMLDataType(prefix+family.title()+'.Items',''))
                self.assertIs(from_xml_type(descriptor,resolver=lambda name:kind),kind)

    def test_metadata_manager_not_synthesized(self):
        from uuid import UUID
        from yadinassi.catalog_types import BSLCatalogType
        with self.assertRaises(ValueError):xml_type(BSLCatalogType(UUID(int=1),'Items',object(),'manager'))

    def test_metadata_reverse_needs_context_and_exact_name(self):
        from uuid import UUID
        from yadinassi.catalog_types import BSLCatalogType
        kind=BSLCatalogType(UUID(int=1),'Items',object())
        with self.assertRaisesRegex(ValueError,'контекст'):from_xml_type('CatalogRef.Items','')
        self.assertIsNone(from_xml_type('CatalogRef.items','',resolver=lambda name:kind))

    def test_reverse_helper_rebound_for_child_activation(self):
        from types import MethodType
        parent=Interpreter();child=Interpreter(family_owner=parent)
        self.addCleanup(parent.close);self.addCleanup(child.close)
        child._inherit_host_bindings(parent)
        callback=child.functions['fromxmltype'].function
        self.assertIs(type(callback),MethodType)
        self.assertIs(callback.__self__,child)

    def test_source_enum_roundtrip_uses_actual_snapshot(self):
        from test_source_enumeration_runtime import package
        from yadinassi.configuration_source_runtime import SourceApplication
        out=[];app=SourceApplication(package('T=XMLTypeOf(Enums.Status.Active); Message(T.TypeName); Message(T.NamespaceURI); Message(FromXMLType(T)=Type("EnumRef.Status"));'),output=out.append)
        self.addCleanup(app.close);app.start()
        self.assertEqual(out,['EnumRef.Status','','Да'])

    def test_missing_metadata_is_undefined_without_fabrication(self):
        import tempfile
        from pathlib import Path
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi.configuration_xml import import_configuration
        from test_document_configuration_xml import document_files
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        context=SQLiteDBContext.create(Path(temp.name)/'test.sqlite',import_configuration(document_files()))
        self.addCleanup(context.close)
        interpreter=Interpreter(database_context=context);self.addCleanup(interpreter.close)
        for name in ('CatalogRef.Absent','DocumentRef.Absent','EnumRef.Absent','CatalogRef.'):
            self.assertIsNone(interpreter.execute('FromXMLType("'+name+'","")'))
        self.assertIsNone(from_xml_type('CatalogRef.Absent','',resolver=lambda name:None))
        for name in ('CatalogRef.Categories','CatalogObject.Categories','DocumentRef.Orders','DocumentObject.Orders'):
            self.assertTrue(interpreter.execute('(FromXMLType(XMLType(Type("'+name+'")))=Type("'+name+'"))'))

    def test_closed_interpreter_reverse_does_not_hide_lifetime_error(self):
        interpreter=Interpreter();interpreter.close()
        with self.assertRaises(Exception):interpreter._from_xml_type('CatalogRef.Absent','')
