from dataclasses import replace
from decimal import Decimal
import unittest
from configuration_xdto_fixture import files
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration_xml import import_configuration
from yadinassi.xdto_io import BSLXDTOFactory,XS
from yadinassi.xml_writer import BSLXMLWriter
from yadinassi.json_processing import BSLJSONWriter

RESOURCE='XDTOPackages/OwnedRecords/Ext/Package.bin'

class PackageTests(unittest.TestCase):
    def app(self, linked=True):
        app=ConfigurationApplication.from_files(files(linked));self.addCleanup(app.close,force=True);return app
    def reject(self, old, new, *, linked=True):
        source=files(linked);source[RESOURCE]=source[RESOURCE].replace(old,new)
        self.assertNotEqual(source[RESOURCE],files(linked)[RESOURCE])
        with self.assertRaises(ValueError):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_opt_in_and_exact_source(self):
        source=files();inactive=import_configuration(source);self.assertTrue(inactive.activation_issues)
        with self.assertRaises(TypeError):ConfigurationApplication(inactive)
        c=import_configuration(source,module_runtime=MODULE_RUNTIME)
        self.assertFalse(c.activation_issues);self.assertEqual({f.path:f.content for f in c.files},source)
        self.assertEqual(c.xdto_packages[0].namespace,'urn:owned:records')
    def test_unknown_binary_path_rejected(self):
        source=files();source['Other.bin']=b'<x/>'
        with self.assertRaises(ValueError):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_missing_package_resource_rejected(self):
        source=files();del source[RESOURCE]
        with self.assertRaises(ValueError):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_namespace_mismatch_rejected(self):self.reject(b'targetNamespace="urn:owned:records"',b'targetNamespace="urn:other"')
    def test_duplicate_type_rejected(self):self.reject(b'</package>',b'<valueType name="Code" base="xs:string" variety="Atomic"/></package>')
    def test_unknown_type_rejected(self):self.reject(b'type="xs:string"',b'type="xs:Absent"')
    def test_facets_rejected(self):self.reject(b'variety="Atomic"/>',b'variety="Atomic"><length value="1"/></valueType>',linked=True)
    def test_alias_chain_rejected(self):
        self.reject(b'base="xs:string"',b'base="xs:Missing"')
        source=files(True);source[RESOURCE]=source[RESOURCE].replace(b'<package ',b'<package xmlns:r="urn:owned:records" ').replace(b'name="AmountValue" base="xs:decimal"',b'name="AmountValue" base="r:Code"')
        with self.assertRaisesRegex(ValueError,'scalar alias'):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_recursive_object_rejected(self):
        source=files(True);source[RESOURCE]=source[RESOURCE].replace(b'<package ',b'<package xmlns:r="urn:owned:records" ').replace(b'type="xs:string"',b'type="r:Child"')
        with self.assertRaisesRegex(ValueError,'cyclic'):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_external_import_rejected(self):self.reject(b'</package>',b'<import namespace="https://no-resolver.invalid/model"/></package>')
    def test_import_cycle_rejected(self):
        source=files(True);source[RESOURCE]=source[RESOURCE].replace(b'</package>',b'<import namespace="urn:owned:envelope"/></package>')
        with self.assertRaisesRegex(ValueError,'cyclic'):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_undeclared_import_rejected(self):
        source=files(True);p='XDTOPackages/OwnedEnvelope/Ext/Package.bin';source[p]=source[p].replace(b'<import namespace="urn:owned:records"/>',b'')
        with self.assertRaisesRegex(ValueError,'undeclared'):import_configuration(source,module_runtime=MODULE_RUNTIME)
    def test_qualified_default_and_property_namespace(self):
        factory=self.app()._xdto_factory;t=factory.type('urn:owned:envelope','Envelope')
        self.assertEqual(t._properties.get('Child')._uri,'urn:owned:envelope')
    def test_forward_object_reference(self):
        source=files();raw=source[RESOURCE];a=b'<objectType name="Child"><property name="Label" type="xs:string"/></objectType>'
        source[RESOURCE]=raw.replace(a,b'').replace(b'</package>',a+b'</package>')
        app=ConfigurationApplication.from_files(source);self.addCleanup(app.close,force=True)
        self.assertIsNotNone(app._xdto_factory.type('urn:owned:records','Record'))
    def test_independent_app_factory(self):
        a=self.app()._xdto_factory;b=self.app()._xdto_factory
        self.assertIsNot(a,b)
        with self.assertRaises(TypeError):a.create(b.type(XS,'string'),'x')
    def test_common_module_factory_identity(self):
        app=self.app();out=[];app._output=out.append;app.start();app.execute('T=XDTOFactory.Type("urn:owned:envelope","Envelope"); V=OwnedXDTOBridge.MakeRecord(T);Message(OwnedXDTOBridge.FactoryMatches(V));')
        self.assertEqual(out,['Да'])
    def test_alias_assignment_base_retains_alias(self):
        f=self.app()._xdto_factory;o=f.create(f.type('urn:owned:envelope','Envelope'));a=f.create(f.type('urn:owned:records','Code'),'x');o.set('BaseText',a)
        self.assertIs(o.get_xdto('BaseText'),a)
    def test_base_assignment_alias_rewraps(self):
        f=self.app()._xdto_factory;o=f.create(f.type('urn:owned:envelope','Envelope'));a=f.create(f.type(XS,'string'),'x');o.set('Code',a)
        self.assertEqual(o.get_xdto('Code')._type._name,'Code')
    def test_foreign_alias_rejected(self):
        f=self.app()._xdto_factory;g=self.app()._xdto_factory;o=f.create(f.type('urn:owned:envelope','Envelope'))
        with self.assertRaises(TypeError):o.set('Code',g.create(g.type('urn:owned:records','Code'),'x'))
    def test_retained_alias_xml_refuses_before_writer(self):
        f=self.app()._xdto_factory;o=f.create(f.type('urn:owned:envelope','Envelope'));o.set('Code','c');o.set('BaseText',f.create(f.type('urn:owned:records','Code'),'x'))
        w=BSLXMLWriter();w.set_string();before=dict(w.__dict__)
        with self.assertRaisesRegex(ValueError,'retained'):f.write_xml(w,o,'Envelope','urn:owned:envelope')
        self.assertEqual(w.__dict__,before)
    def test_retained_alias_json_refuses_before_writer(self):
        f=self.app()._xdto_factory;o=f.create(f.type('urn:owned:envelope','Envelope'));o.set('Code','c');o.set('BaseText',f.create(f.type('urn:owned:records','Code'),'x'))
        w=BSLJSONWriter();w.set_string();before=dict(w.__dict__)
        with self.assertRaisesRegex(ValueError,'retained'):f.write_json(w,o)
        self.assertEqual(w.__dict__,before)
    def test_metadata_forgery_rejected(self):
        c=import_configuration(files(),module_runtime=MODULE_RUNTIME)
        with self.assertRaises(ValueError):ConfigurationApplication(replace(c,xdto_packages=()))
        for declaration in (b'<XDTOPackage ignored="true">OwnedRecords</XDTOPackage>',b'<XDTOPackage>OwnedRecords<Unknown/></XDTOPackage>'):
            source=files();source['Configuration.xml']=source['Configuration.xml'].replace(b'<XDTOPackage>OwnedRecords</XDTOPackage>',declaration)
            with self.subTest(declaration=declaration),self.assertRaises(ValueError):import_configuration(source,module_runtime=MODULE_RUNTIME)
        for before,after in ((b'<Name>OwnedRecords</Name>',b'<Name>OwnedRecords<Unknown/></Name>'),(b'<Namespace>',b'<Namespace ignored="true">'),(b'</Properties>',b'</Properties><ChildObjects><Unknown/></ChildObjects>'),(b'</Properties>',b'</Properties><Unknown/>')):
            source=files();p='XDTOPackages/OwnedRecords.xml';source[p]=source[p].replace(before,after)
            with self.subTest(after=after):
                try:invalid=import_configuration(source,module_runtime=MODULE_RUNTIME)
                except ValueError:continue  # A structured scalar is refused at admission.
                self.assertTrue(invalid.activation_issues)
                with self.assertRaises(ValueError):ConfigurationApplication(invalid)
    def test_scalar_alias_validation_and_base_relation(self):
        f=self.app()._xdto_factory;a=f.type('urn:owned:records','AmountValue');base=f.type(XS,'decimal')
        self.assertTrue(base.is_descendant(a));self.assertFalse(a.is_descendant(base))
        self.assertEqual(f.create(a,Decimal('12.50'))._lexical,'12.5')
        with self.assertRaises(ValueError):f.create(a,'not-a-number')
    def test_unknown_namespace_and_type(self):
        f=self.app()._xdto_factory;self.assertIsNone(f.type('urn:absent','Code'));self.assertIsNone(f.type('urn:owned:records','Absent'))
