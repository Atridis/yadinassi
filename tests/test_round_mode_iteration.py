"""EDT-documented namespace iteration; no claim about native traversal order."""

import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.numeric.round_modes import BSLRoundMode, BSLRoundModes, ROUND_MODES
from yadinassi.values import BSLObject


class RoundModeIterationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_namespace_iterators_are_independent_and_unique(self):
        first, second = iter(ROUND_MODES), iter(ROUND_MODES)
        self.assertIsNot(first, second)
        expected = {BSLRoundMode.ROUND15_AS10, BSLRoundMode.ROUND15_AS20}
        self.assertEqual(set(first), expected)
        self.assertEqual(set(second), expected)
        self.assertEqual(len(list(ROUND_MODES)), 2)

    def test_bilingual_names_alias_and_expression_evaluated_once(self):
        calls = []
        def modes():
            calls.append(True)
            return ROUND_MODES
        self.vm.register_function('Modes', modes)
        for expression in ['РежимОкругления', 'rOuNdMoDe', 'alias', 'Modes()']:
            with self.subTest(expression=expression):
                self.vm.execute(f'''
                    alias = RoundMode; found = New Array;
                    Для Каждого item Из {expression} Цикл found.Add(item); КонецЦикла;
                ''')
                found = self.vm.variables['found'].items
                self.assertEqual(len(found), 2)
                self.assertEqual(set(found), set(BSLRoundMode))
        self.assertEqual(calls, [True])

    def test_values_keep_identity_type_rounding_and_serialization(self):
        self.vm.execute('''
            seen = New Map;
            For Each mode In RoundMode Do
                Message(TypeOf(mode) = Type("RoundMode"));
                restored = ValueFromStringInternal(ValueToStringInternal(mode));
                Message(restored = mode);
                seen.Insert(mode, Round(1.5, 0, mode));
            EndDo;
            Message(seen.Count());
            Message(seen[RoundMode.Round15as10]);
            Message(seen[RoundMode.Round15as20]);
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Да', 'Да', '2', '1', '2'])

    def test_nested_break_continue_and_repeat_do_not_consume_namespace(self):
        self.vm.execute('''
            total = 0;
            For Each outer In RoundMode Do
                For Each inner In РежимОкругления Do
                    total = total + 1;
                EndDo;
            EndDo;
            Message(total);
            total = 0;
            For Each outer In RoundMode Do
                For Each inner In RoundMode Do
                    total = total + 1; Break;
                EndDo;
                Continue; total = 100;
            EndDo;
            Message(total);
            total = 0;
            Для Каждого mode Из РежимОкругления Цикл
                Если mode = RoundMode.Round15as10 Тогда Продолжить; КонецЕсли;
                total = total + 1;
            КонецЦикла;
            Сообщить(total);
            total = 0;
            Для Каждого mode Из РежимОкругления Цикл
                total = total + 1; Прервать;
            КонецЦикла;
            Сообщить(total);
            total = 0;
            For Each mode In RoundMode Do total = total + 1; EndDo;
            Message(total);
        ''')
        self.assertEqual(self.output, ['4', '2', '1', '1', '2'])

    def test_scope_return_and_assignment_follow_normal_loop_rules(self):
        self.vm.execute('''
            Function FirstMode()
                For Each localMode In RoundMode Do Return localMode; EndDo;
            EndFunction
            mode = "before";
            For Each mode In RoundMode Do last = mode; EndDo;
            Message(mode = last);
            Message(TypeOf(FirstMode()) = Type("RoundMode"));
            For Each mode In RoundMode Do mode = 123; EndDo;
            Message(mode);
            For Each mode In RoundMode Do Message(TypeOf(mode) = Type("RoundMode")); EndDo;
        ''')
        self.assertEqual(self.output, ['Да', 'Да', '123', 'Да', 'Да'])
        self.assertNotIn('localmode', self.vm.variables)

    def test_body_error_does_not_poison_next_iteration(self):
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('For Each mode In RoundMode Do value = 1 / 0; EndDo;')
        self.vm.execute('count = 0; For Each mode In RoundMode Do count = count + 1; EndDo; Message(count);')
        self.assertEqual(self.output, ['2'])

    def test_iteration_does_not_enable_indexing_mutation_or_host_reflection(self):
        for expression in ['RoundMode[0]', 'RoundMode.Count()', 'RoundMode.Количество()',
                           'RoundMode.Get(0)', 'RoundMode.__iter__()', 'RoundMode.items']:
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        for source in ['RoundMode[0] = 1;', 'RoundMode.Round15as10 = 1;']:
            with self.subTest(source=source), self.assertRaises(BSLRuntimeError):
                self.vm.execute(source)
        self.assertEqual(set(ROUND_MODES), set(BSLRoundMode))

    def test_closed_runtime_boundary_rejects_host_iterables_and_individual_modes(self):
        class HostIterable(BSLObject):
            def __iter__(self):
                raise AssertionError('Host iterator must not be invoked')
        class HostNamespace(BSLRoundModes):
            def __iter__(self):
                raise AssertionError('Host subclass iterator must not be invoked')
        for value in [[], (), {}, 'abc', iter([1]), HostIterable(), HostNamespace(),
                      BSLRoundMode.ROUND15_AS10, BSLRoundMode.ROUND15_AS20]:
            with self.subTest(value=type(value).__name__):
                self.vm.variables['source'] = value
                with self.assertRaisesRegex(BSLRuntimeError, 'Для Каждого ожидает'):
                    self.vm.execute('For Each item In source Do EndDo;')


if __name__ == '__main__':
    unittest.main()
