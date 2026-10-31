"""Real CLI -> exclusive descriptor exporter; no Docker/native execution."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import test_native_catalog_numeric_code_host as h
import catalog_numeric_code_policy as policy

host=h.host

@unittest.skipUnless(h.old.DESCRIPTOR_HANDOFF,'requires existing POSIX exclusive no-follow exporter')
class NumericExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.info=self.root.stat();self.identity=(self.info.st_dev,self.info.st_ino)
    def argv(self,case):
        return ['--execute-approved-image','--file-db-oracle','--catalog-numeric-code',case,'--output',str(host.NUMERIC_CODE_OUTPUTS[case])]
    def test_real_main_exports_both_validated_successes_and_aggregate(self):
        reports={c:h.facts.fixture(c,nonce=('a'if c=='number3'else'b')*32)for c in policy.CASES}
        def produce(_,*,numeric_case):
            r=reports[numeric_case]
            return policy.validate_report(h.protocol.encode(r),nonce=r['nonce'],provenance=r['provenance'],final=True)
        output=self.root/'github-output'
        env={'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','GITHUB_OUTPUT':str(output)}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'run_oracle',side_effect=produce),mock.patch.object(host,'provenance',return_value=reports['number3']['provenance']),mock.patch.dict(os.environ,env,clear=True):
            self.assertEqual(host.main(self.argv('number3')),0)
            a=(self.root/host.NUMERIC_CODE_OUTPUTS['number3']).read_bytes()
            self.assertEqual(a,h.protocol.encode(reports['number3'])+b'\n')
            self.assertIn('numeric_code_sha256='+hashlib.sha256(a).hexdigest(),output.read_text())
            os.environ.update(NUMERIC_CODE3_SHA256=hashlib.sha256(a).hexdigest(),NUMERIC_CODE3_RUN_ID='123',NUMERIC_CODE3_RUN_ATTEMPT='2')
            self.assertEqual(host.main(self.argv('number6')),0)
            b=(self.root/host.NUMERIC_CODE_OUTPUTS['number6']).read_bytes()
            agg=(self.root/host.NUMERIC_CODE_AGGREGATE).read_bytes()
            policy.validate_aggregate(agg,provenance=reports['number3']['provenance'],run_id=123,run_attempt=2,reports=tuple(reports.values()),report_sha256s=(hashlib.sha256(a).hexdigest(),hashlib.sha256(b).hexdigest()))
            self.assertIn('aggregate_ready=true',output.read_text())
    def test_real_main_run_oracle_exports_sanitized_credentials_failure(self):
        source=Path(__file__).resolve().parents[1]
        for path in h.inputs.CATALOG_NUMERIC_CODE_SOURCE_FILES:
            dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/path,dest)
        prov=h.facts.provenance();prov['actual_version']=None;prov['sources']=h.inputs.source_hashes(source,numeric_case='number3')
        output=self.root/'github-output'
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'provenance',return_value=prov),mock.patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)},clear=True):
            self.assertEqual(host.main(self.argv('number3')),1)
        raw=(self.root/host.NUMERIC_CODE_OUTPUTS['number3']).read_bytes();r=h.protocol.decode(raw)
        policy.validate_report(raw,nonce=r['nonce'],provenance=prov,final=True)
        self.assertEqual(r['failure_kind'],'registry_credentials_missing');self.assertFalse(r['accepted'])
        self.assertIsNone(r['numeric_code_measurement']);self.assertTrue(all(r['cleanup'].values()))
        self.assertIn('report_ready=true',output.read_text());self.assertFalse((self.root/host.NUMERIC_CODE_AGGREGATE).exists())
    def test_every_declared_closed_profile_path_exports_and_foreign_paths_reject(self):
        # Discover declared path constants, not the implementation's allowlist:
        # adding a future route without its exporter entry must fail this test.
        paths={host.OUTPUT}
        for name,value in vars(host).items():
            if name.endswith('_OUTPUTS'):
                self.assertIs(type(value),dict);paths.update(value.values())
            elif name.endswith('_AGGREGATE'):
                self.assertIsInstance(value,Path);paths.add(value)
        self.assertEqual(len(paths),28)
        with mock.patch.object(host,'ROOT',self.root):
            for path in sorted(paths):
                host.export_report(b'{}',self.identity,output=path)
                self.assertEqual((self.root/path).read_bytes(),b'{}\n')
                with self.assertRaises(Exception):host.export_report(b'{}',self.identity,output=path)
            for path in (Path('native-db-oracle/numeric_code4.json'),Path('other/numeric_code3.json'),Path('native-db-oracle/nested/numeric_code3.json'),Path('../numeric_code3.json')):
                with self.assertRaises(Exception):host.export_report(b'{}',self.identity,output=path)
    def test_numeric_paths_preserve_descriptor_and_byte_guards(self):
        paths=(*host.NUMERIC_CODE_OUTPUTS.values(),host.NUMERIC_CODE_AGGREGATE)
        for path in paths:
            for fault in ('root_identity','bytecap','parent_symlink','target_symlink'):
                with self.subTest(path=path,fault=fault),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp).resolve();info=root.stat();identity=(info.st_dev,info.st_ino)
                    outside=root/'outside';outside.mkdir();target=root/path
                    if fault=='parent_symlink':target.parent.symlink_to(outside,target_is_directory=True)
                    elif fault=='target_symlink':
                        target.parent.mkdir();target.symlink_to(outside/'secret')
                    if fault=='root_identity':identity=(identity[0],identity[1]+1)
                    raw=b'x'*host.MAX_REPORT_BYTES if fault=='bytecap'else b'{}'
                    with mock.patch.object(host,'ROOT',root),self.assertRaises(Exception):host.export_report(raw,identity,output=path)
                    self.assertFalse(list(outside.iterdir()))
                    if fault not in ('parent_symlink','target_symlink'):self.assertFalse(target.exists())
