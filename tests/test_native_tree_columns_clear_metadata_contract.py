"""CD3 setup controls do not prescribe post-Clear retained metadata."""
import unittest
from scripts import native_1c_tree_columns_clear_metadata_contract as wire
from test_native_tree_columns_clear_contract import maximum_snapshot


def initialized_snapshot():
    snapshot=maximum_snapshot().replace('1aa9','1ad9',1)
    queries=['E_']*24;queries[14]='I1';queries[16]='Wd';queries[17]='N9'
    return snapshot[:-48]+''.join(queries)


def maximum_output(available=False,status='S'):
    lines=[wire.CALIBRATION_RECORD]
    for case in range(1,4):
        before=initialized_snapshot() if case==3 else maximum_snapshot()
        after='000'+'E_'*24 if available and case<=2 else maximum_snapshot()
        lines.append(f'CD-{case}: [{status}-0--/{before}/{after}]\n'.encode('ascii'))
    return b''.join(lines)


class MetadataContractTests(unittest.TestCase):
    def test_constructive_maximum(self):
        raw=maximum_output();self.assertEqual(len(raw),1109);self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(wire.validate_output(raw)),3)
        self.assertLess(len(raw),8192)

    def test_nonempty_english_russian_controls_and_independent_setup_gate(self):
        raw=maximum_output(available=True);self.assertEqual(len(wire.require_available(raw)),3)
        for bad in (maximum_output(),maximum_output(available=True,status='M'),raw.replace(b'1ad9',b'1aa9'),
                    raw.replace(b'1ad9',b'1ad8'),raw.replace(b'WdN9',b'WaN9'),raw.replace(b'WdN9',b'WdN8'),
                    raw.replace(b'I1E_WdN9',b'I2E_WdN9')):
            with self.subTest(bad=bad[:30]),self.assertRaises(wire.AvailabilityError):wire.require_available(bad)

    def test_no_after_answer_or_case3_success_is_required(self):
        raw=maximum_output(available=True)
        for status in 'SMAO':
            changed=raw.replace(b'CD-3: [S-',('CD-3: ['+status+'-').encode())
            records=wire.require_available(changed);self.assertEqual(records[2]['status'],status)
        self.assertTrue(wire.require_available(raw)[2]['snapshots'][1]['schema'])

    def test_strict_framing_domain_and_basis_grammar(self):
        raw=maximum_output()
        for bad in (raw+b'x',raw.replace(b'CD-C1: [-]',b'CD-C1: [E]'),raw.replace(b'CD-1:',b'CD-0:'),
                    raw.replace(b'S-0--',b'SS1--',1),raw.replace(b'WdN9',b'WzN9'),raw.replace(b'WdN9',b'WdNX'),
                    raw.replace(b'E_',b'private error',1),raw.replace(b'E_',b'\xff',1),b'x'*8193):
            with self.assertRaises(wire.ObservationError):wire.validate_output(bad)
        for case in (False,True,0,4,None,'1'):
            with self.assertRaises(wire.ObservationError):wire.maximum_record_size(case)


if __name__=='__main__':unittest.main()
