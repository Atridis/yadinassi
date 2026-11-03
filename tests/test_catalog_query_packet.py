"""Owned XML/text-only packet; actual native observations are still pending."""
from pathlib import Path
import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from catalog_query_behavior import packet


class CatalogQueryPacketTests(unittest.TestCase):
    def test_saved_render_full_identity_and_field_inventory(self):
        setup, xml, source = packet.load_saved()
        self.assertEqual(len(packet.CASES), 24)
        self.assertEqual(xml, packet.render_xml(setup))
        self.assertEqual(source, packet.render_program(setup).encode('utf-8'))
        root = ET.fromstring(xml)
        props = root.find(packet.MD+'Catalog/'+packet.MD+'Properties')
        self.assertEqual(props.find(packet.MD+'CodeLength').text, '8')
        self.assertEqual(props.find(packet.MD+'DescriptionLength').text, '64')
        self.assertEqual(props.find(packet.MD+'Hierarchical').text, 'false')
        self.assertEqual(props.find(packet.MD+'Autonumbering').text, 'false')
        self.assertLess(len(source), 8192)

    def test_program_has_exact_sequential_emission_and_bounded_owned_setup(self):
        import re
        setup, xml, source = packet.load_saved()
        text = source.decode('utf-8')
        self.assertEqual([int(x) for x in re.findall(r'CQEmit\(([0-9]+),', text)], list(range(1,25)))
        self.assertEqual(text.count('P.Write();'), 3)
        self.assertEqual(text.count('P.SetNewObjectRef'), 3)
        self.assertEqual(text.count('owned query row bound'), 2)
        for identity in setup.record_ids: self.assertIn(identity, text)
        for forbidden in ('ErrorDescription', 'ExceptionInfo', 'COMObject', 'File(', '.1CD', '.cf', '.dt', 'Delete('):
            self.assertNotIn(forbidden, text)
        # The source measures unknown cursor/regional outcomes, never prescribes.
        self.assertIn('Description=&Name', text)
        self.assertIn('BeforeProbe=Probe;', text)
        self.assertIn('Probe="action-error"', text)

    def test_fresh_identifiers_and_collision_rejections(self):
        first = packet.fresh(); second = packet.fresh()
        self.assertNotEqual(first, second)
        for changed in (replace(first, name='Bad.Name'),
                        replace(first, field_ids=(first.metadata_uuid,*first.field_ids[1:])),
                        replace(first, record_ids=(first.record_ids[0],)*3),
                        replace(first, generated_ids=list(first.generated_ids))):
            with self.assertRaises(ValueError): packet.render_xml(changed)

    def test_closed_slot_types_and_wire_bounds(self):
        booleans = {2,3,4,13,14,15,18,24}
        rows = [False if i in booleans else Decimal(0) if i == 19 else '' for i in range(1,25)]
        self.assertTrue(packet.validate_observations(rows))
        for index, value in ((0,'x'*65),(0,'a|b'),(0,'a\nb'),(1,'false'),(18,True),
                             (18,3),(18,Decimal('3.1')),(18,Decimal(4)),(18,Decimal('NaN'))):
            bad = list(rows); bad[index] = value
            with self.assertRaises(ValueError): packet.validate_observations(bad)
        with self.assertRaises(ValueError): packet.validate_observations(rows[:-1])

    def test_template_hash_and_saved_source_are_not_silently_repaired(self):
        setup, _, _ = packet.load_saved()
        with patch.object(packet, 'TEMPLATE_SHA256', '0'*64), self.assertRaises(ValueError):
            packet.render_xml(setup)
        with patch.object(packet, 'render_program', return_value='changed'), self.assertRaises(ValueError):
            packet.load_saved()


if __name__ == '__main__': unittest.main()
