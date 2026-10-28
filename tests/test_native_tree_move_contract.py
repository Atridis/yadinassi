"""Synthetic finite-domain tests, not native Move semantic answers."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('tree_move_contract_test', ROOT / 'scripts/native_1c_tree_move_contract.py')
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def synthetic_payload():
    return b'1' + b''.join(b'0' + (b'-----' if case == 25 else b'A----' if case == 26 else b'ABCDE')
                           for case in range(1, 33))


def synthetic_record(payload=None):
    payload = synthetic_payload() if payload is None else payload
    return ('TM', b'TM: [' + payload + b']\n', payload)


def synthetic_records():
    from test_native_tree_load_contract import synthetic_records as load_records
    return load_records() + [synthetic_record()]


def synthetic_output(size=None):
    raw = b''.join(row[1] for row in synthetic_records())
    if size is not None:
        if size < len(raw):
            raise ValueError('synthetic output size below grammar minimum')
        raw = raw.replace(b'old0: [ok]', b'old0: [' + b'x' * (size-len(raw)) + b'ok]', 1)
        assert len(raw) == size
    return raw


class TreeMoveContractTests(unittest.TestCase):
    def reject(self, payload):
        with self.assertRaisesRegex(contract.ObservationError, '^tree_move_observation_invalid$'):
            contract.validate_payload(payload)

    def test_exact_bound_and_typed_decode(self):
        payload = synthetic_payload()
        self.assertEqual(len(payload), 193)
        result = contract.validate_payload(payload)
        self.assertEqual(len(result), 32)
        self.assertEqual(result[24], (25, b'0', b'-----'))
        self.assertEqual(contract.validate_records([None] * 1021 + [synthetic_record()]),
                         {'records': 1, 'message_units': 199})
        self.assertEqual(3800 - 3525 - 199, 76)

    def test_all_admitted_orders_and_action_outcomes(self):
        for case in range(1, 33):
            orders = (b'-----',) if case == 25 else (b'A----',) if case == 26 else tuple(
                r + c for r in contract.ROOT_ORDERS for c in contract.CHILD_ORDERS)
            for order in orders:
                for outcome in ((b'0', b'2') if case == 32 else (b'0', b'1')):
                    at = 1 + (case - 1) * 6
                    data = synthetic_payload()
                    contract.validate_payload(data[:at] + outcome + order + data[at+6:])

    def test_failure_markers_and_invalid_permutations_never_accept(self):
        data = synthetic_payload()
        for part in (b'!ABCDE', b'?ABCDE', b'2ABCDE', b'0AACDE', b'0ABCDF', b'0ABDCE', b'0ABC--', b'0abcde'):
            self.reject(data[:1] + part + data[7:])
        self.reject(data[:-6] + b'1ABCDE')
        for bad in (data[:-1], data+b'0', b'2'+data[1:], data.decode(), bytearray(data), b'!'):
            self.reject(bad)

    def test_empty_singleton_shapes_cannot_be_interchanged(self):
        data = synthetic_payload()
        for case in (25, 26):
            at = 1 + (case-1)*6
            self.reject(data[:at] + b'0ABCDE' + data[at+6:])

    def test_exact_records_and_framing(self):
        good = [None] * 1021 + [synthetic_record()]
        for bad in (good[:-1], good+[good[-1]], tuple(good), good[:-1]+[list(good[-1])],
                    good[:-1]+[('TL',good[-1][1],good[-1][2])],
                    good[:-1]+[('TM',good[-1][1]+b'\n',good[-1][2])]):
            with self.assertRaises(contract.ObservationError):
                contract.validate_records(bad)


if __name__ == '__main__':
    unittest.main()
