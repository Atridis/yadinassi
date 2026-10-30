"""Strict CB framing and constructive budgets, never native boundary answers."""
import json
import unittest
from scripts import native_1c_tree_columns_move_boundary_contract as wire
from test_native_tree_columns_move_contract import maximum_snapshot as cm_snapshot, nested_snapshot


def maximum_snapshot(case=1):
    if type(case) is not int or not 1 <= case <= wire.CASE_COUNT:
        raise ValueError('case')
    return cm_snapshot(1)


def maximum_output(status='S'):
    lines=[wire.CALIBRATION_RECORD]
    for case in range(1,wire.CASE_COUNT+1):
        snapshot=maximum_snapshot(case)
        lines.append(f'CB-{case}: [{status}/{snapshot}/{snapshot}]\n'.encode('ascii'))
    return b''.join(lines)


class BoundaryContractTests(unittest.TestCase):
    def payload(self,before,after=None,status='S',case=1):
        return wire.validate_payload(f'{status}/{before}/{before if after is None else after}'.encode(),case)

    def test_constructive_maximum_and_all_case_labels(self):
        raw=maximum_output();decoded=wire.require_available(raw)
        self.assertEqual(len(raw),4779)
        self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertLessEqual(len(raw),8192)
        self.assertEqual([record['case'] for record in decoded],list(range(1,18)))
        for case,line in enumerate(raw.splitlines(keepends=True)[1:],1):
            self.assertEqual(len(line),wire.maximum_record_size(case))
            self.assertEqual(len(maximum_snapshot(case)),wire.snapshot_size(3,5))
            self.assertEqual(len(decoded[case-1]['snapshots'][0]['nodes']),5)

    def test_missing_method_or_failed_either_control_never_available(self):
        raw=maximum_output('M')
        self.assertEqual({item['status'] for item in wire.validate_output(raw)},{'M'})
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        for case in (1,2):
            raw=maximum_output().replace(f'CB-{case}: [S/'.encode(),f'CB-{case}: [O/'.encode())
            with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        wire.require_available(maximum_output().replace(b'CB-17: [S/',b'CB-17: [O/'))

    def test_strict_prefix_order_count_encoding_and_scalar_case_types(self):
        raw=maximum_output();lines=raw.splitlines(keepends=True)
        variants=(None,bytearray(raw),raw+b'\n',raw[:-1],b'\xef\xbb\xbf'+raw,
                  raw.replace(b'\n',b'\r\n'),raw.replace(b'[-]',b'[E]',1),
                  raw.replace(b'CB-',b'CM-',1),raw.replace(b'CB-1:',b'CB-01:',1),
                  raw.replace(b'CB-17:',b'CB-18:'),raw.replace(b'S/',b'\xff/',1),
                  b''.join(lines[:-1]),b''.join([lines[0],lines[1],lines[1]]+lines[3:]),
                  b''.join([lines[0],lines[2],lines[1]]+lines[3:]),b'x'*8193)
        for value in variants:
            with self.subTest(value=repr(value)[:50]),self.assertRaises(wire.ObservationError):
                wire.validate_output(value)
        for case in (False,True,0,18,'1',None):
            with self.assertRaises(wire.ObservationError):wire.validate_payload(b'S/-/-',case)

    def test_all_cases_exclude_expression_and_observer_statuses(self):
        snapshot=maximum_snapshot()
        for case in range(1,18):
            for status in ('E','XB','XO','error',''):
                with self.subTest(case=case,status=status),self.assertRaises(wire.ObservationError):
                    self.payload(snapshot,status=status,case=case)
        changed=snapshot[:-2]+'N0'
        for status in 'SMAO':
            value=self.payload(snapshot,changed,status)
            self.assertNotEqual(*value['snapshots'])

    def test_invalid_ids_schema_duplicate_columns_rows_and_graph(self):
        snapshot=maximum_snapshot()
        for pos,char in ((0,'1'),(1,'1'),(2,'0'),(3,'4'),(4,'9'),(17,'2'),
                         (5,'z'),(8,'Q'),(11,'2'),(44,'z'),(48,'6'),(62,'5'),(50,'Q')):
            bad=snapshot[:pos]+char+snapshot[pos+1:]
            with self.subTest(pos=pos),self.assertRaises(wire.ObservationError):self.payload(bad,snapshot)
        nested=nested_snapshot()
        self.assertEqual([node.level for node in self.payload(nested)['snapshots'][0]['nodes']],[0,1,2,1,0])
        for pos,char in ((45,'5'),(47,'1'),(49,'3'),(63,'_'),(65,'0'),(99,'6'),(121,'1')):
            bad=nested[:pos]+char+nested[pos+1:]
            with self.subTest(pos=pos),self.assertRaises(wire.ObservationError):self.payload(bad)

    def test_independent_named_cells_and_partial_schema_changes_remain_visible(self):
        before=maximum_snapshot();start=44+6+6
        after=before[:start]+'N0N1N2'+before[start+6:]
        record=self.payload(before,after,status='O');node=record['snapshots'][1]['nodes'][0]
        self.assertEqual(node.cells,(('N','9'),)*3)
        self.assertEqual(node.named_cells,(('N','0'),('N','1'),('N','2')))
        self.payload(before,'00100',status='O',case=17)
        for bad in (after[:start]+'Q0'+after[start+2:],after[:start]+after[start+2:]):
            with self.assertRaises(wire.ObservationError):self.payload(before,bad)

    def test_new_identities_are_not_normalized_to_prior_snapshot(self):
        before=maximum_snapshot()
        ids='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
        after='AAB3'+''.join(ids[i]+'aa9U99090290' for i in (12,13,14))+'5'
        after+=''.join(ids[i]+'_A0'+ids[i]+'0N0N1N2N0N1N2' for i in range(15,20))
        record=self.payload(before,after,status='O')
        self.assertEqual(record['snapshots'][1]['tree'],10)
        self.assertEqual(record['identities'].count('row'),10)

    def test_completed_marker_escaped_spaced_bom_bound(self):
        marker=dict(schema='tree-columns-move-boundary-v1',nonce='f'*32,phase='completed',
                    witness='client',values=maximum_output().decode().splitlines())
        compact=json.dumps(marker,separators=(',',':'),ensure_ascii=True).encode()
        upper=len(compact)+compact.count(b',')+compact.count(b':')+compact.count(b'/')+3
        self.assertLessEqual(upper,16384)
        self.assertEqual((len(compact),upper),(4950,5031))
        self.assertEqual(json.loads(compact)['values'],maximum_output().decode().splitlines())


if __name__=='__main__':unittest.main()
