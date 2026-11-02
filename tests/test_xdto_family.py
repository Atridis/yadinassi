"""Ordinary typed workflows and bounded integrity; native semantics separately measured."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from yadinassi.xdto_io import BSLXDTOFactory, create_xdto_factory
from yadinassi.xdto_values import XS, BSLXDTODataObject, BSLXDTODataValue
from yadinassi.xml_io import BSLXMLReader
from yadinassi.xml_writer import BSLXMLWriter
from yadinassi.json_processing import BSLJSONReader, BSLJSONWriter

SCHEMA = '''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:test" targetNamespace="urn:test" elementFormDefault="qualified">
<xs:complexType name="Child"><xs:sequence><xs:element name="code" type="xs:string"/></xs:sequence></xs:complexType>
<xs:complexType name="Box"><xs:sequence>
<xs:element name="title" type="xs:string" minOccurs="0"/>
<xs:element name="qty" type="xs:decimal" minOccurs="0"/>
<xs:element name="child" type="t:Child" minOccurs="0"/>
<xs:element name="items" type="t:Child" minOccurs="0" maxOccurs="3"/>
<xs:element name="tags" type="xs:string" minOccurs="0" maxOccurs="3"/>
<xs:element name="nil" type="xs:string" minOccurs="0" nillable="true"/>
</xs:sequence><xs:attribute name="id" type="xs:string"/></xs:complexType>
<xs:element name="box" type="t:Box"/></xs:schema>'''


def factory(schema=SCHEMA):
    with tempfile.TemporaryDirectory(prefix='xdto-unit-') as root:
        path=Path(root)/'owned.xsd';path.write_text(schema,encoding='utf-8')
        return create_xdto_factory(str(path))


def xml_reader(source):
    reader=BSLXMLReader();reader.set_string(source);return reader


def json_reader(source):
    reader=BSLJSONReader();reader.set_string(source);return reader


class XDTOFamilyTests(unittest.TestCase):
    def setUp(self):
        self.f=factory();self.kind=self.f.type('urn:test','Box');self.obj=self.f.create(self.kind)

    def test_scalar_types_lexical_and_closed_admission(self):
        for name,value,lexical in [('string','Привет😀','Привет😀'),('boolean',True,'true'),('decimal',Decimal('12.50'),'12.5'),('int',-7,'-7')]:
            result=self.f.create(self.f.type(XS,name),value)
            self.assertEqual(result.get_member('LexicalValue'),lexical)
        for name,value in [('int',Decimal('1.5')),('int',2**31),('decimal',Decimal('NaN')),('decimal',Decimal('1e999')),('boolean',1),('string',object())]:
            with self.subTest(name=name), self.assertRaises((ValueError,TypeError)):
                self.f.create(self.f.type(XS,name),value)
        other=BSLXDTOFactory()
        with self.assertRaises(TypeError):self.f.create(other.type(XS,'string'),'x')
        class Derived(BSLXDTODataValue):pass
        with self.assertRaises(TypeError):self.obj.set('title',Derived(self.f.type(XS,'string'),'x'))

    def test_metadata_readonly_foreign_property_and_unknown_xpath(self):
        prop=self.kind._properties.get('title')
        self.assertIs(prop.get_member('OwnerType'),self.kind)
        for value in (prop,self.kind,self.f._packages):
            with self.assertRaises(ValueError):value.set_member('Name','other')
        with self.assertRaises(ValueError):self.obj.set(factory().type('urn:test','Box')._properties.get('title'),'x')
        with self.assertRaises(ValueError):self.obj.get('child/code')
        with self.assertRaises(ValueError):self.obj.set('unknown','x')

    def test_object_scalar_and_unset(self):
        self.assertFalse(self.obj.is_set('title'));self.obj.set('title','')
        self.assertTrue(self.obj.is_set('title'));self.assertEqual(self.obj.get('title'),'')
        self.assertIs(type(self.obj.get_xdto('title')),BSLXDTODataValue)
        self.obj.unset('title');self.assertFalse(self.obj.is_set('title'))
        with self.assertRaises(ValueError):self.obj.set('title',None)
        self.obj.set('nil',None);self.obj.validate()

    def child(self):
        value=self.f.create(self.f.type('urn:test','Child'));value.set('code','a');return value

    def test_single_owner_and_atomic_replacement(self):
        child=self.child();self.obj.set('child',child)
        self.assertIs(child.owner(),self.obj)
        other=self.f.create(self.kind)
        with self.assertRaises(ValueError):other.set('child',child)
        self.assertFalse(other.is_set('child'));self.assertIs(self.obj.get('child'),child)
        with self.assertRaises(TypeError):self.obj.set('child','bad')
        self.assertIs(self.obj.get('child'),child)
        self.obj.unset('child');self.assertIsNone(child.owner());other.set('child',child)

    def test_list_mutations_bounds_and_detach(self):
        values=self.obj.get_list('tags');values.add('b');values.insert(0,'a');values.set(1,'c')
        self.assertEqual(list(values),['a','c']);self.assertEqual(values.delete(0)._value,'a')
        values.add('d');values.add('e')
        with self.assertRaises(ValueError):values.add('f')
        self.assertEqual(list(values),['c','d','e'])
        child=self.child();children=self.obj.get_list('items');children.add(child)
        with self.assertRaises(ValueError):children.add(child)
        self.assertEqual(children.count(),1)
        children.clear();self.assertIsNone(child.owner())
        self.obj.unset('tags');self.assertEqual(values.count(),0)

    def test_required_validation(self):
        child=self.f.create(self.f.type('urn:test','Child'))
        with self.assertRaises(ValueError):child.validate()
        child.set('code','');child.validate()

    def test_allocation_failure_atomicity(self):
        values=self.obj.get_list('tags');before=self.f._nodes,self.f._units
        with mock.patch('yadinassi.xdto_io.MAX_NODES',self.f._nodes+1):
            with self.assertRaises(ValueError):values.add('not committed')
        self.assertEqual(values.count(),0);self.assertEqual((self.f._nodes,self.f._units),before)
        with mock.patch('yadinassi.xdto_io.MAX_UNITS',self.f._units):
            with self.assertRaises(ValueError):self.obj.set('title','not committed')
        self.assertFalse(self.obj.is_set('title'))

    def test_xml_roundtrip_borrowed_reader_and_writer(self):
        self.obj.set('title','A<&😀');self.obj.set('id','q"');self.obj.set('child',self.child())
        self.obj.get_list('tags').add('one');self.obj.set('nil',None)
        writer=BSLXMLWriter();writer.set_string();self.f.write_xml(writer,self.obj)
        source=writer.close();reader=xml_reader(source);result=self.f.read_xml(reader)
        self.assertEqual(result.get('title'),'A<&😀');self.assertEqual(result.get('id'),'q"')
        self.assertEqual(result.get('child').get('code'),'a');self.assertEqual(list(result.get_list('tags')),['one'])
        self.assertTrue(result.is_set('nil'));self.assertIsNotNone(reader._source)

    def test_xml_scalar_whitespace_is_not_schema_layout(self):
        result=self.f.read_xml(xml_reader('<box xmlns="urn:test"> <title>  </title> </box>'))
        self.assertEqual(result.get('title'),'  ')

    def test_xml_failure_preserves_reader_and_factory(self):
        for source in ['<box xmlns="urn:test"><title>x</title><unknown/></box>',
                       '<box xmlns="urn:test"><title>x</title><title>y</title></box>',
                       '<box xmlns="urn:test"><qty>1</qty><title>x</title></box>',
                       '<box xmlns="urn:test" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/>']:
            reader=xml_reader(source);before=reader.__dict__.copy();budget=self.f._nodes,self.f._units
            with self.subTest(source=source),self.assertRaises(ValueError):self.f.read_xml(reader)
            self.assertEqual(reader.__dict__,before);self.assertEqual((self.f._nodes,self.f._units),budget)

    def test_xml_entities_and_unsupported_attributes_rejected(self):
        for source in ['<!DOCTYPE box [<!ENTITY x "x">]><box xmlns="urn:test">&x;</box>',
                       '<box xmlns="urn:test" unknown="x"/>',
                       '<box xmlns="urn:test"><nil xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true" other="x"/></box>']:
            with self.subTest(source=source),self.assertRaises(ValueError):self.f.read_xml(xml_reader(source))

    def test_xml_writer_failure_and_parent_namespace(self):
        writer=BSLXMLWriter();writer.set_string();writer.write_start_element('outer');writer.write_namespace_mapping('','urn:outer')
        value=self.f.create(self.f.type(XS,'string'),'x');self.f.write_xml(writer,value,'plain','')
        writer.write_end_element();source=writer.close()
        self.assertIn('xmlns=""',source)
        writer=BSLXMLWriter();writer.set_string();before=writer.__dict__.copy()
        incomplete=self.f.create(self.f.type('urn:test','Child'))
        with self.assertRaises(ValueError):self.f.write_xml(writer,incomplete,'child','urn:test')
        self.assertEqual(writer.__dict__,before)

    def test_json_roundtrip_nested_lists(self):
        self.obj.set('title','Привет😀');self.obj.set('qty',Decimal('1.25'));self.obj.set('child',self.child())
        self.obj.get_list('tags').add('a');writer=BSLJSONWriter();writer.set_string();self.f.write_json(writer,self.obj)
        reader=json_reader(writer.close());result=self.f.read_json(reader,self.kind)
        self.assertEqual(result.get('title'),'Привет😀');self.assertEqual(result.get('qty'),Decimal('1.25'))
        self.assertEqual(result.get('child').get('code'),'a');self.assertEqual(list(result.get_list('tags')),['a'])
        self.assertIsNotNone(reader._source)

    def test_json_failure_duplicate_unknown_and_callback_atomic(self):
        for source in ['{"title":"a","title":"b"}','{"title":"a","unknown":1}','{"child":{}}','{"tags":["a",null]}']:
            reader=json_reader(source);before=reader.__dict__.copy();budget=self.f._nodes,self.f._units
            with self.subTest(source=source),self.assertRaises((ValueError,TypeError)):self.f.read_json(reader,self.kind)
            self.assertEqual(reader.__dict__,before);self.assertEqual((self.f._nodes,self.f._units),budget)
        with self.assertRaises(ValueError):self.f.read_json(json_reader('{}'),self.kind,object())

    def test_schema_closed_subset(self):
        for content in ['<xs:import namespace="urn:else" schemaLocation="never-read.xsd"/>',
                        '<xs:include schemaLocation="never-read.xsd"/>',
                        '<xs:complexType name="Bad"><xs:choice/></xs:complexType>',
                        '<xs:complexType name="Bad" mixed="true"/>',
                        '<xs:simpleType name="Bad"><xs:restriction base="xs:string"/></xs:simpleType>',
                        '<xs:complexType name="Bad"><xs:sequence><xs:element name="self" type="t:Bad"/></xs:sequence></xs:complexType>']:
            schema=SCHEMA.replace('</xs:schema>',content+'</xs:schema>')
            with self.subTest(content=content),self.assertRaises(ValueError):factory(schema)

    def test_type_depth_independent_of_declaration_order(self):
        parts=['<xs:complexType name="A"><xs:sequence><xs:element name="v" type="xs:string"/></xs:sequence></xs:complexType>']
        for previous,current in zip('ABCD','BCDE'):
            parts.append(f'<xs:complexType name="{current}"><xs:sequence><xs:element name="v" type="t:{previous}"/></xs:sequence></xs:complexType>')
        prefix=SCHEMA.split('>')[0]+'>'
        for declarations in (parts,list(reversed(parts))):
            with self.subTest(order=declarations[0]),mock.patch('yadinassi.xdto_schema.MAX_DEPTH',4):
                with self.assertRaises(ValueError):factory(prefix+''.join(declarations)+'</xs:schema>')

    def test_json_preserves_schema_names_not_bsl_identifiers(self):
        f=factory(SCHEMA.replace('name="title"','name="first-name"'));kind=f.type('urn:test','Box');value=f.create(kind)
        value.set('first-name','x');writer=BSLJSONWriter();writer.set_string();f.write_json(writer,value)
        result=f.read_json(json_reader(writer.close()),kind);self.assertEqual(result.get('first-name'),'x')

    def test_schema_budget_and_file_boundary(self):
        with mock.patch('yadinassi.xdto_schema.MAX_SCHEMA_BYTES',20):
            with self.assertRaises(ValueError):factory()
        with mock.patch('yadinassi.xdto_schema._open_regular') as opened:
            for path in ['https://example.invalid/schema.xsd',r'\\server\share\schema.xsd',r'\\.\pipe\schema']:
                with self.subTest(path=path),self.assertRaises(ValueError):create_xdto_factory(path)
            opened.assert_not_called()
        with self.assertRaises(ValueError):factory('<!DOCTYPE schema [<!ENTITY x "x">]>'+SCHEMA)


if __name__=='__main__':unittest.main()
