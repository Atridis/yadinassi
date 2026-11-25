"""Canonical fixed-array lookup must not compare direct collection payloads."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter,BSLError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.types.values import BSLFixedArray, HostFunction
from yadinassi.execution.codegen.direct_structure import _DirectStructure
from yadinassi.execution.codegen.direct_collections import _TypedMap
from yadinassi.execution.direct.python_direct import make_boundary
from yadinassi.execution.direct.python_direct_fixed_find import captured

SETUP='S=New Structure("X",1);M=New Map;M["X"]=1;A=New Array;A.Add(S);A.Add(M);A.Add(S);F=New FixedArray(A);'
BODY='R=F.Find(S);Q=F.Найти(M);U=F.Find(New Structure("X",1));N=New Map;N["X"]=1;V=F.Find(N);'

class DirectFixedReceiverFindTests(unittest.TestCase):
    def test_routes_canonical_consistency_without_vm(self):
        for route in ('source','ast','prepared','execute','eval'):
            vm=Interpreter();vm.execute(SETUP)
            with self.subTest(route=route):
                if route=='source':vm.execute(BODY)
                elif route=='ast':vm.execute_program(parse(BODY))
                elif route=='prepared':vm.execute_prepared(vm.prepare(BODY))
                elif route=='execute':vm.execute('Var R,Q,U,N,V;Execute("'+BODY.replace('"','""')+'");')
                else:
                    vm.execute('R=Eval("F.Find(S)");Q=Eval("F.Найти(M)");U=Eval("F.Find(New Structure(""X"",1))");N=New Map;N["X"]=1;V=Eval("F.Find(N)");')
            self.assertEqual((vm.variables['r'],vm.variables['q']),(0,1))
            self.assertIsNone(vm.variables['u']);self.assertIsNone(vm.variables['v'])
            self.assertIs(type(vm.variables['r']),Decimal)

    def test_named_captured_cached_alias_and_live_state(self):
        vm=Interpreter();vm.execute(SETUP);saved=vm.variables['f'].get_method('Find');vm.variables['saved']=saved
        plan=vm.prepare('R=Saved(S);Q=F.Find(M);')
        for value in (7,8):
            vm.execute('S.X='+str(value)+';M["X"]='+str(value)+';')
            vm.execute_prepared(plan);self.assertEqual((vm.variables['r'],vm.variables['q']),(0,1))
        vm.execute('G=New FixedArray(New Array);F=G;')
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],0);self.assertIsNone(vm.variables['q'])

    def test_direct_payload_cycles_and_foreign_elements_no_hooks(self):
        vm=Interpreter();vm.execute(SETUP);seen=[]
        class Evil:
            def __eq__(self,other):seen.append('eq');raise AssertionError('eq')
            def __getattribute__(self,name):seen.append(name);raise AssertionError(name)
        vm.variables['evil']=Evil();vm.execute('S.Insert("cycle",S);S.Insert("payload",evil);');needle=vm.variables['s']
        fixed=vm.variables['f'];fixed.items=(Evil(),needle,needle)
        for cls in (_DirectStructure,_TypedMap):
            with patch.object(cls,'__eq__',lambda *args:(_ for _ in ()).throw(AssertionError('eq'))):
                vm.execute('R=F.Find(S);');self.assertEqual(vm.variables['r'],1)
        self.assertEqual(seen,[])

    def test_argument_effect_order_close_revoke_policy_and_tampering(self):
        for mode in ('close','revoke','policy','storage','method'):
            vm=Interpreter(allow_extensions=True);vm.execute(SETUP);context=make_boundary(vm);context.start()
            fixed=vm.variables['f'];saved=fixed.get_method('Find');invoke=captured(context,saved)
            if mode=='close':vm.close()
            elif mode=='revoke':context.revoke()
            elif mode=='policy':context.policy=lambda *args:False
            elif mode=='storage':fixed.items=[]
            else:saved.function=lambda x:0
            with self.subTest(mode=mode),self.assertRaises(BoundaryViolation):invoke(vm.variables['s'])
        vm=Interpreter(allow_extensions=True);vm.execute(SETUP);seen=[]
        vm.register_function('Arg',lambda:seen.append('arg') or vm.variables['s'])
        vm.execute('R=F.Find(Arg());');self.assertEqual(seen,['arg']);self.assertEqual(vm.variables['r'],0)
        vm.register_function('Close',lambda:vm.close() or vm.variables['s'])
        with self.assertRaises(BoundaryViolation):vm.execute('F.Find(Close());')

    def test_captured_metadata_mutation_during_argument_is_fatal(self):
        vm=Interpreter(allow_extensions=True);vm.execute(SETUP);saved=vm.variables['f'].get_method('Find');vm.variables['saved']=saved
        seen=[]
        def mutate():
            saved.function=lambda value:seen.append('replacement')
            return vm.variables['s']
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('Saved(Mutate());')
        self.assertEqual(seen,[])

    def test_policy_distinguishes_named_and_captured_after_arguments(self):
        from yadinassi.execution.direct.python_direct_fixed_find import resolve
        for operation in ('call_member','call_value'):
            vm=Interpreter();vm.execute(SETUP);context=make_boundary(vm);context.start();fixed=vm.variables['f'];seen=[]
            invoke=(resolve(context,fixed,'Find') if operation=='call_member'
                    else captured(context,fixed.get_method('Find')))
            def policy(op,name):
                seen.append((op,name));return op!=operation
            context.policy=policy
            with self.subTest(operation=operation),self.assertRaises(BoundaryViolation):invoke(vm.variables['s'])
            self.assertEqual(seen,[(operation,'find')])

    def test_named_find_binds_once_without_synthetic_capture(self):
        from yadinassi.execution.direct import python_direct_fixed_find as fixed_find
        vm=Interpreter();self.addCleanup(vm.close);vm.execute(SETUP)
        plan=vm.prepare('R=F.Find(S);')
        with patch.object(fixed_find,'_check',wraps=fixed_find._check) as admission:
            with patch.object(fixed_find,'captured',side_effect=AssertionError('not a real capture')):
                vm.execute_prepared(plan)
        self.assertEqual(admission.call_count,4)  # bind, before/after policy, after comparison
        self.assertEqual(vm.variables['r'],0)

    def test_allowing_policy_cannot_invalidate_named_or_saved_receiver(self):
        from yadinassi.execution.direct.python_direct_fixed_find import resolve
        for operation in ('call_member','call_value'):
            with self.subTest(operation=operation):
                vm=Interpreter();self.addCleanup(vm.close);vm.execute(SETUP)
                context=make_boundary(vm);context.start();fixed=vm.variables['f'];seen=[]
                bound=(resolve(context,fixed,'Find') if operation=='call_member'
                       else captured(context,fixed.get_method('Find')))
                def policy(op,name):
                    seen.append((op,name));fixed.items=[];return True
                context.policy=policy
                with self.assertRaises(BoundaryViolation):bound(vm.variables['s'])
                self.assertEqual(seen,[(operation,'find')])

    def test_storage_and_class_overrides_reject_before_hooks(self):
        vm=Interpreter();vm.execute(SETUP);seen=[]
        def hostile(*args):seen.append('hook');raise AssertionError('hook')
        with patch.object(BSLFixedArray,'items',property(hostile),create=True),self.assertRaises(BoundaryViolation):vm.execute('F.Find(S);')
        vm.variables['f'].find=hostile
        with self.assertRaises(BoundaryViolation):vm.execute('F.Find(S);')
        self.assertEqual(seen,[])

    def test_exact_capture_does_not_admit_foreign_receiver_or_override(self):
        vm=Interpreter();context=make_boundary(vm);context.start();seen=[]
        class Meta(type):
            def __eq__(self,other):seen.append('eq');raise AssertionError('eq')
        class Foreign(metaclass=Meta):
            def find(self,value):seen.append('find');raise AssertionError('find')
        fake=HostFunction('Find',Foreign().find)
        self.assertIsNone(captured(context,fake));self.assertEqual(seen,[])

    def test_scalar_native_observation_and_date_controls_are_unchanged(self):
        capture=(Path(__file__).resolve().parents[1]/'integrational_tests/fill_exclude_native/collections.out').read_text(encoding='utf-8')
        self.assertIn('fixed-array.find: [0]',capture)
        vm=Interpreter();vm.execute('A=New Array;A.Add(1);F=New FixedArray(A);R=F.Find(1);')
        self.assertEqual(vm.variables['r'],0)
        vm.execute('A=New Array;A.Add(True);A.Add(1);A.Add("1");F=New FixedArray(A);')
        self.assertEqual([vm.execute('F.Find('+text+')') for text in ('True','1','"1"')],[0,1,2])
        from yadinassi.temporal.dates import BSLDate,MAX_TICKS,UnsupportedDateRange
        vm.variables['date']=BSLDate(MAX_TICKS,boundary=True)
        with self.assertRaises(BSLError):vm.execute('F.Find(date);')

if __name__=='__main__':unittest.main()
