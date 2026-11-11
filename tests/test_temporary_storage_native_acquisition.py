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
from temporary_storage_behavior import fixture,route
import native_1c_temporary_storage_profile as host
from test_session_parameter_native_acquisition import baseline

class TemporaryStorageNativeAcquisitionTests(unittest.TestCase):
    def setUp(self):
        if os.name=='nt':
            from test_native_1c_full_host import read_synthetic_file
            patch=mock.patch.object(host.FULL,'read_regular',side_effect=read_synthetic_file)
            patch.start();self.addCleanup(patch.stop)
    def wire(self):
        prefix='TMP|'+'a'*32+'|'
        return (prefix+'entered\n'+''.join(prefix+str(n)+'|"value"\n' for n in range(1,17))+prefix+'completed\n').encode()
    def test_wire_roundtrip(self):
        self.assertEqual(route.parse_wire(self.wire(),'a'*32),['value']*16)
        self.assertEqual(route.parse_attempt(self.wire(),'a'*32),([[i,'value'] for i in range(1,17)],[]))
    def test_invalid_nonce_order_and_extra_lines(self):
        for raw,nonce in [(self.wire(),'b'*32),(self.wire().replace(b'|2|',b'|3|'),'a'*32),(self.wire()+b'extra\n','a'*32)]:
            with self.assertRaises(ValueError):route.parse_wire(raw,nonce)
    def test_source_digest_and_parse(self):
        from yadinassi.syntax.parser import parse
        setup,assets=fixture.load_saved()
        self.assertEqual(hashlib.sha256(assets['generated/observe.bsl']).hexdigest(),route.SOURCE_SHA256)
        parse(route.program(setup,'a'*32).decode())
    def test_generated_addresses_do_not_leave_observer(self):
        source=route.source().decode()
        self.assertNotIn('Return Address;',source)
        self.assertIn('Address=Replaced',source)
        self.assertIn('IsTempStorageURL(Address)',source)
    def test_no_schema_or_permission_change(self):
        before=baseline();_,after=fixture.prepare(before,bootstrap_module=before['Ext/SessionModule.bsl'])
        self.assertEqual(before,after);self.assertTrue(fixture.verify_redump(before,after))
        with self.assertRaises(ValueError):fixture.prepare(before,bootstrap_module=b'changed')
    def test_identity_reaches_shared_lifecycle_boundary(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            cmd=host.container_command(dest,hashes,'onec-temporary-storage-'+'a'*32,'a'*32,host.SMOKE)
            calls=[]
            def stopped(command,env,**kwargs):
                calls.append(command);raise host.DOCKER.CliError('docker_command_unavailable')
            with self.assertRaises(host.DOCKER.LifecycleError):
                host.DOCKER.run_owned(cmd,{},name='onec-temporary-storage-'+'a'*32,nonce='a'*32,
                    image=host.SMOKE.IMAGE,seconds=host.SMOKE.FULL_MAX_RUNTIME,output_limit=host.MAX_TRANSPORT,runner=stopped)
            self.assertTrue(calls);self.assertIn('--read-only',cmd);self.assertEqual(cmd[cmd.index('--network')+1],'none')
    def test_staged_source_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as directory:
            dest=Path(directory)/'inputs';hashes=host.stage_inputs(ROOT,dest,host.SMOKE)
            (dest/'bootstrap/temporary_storage_behavior/observe.bsl').write_bytes(b'changed')
            with self.assertRaises(ValueError):host.validate_inputs(dest,hashes,host.SMOKE)
    def test_observation_bounds(self):
        for value in [None,42,'x'*1025,'\ud800']:
            with self.assertRaises(ValueError):route.canonical([value]*16)
    def test_exact_owner_workflow(self):
        source=(ROOT/'.github/workflows/native-1c-temporary-storage.yml').read_text()
        for text in ["head.ref == 'codex/application-temporary-storage'",'persist-credentials: false','packages: read','native_1c_ci_policy.py bind']:
            self.assertIn(text,source)
        self.assertNotIn('pull_request_target',source)
    def test_no_xml_reimport_or_shared_launcher_mutation(self):
        source=(ROOT/'scripts/native_1c_bootstrap/temporary_storage_suite.py').read_text()
        self.assertNotIn("designer('load'",source);self.assertNotIn("designer('update'",source)
        tree=ast.parse(source)
        for n in ast.walk(tree):
            if isinstance(n,ast.Assign):
                for target in n.targets:self.assertFalse(isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=='launcher')
    def test_line_endings_and_not_runtime_parity(self):
        lines=(ROOT/'.gitattributes').read_text().splitlines()
        self.assertIn('scripts/temporary_storage_behavior/** text eol=lf',lines)
        self.assertIn("'runtime_parity_accepted':False",(ROOT/'scripts/native_1c_temporary_storage_profile.py').read_text())
    def test_diagnostics_do_not_publish_arbitrary_text(self):
        value=route.install_diagnostic('password=secret\nError hidden-identity','before')
        self.assertTrue(route.valid_install_diagnostic(value));self.assertNotIn('secret',str(value));self.assertNotIn('hidden-identity',str(value))
