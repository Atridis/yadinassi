from compiled_contract_fixture import mutable_compiled_contract
"""Generic compiled For slot guards, not an arithmetic benchmark special case."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine
from yadinassi.syntax.parser import parse
from yadinassi.values import Reference
from yadinassi.errors import BSLRuntimeError


class CompiledForSlotTests(unittest.TestCase):
    def setUp(self):
        for name in ('INLINE', 'FAST_INLINE'):
            flag = patch.object(Engine, name, True)
            flag.start(); self.addCleanup(flag.stop)

    def test_bounds_once_and_live_counter_mutation(self):
        trace = []
        vm = Interpreter(execution_backend='compiled-strict')
        vm.register_function('StartBound', lambda: trace.append('start') or Decimal(1))
        vm.register_function('EndBound', lambda: trace.append('end') or Decimal(6))
        vm.execute('total=0;For i=StartBound() To EndBound() Do i=i+1;total=total+i;EndDo;')
        self.assertEqual(trace, ['start', 'end'])
        self.assertEqual(vm.variables['total'], 12)
        self.assertEqual(vm.variables['i'], 7)

    def test_reference_counter_keeps_get_and_set_authority(self):
        for mode in ('interpreter', 'compiled-strict'):
            value = [Decimal(0)]; writes = []; reads = []
            def get():
                reads.append(value[0]); return value[0]
            def set_value(new):
                writes.append(new); value[0] = new
            vm = Interpreter(execution_backend=mode)
            vm.locals = {'i': Reference(get, set_value)}
            vm.visit(parse('For i=1 To 3 Do EndDo;')[0])
            self.assertEqual(writes, list(map(Decimal, (1, 2, 3, 4))))
            self.assertEqual(len(reads), 7)
            self.assertEqual(value[0], 4)

    def test_host_installed_reference_invalidates_plain_local_slot(self):
        vm = Interpreter(execution_backend='compiled-strict')
        current = [Decimal(1)]; writes = []
        reference = Reference(lambda: current[0], lambda value: (writes.append(value), current.__setitem__(0, value)))
        vm.locals = {'i': Decimal(0)}
        vm.register_function('Install', lambda: vm.locals.__setitem__('i', reference))
        vm.visit(parse('For i=1 To 2 Do Install();EndDo;')[0])
        self.assertEqual(writes, [Decimal(2), Decimal(3)])
        self.assertIs(vm.locals['i'], reference)

    def test_host_installed_import_invalidates_counter_write(self):
        vm = Interpreter(execution_backend='compiled-strict')
        vm.register_function('Install', lambda: vm.imports.__setitem__('i', object()))
        with self.assertRaises(BSLRuntimeError):
            vm.execute('For i=1 To 2 Do Install();EndDo;')
        self.assertEqual(vm.variables['i'], 1)

    def test_host_installed_configuration_check_assignment_is_authoritative(self):
        vm = Interpreter(execution_backend='compiled-strict')
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
        vm = Interpreter(execution_backend='compiled-strict')
        vm.variables['thisobject'] = Decimal(0)
        vm.register_function('Install', lambda: vm.variables.pop('thisobject'))
        with self.assertRaises(BSLRuntimeError):
            vm.execute('For ThisObject=1 To 2 Do Install();EndDo;')
        self.assertNotIn('thisobject', vm.variables)

    def test_var_shadowing_invalidates_module_counter_slot(self):
        source = 'Var i;Procedure F() For i=1 To 2 Do Var i;i=10;EndDo;EndProcedure F();'
        values = []
        for mode in ('interpreter', 'compiled-strict'):
            vm = Interpreter(execution_backend=mode);vm.execute(source)
            values.append(vm.variables['i'])
        self.assertEqual(values, [Decimal(1), Decimal(1)])


if __name__ == '__main__': unittest.main()

class MetadataContainerGuards(unittest.TestCase):
    @mutable_compiled_contract
    def test_custom_scope_membership_is_opaque_in_all_fast_paths(self):
        from yadinassi.compiled_backend import CompiledUnsupported
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('For i=1 To 1 Do x=1;EndDo;')
        class Names(set):
            def __contains__(self, key):
                if key == 'i':
                    program[0].body[0].value.value = Decimal(9)
                return super().__contains__(key)
        vm.locals = {}
        vm.variables['i'] = Decimal(0)
        vm.module_names = Names(['i'])
        with self.assertRaises(CompiledUnsupported):
            vm.visit(program[0])
        self.assertNotIn('x', vm.locals)
        self.assertFalse(vm._compiled().fast_available(refresh=True))

    def test_custom_scope_key_disables_fast_admission_without_calling_equality(self):
        vm = Interpreter(execution_backend='compiled-strict')
        class Key(str):
            def __eq__(self, other):
                raise AssertionError('admission called custom key equality')
            __hash__ = str.__hash__
        vm.module_names = {Key('i')}
        self.assertFalse(vm._compiled().fast_available(refresh=True))
