"""Native pair labels without traversing direct iterator payloads."""
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.codegen.direct_collections import _DIRECT_MAP_ENTRY_TYPE as Pair
from yadinassi.syntax.parser import parse

class DirectPairStringTests(unittest.TestCase):
    def test_native_labels_all_routes_no_vm(self):
        fixture=(Path(__file__).resolve().parents[1]/'integrational_tests/fill_exclude_native/collections.out').read_text(encoding='utf-8')
        for kind,constructor in (('structure','New Structure("X",1)'),('map','New Map')):
            self.assertIn('present.key-and-value.'+kind+': [КлючИЗначение]',fixture)
            for route in ('source','ast','prepared','execute','eval'):
                vm=Interpreter();vm.execute('S='+constructor+';S["X"]=1;For Each P In S Do EndDo;')
                source='R=String(P);Q=Строка(P);'
                with self.subTest(kind=kind,route=route):
                    if route=='source':vm.execute(source)
                    elif route=='ast':vm.execute_program(parse(source))
                    elif route=='prepared':vm.execute_prepared(vm.prepare(source))
                    elif route=='execute':vm.execute('Var R,Q;Execute("'+source+'");')
                    else:vm.execute('R=Eval("String(P)");Q=Eval("Строка(P)");')
                self.assertEqual((vm.variables['r'],vm.variables['q']),('КлючИЗначение','КлючИЗначение'))

    def test_payload_hooks_cycles_and_pair_hooks_are_not_read(self):
        seen=[]
        class Evil:
            def __repr__(self):seen.append('repr');raise AssertionError('repr')
            def __str__(self):seen.append('str');raise AssertionError('str')
        cycle=[];cycle.append(cycle);cycle.append(Evil())
        vm=Interpreter();vm.variables['p']=Pair(Evil(),cycle)
        def hostile(*args):seen.append('pair hook');raise AssertionError('pair hook')
        with patch.object(Pair,'__str__',hostile,create=True),patch.object(Pair,'__repr__',hostile),patch.object(Pair,'__getattribute__',hostile):
            self.assertEqual(vm.execute('String(P)'),'КлючИЗначение')
        self.assertEqual(seen,[])

    def test_named_captured_custom_override_and_cached_plan(self):
        vm=Interpreter(allow_extensions=True);vm.variables['p']=Pair('x',1);vm.variables['saved']=vm.functions['string']
        plan=vm.prepare('R=String(P);Q=Saved(P);')
        vm.execute_prepared(plan);self.assertEqual((vm.variables['r'],vm.variables['q']),('КлючИЗначение','КлючИЗначение'))
        vm.register_function('String',lambda value:'custom')
        vm.execute_prepared(plan);self.assertEqual((vm.variables['r'],vm.variables['q']),('custom','КлючИЗначение'))

    def test_argument_effects_replacement_and_lifetime_guards(self):
        for mode in ('named','captured','close'):
            vm=Interpreter(allow_extensions=True);pair=Pair('x',1);vm.variables['saved']=vm.functions['string'];seen=[]
            def effect():
                seen.append('argument')
                if mode=='close':vm.close()
                else:vm.functions['string'].function=lambda value:seen.append('replacement')
                return pair
            vm.register_function('Effect',effect)
            with self.subTest(mode=mode),self.assertRaises(BoundaryViolation):vm.execute(('Saved' if mode=='captured' else 'String')+'(Effect());')
            self.assertEqual(seen,['argument'])

    def test_policy_revocation_and_class_rebinding_do_not_grant_authority(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        from yadinassi.execution.codegen import direct_collections as collections
        vm=Interpreter(allow_extensions=True);pair=Pair('x',1);vm.variables['p']=pair
        context=make_boundary(vm);context.start();invoke=context.resolve_callable(vm.functions['string'])
        context.policy=lambda operation,name:False
        with self.assertRaises(BoundaryViolation):invoke(pair)
        context.policy=None;context.revoke()
        with self.assertRaises(BoundaryViolation):invoke(pair)
        class Fake:
            def __str__(self):return 'foreign'
        with patch.object(collections,'_MapEntry',Fake):
            self.assertEqual(vm.execute('String(P)'),'КлючИЗначение')
            vm.variables['fake']=Fake();self.assertEqual(vm.execute('String(Fake)'),'foreign')

    def test_subclass_and_foreign_values_keep_existing_host_semantics(self):
        seen=[]
        class Child(Pair):
            def __str__(self):seen.append('child');return 'child'
        vm=Interpreter();vm.variables['p']=Child('x',1)
        self.assertEqual(vm.execute('String(P)'),'child');self.assertEqual(seen,['child'])

if __name__=='__main__':unittest.main()
