import unittest
from unittest.mock import patch
from configuration_xdto_fixture import files
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.xdto_io import BSLXDTOFactory, XS
from yadinassi.xdto_packages import load_packages
from yadinassi.configuration_xdto import ConfigurationXDTOPackage
from yadinassi.errors import BSLError

R='XDTOPackages/OwnedRecords/Ext/Package.bin'
E='XDTOPackages/OwnedEnvelope/Ext/Package.bin'


class SourceXDTOTests(unittest.TestCase):
    def mapping(self, linked=True):
        return {k:v for k,v in files(linked).items() if k.startswith('XDTOPackages/')}

    def app(self, mapping=None, code=b''):
        app=SourceApplication(source(code, self.mapping() if mapping is None else mapping),output=lambda value:None)
        self.addCleanup(app.close)
        if not code: app.start()
        return app

    def test_lazy_source_factory(self):
        app=self.app(); self.assertEqual(app.xdto._loaded,set())
        self.assertIsNotNone(app.xdto.factory.type(XS,'string'))
        self.assertEqual(app.xdto._loaded,set())
        self.assertIsNotNone(app.xdto.factory.type('urn:owned:records','Code'))
        self.assertEqual(app.xdto._loaded,{'urn:owned:records'})

    def test_import_closure(self):
        app=self.app();f=app.xdto.factory
        t=f.type('urn:owned:envelope','Envelope')
        self.assertIs(t._properties.get('Code')._type,f.type('urn:owned:records','Code'))
        self.assertEqual(len(app.xdto._loaded),2)

    def test_incremental_descriptor_identity(self):
        f=self.app().xdto.factory;t=f.type('urn:owned:records','Code');v=f.create(t,'a')
        f.type('urn:owned:envelope','Envelope')
        self.assertIs(t,f.type('urn:owned:records','Code'));self.assertIs(v._factory,f)
        self.assertIs(f._kind(t),t)

    def test_unknown_type_and_namespace(self):
        f=self.app().xdto.factory
        self.assertIsNone(f.type('urn:missing','Unknown'))
        self.assertIsNone(f.type('urn:owned:records','Unknown'))

    def test_bad_unused_resource_does_not_block_primitives_or_other_namespace(self):
        mapping=self.mapping();mapping[E]=b'<unsupported/>'
        f=self.app(mapping).xdto.factory
        self.assertIsNotNone(f.type(XS,'string'))
        self.assertIsNotNone(f.type('urn:owned:records','Code'))
        with self.assertRaises(ValueError):f.type('urn:owned:envelope','Envelope')

    def test_failed_graph_is_atomic(self):
        mapping=self.mapping();mapping[E]=mapping[E].replace(b'type="r:Code"',b'type="r:Absent"')
        app=self.app(mapping);f=app.xdto.factory;before=dict(f._types)
        with self.assertRaises(ValueError):f.type('urn:owned:envelope','Envelope')
        self.assertEqual(f._types,before);self.assertEqual(app.xdto._loaded,set())
        self.assertIsNotNone(f.type('urn:owned:records','Code'))

    def test_failure_preserves_existing_values(self):
        mapping=self.mapping();mapping[E]=mapping[E].replace(b'type="r:Code"',b'type="r:Absent"')
        f=self.app(mapping).xdto.factory;t=f.type('urn:owned:records','Code');value=f.create(t,'retained')
        with self.assertRaises(ValueError):f.type('urn:owned:envelope','Envelope')
        self.assertIs(f._kind(t),t);self.assertEqual(value._value,'retained')

    def test_packages_loads_all(self):
        app=self.app();packages=app.xdto.factory.get_member('Пакеты')
        self.assertEqual(len(packages._items),3);self.assertEqual(len(app.xdto._loaded),2)

    def test_packages_reports_unused_unsupported_graph(self):
        mapping=self.mapping();mapping[E]=b'<unsupported/>'
        app=self.app(mapping)
        with self.assertRaises(ValueError):app.xdto.factory.get_member('Packages')
        self.assertEqual(app.xdto._loaded,set())

    def test_external_import_no_resolution(self):
        mapping=self.mapping();mapping[R]=mapping[R].replace(b'</package>',b'<import namespace="https://external.invalid/model"/></package>')
        with self.assertRaisesRegex(ValueError,'not declared'):
            self.app(mapping).xdto.factory.type('urn:owned:records','Code')

    def test_cycle_rejected(self):
        mapping=self.mapping();mapping[R]=mapping[R].replace(b'</package>',b'<import namespace="urn:owned:envelope"/></package>')
        with self.assertRaisesRegex(ValueError,'cyclic'):
            self.app(mapping).xdto.factory.type('urn:owned:envelope','Envelope')

    def test_missing_resource(self):
        mapping=self.mapping();del mapping[R]
        with self.assertRaisesRegex(ValueError,'missing package resource'):
            self.app(mapping).xdto.factory.type('urn:owned:records','Code')

    def test_foreign_factory_rejected(self):
        a=self.app().xdto.factory;b=self.app().xdto.factory
        with self.assertRaises(TypeError):a.create(b.type('urn:owned:records','Code'),'x')

    def test_closed_application_cannot_load(self):
        app=self.app();f=app.xdto.factory;app.close()
        with self.assertRaises(ValueError):f.type('urn:owned:records','Code')

    def test_standalone_constructor_remains_empty(self):
        self.assertIsNone(BSLXDTOFactory().type('urn:owned:records','Code'))

    def test_source_module_global_and_local_shadow(self):
        code=b'''Procedure OnStart()
T=XDTOFactory.Type("urn:owned:records","Code");
V=XDTOFactory.Create(T,"yes"); Message(V.Value);
EndProcedure'''
        app=self.app(code=code);out=[];app.output=out.append;app.interpreter.output=out.append
        self.assertTrue(app.start());self.assertEqual(out,['yes'])

    def test_qualified_native_package_xml_and_json(self):
        code=b'''Procedure OnStart()
T=XDTOFactory.Type("urn:owned:records","Record");
V=XDTOFactory.Create(T); V.Title="hello";
W=New XMLWriter; W.SetString(); XDTOFactory.WriteXML(W,V,"Record","urn:owned:records"); S=W.Close();
R=New XMLReader; R.SetString(S); V2=XDTOFactory.ReadXML(R,T); R.Close();
If V2.Title<>"hello" Then Raise "XML mismatch"; EndIf;
J=New JSONWriter; J.SetString(); XDTOFactory.WriteJSON(J,V); S=J.Close();
Q=New JSONReader; Q.SetString(S); V3=XDTOFactory.ReadJSON(Q,T); Q.Close();
If V3.Title<>"hello" Then Raise "JSON mismatch"; EndIf;
EndProcedure'''
        self.assertTrue(self.app(self.mapping(False),code).start())

    def test_cumulative_bytes_budget(self):
        app=self.app();f=app.xdto.factory;f.type('urn:owned:records','Code')
        with patch('yadinassi.source_xdto_packages.MAX_SCHEMA_BYTES',app.xdto._bytes+1):
            with self.assertRaisesRegex(ValueError,'bytes'):f.type('urn:owned:envelope','Envelope')
        self.assertIsNotNone(f.type('urn:owned:records','Code'))

    def test_duplicate_namespace_explicitly_rejected(self):
        mapping=self.mapping();mapping['XDTOPackages/OwnedEnvelope.xml']=mapping['XDTOPackages/OwnedEnvelope.xml'].replace(b'urn:owned:envelope',b'urn:owned:records')
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            self.app(mapping).xdto.factory.type('urn:owned:records','Code')

    def test_shared_factory_between_client_module_and_application(self):
        mapping=self.mapping()
        mapping['CommonModules/Helpers.xml']=b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><CommonModule uuid="00000000-0000-0000-0000-000000000022"><Properties><Name>Helpers</Name><ClientManagedApplication>true</ClientManagedApplication></Properties></CommonModule></MetaDataObject>'
        mapping['CommonModules/Helpers/Ext/Module.bsl']=b'Function Build(T) Export\nReturn XDTOFactory.Create(T,"shared");\nEndFunction'
        code=b'''Procedure OnStart()
T=XDTOFactory.Type("urn:owned:records","Code"); V=Helpers.Build(T);
If V.Value<>"shared" Then Raise "not shared"; EndIf;
EndProcedure'''
        self.assertTrue(self.app(mapping,code).start())

    def test_local_factory_name_shadows_global(self):
        code=b'''Procedure OnStart()
XDTOFactory=New XDTOFactory;
If XDTOFactory.Type("urn:owned:records","Code")<>Undefined Then Raise "unexpected source type"; EndIf;
EndProcedure'''
        self.assertTrue(self.app(code=code).start())

    def test_strict_existing_dependencies_remain_disabled(self):
        app=self.app();f=app.xdto.factory;f.type('urn:owned:records','Code')
        item=next(i for i in app.source.metadata if i.name=='OwnedEnvelope')
        definition=ConfigurationXDTOPackage(item.identity,item.name,'urn:owned:envelope',app.files[E])
        candidate=BSLXDTOFactory();candidate._types=dict(f._types);candidate._packages=f._packages
        with self.assertRaisesRegex(ValueError,'not supplied'):load_packages(candidate,(definition,))

    def test_incremental_graph_depth_matches_whole_graph(self):
        mapping=self.mapping()
        def chain(uri, prefix, last):
            types=''.join('<objectType name="T'+str(i)+'"><property name="Next" type="'+(prefix+':T'+str(i+1) if i<19 else last)+'" lowerBound="0"/></objectType>' for i in range(20))
            imports='<import namespace="urn:owned:records"/>' if prefix=='e' else ''
            return ('<package xmlns="http://v8.1c.ru/8.1/xdto" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:r="urn:owned:records" xmlns:e="urn:owned:envelope" targetNamespace="'+uri+'">'+imports+types+'</package>').encode()
        mapping[R]=chain('urn:owned:records','r','xs:string')
        mapping[E]=chain('urn:owned:envelope','e','r:T0')
        app=self.app(mapping);f=app.xdto.factory;t=f.type('urn:owned:records','T0')
        with self.assertRaisesRegex(ValueError,'deep model'):f.type('urn:owned:envelope','T0')
        self.assertIs(f.type('urn:owned:records','T0'),t)
        self.assertEqual(app.xdto._loaded,{'urn:owned:records'})
