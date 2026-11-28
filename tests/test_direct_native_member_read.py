"""Behavior retained when owned field reads become native mapping reads."""
import unittest

from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.types.values import HostFunction


class DirectNativeMemberReadTests(unittest.TestCase):
    def test_casefold_none_and_live_replacement(self):
        vm = Interpreter()
        program = vm.prepare('''
S = New Structure("Name, Empty", "old");
Alias = S;
First = Alias.nAmE;
S.Name = "new";
Last = Alias.NAME;
Blank = Alias.EmPtY;
''')
        vm.execute_prepared(program)
        self.assertEqual(vm.variables['first'], 'old')
        self.assertEqual(vm.variables['last'], 'new')
        self.assertIsNone(vm.variables['blank'])

    def test_missing_field_keeps_ordinary_bsl_error(self):
        vm = Interpreter()
        with self.assertRaisesRegex(BSLRuntimeError, 'Свойство структуры не найдено: AbSeNt'):
            vm.execute('S = New Structure("Name", "old"); Value = S.AbSeNt;')

    def test_unknown_native_method_is_rejected_before_actual(self):
        events = []
        vm = Interpreter(allow_extensions=True)
        vm.register_function('Effect', lambda: events.append('actual') or 1)
        with self.assertRaisesRegex(BSLRuntimeError, 'Метод структуры не найден: NotAMethod'):
            vm.execute('S = New Structure; S.NotAMethod(Effect());')
        self.assertEqual(events, [])

    def test_named_calls_read_live_values_and_preserve_byref(self):
        vm = Interpreter(allow_extensions=True)
        vm.functions['change'] = HostFunction('Change', lambda ref: ref.set('changed'),
                                             reference_parameters=(0,), returns_value=False)
        vm.execute('''
S = New Structure("Code", "start");
First = String(S.CoDe);
Change(S.cOdE);
Second = Upper(S.CODE);
''')
        self.assertEqual(vm.variables['first'], 'start')
        self.assertEqual(vm.variables['second'], 'CHANGED')
