import gc
import unittest
import weakref
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.errors import BSLError
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse


def finish(frame):
    try:
        next(frame)
    except StopIteration as done:
        return done.value
    raise AssertionError('unexpected suspension')


class PreparedRoutineMetadataTests(unittest.TestCase):
    def vm(self):
        vm = Interpreter(execution_backend='compiled-strict'); self.addCleanup(vm.close)
        return vm

    def test_static_layout_and_no_call_time_label_walk(self):
        vm = self.vm(); e = vm._compiled()
        routine = parse('Function F(Val A, B=2) Return A+B;EndFunction')[0]
        e.prepare([routine]); view = e.execution_view(routine)
        layout = e.routine_call_metadata(view)
        self.assertEqual((layout.required, layout.byref_indexes), (1, (1,)))
        self.assertEqual([p.name for p in layout.parameters], ['a', 'b'])
        self.assertEqual(len(layout.defaults), 1)
        argument = parse('x=3;')[0].value
        with patch('yadinassi.runtime.validate_labels', side_effect=AssertionError('hot AST walk')):
            for _ in range(3):
                self.assertEqual(finish(vm.call_routine(routine, [argument], vm, require_value=True)), 5)
        self.assertEqual(e._routine_metadata_slots, layout.slots)

    def test_shared_parameter_layouts_are_charged_and_roll_back(self):
        vm = self.vm(); e = vm._compiled(); effects = []
        vm.register_function('Host', lambda: effects.append(1))
        template = parse('Function F(x) Return x;EndFunction')[0]
        template.parameters *= 32
        routines = [ast.Routine(template.token, 'F'+str(i), template.parameters,
                                True, False, template.body) for i in range(16)]
        e.MAX_REGISTRY_ENTRIES = 300
        with self.assertRaisesRegex(CompiledUnsupported, 'routine metadata registry budget'):
            vm.execute_program(parse('Host();') + routines)
        self.assertEqual(effects, [])
        self.assertEqual(e._routine_metadata_slots, 0)
        self.assertFalse(e._nodes); self.assertFalse(e._owned.versions)

    def test_owner_version_is_rechecked_after_each_actual(self):
        vm = self.vm(); effects = []
        def first():
            effects.append('first'); e = vm._compiled()
            view = e.execution_view(vm.routines['f']); e._owned.versions.pop(id(view))
            return Decimal(1)
        vm.register_function('First', first)
        vm.register_function('Second', lambda: effects.append('second') or Decimal(2))
        with self.assertRaises(CompiledUnsupported):
            vm.execute('Function F(Val x,Val y) Return x+y;EndFunction r=F(First(),Second());')
        self.assertEqual(effects, ['first'])

    def test_foreign_owner_default_is_admitted_in_caller(self):
        caller, owner = self.vm(), self.vm()
        routine = parse('Function F(Val x=1) Return x;EndFunction')[0]
        # Embedding AST exercises caller ownership; ordinary parsed defaults
        # deliberately accept only literals.
        routine.parameters[0].default = ast.Name(routine.token, 'CallerValue')
        owner._compiled().prepare([routine]); caller.variables['callervalue'] = Decimal(7)
        self.assertEqual(finish(caller.call_routine(routine, [], owner, require_value=True)), 7)
        default = owner._compiled().routine_call_metadata(owner._compiled().execution_view(routine)).defaults[0]
        self.assertTrue(caller._compiled().has_node(default))
        caller._compiled().verify_node(default)

    def test_label_diagnostic_keeps_arity_precedence_for_direct_routine(self):
        vm = self.vm(); routine = parse('Function F(x) Return x;EndFunction')[0]
        routine.body = [ast.Goto(routine.token, 'missing')]
        vm._compiled().prepare([routine])
        with self.assertRaises(TypeError):
            finish(vm.call_routine(routine, [], vm, require_value=True))
        with self.assertRaises(BSLError) as error:
            finish(vm.call_routine(routine, [ast.Literal(routine.token, Decimal(1))], vm, require_value=True))
        self.assertIn('missing', str(error.exception))
        self.assertEqual(error.exception.line, routine.token.line)

    def test_release_drops_layout_and_charge(self):
        vm = self.vm(); e = vm._compiled(); routine = parse('Function F(x=1) Return x;EndFunction')[0]
        e.prepare([routine]); layout = e.routine_call_metadata(e.execution_view(routine))
        reference = weakref.ref(layout); self.assertGreater(e._routine_metadata_slots, 0)
        e.release(); del layout; gc.collect()
        self.assertIsNone(reference()); self.assertEqual(e._routine_metadata_slots, 0)

    def test_snapshot_original_parameter_mutation_does_not_change_layout(self):
        vm = self.vm(); e = vm._compiled(); routine = parse('Function F(Val x=1) Return x;EndFunction')[0]
        e.prepare([routine]); routine.parameters[0].name = 'changed'
        routine.parameters[0].default.value = Decimal(99)
        self.assertEqual(finish(vm.call_routine(routine, [], vm, require_value=True)), 1)

    def test_nested_admission_same_layout_is_charged_once_and_outer_failure_rolls_back(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                vm = self.vm(); e = vm._compiled()
                routine = parse('Function F(x=1) Return x;EndFunction')[0]
                lower = e._prepare_python_unit; entered = False
                def nested(*args, **kwargs):
                    nonlocal entered
                    if not entered:
                        entered = True; e.prepare_node(routine)
                        if fail: raise CompiledUnsupported(None, 'outer rollback probe')
                    return lower(*args, **kwargs)
                with patch.object(e, '_prepare_python_unit', nested):
                    if fail:
                        with self.assertRaises(CompiledUnsupported): e.prepare([routine])
                    else: e.prepare([routine])
                charged = sum(p.routine.slots for p in e._nodes.values() if p.routine is not None)
                self.assertEqual(e._routine_metadata_slots, charged)
                if fail: self.assertEqual(charged, 0); self.assertFalse(e._nodes)
