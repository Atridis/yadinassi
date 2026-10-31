"""Real Git/source cleanliness for the separately named Description handoff."""
import hashlib
import os
import shutil
import subprocess
import unittest
from unittest import mock
import test_native_catalog_reference_route as route
import test_native_catalog_zero_code_policy as facts
import test_native_catalog_rows_host as host_tests
import catalog_reference_identity as measurement
import inputs
import protocol
from contract import source_binding
host = route.host
old = route.old
DESCRIPTOR_HANDOFF = route.DESCRIPTOR_HANDOFF


class NumericCodeGitHandoffTests(unittest.TestCase):
    setUp = host_tests.RowsHostTests.setUp

    @unittest.skipUnless(DESCRIPTOR_HANDOFF and shutil.which('git'),
                         'Real Git handoff requires POSIX no-follow dirfd support and git')
    def test_description_real_git_handoff_keeps_source_and_artifact_guards(self):
        # Real repository_provenance and source_hashes, not a mocked identity.
        names=set(inputs.CATALOG_ZERO_CODE_SOURCE_FILES)
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
             'ZERO_CODE0_RUN_ID':'123','ZERO_CODE0_RUN_ATTEMPT':'2'}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.dict(os.environ,env,clear=True):
            report=facts.fixture("zero0")
            report['provenance']=host.provenance(zero_case='zero0')
            report['provenance']['actual_version']=protocol.VERSION
            raw=protocol.encode(report)+b'\n'
            parent=self.root/'native-db-oracle';parent.mkdir()
            artifact=parent/'zero_code0.json';artifact.write_bytes(raw)
            os.environ['ZERO_CODE0_SHA256']=hashlib.sha256(raw).hexdigest()
            info=self.root.stat();identity=(info.st_dev,info.st_ino)
            self.assertEqual(git('status','--porcelain','--untracked-files=all'),b'')
            self.assertEqual(host.validate_zero_code0(identity),raw)
            self.assertEqual(host.main(['--validate-zero-code0']),0)
            # The exception is one exact rooted filename, never a directory waiver.
            for relative in ('unrelated.txt','native-db-oracle/extra.json',
                             'native-db-oracle/zero_code8.json',
                             'native-db-oracle/zero-code-aggregate.json',
                             'other/native-db-oracle/zero_code0.json'):
                path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'{}')
                self.assertNotEqual(git('status','--porcelain','--untracked-files=all'),b'')
                with self.assertRaises(Exception):host.provenance(zero_case='zero8')
                self.assertEqual(host.main(['--validate-zero-code0']),2)
                path.unlink()
            tracked=self.root/'scripts/native_infobase_fixture.py'
            original=tracked.read_bytes();tracked.write_bytes(original+b'\n')
            with self.assertRaises(Exception):host.provenance(zero_case='zero8')
            self.assertEqual(host.main(['--validate-zero-code0']),2)
            tracked.write_bytes(original)
            # Even a digest-authenticated ignored artifact is not trusted as a report.
            for bad in (b'{',b'{}'):
                artifact.write_bytes(bad)
                os.environ['ZERO_CODE0_SHA256']=hashlib.sha256(bad).hexdigest()
                self.assertEqual(git('status','--porcelain','--untracked-files=all'),b'')
                self.assertEqual(host.main(['--validate-zero-code0']),2)
            artifact.write_bytes(raw)
            os.environ['ZERO_CODE0_SHA256']=hashlib.sha256(raw).hexdigest()
            self.assertEqual(host.validate_zero_code0(identity),raw)

