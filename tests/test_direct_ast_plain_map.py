import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_plain_map import PlainMap

class PlainMapTests(unittest.TestCase):
    def test_default_and_prepared_use_plain_dict(self):
        for prepared in (False,True):
            vm=Interpreter()
            try:
                source='M=New Map;For I=0 To 7 Do M.Insert(I,I);EndDo;R=0;For I=0 To 7 Do R=R+M.Get(I);EndDo;Missing=M[99];'
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertIs(type(vm.variables['m']),PlainMap)
                self.assertEqual(vm.variables['r'],Decimal(28));self.assertIsNone(vm.variables['missing'])
            finally:vm.close()
    def test_iteration_order_and_dynamic_constructor(self):
        vm=Interpreter()
        try:
            vm.execute('M=New("Map");M.Insert(2,3);M.Insert(1,4);R=0;For Each P In M Do R=R*10+P.Key;EndDo;')
            self.assertIs(type(vm.variables['m']),PlainMap);self.assertEqual(vm.variables['r'],Decimal(21))
        finally:vm.close()
    def test_record_python_key_domain_differences(self):
        vm=Interpreter()
        try:
            vm.execute('M=New Map;M.Insert(True,4);M.Insert(1,5);R=M.Count();V=M.Get(True);')
            self.assertEqual(vm.variables['r'],Decimal(1));self.assertEqual(vm.variables['v'],Decimal(5))
            with self.assertRaisesRegex(Exception,'scalar Python value'):
                vm.execute('M=New Map;A=New Array;M.Insert(A,1);')
            self.assertEqual(len(vm.variables['m']),0)
        finally:vm.close()

    def test_opaque_key_does_not_invoke_hash_or_eq(self):
        from yadinassi.types.values import HostFunction
        for operation in ('M.Insert(K,1);','R=M.Get(K);','R=M[K];','M[K]=1;','M.Delete(K);'):
            vm=Interpreter();events=[]
            class Key:
                def __hash__(self):events.append('hash');vm.close();return 1
                def __eq__(self,other):events.append('eq');return False
            vm.functions['opaque']=HostFunction('Opaque',lambda:Key())
            try:
                with self.assertRaisesRegex(Exception,'scalar Python value'):
                    vm.execute('K=Opaque();M=New Map;'+operation+'After=1;')
                self.assertEqual(events,[]);self.assertNotIn('after',vm.variables)
                self.assertEqual(len(vm.variables['m']),0)
            finally:vm.close()

    def test_public_mapping_mutators_reject_foreign_keys(self):
        class Key:
            def __hash__(self):return 1
        key=Key();source={key:1}
        for change in (lambda m:m.update(source),lambda m:m.setdefault(key,1),lambda m:m.__ior__(source)):
            m=PlainMap()
            with self.assertRaises(TypeError):change(m)
            self.assertEqual(len(m),0)

    def test_map_equality_never_compares_opaque_values_or_foreign_receiver(self):
        from yadinassi.types.values import HostFunction
        vm=Interpreter();events=[]
        class Opaque:
            def __eq__(self,other):events.append('eq');vm.close();return False
            def __ne__(self,other):events.append('ne');vm.close();return True
        vm.functions['opaque']=HostFunction('Opaque',lambda:Opaque())
        try:
            vm.execute('H=Opaque();A=New Map;B=New Map;A.Insert(1,H);B.Insert(1,H);X=A=B;Y=A<>B;L=H=A;R=A=H;P=H<>A;Q=A<>H;Self=A=A;')
            self.assertEqual(events,[])
            self.assertEqual([vm.variables[k] for k in ('x','y','l','r','p','q','self')],[False,True,False,False,True,True,True])
        finally:vm.close()

    def test_fixed_copy_rejects_opaque_before_hash(self):
        from yadinassi.collections.maps import BSLMap,BSLFixedMap
        events=[]
        class Key:
            def __hash__(self):events.append('hash');return 1
            def __eq__(self,other):events.append('eq');return False
        original=BSLMap();original.insert(Key(),1);fixed=BSLFixedMap(original)
        for dynamic in (False,True):
            vm=Interpreter();vm.variables['fixed']=fixed
            try:
                source='Args=New Array;Args.Add(Fixed);M=New("Map",Args);' if dynamic else 'M=New Map(Fixed);'
                with self.assertRaisesRegex(Exception,'scalar Python value'):vm.execute(source)
                self.assertEqual(events,[]);self.assertNotIn('m',vm.variables)
            finally:vm.close()
