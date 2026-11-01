from pathlib import Path
import sys,json,hashlib,copy,tempfile,unittest,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle')]
from information_register_packet import register_packet as p
from yadinassi.syntax.parser import parse

def wire(values):
    def scalar(v):
        if type(v) is str:return 'S'+str(len(v.encode('utf-16-be'))//2)+':'+v.encode('utf-16-be').hex()
        if type(v) is bool:return 'B'+str(int(v))
        return 'N'+str(v)
    w=p.linked.scalar_wire
    return w.C1+w.C2+b''.join(f'CR-{i:02}: [ok|{scalar(v)}]\n'.encode() for i,v in enumerate(values,1))

class Tests(unittest.TestCase):
    def setUp(self):self.s,self.p=p.fresh()
    def test_xml_profile(self):
        raw=p.xml(self.s,self.p);self.assertTrue(p.validate_xml(self.s,self.p,raw))
        md='{'+p.linked.setup_adapter.MD+'}';root=ET.fromstring(raw[next(iter(raw))]);obj=root.find(md+'InformationRegister');props=obj.find(md+'Properties')
        self.assertEqual(props.findtext(md+'WriteMode'),'Independent')
        self.assertEqual(props.findtext(md+'InformationRegisterPeriodicity'),'Nonperiodical')
        self.assertFalse(props.findtext(md+'RecordSetModule'));self.assertFalse(props.findtext(md+'ManagerModule'))
        children=obj.find(md+'ChildObjects')
        self.assertEqual([n.tag.removeprefix(md) for n in children],['Resource']*3+['Attribute']+['Dimension']*2)
        dim={n.findtext(md+'Properties/'+md+'Name'):n for n in children.findall(md+'Dimension')}
        self.assertEqual(dim['Product'].findtext(md+'Properties/'+md+'Indexing'),'Index')
        self.assertTrue(all(len(x)<=65536 for x in raw.values()))
    def test_closed_names_modes_and_identities(self):
        for key,value in (('register','Injected";Raise'),('catalog','Wrong'),('write_mode','RecorderSubordinate'),('periodicity','Day'),('extra',1),('columns',list(p.FIELDS)[:-1])):
            bad=copy.deepcopy(self.p);bad[key]=value
            for call in (lambda:p.xml(self.s,bad),lambda:p.render(self.s,bad,'get'),lambda:p.setup(self.s,bad,'filled'),lambda:p.capture(b'',self.s,bad)):
                with self.subTest(key=key),self.assertRaises(ValueError):call()
        bad=copy.deepcopy(self.p);bad['ids']['Price']=bad['ids']['Variant']
        with self.assertRaises(ValueError):p.xml(self.s,bad)
        bad=copy.deepcopy(self.p);bad['ids']['Price']=self.s.base.metadata_ids[0]
        with self.assertRaises(ValueError):p.xml(self.s,bad)
        bad=copy.deepcopy(self.p);bad['columns']=tuple(bad['columns'])
        with self.assertRaises(ValueError):p.render(self.s,bad,'get')
    def test_modules_namespaces_and_index_closed(self):
        saved=p.xml(self.s,self.p);name=next(iter(saved))
        for old,new in ((b'<RecordSetModule></RecordSetModule>',b'<RecordSetModule>handler.bsl</RecordSetModule>'),
            (b'<ManagerModule></ManagerModule>',b'<ManagerModule>handler.bsl</ManagerModule>'),
            (b'<WriteMode>Independent',b'<WriteMode>RecorderSubordinate'),
            (b'<InformationRegisterPeriodicity>Nonperiodical',b'<InformationRegisterPeriodicity>Day'),
            (b'xmlns:cfg="'+p.linked.CFG.encode()+b'"',b'xmlns:cfg="urn:wrong"'),
            (b'<Indexing>Index</Indexing>',b'<Indexing>DontIndex</Indexing>')):
            actual=dict(saved);actual[name]=actual[name].replace(old,new)
            with self.assertRaises(ValueError):p.validate_xml(self.s,self.p,actual)
    def test_exact_scoped_read_update_rights(self):
        baseline=(ROOT/'scripts/native_1c_db_oracle/linked_card_packet/base/CRUDRights.xml').read_bytes().replace(b'@@CONFIGURATION_NAME@@',b'Owned')
        result=p.rights(self.s,self.p,baseline);self.assertTrue(p.validate_rights(self.s,self.p,baseline,result))
        ns='{http://v8.1c.ru/8.2/roles}';obj=next(n for n in ET.fromstring(result).findall(ns+'object') if n.findtext(ns+'name').startswith('InformationRegister.'))
        self.assertEqual([n.findtext(ns+'name') for n in obj.findall(ns+'right')],['Read','Update'])
        for grant in ('Insert','Delete','InteractiveUpdate','Administration','Posting'):
            bad=result.replace(b'</Rights>',('<object><name>InformationRegister.'+self.p['register']+'</name><right><name>'+grant+'</name><value>true</value></right></object></Rights>').encode())
            with self.assertRaises(ValueError):p.validate_rights(self.s,self.p,baseline,bad)
        with self.assertRaises(ValueError):p.rights(self.s,self.p,baseline.replace(b'<name>ThickClient</name>',b'<name>Administration</name>'))
    def test_parser_and_bounded_readonly(self):
        for block in p.BLOCKS:
            source=p.render(self.s,self.p,block);parse(source)
            self.assertEqual(len(p.cases(self.s,self.p,block)),24);self.assertLessEqual(len(source.encode()),8192)
            for forbidden in ('New Query','.Write(','.CreateRecordManager(','.CreateItem(','.Delete('):self.assertNotIn(forbidden,source)
        for state in p.STATES:
            source=p.setup(self.s,self.p,state);parse(source);self.assertLessEqual(len(source.encode()),8192)
        self.assertEqual(p.setup(self.s,self.p,'filled').count('R.Write(False)'),3)
    def test_key_shape_and_unmeasured_boundaries_observed(self):
        get=dict(p.cases(self.s,self.p,'get'));types=dict(p.cases(self.s,self.p,'types'));filtered=dict(p.cases(self.s,self.p,'filter'))
        self.assertEqual(get['has.note'],'G1.Property("Note")');self.assertIn('missing.type',get)
        for key in ('before','exhaust','retained','restart'):self.assertIn(key,types)
        self.assertIn('missing',filtered);self.assertIn('desc1',filtered)
        self.assertIn('Structure("Product,Variant"',p.render(self.s,self.p,'get'))
    def test_query_witness_and_empty_control(self):
        values=[self.p['register'],self.p['catalog'],3,2]
        for key,variant,price,available,date,note in sorted(p.records(),key=lambda r:(r[0],r[1])):
            values += [True,self.s.base.record_ids[0] if key=='A' else self.p['ids']['product2'],variant,price,available=='True',True]
        values += [False,self.p['register']]
        self.assertEqual(len(p.require_setup(wire(values),self.s,self.p,'filled')),24)
        for index in (2,3,5,6,7,8,9,22):
            bad=values.copy();bad[index]='wrong'
            with self.assertRaises(ValueError):p.require_setup(wire(bad),self.s,self.p,'filled')
        empty=[self.p['register'],self.p['catalog'],0,0]+[False]*18+[False,self.p['register']]
        self.assertEqual(len(p.require_setup(wire(empty),self.s,self.p,'empty')),24)
    def test_new_identity_generation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'generated';p.generate(root)
            m=[json.loads(f.read_text()) for f in sorted(root.glob('*/manifest.json'))]
            self.assertNotEqual(m[0]['metadata_ids'],m[1]['metadata_ids'])
            self.assertEqual(m[0]['profile']['columns'],list(reversed(m[1]['profile']['columns'])))
            self.assertTrue(all(len(x['files'])==8 for x in m))
            with self.assertRaises(ValueError):p.generate(root)
    def test_saved_replay_no_identity_regeneration(self):
        for root in sorted((ROOT/'scripts/native_1c_db_oracle/information_register_packet/generated').iterdir()):
            m=json.loads((root/'manifest.json').read_text());pr=m['profile']
            s=p.linked.Setup(p.linked.probe.Setup(*(tuple(m[k]) for k in ('names','metadata_ids','record_ids'))),*(tuple(m[k]) for k in ('product_rows','attribute_names','attribute_ids','order'))).validate()
            for name,raw in p.xml(s,pr).items():self.assertEqual((root/name).read_bytes(),raw)
            for state in p.STATES:self.assertEqual((root/f'setup-{state}.bsl').read_text(),p.setup(s,pr,state))
            for block in p.BLOCKS:self.assertEqual((root/f'{block}.bsl').read_text(),p.render(s,pr,block))
            for name,digest in m['files'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
if __name__=='__main__':unittest.main()
