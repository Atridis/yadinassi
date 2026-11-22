"""Live behavior migrated from retired compiled-engine tests.

No legacy oracle or fallback. Unsupported live behavior must fail normally.
Engine flags, registry layouts, tier counters and old node-visitor ABI are retired.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.types.values import Reference

class CompiledForSlotTests(unittest.TestCase):
    def test_bounds_once_and_live_counter_mutation(self):
        trace = []
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        vm.register_function('StartBound', lambda: trace.append('start') or Decimal(1))
        vm.register_function('EndBound', lambda: trace.append('end') or Decimal(6))
        vm.execute('total=0;For i=StartBound() To EndBound() Do i=i+1;total=total+i;EndDo;')
        self.assertEqual(trace, ['start', 'end'])
        self.assertEqual(vm.variables['total'], 12)
        self.assertEqual(vm.variables['i'], 7)

    def test_reference_counter_keeps_get_and_set_authority(self):
        for mode in ('python-direct',):
            value = [Decimal(0)]; writes = []; reads = []
            def get():
                reads.append(value[0]); return value[0]
            def set_value(new):
                writes.append(new); value[0] = new
            vm = Interpreter(execution_backend=mode, allow_extensions=True)
            self.addCleanup(vm.close)
            # Exercise the live host reference via a separately compiled BSL
            # by-reference routine, not the retired visitor's vm.locals.
            vm.variables['actual'] = Reference(get, set_value)
            vm.execute('Procedure CountThrough(i) For i=1 To 3 Do EndDo; EndProcedure')
            vm.execute('CountThrough(actual);')
            self.assertEqual(writes, list(map(Decimal, (1, 2, 3, 4))))
            self.assertEqual(len(reads), 7)
            self.assertEqual(value[0], 4)

    def test_host_installed_reference_invalidates_plain_local_slot(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        current = [Decimal(1)]; writes = []
        reference = Reference(lambda: current[0], lambda value: (writes.append(value), current.__setitem__(0, value)))
        vm.locals = {'i': Decimal(0)}
        vm.register_function('Install', lambda: vm.locals.__setitem__('i', reference))
        vm.execute('For i=1 To 2 Do Install();EndDo;')
        self.assertEqual(writes, [Decimal(2), Decimal(3)])
        self.assertIs(vm.locals['i'], reference)

    def test_host_installed_import_invalidates_counter_write(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        vm.register_function('Install', lambda: vm.imports.__setitem__('i', object()))
        with self.assertRaisesRegex(BoundaryViolation, 'foreign import binding'):
            vm.execute('For i=1 To 2 Do Install();EndDo;')
        self.assertEqual(vm.variables['i'], 1)

    def test_host_installed_configuration_check_assignment_is_authoritative(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        calls = []
        class Configuration:
            def check_assignment(self, name, owner):
                calls.append(name)
                raise ValueError('assignment revoked by configuration')
        vm.register_function('Install', lambda: setattr(vm, '_configuration_runtime', Configuration()))
        with self.assertRaises(BSLRuntimeError) as failure:
            vm.execute('For i=1 To 2 Do Install();EndDo;')
        self.assertIn('assignment revoked', str(failure.exception))
        self.assertEqual(calls, ['i'])
        self.assertEqual(vm.variables['i'], 1)

    def test_host_removed_readonly_name_does_not_recreate_plain_slot(self):
        vm = Interpreter(execution_backend='python-direct', allow_extensions=True)
        vm.variables['thisobject'] = Decimal(0)
        vm.register_function('Install', lambda: vm.variables.pop('thisobject'))
        with self.assertRaises(BSLRuntimeError):
            vm.execute('For ThisObject=1 To 2 Do Install();EndDo;')
        self.assertNotIn('thisobject', vm.variables)

    def test_var_shadowing_invalidates_module_counter_slot(self):
        source = 'Var i;Procedure F() For i=1 To 2 Do Var i;i=10;EndDo;EndProcedure F();'
        values = []
        for mode in ('python-direct',):
            vm = Interpreter(execution_backend=mode);vm.execute(source)
            values.append(vm.variables['i'])
        self.assertEqual(values, [Decimal(1)])
