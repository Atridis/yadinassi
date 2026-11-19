"""Exact historic oracle: unittest fails on differences; direct run reports them.

Both entry points validate fixture coverage and data invariants without catching
errors. Only the final historic ID-order comparison is informational in CI.
"""
import unittest
from decimal import Decimal
from tests import test_native_target_sort as fixtures
from tests.test_native_target_sort import NATIVE_ORDERS, ORDERS, probe_table
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


if __name__ == '__main__':
    results = list(historic_cases())  # Complete validation before reporting success.
    mismatches = [(case, actual, expected) for case, actual, expected in results if actual != expected]
    print(f'### Historic Table order: {len(results)}/96 cases checked; {len(mismatches)} ordering differences')
    print('Ordering differences are informational, not native parity. Data/fixture errors fail this step.')
    for case, actual, expected in mismatches:
        print(f'- {case}: actual={actual}; native={expected}')
