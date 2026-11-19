from yadinassi.errors import BSLRuntimeError
'Independent adversarial regressions for experimental service admission.'
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests.direct_boundary_compile import compile_boundary
from yadinassi.values import HostFunction
from yadinassi.experimental_naked_boundaries import BoundaryContext, BoundaryViolation, HostMembers

class NakedReviewRegressions(unittest.TestCase):

    def test_grouped_readable_member_does_not_grant_call_capability(self):
        events = []
        obj = SimpleNamespace(callback=lambda: events.append('called'))
        ctx = BoundaryContext(members=[HostMembers(obj, readable=('callback',))])
        with self.assertRaises(BoundaryViolation):
            compile_boundary('(obj.callback)();').run({'obj': obj}, context=ctx)
        self.assertEqual(events, [])

    def test_service_return_does_not_implicitly_grant_callable_capability(self):
        events = []

        def get():
            events.append('get')
            return lambda: events.append('called')
        ctx = BoundaryContext(services={'get': get})
        with self.assertRaisesRegex(BSLRuntimeError, 'Значение не является функцией'):
            compile_boundary('result=(Get())();').run({}, context=ctx)
        self.assertNotIn('called', events)

    def test_explicit_callable_identity_is_allowed(self):
        events = []

        def callback(x):
            events.append(x)
            return x + 1
        ctx = BoundaryContext(services={'get': lambda: HostFunction('chosen', callback)})
        result = compile_boundary('result=(Get())(3);').run({}, context=ctx)
        self.assertEqual(result['result'], 4)
        self.assertEqual(events, [3])

    def test_unknown_callable_denied_before_argument_effect(self):
        events = []
        ctx = BoundaryContext(services={'get': lambda: lambda x: x, 'arg': lambda: events.append('argument')})
        with self.assertRaisesRegex(BSLRuntimeError, 'Значение не является функцией'):
            compile_boundary('result=(Get())(Arg());').run({}, context=ctx)
        self.assertEqual(events, [])

    def test_explicit_callable_revocation_after_effect_no_replay(self):
        events = []

        def callback():
            events.append('called')
            ctx.revoke()
            return 7
        ctx = BoundaryContext(services={'get': lambda: HostFunction('chosen', callback)})
        program = compile_boundary('result=(Get())();after=1;')
        with self.assertRaises(BoundaryViolation):
            program.run({}, context=ctx)
        self.assertEqual(events, ['called'])
        self.assertNotIn('after', program.last_state)

    def test_explicit_callable_policy_checked(self):
        events = []

        def callback():
            events.append('called')
        ctx = BoundaryContext(services={'get': lambda: HostFunction('chosen', callback)}, policy=lambda operation, name: operation != 'call_value')
        with self.assertRaises(BoundaryViolation):
            compile_boundary('result=(Get())();').run({}, context=ctx)
        self.assertEqual(events, [])

    def test_grouped_registered_member_is_allowed(self):
        events = []
        obj = SimpleNamespace(callback=lambda: events.append('called'))
        ctx = BoundaryContext(members=[HostMembers(obj, callable=('callback',))])
        compile_boundary('(obj.callback)();').run({'obj': obj}, context=ctx)
        self.assertEqual(events, ['called'])

    def test_map_entry_value_reads_and_live_values_with_boundaries(self):
        source = 'm=New Map;m.Insert("a",1);m.Insert("b",2);s=0;For Each p In m Do s=s+p.Value;m.Insert("b",9);EndDo;result=s;'
        program = compile_boundary(source)
        self.assertEqual(program.run({}, context=BoundaryContext())['result'], 10)

    def test_map_entry_mutation_preserves_partial_sum_not_boundary_failure(self):
        source = 'm=New Map;m.Insert("a",1);m.Insert("b",2);s=0;For Each p In m Do s=s+p.Value;m.Insert("c",3);EndDo;'
        program = compile_boundary(source)
        with self.assertRaisesRegex(BSLRuntimeError, 'Изменение состава соответствия'):
            program.run({}, context=BoundaryContext())
        self.assertEqual(program.last_state['s'], 1)

    def test_map_entry_does_not_allow_host_namespace_or_writes(self):
        obj = SimpleNamespace(key='a', value=7)
        with self.assertRaises(BoundaryViolation):
            compile_boundary('r=obj.Value;').run({'obj': obj}, context=BoundaryContext())
        source = 'm=New Map;m.Insert("a",1);For Each p In m Do p.Value=9;EndDo;'
        with self.assertRaises(BoundaryViolation):
            compile_boundary(source).run({}, context=BoundaryContext())

    def test_service_only_and_byref_registered_routines(self):
        source = 'Function F(x) Return x+1;EndFunction result=F(3);'
        self.assertEqual(compile_boundary(source).run({}, context=BoundaryContext())['result'], 4)

    def test_reassigned_routine_does_not_grant_host_call_before_args(self):
        source = 'Function F(x) Return x;EndFunction F=Get();result=F(Arg());'
        events = []

        def unauthorized(x):
            events.append('called')
            return x
        ctx = BoundaryContext(services={'get': lambda: unauthorized, 'arg': lambda: events.append('argument')})
        result = compile_boundary(source).run({}, context=ctx)
        self.assertIsNone(result['result'])
        self.assertEqual(events, ['argument'])
