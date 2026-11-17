"""Flat object writes revalidate provenance and quotas before publication."""
import unittest
from unittest.mock import patch
import test_python_direct_source_xdto as basic
import test_python_direct_source_xdto_objects as flat
from yadinassi import xdto_values
from yadinassi.values import HostFunction

class FlatXDTOSecurity(unittest.TestCase):
    setUp=flat.FlatXDTOTests.setUp
    app=flat.FlatXDTOTests.app
    prepared=flat.FlatXDTOTests.prepared
    def test_global_factory_method_reference_metadata_no_callbacks(self):
        app=self.prepared();vm=app.interpreter;effects=[]
        vm.execute('Build=XDTOFactory.Create;')
        class Evil:
            def __bool__(self):effects.append('bool');return False
        vm.variables['build'].reference_parameters=Evil()
        with self.assertRaises(basic.DENIED):vm.execute('Build(T);')
        self.assertEqual(effects,[])
    def test_global_hostfunction_class_hook_no_callbacks(self):
        app=self.prepared();effects=[]
        with patch.object(HostFunction,'__init__',lambda *a:effects.append('init')):
            with self.assertRaises(basic.DENIED):app.interpreter.execute('XDTOFactory.Create(T);')
        self.assertEqual(effects,[])
    def test_primitive_namespace_changed_before_property_rhs(self):
        app=self.prepared();vm=app.interpreter;effects=[]
        class Evil(str):
            def __eq__(self,other):effects.append('eq');return False
            def __ne__(self,other):effects.append('ne');return True
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('touch') or 'x')
        with patch.object(xdto_values,'XS',Evil(xdto_values.XS)):
            with self.assertRaises(basic.DENIED):vm.execute('V.Label=Touch();')
        self.assertEqual(effects,[])
    def test_saved_method_fields_rechecked_after_argument_callback(self):
        app=self.prepared();vm=app.interpreter;effects=[];vm.execute('Build=XDTOFactory.Create;')
        class Key:
            def __hash__(self):return hash('function')
            def __eq__(self,other):effects.append('eq');return False
        def mutate():
            fields=vm.variables['build'].__dict__;fields.pop('function');fields[Key()]=None
            return vm.variables['t']
        vm.functions['mutate']=HostFunction('Mutate',mutate)
        with self.assertRaises(basic.DENIED):vm.execute('Build(Mutate());')
        self.assertEqual(effects,[])
    def test_unknown_property_denied_before_rhs(self):
        app=self.prepared();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('touch') or 'x')
        with self.assertRaises(basic.DENIED):vm.execute('V.Unknown=Touch();')
        self.assertEqual(effects,[])
    def test_foreign_application_object_and_type_rejected(self):
        first=self.prepared();second=self.prepared();vm=second.interpreter
        vm.variables['foreign']=first.interpreter.variables['v'];vm.variables['foreignkind']=first.interpreter.variables['t']
        for code in ('Foreign.Label;','Foreign.Label="x";','XDTOFactory.Create(ForeignKind);'):
            with self.subTest(code=code),self.assertRaises(basic.DENIED):vm.execute(code)
    def test_forged_host_object_not_admitted(self):
        app=self.prepared();vm=app.interpreter
        forged=object.__new__(xdto_values.BSLXDTODataObject);forged.__dict__.update(vm.variables['v'].__dict__)
        vm.variables['forged']=forged
        with self.assertRaises(basic.DENIED):vm.execute('Forged.Label;')
    def test_scalar_object_inputs_not_implicitly_reowned(self):
        app=self.prepared();vm=app.interpreter
        vm.execute('S=XDTOFactory.Type("'+flat.XS+'","string");D=XDTOFactory.Create(S,"scalar");')
        with self.assertRaises(basic.DENIED):vm.execute('V.Label=D;')
        self.assertIsNone(vm.execute('V.Label;'))
    def test_values_dict_replacement_and_hidden_extra_property_denied(self):
        for replacement in ('copy','extra'):
            app=self.prepared();vm=app.interpreter;obj=vm.variables['v']
            if replacement=='copy':obj._values=dict(obj._values)
            else:obj._values['Unknown']=None
            with self.subTest(replacement=replacement),self.assertRaises(basic.DENIED):vm.execute('V.Label;')
    def test_scalar_child_mutation_denied(self):
        app=self.prepared();vm=app.interpreter;vm.execute('V.Label="ok";')
        obj=vm.variables['v'];obj._values['Label']._value='changed'
        with self.assertRaises(basic.DENIED):vm.execute('V.Label;')
    def test_mutation_during_rhs_prevents_setter_commit(self):
        app=self.prepared();vm=app.interpreter;vm.execute('V.Label="ok";')
        obj=vm.variables['v'];old=obj._values['Label'];before=app.xdto.factory._nodes
        def touch():obj._values=dict(obj._values);return 'bad'
        vm.functions['touch']=HostFunction('Touch',touch)
        with self.assertRaises(basic.DENIED):vm.execute('V.Label=Touch();')
        self.assertIs(obj._values['Label'],old);self.assertEqual(app.xdto.factory._nodes,before)
    def test_field_key_and_mapping_subclass_callbacks_not_run(self):
        effects=[]
        class Key:
            def __hash__(self):return hash('_factory')
            def __eq__(self,other):effects.append('eq');return False
        class Mapping(dict):
            def get(self,*args):effects.append('get');raise AssertionError('callback')
            def items(self):effects.append('items');raise AssertionError('callback')
            def __iter__(self):effects.append('iter');raise AssertionError('callback')
        app=self.prepared();vm=app.interpreter;vm.variables['v'].__dict__[Key()]=0;effects.clear()
        with self.assertRaises(basic.DENIED):vm.execute('V.Label;')
        app=self.prepared();vm=app.interpreter;vm.variables['v']._values=Mapping()
        with self.assertRaises(basic.DENIED):vm.execute('V.Label;')
        self.assertEqual(effects,[])
    def test_null_binding_changed_before_rhs(self):
        app=self.prepared();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('touch') or 'x')
        with patch.object(xdto_values,'NULL',True):
            with self.assertRaises(basic.DENIED):vm.execute('V.Optional=Touch();')
        self.assertEqual(effects,[])
    def test_canonical_set_hook_checked_before_rhs(self):
        app=self.prepared();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('touch') or 'x')
        with patch.object(xdto_values.BSLXDTODataObject,'set',lambda *a:effects.append('set')):
            with self.assertRaises(basic.DENIED):vm.execute('V.Label=Touch();')
        self.assertEqual(effects,[])
    def test_property_descriptor_mutation_before_rhs(self):
        app=self.prepared();vm=app.interpreter;effects=[]
        vm.functions['touch']=HostFunction('Touch',lambda:effects.append('touch') or 'x')
        vm.variables['t']._properties._items[0]._upper=2
        with self.assertRaises(basic.DENIED):vm.execute('V.Label=Touch();')
        self.assertEqual(effects,[])
    def test_bound_setter_expires_with_activation(self):
        from yadinassi import python_direct_source_xdto_objects as helper
        app=self.prepared();vm=app.interpreter;captured=[];original=helper.set_member
        def intercept(*args):
            result=original(*args);captured.append(result);return result
        with patch.object(helper,'set_member',intercept):vm.execute('V.Label="ok";')
        with self.assertRaises(basic.DENIED):captured[-1]('bad')
        self.assertEqual(vm.execute('V.Label;'),'ok')
    def test_closed_application_object_cannot_be_lent(self):
        first=self.prepared();second=self.prepared();second.interpreter.variables['foreign']=first.interpreter.variables['v'];first.close()
        with self.assertRaises(basic.DENIED):second.interpreter.execute('Foreign.Label;')
