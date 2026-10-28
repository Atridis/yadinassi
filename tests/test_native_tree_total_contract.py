"""Synthetic finite observation controls, not native Total semantic evidence."""
import unittest
from scripts import native_1c_tree_total_contract as contract


def synthetic_payload():
    return b'1' + b'E' * 32


def synthetic_record(payload=None):
    payload = synthetic_payload() if payload is None else payload
    return ('TT', b'TT: [' + payload + b']\n', payload)


def synthetic_records():
    from test_native_tree_move_contract import synthetic_records as move_records
    return move_records() + [synthetic_record()]


def synthetic_output(size=None):
    raw = b''.join(record[1] for record in synthetic_records())
    if size is not None:
        if size < len(raw):
            raise ValueError('synthetic output below grammar minimum')
        raw = raw.replace(b'old0: [ok]', b'old0: [' + b'x' * (size-len(raw)) + b'ok]', 1)
        assert len(raw) == size
    return raw


class TotalContractTests(unittest.TestCase):
    def reject(self, value):
        with self.assertRaisesRegex(contract.ObservationError, '^tree_total_observation_invalid$'):
            contract.validate_payload(value)

    def test_exact_bound_decoding_and_conservative_capture_margin(self):
        self.assertEqual(len(synthetic_payload()), 33)
        self.assertEqual(len(synthetic_record()[1]), 40)
        self.assertEqual(contract.validate_records(synthetic_records()), {'records': 1, 'message_units': 39})
        self.assertEqual(contract.validate_payload(synthetic_payload()), tuple((i, 'exception', None) for i in range(1, 33)))
        # Measured old1022 full-message units, not the former 76-unit estimate.
        self.assertEqual((1048576 - 1023) // 4 - 261827 - 39, 22)

    def test_all_finite_symbols_have_unambiguous_exact_typed_meanings(self):
        base = synthetic_payload()
        for case in range(1, 33):
            numbers = contract.CASE_NUMBERS.get(case, contract.NUMBER_VALUES)
            symbols = b'EUL' + contract.ALPHABET[:len(numbers)]
            decoded = set()
            for code in symbols:
                at = case
                value = base[:at] + bytes([code]) + base[at+1:]
                outcome = contract.validate_payload(value)[case-1]
                self.assertNotIn(outcome, decoded)
                decoded.add(outcome)
            self.assertEqual(len(decoded), len(symbols))

    def test_unknown_and_each_independent_observer_failure_reject_every_case(self):
        base = synthetic_payload()
        for case in range(1, 33):
            at = case
            for symbol in b'!PQRTs Z':
                self.reject(base[:at] + bytes([symbol]) + base[at+1:])
            for symbol in contract.ALPHABET[len(contract.CASE_NUMBERS.get(case, contract.NUMBER_VALUES)):]:
                self.reject(base[:at] + bytes([symbol]) + base[at+1:])

    def test_malformed_version_shape_types_and_framing_reject(self):
        base = synthetic_payload()
        for value in (base[:-1], base+b'S', b'2'+base[1:], base.decode(), bytearray(base), b'!'):
            self.reject(value)
        records = synthetic_records()
        for value in (records[:-1], records+[records[-1]], tuple(records), records[:-1]+[list(records[-1])],
                      records[:-1]+[('TM', records[-1][1], records[-1][2])],
                      records[:-1]+[('TT', records[-1][1]+b'\n', records[-1][2])]):
            with self.assertRaises(contract.ObservationError):
                contract.validate_records(value)
