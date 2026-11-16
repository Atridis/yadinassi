"""Closed translated segments must reacquire live authority after services."""
import unittest
from decimal import Decimal

from yadinassi import Interpreter


class PythonSyncSegmentTests(unittest.TestCase):
    def test_module_segments_publish_and_reacquire_replaced_scope(self):
        vm = Interpreter(execution_backend='compiled-strict')
        seen = []
        def boundary():
            seen.append(vm.variables['s'])
            vm.variables = {'s': Decimal(100)}
        vm.register_function('Boundary', boundary)
        vm.execute('s=0;For i=1 To 3 Do s=s+i;EndDo;Boundary();For i=1 To 3 Do s=s+i;EndDo;result=s;')
        self.assertEqual(seen, [6])
        self.assertEqual(vm.variables['result'], 106)
        self.assertGreaterEqual(vm.compiled_backend_stats.get('python_sync_segment_calls', 0), 2)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def test_mixed_routine_reacquires_locals_after_opaque_call_without_replay(self):
        vm = Interpreter(execution_backend='compiled-strict')
        seen = []
        def boundary():
            seen.append(vm.locals['s'])
            vm.locals = {'s': Decimal(100), 'n': Decimal(3)}
        vm.register_function('Boundary', boundary)
        vm.execute('''Function F(Val n)
        s=0;For i=1 To n Do s=s+i;EndDo;
        Boundary();
        For i=1 To n Do s=s+i;EndDo;
        Return s;
        EndFunction result=F(3);''')
        self.assertEqual(seen, [6])
        self.assertEqual(vm.variables['result'], 106)
        self.assertIsNone(vm.locals)
        self.assertGreaterEqual(vm.compiled_backend_stats.get('python_sync_segment_calls', 0), 2)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_routine_calls', 0), 0)

    def test_partial_module_writes_and_error_location_match_general_route(self):
        outcomes = []
        for observed in (True, False):
            vm = Interpreter(execution_backend='compiled-strict')
            if observed:
                vm.compiled_before = lambda node: None
            try:
                vm.execute('s=0;\nFor i=1 To 4 Do\n s=s+i;\n q=1/(3-i);\nEndDo;', 'segments.bsl')
            except Exception as error:
                outcomes.append((type(error), str(error), dict(vm.variables)))
            else:
                self.fail('expected division by zero')
            self.assertEqual(vm._compiled()._active_frames, 0)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1][2]['s'], 6)
        self.assertEqual(outcomes[1][2]['i'], 3)

    def test_byref_slot_keeps_copyback_across_services(self):
        vm = Interpreter(execution_backend='compiled-strict')
        seen = []
        vm.register_function('Boundary', lambda value: seen.append(value))
        vm.execute('''Procedure F(x)
        For i=1 To 3 Do x=x+i;EndDo;
        Boundary(x);
        For i=1 To 3 Do x=x+i;EndDo;
        EndProcedure x=1;F(x);result=x;''')
        self.assertEqual(seen, [7])
        self.assertEqual(vm.variables['result'], 13)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def test_import_assignment_authority_is_not_bypassed(self):
        outcomes = []
        for observed in (True, False):
            vm = Interpreter(execution_backend='compiled-strict')
            vm.imports['reserved'] = object()
            if observed:
                vm.compiled_before = lambda node: None
            try:
                vm.execute('For i=1 To 2 Do reserved=3;EndDo;', 'imports.bsl')
            except Exception as error:
                outcomes.append((type(error), str(error)))
            else:
                self.fail('assignment to import was accepted')
            self.assertNotIn('reserved', vm.variables)
        self.assertEqual(outcomes[0], outcomes[1])

    def test_return_exits_mixed_routine_and_does_not_run_later_service(self):
        vm = Interpreter(execution_backend='compiled-strict')
        events = []
        vm.register_function('Boundary', lambda: events.append('boundary'))
        vm.execute('''Function F(Val n)
        Boundary();
        s=0;For i=1 To n Do s=s+i;If i=3 Then Return s;EndIf;EndDo;
        Boundary();Return -1;
        EndFunction result=F(10);''')
        self.assertEqual(events, ['boundary'])
        self.assertEqual(vm.variables['result'], 6)
        self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls', 0), 0)
        self.assertIsNone(vm.locals)

    def test_callback_replaces_scalar_with_reference_next_segment_declines(self):
        from yadinassi.values import Reference
        vm = Interpreter(execution_backend='compiled-strict')
        cell = [Decimal(100)]
        entries = []
        def boundary():
            entries.append(vm.compiled_backend_stats.get('python_sync_segment_calls', 0))
            vm.locals['s'] = Reference(lambda: cell[0], lambda value: cell.__setitem__(0, value))
        vm.register_function('Boundary', boundary)
        vm.execute('''Function F(Val n)
        s=0;For i=1 To n Do s=s+i;EndDo;
        Boundary();
        For i=1 To n Do s=s+i;EndDo;
        Return s;
        EndFunction result=F(3);''')
        self.assertEqual(cell, [106])
        self.assertEqual(vm.variables['result'], 106)
        self.assertGreater(entries[0], 0)
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls', 0), entries[0])

    def test_module_context_revocation_is_rechecked_after_service(self):
        outcomes = []
        for observed in (True, False):
            vm = Interpreter(execution_backend='compiled-strict')
            if observed:
                vm.compiled_before = lambda node: None
            calls = []
            def boundary():
                calls.append(1)
                vm._module_context_stack[-1] = False
            vm.register_function('Boundary', boundary)
            try:
                vm.execute('s=0;For i=1 To 3 Do s=s+i;EndDo;Boundary();For i=1 To 3 Do s=s+i;EndDo;', 'revoked.bsl')
            except Exception as error:
                outcomes.append((type(error), str(error), vm.variables['s']))
            else:
                self.fail('module reads survived context revocation')
            finally:
                vm._module_context_stack[-1] = True
            self.assertEqual(calls, [1])
        self.assertEqual(outcomes[0], outcomes[1])

    def test_thisobject_readonly_assignment_stays_general(self):
        outcomes = []
        for observed in (True, False):
            vm = Interpreter(execution_backend='compiled-strict')
            if observed:
                vm.compiled_before = lambda node: None
            try:
                vm.execute('For i=1 To 2 Do ThisObject=3;EndDo;', 'receiver.bsl')
            except Exception as error:
                outcomes.append((type(error), str(error)))
            else:
                self.fail('read-only receiver assignment was accepted')
            self.assertNotIn('thisobject', vm.variables)
        self.assertEqual(outcomes[0], outcomes[1])
