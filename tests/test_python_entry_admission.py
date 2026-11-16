"""Explicit entry capabilities and fail-before-effects whole-unit role checks."""
import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse


def finish(frame):
    try:
        next(frame)
    except StopIteration as result:
        return result.value
    raise AssertionError('unexpected suspension')


class EntryAdmissionTests(unittest.TestCase):
    def vm(self):
        vm = Interpreter(execution_backend='compiled-strict')
        self.addCleanup(vm.close)
        return vm

    def test_public_visit_admits_nested_statement_without_legacy_execution(self):
        for source, select, expected in (
            ('If True Then x=1;y=2;EndIf;', lambda p: p[0].branches[0][1][0], 1),
            ('While False Do x=3;y=4;EndDo;', lambda p: p[0].body[0], 3),
            ('Try x=5;y=6;Except x=7;EndTry;', lambda p: p[0].body[0], 5),
        ):
            with self.subTest(source=source):
                vm = self.vm(); engine = vm._compiled(); program = parse(source)
                engine.prepare(program); node = select(program)
                self.assertTrue(engine.has_node(node))
                self.assertFalse(engine.has_executable_node(node))
                with patch.object(Interpreter, 'visit_Assign', side_effect=AssertionError('legacy')):
                    vm.visit(node)
                self.assertEqual(vm.variables['x'], expected)
                self.assertEqual(engine.stats['interpreter_fallbacks'], 0)
                self.assertEqual(engine.active_frames, 0)
                # Scheduler release may discard entries; another explicit entry
                # must re-admit normally rather than fall back to AST execution.
                vm.visit(node)
                self.assertEqual(vm.variables['x'], expected)

    def test_internal_lookup_does_not_prepare_missing_entry(self):
        vm = self.vm(); e = vm._compiled(); p = parse('If True Then x=1;y=2;EndIf;')
        e.prepare(p); node = p[0].branches[0][1][0]; before = e.stats['prepared_units']
        with self.assertRaises(CompiledUnsupported): finish(e.run_node(node))
        self.assertEqual(e.stats['prepared_units'], before)
        self.assertNotIn('x', vm.variables)

    def test_entry_budget_failure_rolls_back_without_host_effect(self):
        vm = self.vm(); e = vm._compiled(); seen = []
        vm.register_function('Host', lambda: seen.append(1) or Decimal(2))
        p = parse('If True Then x=Host();y=2;EndIf;'); e.prepare(p)
        node = p[0].branches[0][1][0]
        units, nodes, versions = dict(e._python_units), dict(e._nodes), dict(e._owned.versions)
        e.MAX_INLINE_UNIT_BYTES = 0
        with self.assertRaises(CompiledUnsupported): vm.visit(node)
        self.assertEqual(seen, [])
        self.assertEqual(e._python_units, units); self.assertEqual(e._nodes, nodes)
        self.assertEqual(e._owned.versions, versions)

    def test_role_failures_precede_all_program_effects(self):
        def malformed_target(p): p[1].target = p[1].value
        def omitted_value(p): p[1].value = ast.OmittedArgument(p[1].token)
        def statement_operand(p): p[1].value = ast.Group(p[1].token, p[0])
        def metadata_statement(p): p.append(ast.Parameter(p[1].token, 'p', True))
        for mutate in (malformed_target, omitted_value, statement_operand, metadata_statement):
            with self.subTest(case=mutate.__name__):
                vm = self.vm(); effects = []; vm.register_function('Host', lambda: effects.append(1))
                p = parse('Host();x=1;', 'roles.bsl'); mutate(p)
                e = vm._compiled(); original = dict(e._nodes)
                with self.assertRaises(CompiledUnsupported) as error: vm.execute_program(p)
                self.assertEqual(effects, [])
                self.assertEqual(e._nodes, original)
                self.assertIn('roles.bsl', str(error.exception))

    def test_legal_metadata_defaults_omissions_and_byref_stay_live(self):
        source = ('Procedure F(x, Val y=2) x=x+y;EndProcedure\n'
                  'x=3;F(x,);a=New Array;a.Add(x);F(a[0],4);r=a[0];')
        values = []
        for backend in ('interpreter', 'compiled-strict'):
            vm = Interpreter(execution_backend=backend); self.addCleanup(vm.close)
            vm.execute(source); values.append((vm.variables['x'], vm.variables['r']))
        self.assertEqual(values, [(Decimal(5), Decimal(9))] * 2)

    def test_foreign_metadata_does_not_grant_entry_capability(self):
        vm = self.vm(); other = self.vm(); e = vm._compiled()
        p = parse('If True Then x=1;y=2;EndIf;'); e.prepare(p)
        view = e._owned.existing(p[0].branches[0][1][0])
        other._compiled()._nodes[id(view)] = e._nodes[id(view)]
        self.assertFalse(other._compiled().has_executable_node(view))

    def test_mutable_force_has_explicit_rejection_without_effects(self):
        vm = Interpreter(execution_backend='compiled-strict', compiled_ast_contract='mutable')
        self.addCleanup(vm.close); effects = []
        vm.register_function('Host', lambda: effects.append(1))
        with self.assertRaisesRegex(CompiledUnsupported, 'requires owned snapshot'):
            vm.execute('Host();')
        self.assertEqual(effects, [])

    def test_shared_operand_graph_validates_roles_once_per_unique_node(self):
        from yadinassi import compiled_backend
        from yadinassi.owned_syntax import origin_node
        vm = self.vm(); call = parse('Host(1);')[0].expression
        call.arguments *= 64
        program = [ast.ExpressionStatement(call.token, call) for _ in range(16)]
        original = compiled_backend.validate_node_roles; calls = []
        def validate(node, kind, reject):
            if origin_node(node) is call: calls.append(node)
            return original(node, kind, reject)
        with patch.object(compiled_backend, 'validate_node_roles', validate):
            vm._compiled().prepare(program)
        self.assertEqual(len(calls), 1)
