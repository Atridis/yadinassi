"""Source scalar XDTO retains canonical lazy package admission without VM."""
import unittest
from unittest.mock import patch
import test_source_xdto_packages as existing
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.errors import BSLError
from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi import xdto_io,xdto_values,xml_io

DENIED=(BSLError,BoundaryViolation,ValueError,TypeError,UnsupportedNakedSyntax)

class SourceScalarXDTOTests(unittest.TestCase):
    def setUp(self):
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            p=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name));p.start();self.addCleanup(p.stop)
    def app(self,mapping=None):
        mapping=existing.SourceXDTOTests().mapping() if mapping is None else mapping
        app=SourceApplication(source(b'',mapping),output=lambda _:None);self.addCleanup(app.close);app.start();return app
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
        for code in ('XDTOFactory.Packages;','XDTOFactory.Type("urn:owned:envelope","Envelope");',
                     'XDTOFactory.WriteXML(Undefined,Undefined);','New XDTOFactory(Undefined);'):
            with self.subTest(code=code),self.assertRaises(DENIED):app.interpreter.execute(code)
        app=self.app();app.xdto.factory.type('urn:owned:records','Code')
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
    def test_arity_before_effects(self):
        app=self.app();effects=[];app.interpreter.register_function('Touch',lambda:effects.append('arg') or '')
        with self.assertRaises(DENIED):app.interpreter.execute('XDTOFactory.Type(Touch());')
        self.assertEqual(effects,[])
