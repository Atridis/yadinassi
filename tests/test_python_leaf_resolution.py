import unittest
from types import SimpleNamespace
from yadinassi.python_translation_expressions import ExpressionPlan, UnsupportedExpression


def drain(generator):
    try:
        next(generator)
    except StopIteration as result:
        return result.value
    raise AssertionError('unexpected suspension')


class LeafResolutionTests(unittest.TestCase):
    def execution(self):
        self.events=[]
        self.node=object()
        self.available=True
        def resolve(node):
            self.events.append('resolve')
            return (self.node,lambda vm,node:self.events.append('value') or 7) if self.available else None
        vm=SimpleNamespace(compiled_before=lambda n:self.events.append('before'),
                           compiled_after=lambda n,v:self.events.append('after') or v,
                           compiled_exception=lambda n,e:self.events.append('exception') or e)
        return ExpressionPlan({},(),'').bind(vm,guard=lambda n:self.events.append('guard'),access=None,leaf_resolve=resolve)

    def test_each_entry_resolves_once_and_preserves_hooks(self):
        for method in ('evaluate','leaf_id','leaf'):
            with self.subTest(method=method):
                execution=self.execution()
                result=getattr(execution,method)(self.node if method!='leaf_id' else id(self.node))
                if method=='evaluate':result=drain(result)
                self.assertEqual(result,7)
                self.assertEqual(self.events,['resolve','before','guard','value','after'])
                self.available=False
                with self.assertRaises(UnsupportedExpression):
                    result=getattr(execution,method)(self.node if method!='leaf_id' else id(self.node))
                    if method=='evaluate':drain(result)

    def test_guard_failure_after_before_has_no_value_effect(self):
        execution=self.execution()
        def guard(node):
            self.events.append('guard')
            raise PermissionError('revoked')
        execution.guard=guard
        with self.assertRaisesRegex(PermissionError,'revoked'):drain(execution.evaluate(self.node))
        self.assertEqual(self.events,['resolve','before','guard','exception'])

    def test_bound_callee_still_runs_guards(self):
        execution=self.execution().with_bound_callee(self.node,11)
        self.events.clear()
        self.assertEqual(drain(execution.evaluate(self.node)),11)
        self.assertEqual(self.events,['resolve','before','guard','after'])
