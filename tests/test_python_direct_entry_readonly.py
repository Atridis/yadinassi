"""Readonly direct iterator pairs report catchable errors, not DB authority failures."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen.direct_collections import _DIRECT_MAP_ENTRY_TYPE as Entry
from yadinassi.execution.direct.python_direct_services import ServicesBoundary


class DirectEntryReadonlyTests(unittest.TestCase):
    def vm(self, backend='python-direct', *, allow_extensions=False):
        vm=Interpreter(allow_extensions=allow_extensions, execution_backend=backend);self.addCleanup(vm.close);return vm

    def test_map_structure_properties_catch_error_and_keep_contents(self):
        for constructor in ('New Map', 'New Structure'):
            for name in ('Key','Ключ','vAlUe','Значение','Missing'):
                source=f'''M={constructor};M.Insert("K",1);Caught=False;
For Each P In M Do
    Try P.{name}=2; Except Caught=True;Error=ErrorDescription();EndTry;
    K=P.Key;V=P.Value;
EndDo;
N=M.Count();'''
                with self.subTest(constructor=constructor,name=name):
                    vm=self.vm()
                    vm.execute(source)
                    # Python3.10 direct tracebacks retain line but not expression columns.
                    error=vm.variables['error'].split(': ',1)[1]
                    self.assertIs(vm.variables['caught'],True)
                    self.assertEqual((vm.variables['k'],vm.variables['v'],vm.variables['n']),
                                     ('K',Decimal(1),Decimal(1)))
                    self.assertIn('Свойство недоступно для записи: '+name,error)

    def test_receiver_once_then_rhs_and_rhs_error_takes_precedence(self):
        for rhs_fails in (False,True):
            with self.subTest(rhs_fails=rhs_fails):
                vm=self.vm(allow_extensions=True);events=[]
                vm.execute('M=New Map;M.Insert("K",1);For Each P In M Do EndDo;')
                pair=vm.variables['p']
                def receiver():events.append('receiver');return pair
                def rhs():
                    events.append('rhs')
                    if rhs_fails:raise ValueError('rhs failed')
                    return Decimal(2)
                vm.register_function('Receiver',receiver);vm.register_function('Effect',rhs)
                vm.execute('Try Receiver().Value=Effect();Except E=ErrorDescription();EndTry;')
                self.assertEqual(events,['receiver','rhs'])
                self.assertIn('rhs failed' if rhs_fails else 'Свойство недоступно для записи',vm.variables['e'])
                self.assertEqual(pair.value,Decimal(1))

    def test_closed_lifetime_cannot_be_hidden_as_catchable_readonly(self):
        vm=self.vm(allow_extensions=True);pair=Entry('K',Decimal(1));vm.variables['p']=pair
        def close():vm.close();return Decimal(2)
        vm.register_function('CloseNow',close)
        with self.assertRaises(BoundaryViolation):vm.execute('Try P.Value=CloseNow();Except Caught=True;EndTry;')
        self.assertNotIn('caught',vm.variables);self.assertEqual(pair.value,Decimal(1))

    def test_exact_type_only_no_payload_protocol_and_recheck_delayed_writer(self):
        class Context(ServicesBoundary,BoundaryContext):pass
        events=[]
        class Evil:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        class Child(Entry):pass
        context=Context();context.enter()
        try:
            pair=Entry(Evil(),Evil());writer=context.resolve_set_member(pair,'Value')
            with self.assertRaisesRegex(ValueError,'Свойство недоступно'):writer(Evil())
            with self.assertRaises(BoundaryViolation):context.resolve_set_member(Child(None,None),'Value')
            with self.assertRaises(BoundaryViolation):context.resolve_set_member(Evil(),'Value')
        finally:context.leave();context.revoke()
        with self.assertRaises(BoundaryViolation):writer(None)
        self.assertEqual(events,[])

    def test_counterfeit_class_rebinding_cannot_gain_catchable_admission(self):
        class Fake:pass
        vm=self.vm();pair=Entry('K',Decimal(1));vm.variables['p']=pair
        with patch('yadinassi.execution.codegen.direct_collections._MapEntry',Fake):
            vm.execute('Try P.Value=2;Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught'])
            vm.variables['p']=Fake()
            with self.assertRaises(BoundaryViolation):vm.execute('P.Value=2;')
        self.assertEqual(pair.value,Decimal(1))

    def test_delete_absent_map_keys_is_noop_and_preserves_typed_identity(self):
        source='''M=New Map;K=New Array;Other=New Array;Alias=M;
M.Insert("1",10);M.Insert(1,20);M.Insert(True,30);M.Insert(K,40);
M.Delete(Other);M.Удалить("absent");N=M.Count();
M.Delete(1);M.Delete(1);S=M.Get("1");B=M.Get(True);A=M.Get(K);
M.Delete(K);M.Delete(K);Final=Alias.Count();'''
        vm=self.vm();vm.execute(source)
        self.assertEqual(tuple(vm.variables[k] for k in ('n','s','b','a','final')),
                         tuple(map(Decimal,(4,10,30,40,2))))
