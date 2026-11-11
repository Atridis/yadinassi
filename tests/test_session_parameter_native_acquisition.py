"""Offline source/transport/isolation contracts, not real native evidence."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from session_parameter_behavior import fixture,route
import native_1c_session_parameter_profile as host
from test_catalog_object_fixture import baseline as catalog_baseline

def baseline():
    from native_1c_bootstrap.inject_modules import render_module
    files=catalog_baseline()
    files['Ext/SessionModule.bsl']=render_module(ROOT/'scripts/native_1c_bootstrap/modules/SessionModule.bsl','a'*32,'NativeSmoke','/tmp/onec-smoke/stage2-'+'b'*32)
    return files

def prepare(files):
    return fixture.prepare(files,bootstrap_module=baseline()['Ext/SessionModule.bsl'])

class SessionParameterNativeAcquisitionTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patch=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patch.start();self.addCleanup(patch.stop)

    def wire(self,values=None):
        values=['']*16 if values is None else values;p='SES|'+'a'*32+'|'
        return (p+'entered\n'+''.join(p+str(n)+'|'+json.dumps(v,ensure_ascii=False)+'\n' for n,v in enumerate(values,1))+p+'completed\n').encode()

    def test_empty_and_unicode_roundtrip(self):
        values=['','Да','Параметр сеанса: OwnedLazy','a|b\nc']*4
        self.assertEqual(route.parse_wire(self.wire(values),'a'*32),values)
        self.assertEqual(route.parse_attempt(self.wire(values),'a'*32),([[i,v] for i,v in enumerate(values,1)],[]))
        self.assertEqual(json.loads(route.canonical(values)),values)

    def test_wrong_nonce_and_order_rejected(self):
        for raw,nonce in ((self.wire(),'b'*32),(self.wire().replace(b'|2|',b'|3|'),'a'*32)):
            with self.assertRaises(ValueError):route.parse_wire(raw,nonce)

    def test_unbounded_nonstring_and_surrogate_rejected(self):
        for value in ('x'*1025,4,None,'\ud800'):
            with self.assertRaises(ValueError):route.canonical([value]*16)

    def test_injected_line_rejected(self):
        with self.assertRaises(ValueError):route.parse_wire(self.wire()+b'extra\n','a'*32)

    def test_exact_source_and_parse(self):
        setup,assets=fixture.load_saved();self.assertEqual(assets['generated/observe.bsl'],route.source())
        self.assertEqual(hashlib.sha256(route.source()).hexdigest(),route.SOURCE_SHA256)
        from yadinassi.syntax.parser import parse
        parse(route.program(setup,'a'*32).decode())

    def test_program_no_expected_answers(self):
        program=route.program(None,'a'*32)
        self.assertIn(b'WriteJSON(Writer,V)',program)
        self.assertLess(program.index(b'Function ObserveCase'),program.index(b'|entered'))
        self.assertIn(b'SessionParameters.OwnedStartup',program);self.assertIn(b'OwnedFailure',program)

    def test_fixture_adds_only_owned_parameters_and_get_set(self):
        before=baseline();_,after=prepare(before)
        self.assertEqual(set(after)-set(before),{'SessionParameters/'+n+'.xml' for n in fixture.PARAMETERS})
        rn='{'+fixture.original.RIGHTS+'}'
        rights=ET.fromstring(after[fixture.original.ROLE_FILES[1]])
        added=[o for o in rights.findall(rn+'object') if o.find(rn+'name').text.startswith('SessionParameter.')]
        self.assertEqual(len(added),len(fixture.PARAMETERS))
        for obj in added:
            self.assertEqual({r.find(rn+'name').text for r in obj.findall(rn+'right')},{'Get','Set'})
            self.assertTrue(all(r.find(rn+'value').text=='true' for r in obj.findall(rn+'right')))
        self.assertEqual(after[fixture.original.ROLE_FILES[0]],before[fixture.original.ROLE_FILES[0]])
        with self.assertRaises(ValueError):fixture.prepare(before)
        self.assertNotEqual(after['Ext/SessionModule.bsl'],before['Ext/SessionModule.bsl'])
        self.assertIn(b'<SessionParameter>OwnedLazy</SessionParameter>',after['Configuration.xml'])

    def test_material_projection_rejects_type_drift(self):
        _,files=prepare(baseline());actual=dict(files);name='SessionParameters/OwnedBoolean.xml'
        actual[name]=files[name].replace(b'xs:boolean',b'xs:string')
        with self.assertRaises(ValueError):fixture.verify_redump(files,actual)

    def test_material_projection_rejects_module_drift(self):
        _,files=prepare(baseline());actual=dict(files);name='Ext/SessionModule.bsl'
        actual[name]=files[name].replace(b'OwnedWitness = 42',b'OwnedWitness = 43')
        with self.assertRaises(ValueError):fixture.verify_redump(files,actual)

    def test_material_projection_tolerates_line_endings(self):
        _,files=prepare(baseline());actual=dict(files);name='Ext/SessionModule.bsl'
        actual[name]=files[name].replace(b'\n',b'\r\n')
        self.assertTrue(fixture.verify_redump(files,actual))

    def test_unknown_executable_file_rejected(self):
        _,files=prepare(baseline());actual=dict(files);actual['SessionParameters/OwnedLazy/Ext/ManagerModule.bsl']=b'Message("x");'
        with self.assertRaises(ValueError):fixture.verify_redump(files,actual)

    def test_staged_inventory_and_container_scope(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            host.validate_inputs(dest,hashes,host.SMOKE)
            cmd=host.container_command(dest,hashes,'onec-session-parameter-'+'a'*32,'a'*32,host.SMOKE)
            self.assertIn('--session_parameter-suite',cmd);self.assertIn('--read-only',cmd)
            self.assertEqual(cmd[cmd.index('--network')+1],'none')
            self.assertNotIn('--accumulation-register-suite',cmd)
            # Exercise the real shared validation boundary without Docker I/O.
            calls=[]
            def stopped(command, env, **kwargs):
                calls.append(command)
                raise host.DOCKER.CliError('docker_command_unavailable')
            with self.assertRaises(host.DOCKER.LifecycleError) as error:
                host.DOCKER.run_owned(cmd,{},name='onec-session-parameter-'+'a'*32,
                    nonce='a'*32,image=host.SMOKE.IMAGE,seconds=host.SMOKE.FULL_MAX_RUNTIME,
                    output_limit=host.MAX_TRANSPORT,runner=stopped)
            self.assertTrue(calls, 'valid identity must reach image inspection')
            self.assertNotIn('docker_lifecycle_invalid',str(error.exception))


    def test_changed_staged_source_denied(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            (dest/'bootstrap/session_parameter_behavior/OwnedLazy.xml').write_bytes(b'changed')
            with self.assertRaises(ValueError):host.validate_inputs(dest,hashes,host.SMOKE)

    def test_workflow_owner_branch_and_credentials_closed(self):
        text=(ROOT/'.github/workflows/native-1c-session-parameters.yml').read_text()
        for part in ("head.ref == 'codex/session-parameters'",'persist-credentials: false','native_1c_ci_policy.py bind','packages: read'):
            self.assertIn(part,text)
        self.assertNotIn('pull_request_target',text)

    def test_no_shared_launcher_monkeypatch(self):
        path=ROOT/'scripts/native_1c_bootstrap/session_parameter_suite.py';text=path.read_text();tree=ast.parse(text)
        for n in ast.walk(tree):
            if isinstance(n,ast.Assign):
                for t in n.targets:
                    self.assertFalse(isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name) and t.value.id=='launcher')
        self.assertIn('def run_owned_case(',text);self.assertNotIn('FunctionType',text)

    def test_source_hash_inputs_have_lf_pins(self):
        lines=(ROOT/'.gitattributes').read_text().splitlines()
        for name in ('scripts/session_parameter_behavior/**','scripts/native_1c_bootstrap/session_parameter_suite.py','scripts/native_1c_session_parameter_probe.sh'):
            self.assertIn(name+' text eol=lf',lines)

    def test_diagnostics_do_not_export_arbitrary_text(self):
        value=route.install_diagnostic('password=secret\nBroken OwnedLazy private-token-19282','load')
        self.assertTrue(route.valid_install_diagnostic(value));self.assertNotIn('secret',str(value));self.assertNotIn('private-token',str(value))
        diagnostic=route.install_diagnostic('Имя не соответствует имени файла; SessionParameter Get; secret=hidden','load')
        self.assertNotIn('hidden',str(diagnostic))
        diagnostic=route.install_diagnostic('Имя не соответствует имени файла; SessionParameter Get','load')
        self.assertIn('match',diagnostic['tokens']);self.assertIn('owned:Get',diagnostic['tokens'])
        self.assertTrue(route.valid_install_diagnostic(diagnostic))

    def test_native_only_not_runtime_parity(self):
        text=(ROOT/'scripts/native_1c_session_parameter_profile.py').read_text()
        self.assertIn("'runtime_parity_accepted':False",text);self.assertIn('comparison=None',text)

    def adapter(self):
        import importlib.util
        sys.path.insert(0,str(ROOT/'scripts/native_1c_bootstrap'))
        spec=importlib.util.spec_from_file_location('session_suite_test',ROOT/'scripts/native_1c_bootstrap/session_parameter_suite.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            # Test-only stable fixture reader. Linux retains real no-follow guards.
            patch=mock.patch.object(module.full,'secure_bytes',side_effect=lambda path,limit,allow_empty=False:read_synthetic_file(path,limit,nonempty=not allow_empty))
            patch.start();self.addCleanup(patch.stop)
        return module

    def test_explicit_adapter_uses_guarded_processes_without_shared_mutation(self):
        import types
        suite=self.adapter()
        launcher=types.SimpleNamespace(TEMPLATES=ROOT/'integrational_tests/launcher_1c',read_result=object(),run_process=object(),build_epf=object())
        before=dict(vars(launcher))
        platform=types.SimpleNamespace(timeout=120,command=lambda mode:['/owned/1cv8',mode])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'probe.bsl';source.write_bytes(route.program(None,'a'*32))
            expected=suite.full.generated_module(source.read_bytes());case=root/'case';output=root/'wire'
            with mock.patch.object(suite.full,'run_process') as process, mock.patch.object(suite.full,'require_zero_result') as result, mock.patch.object(suite.full,'require_epf') as epf, mock.patch.object(suite.full,'validate_case_request') as request, mock.patch.object(suite.full,'read_native_result',return_value=(['ok'],'')):
                suite.run_owned_case(launcher,platform,source,root/'Launcher.epf',case,output,expected)
            self.assertEqual(output.read_bytes(),b'ok\n');self.assertEqual(vars(launcher),before)
            self.assertEqual(process.call_count,2)
            self.assertTrue(all(c.kwargs['require_clean_tree'] for c in process.call_args_list))
            result.assert_called_once();epf.assert_called_once();request.assert_called_once()
            self.assertEqual((case/'src/TestModule/Ext/ObjectModule.bsl').read_bytes(),expected)

    def test_adapter_source_mismatch_precedes_process(self):
        import types
        suite=self.adapter();launcher=types.SimpleNamespace(TEMPLATES=ROOT/'integrational_tests/launcher_1c')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'probe.bsl';source.write_bytes(b'Message("wrong");')
            with mock.patch.object(suite.full,'run_process') as process, self.assertRaises(suite.full.FullError):
                suite.run_owned_case(launcher,None,source,None,root/'case',root/'wire',b'expected')
            process.assert_not_called()

    def test_partial_case_failure_is_not_empty_success(self):
        prefix='SES|'+'a'*32+'|'
        raw=(prefix+'entered\n'+prefix+'error|1|read|"private native detail"\n'+prefix+'2|""\n'+prefix+'completed\n').encode()
        values,errors=route.parse_attempt(raw,'a'*32)
        self.assertEqual(values,[[2,'']]);self.assertEqual(errors,[(1,'read','private native detail')])
        with self.assertRaises(ValueError):route.parse_wire(raw,'a'*32)

    def test_session_module_has_only_nonexported_declarations(self):
        source=(ROOT/'scripts/session_parameter_behavior/SessionModule.bsl').read_text()
        from yadinassi.syntax.parser import parse
        parse(source)
        self.assertNotIn(' Export',source);self.assertNotIn('Var ',source)
        self.assertIn('Procedure SessionParametersSetting(RequiredParameters)',source)
        self.assertIn('RequiredParameters = Undefined',source)
        self.assertIn('For Each ParameterName In RequiredParameters',source)
        self.assertIn('Raise "owned-session-failure"',source)

    def test_existing_nonempty_session_module_is_not_overwritten(self):
        files=baseline();files['Ext/SessionModule.bsl']=b'Procedure Existing()\nEndProcedure\n'
        with self.assertRaises(ValueError):prepare(files)

    def test_session_qualification_and_startup_sources_pinned(self):
        _,assets=fixture.load_saved()
        self.assertIn(b'<v8:Length>5</v8:Length>',assets['OwnedString.xml'])
        self.assertIn(b'<v8:FractionDigits>2</v8:FractionDigits>',assets['OwnedNumber.xml'])
        self.assertIn(b'SessionParameters.OwnedStartup = 1',assets['SessionModule.bsl'])
        source=(ROOT/'scripts/native_1c_bootstrap/session_parameter_suite.py').read_text()
        self.assertNotIn('xwininfo',source);self.assertNotIn('xprop',source)
        suite=self.adapter()
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);stage=base/('stage2-'+'b'*32)
            target=stage/'injected/Ext/SessionModule.bsl';target.parent.mkdir(parents=True)
            expected=suite.inject_modules.render_module(ROOT/'scripts/native_1c_bootstrap/modules/SessionModule.bsl','a'*32,'NativeSmoke',str(stage))
            target.write_bytes(expected)
            (stage/'verify-session.json').write_text(json.dumps({'run_id':'a'*32}))
            with mock.patch.object(suite.run_stage,'ROOT',base), mock.patch.object(suite.evidence_gates,'require_marker_pair') as gate:
                self.assertEqual(suite.bootstrap_session_source(stage/'Launcher.epf'),expected)
                self.assertEqual(gate.call_count,2)
                self.assertEqual([c.args[1] for c in gate.call_args_list],['bootstrap','verify'])
                target.write_bytes(expected+b'// drift\n')
                with self.assertRaises(suite.full.FullError):suite.bootstrap_session_source(stage/'Launcher.epf')
                target.write_bytes(expected)
                (stage/'control.json').write_text('{}')
                with self.assertRaises(suite.full.FullError):suite.bootstrap_session_source(stage/'Launcher.epf')
