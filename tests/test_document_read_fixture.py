"""Saved Document input and full semantic redump closure (synthetic, not native)."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'scripts')]
import document_read_fixture as fixture
from document_read_packet import document_packet as packet
from linked_card_packet import linked
from snapshots import OracleError


class DocumentFixtureTests(unittest.TestCase):
    def setUp(self):
        self.s, self.manifest, self.files = fixture.load(1)
        self.request = self.manifest['profile']
        self.saved = {n: b for n, b in self.files.items() if n.endswith('.xml')}

    def test_both_saved_sets_full_sources_and_actual_mapping(self):
        all_ids = []
        for repeat in (1, 2):
            s, manifest, files = fixture.load(repeat)
            p = fixture.profile(s)
            self.assertEqual(p, manifest['profile'])
            saved = {n: b for n, b in files.items() if n.endswith('.xml')}
            mapped = fixture.actual_mapping(s, p, saved)
            self.assertEqual([m['name'] for m in mapped], [p['document_name'], p['catalog_name']])
            self.assertEqual([m['metadata_uuid'] for m in mapped], list(s.base.metadata_ids))
            for row in mapped:
                self.assertNotEqual(row['metadata_uuid'], row['ref_type_uuid'])
                all_ids.extend(row.values())
        self.assertEqual(len(all_ids), len(set(all_ids)))
        for bad in (True, 0, 3, '1'):
            with self.assertRaises(OracleError): fixture.load(bad)

    def test_manifest_and_source_mutation_refused(self):
        import inputs
        original = inputs.read_source
        for mutation in ('name', 'hash', 'extra'):
            def read(path):
                data = original(path)
                if path.name == 'manifest.json':
                    item = json.loads(data)
                    if mutation == 'name': item['profile']['document_name'] = 'Other'
                    elif mutation == 'hash': item['files']['identity.bsl'] = '0'*64
                    else: item['extra'] = True
                    return json.dumps(item).encode()
                return data
            with mock.patch.object(inputs, 'read_source', side_effect=read):
                with self.assertRaises((ValueError, OracleError)): fixture.load(1)

    def test_redump_resolves_qnames_but_never_strips_defaults(self):
        actual = {n: b.replace(b'<MetaDataObject ', b'<MetaDataObject xmlns:unused="urn:unused" ', 1)
                  for n, b in self.saved.items()}
        self.assertTrue(fixture.verify_redump(self.s, self.request, self.saved, actual))
        self.assertEqual(fixture.actual_mapping(self.s, self.request, actual),
                         fixture.actual_mapping(self.s, self.request, self.saved))
        doc = 'Documents/'+self.request['document_name']+'.xml'
        for old, new in ((b'http://www.w3.org/2001/XMLSchema"', b'urn:wrong"'),
                (b'<Posting>Allow', b'<Posting>Deny'),
                (b'<RealTimePosting>Deny', b'<RealTimePosting>Allow'),
                (b'<ObjectModule></ObjectModule>', b'<ObjectModule>unsafe</ObjectModule>'),
                (b'<StandardAttributes></StandardAttributes>', b'<StandardAttributes><Added/></StandardAttributes>'),
                (b'<RegisterRecords></RegisterRecords>', b'<RegisterRecords><Register>Other</Register></RegisterRecords>')):
            changed = dict(actual)
            self.assertIn(old, changed[doc])
            changed[doc] = changed[doc].replace(old, new)
            with self.assertRaises(ValueError): fixture.verify_redump(self.s, self.request, self.saved, changed)
        with self.assertRaises(ValueError): fixture.verify_redump(self.s, self.request, self.saved, {})

    def test_mapping_cannot_substitute_metadata_uuid_for_ref_type(self):
        changed = dict(self.saved)
        path = 'Documents/'+self.request['document_name']+'.xml'
        old = self.request['linked_schema']['generated_ids'][self.s.base.names[0]]['REF_TYPE_UUID']
        changed[path] = changed[path].replace(old.encode(), self.request['document_uuid'].encode())
        with self.assertRaises(ValueError): fixture.actual_mapping(self.s, self.request, changed)

    def test_exact_configuration_inventory_and_minimal_document_rights(self):
        configuration = (f'<MetaDataObject xmlns="{fixture.MD}"><Configuration><Properties><Name>Owned</Name>'
            '</Properties><ChildObjects><Catalog>NativeOracleItems</Catalog><Role>Keep</Role>'
            '</ChildObjects></Configuration></MetaDataObject>').encode()
        rights = Path(linked.__file__).with_name('base').joinpath('CRUDRights.xml').read_bytes().replace(
            b'@@CONFIGURATION_NAME@@', b'Owned')
        extended = fixture.extend_sources(self.s, self.request, self.saved, configuration, rights)
        root = ET.fromstring(extended['Configuration.xml'])
        children = root.find('{'+fixture.MD+'}Configuration/{'+fixture.MD+'}ChildObjects')
        self.assertEqual([(n.tag.rsplit('}', 1)[1], n.text) for n in children], [
            ('Document', self.request['document_name']), ('Catalog', self.request['catalog_name']),
            ('Catalog', 'NativeOracleItems'), ('Role', 'Keep')])
        raw = extended['Roles/NativeOracleCatalogCRUD/Ext/Rights.xml']
        self.assertTrue(packet.validate_rights(self.s, self.request, rights, raw))
        rns = '{http://v8.1c.ru/8.2/roles}'
        document = next(n for n in ET.fromstring(raw).findall(rns+'object')
            if n.findtext(rns+'name') == 'Document.'+self.request['document_name'])
        self.assertEqual([n.findtext(rns+'name') for n in document.findall(rns+'right')],
                         ['Read', 'Insert', 'Update', 'Posting'])
        for extra in (b'<Document>Other</Document>', b'<Catalog>Other</Catalog>'):
            bad = configuration.replace(b'</ChildObjects>', extra+b'</ChildObjects>')
            with self.assertRaises(ValueError): fixture.extend_sources(self.s, self.request, self.saved, bad, rights)
        for right in ('Delete', 'InteractivePosting', 'UndoPosting', 'Administration'):
            bad = raw.replace(b'<name>Posting</name>', ('<name>'+right+'</name>').encode())
            with self.assertRaises(ValueError): packet.validate_rights(self.s, self.request, rights, bad)


if __name__ == '__main__': unittest.main()
