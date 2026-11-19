"""Exact historic oracle: unittest fails on differences; direct run reports them.

Both entry points validate fixture coverage and data invariants without catching
errors. Only the final historic ID-order comparison is informational in CI.
"""
import argparse
from pathlib import Path
import unittest
from decimal import Decimal
from tests import test_native_target_sort as fixtures
from tests.test_native_target_sort import KEYS, NATIVE_ORDERS, ORDERS, probe_table
from yadinassi.native_targets import LINUX_8_3_27_1508, target_context


def historic_cases():
    check = unittest.TestCase()  # Assertions remain active under python -O.
    fixtures.NativeTargetSortTests().test_fixture_covers_all_96_exact_native_records()
    observed = 0
    with target_context(LINUX_8_3_27_1508):
        for case, expected in NATIVE_ORDERS.items():
            size, insertion, mode = case
            table, original = probe_table(size, insertion)
            container = table.rows
            columns = tuple(table.columns)
            metadata = tuple((c.name, c.title, c.width, id(c.value_type)) for c in columns)
            payloads = {i: tuple(row) for i, row in original.items()}
            for repeat in (1, 2):
                table.sort(ORDERS[mode])
                identifiers = tuple(row.get_member('ID') for row in table.rows)
                check.assertTrue(all(type(value) is Decimal for value in identifiers))
                actual = tuple(int(value) for value in identifiers)
                check.assertEqual(sorted(actual), list(range(1, size + 1)))
                check.assertIs(table.rows, container)
                check.assertEqual(tuple(id(c) for c in table.columns), tuple(id(c) for c in columns))
                check.assertEqual(tuple((c.name, c.title, c.width, id(c.value_type))
                                        for c in table.columns), metadata)
                for identifier, row in zip(actual, table.rows):
                    check.assertIs(row, original[identifier])
                    check.assertIs(row.owner(), table)
                    check.assertEqual(len(row), len(payloads[identifier]))
                    for value, before in zip(row, payloads[identifier]):
                        check.assertIs(value, before)
                observed += 1
                yield (*case, repeat), actual, expected
    check.assertEqual(observed, 96)


class HistoricNativeTableOrderDiagnostic(unittest.TestCase):
    def test_all_96_exact_historic_native_orders(self):
        for case, actual, expected in historic_cases():
            with self.subTest(case=case):
                self.assertEqual(actual, expected)


def _sequence(ids):
    # Quotes make case, spaces, and trailing blanks visible; IDs disambiguate
    # rows with equal text. The fixture controls all values in this report.
    return ', '.join(f'{KEYS[i - 1]!r} (#{i})' for i in ids)


def render(results, limit=None):
    mismatches = [(case, actual, expected) for case, actual, expected in results if actual != expected]
    shown = mismatches if limit is None else mismatches[:limit]
    lines = [
        '### Порядок сортировки ТаблицыЗначений',
        '',
        f'Проверено: {len(results)}/96. Расхождений: {len(mismatches)}. Показано: {len(shown)}.',
        'Основной ключ: текстовая колонка `Key`. В комбинированных режимах `ID` служит вторым ключом.',
        'В списках ниже показано `значение Key (#ID строки)`. Кавычки показывают, где есть пробелы.',
        '',
    ]
    if len(shown) < len(mismatches):
        lines += ['Полный список в артефакте `compatibility-differences-*`.', '']
    for (size, insertion, mode, repeat), actual, expected in shown:
        lines += [
            f'- **{size} строк; вставка `{insertion}`; `{ORDERS[mode]}`; проход {repeat}**',
            f'  - yadinassi: `{_sequence(actual)}`',
            f'  - 1С: `{_sequence(expected)}`',
        ]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary-output', type=Path,
                        help='Write the first 10 examples separately for CI Summary')
    args = parser.parse_args()
    results = list(historic_cases())  # Validate all 96 even when displaying ten.
    if args.summary_output is not None:
        args.summary_output.write_text(render(results, limit=10), encoding='utf-8')
    print(render(results), end='')


if __name__ == '__main__':
    main()
