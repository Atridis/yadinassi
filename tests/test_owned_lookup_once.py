import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.syntax.parser import parse
from yadinassi import owned_syntax

class OwnedLookupOnceTests(unittest.TestCase):
    def admitted(self):
        vm=Interpreter(execution_backend='compiled-strict');node=parse('r=1;')[0].value
        engine=vm._compiled();engine.prepare_node(node)
        return engine,node,engine._owned.existing(node)

    def test_origin_and_owned_views_both_check_current_plan(self):
        engine,origin,view=self.admitted()
        engine.verify_node(origin);engine.verify_node(view)
        origin.value=Decimal(2)
        engine.verify_node(origin);engine.verify_node(view)
        self.assertEqual(view.value,1)
        engine._owned.versions.pop(id(view))
        for node in (origin,view):
            with self.assertRaises(CompiledUnsupported):engine.verify_node(node)

    def test_foreign_view_not_authorized_by_foreign_plan(self):
        engine,_,view=self.admitted();other,_,_=self.admitted()
        other._nodes[id(view)]=engine._nodes[id(view)]
        with self.assertRaises(CompiledUnsupported):other.verify_node(view)

    def test_current_global_owned_identity_is_not_cached(self):
        engine,_,view=self.admitted();engine.verify_node(view)
        saved=owned_syntax._ORIGINS.pop(id(view))
        try:
            with self.assertRaises(CompiledUnsupported):engine.verify_node(view)
        finally:owned_syntax._ORIGINS[id(view)]=saved
        engine.verify_node(view)

    def test_version_origin_mismatch_not_cached(self):
        engine,origin,view=self.admitted();engine.verify_node(view)
        saved=engine._owned.versions[id(view)]
        engine._owned.versions[id(view)]=(object(),view)
        try:
            with self.assertRaises(CompiledUnsupported):engine.verify_node(view)
        finally:engine._owned.versions[id(view)]=saved
        engine.verify_node(view)

    def test_mutable_contract_keeps_origin_mutation_rejection(self):
        vm=Interpreter(execution_backend='compiled-strict',compiled_ast_contract='mutable')
        node=parse('r=1;')[0].value;engine=vm._compiled()
        engine.FORCE_PYTHON_TRANSLATION=False  # Explicit legacy mutable compatibility oracle.
        engine.prepare_node(node)
        engine.verify_node(node);node.value=Decimal(2)
        with self.assertRaises(CompiledUnsupported):engine.verify_node(node)

    def test_full_origin_monitor_still_rechecks_before_owned_execution(self):
        vm=Interpreter(execution_backend='compiled-strict');engine=vm._compiled()
        engine.ORIGIN_MUTATION_MONITOR=True  # Explicit compatibility monitor, not default.
        origin=parse('r=1;')[0].value;engine.prepare_node(origin)
        view=engine._owned.existing(origin);engine.verify_node(view)
        origin.value=Decimal(2)
        with self.assertRaises(CompiledUnsupported):engine.verify_node(view)
