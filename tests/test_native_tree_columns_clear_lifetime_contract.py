"""Constructive bounds and strict checkpoint negatives for immutable CL6."""
import json
import unittest
from scripts import native_1c_tree_columns_clear_lifetime_contract as wire
from test_native_tree_columns_clear_contract import maximum_snapshot


def maximum_output(available=False, status='S'):
    lines = [wire.CALIBRATION_RECORD]
    for case, count in enumerate(wire.ACTION_COUNTS, 1):
        parts = []
        for index in range(count + 1):
            phase = 3 if index == 2 and case in (4, 5, 6) else 1
            head = '-0' if index == 0 or (index > 1 and status != 'S') else status + str(phase)
            snapshot = '000' + 'E_' * 24 if available and case <= 2 and index == 1 else maximum_snapshot()
            parts.append(head + '~' + snapshot + '~' + 'E_' * 16)
        lines.append(f'CL-{case}: [{"/".join(parts)}]\n'.encode('ascii'))
    return b''.join(lines)


class LifetimeContractTests(unittest.TestCase):
    def test_exact_maximum_and_marker(self):
        raw = maximum_output()
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(raw), 5147)
        self.assertEqual(wire.snapshot_size(), 207)
        self.assertEqual(len(wire.validate_output(raw)), 6)
        envelope = {'completed': True, 'output': raw.decode('ascii'), 'nonce': '0' * 32}
        self.assertLess(len(json.dumps(envelope).encode('ascii')), 16384)
        self.assertLess(len(raw), 8192)

    def test_only_clear_controls_gate_availability(self):
        with self.assertRaises(wire.AvailabilityError): wire.require_available(maximum_output())
        self.assertEqual(len(wire.require_available(maximum_output(available=True))), 6)
        for status in 'MAO':
            with self.subTest(status=status), self.assertRaises(wire.AvailabilityError): wire.require_available(maximum_output(available=True, status=status))

    def test_empty_before_controls_and_invalid_case_domain(self):
        raw=maximum_output(available=True)
        snapshot=maximum_snapshot();empty='000'+'E_'*24
        raw=raw.replace(('-0~'+snapshot+'~').encode(),('-0~'+empty+'~').encode())
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)
        for case in (True,False,0,7,'1',None):
            with self.assertRaises(wire.ObservationError): wire.maximum_record_size(case)

    def test_strict_framing_and_checkpoint_order(self):
        raw = maximum_output()
        variants = [raw+b'x',raw.replace(b'CL-1:',b'CL-0:',1),raw.replace(b'CL-C1: [-]',b'CL-C1: [E]'),raw.replace(b'-0~',b'S1~',1),raw.replace(b'S1~',b'S0~',1),raw.replace(b'S3~',b'S2~',1),raw.replace(b'~E_E_',b'~E_',1),raw.replace(b'~E_E_',b'~Z_E_',1),raw.replace(b'/S1~',b'/--~',1),b'x'*8193]
        for mutated in variants:
            with self.subTest(mutated=mutated[:40]), self.assertRaises(wire.ObservationError): wire.validate_output(mutated)

    def test_extra_types_new_identities_and_independent_parents(self):
        registry = ['tree', 'row']
        raw = 'N1I1I2' * 4 + 'I2I0I_N0'
        extra = wire.decode_extra(raw, registry)
        self.assertEqual(extra[1], ('I', 1)); self.assertEqual(extra[14], ('I', None))
        self.assertEqual(registry, ['tree', 'row', 'row'])
        for wrong in ('N1I0I2', 'N1I1I9', 'N1I1I_'):
            with self.assertRaises(wire.ObservationError): wire.decode_extra(wrong + raw[6:], ['tree', 'row'])

    def test_first_failure_skips_but_later_errors_remain_observations(self):
        raw = maximum_output(status='O'); wire.validate_output(raw)
        with self.assertRaises(wire.ObservationError): wire.validate_output(raw.replace(b'/-0~', b'/S1~', 1))
        raw = maximum_output().replace(b'S3~', b'O2~', 1)
        self.assertEqual(wire.validate_output(raw)[3]['checkpoints'][2]['phase'], 2)

    def test_private_diagnostics_never_admitted(self):
        for token in (b'private password', b'XO', b'\xff', b'\r'):
            with self.assertRaises(wire.ObservationError): wire.validate_output(maximum_output().replace(b'E_',token,1))


if __name__ == '__main__': unittest.main()
