"""Leaf instrumentation is opt-in; disabling it never disables admission."""
import unittest
from types import SimpleNamespace
from yadinassi.compiled_backend import Engine
from yadinassi.syntax.parser import parse

class LeafStatsTests(unittest.TestCase):
    def test_leaf_default_and_detailed_keep_guards_and_result(self):
        node=parse('r=7;')[0].value
        for detailed in (False,True):
            events=[]
            engine=SimpleNamespace(DETAILED_INLINE_STATS=detailed,stats={},vm=object(),_active_frames=0,
                execution_view=lambda value:value,
                _verify_active_plans=lambda:events.append('active'),
                verify_node=lambda value:events.append(('verify',value)),
                _python_leaf_operation=lambda value:(None,lambda vm,view:events.append('leaf') or 7))
            with self.assertRaises(StopIteration) as result:
                next(Engine._run_python_node(engine,node))
            self.assertEqual(result.exception.value,7)
            self.assertEqual(events,['active',('verify',node),'leaf'])
            self.assertEqual(engine._active_frames,0)
            self.assertEqual(engine.stats,{'python_translated_node_kinds':{'Literal':1}} if detailed else {})

    def test_leaf_denial_prevents_effect_even_without_instrumentation(self):
        node=parse('r=7;')[0].value
        for detailed in (False,True):
            events=[]
            def reject(value):raise PermissionError('denied')
            engine=SimpleNamespace(DETAILED_INLINE_STATS=detailed,stats={},vm=object(),_active_frames=0,
                execution_view=lambda value:value,_verify_active_plans=lambda:None,
                verify_node=reject,_python_leaf_operation=lambda value:(None,lambda vm,view:events.append('effect')))
            with self.assertRaises(PermissionError):next(Engine._run_python_node(engine,node))
            self.assertEqual(events,[])
            self.assertEqual(engine.stats,{})
            self.assertEqual(engine._active_frames,0)
