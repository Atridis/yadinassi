"""Offline contract only: no Docker, Designer or runtime parity claims."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

host = load('native_1c_main_demo_designer')
policy = load('native_1c_main_demo_ci_policy')

class MainDemoDesignerTests(unittest.TestCase):
    def report(self):
        return dict(schema=host.SCHEMA,nonce='a'*32,status='ok',phase='complete',failure='none',
            input_sha256={'fixture':'b'*64},source_sha256=host.SOURCE_SHA256,
            platform_sha256={n:host.SOURCE_SHA256[n] for n in host.PLATFORM_FILES},
            excluded_files=[host.MANIFEST],check_flags=list(host.CHECK_FLAGS),completed=list(host.PHASES),diagnostics=host.diagnostics.empty())
    def validate(self, value):
        return host.validate_report(json.dumps(value).encode(),'a'*32,{'fixture':'b'*64})
    def context(self):
        user=dict(login='Atridis',id=30860798,type='User')
        c=dict(GITHUB_REPOSITORY='Atridis/yadinassi',GITHUB_REPOSITORY_ID='359770628',
            GITHUB_REPOSITORY_OWNER='Atridis',GITHUB_REPOSITORY_OWNER_ID='30860798',
            GITHUB_ACTOR='Atridis',GITHUB_ACTOR_ID='30860798',NATIVE_TRIGGERING_ACTOR='Atridis',
            GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF_TYPE='branch',GITHUB_BASE_REF='',
            GITHUB_HEAD_REF='',GITHUB_SHA='a'*40,GITHUB_REF='refs/heads/codex/demo',
            GITHUB_WORKFLOW_SHA='a'*40,GITHUB_WORKFLOW_REF=
            'Atridis/yadinassi/.github/workflows/native-1c-main-demo-designer.yml@refs/heads/codex/demo',
            NATIVE_DISPATCH_INPUTS=json.dumps({'reviewed_sha':'a'*40}))
        e=dict(repository=dict(full_name='Atridis/yadinassi',id=359770628,fork=False,owner=user),
            sender=user,ref='codex/demo',inputs={'reviewed_sha':'a'*40})
        return e,c

    def test_source_is_canonical_33_and_projection_is_exact_32(self):
        source=host.source_files()
        self.assertEqual(len(source),33)
        original=ast.literal_eval(ast.parse((ROOT/'yadinassi/main_demo_source.py').read_text()).body[1].value)
        self.assertEqual(host.SOURCE_SHA256,original)
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'source';host.stage_source(target,source)
            self.assertEqual(host.dump_files(target),{n:raw for n,raw in source.items() if n!=host.MANIFEST})
            self.assertEqual(len(host.dump_files(target)),32)

    def test_projection_refuses_changed_or_extra_bytes(self):
        source=host.source_files()
        for change in ({**source,'extra.xml':b'x'},{**source,'Configuration.xml':b'x'}):
            with tempfile.TemporaryDirectory() as temp, self.assertRaises(host.DemoError):
                host.stage_source(Path(temp)/'source',change)

    def test_regular_input_refuses_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'a';p.write_bytes(b'x');q=Path(temp)/'b';q.symlink_to(p)
            with self.assertRaises(host.DemoError):host.read_regular(q)
            q.unlink();q.hardlink_to(p)
            with self.assertRaises(host.DemoError):host.read_regular(p)

    def test_operations_only_create_load_check_update(self):
        operations=host.operations(Path('/tmp/owned'))
        self.assertEqual([p for p,_ in operations],list(host.PHASES))
        self.assertEqual(operations[0][1][1],'CREATEINFOBASE')
        self.assertTrue(all(c[1]=='DESIGNER' for _,c in operations[1:]))
        flat=[x for _,c in operations for x in c]
        self.assertNotIn('ENTERPRISE',flat);self.assertNotIn('/DumpConfigToFiles',flat)
        self.assertIn('/LoadConfigFromFiles',flat);self.assertIn('/UpdateDBCfg',flat)
        for flag in host.CHECK_FLAGS:self.assertIn(flag,flat)

    def test_container_isolation_and_pinned_image(self):
        command=host.container_command(Path('/tmp/staged'),'a'*32)
        for flag,value in (('--network','none'),('--user','1000:1000'),('--cap-drop','ALL'),
                ('--security-opt','no-new-privileges:true'),('--pull','never'),('--platform','linux/amd64')):
            self.assertEqual(command[command.index(flag)+1],value)
        self.assertIn('--read-only',command);self.assertIn(host.IMAGE,command)
        self.assertEqual(command.count('--mount'),1)
        self.assertIn('readonly',command[command.index('--mount')+1])
        self.assertNotIn('GHCR_TOKEN',' '.join(command))
        with self.assertRaises(host.DemoError):host.container_command(Path('/tmp/a,b'),'a'*32)

    def test_success_report_is_exact(self):
        self.assertEqual(self.validate(self.report())['status'],'ok')

    def test_report_refuses_changed_binding_or_checks(self):
        for key,value in (('nonce','b'*32),('input_sha256',{}),('source_sha256',{}),
                ('platform_sha256',{}),('excluded_files',[]),('check_flags',[])):
            r=self.report();r[key]=value
            with self.subTest(key=key),self.assertRaises(host.DemoError):self.validate(r)

    def test_report_refuses_extra_duplicate_and_oversized_fields(self):
        r=self.report();r['log']='private'
        with self.assertRaises(host.DemoError):self.validate(r)
        raw=json.dumps(self.report()).encode()
        with self.assertRaises(host.DemoError):
            host.validate_report(b'{"schema":"duplicate",'+raw[1:],'a'*32,{'fixture':'b'*64})
        with self.assertRaises(host.DemoError):host.validate_report(b' '*(host.MAX_REPORT+1),'a'*32,{})

    def test_report_enforces_prefix_and_terminal_results(self):
        for complete in ([],['load'],['create','check'],list(reversed(host.PHASES))):
            r=self.report();r['completed']=complete
            with self.assertRaises(host.DemoError):self.validate(r)
        for n,phase in enumerate(host.PHASES):
            r=self.report();r.update(status='failed',failure='process_failed',phase=phase,
                                    completed=list(host.PHASES[:n]))
            self.assertEqual(self.validate(r)['phase'],phase)
        r=self.report();r.update(status='failed',failure='none')
        with self.assertRaises(host.DemoError):self.validate(r)

    def test_zero_result_requires_exact_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'result'
            for raw in (b'0\n','0'.encode('utf-16')):
                p.write_bytes(raw);host.zero_result(p)
            for raw in (b'',b'1',b'00',b'0\nerror'):
                p.write_bytes(raw)
                with self.assertRaises(host.DemoError):host.zero_result(p)

    def test_admission_requires_owner_exact_sha_and_dispatch(self):
        e,c=self.context();self.assertEqual(policy.admission(e,c),'a'*40)
        for key,value in (('GITHUB_SHA','b'*40),('GITHUB_EVENT_NAME','push'),
                ('GITHUB_ACTOR_ID','1'),('NATIVE_TRIGGERING_ACTOR','other'),
                ('GITHUB_WORKFLOW_REF','wrong')):
            bad=dict(c);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):policy.admission(e,bad)
        bad=copy.deepcopy(e);bad['repository']['fork']=True
        with self.assertRaises(ValueError):policy.admission(bad,c)

    def test_embedded_admission_matches_policy_before_checkout(self):
        workflow=(ROOT/'.github/workflows/native-1c-main-demo-designer.yml').read_text()
        script=(ROOT/'scripts/native_1c_main_demo_ci_policy.py').read_text()
        start='# BEGIN MAIN DEMO ADMISSION';end='# END MAIN DEMO ADMISSION'
        inline=workflow.split(start,1)[1].split(end,1)[0]
        inline='\n'.join(line[10:] if line.startswith(' '*10) else line for line in inline.splitlines())
        self.assertEqual(inline.strip(),script.split(start,1)[1].split(end,1)[0].strip())
        self.assertLess(workflow.index(start),workflow.index('actions/checkout@'))
        self.assertIn('needs: eligibility',workflow)
        self.assertIn('branches: [codex/main-demo-designer-reviewed]',workflow)
        self.assertNotIn('pull_request:',workflow);self.assertNotIn('pull_request_target:',workflow)
        self.assertIn('persist-credentials: false',workflow)
        self.assertEqual(workflow.count("${{ github.event_name == 'workflow_dispatch' && toJSON(inputs) || '{}' }}"), 3)

    def test_bootstrap_private_display_and_bus(self):
        shell=(ROOT/'scripts/native_1c_main_demo_designer.sh').read_text()
        self.assertIn('-rfbport -1 -nolisten tcp',shell)
        self.assertIn('/usr/bin/dbus-run-session -- python3',shell)
        self.assertIn('native_1c_main_demo_designer.py --inside-container',shell)
        self.assertIn('trap ',shell)
        executable = '\n'.join(line for line in shell.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('ENTERPRISE', executable)

    def test_host_cleanup_precedes_report_and_no_payload_export(self):
        source=(ROOT/'scripts/native_1c_main_demo_designer.py').read_text()
        tree=ast.parse(source)
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_host')
        ret=next(n for n in run.body if isinstance(n,ast.Return))
        owned=next(n for n in run.body if isinstance(n,ast.With))
        self.assertGreater(ret.lineno,owned.end_lineno)
        self.assertIn("del report['nonce']",source)
        self.assertIn('lifecycle.run_owned(',source)
        self.assertNotIn('publish_xml_evidence',source)
        self.assertNotIn('/DumpConfigToFiles',source)
        self.assertIn('private_payloads_removed=True',source)

    def test_reviewed_push_is_bound_to_exact_fixed_branch_and_commit(self):
        e,c=self.context()
        c.update(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/codex/main-demo-designer-reviewed',
            GITHUB_WORKFLOW_REF='Atridis/yadinassi/.github/workflows/native-1c-main-demo-designer.yml@refs/heads/codex/main-demo-designer-reviewed',
            NATIVE_DISPATCH_INPUTS='{}')
        e.update(ref=c['GITHUB_REF'],deleted=False,forced=False,after='a'*40,
                 head_commit={'id':'a'*40},inputs={})
        self.assertEqual(policy.admission(e,c),'a'*40)
        for key,value in (('ref','refs/heads/main'),('deleted',True),('forced',True),
                ('after','b'*40),('head_commit',{'id':'b'*40}),('inputs',{'reviewed_sha':'a'*40})):
            bad=copy.deepcopy(e);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):policy.admission(bad,c)
        for key,value in (('GITHUB_ACTOR_ID','1'),('GITHUB_REF','refs/heads/main'),
                ('GITHUB_WORKFLOW_SHA','b'*40),('NATIVE_DISPATCH_INPUTS','null')):
            bad=dict(c);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):policy.admission(e,bad)

    def test_execution_step_supplies_its_own_admission_environment(self):
        workflow = (ROOT/'.github/workflows/native-1c-main-demo-designer.yml').read_text()
        steps = workflow.split('      - name: ')
        execution, = [step for step in steps if '--execute-approved-image' in step]
        env = execution.split('        env:\n', 1)[1].split('        run:', 1)[0]
        self.assertIn('          NATIVE_TRIGGERING_ACTOR: ${{ github.triggering_actor }}', env)
        self.assertIn("          NATIVE_DISPATCH_INPUTS: ${{ github.event_name == 'workflow_dispatch' && toJSON(inputs) || '{}' }}", env)
        self.assertIn('          GHCR_USER: ${{ github.actor }}', env)
        self.assertIn('          GHCR_TOKEN: ${{ github.token }}', env)

    def test_private_diagnostic_exports_only_codes_and_fixed_file_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'load.log'
            p.write_text('Ошибка чтения XML: /private/secret/Documents/Receipt.xml token=secret',encoding='utf-8')
            value=host.diagnostics.classify(p,host.PLATFORM_FILES)
            self.assertEqual(value['codes'],['xml_parse'])
            self.assertEqual(value['file_ids'],[host.PLATFORM_FILES.index('Documents/Receipt.xml')])
            self.assertNotIn('secret',json.dumps(value))
            self.assertTrue(host.diagnostics.valid(value,32))

    def test_private_diagnostic_bounds_and_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'load.log'
            self.assertEqual(host.diagnostics.classify(p,())['reason'],'missing')
            p.write_bytes(b'x'*(host.diagnostics.MAX_BYTES+1))
            self.assertEqual(host.diagnostics.classify(p,())['reason'],'budget')
            p.write_bytes(b'\xff')
            self.assertEqual(host.diagnostics.classify(p,())['reason'],'encoding')
            p.write_bytes('Неизвестное свойство'.encode('utf-16'))
            self.assertEqual(host.diagnostics.classify(p,())['codes'],['unknown_property'])

    def test_diagnostic_validator_rejects_text_unknown_ids_and_false_success(self):
        for change in (dict(codes=['raw error']),dict(file_ids=[32]),dict(file_ids=[True]),
                       dict(reason='private path'),dict(extra='secret')):
            value=dict(state='classified',reason='none',codes=['unclassified'],file_ids=[])
            value.update(change)
            self.assertFalse(host.diagnostics.valid(value,32))
        value=self.report()
        value['diagnostics']=dict(state='classified',reason='none',codes=['unclassified'],file_ids=[])
        with self.assertRaises(host.DemoError):self.validate(value)

    def test_diagnostic_symlink_refused_and_unknown_log_not_exported(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'load.log';p.write_text('private arbitrary diagnostic')
            q=Path(temp)/'alias';q.symlink_to(p)
            self.assertEqual(host.diagnostics.classify(q,())['reason'],'unsafe_file')
            self.assertEqual(host.diagnostics.classify(p,()),
                             dict(state='classified',reason='none',codes=['unclassified'],file_ids=[]))
