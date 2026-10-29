"""Closed reference routing and descriptor-bound same-run artifact handoff."""
import copy
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_catalog_readonly_route as old
import test_native_catalog_reference_identity as facts
import inputs
import protocol
from contract import source_binding

host=old.host
# This real filesystem test is the same POSIX-only boundary as HostSecurityTests.
DESCRIPTOR_HANDOFF = (hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
                      and os.open in os.supports_dir_fd)

class ReferenceRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.addCleanup(lambda:old.old.writable(self.root))

    def test_closed_selector_stage_and_container(self):
        for case in ('distinct_a','distinct_b'):
            options={'reference_case':case};value=old.identity()
            value['sources']=inputs.source_hashes(old.ROOT,**options)
            stage=self.root/case
            inputs.stage_inputs(old.ROOT,stage,old.NONCE,value,**options)
            self.assertEqual(inputs.verify_inputs(stage,old.NONCE,**options),value)
            invocation=protocol.decode((stage/'invocation.json').read_bytes())
            self.assertEqual((invocation['schema'],invocation['reference_case']),(24,case))
            command=host.container_command(stage,'onec-db-oracle-'+'a'*32,old.NONCE,**options)
            self.assertEqual(command[-1],'--catalog-reference-'+case.replace('_','-'))
            with self.assertRaises(Exception):inputs.verify_inputs(stage,old.NONCE,catalog_readonly_binding=True)
            with self.assertRaises(Exception):inputs.verify_inputs(stage,old.NONCE,reference_case='distinct_b' if case=='distinct_a' else 'distinct_a')
        for case in (True,1,[],{},'other'):
            with self.assertRaises(Exception):inputs.inventory(reference_case=case)
        with self.assertRaises(Exception):inputs.inventory(reference_case='distinct_a',catalog_readonly_binding=True)

    def artifact(self):
        report=facts.fixture();raw=protocol.encode(report)+b'\n'
        parent=self.root/'native-db-oracle';parent.mkdir();(parent/'distinct_a.json').write_bytes(raw)
        info=self.root.stat()
        return report,raw,(info.st_dev,info.st_ino)

    @unittest.skipUnless(DESCRIPTOR_HANDOFF, 'Native handoff requires POSIX no-follow dirfd support')
    def test_handoff_exact_digest_run_source_case_and_inventory(self):
        report,raw,identity=self.artifact()
        env={'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','REFERENCE_A_RUN_ID':'123',
             'REFERENCE_A_RUN_ATTEMPT':'2','REFERENCE_A_SHA256':hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'provenance',return_value=report['provenance']),mock.patch.dict(os.environ,env,clear=True):
            self.assertEqual(host.validate_reference_a(identity),raw)
            for key,value in (('REFERENCE_A_SHA256','f'*64),('REFERENCE_A_RUN_ID','124'),('REFERENCE_A_RUN_ATTEMPT','1')):
                with mock.patch.dict(os.environ,{key:value}),self.assertRaises(Exception):host.validate_reference_a(identity)
            foreign=self.root/'native-db-oracle'/'extra.json';foreign.write_bytes(b'{}')
            with self.assertRaises(Exception):host.validate_reference_a(identity)
            foreign.unlink()
            path=self.root/'native-db-oracle'/'distinct_a.json';path.unlink();path.symlink_to(self.root/'foreign')
            with self.assertRaises(Exception):host.validate_reference_a(identity)

    @unittest.skipUnless(DESCRIPTOR_HANDOFF and shutil.which('git'),
                         'Real Git handoff requires POSIX no-follow dirfd support and git')
    def test_real_git_handoff_keeps_source_and_artifact_guards(self):
        # Real repository_provenance and source_hashes, not a mocked identity.
        names=set(inputs.CATALOG_REFERENCE_SOURCE_FILES)
        names.update(path.relative_to(old.ROOT).as_posix()
                     for path in (old.ROOT/'yadinassi').rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts)
        names.update(('.gitignore','scripts/native_infobase_fixture.py',
                      'scripts/native_1c_tree_load_contract.py',
                      'scripts/native_1c_tree_move_contract.py',
                      'scripts/native_1c_tree_total_contract.py'))
        for name in names:
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(old.ROOT/name,target)
        def git(*args):
            return subprocess.run(['git','-C',str(self.root),*args],check=True,
                                  capture_output=True).stdout
        git('init','-q');git('add','.')
        git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            '-c','commit.gpgsign=false','commit','-qm','Synthetic source fixture')
        env={'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2',
             'REFERENCE_A_RUN_ID':'123','REFERENCE_A_RUN_ATTEMPT':'2'}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.dict(os.environ,env,clear=True):
            report=facts.fixture()
            report['provenance']=host.provenance(reference_case='distinct_a')
            report['provenance']['actual_version']=protocol.VERSION
            report['record_readback']['record_reader_source_sha256']=report['provenance']['sources'][facts.p.READER_SOURCE]
            report['record_readback']['audit']['reader_source_sha256']=report['provenance']['sources'][facts.p.metadata.READER_SOURCE]
            report['record_readback']['audit']['source_manifest_sha256']=source_binding(report['provenance'])
            raw=protocol.encode(report)+b'\n'
            parent=self.root/'native-db-oracle';parent.mkdir()
            artifact=parent/'distinct_a.json';artifact.write_bytes(raw)
            os.environ['REFERENCE_A_SHA256']=hashlib.sha256(raw).hexdigest()
            info=self.root.stat();identity=(info.st_dev,info.st_ino)
            self.assertEqual(git('status','--porcelain','--untracked-files=all'),b'')
            self.assertEqual(host.validate_reference_a(identity),raw)
            self.assertEqual(host.main(['--validate-reference-a']),0)
            # The exception is one exact rooted filename, never a directory waiver.
            for relative in ('unrelated.txt','native-db-oracle/extra.json',
                             'native-db-oracle/distinct_b.json',
                             'other/native-db-oracle/distinct_a.json'):
                path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'{}')
                self.assertNotEqual(git('status','--porcelain','--untracked-files=all'),b'')
                with self.assertRaises(Exception):host.provenance(reference_case='distinct_b')
                self.assertEqual(host.main(['--validate-reference-a']),1)
                path.unlink()
            tracked=self.root/'scripts/native_infobase_fixture.py'
            original=tracked.read_bytes();tracked.write_bytes(original+b'\n')
            with self.assertRaises(Exception):host.provenance(reference_case='distinct_b')
            self.assertEqual(host.main(['--validate-reference-a']),1)
            tracked.write_bytes(original)
            # Even a digest-authenticated ignored artifact is not trusted as a report.
            for bad in (b'{',b'{}'):
                artifact.write_bytes(bad)
                os.environ['REFERENCE_A_SHA256']=hashlib.sha256(bad).hexdigest()
                self.assertEqual(git('status','--porcelain','--untracked-files=all'),b'')
                self.assertEqual(host.main(['--validate-reference-a']),1)
            artifact.write_bytes(raw)
            os.environ['REFERENCE_A_SHA256']=hashlib.sha256(raw).hexdigest()
            self.assertEqual(host.validate_reference_a(identity),raw)

    def test_no_credentials_preflight(self):
        with mock.patch.dict(os.environ,{'GHCR_TOKEN':'PRIVATE'},clear=True),mock.patch.object(host,'validate_reference_a') as validate:
            self.assertEqual(host.main(['--validate-reference-a']),1);validate.assert_not_called()

if __name__=='__main__':unittest.main()
