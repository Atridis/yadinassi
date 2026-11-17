"""Source-created empty factories retain identity without loading source packages."""
import gc
import unittest
import weakref
from decimal import Decimal
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_source_xdto_packages as existing
from yadinassi import xdto_io,xdto_values
from yadinassi.values import HostFunction

XS='http://www.w3.org/2001/XMLSchema'

class LocalXDTOTests(unittest.TestCase):
    setUp=basic.SourceScalarXDTOTests.setUp
    app=basic.SourceScalarXDTOTests.app
    def prepared(self):
        app=self.app();app.interpreter.execute('F=New XDTOFactory;T=F.Type("'+XS+'","string");V=F.Create(T,"ok");')
        return app
    def test_original_implicit_shadow(self):
        original=existing.SourceXDTOTests();self.addCleanup(original.doCleanups)
        original.test_local_factory_name_shadows_global()
    def test_new_factory_empty_but_scalar_capable(self):
        app=self.prepared();vm=app.interpreter
        self.assertEqual(vm.execute('V.Value;'),'ok')
        self.assertIsNone(vm.execute('F.Type("urn:owned:records","Code");'))
        self.assertEqual(app.xdto._loaded,set());self.assertIsNone(app.xdto._inventory)
        self.assertIsNot(vm.variables['f'],app.xdto.factory)
    def test_preloaded_global_factory_does_not_pollute_local(self):
        app=self.app();app.xdto.factory.type('urn:owned:records','Code')
        vm=app.interpreter;vm.execute('F=New XDTOFactory;')
        self.assertIsNone(vm.execute('F.Type("urn:owned:records","Code");'))
        self.assertEqual(app.xdto._loaded,{'urn:owned:records'})
    def test_bilingual_constructor_and_values(self):
        app=self.app();vm=app.interpreter
        vm.execute('F=Новый ФабрикаXDTO;T=F.Тип("'+XS+'","boolean");V=F.Создать(T,Истина);')
        self.assertIs(vm.execute('V.Значение;'),True)
    def test_same_app_factories_do_not_share_descriptors(self):
        app=self.prepared();vm=app.interpreter;vm.execute('Other=New XDTOFactory;')
        with self.assertRaises(basic.DENIED):vm.execute('Other.Create(T,"bad");')
        self.assertEqual(vm.execute('V.Value;'),'ok')
    def test_global_and_local_factory_separate(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('GlobalType=XDTOFactory.Type("urn:owned:records","Code");')
        with self.assertRaises(basic.DENIED):vm.execute('F.Create(GlobalType,"bad");')
        with self.assertRaises(basic.DENIED):vm.execute('XDTOFactory.Create(T,"bad");')
        self.assertEqual(vm.execute('F.Create(T,"local").Value;'),'local')
    def test_host_created_and_foreign_app_factory_denied(self):
        first=self.prepared();second=self.app()
        for value in (xdto_io.BSLXDTOFactory(),first.interpreter.variables['f']):
            second.interpreter.variables['foreign']=value
            with self.assertRaises(basic.DENIED):second.interpreter.execute('Foreign.Type("'+XS+'","string");')
    def test_constructor_arity_and_binding_fail_before_argument_effects(self):
        app=self.app();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('called'))
        with self.assertRaises(basic.DENIED):vm.execute('F=New XDTOFactory(Touch());')
        vm.types['xdtofactory']=HostFunction('XDTOFactory',lambda:effects.append('constructor'))
        with self.assertRaises(basic.DENIED):vm.execute('F=New XDTOFactory;')
        self.assertEqual(effects,[])
    def test_factory_counter_not_reset_after_gc(self):
        app=self.app();vm=app.interpreter
        for _ in range(32):vm.execute('F=New XDTOFactory;F=Undefined;')
        gc.collect()
        with self.assertRaises(basic.DENIED):vm.execute('F=New XDTOFactory;')
    def test_node_budget_is_cumulative_across_factories(self):
        app=self.app();vm=app.interpreter
        with patch.object(xdto_io,'MAX_NODES',2),patch.object(xdto_values,'MAX_NODES',2):
            for _ in range(2):vm.execute('F=New XDTOFactory;T=F.Type("'+XS+'","string");V=F.Create(T,"x");F=Undefined;T=Undefined;V=Undefined;')
            gc.collect();vm.execute('F=New XDTOFactory;T=F.Type("'+XS+'","string");')
            with self.assertRaises(basic.DENIED):vm.execute('V=F.Create(T,"x");')
    def test_unit_budget_is_cumulative_and_failed_conversion_does_not_spend(self):
        app=self.app();vm=app.interpreter
        with patch.object(xdto_io,'MAX_UNITS',3),patch.object(xdto_values,'MAX_UNITS',3):
            vm.execute('F=New XDTOFactory;T=F.Type("'+XS+'","integer");')
            with self.assertRaises(basic.DENIED):vm.execute('V=F.Create(T,"bad");')
            vm.execute('V=F.Create(T,123);G=New XDTOFactory;S=G.Type("'+XS+'","string");')
            with self.assertRaises(basic.DENIED):vm.execute('G.Create(S,"x");')
            self.assertEqual(vm.execute('V.Value;'),Decimal(123))
    def test_no_io_packages_or_schema_loader(self):
        app=self.prepared();vm=app.interpreter
        for text in ('F.Packages;','F.WriteXML(Undefined,V);','F.ReadJSON(Undefined,T);'):
            with self.subTest(text=text),self.assertRaises(basic.DENIED):vm.execute(text)
        self.assertFalse(hasattr(vm.variables['f'],'_source_packages_loader'))
    def test_scalar_kind_limit_unchanged(self):
        app=self.prepared();vm=app.interpreter
        with self.assertRaises(basic.DENIED):vm.execute('F.Create(F.Type("'+XS+'","date"),"2020-01-01");')
    def test_factory_retention_is_bounded_by_application_close(self):
        app=self.prepared();vm=app.interpreter
        observed=weakref.ref(vm.variables['f'])
        vm.execute('F=Undefined;T=Undefined;V=Undefined;')
        gc.collect();self.assertIsNotNone(observed())
        app.close();gc.collect();self.assertIsNone(observed())
    def test_closed_application_rejects_retained_factory(self):
        app=self.prepared();vm=app.interpreter;app.close()
        with self.assertRaises(basic.DENIED):vm.execute('F.Type("'+XS+'","string");')
