"""Synthetic property-transfer witnesses test the observer, not native semantics."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import unittest

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508
from yadinassi.syntax.parser import parse
from yadinassi.structures import BSLStructure, BSLFixedStructure
from yadinassi.value_tables import BSLValueTableRow
from yadinassi.value_trees import BSLValueTreeRow

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_property_transfer_contract as wire

SOURCE = (ROOT / 'integrational_tests/measurements/property_transfer.bsl').read_text(encoding='utf-8')
SOURCE_SHA = '25abcace2821e4d03da731e4cf96a97a33348f21a58ee291399232c51ad5e7c8'
HELPERS = SOURCE.split('\nСообщить("PV-C1: [wire-v1]");\n', 1)[0]
MAPPING = json.loads((ROOT / 'tests/fixtures/property_transfer/original48-mapping.json').read_text(encoding='utf-8'))


def noop(*args):
    pass


def configure(vm, action):
    vm.register_function('FillPropertyValues', action, 'ЗаполнитьЗначенияСвойств', returns_value=False)


def emit(action=noop):
    output = []
    vm = Interpreter(output.append, native_target=LINUX_8_3_27_1508)
    configure(vm, action)
    vm.execute(SOURCE)
    return ('\n'.join(output) + '\n').encode('ascii')


def case_record(case, action=noop):
    vm = Interpreter(native_target=LINUX_8_3_27_1508)
    configure(vm, action)
    vm.execute(HELPERS)
    vm.execute(f'Result = PVProbe({case});')
    payload = vm.variables['result'].encode('ascii')
    line = f'PV-{case:02}: ['.encode() + payload + b']\n'
    # Independent fixed synthetic filler records are not semantic expectations.
    snapshot = b'U_' * 10 + b'S0------S0------A0-U_U_'
    lines = [f'PV-{n:02}: [S/'.encode() + b'/'.join([snapshot] * 3) + b']\n' for n in range(1, 49)]
    lines[case - 1] = line
    return wire.validate_output(wire.CALIBRATION + b''.join(lines))[case - 1]


class PropertyTransferObserverTests(unittest.TestCase):
    def test_source_pin_archive_and_unacquired_mapping(self):
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(), SOURCE_SHA)
        self.assertEqual((ROOT / 'tests/fixtures/property_transfer/original48.bsl').read_bytes(), SOURCE.encode())
        self.assertEqual(MAPPING['source_sha256'], SOURCE_SHA)
        self.assertEqual(MAPPING['evidence_status'], 'not_acquired')
        self.assertFalse(MAPPING['native_measurement_accepted'])
        self.assertFalse(MAPPING['runtime_parity_accepted'])
        self.assertEqual([r['case'] for r in MAPPING['cases']], list(range(1, 49)))
        self.assertEqual(len({(r['topic'], r['target']) for r in MAPPING['cases']}), 48)
        parse(SOURCE)
        for forbidden in ('ОписаниеОшибки', 'Вычислить(', 'Выполнить(', 'Metadata', 'Метаданные', '.Write('):
            self.assertNotIn(forbidden, SOURCE)
        self.assertEqual(SOURCE.count('Сообщить('), 3)
        self.assertIn('Для Case = 1 По 48 Цикл', SOURCE)

    def test_all48_fixtures_are_observable_with_noop_action_and_fit_cap(self):
        raw = emit()
        records = wire.require_available(raw)
        self.assertEqual(len(records), 48)
        self.assertTrue(all(r['status'] == 'ok' for r in records))
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertEqual(wire.MAX_ENCODED_BYTES, 6903)
        self.assertEqual(wire.MAX_RECORD_BYTES, 143)
        self.assertEqual(wire.MAX_OUTPUT_BYTES, 8192)
        for row in records:
            self.assertEqual(row['snapshots'][0]['shared'], 'A0')
            self.assertEqual(row['snapshots'][2]['shared'], 'A1')

    def test_fixed_cross_container_directions_reach_action_unchanged(self):
        kinds = {BSLStructure: 'Structure', BSLFixedStructure: 'FixedStructure',
                 BSLValueTableRow: 'ValueTableRow', BSLValueTreeRow: 'ValueTreeRow'}
        for case in range(5, 15):
            seen = []
            record = case_record(case, lambda target, source, *args: seen.append((kinds[type(target)], kinds[type(source)])))
            self.assertEqual(record['status'], 'ok')
            expected = MAPPING['cases'][case - 1]
            self.assertEqual(seen, [(expected['target'], expected['source'])])

    def test_include_exclude_undefined_and_ignored_type_inputs_are_exact(self):
        for case in range(15, 35):
            seen = []
            case_record(case, lambda target, source, *args: seen.append(args))
            row = MAPPING['cases'][case - 1]
            mode = (case - 15) % 10
            expected = (row['selection'],) if mode < 5 else (None, row['exclude']) if mode < 8 else (row['selection'], row['exclude'])
            self.assertEqual(seen, [expected])

    def test_action_failure_records_partial_writes_without_error_text(self):
        def partial(target, source, *args):
            target.set_member('First', source.get_member('First'))
            raise ValueError('PRIVATE message must not escape')
        row = case_record(5, partial)
        self.assertEqual(row['status'], 'action-error')
        before, after, shared = row['snapshots']
        self.assertEqual(before['target'][0], 'N1')
        self.assertEqual(after['target'][0], 'NA')
        self.assertEqual(after['target'][1], before['target'][1])
        self.assertEqual(after['source'], before['source'])
        self.assertEqual(shared['target'], after['target'])
        self.assertNotIn(b'PRIVATE', emit(partial))

    def test_normal_setter_index_updates_and_order_are_observable(self):
        def copy(target, source, *args):
            target.set_member('First', source.get_member('First'))
        row = case_record(5, copy)
        before, after, _ = row['snapshots']
        self.assertEqual(before['target_shape'], 'T32-1100')
        self.assertEqual(after['target_shape'], 'T32-0201')
        self.assertEqual(after['source_shape'], before['source_shape'])

    def test_shallow_reference_mutation_distinguishes_copy_from_alias(self):
        def alias(target, source, *args):
            target.set_member('Last', source.get_member('Last'))
        for case in (47, 48):
            observed = case_record(case, alias)['snapshots']
            self.assertEqual(observed[1]['target'][1], 'A0')
            self.assertEqual(observed[2]['target'][1], 'A1')
            self.assertEqual(observed[2]['source'][1], 'A1')
            def cloned(target, source, *args):
                from yadinassi.values import BSLArray
                value = BSLArray()
                value.items = list(source.get_member('Last').items)
                target.set_member('Last', value)
            copied = case_record(case, cloned)['snapshots']
            self.assertEqual(copied[1]['target'][1], 'A2')
            self.assertEqual(copied[2]['target'][1], 'A2')

    def test_readonly_source_identity_and_scalar_cells_are_observed_separately(self):
        def copy(target, source, *args):
            target.set_member('Parent', source.get_member('Parent'))
            target.set_member('Rows', source.get_member('Rows'))
        row = case_record(45, copy)
        self.assertEqual(row['status'], 'ok')
        before, after, _ = row['snapshots']
        self.assertEqual(before['target'][3:], ('U_', 'U_'))
        self.assertEqual(after['target'][3:], ('R3', 'C1'))
        self.assertEqual(after['source'][3:], ('R3', 'C1'))
        self.assertEqual(after['source_shape'], before['source_shape'])

    def test_typed_reference_setter_observation_does_not_assert_native_result(self):
        for case in range(35, 41):
            before, after, _ = case_record(case)['snapshots']
            self.assertIn(before['setter_status'], ('S', 'E'))
            self.assertEqual(after['setter_status'], before['setter_status'])
            self.assertEqual(after['setter_values'], before['setter_values'])
            self.assertEqual(after['target'], before['target'])

    def test_unknown_observer_value_is_not_mislabeled_action_failure(self):
        def unsupported(target, source, *args):
            target.set_member('Last', 'PRIVATE OUTSIDE FINITE DOMAIN')
        row = case_record(5, unsupported)
        self.assertEqual((row['status'], row['stage']), ('observer-error', 2))
        raw = emit(unsupported)
        self.assertNotIn(b'PRIVATE', raw)
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)

    def test_controls_and_observer_failures_cannot_pass_availability(self):
        raw = emit()
        for case in (1, 2, 3, 4):
            modified = raw.replace(f'PV-{case:02}: [S/'.encode(), f'PV-{case:02}: [E/'.encode(), 1)
            with self.assertRaises(wire.AvailabilityError):
                wire.require_available(modified)
        lines = raw.splitlines(keepends=True)
        lines[6] = b'PV-05: [X2]\n'
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(b''.join(lines))
        modified = raw.replace(b'PV-05: [S/', b'PV-05: [E/', 1)
        self.assertEqual(wire.require_available(modified)[4]['status'], 'action-error')

    def test_noncanonical_framing_and_snapshot_domains_fail_closed(self):
        raw = emit()
        for bad in (raw[:-1], raw+b'\n', raw.replace(b'\n', b'\r\n'), bytearray(raw), raw.decode(),
                    raw.replace(b'PV-01:', b'PV-02:', 1), raw.replace(b'wire-v1', b'wire-v2', 1),
                    raw.replace(b'N1S1', b'NZS1', 1), raw.replace(b'T32-', b'T32/', 1), b'x'*8193):
            with self.assertRaises(wire.ObservationError):
                wire.validate_output(bad)
        for bad in (b'X9', b'S', b'E/x/x/x', b'private'):
            lines = raw.splitlines(keepends=True)
            lines[6] = b'PV-05: [' + bad + b']\n'
            with self.assertRaises(wire.ObservationError):
                wire.validate_output(b''.join(lines))


if __name__ == '__main__':
    unittest.main()
