from pathlib import Path
import sys,json,hashlib,copy,tempfile,unittest,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'scripts/native_1c_db_oracle/periodic_information_register_packet'
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle')]
from periodic_information_register_packet import periodic_packet as p
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
        self.assertEqual(props.findtext(md+'InformationRegisterPeriodicity'),'Second')
        self.assertFalse(props.findtext(md+'RecordSetModule'));self.assertFalse(props.findtext(md+'ManagerModule'))
        children=obj.find(md+'ChildObjects')
        self.assertEqual([n.tag.removeprefix(md) for n in children],['Resource']*3+['Attribute']+['Dimension']*2)
        dim={n.findtext(md+'Properties/'+md+'Name'):n for n in children.findall(md+'Dimension')}
        self.assertEqual(dim['Product'].findtext(md+'Properties/'+md+'Indexing'),'Index')
        self.assertTrue(all(len(x)<=65536 for x in raw.values()))
    def test_measured_owned_defaults_are_explicit_not_stripped(self):
        md='{'+p.linked.setup_adapter.MD+'}';xr='{http://v8.1c.ru/8.3/xcf/readable}';xsi='{http://www.w3.org/2001/XMLSchema-instance}'
        obj=ET.fromstring(next(iter(p.xml(self.s,self.p).values()))).find(md+'InformationRegister')
        self.assertEqual([n.get('category') for n in obj.find(md+'InternalInfo')],list(p.NATIVE_FAMILIES))
        props=obj.find(md+'Properties')
        for name in ('ObjectBelonging','Help','RecordSetModule','ManagerModule','AdditionalIndexes'):self.assertIsNone(props.find(md+name))
        standards=props.find(md+'StandardAttributes')
        self.assertEqual([n.get('name') for n in standards],['Active','LineNumber','Recorder','Period'])
        self.assertEqual([n.findtext(xr+'FillChecking') for n in standards],['DontCheck']*3+['ShowError'])
        for field in obj.find(md+'ChildObjects'):
            values=field.find(md+'Properties');name=values.findtext(md+'Name');fill=values.find(md+'FillValue')
            self.assertEqual(fill.attrib,{xsi+'type':'xs:string'} if name=='Note' else {xsi+'nil':'true'})
            self.assertEqual(values.findtext(md+'FillFromFillingValue'),'false')
            if field.tag==md+'Dimension':self.assertEqual(values.findtext(md+'DenyIncompleteValues'),'false')
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
        for old,new in ((b'</Properties>',b'<RecordSetModule>handler.bsl</RecordSetModule></Properties>'),
            (b'</Properties>',b'<ManagerModule>handler.bsl</ManagerModule></Properties>'),
            (b'<WriteMode>Independent',b'<WriteMode>RecorderSubordinate'),
            (b'<InformationRegisterPeriodicity>Second',b'<InformationRegisterPeriodicity>Day'),
            (b'xmlns:cfg="'+p.linked.CFG.encode()+b'"',b'xmlns:cfg="urn:wrong"'),
            (b'<Indexing>Index</Indexing>',b'<Indexing>DontIndex</Indexing>')):
            self.assertIn(old,saved[name]);actual=dict(saved);actual[name]=actual[name].replace(old,new);self.assertNotEqual(actual[name],saved[name])
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
    def test_parser_readonly_and_closed_temporal_scope(self):
        for reverse in (False,True):
            s,pr=p.fresh(reverse)
            for block in p.BLOCKS:
                text=p.render(s,pr,block);parse(text)
                self.assertEqual(len(p.cases(s,pr,block)),24);self.assertLessEqual(len(text.encode()),8192)
                for x in ('New Query','.Write(','.CreateRecordManager(','.CreateItem(','.Delete('):self.assertNotIn(x,text)
            for state in p.STATES:parse(p.setup(s,pr,state))
            self.assertEqual(p.setup(s,pr,'filled').count('R.Write(False)'),5)
        self.assertNotEqual(list(p.records()),p.ordered_records())
        self.assertEqual(len({(r[0],r[1],r[2]) for r in p.records()}),5)
        self.assertEqual(len({r[2] for r in p.records()}),3)
        self.assertEqual(len([r for r in p.records() if r[2]==p.T1]),3)
        for name in ('EnableTotalsSliceFirst','EnableTotalsSliceLast'):
            self.assertIn(f'<{name}>false</{name}>',p.REGISTER_PROPERTIES)
        self.assertIn('<DataHistory>DontUse</DataHistory>',p.REGISTER_PROPERTIES)
    def test_exact_and_neighbor_edges_and_public_result_observations(self):
        get=p.render(self.s,self.p,'get');sl=p.render(self.s,self.p,'slices');ed=p.render(self.s,self.p,'edges')
        for value in (p.T0,p.T1,p.T2,p.T1+' + 1',p.T1+' - 1',p.T2+' + 1'):self.assertIn(value,get)
        for value in ('GetFirst','GetLast','Property("Period")','Property("Note")'):self.assertIn(value,get)
        for value in ('SliceFirst','SliceLast','Columns.Count()','Product.Description','LK[0].Note'):self.assertIn(value,sl)
        for label in ('before','exact.end','exact.again','desc.end','missing','period.type'):self.assertIn(label,dict(p.cases(self.s,self.p,'edges')))
        self.assertIn(f'Select({p.T1},{p.T1},',ed)
    def test_witness_full_key_and_temporal_values(self):
        values=[self.p['register'],self.p['catalog'],5,2]
        for product,variant,period,price,available,date,note in p.ordered_records():
            values += [True,self.s.base.record_ids[0] if product=='A' else self.p['ids']['product2'],'2024-02-29T12:00:'+{p.T0:'00',p.T1:'01',p.T2:'02'}[period],True]
        self.assertEqual(len(p.require_setup(wire(values),self.s,self.p,'filled')),24)
        for i in range(2,24):
            bad=values.copy();bad[i]='wrong'
            with self.subTest(i=i),self.assertRaises(ValueError):p.require_setup(wire(bad),self.s,self.p,'filled')
        self.assertEqual(len(p.require_setup(wire([self.p['register'],self.p['catalog'],0,0]+[False]*20),self.s,self.p,'empty')),24)
    def test_saved_inputs_no_regeneration(self):
        seen=[]
        for root in sorted((HERE/'generated').iterdir()):
            m=json.loads((root/'manifest.json').read_text(encoding='utf-8'));pr=m['profile'];seen.append(pr)
            s=p.linked.Setup(p.linked.probe.Setup(*(tuple(m[k]) for k in ('names','metadata_ids','record_ids'))),*(tuple(m[k]) for k in ('product_rows','attribute_names','attribute_ids','order'))).validate()
            for name,raw in p.xml(s,pr).items():self.assertEqual((root/name).read_bytes(),raw)
            for state in p.STATES:self.assertEqual((root/f'setup-{state}.bsl').read_text(encoding='utf-8'),p.setup(s,pr,state))
            for block in p.BLOCKS:self.assertEqual((root/f'{block}.bsl').read_text(encoding='utf-8'),p.render(s,pr,block))
            for name,digest in m['files'].items():self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
        self.assertNotEqual(seen[0]['metadata_uuid'],seen[1]['metadata_uuid']);self.assertEqual(seen[0]['columns'],list(reversed(seen[1]['columns'])))
    def test_generation_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst=Path(tmp)/'generated';p.generate(dst)
            with self.assertRaises(ValueError):p.generate(dst)
    def test_schema_and_method_primary_proof(self):
        facts=json.loads(p.SCHEMA.read_bytes());self.assertEqual(facts['periodic_input']['periodicity'],'Second')
        self.assertEqual(facts['periodic_input']['enum_definition_sha256'],facts['backend_sha256'])
        # Archive bytes were independently checked during packet preparation.
        # Public tests require only the pinned, source-owned facts, never network or vendor archives.
        self.assertEqual(hashlib.sha256(p.SCHEMA.read_bytes()).hexdigest(),p.SCHEMA_SHA)
        methods=facts['periodic_input']['methods']
        self.assertEqual(len(methods),5)
        for entry in methods:
            self.assertEqual(len(entry['sha256']),64)
            self.assertTrue(entry['member'].endswith('.html'))
if __name__=='__main__':unittest.main()
