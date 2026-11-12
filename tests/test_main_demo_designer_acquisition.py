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
            check_excerpt=host.diagnostics.check_empty(),input_sha256={'fixture':'b'*64},source_sha256=host.SOURCE_SHA256,
            platform_sha256={n:host.SOURCE_SHA256[n] for n in host.PLATFORM_FILES},
            excluded_files=[host.MANIFEST],check_flags=list(host.CHECK_FLAGS),completed=list(host.PHASES),diagnostics=host.diagnostics.empty(),channels=dict(exit_code=0,channels={
                name:dict(state='read',bytes=1,encoding='utf8',lines=['[hidden]'],result='zero')
                for name in host.diagnostics.CHANNELS}))
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

    def test_source_is_canonical_39_and_projection_is_exact_38(self):
        source=host.source_files()
        self.assertEqual(len(source),39)
        original=ast.literal_eval(ast.parse((ROOT/'yadinassi/main_demo_source.py').read_text(encoding='utf-8')).body[1].value)
        self.assertEqual(host.SOURCE_SHA256,original)
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'source';host.stage_source(target,source)
            self.assertEqual(host.dump_files(target),{n:raw for n,raw in source.items() if n!=host.MANIFEST})
            self.assertEqual(len(host.dump_files(target)),38)

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
        command=host.container_command((Path(tempfile.gettempdir()).resolve()/'staged'),'a'*32)
        for flag,value in (('--network','none'),('--user','1000:1000'),('--cap-drop','ALL'),
                ('--security-opt','no-new-privileges:true'),('--pull','never'),('--platform','linux/amd64')):
            self.assertEqual(command[command.index(flag)+1],value)
        self.assertIn('--read-only',command);self.assertIn(host.IMAGE,command)
        self.assertEqual(command.count('--mount'),1)
        self.assertIn('readonly',command[command.index('--mount')+1])
        self.assertNotIn('GHCR_TOKEN',' '.join(command))
        with self.assertRaises(host.DemoError):host.container_command((Path(tempfile.gettempdir()).resolve()/'a,b'),'a'*32)

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
        workflow=(ROOT/'.github/workflows/native-1c-main-demo-designer.yml').read_text(encoding='utf-8')
        script=(ROOT/'scripts/native_1c_main_demo_ci_policy.py').read_text(encoding='utf-8')
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
        shell=(ROOT/'scripts/native_1c_main_demo_designer.sh').read_text(encoding='utf-8')
        self.assertIn('-rfbport -1 -nolisten tcp',shell)
        self.assertIn('/usr/bin/dbus-run-session -- python3',shell)
        self.assertIn('native_1c_main_demo_designer.py --inside-container',shell)
        self.assertIn('trap ',shell)
        executable = '\n'.join(line for line in shell.splitlines() if not line.lstrip().startswith('#'))
        self.assertNotIn('ENTERPRISE', executable)

    def test_host_cleanup_precedes_report_and_no_payload_export(self):
        source=(ROOT/'scripts/native_1c_main_demo_designer.py').read_text(encoding='utf-8')
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
        workflow = (ROOT/'.github/workflows/native-1c-main-demo-designer.yml').read_text(encoding='utf-8')
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
            self.assertTrue(host.diagnostics.valid(value,38))

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
        for change in (dict(codes=['raw error']),dict(file_ids=[38]),dict(file_ids=[True]),
                       dict(reason='private path'),dict(extra='secret')):
            value=dict(state='classified',reason='none',codes=['unclassified'],file_ids=[])
            value.update(change)
            self.assertFalse(host.diagnostics.valid(value,38))
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

    def test_channel_vocabulary_never_copies_unknown_tokens_or_paths(self):
        text='Ошибка загрузки метаданных /private/name/file.xml token=receipt\nUnknown property INTERNALINFO user@example.com\nsecret_123 ABCDEFGH123456789 1234567890'
        lines=host.diagnostics.sanitized_lines(text)
        self.assertEqual(lines[0],'[hidden]')
        self.assertIn('unknown property internalinfo',lines[1])
        for value in ('private','name','example','secret_123','1234567890','ABCDEFG'):
            self.assertNotIn(value,' '.join(lines))

    def test_channel_empty_and_dump_result_are_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'result';p.write_bytes(b'')
            self.assertEqual(host.diagnostics.channel(p)['state'],'empty')
            p.write_bytes(b'1');r=host.diagnostics.channel(p)
            self.assertEqual(r['result'],'nonzero');self.assertEqual(r['bytes'],1)
            p.write_bytes('0'.encode('utf-16'))
            self.assertEqual(host.diagnostics.channel(p)['encoding'],'utf16')
            self.assertEqual(host.diagnostics.channel(p)['result'],'zero')

    def test_channels_validator_rejects_raw_text_and_invalid_exit(self):
        r=self.report()['channels'];self.assertTrue(host.diagnostics.channels_valid(r))
        for code in (True,256,-129,'1'):
            bad=copy.deepcopy(r);bad['exit_code']=code
            self.assertFalse(host.diagnostics.channels_valid(bad))
        for line in ('/private/file','password=secret','unknown secretword','unknown\nproperty'):
            bad=copy.deepcopy(r);bad['channels']['out']['lines']=[line]
            self.assertFalse(host.diagnostics.channels_valid(bad))

    def test_channel_caps_lines_and_bytes_without_export_on_failure(self):
        self.assertLessEqual(len(host.diagnostics.sanitized_lines('error\n'*100)),3)
        self.assertTrue(all(len(x)<=240 for x in host.diagnostics.sanitized_lines('error '*1000)))
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'out';p.write_bytes(b'x'*(host.diagnostics.MAX_BYTES+1))
            r=host.diagnostics.channel(p)
            self.assertEqual(r['state'],'budget');self.assertEqual(r['lines'],[])

    def test_check_excerpt_preserves_readable_module_and_location(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'check.log'
            p.write_text('{ОбщаяФорма.OperationDraft.Форма.Модуль(12,7)}: Переменная не определена (PendingDraft)\n/tmp/private/source/CommonForms/DraftDetails/Ext/Form.xml',encoding='utf-8')
            value=host.diagnostics.check_excerpt(p,host.PLATFORM_FILES)
            self.assertEqual(value['state'],'read')
            self.assertIn('(12,7)',value['lines'][0]);self.assertIn('PendingDraft',value['lines'][0])
            self.assertEqual(value['lines'][1],'[source:15]')
            self.assertTrue(host.diagnostics.check_valid(value,host.PLATFORM_FILES))

    def test_check_excerpt_redacts_paths_and_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'check.log';p.write_text('password=some private value\nC:\\private\\file.txt error\nhttps://private.example/secret',encoding='utf-8')
            value=host.diagnostics.check_excerpt(p,host.PLATFORM_FILES)
            self.assertEqual(value['state'],'read')
            self.assertNotIn('private',str(value));self.assertNotIn('some',str(value))
            self.assertTrue(host.diagnostics.check_valid(value,host.PLATFORM_FILES))

    def test_check_excerpt_fails_closed_for_unsafe_or_oversized_content(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'check.log'
            for raw in (b'x'*16385,b'bad\x00control',b'\xff',b'ghp_abcdefghijklmnopqrstuvwxyz1234567890'):
                p.write_bytes(raw);value=host.diagnostics.check_excerpt(p,host.PLATFORM_FILES)
                self.assertEqual(value['state'],'unavailable');self.assertEqual(value['lines'],[])
            p.unlink();p.symlink_to(Path(temp)/'missing')
            self.assertEqual(host.diagnostics.check_excerpt(p,host.PLATFORM_FILES)['reason'],'unsafe_file')

    def test_check_excerpt_host_refuses_raw_paths_and_wrong_phase(self):
        r=self.report();r['check_excerpt']=dict(state='read',reason='none',lines=['/private/file'])
        with self.assertRaises(host.DemoError):self.validate(r)
        r=self.report();r.update(status='failed',phase='load',failure='process_failed',completed=['create'])
        r['check_excerpt']=dict(state='read',reason='none',lines=['Public diagnostic'])
        with self.assertRaises(host.DemoError):self.validate(r)

    def test_check_excerpt_truncates_only_after_scanning_all_input(self):
        d=host.diagnostics
        lines=d._check_text('line\n'*40,host.PLATFORM_FILES)
        self.assertEqual(len(lines),32)
        self.assertEqual(lines[-1],'[diagnostic truncated]')
        self.assertTrue(d.check_valid(dict(state='read',reason='none',lines=lines),host.PLATFORM_FILES))
        with self.assertRaises(ValueError):
            d._check_text('line\n'*40+'ghp_abcdefghijklmnopqrstuvwxyz1234567890',host.PLATFORM_FILES)
