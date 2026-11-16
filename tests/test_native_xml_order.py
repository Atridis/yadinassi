"""Offline contracts only; fake native reports never prove 1C semantics."""
import copy, json, sys, unittest
from unittest import mock
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import native_1c_xml_order as runner
import native_1c_xml_order_ci_policy as policy
from xml_order_packet import packet
from xml_order_packet.mutations import projection,rearrange,attributes,parent
import native_1c_main_demo_designer as base

class XMLOrderTests(unittest.TestCase):
    def setUp(self):self.source=base.source_files();self.baseline=packet.baseline(self.source)
    def test_mutations_are_one_axis_and_reversible(self):
        original=packet.digest_files(self.source)
        for case in packet.CASES:
            files=packet.case_files(self.source,case)
            changed=[k for k in files if files[k]!=self.baseline[k]]
            self.assertEqual(changed,[] if case=='baseline' else [packet.META if case in ('properties','duplicate_property') else packet.FORM])
            self.assertEqual(files[packet.MODULE],self.baseline[packet.MODULE])
            if case in ('attributes','properties','events'):
                for k in changed:self.assertEqual(projection(files[k],True),projection(self.baseline[k],True))
            if case in ('handler_changed','ui_childitems'):
                self.assertNotEqual(projection(files[packet.FORM],True),projection(self.baseline[packet.FORM],True))
            if case in ('duplicate_property','duplicate_event'):
                with self.assertRaises(ValueError):projection(files[changed[0]],True)
        self.assertEqual(original,packet.digest_files(self.source))
        raw=self.baseline[packet.FORM]
        self.assertEqual(attributes(attributes(raw)),raw)
        for section in ('Events','ChildItems'):self.assertEqual(rearrange(rearrange(raw,section),section),raw)
    def test_local_scopes_and_qnames_preserved(self):
        raw=b'<r xmlns:p="urn:outer"><Properties><A xmlns:p="urn:inner" q="p:T"/><B q="p:T"/></Properties></r>'
        self.assertEqual(projection(raw,True),projection(rearrange(raw,'Properties'),True))
        self.assertNotEqual(projection(raw,True),projection(raw.replace(b'urn:inner',b'urn:changed'),True))
    def test_unchanged_ui_and_outside_bytes(self):
        for case in ('properties','events','handler_changed','duplicate_property','duplicate_event'):
            path=packet.META if 'propert' in case else packet.FORM
            section='Properties' if path==packet.META else 'Events'
            left=self.baseline[path];right=packet.case_files(self.source,case)[path]
            a=parent(left,section);b=parent(right,section)
            self.assertEqual(left[:a['head']],right[:b['head']]);self.assertEqual(left[a['end']:],right[b['end']:])
    def test_only_copied_observers_and_modules(self):
        changed=[k for k in self.baseline if self.baseline[k]!=self.source[k]]
        self.assertEqual(set(changed),{packet.FORM,packet.MODULE,'Ext/ManagedApplicationModule.bsl'})
        self.assertNotIn('InventoryApplication.xml',self.baseline)
        for n in ('Created','Closing'):
            self.assertNotIn((n+'(').encode(),(packet.ROOT/'startup.bsl').read_bytes())
    def trace(self,case='baseline'):
        ui=list(packet.UI)
        if case=='ui_childitems':ui[:2]=reversed(ui[:2])
        return dict(nonce='a'*32,events=['create','open_effect','items:'+','.join(ui),'closing_blocked','cancel_effect','closing_allowed','closed'])
    def test_runtime_witness_rejects_missing_changed_replayed_order(self):
        t=self.trace();self.assertEqual(packet.witness(json.dumps(t).encode(),'a'*32,'baseline'),'baseline')
        self.assertEqual(packet.witness(json.dumps(self.trace('ui_childitems')).encode(),'a'*32,'ui_childitems'),'changed')
        for bad in (dict(t,nonce='b'*32),dict(t,events=t['events'][:-1]),dict(t,events=t['events']+['closed']),self.trace('ui_childitems')):
            with self.assertRaises(ValueError):packet.witness(json.dumps(bad).encode(),'a'*32,'baseline')
    def report(self,case='baseline'):
        r=runner.empty('a'*32,case,{'fixed':'b'*64},'c'*64)
        r.update(completed=list(runner.PHASES),phase='complete',failure='none',redump='d'*64,lifecycle='observed',runtime_items_order='changed' if case=='ui_childitems' else 'baseline',status='collected')
        return r
    def validate(self,r):return runner.validate(json.dumps(r).encode(),'a'*32,'baseline',{'fixed':'b'*64},'c'*64)
    def test_report_binding_and_finite_values(self):
        r=self.report();self.validate(r)
        for k,v in (('source','d'*64),('inputs',{}),('nonce','b'*32),('visual_ui','PASS'),('runtime_items_order','arbitrary'),('phase','load'),('completed',['load']),('redump','native secret')):
            bad=dict(r);bad[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):self.validate(bad)
        with self.assertRaises(ValueError):runner.validate(b'{' + b'"case":"evil",'+json.dumps(r).encode()[1:],'a'*32,'baseline',{'fixed':'b'*64},'c'*64)
        with self.assertRaises(ValueError):runner.validate(b' '*(runner.MAX_REPORT+1),'a'*32,'baseline',{},'')
    def test_negative_never_equivalent_and_baseline_gate(self):
        reports={c:self.report(c) for c in packet.CASES}
        results=runner.assessment(reports)
        self.assertEqual(results['events'],'runtime_and_redump_match_visual_pending')
        self.assertEqual(results['ui_childitems'],'inconclusive_ui_control')
        for c in ('duplicate_property','duplicate_event'):self.assertIn('never_equivalent',results[c])
        self.assertEqual(results['handler_changed'],'not_equivalent')
        reports['baseline']['status']='failed'
        self.assertEqual(set(runner.assessment(reports).values()),{'inconclusive_baseline'})
    def test_acquisition_requires_negative_controls_and_redump(self):
        reports={c:self.report(c) for c in packet.CASES}
        reports['ui_childitems']['redump']='e'*64
        reports['handler_changed'].update(status='failed',phase='check',failure='native_rejected',completed=list(runner.PHASES[:2]),lifecycle='NOT RUN',runtime_items_order='NOT RUN',redump=None)
        self.assertTrue(runner.acquisition_complete(reports))
        for case in packet.CASES:
            bad=copy.deepcopy(reports);bad[case].update(status='failed',phase='enterprise',failure='timeout')
            self.assertFalse(runner.acquisition_complete(bad))
        for case in ('handler_changed','duplicate_property','duplicate_event'):
            bad=copy.deepcopy(reports);bad[case].update(status='failed',phase='enterprise',failure='witness',completed=list(runner.PHASES[:5]))
            self.assertFalse(runner.acquisition_complete(bad))
        for failure in ('process','result'):
            bad=copy.deepcopy(reports);bad['handler_changed']['failure']=failure
            self.assertFalse(runner.acquisition_complete(bad))
            self.assertNotEqual(runner.assessment(bad)['handler_changed'],'rejected')
        bad=copy.deepcopy(reports);bad['properties']['redump']=None
        self.assertFalse(runner.acquisition_complete(bad))
    def test_projection_preserves_significant_leaf_whitespace(self):
        self.assertNotEqual(projection(b'<r><A> x </A></r>'),projection(b'<r><A>x</A></r>'))
    def test_host_stages_no_auth_and_uses_owned_lifecycle(self):
        import native_1c_smoke as smoke
        import native_1c_docker_lifecycle as lifecycle
        seen=[]
        hashes=runner.inventory(ROOT)
        def fake(cmd,env,**kwargs):
            case=cmd[-1];nonce=kwargs['nonce'];seen.append(case)
            self.assertNotIn('GHCR_TOKEN',env)
            self.assertNotIn('GITHUB_TOKEN',env)
            mount=cmd[cmd.index('--mount')+1]
            staged=Path(mount.split('src=',1)[1].split(',',1)[0])
            self.assertEqual(runner.inventory(staged),hashes)
            self.assertFalse((staged.parent/'auth').exists())
            r=self.report(case);r.update(nonce=nonce,inputs=hashes,source=packet.digest_files(packet.case_files(self.source,case)))
            if case=='ui_childitems':r['redump']='e'*64
            if case=='handler_changed':
                r.update(status='failed',phase='check',failure='native_rejected',completed=list(runner.PHASES[:2]),lifecycle='NOT RUN',runtime_items_order='NOT RUN',redump=None)
                return 1,json.dumps(r).encode()
            return 0,json.dumps(r).encode()
        with mock.patch.dict(runner.os.environ,{'GHCR_USER':'Atridis','GHCR_TOKEN':'TEST_SECRET','GITHUB_TOKEN':'OTHER_SECRET','GITHUB_RUN_ID':'1','GITHUB_RUN_ATTEMPT':'1'},clear=True), mock.patch.object(base,'revision',return_value=('a'*40,'b'*40)), mock.patch.object(policy,'check_environment',return_value='a'*40), mock.patch.object(smoke,'run_silent'), mock.patch.object(lifecycle,'run_owned',side_effect=fake):
            report=runner.run_host()
        self.assertEqual(seen,list(packet.CASES))
        self.assertTrue(report['acquisition_complete'])
        self.assertTrue(report['container_cleanup_verified'])
        self.assertEqual(report['semantic_acceptance'],'NOT PROVEN')
        self.assertNotIn('TEST_SECRET',json.dumps(report))

    def test_native_rejection_requires_valid_nonzero_dumpresult(self):
        for raw,value in ((b'0',0),(b'1',1),('2'.encode('utf-16'),2)):
            with mock.patch.object(base,'read_regular',return_value=raw):
                self.assertEqual(runner.designer_result(Path('/unused')),value)
        for raw in (b'',b'crash',b'01',b'-1',b'0\\nerror',b'1'*100):
            with mock.patch.object(base,'read_regular',return_value=raw),self.assertRaises(ValueError):
                runner.designer_result(Path('/unused'))

    def context(self,event='push'):
        sha='a'*40;ref='refs/heads/codex/xml-order-native-reviewed'
        owner=dict(login='Atridis',id=30860798,type='User')
        e=dict(repository=dict(full_name='Atridis/yadinassi',id=359770628,fork=False,owner=owner),sender=owner,ref=ref,deleted=False,forced=False,after=sha,head_commit=dict(id=sha))
        c=dict(GITHUB_REPOSITORY='Atridis/yadinassi',GITHUB_REPOSITORY_ID='359770628',GITHUB_REPOSITORY_OWNER='Atridis',GITHUB_REPOSITORY_OWNER_ID='30860798',GITHUB_ACTOR='Atridis',GITHUB_ACTOR_ID='30860798',NATIVE_TRIGGERING_ACTOR='Atridis',GITHUB_REF_TYPE='branch',GITHUB_BASE_REF='',GITHUB_HEAD_REF='',GITHUB_SHA=sha,GITHUB_REF=ref,GITHUB_WORKFLOW_SHA=sha,GITHUB_WORKFLOW_REF='Atridis/yadinassi/.github/workflows/native-1c-xml-order.yml@'+ref,GITHUB_EVENT_NAME=event,NATIVE_DISPATCH_INPUTS='{}')
        if event=='workflow_dispatch':e['inputs']={'reviewed_sha':sha};c['NATIVE_DISPATCH_INPUTS']=json.dumps(e['inputs'])
        return e,c
    def test_owner_admission_and_push_before_default_catalog(self):
        for event in ('push','workflow_dispatch'):
            e,c=self.context(event);self.assertEqual(policy.admission(e,c),'a'*40)
            for k,v in (('GITHUB_ACTOR_ID','1'),('GITHUB_REF','refs/heads/main'),('GITHUB_WORKFLOW_SHA','b'*40),('NATIVE_TRIGGERING_ACTOR','other'),('GITHUB_EVENT_NAME','pull_request')):
                bad=dict(c);bad[k]=v
                with self.assertRaises(ValueError):policy.admission(e,bad)
            bad=copy.deepcopy(e);bad['repository']['fork']=True
            with self.assertRaises(ValueError):policy.admission(bad,c)
        e,c=self.context();e['forced']=True
        with self.assertRaises(ValueError):policy.admission(e,c)
    def test_workflow_embedded_policy_and_isolation(self):
        workflow=(ROOT/'.github/workflows/native-1c-xml-order.yml').read_text()
        script=(ROOT/'scripts/native_1c_xml_order_ci_policy.py').read_text()
        start='# BEGIN XML ORDER ADMISSION';end='# END XML ORDER ADMISSION'
        embedded=workflow[workflow.index(start):workflow.index(end)+len(end)]
        self.assertEqual('\n'.join(line[10:] if line.startswith(' '*10) else line for line in embedded.splitlines()),script[script.index(start):script.index(end)+len(end)])
        self.assertIn('branches: [codex/xml-order-native-reviewed]',workflow)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertNotIn('pull_request:',workflow)
        cmd=runner.command(Path('/tmp/staged'),'a'*32,'events')
        for flag in ('--read-only','--cap-drop','--network','--init','--tmpfs'):self.assertIn(flag,cmd)
        self.assertEqual(cmd[cmd.index('--network')+1],'none')
        self.assertIn('readonly',cmd[cmd.index('--mount')+1]);self.assertIn('-i',cmd)
        self.assertNotIn('GHCR_TOKEN',' '.join(cmd));self.assertEqual(cmd[-1],'events')
        self.assertEqual(cmd[cmd.index('--name')+1],'onec-xml-order-'+'a'*32)

if __name__=='__main__':unittest.main()
