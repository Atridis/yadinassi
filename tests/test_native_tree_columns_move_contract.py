"""Synthetic Columns.Move wire/graph bounds; never native Move answers."""
import json
import unittest
from scripts import native_1c_tree_columns_move_contract as wire


def maximum_snapshot(case):
    schema=''.join(wire.IDS[index+2]+'aa9U99090290' for index in range(3))
    rows=''.join(wire.IDS[index+5]+'_00'+wire.IDS[index+5]+'0N9N9N9N9N9N9'
                 for index in range(wire.NODE_LIMITS[case-1]))
    return '0013'+schema+wire.IDS[wire.NODE_LIMITS[case-1]]+rows


def maximum_output(status='S'):
    lines=[wire.CALIBRATION_RECORD]
    for case in range(1,wire.CASE_COUNT+1):
        snapshot=maximum_snapshot(case)
        lines.append(f'CM-{case}: [{status}/{snapshot}/{snapshot}]\n'.encode())
    return b''.join(lines)


def nested_snapshot():
    head=maximum_snapshot(1)[:44]
    nodes=((5,None,0,2),(6,5,1,1),(7,6,2,0),(8,5,1,0),(9,None,0,0))
    return head+''.join(wire.IDS[row]+('_' if parent is None else wire.IDS[parent])+
                        '0'+str(level)+wire.IDS[row]+str(children)+'N9N9N9N9N9N9'
                        for row,parent,level,children in nodes)


class ColumnsMoveContractTests(unittest.TestCase):
    def payload(self,before,after=None,status='S',case=1):
        return wire.validate_payload(f'{status}/{before}/{before if after is None else after}'.encode(),case)

    def test_constructive_maximum_matches_per_record_and_capture_majorants(self):
        raw=maximum_output();decoded=wire.require_available(raw)
        self.assertEqual(len(decoded),28)
        self.assertEqual(len(raw),wire.MAX_ENCODED_BYTES)
        self.assertEqual(len(raw),7690)
        self.assertLessEqual(len(raw),8192)
        for case,line in enumerate(raw.splitlines(keepends=True)[1:],1):
            self.assertEqual(len(line),wire.maximum_record_size(case))
            self.assertEqual(len(maximum_snapshot(case)),wire.snapshot_size(3,wire.NODE_LIMITS[case-1]))
            self.assertEqual(len(decoded[case-1]['snapshots'][0]['nodes']),wire.NODE_LIMITS[case-1])

    def test_same_missing_method_errors_are_parseable_never_availability(self):
        raw=maximum_output('M')
        self.assertEqual({case['status'] for case in wire.validate_output(raw)},{'M'})
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        for case in (1,2):
            raw=maximum_output().replace(f'CM-{case}: [S/'.encode(),f'CM-{case}: [M/'.encode())
            with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)
        wire.require_available(maximum_output().replace(b'CM-3: [S/',b'CM-3: [A/'))

    def test_finite_statuses_preserve_observed_posterror_changes(self):
        before=maximum_snapshot(1);after=before[:-2]+'N0'
        for status in 'SMAO':
            value=self.payload(before,after,status)
            self.assertNotEqual(value['snapshots'][0],value['snapshots'][1])
        self.assertEqual(self.payload(before,status='E',case=23)['status'],'E')
        for case in (1,22,24,28):
            with self.assertRaises(wire.ObservationError):self.payload(before,status='E',case=case)
        for status in ('XB','XO','X','U','error','SS',''):
            with self.assertRaises(wire.ObservationError):self.payload(before,status=status)

    def test_strict_framing_unknown_duplicate_and_out_of_order_records(self):
        raw=maximum_output();lines=raw.splitlines(keepends=True)
        invalid=(None,bytearray(raw),raw+b'\n',raw[:-1],b'\xef\xbb\xbf'+raw,
                 raw.replace(b'\n',b'\r\n'),raw.replace(b'[-]',b'[X]',1),
                 raw.replace(b'CM-1:',b'CM-01:',1),raw.replace(b'CM-28:',b'CM-29:',1),
                 raw.replace(b'S/',b'\xc3\xa9/',1),b''.join(lines[:-1]),
                 b''.join([lines[0],lines[1],lines[1]]+lines[3:]),
                 b''.join([lines[0],lines[2],lines[1]]+lines[3:]),b'x'*8193)
        for value in invalid:
            with self.subTest(value=repr(value)[:50]),self.assertRaises(wire.ObservationError):wire.validate_output(value)
        for case in (False,True,0,29,'1',None):
            with self.assertRaises(wire.ObservationError):wire.validate_payload(b'S/-/-',case)

    def test_invalid_ids_kinds_duplicate_columns_rows_and_schema_fields(self):
        snapshot=maximum_snapshot(1)
        for pos,char in ((0,'1'),(1,'1'),(2,'0'),(3,'4'),(4,'9'),(17,'2'),
                         (5,'z'),(8,'Q'),(11,'2'),(44,'z'),(48,'6'),(62,'5'),(50,'Q')):
            bad=snapshot[:pos]+char+snapshot[pos+1:]
            with self.subTest(pos=pos),self.assertRaises(wire.ObservationError):self.payload(bad,snapshot)
        with self.assertRaises(wire.ObservationError):self.payload(snapshot+'x')
        # Empty-tree case admits no row even though every other case admits five.
        with self.assertRaises(wire.ObservationError):self.payload(snapshot,case=17)

    def test_coherent_preorder_graph_and_incoherent_graph_rejection(self):
        raw=nested_snapshot();decoded=self.payload(raw)['snapshots'][0]
        self.assertEqual([node.level for node in decoded['nodes']],[0,1,2,1,0])
        # Wrong root/child levels, parent edge, structural Rows owner or counts.
        for pos,char in ((45,'5'),(47,'1'),(49,'1'),(49,'3'),(63,'_'),(65,'0'),
                         (99,'6'),(101,'2'),(120,'8'),(121,'1'),(46,'A')):
            bad=raw[:pos]+char+raw[pos+1:]
            with self.subTest(pos=pos),self.assertRaises(wire.ObservationError):self.payload(bad)

    def test_column_permutations_and_new_identity_graph_are_observations(self):
        before=maximum_snapshot(1)
        after=before[:4]+before[30:43]+before[4:17]+before[17:30]+before[43:]
        value=self.payload(before,after)
        self.assertEqual([c[0] for c in value['snapshots'][1]['schema']],[4,2,3])
        # A replacement tree/columns/columns/rows may allocate fresh identities.
        after='AAB3'+''.join(wire.IDS[i]+'aa9U99090290' for i in (12,13,14))+'5'
        after+=''.join(wire.IDS[i]+'_A0'+wire.IDS[i]+'0N0N1N2N0N1N2' for i in range(15,20))
        value=self.payload(before,after,status='O')
        self.assertEqual(value['snapshots'][1]['tree'],10)
        self.assertNotEqual(value['snapshots'][0],value['snapshots'][1])
        self.assertEqual(value['identities'].count('row'),10)

    def test_schema_and_node_limits_are_caps_not_preservation_assumptions(self):
        before=maximum_snapshot(1)
        # Known identities may disappear from an independently coherent snapshot.
        empty='00100';self.payload(before,empty)
        one_column='0011'+before[4:17]+'1'+'5_0050N1N1'
        value=self.payload(before,one_column)
        self.assertEqual(len(value['snapshots'][1]['schema']),1)
        self.assertEqual(len(value['snapshots'][1]['nodes']),1)
        self.payload('00100',case=17)

    def test_named_cells_are_independent_and_strictly_bounded(self):
        before=maximum_snapshot(1)
        # First row's named sequence begins after metadata and positional cells.
        start=44+6+6
        after=before[:start]+'N0N1N2'+before[start+6:]
        value=self.payload(before,after)
        node=value['snapshots'][1]['nodes'][0]
        self.assertEqual(node.cells,(('N','9'),)*3)
        self.assertEqual(node.named_cells,(('N','0'),('N','1'),('N','2')))
        for bad in (after[:start]+'Q0'+after[start+2:],after[:start]+after[start+2:]):
            with self.assertRaises(wire.ObservationError):self.payload(before,bad)

    def test_complete_capture_marker_budget_with_json_escaping_overhead(self):
        marker=dict(schema='tree-columns-move-v1',nonce='f'*32,phase='completed',
                    witness='client',values=maximum_output().decode().splitlines())
        compact=json.dumps(marker,separators=(',',':'),ensure_ascii=True).encode()
        upper=len(compact)+compact.count(b',')+compact.count(b':')+compact.count(b'/')+3
        self.assertLessEqual(upper,16384)
        self.assertEqual((len(compact),upper),(7874,7999))
        self.assertEqual(json.loads(compact)['values'],maximum_output().decode().splitlines())


if __name__=='__main__':unittest.main()
