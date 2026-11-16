"""Offline detail-run tests; native observations remain a separate result."""
import copy,json,os,re,sys,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import native_1c_xml_order_detail as host
from xml_order_packet import paths,detail_packet as detail,measurement as m,packet
DUMP=b'<ConfigDumpInfo xmlns="http://v8.1c.ru/8.3/xcf/dumpinfo" version="2.17"><ConfigVersions><Metadata name="Configuration.test" id="11111111-1111-1111-1111-111111111111" configVersion="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/></ConfigVersions></ConfigDumpInfo>'

class DetailTests(unittest.TestCase):
    def setUp(self):self.source=host.base.source_files();self.files=detail.files(self.source,'baseline1')
    def report(self,case='baseline1',nonce='a'*32,hashes=None):
        files=detail.files(self.source,case);dump={**files,'ConfigDumpInfo.xml':DUMP}
        r=host.empty(nonce,case,hashes or {},packet.digest_files(files))
        fp=m.fingerprint(dump,known_names=files);pd=paths.export(dump,files)
        r.update(completed=list(host.PHASES),phase='complete',failure='none',status='collected',dumps=[fp,fp],path_dumps=[pd,pd],
            redump_bindings=[detail.expected_bindings(case)]*2,designer_complete=True,enterprise_attempted=True,
            runtime_witness='observed',trace={'state':'observed','codes':detail.expected_trace(case)})
        return r
    def test_control_one_binding_identical_modules_server_signature(self):
        other=detail.files(self.source,'handler_compatible')
        self.assertEqual([k for k in self.files if self.files[k]!=other[k]],[packet.FORM])
        self.assertEqual(self.files,detail.files(self.source,'baseline2'))
        text=self.files[packet.MODULE].decode()
        self.assertRegex(text,r'&НаСервере\s+Процедура ChangedCreated\(Cancel, StandardProcessing\)')
        self.assertIn('DraftTitle = "XML-order changed";',text)
        self.assertNotRegex(text,r'(?m)^\s*Created\(')
        self.assertEqual(detail.bindings(other[packet.FORM])['OnCreateAtServer'],'ChangedCreated')
        self.assertEqual(detail.bindings(self.files[packet.FORM])['BeforeClose'],'Closing')
    def test_binding_duplicate_and_unknown_rejected(self):
        raw=self.files[packet.FORM]
        for bad in (raw.replace(b'</Events>',b'<Event name="OnOpen">XmlOrderOpen</Event></Events>'),raw.replace(b'>Created<',b'>PrivateUnknown<')):
            with self.assertRaises(ValueError):detail.bindings(bad)
    def test_exact_path_uuid_and_source_relation(self):
        dump={**self.files,'ConfigDumpInfo.xml':DUMP}
        changed=copy.deepcopy(dump)
        changed['Configuration.xml']=changed['Configuration.xml'].replace(b'a572bff0-7809-5c97-9060-1d1d988fdddb',b'22222222-2222-2222-2222-222222222222')
        a=paths.export(dump,self.files);b=paths.export(changed,self.files);paths.validate(b,self.files)
        difference=paths.compare(a,b)['Configuration.xml']['changes']
        self.assertEqual(len(difference),1);d=difference[0]
        self.assertEqual(d['path'][-2][1],3)
        self.assertEqual(d['path'][-1][0],'{http://v8.1c.ru/8.3/xcf/readable}ObjectId')
        self.assertEqual((d['field'],d['kind'],d['left_source'],d['right_source']),('#text','uuid','same','changed'))
    def test_unlike_tag_order_is_not_erased(self):
        dump={**self.files,'ConfigDumpInfo.xml':DUMP}
        original=dump['Configuration.xml']
        self.assertIn(b'<NamePrefix />',original)
        self.assertIn(b'<Comment />',original)
        changed={**dump,'Configuration.xml':original.replace(b'<NamePrefix />',b'<NamePrefix>same</NamePrefix>').replace(b'<Comment />',b'<Comment>same</Comment>')}
        moved={**changed,'Configuration.xml':changed['Configuration.xml'].replace(b'<NamePrefix>same</NamePrefix>',b'<SWAP />').replace(b'<Comment>same</Comment>',b'<NamePrefix>same</NamePrefix>').replace(b'<SWAP />',b'<Comment>same</Comment>')}
        differences=paths.compare(paths.export(changed,self.files),paths.export(moved,self.files))['Configuration.xml']['changes']
        self.assertEqual(len(differences),2)
        self.assertTrue(all(x['category']=='position_changed' for x in differences))

    def test_unknown_subtree_and_values_not_exported(self):
        dump={**self.files,'ConfigDumpInfo.xml':DUMP,'private.xml':b'<Private>DO_NOT_EXPORT</Private>'}
        dump['Configuration.xml']=dump['Configuration.xml'].replace(b'</Configuration>',b'<PrivateSecret>DO_NOT_EXPORT</PrivateSecret></Configuration>')
        r=paths.export(dump,self.files);wire=json.dumps(r)
        self.assertNotIn('PrivateSecret',wire);self.assertNotIn('DO_NOT_EXPORT',wire);self.assertNotIn('private.xml',wire)
        self.assertGreater(r['Configuration.xml']['omitted'],0)
        self.assertNotIn('a572bff0-7809-5c97',wire)
    def test_schema_rejects_path_and_report_forgeries(self):
        r=self.report();host.validate(json.dumps(r).encode(),'a'*32,'baseline1',{},self.files)
        changes=[('source','0'*64),('designer_complete',False),('enterprise_attempted',False),('runtime_witness','NOT RUN')]
        for k,v in changes:
            bad=copy.deepcopy(r);bad[k]=v
            with self.assertRaises(ValueError):host.validate(json.dumps(bad).encode(),'a'*32,'baseline1',{},self.files)
        bad=copy.deepcopy(r);bad['path_dumps'][0]['Configuration.xml']['rows'][0]['path'][0][0]='PrivateQName'
        with self.assertRaises(ValueError):host.validate(json.dumps(bad).encode(),'a'*32,'baseline1',{},self.files)
        bad=copy.deepcopy(r);bad['redump_bindings'][0]['OnCreateAtServer']='Closing'
        with self.assertRaises(ValueError):host.validate(json.dumps(bad).encode(),'a'*32,'baseline1',{},self.files)
        self.assertLess(len(json.dumps(r).encode()),host.MAX_REPORT)
    def test_partial_trace_never_means_success(self):
        r=self.report();r.update(status='failed',phase='enterprise',failure='timeout',completed=list(host.PHASES[:6]),runtime_witness='NOT OBSERVED',trace={'state':'observed','codes':['create']})
        host.validate(json.dumps(r).encode(),'a'*32,'baseline1',{},self.files)
        self.assertFalse(host.semantic_observations({'baseline1':r})['compatible_handler_effect_distinguished'])
        bad=self.report();bad.update(status='failed',phase='enterprise',failure='diagnostic')
        self.assertFalse(host.semantic_observations({'baseline1':bad,'baseline2':bad})['baseline_lifecycle_repeat_observed'])
        for raw in (None,b'{}',b'{"nonce":"wrong","events":["create"]}'):
            self.assertIn(detail.trace(raw,'a'*32)['state'],('missing','invalid'))
    def test_trace_distinguishes_actual_effect(self):
        a=detail.expected_trace('baseline1');b=detail.expected_trace('handler_compatible')
        self.assertNotEqual(a,b);self.assertEqual(a[2:],b[2:])
        for trace in (a,b):self.assertEqual(detail.trace(json.dumps(dict(nonce='a'*32,events=trace)).encode(),'a'*32),dict(state='observed',codes=trace))
        r=self.report('handler_compatible');r['trace']['codes']=a
        with self.assertRaises(ValueError):host.validate(json.dumps(r).encode(),'a'*32,'handler_compatible',{},detail.files(self.source,'handler_compatible'))
    def test_host_three_containers_identical_input_baselines_and_finite_output(self):
        import native_1c_smoke as smoke
        import native_1c_docker_lifecycle as lifecycle
        seen=[];hashes=host.inventory(ROOT)
        def fake(cmd,env,**kw):
            seen.append((cmd[-1],kw['nonce']))
            self.assertNotIn('GHCR_TOKEN',env);self.assertEqual(cmd[cmd.index('--network')+1],'none')
            path=Path(cmd[cmd.index('--mount')+1].split('src=')[1].split(',')[0]);self.assertFalse((path.parent/'auth').exists())
            self.assertEqual(host.inventory(path),hashes)
            return 0,json.dumps(self.report(cmd[-1],kw['nonce'],hashes)).encode()
        with mock.patch.dict(os.environ,{'GHCR_USER':'Atridis','GHCR_TOKEN':'TEST_SECRET','GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'},clear=True),mock.patch.object(host.base,'revision',return_value=('a'*40,'b'*40)),mock.patch.object(host.policy,'check_environment',return_value='a'*40),mock.patch.object(smoke,'run_silent'),mock.patch.object(lifecycle,'run_owned',side_effect=fake):
            r=host.run_host()
        self.assertEqual([c for c,n in seen],list(detail.CASES));self.assertEqual(len({n for c,n in seen}),3)
        self.assertTrue(r['semantic_observations']['compatible_handler_effect_distinguished']);self.assertEqual(r['semantic_acceptance'],'NOT PROVEN')
        self.assertLess(len(json.dumps(r).encode()),host.MAX_HOST_REPORT)
    def test_workflow_and_operation_scope(self):
        ops=host.operations(Path('/tmp/test'))
        self.assertEqual([p for p,c in ops],list(host.PHASES));self.assertEqual(sum(c[1]=='ENTERPRISE' for p,c in ops),1)
        w=(ROOT/'.github/workflows/native-1c-xml-order.yml').read_text()
        self.assertIn('native_1c_xml_order_detail.py --execute-approved-image',w);self.assertNotIn('pull_request:',w)
        self.assertIn('cancel-in-progress: false',w)

if __name__=='__main__':unittest.main()
