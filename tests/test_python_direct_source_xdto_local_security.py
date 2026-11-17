"""Local XDTO factories do not gain authority from mutable host shapes."""
import unittest
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_python_direct_source_xdto_local as local
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi import xdto_io,xdto_values
from yadinassi.values import HostFunction

class LocalXDTOSecurity(unittest.TestCase):
    setUp=local.LocalXDTOTests.setUp
    app=local.LocalXDTOTests.app
    prepared=local.LocalXDTOTests.prepared
    def test_marker_cannot_reassign_factory_to_another_application(self):
        from weakref import ref
        first=self.prepared();second=self.app();factory=first.interpreter.variables['f']
        factory._direct_local_xdto.application=ref(second)
        second.interpreter.variables['foreign']=factory
        with self.assertRaises(basic.DENIED):second.interpreter.execute('Foreign.Type("'+local.XS+'","string");')
    def test_marker_callbacks_rejected_before_invocation(self):
        effects=[]
        class Evil:
            def __call__(self):effects.append('call');return None
            def __iter__(self):effects.append('iter');return iter(())
            def __eq__(self,other):effects.append('eq');return False
            def __ne__(self,other):effects.append('ne');return True
        for field in ('application','nodes','units','graph'):
            app=self.prepared();factory=app.interpreter.variables['f']
            setattr(factory._direct_local_xdto,field,Evil())
            with self.subTest(field=field),self.assertRaises(basic.DENIED):app.interpreter.execute('F.Type("'+local.XS+'","string");')
        self.assertEqual(effects,[])
    def test_mutable_marker_cannot_authorize_counter_rollback(self):
        app=self.prepared();vm=app.interpreter;factory=vm.variables['f']
        factory._nodes=0;factory._units=0
        factory._direct_local_xdto.nodes=0;factory._direct_local_xdto.units=0
        with self.assertRaises(basic.DENIED):vm.execute('F.Create(T,"x");')
    def test_mutable_marker_cannot_authorize_replaced_graph(self):
        from yadinassi import python_direct_source_xdto_local as helper
        app=self.prepared();vm=app.interpreter;factory=vm.variables['f'];seal=factory._direct_local_xdto
        factory._types=dict(factory._types);seal.types=factory._types;seal.graph=helper._graph(factory)
        with self.assertRaises(basic.DENIED):vm.execute('F.Type("'+local.XS+'","string");')
    def test_failed_close_cannot_refund_creation_quota(self):
        app=self.app();vm=app.interpreter
        for _ in range(32):vm.execute('F=New XDTOFactory;')
        class FailedClose:
            def close(self):raise ValueError('injected close failure')
        original=app.constant_store;app.constant_store=FailedClose()
        try:
            with self.assertRaisesRegex(ValueError,'injected close failure'):app.close()
            self.assertEqual(app.state,'running')
            app.constant_store=original
            with self.assertRaises(basic.DENIED):vm.execute('F=New XDTOFactory;')
        finally:app.constant_store=original
    def test_replaced_graph_roots_and_accounting_denied(self):
        for name in ('_types','_roots','_nodes','_units'):
            app=self.prepared();vm=app.interpreter;factory=vm.variables['f']
            setattr(factory,name,dict(getattr(factory,name)) if name in ('_types','_roots') else False)
            with self.subTest(name=name),self.assertRaises(basic.DENIED):vm.execute('F.Type("'+local.XS+'","string");')
    def test_oversized_descriptor_tuple_rejected(self):
        app=self.prepared();vm=app.interpreter;factory=vm.variables['f']
        factory._packages._items=tuple([factory._packages._items[0]]*10001)
        with self.assertRaises(basic.DENIED):vm.execute('F.Type("'+local.XS+'","string");')
    def test_loader_injection_denied_without_callback(self):
        app=self.prepared();effects=[];vm=app.interpreter
        vm.variables['f']._source_packages_loader=lambda *args:effects.append('loader')
        with self.assertRaises(basic.DENIED):vm.execute('F.Type("urn:owned:records","Code");')
        self.assertEqual(effects,[])
    def test_mutated_value_and_descriptor_denied(self):
        app=self.prepared();vm=app.interpreter;vm.variables['v']._value='changed'
        with self.assertRaises(basic.DENIED):vm.execute('V.Value;')
        app=self.prepared();vm=app.interpreter;vm.variables['t']._name='changed'
        with self.assertRaises(basic.DENIED):vm.execute('F.Create(T,"x");')
    def test_dict_subclass_rejected_before_callbacks(self):
        effects=[]
        class Evil(dict):
            def get(self,*args):effects.append('get');raise AssertionError('callback')
            def items(self):effects.append('items');raise AssertionError('callback')
            def __iter__(self):effects.append('iter');raise AssertionError('callback')
        app=self.prepared();app.interpreter.variables['f']._types=Evil()
        with self.assertRaises(basic.DENIED):app.interpreter.execute('F.Type("'+local.XS+'","string");')
        self.assertEqual(effects,[])
    def test_nonstring_instance_keys_rejected_before_equality(self):
        effects=[]
        class Evil:
            def __hash__(self):return hash('_types')
            def __eq__(self,other):effects.append('eq');return False
        app=self.prepared();app.interpreter.variables['f'].__dict__[Evil()]=0;effects.clear()
        with self.assertRaises(basic.DENIED):app.interpreter.execute('F.Type("'+local.XS+'","string");')
        self.assertEqual(effects,[])
    def test_hostfunction_reference_metadata_rejected_before_truthiness(self):
        effects=[]
        class Evil:
            def __bool__(self):effects.append('bool');return False
        app=self.app();vm=app.interpreter
        vm.types['xdtofactory'].reference_parameters=Evil()
        with self.assertRaises(basic.DENIED):vm.execute('F=New XDTOFactory;')
        self.assertEqual(effects,[])
        app=self.prepared();vm=app.interpreter;vm.execute('Fn=F.Type;')
        vm.variables['fn'].reference_parameters=Evil()
        with self.assertRaises(basic.DENIED):vm.execute('Fn("'+local.XS+'","string");')
        self.assertEqual(effects,[])
    def test_hostfunction_class_hook_rejected(self):
        app=self.app();effects=[]
        with patch.object(HostFunction,'__call__',lambda *a:effects.append('call')):
            with self.assertRaises(basic.DENIED):app.interpreter.execute('F=New XDTOFactory;')
        self.assertEqual(effects,[])
    def test_constructor_namespace_rejected_before_hash_callback(self):
        app=self.app();effects=[]
        class Evil(str):
            def __hash__(self):effects.append('hash');return super().__hash__()
        for module in (xdto_io,xdto_values):
            with self.subTest(module=module.__name__),patch.object(module,'XS',Evil(module.XS)):
                with self.assertRaises(basic.DENIED):app.interpreter.execute('F=New XDTOFactory;')
        self.assertEqual(effects,[])
    def test_constructor_internal_class_hook_rejected(self):
        app=self.app();effects=[]
        with patch.object(xdto_values.BSLXDTOValueType,'__init__',lambda *a:effects.append('init')):
            with self.assertRaises(basic.DENIED):app.interpreter.execute('F=New XDTOFactory;')
        self.assertEqual(effects,[])
    def test_mutation_during_argument_evaluation_rejected(self):
        app=self.prepared();vm=app.interpreter
        def change():vm.variables['f']._roots={};return 'x'
        vm.functions['change']=HostFunction('Change',change)
        with self.assertRaises(basic.DENIED):vm.execute('F.Create(T,Change());')
    def test_shadow_before_assignment_and_sibling_global(self):
        out=[];body='''Procedure OnStart()
If XDTOFactory.Type("urn:owned:records","Code")=Undefined Then Raise "missing global";EndIf;
XDTOFactory=New XDTOFactory;
If XDTOFactory.Type("urn:owned:records","Code")<>Undefined Then Raise "local polluted";EndIf;
Other();Message("ok");EndProcedure
Procedure Other()
If XDTOFactory.Type("urn:owned:records","Code")=Undefined Then Raise "sibling shadowed";EndIf;
EndProcedure'''
        import test_source_xdto_packages as existing
        app=SourceApplication(source(body.encode(),existing.SourceXDTOTests().mapping()),output=out.append);self.addCleanup(app.close)
        self.assertTrue(app.start());self.assertEqual(out,['ok'])
    def test_shadow_execute_eval_rejected_before_effects(self):
        for fragment in ('Execute("X=1;");','X=Eval("1");'):
            out=[];body='Procedure OnStart() Message("bad");XDTOFactory=New XDTOFactory;'+fragment+'EndProcedure'
            app=SourceApplication(source(body.encode()),output=out.append);self.addCleanup(app.close)
            with self.assertRaises(basic.DENIED):app.start()
            self.assertEqual(out,[])
    def test_raw_bound_callback_cannot_outlive_activation(self):
        from yadinassi import python_direct_source_xdto_local as helper
        app=self.prepared();vm=app.interpreter;callbacks=[];original=helper.captured
        def capture(*args,**kwargs):
            result=original(*args,**kwargs)
            if result is not None:callbacks.append(result)
            return result
        with patch.object(helper,'captured',capture):vm.execute('F.Type("'+local.XS+'","string");')
        self.assertTrue(callbacks)
        with self.assertRaises(basic.DENIED):callbacks[-1](local.XS,'string')
        vm.functions['old']=HostFunction('Old',lambda:callbacks[-1](local.XS,'string'))
        with self.assertRaises(basic.DENIED):vm.execute('Old();')
    def test_saved_method_descriptor_rebinds_current_activation(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('LookupFn=F.Type;BuildFn=F.Create;')
        vm.execute('T=LookupFn("'+local.XS+'","string");V=BuildFn(T,"later");')
        self.assertEqual(vm.execute('V.Value;'),'later')
    def test_explicit_local_and_parameter_factory_slots(self):
        out=[];body='''Procedure OnStart() Var XDTOFactory;XDTOFactory=New XDTOFactory;Use(XDTOFactory);EndProcedure
Procedure Use(Val XDTOFactory)
T=XDTOFactory.Type("http://www.w3.org/2001/XMLSchema","string");
V=XDTOFactory.Create(T,"explicit");Message(V.Value);
EndProcedure'''
        app=SourceApplication(source(body.encode()),output=out.append);self.addCleanup(app.close)
        self.assertTrue(app.start());self.assertEqual(out,['explicit'])
    def test_late_shadow_export_conflict_rejected(self):
        app=self.app();vm=app.interpreter
        vm.execute('Procedure P() XDTOFactory=New XDTOFactory;EndProcedure')
        vm.exported_variables.add('xdtofactory')
        with self.assertRaises(basic.DENIED):vm.execute('P();')
