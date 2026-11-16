import unittest
import weakref
from unittest.mock import patch
from yadinassi import Interpreter, owned_syntax as owned
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.python_translation_expressions import ExpressionPlan
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse


class OwnedDispatchGuards(unittest.TestCase):
    def admitted(self):
        vm = Interpreter(execution_backend='compiled-strict')
        self.addCleanup(vm.close)
        origin = parse('x=1;')[0].value
        engine = vm._compiled(); engine.prepare_node(origin)
        return vm, engine, origin, engine._owned.existing(origin)

    def test_combined_kind_preserves_original_return_and_snapshot(self):
        _, engine, origin, view = self.admitted()
        self.assertIsNone(engine.verify_node(view))
        self.assertIs(engine._verify_owned_identity(view), origin)
        origin.value = 99
        for node in (origin, view):
            self.assertIs(engine.verify_node(node, _return_kind=True), ast.Literal)
        self.assertEqual(view.value, 1)

    def test_pre_hook_resolution_cannot_authorize_post_hook_execution(self):
        for registry_name in ('origins', 'versions', 'plans'):
            with self.subTest(registry=registry_name):
                vm, engine, _, view = self.admitted()
                registry = {'origins': owned._ORIGINS, 'versions': engine._owned.versions,
                            'plans': engine._nodes}[registry_name]
                events = []
                saved = registry[id(view)]
                def before(node):
                    events.append('before'); registry.pop(id(node))
                vm.compiled_before = before
                vm.compiled_after = lambda node, value: events.append('after') or value
                execution = ExpressionPlan({}, (), '').bind(vm,
                    guard=lambda node: engine.verify_node(node, _return_kind=True),
                    access=None, leaf_resolve=engine._python_leaf_operation)
                try:
                    with self.assertRaises(CompiledUnsupported):
                        execution.leaf_id(id(view))
                    self.assertEqual(events, ['before'])
                    self.assertEqual(engine.stats['unsupported_executions'], 1)
                finally:
                    registry[id(view)] = saved

    def test_fabrication_wrong_weakref_and_foreign_version_reject(self):
        _, engine, _, view = self.admitted()
        fake = object.__new__(type(view))
        self.assertIsNone(owned.owned_identity(fake))
        with patch.dict(owned._ORIGINS, {id(fake): weakref.ref(view)}):
            self.assertIsNone(owned.owned_identity(fake))
        with patch.dict(engine._owned.versions, {id(view): (object(), view)}):
            with self.assertRaises(CompiledUnsupported):
                engine.verify_node(view, _return_kind=True)
        _, other, _, _ = self.admitted()
        other._nodes[id(view)] = engine._nodes[id(view)]
        with self.assertRaises(CompiledUnsupported):
            other.verify_node(view, _return_kind=True)

    def test_local_leaf_keeps_precedence_over_resolved_external(self):
        vm, _, _, view = self.admitted()
        events = []
        vm.compiled_before = lambda n: events.append('before')
        vm.compiled_after = lambda n, v: events.append('after') or v
        plan = ExpressionPlan({}, (), '', {id(view): (view, lambda execution: 7)})
        execution = plan.bind(vm, guard=lambda n: events.append('guard'), access=None,
                             leaf_resolve=lambda n: (view, lambda vm, n: 99))
        self.assertEqual(execution.leaf_id(id(view)), 7)
        self.assertEqual(events, ['before', 'guard', 'after'])

    def test_full_monitor_combined_kind_rejects_mutation(self):
        vm = Interpreter(execution_backend='compiled-strict'); self.addCleanup(vm.close)
        engine = vm._compiled(); engine.ORIGIN_MUTATION_MONITOR = True
        origin = parse('x=1;')[0].value; engine.prepare_node(origin)
        view = engine._owned.existing(origin)
        self.assertIs(engine.verify_node(view, _return_kind=True), ast.Literal)
        origin.value = 99
        with self.assertRaises(CompiledUnsupported):
            engine.verify_node(view, _return_kind=True)

    def test_mutable_combined_kind_keeps_fingerprint_check(self):
        vm = Interpreter(execution_backend='compiled-strict', compiled_ast_contract='mutable')
        self.addCleanup(vm.close)
        engine = vm._compiled(); engine.FORCE_PYTHON_TRANSLATION = False
        origin = parse('x=1;')[0].value; engine.prepare_node(origin)
        self.assertIs(engine.verify_node(origin, _return_kind=True), ast.Literal)
        origin.value = 99
        with self.assertRaises(CompiledUnsupported):
            engine.verify_node(origin, _return_kind=True)
