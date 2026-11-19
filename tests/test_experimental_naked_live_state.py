import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.values import Reference, HostFunction
from yadinassi.errors import BSLRuntimeError
from yadinassi.experimental_naked_boundaries import BoundaryContext, BoundaryViolation

class LiveModuleStateTests(unittest.TestCase):

    def run_live(self, source, state=None, services=None, module_names=()):
        vm = Interpreter()
        self.addCleanup(vm.close)
        if state is not None:
            vm.variables = state
        vm.module_names.update(module_names)
        for name, function in (services or {}).items():
            vm.register_function(name, function)
        vm.execute(source, 'live.bsl')
        return vm.variables

    def test_callback_read_write_same_object(self):
        state = {}
        seen = []

        def host():
            seen.append(state['x'])
            state['x'] = Decimal(8)
        self.run_live('x=1;Host();r=x;', state, {'Host': host})
        self.assertEqual(seen, [1])
        self.assertEqual(state, {'x': 8, 'r': 8})

    def test_delete_and_missing_error_does_not_republish(self):
        state = {}
        with self.assertRaisesRegex(BSLRuntimeError, 'не определена: x'):
            self.run_live('x=1;Delete();r=x;', state, {'Delete': lambda: state.pop('x')})
        self.assertEqual(state, {})

    def test_host_rebinds_its_own_variable_not_actual_namespace(self):
        original = {}
        holder = [original]

        def host():
            holder[0] = {}
            original['x'] = Decimal(8)
        self.run_live('x=1;Host();r=x;', original, {'Host': host})
        self.assertEqual(original['r'], 8)
        self.assertEqual(holder[0], {})

    def test_source_reference_alias(self):
        self.assertEqual(self.run_live('Procedure F(a,b) a=a+1;b=b+2;EndProcedure x=1;F(x,x);r=x;')['r'], 4)

    def test_retained_host_reference_live_after_return(self):
        refs = []
        h = HostFunction('h', lambda x: refs.append(x), reference_parameters=frozenset({0}))
        state = self.run_live('x=1;f=Get();f(x);', services={'Get': lambda: h})
        self.assertIs(type(refs[0]), Reference)
        refs[0].set(Decimal(9))
        self.assertEqual(state['x'], 9)

    def test_seeded_reference_identity_and_source_forwarding(self):
        box = [Decimal(1)]
        ref = Reference(lambda: box[0], lambda v: box.__setitem__(0, v))
        seen = []
        host = HostFunction('h', lambda arg: seen.append(arg is ref), reference_parameters=frozenset({0}))
        state = {'x': ref}
        self.run_live('Procedure Bump(a) a=a+1;EndProcedure f=Get();f(x);Bump(x);', state, {'Get': lambda: host})
        self.assertEqual(seen, [True])
        self.assertEqual(box[0], 2)
        self.assertIs(state['x'], ref)

    def test_predeclaration_and_explicit_previous_module_names(self):
        self.assertIsNone(self.run_live('r=x;Var x;')['r'])

    def test_explicit_previous_module_names(self):
        self.assertEqual(self.run_live('Function F() x=x+1;Return x;EndFunction r=F();', {'x': Decimal(8)}, module_names=('x',))['r'], 9)

    def test_routine_private_locals_stay_private(self):
        source = 'Var x;Function F() Var y;y=8;x=x+1;Return y;EndFunction x=1;r=F();'
        state = self.run_live(source)
        self.assertEqual(state, {'x': 2, 'r': 8})
        self.assertNotIn('y', state)

    def test_readonly_rhs_first_and_shadow(self):
        for source in ('ThisObject=Host();', 'Procedure F() ThisObject=Host();EndProcedure F();'):
            events = []
            with self.assertRaisesRegex(BSLRuntimeError, 'только для чтения'):
                self.run_live(source, services={'Host': lambda: events.append(1) or 1})
            self.assertEqual(events, [1])
        self.assertEqual(self.run_live('Var ThisObject;ThisObject=1;r=ThisObject;')['r'], 1)
        self.assertEqual(self.run_live('Procedure F() Var ThisObject;ThisObject=1;EndProcedure F();'), {})

    def test_for_order_mutation_continue(self):
        state = {}
        seen = []

        def bound():
            seen.append(state['i'])
            return Decimal(3)

        def change():
            state['i'] = Decimal(10)
        self.run_live('i=9;For i=1 To Bound() Do Change();Continue;EndDo;r=i;', state, {'Bound': bound, 'Change': change})
        self.assertEqual(seen, [9])
        self.assertEqual(state['r'], 11)

    def test_counter_delete_errors_without_keyerror(self):
        state = {}
        with self.assertRaisesRegex(BSLRuntimeError, 'не определена: i'):
            self.run_live('For i=1 To 2 Do Delete();EndDo;', state, {'Delete': lambda: state.pop('i')})
        self.assertNotIn('i', state)

    def test_foreach_readonly_target_rejects_after_iterator_value(self):
        with self.assertRaisesRegex(BSLRuntimeError, 'только для чтения'):
            self.run_live('a=New Array;a.Add(1);For Each ThisObject In a Do r=1;EndDo;')

    def test_partial_writes_before_error(self):
        state = {}
        with self.assertRaises(BSLRuntimeError):
            self.run_live('x=1;y=1/0;', state)
        self.assertEqual(state, {'x': 1})

    def test_module_globals_and_loop_results(self):
        state = self.run_live('Var x;Procedure F(a) a=a+1;x=x+1;EndProcedure x=1;s=0;For i=1 To 5 Do F(x);s=s+x;EndDo;r=s;')
        self.assertEqual([state[n] for n in ('x', 'r', 's', 'i')], [11, 35, 35, 6])

class LiveReferenceSpoofTests(unittest.TestCase):

    def test_reference_binding_does_not_consult_host_class_property(self):
        from yadinassi.experimental_naked_live_state import source_reference, host_reference
        events = []

        class Host:

            @property
            def __class__(self):
                events.append('class')
                return Reference
        value = Host()
        state = {'x': value}
        self.assertIs(source_reference(state, 'x').get(), value)
        self.assertIs(host_reference(state, 'x').get(), value)
        self.assertEqual(events, [])
