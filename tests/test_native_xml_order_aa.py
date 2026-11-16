"""Offline A/A contracts, not native evidence."""
import copy,json,os,sys,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import native_1c_xml_order_aa as aa
from xml_order_packet import measurement as m

class AATests(unittest.TestCase):
    def setUp(self):self.files=aa.packet.baseline(aa.base.source_files())
    def report(self,case='aa1',nonce='a'*32,hashes=None):
        r=aa.empty(nonce,case,{} if hashes is None else hashes,aa.packet.digest_files(self.files))
        fp=m.fingerprint(self.files,known_names=self.files)
        r.update(status='collected',phase='complete',failure='none',completed=list(aa.PHASES),dumps=[fp,fp])
        return r
    def test_operations_four_designer_after_load_no_enterprise(self):
        ops=aa.operations(Path('/tmp/owned'))
        self.assertEqual([x[0] for x in ops],list(aa.PHASES))
        self.assertNotIn('ENTERPRISE',[s for _,cmd in ops for s in cmd])
        self.assertEqual([cmd[cmd.index('/F')+1] for _,cmd in ops[1:]],['/tmp/owned/db']*5)
        self.assertEqual([cmd[cmd.index('/DumpConfigToFiles')+1] for _,cmd in ops if '/DumpConfigToFiles' in cmd],['/tmp/owned/dump1','/tmp/owned/dump2'])
        self.assertEqual(sum('/LoadConfigFromFiles' in cmd for _,cmd in ops),1)
    def test_schema_rejects_forgery_and_overbudget(self):
        r=self.report();aa.validate(json.dumps(r).encode(),'a'*32,'aa1',{},self.files)
        for k,v in (('nonce','b'*32),('source','c'*64),('enterprise_executed',True),('completed',['dump1']),('phase','load'),('dumps',[])):
            bad=copy.deepcopy(r);bad[k]=v
            with self.assertRaises(ValueError):aa.validate(json.dumps(bad).encode(),'a'*32,'aa1',{},self.files)
        for k,v in (('raw_sha256','secret'),('slot',True),('known_slot',1000),('uuid_token_count',-1),('legacy_excluded','yes')):
            bad=copy.deepcopy(r);bad['dumps'][0]['files'][0][k]=v
            with self.assertRaises(ValueError):aa.validate(json.dumps(bad).encode(),'a'*32,'aa1',{},self.files)
        with self.assertRaises(ValueError):aa.validate(b' '*(aa.MAX_REPORT+1),'a'*32,'aa1',{},self.files)
        with self.assertRaises(ValueError):aa.validate(b'{"case":"bad",'+json.dumps(r).encode()[1:],'a'*32,'aa1',{},self.files)
    def test_exact_uuid_and_configdump_differences_remain(self):
        x={'Configuration.xml':b'<x uuid="11111111-1111-1111-1111-111111111111"/>','ConfigDumpInfo.xml':b'<info>1</info>'}
        y={**x,'Configuration.xml':x['Configuration.xml'].replace(b'11111111-1111-1111-1111-111111111111',b'22222222-2222-2222-2222-222222222222')}
        c=m.compare(m.fingerprint(x),m.fingerprint(y));self.assertFalse(c['raw_equal']);self.assertFalse(c['strict_equal']);self.assertFalse(c['permutation_equal'])
        self.assertEqual(c['slots'][0]['category'],'projected_uuid_token_difference_only')
        y={**x,'ConfigDumpInfo.xml':b'<info>2</info>'}
        c=m.compare(m.fingerprint(x),m.fingerprint(y));self.assertFalse(c['strict_equal']);self.assertTrue(c['slots'][0]['legacy_excluded'])
    def test_permitted_permutation_is_not_raw_only(self):
        a={aa.packet.META:b'<r><Properties><Name>X</Name><FormType>Managed</FormType></Properties></r>'}
        b={aa.packet.META:b'<r><Properties><FormType>Managed</FormType><Name>X</Name></Properties></r>'}
        c=m.compare(m.fingerprint(a),m.fingerprint(b))
        self.assertEqual(c['slots'][0]['category'],'permitted_permutation_difference')
        self.assertFalse(c['strict_equal']);self.assertTrue(c['permutation_equal'])
        a={'x.xml':b'<r a="1" b="2"/>'};b={'x.xml':b'<r b="2" a="1"/>'}
        self.assertEqual(m.compare(m.fingerprint(a),m.fingerprint(b))['slots'][0]['category'],'raw_only_difference')

    def test_bounds_and_untrusted_fingerprint(self):
        for data in ({'x'*1025+b'.xml'.decode():b'<r/>'},{'x.xml':b'<r>'*65+b'</r>'*65}):
            with self.assertRaises(ValueError):m.fingerprint(data)
        fp=m.fingerprint({'x.xml':b'<r/>'});fp['files'][0]['private']='secret'
        with self.assertRaises(ValueError):m.validate(fp)
    def test_comparisons_have_two_repeats_two_cross_and_no_semantic_pass(self):
        reports={c:self.report(c) for c in aa.CASES}
        comparisons=aa.comparisons(reports)
        self.assertEqual(set(comparisons),{'aa1_repeat','aa2_repeat','cross_dump1','cross_dump2'})
        self.assertTrue(all(v['raw_equal'] for v in comparisons.values()))
        self.assertNotIn('semantic_acceptance',comparisons)
    def test_host_uses_two_distinct_owned_containers_same_source(self):
        import native_1c_smoke as smoke
        import native_1c_docker_lifecycle as lifecycle
        seen=[];hashes=aa.inventory(ROOT)
        def fake(cmd,env,**kw):
            seen.append((cmd[-1],kw['nonce'],kw['name']))
            self.assertNotIn('GHCR_TOKEN',env);self.assertEqual(cmd[cmd.index('--network')+1],'none')
            path=Path(cmd[cmd.index('--mount')+1].split('src=')[1].split(',')[0])
            self.assertFalse((path.parent/'auth').exists());self.assertEqual(aa.inventory(path),hashes)
            return 0,json.dumps(self.report(cmd[-1],kw['nonce'],hashes)).encode()
        with mock.patch.dict(os.environ,{'GHCR_USER':'Atridis','GHCR_TOKEN':'TEST_SECRET','GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'},clear=True),mock.patch.object(aa.base,'revision',return_value=('a'*40,'b'*40)),mock.patch.object(aa.policy,'check_environment',return_value='a'*40),mock.patch.object(smoke,'run_silent'),mock.patch.object(lifecycle,'run_owned',side_effect=fake):
            result=aa.run_host()
        self.assertEqual([x[0] for x in seen],list(aa.CASES));self.assertNotEqual(seen[0][1],seen[1][1]);self.assertNotEqual(seen[0][2],seen[1][2])
        self.assertTrue(result['acquisition_complete']);self.assertFalse(result['enterprise_executed'])
        self.assertEqual(result['semantic_acceptance'],'NOT PROVEN');self.assertNotIn('TEST_SECRET',json.dumps(result))
        self.assertEqual(result['cases']['aa1']['source'],result['cases']['aa2']['source'])
    def test_current_workflow_scope_and_aa_command(self):
        w=(ROOT/'.github/workflows/native-1c-xml-order.yml').read_text()
        self.assertIn('native_1c_xml_order_detail.py --execute-approved-image',w)
        self.assertNotIn('native_1c_xml_order.py --execute-approved-image',w)
        self.assertIn('branches: [codex/xml-order-native-reviewed]',w)
        self.assertIn('timeout-minutes: 65',w)
        self.assertIn('cancel-in-progress: false',w)
        cmd=aa.command(Path('/tmp/staged'),'a'*32,'aa1')
        self.assertIn('/smoke/scripts/native_1c_xml_order_aa.sh',cmd)
        self.assertNotIn('GHCR_TOKEN',' '.join(cmd))

if __name__=='__main__':unittest.main()
