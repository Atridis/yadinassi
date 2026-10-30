"""Synthetic strict lifecycle grammar and constructive bounds, not native answers."""
import json
import unittest
from scripts import native_1c_tree_columns_clear_contract as wire


def maximum_snapshot():
    schema = ''.join(str(i) + chr(96 + i) + 'a9U99090290' for i in range(1, 4))
    rows = ''.join(str(i) + '_000' + 'N9' * 6 for i in range(4, 9))
    return '03' + schema + '5' + rows + 'E_' * 24


def header(case, status='S'):
    if status != 'S': return status + '-0--'
    if case == 8: return 'S-0U_'
    if case == 12: return 'SS5--'
    if case == 6 or case >= 9: return 'SS1--'
    return 'S-0--'


def maximum_output(status='S'):
    snapshot = maximum_snapshot()
    return wire.CALIBRATION_RECORD + b''.join(
        f'CC-{case}: [{header(case, status)}/{snapshot}/{snapshot}]\n'.encode()
        for case in range(1, 13))


def maximum_available_output(status='S'):
    raw = maximum_output(status)
    if status != 'S': return raw
    before = maximum_snapshot(); after = '000' + 'E_' * 24
    for case in (1, 2):
        raw = raw.replace(f'CC-{case}: [S-0--/{before}/{before}]'.encode(),
                          f'CC-{case}: [S-0--/{before}/{after}]'.encode())
    return raw


class ClearContractTests(unittest.TestCase):
    def payload(self, before=None, after=None, action='S-0--', case=1):
        before = maximum_snapshot() if before is None else before
        after = before if after is None else after
        return wire.validate_payload(f'{action}/{before}/{after}'.encode(), case)

    def test_constructive_maximum_and_complete_marker(self):
        raw = maximum_output()
        self.assertEqual(len(wire.validate_output(raw)), 12)
        self.assertEqual(len(maximum_snapshot()), wire.snapshot_size())
        self.assertEqual(wire.snapshot_size(), 175)
        self.assertEqual(len(raw), wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(raw), 4406)
        self.assertLessEqual(len(raw), 8192)
        for case, line in enumerate(raw.splitlines(keepends=True)[1:], 1):
            self.assertEqual(len(line), wire.maximum_record_size(case))
        marker = dict(schema='tree-columns-clear-v1', nonce='f' * 32, phase='completed',
                      witness='client', values=raw.decode().splitlines())
        compact = json.dumps(marker, separators=(',', ':'), ensure_ascii=True).encode()
        upper = len(compact) + compact.count(b',') + compact.count(b':') + compact.count(b'/') + 3
        self.assertEqual((len(compact), upper), (4559, 4620))
        self.assertLessEqual(upper, 16384)
        self.assertEqual(json.loads(compact)['values'], raw.decode().splitlines())

    def test_missing_or_error_controls_never_make_availability_green(self):
        for status in 'MAO':
            raw = maximum_output(status)
            self.assertEqual({r['status'] for r in wire.validate_output(raw)}, {status})
            with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)
        for case in (1, 2):
            bad = maximum_available_output().replace(f'CC-{case}: [S-0--/'.encode(), f'CC-{case}: [O-0--/'.encode())
            with self.assertRaises(wire.AvailabilityError): wire.require_available(bad)
        wire.require_available(maximum_available_output().replace(b'CC-3: [S-0--/', b'CC-3: [O-0--/'))

    def test_successful_noop_and_columns_only_controls_are_not_available(self):
        raw = maximum_output()
        self.assertEqual(len(wire.validate_output(raw)), 12)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)
        accepted = maximum_available_output()
        self.assertTrue(wire.controls_valid(wire.require_available(accepted)))
        # No schema, but a reachable row remains: method success is insufficient.
        before = maximum_snapshot(); rows_after = '0014_000' + 'E_' * 24
        for case in (1, 2):
            bad = accepted.replace(f'CC-{case}: [S-0--/{before}/000'.encode(),
                                   f'CC-{case}: [S-0--/{before}/0014_000'.encode())
            self.assertEqual(len(wire.validate_output(bad)), 12)
            with self.assertRaises(wire.AvailabilityError): wire.require_available(bad)

    def test_empty_or_half_empty_before_controls_cannot_establish_nonempty_clear(self):
        before=maximum_snapshot(); empty='000'+'E_'*24
        schema_only=before[:41]+'0'+'E_'*24
        rows_only='0011_000'+'E_'*24
        for case in (1,2):
            for observed_before in (empty,schema_only,rows_only):
                raw=maximum_available_output().replace(
                    f'CC-{case}: [S-0--/{before}/{empty}]'.encode(),
                    f'CC-{case}: [S-0--/{observed_before}/{empty}]'.encode())
                self.assertEqual(len(wire.validate_output(raw)),12)
                with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)

    def test_initial_followup_expression_and_rebuild_phases_are_distinct(self):
        for status in 'SMAO': self.payload(action=status + '-0--')
        for status in 'SMAO':
            value = self.payload(action='S' + status + '1--', case=9)
            self.assertEqual(value['follow_status'], status)
        for phase in range(1, 6): self.payload(action=f'SO{phase}--', case=12)
        self.payload(action='SS5--', case=12)
        for token in ('U_', 'L_', 'B0', 'B1', 'Na', 'N9', 'Sa'):
            self.assertEqual(self.payload(action='S-0' + token, case=8)['expression'], token)
        for case, action in ((1, 'SS1--'), (9, 'S-0--'), (9, 'OS1--'),
                             (12, 'SS4--'), (12, 'SO0--'), (8, 'S-0--'), (7, 'S-0U_')):
            with self.assertRaises(wire.ObservationError): self.payload(action=action, case=case)

    def test_partial_error_mutation_and_new_valid_identities_are_preserved(self):
        before = maximum_snapshot(); after = before.replace('4_000', '4_0a0', 1)
        value = self.payload(before, after, 'O-0--')
        self.assertNotEqual(value['snapshots'][0], value['snapshots'][1])
        # The second snapshot may have a new tree identity and reported owner,
        # independent of active traversal; no identity preservation is assumed.
        after = '9' + before[1:]
        value = self.payload(before, after)
        self.assertNotEqual(value['snapshots'][0]['tree'], value['snapshots'][1]['tree'])
        after = before.replace('4_000', '499a0', 1)
        with self.assertRaises(wire.ObservationError): self.payload(before, after)  # ID9 cannot be both row and tree.

    def test_named_and_positional_sequences_remain_independent(self):
        before = maximum_snapshot(); start = 2 + 39 + 1 + 5 + 6
        after = before[:start] + 'N0N1N2' + before[start + 6:]
        row = self.payload(before, after)['snapshots'][1]['nodes'][0]
        self.assertEqual(row.cells, (('N', 9),) * 3)
        self.assertEqual(row.named_cells, (('N', 0), ('N', 1), ('N', 2)))

    def test_retained_query_outcomes_and_foreign_owner_are_independent(self):
        before = maximum_snapshot(); queries = ['E_'] * 24
        queries[0] = 'I4'; queries[1] = 'I9'; queries[2] = 'I_'; queries[3] = 'Na'
        queries[4] = 'U_'; queries[7] = 'A_'; queries[14] = 'I1'; queries[15] = 'Wa'
        after = before[:-48] + ''.join(queries)
        value = self.payload(before, after)['snapshots'][1]
        self.assertEqual(value['queries'][1], ('I', 9))
        self.assertEqual(value['queries'][3], ('N', -1))
        self.assertNotEqual(value['queries'][0], value['queries'][7])
        self.assertEqual(value['queries'][4], ('U', ('U', '_')))
        for index, token in ((0, 'I0'), (1, 'I4'), (3, 'Nq'), (15, 'Wz'), (4, 'X_')):
            bad = list(queries); bad[index] = token
            with self.assertRaises(wire.ObservationError): self.payload(before, before[:-48] + ''.join(bad))

    def test_strict_frames_counts_types_and_trailing_data(self):
        raw = maximum_output()
        mutations = (raw[:-1], raw + b'\n', raw.replace(b'CC-C1: [-]', b'CC-C1: [S]'),
                     raw.replace(b'CC-2:', b'CC-1:'), raw.replace(b'\n', b'\r\n'),
                     raw.replace(b'CC-1:', b'XX-1:'), b'x' * 8193, b'\xff' + raw[1:])
        for value in mutations:
            with self.assertRaises(wire.ObservationError): wire.validate_output(value)
        for value in (None, '', bytearray(raw), memoryview(raw)):
            with self.assertRaises(wire.ObservationError): wire.validate_output(value)
        for case in (0, 13, True, '1'):
            with self.assertRaises(wire.ObservationError): wire.validate_payload(b'', case)
        before = maximum_snapshot()
        for after in (before + 'x', before[:-1], '04' + before[2:], before.replace('4_000', '4_006', 1)):
            with self.assertRaises(wire.ObservationError): self.payload(before, after)

    def test_mutation_corpus_always_has_finite_decoder_failures(self):
        raw = maximum_output()
        rejected = 0
        for index in range(0, len(raw), 13):
            changed = raw[:index] + b'?' + raw[index + 1:]
            try: wire.validate_output(changed)
            except wire.ObservationError as error:
                self.assertEqual(str(error), 'tree_columns_clear_observation_invalid'); rejected += 1
        self.assertGreater(rejected, 250)


if __name__ == '__main__': unittest.main()
