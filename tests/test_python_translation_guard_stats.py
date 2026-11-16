"""Detailed instrumentation must not be an implicit cost or an authority switch."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from yadinassi.compiled_backend import Engine
from yadinassi.python_translation_blocks import Execution
from yadinassi.runtime import Interpreter

class GuardStatsTests(unittest.TestCase):
    def test_default_and_opt_in_preserve_authority_order(self):
        from yadinassi.syntax.parser import parse
        node=parse('x=1;')[0]
        for detailed in (False,True):
            events=[]
            engine=SimpleNamespace(DETAILED_INLINE_STATS=detailed,stats={},
                _verify_active_plans=lambda:events.append('active'),
                verify_node=lambda n:events.append(('node',n)))
            execution=object.__new__(Execution);execution.engine=engine
            execution.guard(node)
            self.assertEqual(events,['active',('node',node)])
            self.assertEqual(engine.stats,{'python_translated_node_kinds':{'Assign':1}} if detailed else {})

    def test_authority_rejection_precedes_statistics(self):
        for detailed in (False,True):
            for failure in ('active','node'):
                events=[]
                def check(name):
                    events.append(name)
                    if name==failure:raise PermissionError(name)
                engine=SimpleNamespace(DETAILED_INLINE_STATS=detailed,stats={},
                    _verify_active_plans=lambda:check('active'),verify_node=lambda n:check('node'))
                execution=object.__new__(Execution);execution.engine=engine
                with self.assertRaises(PermissionError):execution.guard(object())
                self.assertEqual(events,['active'] if failure=='active' else ['active','node'])
                self.assertEqual(engine.stats,{})

    def test_actual_byref_caller_default_and_detailed(self):
        source='Procedure Inc(x) x=x+1;EndProcedure x=0;For i=1 To 20 Do Inc(x);EndDo;'
        for detailed in (False,True):
            with patch.object(Engine,'DETAILED_INLINE_STATS',detailed):
                vm=Interpreter(execution_backend='compiled-strict')
                calls=[];original=Execution.guard
                def counted(execution,node):
                    calls.append(node);return original(execution,node)
                with patch.object(Execution,'guard',counted):vm.execute(source)
                self.assertEqual(vm.variables['x'],20)
                self.assertGreater(len(calls),20)
                stats=vm.compiled_backend_stats
                self.assertEqual(stats.get('interpreter_fallbacks',0),0)
                self.assertEqual(stats['node_coverage'],'observed' if detailed else 'unobserved')
                if detailed:self.assertGreater(stats['python_translated_node_kinds']['Assign'],20)
                else:self.assertNotIn('python_translated_node_kinds',stats)
                self.assertEqual(vm._compiled().active_frames,0)
