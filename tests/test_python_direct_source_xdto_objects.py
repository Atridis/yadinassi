"""Whole flat scalar XDTO objects do not imply graph or serialization grants."""
from decimal import Decimal
import gc
import weakref
import unittest
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_source_xdto_packages as existing
from yadinassi.formats.xml import xdto_io,xdto_values

XS='http://www.w3.org/2001/XMLSchema'
BODY=b'''<package xmlns="http://v8.1c.ru/8.1/xdto" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:t="urn:owned:records" targetNamespace="urn:owned:records">
<valueType name="Code" base="xs:string" variety="Atomic"/>
<objectType name="Flat"><property name="Label" type="t:Code"/><property name="Amount" type="xs:decimal" lowerBound="0"/><property name="Flag" type="xs:boolean" lowerBound="0"/><property name="Optional" type="xs:string" lowerBound="0" nillable="true"/></objectType>
<objectType name="Nested"><property name="Child" type="t:Flat" lowerBound="0"/></objectType>
<objectType name="Many"><property name="Labels" type="xs:string" lowerBound="0" upperBound="-1"/></objectType>
</package>'''

class FlatXDTOTests(unittest.TestCase):
    setUp=basic.SourceScalarXDTOTests.setUp
    def app(self,mapping=None):
        if mapping is None:
            mapping=existing.SourceXDTOTests().mapping(False);mapping[existing.R]=BODY
        return basic.SourceScalarXDTOTests.app(self,mapping)
    def prepared(self):
        app=self.app();app.interpreter.execute('T=XDTOFactory.Type("urn:owned:records","Flat");V=XDTOFactory.Create(T);')
        return app
    def test_native_child_flat_type_without_io(self):
        app=self.app(existing.SourceXDTOTests().mapping(False));vm=app.interpreter
        vm.execute('T=XDTOFactory.Type("urn:owned:records","Child");V=XDTOFactory.Create(T);V.Label="native child";')
        self.assertEqual(vm.execute('V.Label;'),'native child')
    def test_whole_type_and_primitive_property_conversion(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('V.Label="hello";V.Amount="12.50";V.Flag="true";')
        self.assertEqual(vm.execute('V.Label;'),'hello')
        self.assertEqual(vm.execute('V.Amount;'),Decimal('12.50'))
        self.assertIs(vm.execute('V.Flag;'),True)
        self.assertIsNone(vm.execute('V.Optional;'))
        self.assertIs(vm.variables['v']._type,vm.variables['t'])
    def test_nullable_values_without_allocation(self):
        app=self.prepared();vm=app.interpreter;factory=app.xdto.factory
        before=(factory._nodes,factory._units)
        vm.execute('V.Optional=Undefined;V.Optional=Null;')
        self.assertIsNone(vm.execute('V.Optional;'));self.assertEqual((factory._nodes,factory._units),before)
        with self.assertRaises(basic.DENIED):vm.execute('V.Label=Undefined;')
        self.assertEqual((factory._nodes,factory._units),before)
    def test_invalid_conversion_preserves_property_and_accounting(self):
        app=self.prepared();vm=app.interpreter;vm.execute('V.Amount=12;')
        before=(app.xdto.factory._nodes,app.xdto.factory._units);old=vm.variables['v']._values['Amount']
        with self.assertRaises(basic.DENIED):vm.execute('V.Amount="bad";')
        self.assertIs(vm.variables['v']._values['Amount'],old)
        self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_property_quota_failure_preserves_old_value(self):
        app=self.prepared();vm=app.interpreter;vm.execute('V.Label="ok";')
        factory=app.xdto.factory;before=(factory._nodes,factory._units);old=vm.variables['v']._values['Label']
        with patch.object(xdto_io,'MAX_NODES',before[0]),patch.object(xdto_values,'MAX_NODES',before[0]):
            with self.assertRaises(basic.DENIED):vm.execute('V.Label="new";')
            self.assertEqual(vm.execute('V.Label;'),'ok')
        self.assertIs(vm.variables['v']._values['Label'],old);self.assertEqual((factory._nodes,factory._units),before)
    def test_object_creation_reserves_one_node_and_checks_tight_alias(self):
        app=self.app();vm=app.interpreter;vm.execute('T=XDTOFactory.Type("urn:owned:records","Flat");')
        with patch.object(xdto_io,'MAX_NODES',1):
            vm.execute('V=XDTOFactory.Create(T);')
            self.assertEqual(app.xdto.factory._nodes,1)
            with self.assertRaises(basic.DENIED):vm.execute('Other=XDTOFactory.Create(T);')
            self.assertEqual(app.xdto.factory._nodes,1)
    def test_unit_quota_checked_before_assignment(self):
        app=self.prepared();vm=app.interpreter;vm.execute('V.Label="ok";')
        before=(app.xdto.factory._nodes,app.xdto.factory._units)
        with patch.object(xdto_io,'MAX_UNITS',before[1]):
            with self.assertRaises(basic.DENIED):vm.execute('V.Label="new";')
        self.assertEqual(vm.execute('V.Label;'),'ok');self.assertEqual((app.xdto.factory._nodes,app.xdto.factory._units),before)
    def test_nested_and_list_types_are_whole_admitted_graphs(self):
        app=self.app();vm=app.interpreter
        for name in ('Nested','Many'):
            self.assertIsNotNone(vm.execute('XDTOFactory.Type("urn:owned:records","'+name+'");'))
        app=self.app(existing.SourceXDTOTests().mapping(False))
        self.assertIsNotNone(app.interpreter.execute('XDTOFactory.Type("urn:owned:records","Record");'))
    def test_object_factory_is_the_current_readonly_factory(self):
        app=self.prepared();vm=app.interpreter
        for code in ('V.Factory();','V.Фабрика();'):
            self.assertIs(vm.execute(code),app.xdto.factory)
        for code in ('V.Properties();','V.Factory(Undefined);','V.Factory=Undefined;',
                     'XDTOFactory.WriteXML(Undefined,V);','New XMLWriter(Undefined);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_factory_and_scalar_create_arities_preserved(self):
        app=self.prepared();vm=app.interpreter
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.Create(T,"bad");')
        vm.execute('S=XDTOFactory.Type("'+XS+'","string");')
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.Create(S);')
        vm.execute('D=XDTOFactory.Create(S,"scalar");')
        self.assertEqual(vm.execute('D.Value;'),'scalar')
    def test_raw_property_spelling_is_not_normalized(self):
        app=self.prepared();vm=app.interpreter
        with self.assertRaises(basic.DENIED):vm.execute('V.label="wrong case";')
        vm.execute('V.Label="exact";');self.assertEqual(vm.execute('V.Label;'),'exact')
    def test_object_records_release_at_application_close(self):
        app=self.prepared();vm=app.interpreter;observed=weakref.ref(vm.variables['v'])
        vm.execute('V=Undefined;');gc.collect();self.assertIsNotNone(observed())
        app.close();gc.collect();self.assertIsNone(observed())
