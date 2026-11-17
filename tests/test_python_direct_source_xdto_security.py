"""XDTO source grants reject forged state before host callbacks."""
import gc
import unittest
import weakref
from decimal import Decimal
from types import MethodType
from unittest.mock import patch
import test_python_direct_source_xdto as basic
from yadinassi import xdto_io,xdto_values,source_xdto_packages
from yadinassi.values import HostFunction


class SourceScalarXDTOSecurity(unittest.TestCase):
    setUp=basic.SourceScalarXDTOTests.setUp
    app=basic.SourceScalarXDTOTests.app

    def prepared(self):
        app=self.app();app.interpreter.execute('T=XDTOFactory.Type("urn:owned:records","Code");V=XDTOFactory.Create(T,"ok");')
        return app

    def test_registry_root_replacement_denied(self):
        for field in ('_types','_roots','_packages'):
            with self.subTest(field=field):
                app=self.prepared();factory=app.xdto.factory
                if field=='_packages':replacement=xdto_values.BSLXDTOPackageCollection(factory._packages._items)
                else:replacement=dict(getattr(factory,field))
                setattr(factory,field,replacement)
                with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,"no");')

    def test_counter_rollback_and_value_tamper_denied(self):
        for field in ('_nodes','_units'):
            app=self.prepared();setattr(app.xdto.factory,field,0)
            with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,"no");')
        for field,value in (('_value','forged'),('_lexical','forged')):
            app=self.prepared();setattr(app.interpreter.variables['v'],field,value)
            with self.assertRaises(basic.DENIED):app.interpreter.execute('V.Value;')
        app=self.prepared();kind=app.interpreter.variables['t']
        forged=object.__new__(xdto_values.BSLXDTODataValue)
        forged._factory=app.xdto.factory;forged._type=kind;forged._value='forged';forged._lexical='forged'
        app.interpreter.variables['v']=forged
        with self.assertRaises(basic.DENIED):app.interpreter.execute('V.Value;')

    def test_dict_subclasses_denied_without_callbacks(self):
        effects=[]
        class Poison(dict):
            def get(self,*a):effects.append('get');raise AssertionError('get')
            def items(self):effects.append('items');raise AssertionError('items')
            def __iter__(self):effects.append('iter');raise AssertionError('iter')
        for target in ('registry','factory','descriptor','owner'):
            app=self.app();factory=app.xdto.factory
            if target=='registry':factory._types=Poison(factory._types)
            else:
                obj=factory if target=='factory' else app.xdto if target=='owner' else factory._types[xdto_values.XS,'string']
                obj.__dict__=Poison(vars(obj))
            with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
        self.assertEqual(effects,[])

    def test_forged_saved_callable_no_equality_callback(self):
        app=self.app();effects=[]
        class Poison:
            def __call__(self,*args):effects.append('call')
            def __eq__(self,other):effects.append('eq');return True
        app.interpreter.variables['f']=HostFunction('Type',MethodType(Poison(),app.xdto.factory))
        with self.assertRaises(basic.DENIED):app.interpreter.execute('F("x","y");')
        self.assertEqual(effects,[])

    def test_argument_time_mutation_and_foreign_type_denied(self):
        app=self.prepared();factory=app.xdto.factory
        def mutate():factory._types=dict(factory._types);return 'late'
        app.interpreter.register_function('Touch',mutate)
        with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,Touch());')
        app=self.prepared();other=self.app()
        app.interpreter.variables['t']=other.xdto.factory.type(xdto_values.XS,'string')
        with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,"foreign");')

    def test_source_files_and_loader_replacement_denied(self):
        app=self.prepared();app.files=dict(app.files)
        with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
        app=self.app();effects=[];app.xdto.factory._source_packages_loader=lambda *_:effects.append('load')
        with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
        self.assertEqual(effects,[])

    def test_quota_and_scalar_coercion_remain_closed(self):
        app=self.prepared();before=app.xdto.factory._nodes
        with patch.object(xdto_values,'MAX_NODES',before):
            with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,"excess");')
        self.assertEqual(app.xdto.factory._nodes,before)
        effects=[]
        class Poison:
            def __str__(self):effects.append('str');return 'poison'
        app.interpreter.variables['p']=Poison()
        with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,P);')
        self.assertEqual(effects,[])

    def test_private_seals_do_not_keep_application_alive(self):
        from yadinassi.configuration_source_runtime import SourceApplication
        from test_configuration_source_runtime import source
        app=SourceApplication(source(b''),output=lambda _:None);app.start()
        app.interpreter.execute('T=XDTOFactory.Type("http://www.w3.org/2001/XMLSchema","string");')
        reference=weakref.ref(app);factory=weakref.ref(app.xdto.factory)
        app.close();del app
        for _ in range(3):gc.collect()
        self.assertIsNone(reference());self.assertIsNone(factory())

    def test_lowered_descriptor_cap_does_not_publish(self):
        app=self.app();factory=app.xdto.factory;before=factory._types
        with patch.object(xdto_values,'MAX_TYPES',len(before)):
            with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("urn:owned:records","Code");')
        self.assertIs(factory._types,before);self.assertEqual(app.xdto._loaded,set())

    def test_initial_registry_roots_cannot_be_replaced(self):
        for field in ('_types','_roots','_packages'):
            with self.subTest(field=field):
                app=self.app();factory=app.xdto.factory
                original=getattr(factory,field)
                replacement=(xdto_values.BSLXDTOPackageCollection(original._items)
                             if field=='_packages' else dict(original))
                setattr(factory,field,replacement)
                with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')

    def test_lowered_package_cap_does_not_publish(self):
        from yadinassi import xdto_packages
        app=self.app();factory=app.xdto.factory;before=factory._types
        with patch.object(xdto_packages,'MAX_PACKAGES',1):
            with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("urn:owned:records","Code");')
        self.assertIs(factory._types,before);self.assertEqual(app.xdto._loaded,set())

    def test_reachable_parser_helpers_rejected_before_callbacks(self):
        from yadinassi import xml_writer,xml_io,configuration_xml
        effects=[]
        for module,name in ((xml_writer,'_text'),(xdto_values.re,'fullmatch')):
            app=self.app()
            with patch.object(module,name,lambda *a,**k:effects.append('helper')):
                with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
        class Poison:
            def __getattribute__(self,name):effects.append('module');raise AssertionError('module')
        for module,name in ((xml_io,'expat'),(configuration_xml,'ET'),(xdto_values,'re')):
            app=self.app()
            with patch.object(module,name,Poison()):
                with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Type("x","y");')
        self.assertEqual(effects,[])

    def test_foreign_metaclass_cannot_run_from_type_admission(self):
        from yadinassi import python_direct_source_xdto as direct
        effects=[]
        class Meta(type):
            def __eq__(self,other):effects.append('eq');return False
            __hash__=type.__hash__
        class Poison(metaclass=Meta):pass
        self.assertFalse(direct.owns(Poison()))
        app=self.prepared();app.interpreter.variables['p']=Poison()
        with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T,P);')
        self.assertEqual(effects,[])
