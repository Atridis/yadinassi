"""Strict finite DL14 framing and exact constructive resource bound."""
import unittest
from scripts import native_1c_tree_columns_delete_contract as wire
from test_native_tree_columns_clear_contract import maximum_snapshot


def snapshot():
    value=maximum_snapshot().replace('1aa9','1ad9',1)
    queries=['E_']*24;queries[14]='I1';queries[16]='Wd';queries[17]='N9'
    return value[:-48]+''.join(queries)


def maximum_output(status='S'):
    lines=[wire.CALIBRATION_RECORD]
    for case in range(1,15):
        header=status+('-0U_' if case==10 and status=='S' else 'S5--' if case==14 and status=='S' else 'S1--' if case>=11 and status=='S' else '-0--')
        lines.append(f'DL-{case}: [{header}/{snapshot()}/{snapshot()}]\n'.encode('ascii'))
    return b''.join(lines)


class DeleteContractTests(unittest.TestCase):
    def test_exact_constructive_bound(self):
        raw=maximum_output();self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(wire.validate_output(raw)),14);self.assertLess(len(raw),8192)

    def test_closed_framing_and_header_shapes(self):
        raw=maximum_output()
        for bad in (raw+b'x',raw.replace(b'DL-C1: [-]',b'DL-C1: [E]'),raw.replace(b'DL-1:',b'DL-0:'),
                    raw.replace(b'DL-10: [S-0U_',b'DL-10: [S-0--'),raw.replace(b'DL-11: [SS1',b'DL-11: [S-0'),
                    raw.replace(b'DL-14: [SS5',b'DL-14: [SS4'),raw.replace(b'WdN9',b'WzN9'),
                    raw.replace(b'E_',b'private detail',1),raw.replace(b'E_',b'\xff',1),b'x'*8193):
            with self.subTest(bad=bad[:25]),self.assertRaises(wire.ObservationError):wire.validate_output(bad)
        for case in (False,True,0,15,None,'1'):
            with self.assertRaises(wire.ObservationError):wire.maximum_record_size(case)

    def test_each_status_is_an_observation_not_an_availability_assumption(self):
        for status in 'SMAO':self.assertEqual([r['status'] for r in wire.validate_output(maximum_output(status))],[status]*14)
        with self.assertRaises(wire.AvailabilityError):wire.require_available(maximum_output())
        with self.assertRaises(wire.AvailabilityError):wire.require_available(maximum_output('M'))

    def test_unsupported_bytes_and_second_cell_sequence_are_rejected(self):
        raw=maximum_output()
        for token in (b'\r',b'\t',b'\x00',b'\x7f',b'\xff'):
            with self.assertRaises(wire.ObservationError):wire.validate_output(raw[:20]+token+raw[21:])
        # Each active row independently carries positional and named scalars.
        before=snapshot();self.assertIn('N9',before)
        with self.assertRaises(wire.ObservationError):wire.validate_payload(('S-0--/'+before[:-1]+'/'+before).encode(),1)


if __name__=='__main__':unittest.main()
