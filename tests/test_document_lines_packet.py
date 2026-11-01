from pathlib import Path
import copy,json,hashlib,sys,tempfile,unittest,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle')]
from document_lines_packet import lines_packet as p
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
    def test_closed_schema_input_and_unchanged_header(self):
        actual=p.xml(self.s,self.p);self.assertTrue(p.validate_xml(self.s,self.p,actual))
        name='Documents/'+self.p['base']['document_name']+'.xml';old=p.base.document_xml(self.s,self.p['base'])
        root=ET.fromstring(actual[name]);child=root.find(p.base.MD+'Document/'+p.base.MD+'ChildObjects')
        section=child.find(p.base.MD+'TabularSection')
        self.assertEqual(section.findtext(p.base.MD+'Properties/'+p.base.MD+'Name'),'Items')
        attrs=section.findall(p.base.MD+'ChildObjects/'+p.base.MD+'Attribute')
        self.assertEqual([a.findtext(p.base.MD+'Properties/'+p.base.MD+'Name') for a in attrs],list(p.COLUMNS))
        child.remove(section)
        self.assertEqual(ET.tostring(root),ET.tostring(ET.fromstring(old[name])))
        self.assertEqual(actual['Catalogs/'+self.p['base']['catalog_name']+'.xml'],old['Catalogs/'+self.p['base']['catalog_name']+'.xml'])
    def test_closed_profile_injection_and_identity_alias_refused(self):
        for key,value in (('section','Items";Raise'),('source','wrong'),('columns',['Product']),('extra','x')):
            bad=copy.deepcopy(self.p);bad[key]=value
            for operation in (lambda:p.xml(self.s,bad),lambda:p.render(self.s,bad,'rows'),lambda:p.setup(self.s,bad,'initial'),lambda:p.capture(b'',self.s,bad)):
                with self.assertRaises(ValueError):operation()
        bad=copy.deepcopy(self.p);bad['ids']['section']=self.s.base.metadata_ids[0]
        with self.assertRaises(ValueError):p.xml(self.s,bad)
        bad=copy.deepcopy(self.p);bad['ids']['Price']=bad['ids']['Amount']
        with self.assertRaises(ValueError):p.xml(self.s,bad)
    def test_parse_budgets_and_readonly_observers(self):
        for block in p.BLOCKS:
            text=p.render(self.s,self.p,block);parse(text);self.assertLessEqual(len(text.encode()),8192)
            self.assertEqual(len(p.cases(self.s,self.p,block)),24)
            for forbidden in ('.Write(','.Add(','.Clear(','.GetObject(', 'New Query'):
                self.assertNotIn(forbidden,text)
        for state in p.STATES:
            for text in (p.setup(self.s,self.p,state),p.witness(self.s,self.p,state)):
                parse(text);self.assertLessEqual(len(text.encode()),8192)
    def test_distinct_transition_and_owner_shapes(self):
        self.assertEqual([len(p.specs('initial',n)) for n in ('30','10','20')],[0,1,3])
        self.assertNotEqual(p.specs('initial','20'),p.specs('rewritten','20'))
        initial=p.setup(self.s,self.p,'initial');rewrite=p.setup(self.s,self.p,'rewritten')
        self.assertEqual(initial.count('P.Items.Add()'),4);self.assertNotIn('.Clear()',initial)
        self.assertEqual(rewrite.count('P.Items.Clear()'),1)
        self.assertEqual(rewrite.count('P.Items.Add()'),3)
        self.assertIn(self.s.product_rows[1],rewrite);self.assertNotIn('DocumentWriteMode.Posting',rewrite)
        self.assertEqual(initial.count('DocumentWriteMode.Posting'),1)
    def test_raw_witness_checks_owner_line_amount_target(self):
        for state in p.STATES:
            values=[self.p['base']['document_name'],self.p['base']['catalog_name']]
            for owner in ('10','20'):
                for i,row in enumerate(p.specs(state,owner),1):
                    target,quantity,price,amount,note=row
                    target={'present':self.s.base.record_ids[0],'empty':str(p.uuid.UUID(int=0)),'absent':self.s.base.record_ids[1],'second':self.p['ids']['product2']}[target]
                    values += [True,owner,i,amount,target]
            values += [False,0]
            self.assertEqual(len(p.require_witness(wire(values),self.s,self.p,state)),24)
            for index in (3,4,5,6,18,20,22,23):
                bad=values.copy();bad[index]='wrong'
                with self.subTest(state=state,index=index),self.assertRaises(ValueError):p.require_witness(wire(bad),self.s,self.p,state)
    def test_two_targets_and_initial_header_witness(self):
        self.assertEqual(p.setup(self.s,self.p,'initial').count('C = Catalogs.'),2)
        u,absent=self.s.base.record_ids
        values=[self.p['base']['document_name'],self.p['base']['catalog_name'],3,2]
        for number,target in (('20',absent),('30',u),('10',str(p.uuid.UUID(int=0)))):
            values += [True,number,True,number=='30',target]
        values += [False]+[True]*4
        self.assertEqual(len(p.require_initial_setup(wire(values),self.s,self.p)),24)
        values[3]=1
        with self.assertRaises(ValueError):p.require_initial_setup(wire(values),self.s,self.p)
        cases=dict(p.cases(self.s,self.p,'identity'))
        self.assertIn('empty.ref.count',cases);self.assertIn('missing.ref.count',cases)
        self.assertIn('second.product.description',cases)

    def test_saved_files_replay_same_identities(self):
        for d in sorted((ROOT/'scripts/native_1c_db_oracle/document_lines_packet/generated').iterdir()):
            m=json.loads((d/'manifest.json').read_text(encoding='utf-8'));pr=m['profile']
            setup=p.linked.Setup(p.linked.probe.Setup(*(tuple(m[k]) for k in ('names','metadata_ids','record_ids'))),
                *(tuple(m[k]) for k in ('product_rows','attribute_names','attribute_ids','order'))).validate()
            for name,raw in p.xml(setup,pr).items():self.assertEqual((d/name).read_bytes(),raw)
            for state in p.STATES:
                self.assertEqual((d/f'setup-{state}.bsl').read_text(encoding='utf-8'),p.setup(setup,pr,state))
                self.assertEqual((d/f'witness-{state}.bsl').read_text(encoding='utf-8'),p.witness(setup,pr,state))
            for block in p.BLOCKS:self.assertEqual((d/f'{block}.bsl').read_text(encoding='utf-8'),p.render(setup,pr,block))
            for name,digest in m['files'].items():self.assertEqual(hashlib.sha256((d/name).read_bytes()).hexdigest(),digest)

    def test_generation_independent_reversed_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'packet';p.generate(root)
            manifests=[json.loads(f.read_text(encoding='utf-8')) for f in sorted(root.glob('*/manifest.json'))]
            self.assertNotEqual(manifests[0]['metadata_ids'],manifests[1]['metadata_ids'])
            self.assertEqual(manifests[0]['profile']['columns'],list(reversed(manifests[1]['profile']['columns'])))
            for m in manifests:self.assertEqual(len(m['files']),10)
            with self.assertRaises(ValueError):p.generate(root)
if __name__=='__main__':unittest.main()
