"""Synthetic strict-grammar and constructive budget proofs, not native answers."""
import json
import unittest
from scripts import native_1c_tree_sort_contract as wire


def maximum_snapshot(case):
    schema = ''.join(wire.IDS[index + 2] + 'aa9U99090290' for index in range(3))
    rows = ''.join(wire.IDS[index + 5] + '_09' + wire.IDS[index + 5] + '9N9N9Sr'
                   for index in range(wire.NODE_LIMITS[case - 1]))
    return '0013' + schema + wire.IDS[wire.NODE_LIMITS[case - 1]] + rows


def maximum_output(status='S'):
    lines = [wire.CALIBRATION_RECORD.decode('ascii').rstrip('\n')]
    for case in range(1, wire.CASE_COUNT + 1):
        snapshot = maximum_snapshot(case)
        lines.append(f'TS-{case}: [{status}/{snapshot}/{snapshot}]')
    return ('\n'.join(lines) + '\n').encode('ascii')


class SortContractTests(unittest.TestCase):
    def test_constructive_maximum_accepted_records_equal_bound(self):
        raw = maximum_output()
        decoded = wire.require_available(raw)
        self.assertEqual(len(decoded), 21)
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(raw), 6443)
        self.assertLessEqual(len(raw), 8192)
        for case, line in enumerate(raw.splitlines(keepends=True)[1:], 1):
            self.assertEqual(len(line), wire.maximum_record_size(case))
            self.assertEqual(len(decoded[case-1]['snapshots'][0]['nodes']), wire.NODE_LIMITS[case-1])
            self.assertEqual(len(maximum_snapshot(case)), wire.snapshot_size(3, wire.NODE_LIMITS[case-1]))

    def test_completed_client_marker_budget_not_fictitious_output_suffix(self):
        # Existing tree_suite.client_marker consumes separate JSON bounded 16384.
        # Proposed profile identity only: no Sort profile integration is claimed.
        values = maximum_output().decode('ascii').splitlines()
        marker = dict(schema='tree-sort-v1', nonce='f' * 32, phase='completed',
                      witness='client', values=values)
        compact = json.dumps(marker, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        self.assertEqual(json.loads(compact)['values'], values)
        # Charge BOM, one space at EVERY separator and optional escaping of every
        # slash; no raw controls, quotes or backslashes occur in any message.
        upper = len(compact) + compact.count(b',') + compact.count(b':') + compact.count(b'/') + 3
        self.assertLessEqual(upper, 16384)
        self.assertEqual(len(compact), 6605)
        self.assertEqual(upper, 6702)

    def test_all_missing_method_parses_but_cannot_pass_availability(self):
        raw = maximum_output('M')
        self.assertEqual({row['status'] for row in wire.validate_output(raw)}, {'M'})
        with self.assertRaises(wire.AvailabilityError):
            wire.require_available(raw)
        for case in (1, 2):
            bad = maximum_output().replace(f'TS-{case}: [S/'.encode(), f'TS-{case}: [M/'.encode())
            with self.assertRaises(wire.AvailabilityError):
                wire.require_available(bad)
        raw = maximum_output().replace(b'TS-11: [S/', b'TS-11: [A/')
        wire.require_available(raw)

    def test_all_finite_action_categories_keep_post_error_state(self):
        snapshot = maximum_snapshot(1)
        changed = snapshot[:-2] + 'Sa'
        for status in 'SMAO':
            value = wire.validate_payload(f'{status}/{snapshot}/{changed}'.encode(), 1)
            self.assertNotEqual(value['snapshots'][0], value['snapshots'][1])
            self.assertEqual(value['status'], status)
        for payload in (b'XB', b'XO', b'X', b'error', b'S', b'S/-/-', b'S///'):
            with self.assertRaises(wire.ObservationError):
                wire.validate_payload(payload, 1)

    def test_strict_framing_ascii_and_counts(self):
        raw = maximum_output()
        lines = raw.splitlines(keepends=True)
        invalid = (None, bytearray(raw), raw + b'\n', raw[:-1], b'\xef\xbb\xbf' + raw,
                   raw.replace(b'\n', b'\r\n'), raw.replace(b'[-]', b'[X]', 1),
                   raw.replace(b'TS-1:', b'TS-01:', 1), raw.replace(b'S/', b'\xc3\xa9/', 1),
                   b''.join([lines[0], lines[2], lines[1]] + lines[3:]),
                   b''.join(lines[:-1]), raw + b'x' * 8192)
        for value in invalid:
            with self.subTest(value=repr(value)[:60]):
                with self.assertRaises(wire.ObservationError):
                    wire.validate_output(value)

    def test_fixed_field_alphabets_and_structural_labels(self):
        snapshot = maximum_snapshot(1)
        for pos, replacement in ((0, '1'), (1, '1'), (2, '0'), (3, '4'),
                                 (4, '9'), (5, 'z'), (8, 'Q'), (11, '2'),
                                 (43, 'I'), (44, 'z'), (45, '1'), (46, '1'),
                                 (48, '6'), (50, 'Q'), (51, '_'), (55, 'z')):
            malformed = snapshot[:pos] + replacement + snapshot[pos+1:]
            with self.subTest(pos=pos):
                with self.assertRaises(wire.ObservationError):
                    wire.validate_payload(f'S/{malformed}/{snapshot}'.encode(), 1)
        for case in (False, True, 0, 22, '1', None):
            with self.assertRaises(wire.ObservationError):
                wire.validate_payload(b'S/-/-', case)

    def test_scalar_kinds_and_identity_changes_are_observed_not_assumed(self):
        snapshot = maximum_snapshot(1)
        for cell in ('N0', 'Sr', 'Sa', 'U_', 'L_', 'B0', 'B1'):
            after = snapshot[:-2] + cell
            wire.validate_payload(f'S/{snapshot}/{after}'.encode(), 1)
        # Allocate new tree13, columns14, column15..17, preserve existing row IDs.
        after = 'DDE3' + ''.join(wire.IDS[i] + 'aa9U99090290' for i in (15,16,17)) + '8'
        after += ''.join(wire.IDS[i] + '_D9' + wire.IDS[i] + '9N9N9Sr' for i in range(5,13))
        value = wire.validate_payload(f'O/{snapshot}/{after}'.encode(), 1)
        self.assertNotEqual(value['snapshots'][0]['tree'], value['snapshots'][1]['tree'])
        self.assertEqual(value['snapshots'][1]['nodes'][0].owner, 13)


if __name__ == '__main__':
    unittest.main()
