"""Finite failure-only diagnostics using synthetic private files, not native evidence."""
import contextlib
import copy
import os
import stat
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_stage as old
import test_native_catalog_zero_code_policy as facts
import test_native_catalog_zero_code_export as export
import catalog_zero_code_policy as policy
import protocol
stage=old.stage

@contextlib.contextmanager
def static_fixture_descriptors(root):
    """Bounded Windows fixture adapter; never changes production/native Linux reads."""
    opened_real,inspected_real=stage.os.open,stage.os.fstat
    paths={};allowed={'bootstrap.json','result.json','completion.json','completion.pending.json',
                     '001-bootstrap.log','001-bootstrap-console.log','002-bootstrap.log','002-bootstrap-console.log','002-zero-compile.log','002-zero-compile.result'}
    allowed.update('zero-frontier-'+point+'.json' for point in facts.measurement.FRONTIER_POINTS)
    nofollow=getattr(stage.os,'O_NOFOLLOW',0)
    def opened(path,flags,*args,**kwargs):
        path=stage.Path(path)
        if path.parent!=root or path.name not in allowed or flags!=(os.O_RDONLY|nofollow) or args or kwargs:
            raise ValueError('static_fixture_path_invalid')
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<=info.st_size<=32768:
            raise ValueError('static_fixture_shape_invalid')
        fd=opened_real(path,flags);paths[fd]=path;return fd
    def inspected(fd):
        actual=inspected_real(fd)
        if fd not in paths:return actual
        current=paths[fd].lstat()
        if (not stat.S_ISREG(actual.st_mode) or actual.st_nlink!=1 or actual.st_size!=current.st_size
                or not stat.S_ISREG(current.st_mode) or current.st_nlink!=1 or not 0<=current.st_size<=32768):
            raise ValueError('static_fixture_shape_invalid')
        return current
    with mock.patch.object(stage.os,'O_NOFOLLOW',nofollow,create=True),mock.patch.object(stage.os,'open',side_effect=opened),mock.patch.object(stage.os,'fstat',side_effect=inspected):
        yield

class BootstrapDiagnosticTests(unittest.TestCase):
    def setUp(self):
        old.NativeBoundaryTests.setUp(self)
        self.native.zero_case='zero0';self.native.description_policy=policy
        self.native.begin_stage('seed_v1');self.native.seed_pending=self.native.seed_launched='bootstrap'
        self.token='b'*32;self.native.counter=1
        self.out=self.native.evidence/'001-bootstrap.log';self.console=self.native.evidence/'001-bootstrap-console.log'
        for name,value in [('quiescent',True),('budgets',None)]:
            patch=mock.patch.object(self.native,name,return_value=value);patch.start();self.addCleanup(patch.stop)
        if os.name=='nt':self.enterContext(static_fixture_descriptors(self.native.evidence))
    def collect(self):return self.native._zero_bootstrap_diagnostic(self.token)
    def bootstrap(self):
        return dict(schema=1,nonce=self.native.nonce,token=self.token,operation='bootstrap',status='ok',actual_version=protocol.VERSION,
            user='',role_verified=True,nonprivileged=False,users_verified=True,metadata_version=1,count=None,code=None,
            payload=None,amount=None,deletion_mark=None,same_reference=None,payload_length=32,amount_digits=9,amount_scale=2)
    def test_fresh_markers_and_private_phrase_projection(self):
        for name in ('bootstrap.json','result.json'):(self.native.evidence/name).write_bytes(protocol.encode(self.bootstrap()))
        for name,status,phase in [('completion.json','error','metadata'),('completion.pending.json','ok','complete')]:
            (self.native.evidence/name).write_bytes(protocol.encode(dict(schema=1,nonce=self.native.nonce,token=self.token,operation='bootstrap',status=status,phase=phase)))
        for encoding in ('utf-8','utf-16-le','utf-16-be'):
            self.out.write_bytes('SECRET /private Ошибка инициализации модуля Переменная не определена Синтаксическая ошибка'.encode(encoding));self.console.write_bytes(b'')
            d=self.collect();self.assertEqual(d['bootstrap'],'valid_ok');self.assertEqual(d['result'],'valid_ok')
            self.assertEqual(d['completion'],'valid_error');self.assertEqual(d['pending'],'valid_ok')
            self.assertEqual(d['out'],dict(state='nonempty',module_error=True,undefined_symbol=True,syntax_error=True))
            self.assertEqual(d['console']['state'],'empty');self.assertNotIn('SECRET',str(d));self.assertNotIn('/private',str(d))
    def test_adapter_is_bounded_and_exercised_on_all_hosts(self):
        with static_fixture_descriptors(self.native.evidence):
            self.test_fresh_markers_and_private_phrase_projection()
            with self.assertRaises(ValueError):os.open(self.root/'outside',os.O_RDONLY)
            self.out.write_bytes(b'x'*32769);self.assertEqual(self.collect()['out']['state'],'unavailable')
    def test_missing_malformed_stale_and_oversized(self):
        self.assertEqual(self.collect()['bootstrap'],'absent')
        path=self.native.evidence/'bootstrap.json'
        for raw in (b'',b'{}',b'PRIVATE',b'x'*32769):
            path.write_bytes(raw);self.assertEqual(self.collect()['bootstrap'],'invalid')
        for key,val in [('token','c'*32),('nonce','d'*32),('code','PRIVATE'),('actual_version','PRIVATE')]:
            value=self.bootstrap();value[key]=val;path.write_bytes(protocol.encode(value));self.assertEqual(self.collect()['bootstrap'],'invalid')
        self.out.write_bytes(b'x'*32769)
        with mock.patch.object(stage.os,'open',side_effect=AssertionError('must not read oversize')):
            self.assertEqual(self.collect()['out']['state'],'unavailable')
    @unittest.skipUnless(os.name=='posix','POSIX descriptor/link semantics')
    def test_links_nonregular_and_races_rejected(self):
        outside=self.root/'private';outside.write_bytes(b'Syntax error')
        self.out.symlink_to(outside);self.assertEqual(self.collect()['out']['state'],'unavailable');self.out.unlink()
        os.link(outside,self.out);self.assertEqual(self.collect()['out']['state'],'unavailable');self.out.unlink()
        self.out.mkdir();self.assertEqual(self.collect()['out']['state'],'unavailable');self.out.rmdir()
        self.out.write_bytes(b'Syntax error');real=stage.os.fstat;count=0
        def mutate(fd):
            nonlocal count
            count+=1
            if count==2:self.out.write_bytes(b'changed longer')
            return real(fd)
        with mock.patch.object(stage.os,'fstat',side_effect=mutate):self.assertEqual(self.collect()['out']['state'],'unavailable')
    def test_guards_and_post_census(self):
        for name,value in [('stage','baseline'),('seed_pending','other'),('seed_launched',None),('counter',True),('counter',129),('zero_case',None)]:
            with mock.patch.object(self.native,name,value):self.assertIsNone(self.collect())
        self.assertIsNone(self.native._zero_bootstrap_diagnostic('bad'))
        with mock.patch.object(self.native,'quiescent',side_effect=[True,False]):self.assertIsNone(self.collect())
        with mock.patch.object(self.native,'budgets',side_effect=RuntimeError('PRIVATE')):self.assertIsNone(self.collect())
    def test_original_timeout_preserved_and_private_files_scrubbed(self):
        original=stage.OracleError('timeout');original.oracle_site='poll'
        with mock.patch.object(self.native,'process',side_effect=original):
            with self.assertRaises(stage.OracleError)as caught:self.native.enterprise(self.db,'bootstrap',token=self.token)
        self.assertIs(caught.exception,original);self.assertIsNotNone(self.native.zero_bootstrap_failure)
        for name in ('control.json','result.json','completion.json','completion.pending.json','zero-code-observation.json'):
            self.assertFalse((self.native.evidence/name).exists())
    def test_collector_errors_preserve_original_and_non_timeout_ignored(self):
        for kind in ('timeout','process_failed'):
            original=stage.OracleError(kind);original.oracle_site='poll'
            with mock.patch.object(self.native,'process',side_effect=original),mock.patch.object(self.native,'_zero_bootstrap_diagnostic',side_effect=RuntimeError('PRIVATE'))as collect:
                with self.assertRaises(stage.OracleError)as caught:self.native.enterprise(self.db,'bootstrap',token=self.token)
                self.assertIs(caught.exception,original);self.assertIsNone(self.native.zero_bootstrap_failure)
                self.assertEqual(collect.call_count,int(kind=='timeout'))
    def test_actual_process_killed_and_reaped_before_collection(self):
        events=[]
        class Child:
            pid=999999;running=True
            def poll(self):return None if self.running else -9
            def wait(self,timeout=None):events.append('reap');self.running=False;return -9
        child=Child();original=self.native._zero_bootstrap_diagnostic
        def collect(token):
            self.assertFalse(child.running);events.append('collect');return original(token)
        with mock.patch.object(stage.subprocess,'Popen',return_value=child),mock.patch.object(stage.os,'killpg',side_effect=lambda *a:events.append('kill'),create=True),mock.patch.object(stage.signal,'SIGKILL',9,create=True),mock.patch.object(stage,'COMMAND_SECONDS',0),mock.patch.object(self.native,'_zero_bootstrap_diagnostic',side_effect=collect):
            with self.assertRaises(stage.OracleError)as caught:self.native.enterprise(self.db,'bootstrap',token=self.token)
        self.assertEqual(caught.exception.kind,'timeout');self.assertEqual(events,['kill','reap','collect'])
    def test_hostile_exception_keys_not_executed(self):
        class Key:
            def __hash__(self):return hash('kind')
            def __eq__(self,other):raise AssertionError('hostile key')
        error=stage.OracleError('timeout');error.__dict__={Key():'timeout','oracle_site':'poll'}
        with mock.patch.object(self.native,'process',side_effect=error),mock.patch.object(self.native,'_zero_bootstrap_diagnostic')as collect:
            with self.assertRaises(stage.OracleError)as caught:self.native._enterprise(self.db,'bootstrap',token=self.token)
            self.assertIs(caught.exception,error);collect.assert_not_called()
    def test_controller_requires_cleanup(self):
        import test_native_catalog_zero_code_lifecycle as lifecycle
        for safe in (False,True):
            with tempfile.TemporaryDirectory()as tmp:
                prov=facts.provenance();r=policy.empty_report(facts.NONCE,prov,zero_case='zero0');backend=lifecycle.ByteBackend(stage.Path(tmp).resolve(),prov)
                controller=stage.Controller(backend,r);backend.controller=controller
                error=stage.SeedCommandError('timeout','bootstrap')
                error.failure_context=dict(operation='enterprise_bootstrap',site='poll',bsl_phase=None,region=None,reason=None);error.failure_context_stage='seed_v1'
                def seed():backend.zero_bootstrap_failure=facts.bootstrap_diagnostic();raise error
                clean=backend.cleanup
                def cleanup():
                    processes,files=clean();return processes and safe,files
                with mock.patch.object(backend,'seed',side_effect=seed),mock.patch.object(backend,'cleanup',side_effect=cleanup):result=controller.run()
                self.assertFalse(result['accepted']);self.assertIsNone(result['zero_code_measurement'])
                self.assertEqual('zero_bootstrap_failure'in result,safe)
                if safe:
                    with self.assertRaises(stage.OracleError):policy.validate_report(protocol.encode(result),nonce=result['nonce'],provenance=prov,final=True)
                    result['cleanup'].update(container_removed=True,private_staging_removed=True)
                    policy.validate_report(protocol.encode(result),nonce=result['nonce'],provenance=prov,final=True)

@unittest.skipUnless(export.h.old.DESCRIPTOR_HANDOFF,'requires POSIX exclusive exporter')
class BootstrapExportTests(unittest.TestCase):
    def setUp(self):export.NumericExportTests.setUp(self)
    argv=export.NumericExportTests.argv
    def test_real_main_exports_failed_diagnostic_without_aggregate(self):
        host=export.host;r=facts.bootstrap_failure();self.assertTrue(policy.set_bootstrap_failure(r,facts.bootstrap_diagnostic(),final=True))
        raw=protocol.encode(r);output=self.root/'github-output'
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'run_oracle',return_value=r),mock.patch.object(host,'provenance',return_value=r['provenance']),mock.patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)},clear=True):
            self.assertEqual(host.main(self.argv('zero0')),1)
        self.assertEqual((self.root/host.ZERO_CODE_OUTPUTS['zero0']).read_bytes(),raw+b'\n')
        self.assertFalse((self.root/host.ZERO_CODE_AGGREGATE).exists());self.assertIn('report_ready=true',output.read_text(encoding='utf-8'))
    def test_host_cleanup_failure_discards_projection(self):
        r=facts.bootstrap_failure();policy.set_bootstrap_failure(r,facts.bootstrap_diagnostic(),final=True)
        export.host.fail_report(r,'cleanup_unverified','cleanup',preserve_primary=True)
        self.assertNotIn('zero_bootstrap_failure',r)

if __name__=='__main__':unittest.main()
