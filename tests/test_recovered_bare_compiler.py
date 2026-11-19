"""Independent reconstructed contract, not legacy parity tests."""
import unittest
from decimal import Decimal
from recovered_bare_fixture import Interpreter
from yadinassi.native_bare_collections import BareArray
from yadinassi.python_direct import PythonDirectUnsupported

class RecoveredBareCompilerTests(unittest.TestCase):
    def run_source(self, source, prepared=False):
        vm=Interpreter()
        if prepared: vm.execute_prepared(vm.prepare(source))
        else: vm.execute(source)
        return vm
    def test_array_composition_and_native_int(self):
        source='A=New Array; For I=0 To 7 Do A.Add(I); EndDo; A.Set(1,9); A.Insert(0,42); A.Delete(2); R=A.Get(0); N=A.Count(); U=A.UBound();'
        for prepared in (False,True):
            vm=self.run_source(source,prepared)
            self.assertIs(type(vm.variables['a']),BareArray)
            self.assertEqual(list(vm.variables['a']),[42,0,2,3,4,5,6,7])
            self.assertEqual((vm.variables['r'],vm.variables['n'],vm.variables['u']),(42,8,7))
            self.assertIs(type(vm.variables['i']),int)
    def test_control_flow_and_fractional_decimal(self):
        source='S=0; A=New Array; A.Add(2); A.Add(3); For Each X In A Do S=S+X; EndDo; While S<8 Do S=S+1; EndDo; If S=8 Then R=1.5+2; Else R=0; EndIf;'
        vm=self.run_source(source,True)
        self.assertEqual(vm.variables['s'],8)
        self.assertEqual(vm.variables['r'],Decimal('3.5'))
    def test_generated_has_direct_constructor_and_calls(self):
        vm=Interpreter(); plan=vm.prepare('A=New Array; A.Add(1); R=A.Get(0); N=StrLen("abcd");')
        self.assertIn('_BareArray()',plan.generated_source)
        self.assertIn('.add(1)',plan.generated_source)
        self.assertIn('.get(0)',plan.generated_source)
        self.assertIn('len(',plan.generated_source)
        for absent in ('admit','resolve','context','_native_protocol_array','import '):
            self.assertNotIn(absent,plan.generated_source)
    def test_snapshot_and_state_reuse(self):
        from yadinassi.syntax.parser import parse
        vm=Interpreter(); nodes=parse('A.Add(7); N=A.Count();'); plan=vm.prepare_program(nodes); nodes.clear()
        vm.variables['a']=BareArray(); vm.execute_prepared(plan); vm.execute_prepared(plan)
        self.assertEqual(list(vm.variables['a']),[7,7]); self.assertEqual(vm.variables['n'],2)
    def test_unsupported_does_not_execute_prefix(self):
        for source in ('X=1; Q=New Query;', 'X=1; Foo();','Function F() Return GlobalUnknown; EndFunction; X=F();'):
            vm=Interpreter()
            with self.assertRaises(PythonDirectUnsupported): vm.execute(source)
            self.assertNotIn('x',vm.variables)
    def test_basic_array_contract(self):
        a=BareArray(2); a.set(0,3); self.assertEqual(list(a),[3,None])
        self.assertEqual(a.find(3),0)
        with self.assertRaises(ValueError): a.find(8)
        with self.assertRaises(TypeError): a.get(Decimal(0))
        self.assertEqual([len(row) for row in BareArray(2,3)], [3,3])
        a.clear(); self.assertEqual(a.count(),0)
    def test_native_strings(self):
        vm=self.run_source('A=ВРег("Straße"); B=НРег("ABC"); C=СокрЛП(" x ");')
        self.assertEqual((vm.variables['a'],vm.variables['b'],vm.variables['c']),('STRASSE','abc','x'))
