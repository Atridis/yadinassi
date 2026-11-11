"""Offline source/transport/isolation contracts, not real native evidence."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from enumeration_behavior import fixture,route
import native_1c_enumeration_profile as host
from test_catalog_object_fixture import baseline

class EnumerationNativeAcquisitionTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patch=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patch.start();self.addCleanup(patch.stop)

    def wire(self,values=None):
        values=['']*16 if values is None else values;p='ENU|'+'a'*32+'|'
        return (p+'entered\n'+''.join(p+str(n)+'|'+json.dumps(v,ensure_ascii=False)+'\n' for n,v in enumerate(values,1))+p+'completed\n').encode()

    def test_empty_and_unicode_roundtrip(self):
        values=['','Да','Перечисление менеджер: OwnedStatus','a|b\nc']*4
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
        self.assertIn(b'FullName()',program);self.assertIn(b'String(Manager)',program)

    def test_fixture_adds_only_enum_and_preserves_baseline_rights(self):
        before=baseline();_,after=fixture.prepare(before)
        self.assertEqual(set(after)-set(before),{'Enums/OwnedStatus.xml'})
        md='{'+fixture.original.MD+'}'
        properties=ET.fromstring(after['Enums/OwnedStatus.xml']).find(md+'Enum/'+md+'Properties')
        names=[node.tag for node in properties]
        index=names.index(md+'StandardAttributes')
        self.assertEqual(names[index-1:index+2],[md+'UseStandardCommands',md+'StandardAttributes',md+'Characteristics'])
        self.assertEqual(len(properties[index]),0)
        self.assertIn(b'<Enum>OwnedStatus</Enum>',after['Configuration.xml'])
        for path in fixture.original.ROLE_FILES:
            self.assertEqual(after[path],before[path])
        self.assertNotIn(b'Enum.OwnedStatus',after[fixture.original.ROLE_FILES[1]])

    def test_material_projection_keeps_value_order(self):
        _,files=fixture.prepare(baseline());name='Enums/OwnedStatus.xml';actual=dict(files)
        root=ET.fromstring(files[name]);md='{'+fixture.original.MD+'}';children=root.find(md+'Enum/'+md+'ChildObjects')
        children[:]=list(reversed(list(children)));actual[name]=ET.tostring(root)
        with self.assertRaises(ValueError):fixture.verify_redump(files,actual)

    def test_material_projection_rejects_synonym_drift(self):
        _,files=fixture.prepare(baseline());actual=dict(files);name='Enums/OwnedStatus.xml'
        actual[name]=files[name].replace(b'Active item',b'Changed item')
        with self.assertRaises(ValueError):fixture.verify_redump(files,actual)

    def test_material_projection_tolerates_designer_ui_defaults(self):
        _,files=fixture.prepare(baseline());actual=dict(files);name='Enums/OwnedStatus.xml'
        actual[name]=files[name].replace(b'<Characteristics/>',b'<Characteristics/><IncludeHelpInContents>false</IncludeHelpInContents>')
        self.assertTrue(fixture.verify_redump(files,actual))

    def test_unknown_executable_file_rejected(self):
        _,files=fixture.prepare(baseline());actual=dict(files);actual['Enums/OwnedStatus/Ext/ManagerModule.bsl']=b'Message("x");'
        with self.assertRaises(ValueError):fixture.verify_redump(files,actual)

    def test_staged_inventory_and_container_scope(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            host.validate_inputs(dest,hashes,host.SMOKE)
            cmd=host.container_command(dest,hashes,'onec-enumeration-'+'a'*32,'a'*32,host.SMOKE)
            self.assertIn('--enumeration-suite',cmd);self.assertIn('--read-only',cmd)
            self.assertEqual(cmd[cmd.index('--network')+1],'none')
            self.assertNotIn('--accumulation-register-suite',cmd)

    def test_changed_staged_source_denied(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            (dest/'bootstrap/enumeration_behavior/Enum.xml').write_bytes(b'changed')
            with self.assertRaises(ValueError):host.validate_inputs(dest,hashes,host.SMOKE)

    def test_workflow_owner_branch_and_credentials_closed(self):
        text=(ROOT/'.github/workflows/native-1c-enumeration.yml').read_text()
        for part in ("head.ref == 'codex/configuration-enumerations'",'persist-credentials: false','native_1c_ci_policy.py bind','packages: read'):
            self.assertIn(part,text)
        self.assertNotIn('pull_request_target',text)

    def test_no_shared_launcher_monkeypatch(self):
        path=ROOT/'scripts/native_1c_bootstrap/enumeration_suite.py';text=path.read_text();tree=ast.parse(text)
        for n in ast.walk(tree):
            if isinstance(n,ast.Assign):
                for t in n.targets:
                    self.assertFalse(isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name) and t.value.id=='launcher')
        self.assertIn('def run_owned_case(',text);self.assertNotIn('FunctionType',text)

    def test_source_hash_inputs_have_lf_pins(self):
        lines=(ROOT/'.gitattributes').read_text().splitlines()
        for name in ('scripts/enumeration_behavior/**','scripts/native_1c_bootstrap/enumeration_suite.py','scripts/native_1c_enumeration_probe.sh'):
            self.assertIn(name+' text eol=lf',lines)
        self.assertIn('tests/fixtures/native_enumeration_43035110558.json -text',lines)

    def test_diagnostics_do_not_export_arbitrary_text(self):
        value=route.install_diagnostic('password=secret\nBroken OwnedStatus private-token-19282','load')
        self.assertTrue(route.valid_install_diagnostic(value));self.assertNotIn('secret',str(value));self.assertNotIn('private-token',str(value))
        diagnostic=route.install_diagnostic('Имя не соответствует имени файла; ChoiceMode BothWays; secret=hidden','load')
        self.assertNotIn('hidden',str(diagnostic))
        diagnostic=route.install_diagnostic('Имя не соответствует имени файла; ChoiceMode BothWays','load')
        self.assertIn('match',diagnostic['tokens']);self.assertIn('owned:ChoiceMode',diagnostic['tokens'])
        self.assertTrue(route.valid_install_diagnostic(diagnostic))

    def test_native_only_not_runtime_parity(self):
        text=(ROOT/'scripts/native_1c_enumeration_profile.py').read_text()
        self.assertIn("'runtime_parity_accepted':False",text);self.assertIn('comparison=None',text)

    def adapter(self):
        import importlib.util
        sys.path.insert(0,str(ROOT/'scripts/native_1c_bootstrap'))
        spec=importlib.util.spec_from_file_location('enum_suite_test',ROOT/'scripts/native_1c_bootstrap/enumeration_suite.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_explicit_adapter_uses_guarded_processes_without_shared_mutation(self):
        import types
        suite=self.adapter()
        launcher=types.SimpleNamespace(TEMPLATES=ROOT/'integrational_tests/launcher_1c',read_result=object(),run_process=object(),build_epf=object())
        before=dict(vars(launcher))
        platform=types.SimpleNamespace(timeout=120,command=lambda mode:['/owned/1cv8',mode])
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory).resolve();source=root/'probe.bsl';source.write_bytes(route.program(None,'a'*32))
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
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            root=Path(directory).resolve();source=root/'probe.bsl';source.write_bytes(b'Message("wrong");')
            with mock.patch.object(suite.full,'run_process') as process, self.assertRaises(suite.full.FullError):
                suite.run_owned_case(launcher,None,source,None,root/'case',root/'wire',b'expected')
            process.assert_not_called()

    def test_partial_case_failure_is_not_empty_success(self):
        prefix='ENU|'+'a'*32+'|'
        raw=(prefix+'entered\n'+prefix+'error|1|read|"private native detail"\n'+prefix+'2|""\n'+prefix+'completed\n').encode()
        values,errors=route.parse_attempt(raw,'a'*32)
        self.assertEqual(values,[[2,'']]);self.assertEqual(errors,[(1,'read','private native detail')])
        with self.assertRaises(ValueError):route.parse_wire(raw,'a'*32)

    def test_timeout_witness_is_finite_and_bounded(self):
        suite=self.adapter()
        tree='\n'.join('  0x%x "private title"' % i for i in range(1,30))
        properties='_NET_WM_STATE_MODAL _NET_WM_WINDOW_TYPE_DIALOG WM_NAME="error private password"'
        with mock.patch.object(suite.shutil,'which',side_effect=lambda n:'/usr/bin/'+n), mock.patch.object(suite,'_xread',side_effect=[tree]+[properties]*8):
            witness=suite.timeout_witness(Path('.'))
        self.assertEqual(witness,dict(available=True,windows=8,dialogs=8,modals=8,categories=['error']))
        self.assertNotIn('private',str(witness))

    def test_timeout_witness_unavailable_is_not_success(self):
        suite=self.adapter()
        source=(ROOT/'scripts/native_1c_bootstrap/enumeration_suite.py').read_text()
        self.assertLess(source.index("if not shutil.which('xwininfo')"),source.index("designer('load'"))
        self.assertIn("raise full.FullError('unsupported_observation')",source)
        with mock.patch.object(suite.shutil,'which',return_value=None):
            self.assertEqual(suite.timeout_witness(Path('.')),dict(available=False,windows=0,dialogs=0,modals=0,categories=[]))

    def test_designer_timeout_observes_before_guaranteed_cleanup(self):
        suite=self.adapter();events=[];child=mock.MagicMock()
        child.wait.side_effect=suite.subprocess.TimeoutExpired('private command',120)
        process=mock.MagicMock();process.__enter__.return_value=child
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory, mock.patch.object(suite,'os',SimpleNamespace(name='posix')), mock.patch.object(suite.subprocess,'Popen',return_value=process), mock.patch.object(suite,'timeout_witness',side_effect=lambda p:events.append('witness') or {}), mock.patch.object(suite.full,'_stop_group',side_effect=lambda p:events.append('stop')):
            with self.assertRaises(suite.full.FullError) as error:
                suite.run_designer_process(['owned','DESIGNER'],Path(directory),Path(directory)/'out',120,report={})
        self.assertEqual(error.exception.kind,'timeout');self.assertEqual(events,['witness','stop'])
