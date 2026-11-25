"""Plain array appends have loop boundaries, not per-iteration checks."""
from decimal import Decimal
import ast
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_emitter import compile_owned
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation, HostMembers
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.syntax.parser import parse


def source(n, body='A.Add(i);'):
    return f'For i=1 To {n} Do {body} EndDo;'


def owned(text, *, source_scopes=True):
    return compile_owned(parse(text), source_text=text, source_name='append-loop.bsl',
                         meter_loops=True, source_scopes=source_scopes)


class DirectArrayLoopBoundaryTests(unittest.TestCase):
    def test_public_prepared_calls_do_not_grow_with_iterations(self):
        count = []
        original = BoundaryContext._check

        def counted(context):
            count.append(1)
            original(context)

        for n in (1, 100):
            with self.subTest(n=n):
                vm = Interpreter()
                self.addCleanup(vm.close)
                array = PlainArray([0])
                vm.variables['a'] = array
                plan = vm.prepare(source(n))
                before = len(count)
                with patch.object(BoundaryContext, '_check', counted):
                    vm.execute_prepared(plan)
                calls = len(count) - before
                if n == 1:
                    baseline = calls
                else:
                    self.assertEqual(calls, baseline)
                self.assertEqual(list(array), list(range(n + 1)))
                self.assertEqual(vm.variables['i'], Decimal(n + 1))

    def test_source_scope_native_arm_has_no_checks(self):
        routine = ('Procedure OnStart() A=New Array;' + source(20, 'A.Добавить(i);')
                   + 'Message(A.Count()); Message(A.Get(19)); EndProcedure')
        plan = compile_owned(parse(routine + '\nOnStart();'), source_text=routine, source_name='append-loop.bsl', source_scopes=True)
        tree = ast.parse(plan.generated_source)
        native_loops = [
            block for block in ast.walk(tree) if isinstance(block, ast.While)
            and any(isinstance(item, ast.Name) and item.id == '_Member' for item in ast.walk(block))
        ]
        self.assertEqual(len(native_loops), 1)
        self.assertNotIn('.checkpoint(', ast.unparse(native_loops[0]))
        seen = []
        from yadinassi.configuration.configuration_source_runtime import SourceApplication
        from test_configuration_source_runtime import source as configuration
        app = SourceApplication(configuration(routine.encode()), output=seen.append)
        self.addCleanup(app.close)
        app.start()
        self.assertEqual(seen, ['20', '20'])

    def test_budgeted_owner_keeps_metering(self):
        array = PlainArray()
        with self.assertRaisesRegex(BoundaryViolation, 'loop backedge budget'):
            owned(source(5)).run({'a': array}, context=BoundaryContext(loop_budget=2))
        self.assertEqual(list(array), [1, 2])

    def test_host_receiver_keeps_dispatch_after_capture(self):
        class Host:
            def __init__(self):
                self.seen = []
            def add(self, value):
                self.seen.append(value)
        host = Host()
        context = BoundaryContext(members=(HostMembers(host, callable=('Add',)),))
        owned(source(3), source_scopes=False).run({'a': host}, context=context)
        self.assertEqual(host.seen, [1, 2, 3])

    def test_revoked_counter_initialization_does_not_append(self):
        original = PlainArray([0])

        # Supply the module counter through an owned dict, which publishes
        # immediately rather than delaying prior value release to final sync.
        context = BoundaryContext()
        class Revoke:
            def __del__(self):
                context.revoke()
        state = {'a': original, 'i': Revoke()}
        with self.assertRaises(BoundaryViolation):
            owned(source(2)).run(state, context=context)
        self.assertEqual(list(original), [0])

    def test_dynamic_argument_still_cannot_append_after_close(self):
        vm = Interpreter(allow_extensions=True)
        array = PlainArray([0])
        vm.variables['a'] = array
        vm.register_function('CloseOwner', lambda: vm.close() or Decimal(9))
        with self.assertRaises(BoundaryViolation):
            vm.execute(source(3, 'A.Add(CloseOwner());'))
        self.assertEqual(list(array), [0])

    def test_custom_checkpoint_keeps_original_loop(self):
        class Metered(BoundaryContext):
            def checkpoint(self):
                super().checkpoint()
                if self.loop_backedges == 2:
                    self.revoke()
                    self._check()

        array = PlainArray()
        with self.assertRaises(BoundaryViolation):
            owned(source(3)).run({'a': array}, context=Metered())
        self.assertEqual(list(array), [1])

    def test_override_is_not_dispatched_as_list_append(self):
        vm = Interpreter()
        array = PlainArray()
        vm.variables['a'] = array
        values = []

        def record(receiver, value):
            self.assertIs(receiver, array)
            values.append(value)

        with patch.object(PlainArray, 'append', record):
            vm.execute(source(3))
        self.assertEqual(values, [1, 2, 3])
        self.assertEqual(list(array), [])

    def test_override_lookup_remains_a_host_boundary(self):
        vm = Interpreter()
        array = PlainArray()
        vm.variables['a'] = array

        def getattribute(receiver, name):
            if name == 'append':
                vm.close()
            return list.__getattribute__(receiver, name)

        with patch.object(PlainArray, '__getattribute__', getattribute):
            with self.assertRaises(BoundaryViolation):
                vm.execute(source(3))
        self.assertEqual(list(array), [])
