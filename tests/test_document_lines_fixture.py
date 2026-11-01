"""Closed saved line input/identity and semantic redump tests; no native proof."""
import copy,json,hashlib
from pathlib import Path
import sys,unittest
from unittest import mock
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts')]
import document_lines_fixture as f
import inputs
from snapshots import OracleError


def wire(values):
    def scalar(v):
        if type(v) is str:return 'S'+str(len(v.encode('utf-16-be'))//2)+':'+v.encode('utf-16-be').hex()
        if type(v) is bool:return 'B'+str(int(v))
        return 'N'+str(v)
    return f.scalar_wire.C1+f.scalar_wire.C2+b''.join(
        f'CR-{i:02}: [ok|{scalar(v)}]\n'.encode() for i,v in enumerate(values,1))


class DocumentLinesFixtureTests(unittest.TestCase):
    def setUp(self):
        self.s,self.manifest,self.files=f.load(1);self.p=self.manifest['profile']
        self.saved={n:b for n,b in self.files.items() if n.endswith('.xml')}
        self.doc='Documents/'+self.p['base']['document_name']+'.xml'

    def test_saved_both_identities_and_exact_packet(self):
        other,manifest,_=f.load(2)
        self.assertNotEqual(self.s,other)
        self.assertEqual(self.p['columns'],list(reversed(manifest['profile']['columns'])))
        self.assertEqual(len(self.files),10);self.assertEqual(f.profile(self.s),self.p)
        self.assertEqual(self.manifest['native_status'],'not-applied')
        for n,b in self.files.items():self.assertEqual(hashlib.sha256(b).hexdigest(),self.manifest['files'][n])

    def test_manifest_status_extra_file_hash_and_cases_fail_closed(self):
        original=inputs.read_source
        for mutate in (lambda m:m.update(native_status='applied'),
                       lambda m:m['files'].update({'unexpected.bsl':'0'*64}),
                       lambda m:m['files'].update({'identity.bsl':'0'*64}),
                       lambda m:m['cases']['identity'].__setitem__(0,['invented','True'])):
            value=copy.deepcopy(self.manifest);mutate(value)
            def read(path):
                return json.dumps(value).encode() if Path(path).name=='manifest.json' else original(path)
            with mock.patch.object(inputs,'read_source',side_effect=read),self.assertRaises((ValueError,OracleError)):
                f.load(1)

    def test_full_semantic_qname_redump_and_separate_section_identities(self):
        actual={n:b.replace(b'<MetaDataObject ',b'<MetaDataObject xmlns:unused="urn:unused" ',1)
                for n,b in self.saved.items()}
        self.assertTrue(f.verify_redump(self.s,self.p,self.saved,actual))
        mapping=f.actual_mapping(self.s,self.p,actual)
        self.assertEqual(mapping['objects'][0]['metadata_uuid'],self.p['base']['document_uuid'])
        section=mapping['section'];ids=self.p['ids']
        self.assertEqual(section['metadata_uuid'],ids['section'])
        self.assertEqual(section['type_uuid'],ids['section_type'])
        self.assertEqual(section['row_type_uuid'],ids['row_type'])
        self.assertEqual(section['value_uuid'],ids['section_value'])
        self.assertEqual(section['row_value_uuid'],ids['row_value'])
        self.assertEqual(section['columns'],[dict(name=n,metadata_uuid=ids[n]) for n in self.p['columns']])
        for old,new in ((ids['row_type'].encode(),ids['section'].encode()),
                        (b'<LineNumberLength>5',b'<LineNumberLength>4'),
                        (b'http://www.w3.org/2001/XMLSchema"',b'urn:wrong"'),
                        (b'</Properties>',b'<ObjectModule>unsafe</ObjectModule></Properties>'),
                        (b'<xr:StandardAttribute name="LineNumber">',b'<xr:StandardAttribute name="LineNumber"><Added/>')):
            changed=dict(actual);self.assertIn(old,changed[self.doc]);changed[self.doc]=changed[self.doc].replace(old,new)
            with self.assertRaises(ValueError):f.actual_mapping(self.s,self.p,changed)
        with self.assertRaises(ValueError):f.verify_redump(self.s,self.p,self.saved,{})

    def test_configuration_and_rights_inventory_unchanged(self):
        raw=(f'<MetaDataObject xmlns="{f.MD}"><Configuration><ChildObjects>'
             '<Catalog>NativeOracleItems</Catalog><Role>Keep</Role></ChildObjects></Configuration></MetaDataObject>').encode()
        rights=Path(f.linked.__file__).with_name('base').joinpath('CRUDRights.xml').read_bytes().replace(b'@@CONFIGURATION_NAME@@',b'Owned')
        extended=f.extend_sources(self.s,self.p,self.saved,raw,rights)
        newrights=extended['Roles/NativeOracleCatalogCRUD/Ext/Rights.xml']
        self.assertTrue(f.document.validate_rights(self.s,self.p['base'],rights,newrights))
        ns='{http://v8.1c.ru/8.2/roles}'
        doc=next(n for n in ET.fromstring(newrights).findall(ns+'object')
                 if n.findtext(ns+'name')=='Document.'+self.p['base']['document_name'])
        self.assertEqual([n.findtext(ns+'name') for n in doc.findall(ns+'right')],['Read','Insert','Update','Posting'])
        for extra in (b'<Catalog>Other</Catalog>',b'<Document>Other</Document>'):
            with self.assertRaises(ValueError):f.extend_sources(self.s,self.p,self.saved,
                raw.replace(b'</ChildObjects>',extra+b'</ChildObjects>'),rights)

    def test_initial_three_documents_two_products_and_rewrite_counts(self):
        u,absent=self.s.base.record_ids;values=[self.p['base']['document_name'],self.p['base']['catalog_name'],3,2]
        for number,target in (('20',absent),('30',u),('10','00000000-0000-0000-0000-000000000000')):
            values += [True,number,True,number=='30',target]
        values += [False]+[True]*4
        self.assertEqual(len(f.require_setup_evidence(wire(values),self.s,'initial')),24)
        values[3]=1
        with self.assertRaises(ValueError):f.require_setup_evidence(wire(values),self.s,'initial')
        rewritten=[self.p['base']['document_name'],self.p['base']['catalog_name'],0,1,3]+[True]*19
        self.assertEqual(len(f.require_setup_evidence(wire(rewritten),self.s,'rewritten')),24)
        rewritten[4]=2
        with self.assertRaises(OracleError):f.require_setup_evidence(wire(rewritten),self.s,'rewritten')

    def test_witness_owner_line_and_phase_are_independent(self):
        p=self.p;s=self.s
        for state in f.STATES:
            values=[p['base']['document_name'],p['base']['catalog_name']]
            refs={'present':s.base.record_ids[0],'second':p['ids']['product2'],
                  'absent':s.base.record_ids[1],'empty':'00000000-0000-0000-0000-000000000000'}
            for owner in ('10','20'):
                for i,(target,qty,price,amount,note) in enumerate(f.packet.specs(state,owner),1):
                    values += [True,owner,i,amount,refs[target]]
            values += [False,0]
            self.assertEqual(len(f.require_witness(wire(values),s,state)),24)
            values[3]='30'
            with self.assertRaises(ValueError):f.require_witness(wire(values),s,state)
        with self.assertRaises(OracleError):f.require_witness(b'',s,'other')

if __name__=='__main__':unittest.main()
