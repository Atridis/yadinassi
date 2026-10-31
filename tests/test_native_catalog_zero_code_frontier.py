"""Bounded zero-only dispatch frontier probes, not native behavior evidence."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import test_native_catalog_zero_code_bootstrap as base
import test_native_catalog_zero_code_policy as facts
import test_native_1c_db_oracle_metadata as metadata
import catalog_zero_code_measurement as measurement
import catalog_zero_code_policy as policy
import protocol


def marker(point,status=None,phase=None):
    return dict(schema=1,nonce=facts.NONCE,token='b'*32,point=point,
        status=status or ('returned' if point=='client_after_call' else 'ok' if point=='server_return' else 'entered'),
        phase=phase or ('complete' if point=='server_return' else 'dispatch'))


class FrontierProjectionTests(unittest.TestCase):
    def test_all_fixed_outcomes(self):
        for point in measurement.FRONTIER_POINTS:
            d=marker(point);result=policy.frontier_marker(protocol.encode(d),nonce=d['nonce'],token=d['token'],point=point)
            self.assertEqual(result,dict(state='valid',status=d['status'],phase=d['phase']))
        for phase in policy.BOOTSTRAP_FRONTIER_PHASES:
            d=marker('server_return','error',phase)
            self.assertEqual(policy.frontier_marker(protocol.encode(d),nonce=d['nonce'],token=d['token'],point=d['point'])['phase'],phase)
        for point in measurement.FRONTIER_POINTS:
            for state in ('absent','invalid'):policy.validate_frontier_projection(dict(state=state,status=None,phase=None),point)
    def test_wrong_fields_types_controls_and_phase(self):
        for point in measurement.FRONTIER_POINTS:
            good=marker(point)
            for key,val in [('schema',True),('schema',1.0),('nonce','f'*32),('token','f'*32),('point','other'),('status','PRIVATE'),('phase','PRIVATE'),('raw','PRIVATE')]:
                d={**good,key:val}
                with self.subTest(point=point,key=key),self.assertRaises(protocol.OracleError):policy.frontier_marker(protocol.encode(d),nonce=good['nonce'],token=good['token'],point=point)
        for d in [dict(state='invalid',status='error',phase=None),dict(state='valid',status='ok',phase='metadata'),dict(state='valid',status='error',phase='complete'),dict(state='valid',status='error',phase='write')]:
            with self.assertRaises(protocol.OracleError):policy.validate_frontier_projection(d,'server_return')
    def test_hostile_frontier_key_guard_precedes_membership(self):
        class Key:
            def __hash__(self):return hash('frontier')
            def __eq__(self,other):raise AssertionError('membership hook')
        d=facts.bootstrap_diagnostic();d[Key()]=None
        with self.assertRaises(protocol.OracleError):policy.validate_bootstrap_failure(d)
        self.assertFalse(policy.set_bootstrap_failure(facts.bootstrap_failure(),d,final=True))
    def test_optional_closed_frontier_failed_report(self):
        d=facts.bootstrap_diagnostic();d['frontier']={point:dict(state='absent',status=None,phase=None)for point in measurement.FRONTIER_POINTS}
        report=facts.bootstrap_failure();self.assertTrue(policy.set_bootstrap_failure(report,d,final=True));facts.validate(report)
        for key in measurement.FRONTIER_POINTS:
            bad=copy.deepcopy(d);del bad['frontier'][key]
            self.assertFalse(policy.set_bootstrap_failure(facts.bootstrap_failure(),bad,final=True))
        for value in (None,[],{'raw':'PRIVATE'}):
            self.assertFalse(policy.set_bootstrap_failure(facts.bootstrap_failure(),{**d,'frontier':value},final=True))


class FrontierFilesTests(base.BootstrapDiagnosticTests):
    # Inherit the existing guarded-file/census/cleanup tests for new collector output.
    def test_four_fresh_nonce_bound_markers_and_stale_rejection(self):
        for point in measurement.FRONTIER_POINTS:
            path=self.native.evidence/('zero-frontier-'+point+'.json')
            self.assertEqual(self.collect()['frontier'][point]['state'],'absent')
            d=marker(point);path.write_bytes(protocol.encode(d))
            self.assertEqual(self.collect()['frontier'][point]['state'],'valid')
            for changed in ({**d,'token':'c'*32},{**d,'nonce':'c'*32},{**d,'point':'other'},{**d,'raw':'PRIVATE'}):
                path.write_bytes(protocol.encode(changed));self.assertEqual(self.collect()['frontier'][point]['state'],'invalid')
            path.write_bytes(b'x'*2049);self.assertEqual(self.collect()['frontier'][point]['state'],'invalid');path.unlink()
    def test_new_files_scrubbed_after_timeout(self):
        error=base.stage.OracleError('timeout');error.oracle_site='poll'
        def launch(*a,**kw):
            for point in measurement.FRONTIER_POINTS:(self.native.evidence/('zero-frontier-'+point+'.json')).write_bytes(protocol.encode(marker(point)))
            raise error
        with mock.patch.object(self.native,'process',side_effect=launch):
            with self.assertRaises(base.stage.OracleError):self.native.enterprise(self.db,'bootstrap',token=self.token)
        self.assertTrue(all(v['state']=='valid' for v in self.native.zero_bootstrap_failure['frontier'].values()))
        self.assertFalse(list(self.native.evidence.glob('zero-frontier-*')))
    def test_preexisting_frontier_cannot_be_reused(self):
        (self.native.evidence/'zero-frontier-server_enter.json').write_bytes(protocol.encode(marker('server_enter')))
        with mock.patch.object(self.native,'process')as process:
            with self.assertRaises(base.stage.OracleError):self.native.enterprise(self.db,'bootstrap',token=self.token)
            process.assert_not_called()


class FrontierRenderingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'), 'Git required for checkout regression')
    def test_pinned_client_survives_autocrlf_checkout(self):
        root=Path(__file__).resolve().parents[1]
        rel='scripts/native_1c_db_oracle/modules/ManagedApplicationModule.bsl'
        raw=(root/rel).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),measurement.CLIENT_TEMPLATE_SHA256)
        with tempfile.TemporaryDirectory(prefix='zero-client-eol-') as directory:
            checkout=Path(directory)
            def git(*args):
                return subprocess.run(['git','-c','core.autocrlf=true','-c','core.safecrlf=false',*args],
                    cwd=checkout,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            git('init','-q')
            (checkout/'.gitattributes').write_bytes((root/'.gitattributes').read_bytes())
            client=checkout/rel;client.parent.mkdir(parents=True);client.write_bytes(raw)
            git('add','--','.gitattributes',rel)
            client.unlink();git('checkout-index','--force','--',rel)
            checked=client.read_bytes()
            self.assertEqual(checked,raw)
            self.assertNotIn(b'\r\n',checked)
            for case in measurement.CASES:
                self.assertIn(b'NativeZeroFrontier',measurement.instrument_module(checked,name='ManagedApplicationModule.bsl',case=case))

    def test_raw_crlf_client_remains_rejected(self):
        raw=(measurement.ROOT/'modules/ManagedApplicationModule.bsl').read_bytes()
        self.assertNotIn(b'\r',raw)
        for case in measurement.CASES:
            with self.assertRaisesRegex(ValueError,'zero_frontier_module_invalid'):
                measurement.instrument_module(raw.replace(b'\n',b'\r\n'),name='ManagedApplicationModule.bsl',case=case)
    def test_closed_instrumentation_and_literals(self):
        for case in measurement.CASES:
            for name in ('ManagedApplicationModule.bsl','NativeOracleServer.bsl'):
                raw=(measurement.ROOT/'modules'/name).read_bytes()
                text=measurement.instrument_module(raw,name=name,case=case).decode('utf-8')
                self.assertIn('Процедура NativeZeroFrontier(',text)
                self.assertIn('КонтрольДиагностики.operation <> "bootstrap"',text)
                self.assertNotIn('ОписаниеОшибки',text)
                with self.assertRaises(ValueError):measurement.instrument_module(raw+b' ',name=name,case=case)
                if name.startswith('Managed'):
                    self.assertLess(text.index('NativeZeroFrontier("client_before_call"'),text.index('Ответ = NativeOracleServer'))
                    self.assertLess(text.index('NativeZeroFrontier("client_after_call"'),text.index('NativeПроверитьОтвет(Ответ);'))
                    self.assertIn('NativeZeroFrontier("client_after_call", ПараметрЗапуска, "returned", "dispatch");',text)
                else:self.assertIn('NativeZeroFrontier("server_return", ТокенЗапуска, Контекст.status, Контекст.phase);',text)
    def test_zero_rendering_only_and_tokens_resolved(self):
        for name in metadata.m.MODULE_FILES:
            plain=metadata.m._module(name,metadata.NONCE,'/tmp/fixture')
            for case in measurement.CASES:
                rendered=metadata.m._module(name,metadata.NONCE,'/tmp/fixture',zero_case=case)
                self.assertNotIn(b'@@',rendered)
                if name=='SessionModule.bsl':self.assertEqual(plain,rendered)
                else:self.assertIn(b'NativeZeroFrontier',rendered)
            self.assertNotIn(b'NativeZeroFrontier',plain)
            for case in ('number3','number6'):
                self.assertNotIn(b'NativeZeroFrontier',metadata.m._module(name,metadata.NONCE,'/tmp/fixture',numeric_case=case))

if __name__=='__main__':unittest.main()
