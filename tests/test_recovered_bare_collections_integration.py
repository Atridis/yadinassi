import unittest
from recovered_bare_fixture import Interpreter
from yadinassi.execution.codegen.native_bare_collections import BareArray

class RecoveredBareCollectionsIntegration(unittest.TestCase):
    def test_map_and_structure_named_reads(self):
        source='M=New Map; M.Insert("a",3); M.Insert("b",4); R=0; For Each P In M Do R=R+P.Value; EndDo; S=New Structure("Name",7); S.Name=9; X=S.Name;'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared: vm.execute_prepared(vm.prepare(source))
            else: vm.execute(source)
            self.assertEqual(vm.variables['r'],7); self.assertEqual(vm.variables['x'],9)
    def test_valuelist_unload_real_composition(self):
        source='V=New ValueList; V.Add(7); V.Add(9); A=V.UnloadValues(); R=A.Get(0); N=A.Count(); A.Set(0,11); V.Get(1).Value=13; X=A.Get(1); Y=V.Get(0).Value;'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared: vm.execute_prepared(vm.prepare(source))
            else: vm.execute(source)
            self.assertEqual([vm.variables[k] for k in ('r','n','x','y')],[7,2,9,7])
            self.assertIs(type(vm.variables['a']),BareArray)
            self.assertEqual(list(vm.variables['a']),[11,9])
