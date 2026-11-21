import unittest
from recovered_bare_fixture import Interpreter

class RecoveredBareFillIntegration(unittest.TestCase):
    def test_common_fields_none_and_payload_alias(self):
        source='S=New Structure("A,B,C",1,Undefined,7); T=New Structure("A,B,D",0,2,9); FillPropertyValues(T,S); X=T.A; Y=T.B; Z=T.D; N=T.Count();'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual([vm.variables[k] for k in ('x','y','z','n')],[1,None,9,3])
    def test_filters_unknown_keys_exclusion_wins(self):
        vm=Interpreter();vm.execute('S=New Structure("A,B,C",1,2,3); T=New Structure("A,B,C",0,0,0); ЗаполнитьЗначенияСвойств(T,S," a, B, missing "," B "); X=T.A; Y=T.B; Z=T.C;')
        self.assertEqual([vm.variables[k] for k in ('x','y','z')],[1,0,0])
    def test_filtered_call_does_not_affect_next_two_arg_call(self):
        vm=Interpreter();vm.execute('S=New Structure("A,B",1,2); T=New Structure("A,B",0,0); FillPropertyValues(T,S,""); X=T.A; FillPropertyValues(T,S); Y=T.A;')
        self.assertEqual((vm.variables['x'],vm.variables['y']),(0,1))
