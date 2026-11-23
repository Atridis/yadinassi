"""Direct execution must preserve live authority and effects across services.

Retired segment counters/instrumented fallback comparisons were removed; the
original result, reference, revocation and no-replay expectations remain.
"""
import unittest
from decimal import Decimal

from yadinassi import Interpreter
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation


class PythonSyncSegmentTests(unittest.TestCase):
    def test_module_segments_publish_and_reload_live_namespace(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        seen = []
        def boundary():
            seen.append(vm.variables['s'])
            vm.variables['s'] = Decimal(100)
        vm.register_function('Boundary', boundary)
        vm.execute('s=0;For i=1 To 3 Do s=s+i;EndDo;Boundary();For i=1 To 3 Do s=s+i;EndDo;result=s;')
        self.assertEqual(seen, [6])
        self.assertEqual(vm.variables['result'], 106)

    def test_mixed_routine_reloads_explicit_byref_after_callback_without_replay(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        seen = []
        def boundary(slot):
            seen.append(slot.get())
            slot.set(Decimal(100))
        vm.functions['boundary'] = HostFunction('Boundary', boundary,
                                                reference_parameters=frozenset({0}))
        vm.execute('''Function F(Val n)
        s=0;For i=1 To n Do s=s+i;EndDo;
        Boundary(s);
        For i=1 To n Do s=s+i;EndDo;
        Return s;
        EndFunction result=F(3);''')
        self.assertEqual(seen, [6])
        self.assertEqual(vm.variables['result'], 106)
        self.assertIsNone(vm.locals)

    def test_partial_module_writes_and_error_location_match_general_route(self):
        outcomes = []
        for observed in (False,):
            vm = Interpreter(execution_backend='python-direct')
            try:
                vm.execute('s=0;\nFor i=1 To 4 Do\n s=s+i;\n q=1/(3-i);\nEndDo;', 'segments.bsl')
            except Exception as error:
                outcomes.append((type(error), str(error), dict(vm.variables)))
            else:
                self.fail('expected division by zero')
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0][2]['s'], 6)
        self.assertEqual(outcomes[0][2]['i'], 3)

    def test_byref_slot_keeps_copyback_across_services(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        seen = []
        vm.register_function('Boundary', lambda value: seen.append(value))
        vm.execute('''Procedure F(x)
        For i=1 To 3 Do x=x+i;EndDo;
        Boundary(x);
        For i=1 To 3 Do x=x+i;EndDo;
        EndProcedure x=1;F(x);result=x;''')
        self.assertEqual(seen, [7])
        self.assertEqual(vm.variables['result'], 13)

    def test_foreign_import_namespace_rejected_before_assignment(self):
        vm=Interpreter(execution_backend='python-direct')
        vm.imports['reserved']=object()
        with self.assertRaises(BoundaryViolation):
            vm.execute('For i=1 To 2 Do reserved=3;EndDo;', 'imports.bsl')
        self.assertNotIn('reserved',vm.variables)

    def test_return_exits_mixed_routine_and_does_not_run_later_service(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        events = []
        vm.register_function('Boundary', lambda: events.append('boundary'))
        vm.execute('''Function F(Val n)
        Boundary();
        s=0;For i=1 To n Do s=s+i;If i=3 Then Return s;EndIf;EndDo;
        Boundary();Return -1;
        EndFunction result=F(10);''')
        self.assertEqual(events, ['boundary'])
        self.assertEqual(vm.variables['result'], 6)
        self.assertIsNone(vm.locals)

    def test_callback_replaces_scalar_with_reference_next_segment_declines(self):
        from yadinassi.types.values import Reference
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        cell = [Decimal(100)]
        def boundary():
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

    def test_module_context_revocation_is_rechecked_after_service(self):
        vm=Interpreter(execution_backend='python-direct', allow_extensions=True);calls=[]
        def boundary():
            calls.append(1)
            vm._module_context_stack[-1]=False
        vm.register_function('Boundary',boundary)
        try:
            with self.assertRaises(BoundaryViolation):
                vm.execute('s=0;For i=1 To 3 Do s=s+i;EndDo;Boundary();For i=1 To 3 Do s=s+i;EndDo;', 'revoked.bsl')
        finally:
            vm._module_context_stack[-1]=True
        self.assertEqual(calls,[1])
        self.assertEqual(vm.variables['s'],6)

    def test_thisobject_readonly_assignment_stays_general(self):
        outcomes = []
        for observed in (False,):
            vm = Interpreter(execution_backend='python-direct')
            try:
                vm.execute('For i=1 To 2 Do ThisObject=3;EndDo;', 'receiver.bsl')
            except Exception as error:
                outcomes.append((type(error), str(error)))
            else:
                self.fail('read-only receiver assignment was accepted')
            self.assertNotIn('thisobject', vm.variables)
        self.assertEqual(len(outcomes), 1)
