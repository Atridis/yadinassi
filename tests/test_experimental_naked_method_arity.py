"""Direct method errors and effect order, not differential retired execution."""
import unittest
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError

class MethodArityTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter();self.addCleanup(vm.close);return vm

    def test_invalid_arity_preserves_argument_effect_order(self):
        cases=[('Array','Get',0),('Array','Get',2),('Array','Set',1),('Array','Set',3),('Array','Insert',0),('Array','Insert',3),('Array','Delete',0),('Array','Delete',2),('Map','Get',0),('Map','Get',2),('Map','Insert',3),('Map','Delete',0),('Map','Delete',2),('Structure','Insert',3),('Structure','Delete',0),('Array','Count',1),('Map','Count',1),('Structure','Count',1)]
        for kind,method,count in cases:
            with self.subTest(kind=kind,method=method,count=count):
                vm=self.vm();effects=[]
                vm.register_function('Host',lambda i:effects.append(i) or i)
                source='a=New '+kind+';a.'+method+'('+','.join('Host('+str(i)+')' for i in range(count))+');'
                with self.assertRaises(BSLRuntimeError):vm.execute(source,'arity.bsl')
                self.assertEqual(effects,list(range(count)))

    def test_set_value_effect_precedes_bounds_error(self):
        vm=self.vm();effects=[];vm.register_function('Host',lambda:effects.append('value') or 7)
        with self.assertRaises(BSLRuntimeError):vm.execute('a=New Array;a.Add(1);a.Set(2,Host());','set.bsl')
        self.assertEqual(effects,['value']);self.assertEqual(vm.variables['a'],[1])

    def test_missing_delete_argument_does_not_delete_undefined_key(self):
        vm=self.vm();vm.execute('m=New Map;m.Insert(Undefined,7);Try m.Delete();Except EndTry;r=m.Count();')
        self.assertEqual(vm.variables['r'],1)

    def test_unsupported_method_is_catchable_before_arguments(self):
        for family,method in (('Array','Nonsense'),('Map','Set'),('Structure','Get')):
            with self.subTest(family=family):
                vm=self.vm();events=[];vm.register_function('Host',lambda:events.append('arg'))
                vm.execute('a=New '+family+';r=False;Try a.'+method+'(Host());Except r=True;EndTry;')
                self.assertTrue(vm.variables['r']);self.assertEqual(events,[])

    def test_map_property_is_not_index_lookup(self):
        vm=self.vm();vm.execute('m=New Map;m.Insert("Count",7);r=False;Try x=m.Count;Except r=True;EndTry;')
        self.assertTrue(vm.variables['r'])

    def test_property_key_error_has_source_position(self):
        vm=self.vm();source='s=New Structure("Name",7);v=0;result=s.Property("!",v);'
        with self.assertRaises(BSLRuntimeError) as caught:vm.execute(source,'property.bsl')
        self.assertEqual(caught.exception.line,1);self.assertEqual(caught.exception.source_line,source)
        self.assertEqual(vm.variables['v'],0)

    def test_map_iterator_mutation_is_catchable(self):
        vm=self.vm();vm.execute('m=New Map;m.Insert("x",1);r=False;Try For Each p In m Do m.Insert("y",2);EndDo;Except r=True;EndTry;')
        self.assertTrue(vm.variables['r'])

    def test_host_error_not_confused_with_iterator_error(self):
        vm=self.vm()
        def host():raise RuntimeError('host runtime failure, not iterator')
        vm.register_function('Host',host)
        with self.assertRaisesRegex(RuntimeError,'host runtime failure'):
            vm.execute('m=New Map;m.Insert("x",1);For Each p In m Do Host();EndDo;')

    def test_missing_map_index_is_undefined(self):
        vm=self.vm();vm.execute('m=New Map;r=m["missing"];');self.assertIsNone(vm.variables['r'])
        with self.assertRaises(BSLRuntimeError):vm.execute('s=New Structure;r=s["missing"];')
