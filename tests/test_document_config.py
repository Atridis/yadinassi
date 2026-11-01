"""Measured Document CONFIG identity routes and fail-closed boundaries."""
import copy
import unittest
from yadinassi.storage import config_document_metadata as m
from yadinassi.storage import config_catalog_attributes as a
from yadinassi.storage import filedb_catalog as c
from yadinassi.storage.document_reader import read_document_rows
from test_document_native_replay import CAPTURE,image

class DocumentConfigTests(unittest.TestCase):
    def parse(self,raw):
        return m.project_document_metadata(raw,budget=c._Budget(c.CatalogLimits()))

    def test_actual_both_attribute_orders_and_declared_identity(self):
        for repeat,configs in CAPTURE['configs'].items():
            raw=bytes.fromhex(configs[2]['raw_hex']);identity,attrs=self.parse(raw)
            self.assertEqual(identity.metadata_uuid,configs[2]['filename'])
            self.assertEqual((identity.number_type,identity.number_length,identity.number_periodicity),(1,8,0))
            self.assertEqual(tuple(a.type_token for a in attrs.attributes),
                             ('S','N','B','D','#') if repeat=='1' else ('#','D','B','N','S'))

    def test_quoted_or_changed_header_is_not_measured_grammar(self):
        raw=bytes.fromhex(CAPTURE['configs']['1'][2]['raw_hex'])
        for before,after in ((b'{1,',b'{"1",'),(b'{40,',b'{"40",'),(b'{40,',b'{39,')):
            changed=raw.replace(before,after,1)
            self.assertNotEqual(raw,changed)
            with self.assertRaises(a.CatalogAttributeError):self.parse(changed)

    def test_missing_reference_target_and_metadata_uuid_substitution_refused(self):
        state=CAPTURE['states'][2]
        mapping=state['physical']['actual_mapping']
        for target in ('00000000-0000-0000-0000-000000000000',mapping[1]['metadata_uuid']):
            configs=copy.deepcopy(CAPTURE['configs'][str(state['repeat'])])
            raw=bytes.fromhex(configs[2]['raw_hex'])
            before=b'{"#",'+mapping[1]['ref_type_uuid'].encode()
            changed=raw.replace(before,b'{"#",'+target.encode())
            self.assertNotEqual(raw,changed);configs[2]['raw_hex']=changed.hex()
            source=image(state,configs)
            with self.assertRaises(c.CatalogError):
                read_document_rows(source.read_at,source.size,document_name=mapping[0]['name'])

    def test_catalog_error_route_remains_bounded_without_document_flag(self):
        from yadinassi.storage.catalog_metadata import read_catalog_metadata
        state=CAPTURE['states'][2];configs=copy.deepcopy(CAPTURE['configs'][str(state['repeat'])])
        raw=bytes.fromhex(configs[3]['raw_hex'])
        before=a.COLLECTION_UUID.encode();changed=raw.replace(before,m.ATTRIBUTE_COLLECTION_UUID.encode())
        self.assertNotEqual(raw,changed);configs[3]['raw_hex']=changed.hex()
        source=image(state,configs)
        with self.assertRaises(c.CatalogError):read_catalog_metadata(source.read_at,source.size)

if __name__=='__main__':unittest.main()
