"""Source scalar XDTO retains canonical lazy package admission without VM."""
import unittest
from unittest.mock import patch
import test_source_xdto_packages as existing
from test_configuration_source_runtime import source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_collections import UnsupportedNakedSyntax
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.formats.xml import xdto_io,xdto_values,xml_io

DENIED=(BSLError,BoundaryViolation,ValueError,TypeError,UnsupportedNakedSyntax)

class SourceScalarXDTOTests(unittest.TestCase):
    def setUp(self):
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            p=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name));p.start();self.addCleanup(p.stop)
    def app(self,mapping=None, *, allow_extensions=False):
        mapping=existing.SourceXDTOTests().mapping() if mapping is None else mapping
        app=SourceApplication(source(b'',mapping),output=lambda _:None, allow_extensions=allow_extensions);self.addCleanup(app.close);app.start();return app
    def test_original_scalar_source_cases(self):
        original=existing.SourceXDTOTests();self.addCleanup(original.doCleanups)
        original.test_source_module_global_and_local_shadow()
        original.test_shared_factory_between_client_module_and_application()
    def test_lazy_primitive_bilingual_saved_methods(self):
        app=self.app();vm=app.interpreter
        vm.execute('T=ФабрикаXDTO.Тип("http://www.w3.org/2001/XMLSchema","string");V=ФабрикаXDTO.Создать(T,"primitive");')
        self.assertEqual(app.xdto._loaded,set());self.assertEqual(vm.execute('V.Значение;'),'primitive')
        vm.execute('F=XDTOFactory.Type;T=F("urn:owned:records","Code");C=XDTOFactory.Create;V=C(T,"owned");')
        self.assertEqual(vm.execute('V.Value;'),'owned');self.assertEqual(app.xdto._loaded,{'urn:owned:records'})
    def test_readonly_type_names_base_and_object_shape_reuse_registered_descriptors(self):
        app=self.app();vm=app.interpreter
        vm.execute('T=ФабрикаXDTO.Тип("urn:owned:records","Code"); '
                   'O=XDTOFactory.Type("urn:owned:envelope","Envelope");')
        self.assertEqual(vm.execute('T.Имя + ":" + T.URIПространстваИмен + ":" + T.БазовыйТип.Name;'),
                         'Code:urn:owned:records:string')
        self.assertEqual(vm.execute('O.Name+":"+O.NamespaceURI;'),'Envelope:urn:owned:envelope')
        self.assertTrue(vm.execute('O.Ordered And Not O.Open And Not O.Abstract '
                                   'And Not O.Sequenced And Not O.Mixed;'))
        for code in ('T.Name="renamed";', 'O.Ordered=False;', 'O.Properties;', 'T.Name();'):
            with self.subTest(code=code),self.assertRaises(DENIED):
                vm.execute(code)
        self.assertEqual(vm.execute('T.Name+":"+O.Name;'),'Code:Envelope')

    def test_type_metadata_rejects_foreign_unregistered_and_changed_descriptors(self):
        mapping=existing.SourceXDTOTests().mapping(False)
        app=self.app(mapping);other=self.app(mapping);vm=app.interpreter
        other.interpreter.execute('T=XDTOFactory.Type("urn:owned:records","Record");')
        vm.execute('T=XDTOFactory.Type("urn:owned:records","Record");')
        vm.variables['foreign']=other.interpreter.variables['t']
        vm.variables['fake']=xdto_values.BSLXDTOObjectType(app.xdto.factory,'Record','urn:owned:records')
        for code in ('Foreign.Name;','Fake.Ordered;'):
            with self.subTest(code=code),self.assertRaises(BoundaryViolation):
                vm.execute(code)
        vm.variables['t']._name='Changed'
        with self.assertRaises(BoundaryViolation):vm.execute('T.Name;')

    def test_scalar_read_methods_preserve_registered_identity_and_aliases(self):
        vm=self.app().interpreter
        vm.execute('A=XDTOFactory.Type("urn:owned:records","Code"); '
                   'B=A.BaseType; V=XDTOFactory.Create(A,"я😀"); '
                   'SavedType=V.Тип; SavedDescendant=B.ЭтоПотомок;')
        self.assertTrue(vm.execute('(SavedType()=A) And SavedDescendant(A) And Not A.IsDescendant(B);'))
        self.assertEqual(vm.execute('V.ЛексическоеЗначение;'),'я😀')
        for code in ('V.Factory();','V.LexicalValue="different";','A.Validate("x");'):
            with self.subTest(code=code),self.assertRaises(DENIED):vm.execute(code)

    def test_scalar_read_methods_recheck_receiver_after_arguments_and_reject_foreign(self):
        app=self.app(allow_extensions=True);other=self.app();vm=app.interpreter
        script=('A=XDTOFactory.Type("urn:owned:records","Code"); '
                'V=XDTOFactory.Create(A,"x");')
        vm.execute(script+' Saved=A.IsDescendant;')
        other.interpreter.execute(script)
        vm.variables['foreign']=other.interpreter.variables['a']
        vm.variables['other_value']=other.interpreter.variables['v']
        vm.variables['forged']=object.__new__(xdto_values.BSLXDTODataValue)
        vm.variables['fake_type']=xdto_values.BSLXDTOValueType(app.xdto.factory,'Code','urn:owned:records')
        for code in ('A.IsDescendant(Foreign);','Foreign.IsDescendant(A);',
                     'A.IsDescendant(Fake_Type);','Other_Value.Type();','Forged.LexicalValue;'):
            with self.subTest(code=code),self.assertRaises(BoundaryViolation):vm.execute(code)
        calls=[]
        def touch():
            calls.append('arg')
            vm.variables['a']._name='replaced'
            return vm.variables['a']
        vm.register_function('Touch',touch)
        with patch.object(xdto_values.BSLXDTOValueType,'is_descendant',lambda *args:calls.append('hook')):
            with self.assertRaises(BoundaryViolation):vm.execute('Saved(Touch());')
        with self.assertRaises(DENIED):vm.execute('V.Type(Touch());')
        self.assertEqual(calls,[])
        with self.assertRaises(BoundaryViolation):vm.execute('Saved(Touch());')
        self.assertEqual(calls,['arg'])

    def test_foreign_types_and_closed_saved_context(self):
        a=self.app();b=self.app();foreign=b.xdto.factory.type(xdto_values.XS,'string')
        a.interpreter.variables['foreign']=foreign
        with self.assertRaises(DENIED):a.interpreter.execute('XDTOFactory.Create(Foreign,"x");')
        a.interpreter.execute('F=XDTOFactory.Type;');a.close()
        with self.assertRaises(DENIED):a.interpreter.execute('F("x","y");')
    def test_failed_graph_atomic(self):
        mapping=existing.SourceXDTOTests().mapping();mapping[existing.E]=mapping[existing.E].replace(b'type="r:Code"',b'type="r:Absent"')
        app=self.app(mapping);before=dict(app.xdto.factory._types)
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type("urn:owned:envelope","Envelope");')
        self.assertEqual(app.xdto.factory._types,before);self.assertEqual(app.xdto._loaded,set())
        app.interpreter.execute('T=XDTOFactory.Type("urn:owned:records","Code");V=XDTOFactory.Create(T,"ok");')
        self.assertEqual(app.interpreter.execute('V.Value;'),'ok')
    def test_hooks_and_descriptor_replacement_no_callback(self):
        app=self.app();effects=[]
        for cls,name in ((xdto_io.BSLXDTOFactory,'create'),(xml_io.BSLXMLReader,'read'),(xml_io.BSLXMLReaderSettings,'__init__')):
            with patch.object(cls,name,lambda *args:effects.append('hook')):
                with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type("urn:owned:records","Code");')
        with patch.object(xdto_values.BSLXDTOValueType,'_name',property(lambda _:effects.append('field')),create=True):
            with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
        self.assertEqual(effects,[])
    def test_current_descriptor_and_primitive_seal(self):
        app=self.app();app.interpreter.execute('T=XDTOFactory.Type("urn:owned:records","Code");')
        app.interpreter.variables['t']._base=app.xdto.factory.type(xdto_values.XS,'boolean')
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Create(T,True);')
        app=self.app();key=(xdto_values.XS,'string')
        app.xdto.factory._types[key]=xdto_values.BSLXDTOValueType(app.xdto.factory,'string')
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
    def test_unsupported_surface_and_preloaded_packages(self):
        app=self.app()
        for code in ('XDTOFactory.Packages;','XDTOFactory.Type("urn:owned:envelope","Envelope").Properties; ',
                     'XDTOFactory.WriteXML(Undefined,Undefined);','New XDTOFactory(Undefined);'):
            with self.subTest(code=code),self.assertRaises(DENIED):app.interpreter.execute(code)
        app=self.app();app.xdto.factory.type('urn:owned:records','Code')
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
    def test_arity_before_effects(self):
        app=self.app(allow_extensions=True);effects=[];app.interpreter.register_function('Touch',lambda:effects.append('arg') or '')
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type(Touch());')
        self.assertEqual(effects,[])
