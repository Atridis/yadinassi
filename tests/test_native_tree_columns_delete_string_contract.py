"""Strict DS6 finite framing; no assumed named-selector outcomes."""
import unittest
from scripts import native_1c_tree_columns_delete_string_contract as wire
from test_native_tree_columns_delete_contract import snapshot

def maximum_output(status='S'):
    lines=[wire.CALIBRATION_RECORD]
    for case in range(1,7):
        header=status+('-0U_' if case>=5 and status=='S' else '-0--')
        lines.append(f'DS-{case}: [{header}/{snapshot()}/{snapshot()}]\n'.encode('ascii'))
    return b''.join(lines)

class DeleteStringContractTests(unittest.TestCase):
    def test_constructive_bound_and_all_statuses(self):
        self.assertEqual(len(maximum_output()),wire.MAX_ENCODED_BYTES)
        self.assertLess(wire.MAX_ENCODED_BYTES,8192)
        for status in 'SMAO':
            self.assertEqual([r['status'] for r in wire.validate_output(maximum_output(status))],[status]*6)
            with self.assertRaises(wire.AvailabilityError):wire.require_available(maximum_output(status))
    def test_strict_framing_and_expression_domains(self):
        raw=maximum_output()
        for bad in (raw+b'x',raw.replace(b'DS-C1: [-]',b'DS-C1: [E]'),raw.replace(b'DS-1:',b'DS-0:'),
                    raw.replace(b'DS-5: [S-0U_',b'DS-5: [S-0--'),raw.replace(b'DS-1: [S-0--',b'DS-1: [S-0U_'),
                    raw.replace(b'WdN9',b'WzN9'),raw.replace(b'E_',b'private detail',1),raw.replace(b'E_',b'\xff',1),b'x'*8193):
            with self.subTest(bad=bad[:30]),self.assertRaises(wire.ObservationError):wire.validate_output(bad)
        for case in (False,True,0,7,None,'1'):
            with self.assertRaises(wire.ObservationError):wire.maximum_record_size(case)
