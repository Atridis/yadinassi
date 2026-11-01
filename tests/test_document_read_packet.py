import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT)]
from document_read_packet import document_packet as p
PACKET=ROOT/'scripts/native_1c_db_oracle/document_read_packet'

def wire(values):
    def scalar(v):
        if type(v) is str:return 'S'+str(len(v.encode('utf-16-be'))//2)+':'+v.encode('utf-16-be').hex()
        if type(v) is bool:return 'B'+str(int(v))
        return 'N'+str(v)
    w=p.linked.scalar_wire
    return w.C1+w.C2+b''.join(f'CR-{i:02}: [ok|{scalar(v)}]\n'.encode() for i,v in enumerate(values,1))

class PacketTests(unittest.TestCase):
    def setUp(self):
        self.s=p.linked.fresh();self.request=p.profile(self.s,p.linked.schema_request(self.s))
    def test_schema_pins(self):
        raw=(PACKET/'document_schema.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),p.PROFILE_SHA)
        facts=json.loads(raw)
        self.assertEqual(facts['source_sha256'],p.SCHEMA_SHA)
        self.assertEqual(facts['enums']['Posting'],['Allow','Deny'])
    def test_exact_document_profile(self):
        raw=p.document_xml(self.s,self.request);self.assertTrue(p.validate_xml(self.s,self.request,raw))
        doc=ET.fromstring(raw['Documents/'+self.request['document_name']+'.xml'])
        self.assertEqual(len(doc.findall('.//'+p.MD+'Attribute')),5)
        self.assertEqual(doc.findtext('.//'+p.MD+'Posting'),'Allow')
        self.assertEqual(doc.findtext('.//'+p.MD+'NumberPeriodicity'),'Nonperiodical')
        self.assertEqual(len(doc.findall('.//'+p.MD+'RegisterRecords/*')),0)
        for item in raw.values():self.assertLessEqual(len(item),65536)
    def test_mutation_refused(self):
        for key,value in (('posting','Deny'),('number_length',True),('attributes',0)):
            bad=copy.deepcopy(self.request);bad[key]=value
            with self.assertRaises(ValueError):p.document_xml(self.s,bad)
        raw=p.document_xml(self.s,self.request);name=next(iter(raw))
        for old,new in ((b'<Posting>Allow',b'<Posting>Deny'),(b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"',b'xmlns:cfg="urn:wrong"')):
            bad=dict(raw);bad[name]=bad[name].replace(old,new)
            with self.assertRaises(ValueError):p.validate_xml(self.s,self.request,bad)
    def test_observers_are_bounded_readonly(self):
        for block in p.BLOCKS:
            text=p.render_block(self.s,self.request,block)
            self.assertEqual(len(p.cases(self.s,self.request,block)),24)
            self.assertLessEqual(len(text.encode()),8192)
            for forbidden in ('CreateDocument','CreateItem','.Write(','.Delete(', 'New Query','.Post('):
                self.assertNotIn(forbidden,text)
        self.assertIn('S = Undefined; Try S = Documents.',p.render_block(self.s,self.request,'cursor'))
        numeric=[expr for key,expr in p.cases(self.s,self.request,'fields') if key.endswith('.number')]
        self.assertTrue(all(x.startswith('XMLString(') for x in numeric))
    def test_bsl_parse_and_inclusive_range_observations(self):
        from yadinassi.syntax.parser import parse
        for block in p.BLOCKS:parse(p.render_block(self.s,self.request,block))
        for state in p.STATES:parse(p.render_setup(self.s,self.request,state)[0])
        cursor=p.render_block(self.s,self.request,'cursor')
        self.assertIn('.Select(Date(2024,2,29,12,34,56),Date(2024,2,29,12,34,56))',cursor)
        self.assertIn('// empty.range',cursor)

    def test_empty_number_discriminants_replace_only_header_padding(self):
        cases=p.cases(self.s,self.request,'header')
        self.assertEqual(len(cases),24)
        self.assertEqual([label for label,_ in cases[-2:]],['empty.number.type','empty.number.uuid'])
        self.assertIn('TypeOf(',cases[-2][1]);self.assertIn('.UUID()',cases[-1][1])
        self.assertTrue(all('FindByNumber("")' in expression for _,expression in cases[-2:]))

    def test_fresh_reference_observations_are_raw_and_relational(self):
        cases=dict(p.cases(self.s,self.request,'identity'))
        self.assertEqual(cases['fresh.omitted.uuid'],'String(F.UUID())')
        self.assertEqual(cases['fresh.undefined.uuid'],'String(G.UUID())')
        self.assertEqual(cases['fresh.distinct'],'F <> G')
        self.assertIn('Not ValueIsFilled',cases['empty.type.filled'])
        text=p.render_block(self.s,self.request,'identity')
        self.assertIn('.GetRef(); Except EndTry;',text)
        self.assertIn('.GetRef(Undefined); Except EndTry;',text)

    def test_setup_single_owned_regular_posting_and_independent_query(self):
        for state in p.STATES:
            text,w=p.render_setup(self.s,self.request,state)
            self.assertEqual(len(w),24);self.assertLessEqual(len(text.encode()),8192)
            self.assertIn('ORDER BY Date',text)
            self.assertEqual(text.count('P.Write(DocumentWriteMode.Posting, DocumentPostingMode.Regular)'),int(state=='filled'))
            self.assertNotIn('P.Posted =',text)
        text,_=p.render_setup(self.s,self.request,'filled')
        self.assertEqual(text.count('.CreateDocument()'),3)
        self.assertIn('P.Number = "30"; P.Date = Date(2024,2,29',text)
    def test_typed_setup_evidence(self):
        s=self.s;r=self.request;u,missing=s.base.record_ids
        values=[r['document_name'],r['catalog_name'],3,1,
            True,'20',True,False,missing,True,'30',True,True,u,
            True,'10',True,False,str(p.linked.uuid.UUID(int=0)),False,True,True,True,True]
        self.assertEqual(len(p.require_setup_evidence(wire(values),s,r,'filled')),24)
        for index in (2,6,7,8,13,18):
            bad=values.copy();bad[index]='wrong'
            with self.assertRaises(ValueError):p.require_setup_evidence(wire(bad),s,r,'filled')
    def test_every_public_observation_path_validates_closed_profile(self):
        operations=[
            lambda r:p.cases(self.s,r,'header'),
            lambda r:p.render_block(self.s,r,'identity'),
            lambda r:p.render_setup(self.s,r,'filled'),
            lambda r:p.require_capture(b'invalid',self.s,r),
            lambda r:p.require_setup_evidence(b'invalid',self.s,r,'filled')]
        mutations=[
            ('document_name','D"; Raise "injected'),
            ('catalog_name','Other'),
            ('extra',True),('role','Administration'),
            ('number_length',8.0),('attributes',True)]
        for key,value in mutations:
            for operation in operations:
                bad=copy.deepcopy(self.request);bad[key]=value
                with self.subTest(key=key),self.assertRaisesRegex(ValueError,'document-profile'):
                    operation(bad)
        bad=copy.deepcopy(self.request);bad['linked_schema']['catalogs']=tuple(bad['linked_schema']['catalogs'])
        with self.assertRaises(ValueError):p.render_setup(self.s,bad,'filled')
        bad=copy.deepcopy(self.request);bad['extra']=bad
        with self.assertRaises(ValueError):p.render_block(self.s,bad,'identity')
        for state in ('posted',True,None,[]):
            with self.subTest(state=state),self.assertRaisesRegex(ValueError,'state'):
                p.render_setup(self.s,self.request,state)
            with self.assertRaisesRegex(ValueError,'state'):
                p.require_setup_evidence(b'invalid',self.s,self.request,state)
        for block in ('arbitrary',True,None,[]):
            with self.assertRaises(ValueError):p.render_block(self.s,self.request,block)
        bad=copy.deepcopy(self.request);bad['linked_schema']['catalogs'][0]['attributes'][0]['type']='Arbitrary'
        with self.assertRaises(ValueError):p.cases(self.s,bad,'identity')

    def test_closed_roles_and_inert_fixture_properties(self):
        baseline=(ROOT/'scripts/native_1c_db_oracle/linked_card_packet/base/CRUDRights.xml').read_bytes().replace(b'@@CONFIGURATION_NAME@@',b'Owned')
        actual=p.extend_rights(self.s,self.request,baseline)
        self.assertTrue(p.validate_rights(self.s,self.request,baseline,actual))
        ns='{http://v8.1c.ru/8.2/roles}'
        doc=next(o for o in ET.fromstring(actual).findall(ns+'object') if o.findtext(ns+'name').startswith('Document.'))
        self.assertEqual({r.findtext(ns+'name') for r in doc.findall(ns+'right')},{'Read','Insert','Update','Posting'})
        for right in ('Delete','InteractivePosting','UndoPosting','Administration'):
            injected=actual.replace(b'</Rights>',('<object><name>Document.'+self.request['document_name']+'</name><right><name>'+right+'</name><value>true</value></right></object></Rights>').encode())
            with self.subTest(right=right),self.assertRaises(ValueError):p.validate_rights(self.s,self.request,baseline,injected)
        for old,new in ((('Document.'+self.request['document_name']).encode(),b'Document.Arbitrary'),(b'<name>Posting</name>',b'<name>Administration</name>')):
            with self.assertRaises(ValueError):p.validate_rights(self.s,self.request,baseline,actual.replace(old,new))
        with self.assertRaises(ValueError):p.extend_rights(self.s,self.request,baseline.replace(b'<name>ThickClient</name>',b'<name>Administration</name>'))
        xml=p.document_xml(self.s,self.request);name=next(iter(xml))
        for old,new in ((b'</Properties>',b'<ObjectModule>handler.bsl</ObjectModule></Properties>'),
                        (b'</Properties>',b'<ManagerModule>manager.bsl</ManagerModule></Properties>'),
                        (b'<RegisterRecords></RegisterRecords>',b'<RegisterRecords><xr:Item>Register.X</xr:Item></RegisterRecords>'),
                        (b'<PostInPrivilegedMode>false',b'<PostInPrivilegedMode>true'),
                        (b'<RealTimePosting>Deny',b'<RealTimePosting>Allow')):
            self.assertIn(old,xml[name])
            changed=dict(xml);changed[name]=changed[name].replace(old,new)
            self.assertNotEqual(changed[name],xml[name])
            with self.assertRaises(ValueError):p.validate_xml(self.s,self.request,changed)

    def test_measured_native_standard_attributes_and_omitted_catalog_only_inputs(self):
        # Owned native redump41255615774, not guessed from Designer defaults.
        self.assertEqual(hashlib.sha256(p.DOCUMENT_STANDARD_ATTRIBUTES.encode()).hexdigest(),
            'ec28e4a88df41269c39955d19eefadca34696069851f52190682b393e0fc9d1a')
        artifacts=p.document_xml(self.s,self.request)
        raw=artifacts['Documents/'+self.request['document_name']+'.xml']
        doc=ET.fromstring(raw).find(p.MD+'Document');props=doc.find(p.MD+'Properties')
        for name in ('ObjectBelonging','ObjectModule','ManagerModule','Help','AdditionalIndexes'):
            self.assertIsNone(props.find(p.MD+name))
        xr='{http://v8.1c.ru/8.3/xcf/readable}'
        attrs=props.find(p.MD+'StandardAttributes')
        self.assertEqual([a.get('name') for a in attrs],['Posted','Ref','DeletionMark','Date','Number'])
        self.assertEqual([a.findtext(xr+'FillChecking') for a in attrs],
            ['DontCheck','DontCheck','DontCheck','ShowError','DontCheck'])
        for attr in doc.findall(p.MD+'ChildObjects/'+p.MD+'Attribute'):
            self.assertIsNone(attr.find(p.MD+'Properties/'+p.MD+'Use'))
        for old,new in ((b'<xr:FillChecking>ShowError',b'<xr:FillChecking>DontCheck'),
                        (b'<StandardAttributes>',b'<StandardAttributes><Extra/>')):
            changed=dict(artifacts);name='Documents/'+self.request['document_name']+'.xml'
            self.assertIn(old,raw);changed[name]=raw.replace(old,new)
            self.assertNotEqual(changed[name],raw)
            with self.assertRaises(ValueError):p.validate_xml(self.s,self.request,changed)

    def test_saved_artifacts_match_sources_without_identity_regeneration(self):
        for root in sorted((PACKET/'generated').iterdir()):
            m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
            s=p.linked.Setup(p.linked.probe.Setup(*(tuple(m[k]) for k in ('names','metadata_ids','record_ids'))),
                *(tuple(m[k]) for k in ('product_rows','attribute_names','attribute_ids','order'))).validate()
            request=m['profile']
            for name,raw in p.document_xml(s,request).items():self.assertEqual((root/name).read_bytes(),raw)
            for block in p.BLOCKS:self.assertEqual((root/f'{block}.bsl').read_text(encoding='utf-8'),p.render_block(s,request,block))
            for state in p.STATES:self.assertEqual((root/f'setup-{state}.bsl').read_text(encoding='utf-8'),p.render_setup(s,request,state)[0])
            for name,digest in m['files'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)

    def test_two_identity_batches_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'generated';p.generate(dest)
            manifests=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(dest.glob('*/manifest.json'))]
            self.assertNotEqual(manifests[0]['metadata_ids'],manifests[1]['metadata_ids'])
            self.assertEqual(manifests[0]['order'],list(reversed(manifests[1]['order'])))
            self.assertTrue(all(len(m['files'])==8 for m in manifests))
            with self.assertRaises(ValueError):p.generate(dest)
if __name__=='__main__':unittest.main()
