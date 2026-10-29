"""Structural Rows-owner labels, never synthetic claims about native Copy."""
import unittest
from unittest import mock
from scripts import native_1c_tree_copy_contract as wire
from scripts import native_1c_tree_access_probe as probe
from test_native_tree_copy_measurement import SOURCE, emit, emit_capture, maximum_output, maximum_snapshot, synthetic_method
from yadinassi.value_trees import BSLValueTree, BSLValueTreeRow, BSLValueTreeRowCollection
from yadinassi.values import BSLObject


class FreshRows(BSLValueTreeRowCollection):
    """Synthetic access wrapper; underlying mutations still hit the real collection."""
    def __init__(self, target): self.target=target
    def __iter__(self):return iter(self.target)
    def get_member(self,name):return self.target.get_member(name)
    def get_method(self,name):return self.target.get_method(name)


class CopyOwnerLabelTests(unittest.TestCase):
    def test_owner_labels_are_explicit_existing_ids_not_collection_identities(self):
        for result in wire.validate_output(maximum_output()):
            self.assertNotIn('rows',result['identities'])
            for snapshot in result['snapshots']:
                self.assertEqual(snapshot['rows_owner'],snapshot['tree'])
                self.assertNotIn('rows',snapshot)
                for row in snapshot['nodes']:
                    self.assertIsInstance(row,wire.RowObservation)
                    self.assertEqual(row.children_owner,row.row)
                    self.assertEqual(row[6],row.cells)
        self.assertIn('columns',wire.validate_output(maximum_output())[2]['identities'])

    def test_old_header_and_old_payload_under_new_header_are_rejected(self):
        raw=maximum_output()
        with self.assertRaises(wire.ObservationError):wire.validate_output(raw.replace(b'TC-C2:',b'TC-C:'))
        # Legacy case1 tree, rows-wrapper, columns-wrapper were three typed IDs.
        old_case=b'TC-1: [S/01200/01200/01200]\n'
        lines=raw.splitlines(keepends=True);lines[1]=old_case
        with self.assertRaises(wire.ObservationError):wire.validate_output(b''.join(lines))
        for position in (1,2,3):
            snaps=['00100']*3;snaps[position-1]='01200'
            with self.assertRaises(wire.ObservationError):wire.validate_payload(('S/'+'/'.join(snaps)).encode(),1)
        with self.assertRaises(probe.ProbeError):probe.split_capture(b'TC-P: [TFTFTFTFTTFTTFTTFTTFTTF]\n'+raw.replace(b'TC-C2:',b'TC-C:'))

    def test_owner_labels_reject_wrong_typed_and_forward_references(self):
        raw=maximum_snapshot(3)
        # Header owner at1; first node owner-label follows header/schema/nodecount
        # and row,parent,actualOwner,level fields.
        child_offset=5+3*13+4
        for offset in (1,child_offset):
            expected=raw[offset]
            for bad in ('_', 'z', '1', '0'):
                if bad==expected:continue
                changed=raw[:offset]+bad+raw[offset+1:]
                with self.subTest(offset=offset,bad=bad),self.assertRaises(wire.ObservationError):
                    wire.validate_payload(('S/'+'/'.join([changed]*3)).encode(),3)

    def test_fresh_rows_access_no_longer_consumes_identity_registry(self):
        tree_get=BSLValueTree.get_member;row_get=BSLValueTreeRow.get_member
        def tree_member(value,name):
            got=tree_get(value,name)
            return FreshRows(got) if name.casefold() in ('rows','строки') else got
        def row_member(value,name):
            got=row_get(value,name)
            return FreshRows(got) if name.casefold() in ('rows','строки') else got
        old=SOURCE.replace('TCId(T, Registry); // Structural root Rows owner label, not wrapper identity.',
                           'TCId(T.Rows, Registry);').replace('TCId(R, Registry); // Structural child Rows owner label, not wrapper identity.',
                           'TCId(R.Rows, Registry);')
        with mock.patch.object(BSLValueTree,'get_member',tree_member),mock.patch.object(BSLValueTreeRow,'get_member',row_member),mock.patch.object(BSLValueTree,'get_method',synthetic_method('deep')):
            previous=emit_capture(old)
            self.assertIn(b'TC-5: [XM15G01]\n',previous)
            current=emit_capture()
            record,main=probe.split_capture(current)
            # Synthetic wrapper model reproduces only the independently observed
            # equality pattern; deep Copy here remains a test stub, not evidence.
            self.assertEqual(record,b'TC-P: [TFTFTFTFTTFTFFTFFTTFTTF]\n')
            cases=wire.validate_output(main)
            self.assertEqual([case['status'] for case in cases],['S']*9)
            self.assertTrue(all(len(case['identities'])<62 for case in cases))
            for case in cases:
                for snapshot in case['snapshots']:
                    self.assertEqual(snapshot['rows_owner'],snapshot['tree'])
                    for row in snapshot['nodes']:self.assertEqual(row.children_owner,row.row)

    def test_labels_follow_identity_not_sibling_position(self):
        with mock.patch.object(BSLValueTree,'get_method',synthetic_method('deep')):
            case=wire.validate_output(emit())[4]
        observed={}
        for snapshot in case['snapshots']:
            for row in snapshot['nodes']:
                observed.setdefault(row.row,set()).add(row.children_owner)
        self.assertTrue(observed)
        self.assertTrue(all(owners=={row} for row,owners in observed.items()))
