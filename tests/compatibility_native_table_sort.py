"""Report exact historic ValueTable orders: 96 Linux records and four BSL probes.

The CLI validates coverage and data invariants without catching errors. Only
the final historic ID-order comparisons are informational in CI. The unittest
entry point separately enforces the exact 96 Linux orders when run explicitly.
"""
import argparse
from contextlib import closing
import re
from pathlib import Path
import unittest
from decimal import Decimal
from tests import test_native_target_sort as fixtures
from tests.test_native_target_sort import KEYS, NATIVE_ORDERS, ORDERS, probe_table
from tests import test_value_table_sort as bsl_fixtures
from yadinassi import Interpreter
from yadinassi.execution.codegen.native_targets import LINUX_8_3_27_1508, target_context


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


def _sequence(ids, show_ids):
    # Quotes make case, spaces, and trailing blanks visible; IDs disambiguate
    # rows with equal text. The fixture controls all values in this report.
    return ', '.join(repr(KEYS[i - 1]) + (f' (#{i})' if show_ids else '') for i in ids)


def render(results, limit=None, *, show_ids=True):
    mismatches = [(case, actual, expected) for case, actual, expected in results if actual != expected]
    shown = mismatches if limit is None else mismatches[:limit]
    lines = [
        '### Порядок сортировки ТаблицыЗначений',
        '',
        f'Проверено: {len(results)}/96. Расхождений: {len(mismatches)}. Показано: {len(shown)}.',
        'Основной ключ: текстовая колонка `Key`. В комбинированных режимах `ID` служит вторым ключом.',
        ('Показаны значения `Key` и ID строк.' if show_ids else 'Показаны только значения `Key`.')
        + ' Кавычки показывают, где есть пробелы.',
        '',
    ]
    if len(shown) < len(mismatches):
        lines += ['Полный список в артефакте `compatibility-differences-*`.', '']
    for (size, insertion, mode, repeat), actual, expected in shown:
        lines += [
            f'- **{size} строк; вставка `{insertion}`; `{ORDERS[mode]}`; проход {repeat}**',
            f'  - yadinassi: `{_sequence(actual, show_ids)}`',
            f'  - 1С: `{_sequence(expected, show_ids)}`',
        ]
    return '\n'.join(lines) + '\n'


def bsl_order_cases():
    check = unittest.TestCase()
    source = bsl_fixtures.sort_probe_source()
    start = source.index('Функция СортировкаТаблицыПробы(')
    probe = source[start:source.index('КонецФункции', start)]
    keys = {}
    for dataset in ('locale', 'utf16-boundary'):
        literals = re.findall(fr'(?m)^    (?:Если|ИначеЕсли) Набор = "{dataset}" Тогда\n'
                              r'        Ключи = ЗначенияОперацийТаблицы\("([^"]+)"\);$', probe)
        check.assertEqual(len(literals), 1, dataset)
        # ЗначенияОперацийТаблицы uses СтрРазделить with empty elements disabled.
        keys[dataset] = [key for key in literals[0].split('|') if key != '']
    cases = [case for case in bsl_fixtures.NATIVE_CASES
             if case[:3] in bsl_fixtures.ADVISORY_ORDER_CASES]
    check.assertCountEqual([case[:3] for case in cases], bsl_fixtures.ADVISORY_ORDER_CASES)
    with closing(Interpreter()) as vm:
        vm.execute(source)
        for case in cases:
            dataset, order, _, _, native = case
            check.assertEqual(sorted(native), list(range(1, len(keys[dataset]) + 1)))
            actual = bsl_fixtures.observe_native_case(check, vm, case)
            yield dataset, order, keys[dataset], actual, native


def render_bsl_orders(results):
    differences = sum(actual != native for _, _, _, actual, native in results)
    lines = ['', '### Порядок строк: четыре исторические BSL-пробы', '',
             f'Проверено: {len(results)}/4. Расхождений: {differences}.',
             'Эталон: 1С 8.3.27.2342 / Windows; yadinassi: BSL, профиль по умолчанию.',
             'Только точный порядок считается диагностикой. Статус, все строки и ссылка на исходную строку проверяются в Light.',
             'Ключи показаны в кавычках, чтобы были видны пробелы.', '']
    for dataset, order, keys, actual, native in results:
        if actual == native:
            continue
        lines.append(f'- **{dataset}; `{order}`**')
        for label, ids in (('yadinassi', actual), ('1С', native)):
            sequence = ', '.join(repr(keys[int(identifier) - 1]) for identifier in ids)
            lines.append(f'  - {label}: `{sequence}`')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary-output', type=Path,
                        help='Write up to 10 historical examples and any differing BSL probes for CI Summary')
    args = parser.parse_args()
    results = list(historic_cases())  # Validate all 96 even when displaying ten.
    bsl_orders = render_bsl_orders(list(bsl_order_cases()))
    if args.summary_output is not None:
        args.summary_output.write_text(render(results, limit=10, show_ids=False) + bsl_orders,
                                       encoding='utf-8')
    print(render(results) + bsl_orders, end='')


if __name__ == '__main__':
    main()
