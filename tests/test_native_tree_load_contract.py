"""Synthetic grammar/negative controls, never native behavioral answers."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tree_load_contract_test', ROOT / 'scripts/native_1c_tree_load_contract.py')
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def synthetic_snapshot(case):
    shape = b'E' if case in (5, 19) else b'N' if case == 6 else b'B'
    cells = b'.' * 48 if shape != b'B' else b'U_' * 24
    kind = contract.SOURCE_KINDS.get(case, b'A')
    if kind in (b'A', b'F'):
        source = kind + b'13' + b'0_1_2_'
    else:
        code = {b'S': b'h_', b'N': b'7_', b'U': b'U_', b'L': b'L_', b'R': b'P0'}[kind]
        source = kind + b'01' + code + b'....'
    return shape * 2 + cells + source


def synthetic_payload(case, *, action=b'0'):
    mutation = (b'1' if action == b'0' else b'3') if case in contract.MUTATIONS else b'0'
    result = b'U_' if case == 34 and action == b'0' else b'--'
    header = b'1' + contract.ALPHABET[case-1:case] + action + mutation + result
    snapshot = synthetic_snapshot(case)
    return header + snapshot + (b'|' + snapshot if case in contract.MUTATIONS else b'')


def synthetic_records():
    records = [(f'old{i}', f'old{i}: [ok]\n'.encode(), b'ok') for i in range(contract.BASE_RECORDS)]
    for case in range(1, 46):
        label, payload = f'TL{case:02d}', synthetic_payload(case)
        records.append((label, label.encode() + b': [' + payload + b']\n', payload))
    return records


def synthetic_output(size=None):
    rows = synthetic_records()
    raw = b''.join(row[1] for row in rows)
    if size is not None:
        if size < len(raw):
            raise ValueError('synthetic output size below grammar minimum')
        # Only an old opaque record is padded; TL widths stay exactly bounded.
        raw = raw.replace(b'old0: [ok]', b'old0: [' + b'x'*(size-len(raw)) + b'ok]', 1)
        assert len(raw) == size
    return raw


class TreeLoadContractTests(unittest.TestCase):
    def reject(self, data, case=1):
        with self.assertRaisesRegex(contract.ObservationError, '^tree_load_observation_invalid$'):
            contract.validate_payload(data, case)

    def test_all45_cases_and_action_failures_remain_observable(self):
        for case in range(1, 46):
            for action in (b'0', b'1'):
                with self.subTest(case=case, action=action):
                    contract.validate_payload(synthetic_payload(case, action=action), case)

    def test_exact_complete_message_majorant_is_not_sample_average(self):
        records = synthetic_records()
        result = contract.validate_records(records)
        self.assertEqual(result, {'records': 45, 'message_units': 3525})
        self.assertEqual(sum(8 + 6 + 59 + (60 if case in contract.MUTATIONS else 0) for case in range(1, 46)), 3525)
        self.assertEqual(3800 - result['message_units'], 275)

    def test_fixed_widths_and_labels(self):
        value = synthetic_payload(1)
        for data in (value[:-1], value+b'x', value[:4]+b'xx'+value[6:], value.replace(b'10', b'11', 1), value.decode()):
            self.reject(data)
        for case in (0, 46, True, '1'):
            self.reject(value, case)
        rows = synthetic_records()
        for changed in (rows[:-1], rows + [rows[-1]], tuple(rows)):
            with self.assertRaises(contract.ObservationError): contract.validate_records(changed)
        rows[-1] = ('TL44', rows[-1][1], rows[-1][2])
        with self.assertRaises(contract.ObservationError): contract.validate_records(rows)

    def test_all_failure_forms_rejected_even_when_bytes_equal(self):
        good = synthetic_payload(1)
        for status in b'SC!?':
            self.reject(good[:2] + bytes([status]) + good[3:])
        self.reject(b'1?S0--' + b'!' + b'.'*58)
        self.reject(good[:6] + b'!' + b'.'*58)
        from scripts import native_1c_full_host as host
        records = synthetic_records()
        whole = b''.join(record[1] for record in records) + __import__('test_native_tree_move_contract').synthetic_record()[1] + __import__('test_native_tree_total_contract').synthetic_record()[1]
        self.assertEqual(host.validate_tree_load_observations(whole)['records'], 45)
        label, _, payload = records[-1]
        payload = payload[:6] + b'!' + b'.'*58
        records[-1] = (label, label.encode()+b': ['+payload+b']\n', payload)
        malformed = b''.join(record[1] for record in records) + __import__('test_native_tree_move_contract').synthetic_record()[1] + __import__('test_native_tree_total_contract').synthetic_record()[1]
        for identical_side in (malformed, malformed):
            with self.assertRaisesRegex(host.FullError, '^tree_load_observation_invalid$'):
                host.validate_tree_load_observations(identical_side)

    def test_scalar_type_codes_do_not_collapse_lookalikes(self):
        value = synthetic_payload(1)
        for char in contract.SCALAR_CODES:
            contract.validate_payload(value[:8]+bytes([char])+b'_'+value[10:],1)
        for code in (b'8_', b'Z_', b'T0', b'..', b'--', b'\xff_'):
            self.reject(value[:8]+code+value[10:])

    def test_structure_identity_same_snapshot_requires_same_mark(self):
        value = synthetic_payload(1)
        contract.validate_payload(value[:8]+b'P0P0'+value[12:],1)
        contract.validate_payload(value[:8]+b'P0Q1'+value[12:],1)
        self.reject(value[:8]+b'P0Q0'+value[12:])
        self.reject(value[:8]+b'P5'+value[10:])
        self.reject(value[:8]+b'P1'+value[10:])
        for identifier in (b'y',b'z',b'_',b'.'):
            self.reject(value[:8]+b'P'+identifier+value[10:])
        value = synthetic_payload(37)
        first = value[6:65]
        second = value[66:]
        contract.validate_payload(value[:6]+first[:2]+b'P0'+first[4:]+b'|'+second[:2]+b'Q0'+second[4:],37)

    def test_mutation_phase_and_expression_contract(self):
        value = synthetic_payload(37)
        contract.validate_payload(value[:3]+b'2'+value[4:],37)
        for data in (value[:3]+b'0'+value[4:], value[:65]+b';'+value[66:], synthetic_payload(37,action=b'1')[:3]+b'1'+value[4:]):
            self.reject(data,37)
        value=synthetic_payload(34)
        self.reject(value[:4]+b'--'+value[6:],34)
        self.reject(synthetic_payload(34,action=b'1')[:4]+b'U_'+value[6:],34)

    def test_schema_empty_padding_and_source_slots(self):
        value=synthetic_payload(5)
        self.reject(value[:8]+b'U_'+value[10:],5)
        for case in range(1,46):
            value=synthetic_payload(case)
            self.reject(value[:6]+b'NN'+value[8:],case) if case!=6 else None
            self.reject(value[:56]+b'Z'+value[57:],case)
        value=synthetic_payload(26)
        self.reject(value[:59]+b'7_'+value[61:],26)
        self.reject(value[:57]+b'1'+value[58:],26)
        self.reject(value[:58]+b'0'+value[59:],26)
        self.reject(value[:61]+b'U_'+value[63:],26)


if __name__ == '__main__': unittest.main()
