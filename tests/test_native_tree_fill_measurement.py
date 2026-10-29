"""Synthetic observer validity, never native FillValues semantic evidence."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest import mock
from yadinassi import Interpreter
from yadinassi.values import HostFunction
from yadinassi.value_trees import BSLValueTreeRowCollection as Rows
from scripts import native_1c_tree_fill_contract as contract

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'integrational_tests/measurements/tree_fill_values.bsl').read_text(encoding='utf-8')
HELPERS = SOURCE[:SOURCE.index('Calibration = TreeFillCalibrate();')]


def vm(source=HELPERS):
    value = Interpreter()
    value.execute(source)
    return value


class FillObserverTests(unittest.TestCase):
    def test_all32_fixtures_and_calibration_without_action(self):
        output = []
        value = Interpreter(output.append)
        original = Rows.get_method
        def missing(rows, name):
            if name.casefold() in ('fillvalues', 'заполнитьзначения'):
                raise ValueError('synthetic unavailable action')
            return original(rows, name)
        with mock.patch.object(Rows, 'get_method', missing):
            value.execute(SOURCE)
        raw = ('\n'.join(output) + '\n').encode('ascii')
        observations = contract.validate_output(raw)
        self.assertEqual(len(observations), 32)
        self.assertTrue(all(item['outcome'] == 'exception' for item in observations))
        self.assertLessEqual(len(raw), contract.MAX_OUTPUT_BYTES)
        self.assertEqual(len(raw), 6017)

    def run_action(self, action, case=2):
        original = Rows.get_method
        def method(rows, name):
            if name.casefold() in ('fillvalues', 'заполнитьзначения'):
                return HostFunction(name, lambda *args: action(rows, args))
            return original(rows, name)
        with mock.patch.object(Rows, 'get_method', method):
            value = vm()
            value.execute(f'Result=TreeFillProbe({case});')
        return value.variables['result']

    def test_success_and_partial_write_exception_remain_distinct(self):
        def write(rows, args):
            rows.items[0].set_member('Key', args[0])
        successful = self.run_action(write)
        def partial(rows, args):
            write(rows, args)
            raise ValueError('synthetic after first cell')
        failed = self.run_action(partial)
        self.assertEqual(successful[1:], failed[1:])
        self.assertEqual(successful[0], 'S')
        self.assertEqual(failed[0], 'E')
        observed = contract.validate_payload(failed.encode(), 2)
        self.assertNotEqual(observed['before'], observed['after'])
        self.assertEqual(observed['after'][1], ('scalar', '4'))

    def test_non_action_schema_and_identity_corruption_is_diagnostic(self):
        actions = [lambda r, a: r.items.reverse(),
                   lambda r, a: r.items[0].rows.items.clear(),
                   lambda r, a: r.tree.columns.items[0].set_member('Title', 'broken')]
        for action in actions:
            with self.subTest(action=action):
                result = self.run_action(action)
                self.assertEqual(result, 'Q')
                with self.assertRaises(contract.ObservationError):
                    contract.validate_payload(result.encode(), 2)

    def test_alias_and_equal_but_distinct_structure_are_observable(self):
        def shared(rows, args):
            rows.items[0].set_member('Key', args[0])
        from yadinassi.structures import BSLStructure
        def copied(rows, args):
            rows.items[0].set_member('Key', BSLStructure('Mark', 'base'))
        first = contract.validate_payload(self.run_action(shared, 31).encode(), 31)
        second = contract.validate_payload(self.run_action(copied, 31).encode(), 31)
        self.assertEqual(first['after'][1], ('reference', 'P', 0))
        self.assertEqual(first['shared'][1], ('reference', 'Q', 0))
        self.assertEqual(second['after'][1], ('reference', 'P', 1))
        self.assertEqual(second['shared'][1], ('reference', 'P', 1))

    def test_unknown_cell_value_fails_closed_not_action_exception(self):
        result = self.run_action(lambda rows, args: rows.items[0].set_member('Key', Decimal(987654)))
        self.assertEqual(result, 'Q')

    def test_precondition_mismatch_and_checker_failure_are_distinct(self):
        before = 'Before = TreeFillSnapshot(S, Value, Original, Refs);'
        for replacement, expected in [(before + ' S.Nodes[0].Key = 7;', 'E'),
                                      ('S.Nodes[0].Key = 7; ' + before, 'B'),
                                      ('S = Неопределено; ' + before, 'P')]:
            value = vm(HELPERS.replace(before, replacement))
            value.execute('Result=TreeFillProbe(2);')
            self.assertTrue(value.variables['result'].startswith(expected))


class FillContractTests(unittest.TestCase):
    def test_reference_registry_and_observer_mutation_are_consistent(self):
        before = contract.baseline(31)
        # Synthetic valid observations, not assumed native FillValues results:
        # one source alias and one equal-but-distinct object.
        after = before[:4] + 'P0' + before[6:12] + 'P1' + before[14:]
        shared = after[:4] + 'Q0' + after[6:53] + 'Q0' + after[55:]
        contract.validate_payload(('S' + before + after + shared).encode(), 31)
        changes = [
            # Missing first identities and contradictory same-object marks.
            (after[:12] + 'PZ' + after[14:], shared[:12] + 'PZ' + shared[14:]),
            (after[:12] + 'Q0' + after[14:], shared),
            # No tree operation occurs between After and Shared.
            (after, shared[:2] + '7_' + shared[4:]),
            (after, shared[:12] + 'P2' + shared[14:]),
            (after, shared[:12] + 'Q1' + shared[14:]),
            (after, shared[:4] + 'P0' + shared[6:]),
        ]
        for changed_after, changed_shared in changes:
            with self.subTest(after=changed_after, shared=changed_shared):
                with self.assertRaises(contract.ObservationError):
                    contract.validate_payload(('S' + before + changed_after + changed_shared).encode(), 31)

    def test_rejects_truncation_unknown_codes_bad_baseline_and_instability(self):
        value = vm()
        value.execute('Result=TreeFillProbe(2);')
        good = value.variables['result'].encode()
        contract.validate_payload(good, 2)
        invalid = [good[:-1], good+b'x', b'Q'+good[1:], good[:3]+b'?'+good[4:],
                   good[:65]+b'?'+good[66:], good[:-8]+b'7'+good[-7:]]
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaises(contract.ObservationError):
                    contract.validate_payload(data, 2)

    def test_output_framing_is_exact(self):
        value = vm()
        payloads = []
        for case in range(1, 33):
            value.execute(f'Result=TreeFillProbe({case});')
            payloads.append(f'TF-{case}: ['.encode() + value.variables['result'].encode() + b']\n')
        good = b'TF-C: [-]\n' + b''.join(payloads)
        contract.validate_output(good)
        bad = [good.replace(b'TF-C: [-]', b'TF-C: [G]'), good.replace(b'\n', b'\r\n'),
               good[:-1], good + payloads[-1], b'TF-C: [-]\n' + b''.join(reversed(payloads)),
               b'TF-C: [-]\n' + b''.join(payloads[:-1]), good + b'x' * 8192]
        for raw in bad:
            with self.subTest(size=len(raw)):
                with self.assertRaises(contract.ObservationError):
                    contract.validate_output(raw)
