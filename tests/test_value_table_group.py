"""GroupBy regressions transcribed from genuine native PR64 observations."""
from decimal import Decimal as D, Inexact, Rounded, localcontext
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from tests.test_value_table_operations_checkpoint import observations

from yadinassi.dates import literal_date
from yadinassi.type_descriptions import BSLTypeDescription as TD
from yadinassi.type_qualifiers import BSLNumberQualifiers
from yadinassi.value_tables import BSLValueTable
from yadinassi.value_table_group import group_by
from yadinassi.values import NULL, BSLArray


def sample(description=None, values=None, keys=None):
    table = BSLValueTable()
    table.columns.add('Key', title='Key title', width=D(12))
    table.columns.add('Second')
    table.columns.add('Amount', description, 'Amount title', D(9))
    table.columns.add('Discard')
    for i, (key, amount) in enumerate(zip(keys or ['B', 'A', 'B', 'C'],
                                         values or [D(2), D(3), D(4), D(5)])):
        row = table.add()
        row.set_member('Key', key)
        row.set_member('Second', 'y' if i == 2 else 'x')
        row.set_member('Amount', amount)
        row.set_member('Discard', D(i + 1))
    return table


def state(table):
    return [c.name for c in table.columns], [list(row) for row in table]


class GroupByTests(unittest.TestCase):
    def test_basic_identity_schema_and_removed_refs(self):
        table = sample()
        first, second, third, fourth = table.rows
        key, _, amount, discard = table.columns.items
        table.group_by('Key', 'Amount')
        self.assertEqual(state(table), (['Key', 'Amount'], [['B', D(6)], ['A', D(3)], ['C', D(5)]]))
        self.assertEqual(table.rows, [first, second, fourth])
        self.assertIs(table.columns.items[0], key)
        self.assertIs(table.columns.items[1], amount)
        self.assertEqual((amount.title, amount.width), ('Amount title', D(9)))
        self.assertEqual(table.index_of(third), D(-1))
        with self.assertRaises(ValueError):
            third.owner()
        with self.assertRaises(ValueError):
            first.get_member('Discard')
        self.assertEqual(table.columns.index_of(discard), D(4294967295))
        self.assertEqual(discard.name, '')
        first.set_member('Key', 'changed')
        self.assertEqual(table.rows[0].get_member('Key'), 'changed')

    def test_detached_iteration_returns_current_owner_rows_by_identity(self):
        # Native evidence creates a fresh iterator after each mutation. It does
        # not establish mutation semantics during an already active iterator.
        for operation in ('group', 'delete', 'clear'):
            with self.subTest(operation=operation):
                table = sample()
                first, second, removed, fourth = table.rows
                original_columns = list(table.columns)
                if operation == 'group':
                    table.group_by('Key', 'Amount')
                    survivors = [first, second, fourth]
                    self.assertEqual(list(table.columns), [original_columns[0], original_columns[2]])
                    self.assertEqual((original_columns[0].title, original_columns[0].width),
                                     ('Key title', D(12)))
                    self.assertEqual((original_columns[2].title, original_columns[2].width),
                                     ('Amount title', D(9)))
                elif operation == 'delete':
                    table.delete(removed)
                    survivors = [first, second, fourth]
                else:
                    table.clear()
                    survivors = []
                self.assertEqual(table.index_of(removed), D(-1))
                for read in (removed.owner, lambda: removed.get(D(0)),
                             lambda: removed.get_member('Key')):
                    with self.assertRaises(ValueError):
                        read()
                observed = list(removed)
                self.assertEqual(len(observed), len(survivors))
                for actual, expected in zip(observed, survivors):
                    self.assertIs(actual, expected)
                    self.assertIs(actual.owner(), table)
                    self.assertIsNot(actual, removed)
                appended = table.add()
                appended.set_member('Key', 'new')
                appended.set_member('Amount', D(99))
                observed = list(removed)
                self.assertEqual(len(observed), len(survivors) + 1)
                self.assertIs(observed[-1], appended)
                self.assertIs(observed[-1].owner(), table)
                self.assertEqual(observed[-1].get_member('Amount'), D(99))
                table.clear()
                self.assertEqual(list(removed), [])
                self.assertEqual(list(appended), [])

    def test_selection_tolerance_and_original_order(self):
        table = sample()
        table.group_by(' Second,, Key,Key ', ' Amount,Amount ')
        self.assertEqual([c.name for c in table.columns], ['Key', 'Second', 'Amount'])
        self.assertEqual(len(table.rows), 4)

    def test_errors_are_atomic(self):
        for groups, totals in [('Key,Missing', 'Amount'), ('Key', 'Amount,Missing'),
                               ('Key', 'Key,Amount'), (D(1), 'Amount'), ('Key', D(1))]:
            table = sample()
            before = state(table)
            with self.assertRaises((ValueError, TypeError)):
                table.group_by(groups, totals)
            self.assertEqual(state(table), before)

    def test_empty_and_omitted_lists(self):
        table = sample()
        table.group_by(None, 'Amount')
        self.assertEqual(state(table), (['Amount'], [[D(14)]]))
        table = sample()
        table.group_by('Key')
        self.assertEqual(state(table), (['Key'], [['B'], ['A'], ['C']]))
        table = sample()
        table.group_by('', '')
        self.assertEqual(state(table), ([], []))
        table = sample()
        table.clear()
        table.group_by('', 'Amount')
        self.assertEqual(state(table), (['Amount'], []))

    def test_exact_scalar_keys(self):
        for keys, expected in [([NULL, None, NULL, None], [[NULL, D(6)], [None, D(8)]]),
                               (['a', 'A', 'a ', 'A'], [['a', D(2)], ['A', D(8)], ['a ', D(4)]]),
                               ([D(1), '1', True, D(1)], [[D(1), D(7)], ['1', D(3)], [True, D(4)]])]:
            table = sample(keys=keys)
            table.group_by('Key', 'Amount')
            self.assertEqual(state(table)[1], expected)

    def test_typed_native_totals(self):
        cases = [('Строка', ['2', '3', '4', '5'], ['6', '3', '5']),
                 ('Строка', ['2', '3', 'bad', '5'], ['2', '3', '5']),
                 ('Булево', [True, False, True, True], [True, False, True]),
                 ('Число,Строка', [D(2), D(3), '4', '4'], [D(2), D(3), D(0)]),
                 ('Булево,Строка', ['2', '2', True, '2'], ['0', '0', '0'])]
        for kind, values, expected in cases:
            table = sample(TD(kind), values)
            table.group_by('Key', 'Amount')
            self.assertEqual([row.get_member('Amount') for row in table], expected)
        table = sample(values=[D(2), True, '4', NULL])
        table.group_by('Key', 'Amount')
        self.assertEqual([row.get_member('Amount') for row in table], [D(2), D(0), D(0)])

    def test_dates_and_qualified_numbers(self):
        dates = [literal_date('2024010' + str(i)) for i in range(1, 5)]
        table = sample(TD('Дата'), dates)
        table.group_by('Key', 'Amount')
        self.assertEqual([row.get_member('Amount') for row in table],
                         [literal_date('00010101'), dates[1], dates[3]])
        table = sample(TD('Число', BSLNumberQualifiers(D(2), D(0))), [D(99)] * 4)
        table.group_by('Key', 'Amount')
        self.assertEqual([row.get_member('Amount') for row in table], [D(99)] * 3)

    def test_exact_sum_does_not_depend_on_ambient_context(self):
        table = sample(values=[D('12345678901234567890'), D(3), D('0.01'), D(5)])
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.traps[Inexact] = ctx.traps[Rounded] = True
            table.group_by('Key', 'Amount')
        self.assertEqual(table.rows[0].get_member('Amount'), D('12345678901234567890.01'))

    def test_unobserved_key_rejected_atomically(self):
        table = sample(keys=[BSLArray(), 'A', 'B', 'C'])
        before = state(table)
        with self.assertRaises(ValueError):
            table.group_by('Key', 'Amount')
        self.assertEqual(state(table), before)

    def test_native_singletons_and_per_merge_clamping(self):
        table = sample(TD('Строка'), ['002', ' 3 ', 'bad'], ['A', 'B', 'C'])
        table.group_by('Key', 'Amount')
        self.assertEqual([row.get_member('Amount') for row in table], ['002', ' 3 ', 'bad'])
        table = sample(TD('Число', BSLNumberQualifiers(D(2), D(0))),
                       [D(99), D(99), D(-99), D(1)], ['B', 'B', 'B', 'C'])
        table.group_by('Key', 'Amount')
        self.assertEqual([row.get_member('Amount') for row in table], [D(0), D(1)])

    def test_unmeasured_composite_clamping_rejects_atomically(self):
        table = sample(TD('Число,Строка', BSLNumberQualifiers(D(2), D(0))),
                       [D(99), D(99), D(-99), D(1)], ['B', 'B', 'B', 'C'])
        before = state(table)
        with self.assertRaisesRegex(ValueError, 'составной'):
            group_by(table, 'Key', 'Amount')
        self.assertEqual(state(table), before)

    def test_resource_boundaries_reject_before_mutation(self):
        for target, budget, grouping, totals in [
                ('_MAX_GROUP_CELLS', 7, 'Key', 'Amount'),
                ('_MAX_GROUP_TEXT', 3, 'Key', 'Amount'),
                ('_MAX_COLUMNS', 2, 'Key,,,', 'Amount')]:
            table = sample()
            before = state(table)
            with patch('yadinassi.value_table_group.' + target, budget):
                with self.assertRaises(ValueError):
                    table.group_by(grouping, totals)
            self.assertEqual(state(table), before)
        table = sample()
        before = state(table)
        with patch('yadinassi.value_tables._MAX_TEXT', 2):
            with self.assertRaises(ValueError):
                table.group_by('Key', 'Amount')
        self.assertEqual(state(table), before)


class NativeGroupByTests(unittest.TestCase):
    def test_all_38_native_observations(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        native = (root / 'integrational_tests/output/collections.out').read_text(encoding='utf-8-sig')
        records = dict(re.findall(r'^(table\.ops\.group\.[^:]+): (\[\n.*?^\])', native,
                                  re.MULTILINE | re.DOTALL))
        output = []
        vm = Interpreter(output=output.append)
        vm.execute(source.split('#Область МассивыИСтруктуры', 1)[0])
        count = 0
        for call in observations():
            label, expression = (argument.value for argument in call.arguments)
            if not label.startswith('ops.group.'):
                continue
            with self.subTest(label=label):
                output.clear()
                quoted = expression.replace('"', '""')
                vm.execute('НаблюдатьТаблицы("' + label + '", "' + quoted + '")')
                actual = output[0].split(': ', 1)[1]
                expected = records['table.' + label]
                self.assertEqual(actual, expected)
            count += 1
        self.assertEqual(count, 38)


if __name__ == '__main__':
    unittest.main()
