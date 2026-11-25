"""Bounded fixed snapshots of direct values, with canonical retained state."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import BSLFixedArray
from yadinassi.collections.structures import BSLFixedStructure

class DirectFixedTests(unittest.TestCase):
    def test_routes_snapshot_aliases_and_repeated_branches(self):
        text='A=New Array;A.Add(1);S=New Structure("Child",A);R=New Array;R.Add(A);R.Add(A);R.Add(S);F=New FixedArray(R);G=New FixedStructure(S);A[0]=2;S.Child=3;'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            if route=='source':vm.execute(text)
            elif route=='ast':vm.execute_program(parse(text))
            else:vm.execute_prepared(vm.prepare(text))
            f=vm.variables['f'];g=vm.variables['g']
            self.assertIs(type(f),BSLFixedArray);self.assertIs(type(g),BSLFixedStructure)
            self.assertIsNot(f.items[0],f.items[1]);self.assertEqual(f.items[0].items,(Decimal(1),))
            self.assertIs(f.items[2],vm.variables['s']);self.assertIs(g.get('Child'),vm.variables['a'])
            self.assertEqual(vm.execute('G.Child[0]'),2)

    def test_cycles_reject_atomically_and_shallow_cycles_remain_aliases(self):
        vm=Interpreter();vm.execute('A=New Array;A.Add(A);F=7;Try F=New FixedArray(A);Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught']);self.assertEqual(vm.variables['f'],7)
        vm.execute('S=New Structure("Self");S.Self=S;G=New FixedStructure(S);')
        self.assertIs(vm.variables['g'].get('Self'),vm.variables['s'])

    def test_readonly_members_indexes_and_private_storage(self):
        vm=Interpreter();vm.execute('A=New Array;A.Add(1);F=New FixedArray(A);G=New FixedStructure("X",1);')
        for text in ('F[0]=9','F.Add(9)','G.X=9','G["X"]=9','G.Insert("Y",2)'):
            with self.assertRaises(BSLError):vm.execute(text)
        self.assertEqual(vm.execute('F[0]'),1);self.assertEqual(vm.execute('G.X'),1)
        for text in ('F.items','G._items'):
            with self.assertRaises(BSLError):vm.execute(text)

    def test_constructor_identity_checked_before_and_after_arguments(self):
        for name in ('FixedArray','FixedStructure'):
            vm=Interpreter(allow_extensions=True);seen=[];vm.register_type(name,lambda *args:seen.append('factory'))
            vm.register_function('Effect',lambda:seen.append('argument'))
            with self.assertRaises(BoundaryViolation):vm.execute('New '+name+'(Effect());')
            self.assertEqual(seen,[])
            vm=Interpreter(allow_extensions=True);original=vm.types[name.casefold()]
            def mutate():original.function=lambda *args:seen.append('replacement');return []
            vm.register_function('Mutate',mutate)
            with self.assertRaises(BoundaryViolation):vm.execute('New '+name+'(Mutate());')
            self.assertEqual(seen,[])

    def test_runtime_close_during_constructor_arguments(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Close',lambda:vm.close())
        with self.assertRaises(BoundaryViolation):vm.execute('F=New FixedStructure("X",Close());')
        self.assertNotIn('f',vm.variables)

    def test_source_session_keeps_canonical_snapshot_and_readonly_protocol(self):
        from test_source_session_types import SourceSessionTypesTests
        owner=SourceSessionTypesTests()
        try:
            app=owner.run_source('A=New Array;A.Add(1);F=New FixedArray(A);A[0]=2;S=New FixedStructure("Items",F);SessionParameters.State=S;If S.Items[0]<>1 Then Raise "snapshot";EndIf;Try S.Items[0]=3;Except EndTry;Try S.Items=3;Except EndTry;','<v8:Type>v8:FixedStructure</v8:Type>')
            result=app.session_parameters._values['state'];self.assertIs(type(result),BSLFixedStructure)
            self.assertEqual(result.get('Items').items,(Decimal(1),))
        finally:owner.doCleanups()

    def test_canonical_array_root_freezes_nested_direct_arrays(self):
        vm=Interpreter();vm.execute('A=New Array;A.Add(1);R=StrSplit("x",",");R.Add(A);F=New FixedArray(R);A[0]=9;')
        self.assertIs(type(vm.variables['f'].items[1]),BSLFixedArray)
        self.assertEqual(vm.execute('F[1][0]'),1)
        vm.execute('A.Add(R);Saved=7;Try Saved=New FixedArray(R);Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught']);self.assertEqual(vm.variables['saved'],7)

    def test_existing_policy_event_and_post_policy_binding_check(self):
        from yadinassi.execution.direct.python_direct_services import ServicesBoundary
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
        class Boundary(ServicesBoundary,BoundaryContext):pass
        for mode in ('deny','mutate','permission'):
            vm=Interpreter(allow_extensions=True);events=[];factory=vm.types['fixedarray']
            def policy(operation,name):
                events.append((operation,name))
                if mode=='mutate':factory.function=lambda *args:None
                return mode!='deny'
            context=Boundary(policy=policy);context.vm=vm;context.start()
            bound=context.resolve_service('new:fixedarray')
            with patch('yadinassi.execution.direct.python_direct_fixed.construct',side_effect=PermissionError('denied')) as construct:
                with self.assertRaises(BoundaryViolation):bound([])
                self.assertEqual(construct.call_count,1 if mode=='permission' else 0)
            self.assertEqual(events,[('call_value',factory.name.casefold())])
