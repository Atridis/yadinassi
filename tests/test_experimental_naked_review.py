"""Independent adversarial regressions for experimental service admission."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from yadinassi.experimental_naked_collections import prepare
from yadinassi.values import HostFunction
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation,HostMembers

class NakedReviewRegressions(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});env.start();self.addCleanup(env.stop)
    def test_grouped_readable_member_does_not_grant_call_capability(self):
        events=[];obj=SimpleNamespace(callback=lambda:events.append('called'))
        ctx=BoundaryContext(members=[HostMembers(obj,readable=('callback',))])
        with self.assertRaises(BoundaryViolation):
            prepare('(obj.callback)();',repairs=('service_boundaries',)).run({'obj':obj},context=ctx)
        self.assertEqual(events,[])
    def test_service_return_does_not_implicitly_grant_callable_capability(self):
        events=[]
        def get():events.append('get');return lambda:events.append('called')
        ctx=BoundaryContext(services={'get':get})
        with self.assertRaisesRegex(TypeError,'Значение не является функцией'):
            prepare('result=(Get())();',repairs=('service_boundaries',)).run(context=ctx)
        self.assertNotIn('called',events)
    def test_explicit_callable_identity_is_allowed(self):
        events=[]
        def callback(x):events.append(x);return x+1
        ctx=BoundaryContext(services={'get':lambda:HostFunction('chosen',callback)})
        result=prepare('result=(Get())(3);',repairs=('service_boundaries',)).run(context=ctx)
        self.assertEqual(result['result'],4);self.assertEqual(events,[3])
    def test_unknown_callable_denied_before_argument_effect(self):
        events=[]
        ctx=BoundaryContext(services={'get':lambda:lambda x:x,'arg':lambda:events.append('argument')})
        with self.assertRaisesRegex(TypeError,'Значение не является функцией'):
            prepare('result=(Get())(Arg());',repairs=('service_boundaries',)).run(context=ctx)
        self.assertEqual(events,[])
    def test_explicit_callable_revocation_after_effect_no_replay(self):
        events=[]
        def callback():events.append('called');ctx.revoke();return 7
        ctx=BoundaryContext(services={'get':lambda:HostFunction('chosen',callback)})
        program=prepare('result=(Get())();after=1;',repairs=('service_boundaries',))
        with self.assertRaises(BoundaryViolation):program.run(context=ctx)
        self.assertEqual(events,['called']);self.assertNotIn('after',program.last_state)
    def test_explicit_callable_policy_checked(self):
        events=[]
        def callback():events.append('called')
        ctx=BoundaryContext(services={'get':lambda:HostFunction('chosen',callback)},
                            policy=lambda operation,name:operation!='call_value')
        with self.assertRaises(BoundaryViolation):
            prepare('result=(Get())();',repairs=('service_boundaries',)).run(context=ctx)
        self.assertEqual(events,[])
    def test_grouped_registered_member_is_allowed(self):
        events=[];obj=SimpleNamespace(callback=lambda:events.append('called'))
        ctx=BoundaryContext(members=[HostMembers(obj,callable=('callback',))])
        prepare('(obj.callback)();',repairs=('service_boundaries',)).run({'obj':obj},context=ctx)
        self.assertEqual(events,['called'])
    def test_map_entry_value_reads_and_live_values_with_boundaries(self):
        source='m=New Map;m.Insert("a",1);m.Insert("b",2);s=0;For Each p In m Do s=s+p.Value;m.Insert("b",9);EndDo;result=s;'
        program=prepare(source,repairs=('service_boundaries','authority_checkpoints','typed_map_keys','byref_routines'))
        self.assertEqual(program.run(context=BoundaryContext())['result'],10)
    def test_map_entry_mutation_preserves_partial_sum_not_boundary_failure(self):
        source='m=New Map;m.Insert("a",1);m.Insert("b",2);s=0;For Each p In m Do s=s+p.Value;m.Insert("c",3);EndDo;'
        program=prepare(source,repairs=('service_boundaries','authority_checkpoints','typed_map_keys','byref_routines'))
        with self.assertRaises(RuntimeError):program.run(context=BoundaryContext())
        self.assertEqual(program.last_state['s'],1)
    def test_map_entry_does_not_allow_host_namespace_or_writes(self):
        obj=SimpleNamespace(key='a',value=7)
        with self.assertRaises(BoundaryViolation):
            prepare('r=obj.Value;',repairs=('service_boundaries',)).run({'obj':obj},context=BoundaryContext())
        source='m=New Map;m.Insert("a",1);For Each p In m Do p.Value=9;EndDo;'
        with self.assertRaises(BoundaryViolation):prepare(source,repairs=('service_boundaries',)).run(context=BoundaryContext())
    def test_error_repair_rejects_missing_position_support_before_execution(self):
        from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax
        with patch('yadinassi.experimental_naked_errors.source_mapping_supported',return_value=False):
            with self.assertRaisesRegex(UnsupportedNakedSyntax,'3.11'):
                prepare('result=1/0;',repairs=('error_boundaries',))
            self.assertEqual(prepare('result=7;').run()['result'],7)
    def test_service_only_and_byref_registered_routines(self):
        source='Function F(x) Return x+1;EndFunction result=F(3);'
        for flags in (('service_boundaries',),('service_boundaries','byref_routines')):
            self.assertEqual(prepare(source,repairs=flags).run(context=BoundaryContext())['result'],4)
    def test_reassigned_routine_does_not_grant_host_call_before_args(self):
        source='Function F(x) Return x;EndFunction F=Get();result=F(Arg());'
        for flags in (('service_boundaries',),('service_boundaries','byref_routines')):
            events=[]
            def unauthorized(x):events.append('called');return x
            ctx=BoundaryContext(services={'get':lambda:unauthorized,'arg':lambda:events.append('argument')})
            result=prepare(source,repairs=flags).run(context=ctx)
            self.assertIsNone(result['result'])
            self.assertEqual(events,['argument'])
