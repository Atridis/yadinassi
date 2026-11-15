"""Offline acquisition contracts, not native behavior evidence."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from dom_xpath_behavior import fixture,route
import native_1c_dom_xpath_profile as host
from test_catalog_object_fixture import baseline as catalog_baseline


def baseline():
    # Use the merged owned baseline and its exact bootstrap renderer directly;
    # acquisition must not depend on another unmerged feature packet.
    from native_1c_bootstrap.inject_modules import render_module
    files=catalog_baseline()
    files['Ext/SessionModule.bsl']=render_module(
        ROOT/'scripts/native_1c_bootstrap/modules/SessionModule.bsl',
        'a'*32,'NativeSmoke','/tmp/onec-smoke/stage2-'+'b'*32)
    return files


class DOMXPathNativeAcquisitionTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patch=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patch.start();self.addCleanup(patch.stop)
    def wire(self):
        prefix='DXP|'+'a'*32+'|'
        return (prefix+'entered\n'+''.join(prefix+str(n)+'|"value"\n' for n in range(1,13))+prefix+'completed\n').encode()
    def test_wire_roundtrip(self):
        self.assertEqual(route.parse_wire(self.wire(),'a'*32),['value']*12)
        self.assertEqual(route.partial_values(self.wire().decode().splitlines()[:4],'a'*32),[[1,'value'],[2,'value'],[3,'value']])
        self.assertEqual(route.parse_attempt(self.wire(),'a'*32),([[i,'value'] for i in range(1,13)],[]))
    def test_invalid_nonce_order_and_extra_lines(self):
        for raw,nonce in [(self.wire(),'b'*32),(self.wire().replace(b'|2|',b'|3|'),'a'*32),(self.wire()+b'extra\n','a'*32)]:
            with self.assertRaises(ValueError):route.parse_wire(raw,nonce)
    def test_source_digest_and_parse(self):
        from yadinassi.syntax.parser import parse
        setup,assets=fixture.load_saved()
        self.assertEqual(hashlib.sha256(assets['generated/observe.bsl']).hexdigest(),route.SOURCE_SHA256)
        parse(route.program(setup,'a'*32).decode())
    def test_observer_measures_without_expected_answers(self):
        source=route.source().decode()
        for text in ('EvaluateXPathExpression','DOMNamespaceResolver(D)','DOMNamespaceResolver(N)','DOMNamespaceResolver("p","urn:owned:p")','InvalidIteratorState','/xmlns:root/xmlns:item','SetNamespaceMapping'):
            self.assertIn(text,source)
        self.assertNotIn('Return "True:True:True"',source)
    def test_no_permission_or_session_change(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        for path in before:
            if path!='Configuration.xml':self.assertEqual(after[path],before[path])
        self.assertEqual(after,before)
        self.assertTrue(fixture.verify_prepared(after,dict(after)))
        with self.assertRaises(ValueError):fixture.prepare(before,bootstrap_module=b'changed')
    def test_identity_reaches_shared_lifecycle_boundary(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            cmd=host.container_command(dest,hashes,'onec-dom-xpath-'+'a'*32,'a'*32,host.SMOKE)
            calls=[]
            def stopped(command,env,**kwargs):
                calls.append(command);raise host.DOCKER.CliError('docker_command_unavailable')
            with self.assertRaises(host.DOCKER.LifecycleError):
                host.DOCKER.run_owned(cmd,{},name='onec-dom-xpath-'+'a'*32,nonce='a'*32,
                    image=host.SMOKE.IMAGE,seconds=host.SMOKE.FULL_MAX_RUNTIME,output_limit=host.MAX_TRANSPORT,runner=stopped)
            self.assertTrue(calls);self.assertIn('--read-only',cmd);self.assertEqual(cmd[cmd.index('--network')+1],'none')
    def test_staged_source_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            (dest/'bootstrap/dom_xpath_behavior/observe.bsl').write_bytes(b'changed')
            with self.assertRaises(ValueError):host.validate_inputs(dest,hashes,host.SMOKE)
    def test_observation_bounds(self):
        for value in [None,42,'x'*1025,'\ud800']:
            with self.assertRaises(ValueError):route.canonical([value]*12)
    def test_exact_owner_workflow(self):
        source=(ROOT/'.github/workflows/native-1c-dom-xpath.yml').read_text()
        for text in ["head.ref == 'codex/dom-xpath-workflows'",'persist-credentials: false','packages: read','native_1c_ci_policy.py bind']:
            self.assertIn(text,source)
        self.assertNotIn('pull_request_target',source)
    def test_owned_import_without_redump_or_shared_launcher_mutation(self):
        source=(ROOT/'scripts/native_1c_bootstrap/dom_xpath_suite.py').read_text()
        self.assertIn("designer('load'",source);self.assertIn("designer('update'",source)
        self.assertIn("designer('before'",source)
        self.assertIn("full.require_zero_result(root/(label+'.result'),0)",source)
        designer=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='designer')
        calls=[n for n in ast.walk(designer) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='full']
        run=next(n for n in calls if n.func.attr=='run_process')
        gate=next(n for n in calls if n.func.attr=='require_zero_result')
        quiet=next(n for n in calls if n.func.attr=='native_processes_quiet')
        self.assertLess(run.lineno,gate.lineno)
        self.assertLess(gate.lineno,quiet.lineno)
        self.assertEqual(ast.literal_eval(gate.args[1]),0)
        self.assertNotIn("designer('after'",source);self.assertNotIn("phase='redump'",source)
        tree=ast.parse(source)
        for n in ast.walk(tree):
            if isinstance(n,ast.Assign):
                for target in n.targets:self.assertFalse(isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=='launcher')
    def test_line_endings_and_not_runtime_parity(self):
        lines=(ROOT/'.gitattributes').read_text().splitlines()
        self.assertIn('scripts/dom_xpath_behavior/** text eol=lf',lines)
        self.assertIn("'runtime_parity_accepted':False",(ROOT/'scripts/native_1c_dom_xpath_profile.py').read_text())
    def test_diagnostics_do_not_publish_arbitrary_text(self):
        value=route.install_diagnostic('password=secret\nError hidden-identity','before')
        self.assertTrue(route.valid_install_diagnostic(value));self.assertNotIn('secret',str(value));self.assertNotIn('hidden-identity',str(value))
    def test_exact_resource_pins(self):
        setup,assets=fixture.load_saved()
        self.assertEqual(set(assets),{'generated/observe.bsl'})
        self.assertEqual(fixture.ASSET_HASHES,{})
        self.assertEqual(hashlib.sha256(assets['generated/observe.bsl']).hexdigest(),route.SOURCE_SHA256)
    def test_resources_are_not_generic_grants(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        for name in ('XDTOPackages/Other/Ext/Package.bin','other.txt','other.bin'):
            modified=dict(after);modified[name]=b'payload'
            with self.assertRaises(ValueError):fixture._files(modified)
    def test_resource_drift_rejected(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        changed=dict(after);changed['Configuration.xml']+=b' '
        with self.assertRaises(ValueError):fixture.verify_prepared(after,changed)
    def test_source_layout_contains_only_unchanged_baseline(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        self.assertEqual(after,before)
        self.assertFalse(any(p.startswith(('XDTOPackages/','CommonModules/')) for p in after))
    def test_no_resource_admission_grants(self):
        self.assertEqual(fixture.RESOURCES,{})
        self.assertNotIn('Package.bin',str(host.staged_files()))
    def test_profile_and_count(self):
        self.assertEqual(route.PROFILE,'dom-xpath-observation-v1')
        self.assertEqual(route.COUNT,12)
        self.assertEqual(fixture.VALIDATION_MODE,'owned-dom-xpath-load-update-observation-v1')
        self.assertNotIn('after',route.INSTALL_LABELS)
    def test_non_resource_source_drift_rejected(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        modified=dict(after);modified['Ext/SessionModule.bsl']+=b'\n// changed'
        with self.assertRaises(ValueError):fixture.verify_prepared(after,modified)
    def test_observation_binding_rejects_partial_output(self):
        values=['value']*route.COUNT;raw=route.canonical(values)
        stage={'record_count':route.COUNT,'incomplete':False,'partial_observations':[[i,v] for i,v in enumerate(values,1)]}
        self.assertEqual(host.validate_observation_binding(stage,raw),values)
        stage['partial_observations'].pop()
        with self.assertRaises(ValueError):host.validate_observation_binding(stage,raw)
