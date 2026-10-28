"""Local observer validity; synthetic Total replacements are not native evidence."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest import mock
from yadinassi import Interpreter
from yadinassi.values import HostFunction
from yadinassi.value_trees import BSLValueTreeRowCollection as Rows
from scripts import native_1c_tree_total_contract as contract

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
HELPERS = SOURCE[SOURCE.index('// Begin bounded ValueTree Total helpers'):SOURCE.index('// Begin bounded ValueTree Move helpers')]
EXACT = SOURCE[SOURCE.index('Функция TreeLoadExact('):SOURCE.index('Функция TreeLoadPair(')]


def vm():
    value = Interpreter()
    value.execute(HELPERS + EXACT)
    return value


class TotalObserverTests(unittest.TestCase):
    def test_all_fixtures_valid_when_action_is_unavailable(self):
        original = Rows.get_method
        def without_total(rows, name):
            if name.casefold() in ('total', 'итог'):
                raise ValueError('synthetic unavailable action')
            return original(rows, name)
        value = vm()
        with mock.patch.object(Rows, 'get_method', without_total):
            value.execute('Result=TreeTotalObservations();')
        self.assertEqual(value.variables['result'], '1'+'E'*32)
        contract.validate_payload(value.variables['result'].encode())

    def test_exact_numbers_and_unexpected_types_do_not_use_text_conversion(self):
        value = vm()
        for case, numbers in [(i, contract.CASE_NUMBERS.get(i, contract.NUMBER_VALUES)) for i in range(1,33)]:
            for index, number in enumerate(numbers):
                value.execute(f'Result=TreeTotalCode({number},{case});')
                self.assertEqual(value.variables['result'], chr(contract.ALPHABET[index]))
        for expression, expected in [('Неопределено','U'),('Null','L'),('Истина','!'),('"3"','!'),('123456789','!'),('Новый Массив','!')]:
            value.execute(f'Result=TreeTotalCode({expression},1);')
            self.assertEqual(value.variables['result'], expected)

    def test_post_state_detects_each_mutation_independently(self):
        value = vm()
        changes = ['S.Tree.Rows.Move(0,1);', 'S.Nodes[0].N=99;', 'S.Nodes[2].Rows.Add();',
                   'S.Column.Title="changed";', 'S.Column.Width=1;', 'S.Column.Name="Other";',
                   'S.Foreign.Rows.Add();', 'S.ForeignColumn.Title="changed";',
                   'S.Tree.Rows.Delete(0);', 'S.Foreign.Columns.Clear();']
        for change in changes:
            with self.subTest(change=change):
                value.execute('S=TreeTotalFresh(1); Before=TreeTotalState(S);'+change+'After=TreeTotalState(S);')
                self.assertIs(value.variables['before'], True)
                self.assertIs(value.variables['after'], False)

    def test_action_success_unknown_and_mutation_are_not_action_exceptions(self):
        original = Rows.get_method
        def run(action):
            def get_method(rows, name):
                if name.casefold() in ('total','итог'):
                    return HostFunction(name, lambda *args: action(rows))
                return original(rows,name)
            with mock.patch.object(Rows,'get_method',get_method):
                value = vm(); value.execute('Result=TreeTotalProbe(1);')
                return value.variables['result']
        self.assertEqual(run(lambda rows: Decimal(5)), '4')
        self.assertEqual(run(lambda rows: '5'), '!')
        def mutate(rows):
            rows.items[0].set_member('N', Decimal(99))
            return Decimal(5)
        self.assertEqual(run(mutate), 'T')
        def failing(rows):
            raise ValueError('synthetic action failure')
        self.assertEqual(run(failing), 'E')
        def mutate_and_fail(rows):
            rows.items[0].set_member('N', Decimal(99))
            raise ValueError('synthetic failure after mutation')
        self.assertEqual(run(mutate_and_fail), 'T')

    def test_encoder_exception_is_invalid_not_action_exception(self):
        value = Interpreter()
        corrupted = HELPERS.replace('    Values = Новый Массив;\n    Если Case = 29', '    ВызватьИсключение "synthetic-encoder-failure";\n    Values = Новый Массив;\n    Если Case = 29')
        self.assertNotEqual(corrupted, HELPERS)
        original = Rows.get_method
        def get_method(rows,name):
            if name.casefold() in ('total','итог'):
                return HostFunction(name,lambda *args:Decimal(5))
            return original(rows,name)
        with mock.patch.object(Rows,'get_method',get_method):
            value.execute(corrupted+EXACT+'Result=TreeTotalProbe(1);')
        self.assertEqual(value.variables['result'],'!')

    def test_precondition_mismatch_error_and_postcheck_error_are_distinct(self):
        mutations = (
            ('S = TreeTotalFresh(Case); Если Не TreeTotalState(S)',
             'S = TreeTotalFresh(Case); S.Column.Title="bad"; Если Не TreeTotalState(S)', 'Q'),
            ('S = TreeTotalFresh(Case); Если Не TreeTotalState(S)',
             'S = Неопределено; Если Не TreeTotalState(S)', 'P'),
            ('Попытка Если Не TreeTotalState(S) Тогда Возврат "T";',
             'S = Неопределено; Попытка Если Не TreeTotalState(S) Тогда Возврат "T";', 'R'),
        )
        for before, after, expected in mutations:
            with self.subTest(expected=expected):
                self.assertEqual(HELPERS.count(before), 1)
                value = Interpreter()
                value.execute(HELPERS.replace(before, after)+EXACT+'Result=TreeTotalProbe(1);')
                self.assertEqual(value.variables['result'], expected)
                with self.assertRaises(contract.ObservationError):
                    contract.validate_payload(('1'+expected+'E'*31).encode())
