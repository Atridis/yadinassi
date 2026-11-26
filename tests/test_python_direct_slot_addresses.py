"""ByRef stores an address, not a copy of an argument or a property proxy."""
import ast
import unittest
from contextlib import closing

from yadinassi import Interpreter
from yadinassi.types.values import Reference


class SlotAddressTests(unittest.TestCase):
    def test_module_and_local_aliases_share_storage(self):
        text = ('Procedure Inc(a,b) a=a+1; b=b+2; EndProcedure '
                'Function Work(Val x) Inc(x,x); Return x; EndFunction '
                'G=1; Inc(G,G); R=Work(2);')
        for prepared in (False, True):
            with self.subTest(prepared=prepared), closing(Interpreter()) as vm:
                plan = vm.prepare(text)
                tree = ast.parse(plan._plan.generated_source)
                self.assertFalse(any(type(node) is ast.Attribute and node.attr == 'value'
                                     for node in ast.walk(tree)))
                if prepared:
                    vm.execute_prepared(plan)
                else:
                    vm.execute(text)
                self.assertEqual((vm.variables['g'], vm.variables['r']), (4, 5))

    def test_local_missing_address_precedes_callee_and_later_actual(self):
        messages = []
        with closing(Interpreter(messages.append)) as vm:
            vm.execute('Procedure F(x, Val y) Message("called"); EndProcedure '
                       'Function Later() Message("later"); Return 1; EndFunction '
                       'Procedure Work() Try F(x,Later()); Except Message("missing"); EndTry; '
                       'x=1; F(x,Later()); EndProcedure Work();')
        self.assertEqual(messages, ['missing', 'later', 'called'])

    def test_local_read_before_first_assignment_stays_catchable(self):
        messages = []
        with closing(Interpreter(messages.append)) as vm:
            vm.execute('Procedure F(x) x=2; EndProcedure '
                       'Procedure Work() Try Message(x); Except Message("missing"); EndTry; '
                       'x=1; F(x); Message(x); EndProcedure Work();')
        self.assertEqual(messages, ['missing', '2'])

    def test_host_reference_crosses_export_and_ordinary_local_call(self):
        for extensions in (False, True):
            with self.subTest(extensions=extensions), closing(Interpreter(allow_extensions=extensions)) as vm:
                box = [1]
                ref = Reference(lambda: box[0], lambda value: box.__setitem__(0, value))
                vm.variables['x'] = ref
                vm.execute('Procedure Inc(a) a=a+1; EndProcedure Inc(x);')
                vm.execute('Inc(x);')
                self.assertEqual(box[0], 3)
                self.assertIs(vm.variables['x'], ref)

    def test_array_address_operands_evaluate_left_to_right_once(self):
        events = []
        array = [0]
        with closing(Interpreter(allow_extensions=True)) as vm:
            vm.register_function('Arr', lambda: events.append('receiver') or array)
            vm.register_function('Idx', lambda: events.append('index') or 0)
            vm.execute('Procedure Inc(x) x=x+1; EndProcedure Inc(Arr()[Idx()]);')
        self.assertEqual(events, ['receiver', 'index'])
        self.assertEqual(array, [1])
