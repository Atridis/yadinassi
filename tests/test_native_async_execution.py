"""Offline synthetic completion evidence; never native Async parity."""
import json
import os
from pathlib import Path
import shutil
import time
import unittest
from unittest import mock
import test_native_client_probe as probe
import test_native_async_protocol as protocol
suite=probe.suite
NONCE=probe.NONCE

class AsyncExecutionTests(unittest.TestCase):
    argument=staticmethod(probe.ClientProbeHarness.argument)
    def setUp(self):
        probe.ClientProbeHarness.setUp(self)
        self.work=self.root/'async';self.transform=None;self.only_entered=False;self.failure=None
        patcher=mock.patch.object(suite,'run_async_process',side_effect=self.fake_async)
        patcher.start();self.addCleanup(patcher.stop)
    def reset(self):
        if self.work.exists():shutil.rmtree(self.work)
        self.events.clear()
    def fake_native(self,*args,**kwargs):raise AssertionError('async used legacy runner')
    def fake_async(self,command,directory,log,timeout,*,require_clean_tree=False):
        self.assertGreater(timeout,0);self.assertLessEqual(timeout,120);self.assertTrue(require_clean_tree)
        self.assertEqual(self.argument(command,'/N'),'NativeSmoke');self.assertNotIn('/P',command)
        case=int(directory.name.split('-')[-1])
        mode='build' if '/LoadExternalDataProcessorOrReportFromFiles' in command else 'dump' if '/DumpExternalDataProcessorOrReportToFiles' in command else 'enterprise'
        self.events.append(mode);self.assertFalse(log.exists());log.write_bytes(b'PRIVATE fake log')
        if mode=='build':
            at=command.index('/LoadExternalDataProcessorOrReportFromFiles')
            Path(command[at+2]).write_bytes(b'OFFLINE fake EPF')
            Path(self.argument(command,'/DumpResult')).write_bytes(b'0\n')
        elif mode=='dump':
            dest=Path(self.argument(command,'/DumpExternalDataProcessorOrReportToFiles')).parent
            shutil.copytree(directory/'src',dest,dirs_exist_ok=True)
            Path(self.argument(command,'/DumpResult')).write_bytes(b'0\n')
        else:
            req=json.loads(Path(self.argument(command,'/C')).read_text())
            self.assertEqual(set(req),{'schema','version','nonce','entered','completed'})
            self.assertEqual(req['nonce'],NONCE)
            base=dict(schema=1,nonce=NONCE,case=case,phase='entered',witness='client')
            Path(req['entered']).write_text(json.dumps(base))
            if not self.only_entered:
                trace,values,errors=protocol.observation(case)
                value=dict(base,phase='completed',status=1,failure=0,trace=trace,values=values,
                           errors=[protocol.private_error(error[0]) for error in errors])
                if self.transform:self.transform(value)
                Path(req['completed']).write_text(json.dumps(value))
        if self.hook:self.hook(mode,directory)
        if mode=='enterprise' and self.failure:raise suite.FullError(self.failure)
    def run_async(self,deadline=None):
        return suite.run_client_async(self.platform,self.work,self.inputs,NONCE,self.hashes,
                                      deadline=time.monotonic()+1000 if deadline is None else deadline)
    def test_eight_cases_exact_hashes_and_no_seventh_output(self):
        value=self.run_async();self.assertEqual(value['status'],'ok',value)
        self.assertEqual(self.events,['build','dump','enterprise']*8)
        self.assertEqual([r[4] for r in value['cases']],[63]*8)
        self.assertEqual(list(self.work.rglob('*.out')),[])
        for row in value['cases']:self.assertEqual(row[3],suite.digest(suite.async_client_module(row[0])))
    def test_early_exit_noise_nonce_witness_duplicate_premature_completion(self):
        self.only_entered=True
        self.assertNotEqual(self.run_async()['status'],'ok');self.reset();self.only_entered=False
        edits=[lambda m:m['trace'].pop(),lambda m:m['trace'].append(29),
               lambda m:m.update(nonce='0'*32),lambda m:m.update(witness='server'),
               lambda m:m.update(case=7),lambda m:m['trace'].__setitem__(2,4),
               lambda m:m['trace'].append(m['trace'][2]),lambda m:m.update(extra='PRIVATE')]
        for edit in edits:
            self.transform=edit;self.assertNotEqual(self.run_async()['status'],'ok');self.reset()
    def test_timeout_nonzero_survivor_and_expired_deadline(self):
        for kind in ('timeout','process_failed'):
            self.failure=kind;self.assertEqual(self.run_async()['failure_kind'],kind);self.reset()
        self.failure=None
        with mock.patch.object(suite,'client_process_snapshot',return_value={(999999,'1')}):
            self.assertEqual(self.run_async()['failure_kind'],'process_failed')
        self.reset();self.assertNotEqual(self.run_async(time.monotonic()-1)['status'],'ok')
    def test_stale_directory_and_roundtrip_tamper(self):
        self.work.mkdir();self.assertEqual(self.run_async()['failure_kind'],'stale_evidence');self.reset()
        def alter(mode,path):
            if mode=='dump':
                module=path/'roundtrip'/suite.CLIENT_MODULE;module.write_bytes(module.read_bytes()+b'\n// tamper')
        self.hook=alter;self.assertEqual(self.run_async()['failure_kind'],'module_mismatch')
        self.assertEqual(self.events,['build','dump'])
    def test_same_content_inode_replacement_before_export(self):
        def replace(mode,path):
            if mode=='enterprise':
                target=path/'src'/suite.CLIENT_MODULE;other=target.with_suffix('.replacement')
                other.write_bytes(target.read_bytes());other.replace(target)
        self.hook=replace;self.assertEqual(self.run_async()['failure_kind'],'stale_evidence')
    def test_final_census_invalidates_last_case_and_aggregate(self):
        value=self.run_async();self.assertEqual(value['status'],'ok')
        report={'status':'ok','failure_kind':'none','client_async':value}
        suite.fail_client_process_checkpoint(report,False)
        self.assertEqual(value['status'],'failed');self.assertEqual(value['cases'][-1][1:3],[2,11])
        self.assertEqual(value['cases'][-1][4:],[0,[],[],[]])
    def test_inconclusive_does_not_export_partial_data(self):
        self.transform=lambda m:m.update(status=3,failure=14,trace=[],values=[],errors=[])
        value=self.run_async();self.assertEqual(value['status'],'inconclusive')
        self.assertEqual(value['cases'][0][1:3],[3,14])
    @unittest.skipUnless(os.name=='posix','POSIX files')
    def test_snapshots_reject_links_and_same_bytes_replacement(self):
        p=self.root/'one';p.write_bytes(b'x');saved=suite.async_file_snapshot(p,10)
        q=self.root/'two';q.write_bytes(b'x');q.replace(p)
        with self.assertRaises(suite.FullError):suite.async_require_snapshot(p,saved,10)
        q.symlink_to(p)
        with self.assertRaises(suite.FullError):suite.async_file_snapshot(q,10)
        q.unlink();os.link(p,q)
        with self.assertRaises(suite.FullError):suite.async_file_snapshot(p,10)

class AsyncFinalContinuityTests(AsyncExecutionTests):
    def test_persisted_continuity_survives_stage_boundary_and_rejects_late_mutation(self):
        value=self.run_async();self.assertEqual(value['status'],'ok',value)
        suite.final_async_evidence_check(self.work,self.inputs,NONCE,value["continuity_sha256"])
        p=self.work/'case-0/completed.json';raw=p.read_bytes();q=p.with_suffix('.swap')
        q.write_bytes(raw);q.replace(p)
        with self.assertRaises(suite.FullError):suite.final_async_evidence_check(self.work,self.inputs,NONCE,value["continuity_sha256"])
    def test_continuity_inventory_and_nonce_are_strict(self):
        record=self.run_async();self.assertEqual(record['status'],'ok')
        p=self.work/'continuity.json';original=p.read_bytes();value=json.loads(original)
        value['files']['/tmp/unrelated']=[[1]*7,'a'*64];p.write_text(json.dumps(value))
        with self.assertRaises(suite.FullError):suite.final_async_evidence_check(self.work,self.inputs,NONCE,record["continuity_sha256"])
        p.write_bytes(original)
        with self.assertRaises(suite.FullError):suite.final_async_evidence_check(self.work,self.inputs,'b'*32,record['continuity_sha256'])

if __name__=='__main__':unittest.main()
