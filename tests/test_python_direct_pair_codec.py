"""Direct detached iterator pairs reuse the native-backed bounded codec."""
from decimal import Decimal
from unittest.mock import patch
import unittest
from yadinassi import Interpreter
from yadinassi.formats.storage import serialization
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _DIRECT_MAP_ENTRY_TYPE as Pair
from yadinassi.collections.structures import BSLKeyAndValue
from yadinassi.syntax.parser import parse
from tests import test_serialization_native as native

class DirectPairCodecTests(unittest.TestCase):
    def test_native_pair_payload_routes_and_roundtrip_no_vm(self):
        native.NativeEvidenceTests.setUpClass(); evidence=native.NativeEvidenceTests()
        for kind,constructor,key in [('structure','New Structure("Ключ",7)','Ключ'),('map','New Map','ключ')]:
            for route in ('source','ast','prepared','execute','eval','captured'):
                vm=Interpreter(allow_extensions=True);vm.execute('S='+constructor+';S["'+key+'"]=7;For Each P In S Do EndDo;')
                vm.variables['saved']=vm.functions['valuetostringinternal']
                code='R=ValueToStringInternal(P);'
                with self.subTest(kind=kind,route=route):
                    if route=='source':vm.execute(code)
                    elif route=='ast':vm.execute_program(parse(code))
                    elif route=='prepared':vm.execute_prepared(vm.prepare(code))
                    elif route=='execute':vm.execute('Var R;Execute("'+code+'");')
                    elif route=='eval':vm.execute('R=Eval("ValueToStringInternal(P)");')
                    else:vm.execute('R=Saved(P);')
                payload=vm.variables['r']
                evidence.assert_codec_payload(payload,evidence.native('collections','internal.key-and-value.'+kind+'.payload'))
                restored=serialization.value_from_string_internal(payload)
                self.assertIs(type(restored),BSLKeyAndValue)
                self.assertEqual((restored.key,restored.value),(key,Decimal(7)))
                self.assertEqual(serialization.value_to_string_internal(restored),payload)

    def test_exact_storage_does_not_invoke_pair_or_payload_hooks(self):
        seen=[]
        def hook(*args):seen.append('hook');raise AssertionError('hook')
        class Evil:
            __str__=__repr__=__iter__=__eq__=hook
        vm=Interpreter();vm.variables['p']=Pair('x',Decimal(1))
        with patch.object(Pair,'__getattribute__',hook),patch.object(Pair,'key',property(hook),create=True):
            self.assertIn('"S","x"',vm.execute('ValueToStringInternal(P)'))
        for p in (Pair(Evil(),1),Pair('x',Evil())):
            vm.variables['p']=p
            with self.assertRaises(BSLError):vm.execute('ValueToStringInternal(P)')
        self.assertEqual(seen,[])

    def test_foreign_subclass_forged_storage_and_no_reflection(self):
        class Child(Pair):pass
        vm=Interpreter()
        for value in (Child('x',Decimal(1)),object()):
            vm.variables['p']=value
            with self.assertRaises(BSLError):vm.execute('ValueToStringInternal(P)')
        p=Pair('x',Decimal(1));vars(p)['extra']=0;vm.variables['p']=p
        with self.assertRaises(BSLError):vm.execute('ValueToStringInternal(P)')
        seen=[]
        class Key:
            def __hash__(self):return hash('key')
            def __eq__(self,other):seen.append('eq');raise AssertionError('eq')
        vars(p).clear();vars(p)[Key()]=1;vars(p)['value']=2
        with self.assertRaises(BSLError):vm.execute('ValueToStringInternal(P)')
        self.assertEqual(seen,[])

    def test_nested_cycles_and_resource_budgets_recover(self):
        vm=Interpreter();p=Pair('x',None);object.__setattr__(p,'value',p);vm.variables['p']=p
        with self.assertRaisesRegex(BSLError,'циклические'):vm.execute('ValueToStringInternal(P)')
        chain=Pair('x',Decimal(1))
        for _ in range(8):chain=Pair('x',chain)
        vm.variables['p']=chain
        for limit in ('_MAX_DEPTH','_MAX_NODES','_MAX_TEXT'):
            with patch.object(serialization,limit,3),self.assertRaises(BSLError):vm.execute('ValueToStringInternal(P)')
        vm.variables['p']=Pair('x',Decimal(1));self.assertIn('"N",1',vm.execute('ValueToStringInternal(P)'))

    def test_cycle_through_list_aliases_undefined_and_public_rebinding(self):
        from yadinassi.execution.codegen import experimental_naked_collections as collections
        vm=Interpreter(allow_extensions=True);items=[];p=Pair('x',items);items.append(p);vm.variables['p']=p
        with self.assertRaisesRegex(BSLError,'циклические'):vm.execute('ValueToStringInternal(P)')
        shared=Pair('nested',None);vm.variables['p']=Pair(shared,shared)
        payload=vm.execute('ValueToStringInternal(P)')
        restored=serialization.value_from_string_internal(payload)
        self.assertIsNot(restored.key,restored.value)
        self.assertIsNone(restored.key.value);self.assertIsNone(restored.value.value)
        class Foreign:pass
        with patch.object(collections,'_MapEntry',Foreign):
            self.assertEqual(vm.execute('ValueToStringInternal(P)'),payload)
            vm.variables['foreign']=Foreign()
            with self.assertRaises(BSLError):vm.execute('ValueToStringInternal(Foreign)')
        # Captured support is deliberately not widened to all direct containers.
        vm.variables.update(saved=vm.functions['valuetostringinternal'],raw=[])
        with self.assertRaises(BSLError):vm.execute('Saved(Raw)')

    def test_cached_custom_capture_and_argument_lifetime_guards(self):
        vm=Interpreter(allow_extensions=True);vm.variables.update(p=Pair('x',Decimal(1)),saved=vm.functions['valuetostringinternal'])
        plan=vm.prepare('R=ValueToStringInternal(P);Q=Saved(P);');vm.execute_prepared(plan)
        payload=vm.variables['r'];self.assertEqual(payload,vm.variables['q'])
        vm.register_function('ValueToStringInternal',lambda value:'custom');vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['q']),('custom',payload))
        for mode in ('replace','close'):
            for name in ('ValueToStringInternal','Saved'):
                vm=Interpreter(allow_extensions=True);vm.variables['saved']=vm.functions['valuetostringinternal'];seen=[]
                def effect():
                    seen.append('arg')
                    if mode=='close':vm.close()
                    else:vm.functions['valuetostringinternal'].function=lambda value:seen.append('replacement')
                    return Pair('x',Decimal(1))
                vm.register_function('Effect',effect)
                with self.subTest(mode=mode,name=name),self.assertRaises(BoundaryViolation):vm.execute(name+'(Effect())')
                self.assertEqual(seen,['arg'])

    def test_retained_callable_policy_and_revocation(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=Interpreter(allow_extensions=True);context=make_boundary(vm);context.start()
        invoke=context.resolve_callable(vm.functions['valuetostringinternal']);p=Pair('x',Decimal(1))
        context.policy=lambda operation,name:operation!='call_value'
        with self.assertRaises(BoundaryViolation):invoke(p)
        context.policy=None;context.revoke()
        with self.assertRaises(BoundaryViolation):invoke(p)
