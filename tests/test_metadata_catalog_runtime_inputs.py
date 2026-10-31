"""Closed real runtime/dependency staging; no native launch or API acceptance."""
from pathlib import Path
import hashlib
import errno
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/native_1c_db_oracle'))
import metadata_catalog_runtime_inputs as subject
from snapshots import OracleError
from protocol import IMAGE


class RuntimeBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.staged = Path(cls.temp.name).resolve() / 'staged'
        cls.nonce = 'a' * 32
        cls.provenance = dict(commit='b'*40,tree='c'*40,
            sources=subject.source_hashes(ROOT),image=IMAGE,platform='linux/amd64',
            actual_version=None,locale='ru_RU.UTF-8',timezone='Etc/UTC')
        subject.stage_inputs(ROOT, cls.staged, cls.nonce, cls.provenance)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_closed_real_bundle_versions_sources_and_data(self):
        actual = subject.verify_inputs(self.staged, self.nonce)
        self.assertEqual(actual, self.provenance)
        raw, manifest = subject._manifest(self.staged)
        self.assertLess(len(raw), subject.MAX_MANIFEST)
        self.assertLess(sum(i['bytes'] for i in manifest['files'].values()), subject.MAX_TOTAL)
        source_files = {p.relative_to(ROOT).as_posix() for p in (ROOT/'yadinassi').rglob('*')
                        if p.is_file() and '__pycache__' not in p.parts}
        self.assertEqual(set(manifest['runtime_sources']), source_files | set(subject.PROVENANCE_FILES))
        self.assertIn('dependencies/pyuca/allkeys-10.0.0.txt', manifest['files'])
        self.assertIn('dependencies/tzdata/zoneinfo/Europe/Moscow', manifest['files'])
        self.assertEqual(manifest['dependencies'], subject.DEPENDENCIES)
        self.assertEqual(subject.runtime_identity(actual)['bundle_manifest_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertLess(len(json.dumps(actual)), 16000)

    def test_clean_child_imports_only_staged_runtime_and_dependencies(self):
        code = '''import sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import metadata_catalog_runtime_inputs as bundle
bundle.verify_inputs(root,sys.argv[2]);identity=bundle.activate_runtime(root)
import yadinassi,pyuca,tzdata,prompt_toolkit,wcwidth
for module in (yadinassi,pyuca,tzdata,prompt_toolkit,wcwidth):
    assert Path(module.__file__).is_relative_to(root), module.__file__
assert yadinassi.Interpreter().execute('20 + 22') == 42
print(json.dumps(identity,sort_keys=True))
'''
        run = subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.staged),self.nonce],
                             capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout),subject.runtime_identity(self.provenance))

    def test_cold_no_site_public_adapter_same_config_image(self):
        from test_catalog_metadata_reader import image
        from test_metadata_catalog_runtime_replay import native_wire, CAPTURE
        value=image(names=('NativeOracleItems',))
        native=native_wire(json.loads(CAPTURE.read_bytes())[0]['rows'])
        with tempfile.TemporaryDirectory() as directory:
            database=Path(directory).resolve()
            path=database/'1Cv8.1CD'
            original=value.read_at(0,value.size);path.write_bytes(original)
            (database/'native.out').write_bytes(native)
            code = """import sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import metadata_catalog_runtime_inputs as bundle
bundle.verify_inputs(root,sys.argv[2]);bundle.activate_runtime(root)
import metadata_catalog_runtime_readback as readback
result=readback.readback(Path(sys.argv[3]),native_wire=(Path(sys.argv[3])/'native.out').read_bytes())
print(json.dumps(result['comparison'],sort_keys=True))
"""
            run=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(self.staged),
                self.nonce,str(database)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(path.read_bytes(),original)
        comparison=json.loads(run.stdout)
        self.assertTrue(comparison['supported_match'])
        self.assertEqual(len(comparison['matched_ids']),24)
        self.assertEqual(comparison['mismatched_ids'],[])
        self.assertEqual([r['runtime_status'] for r in comparison['excluded_controls']],
                         ['action-error','action-error'])

    def test_tampered_uca_rejected(self):
        path=self.staged/'dependencies/pyuca/allkeys-10.0.0.txt'
        raw=path.read_bytes()
        try:
            path.chmod(0o644);path.write_bytes(raw+b'\n')
            with self.assertRaises(OracleError):subject.verify_inputs(self.staged,self.nonce)
        finally:path.write_bytes(raw);path.chmod(0o444)

    def test_unlisted_file_rejected(self):
        path=self.staged/'dependencies/extra.py'
        try:
            path.write_text('pass')
            with self.assertRaises(OracleError):subject.verify_inputs(self.staged,self.nonce)
        finally:path.unlink()

    def test_symlink_rejected(self):
        path=self.staged/'dependencies/extra.py'
        try:
            try:
                path.symlink_to(self.staged/'yadinassi/__init__.py')
            except NotImplementedError:
                self.skipTest('symlink creation is unavailable')
            except OSError as error:
                unavailable = (errno.EPERM, errno.EACCES, errno.ENOSYS,
                               getattr(errno, 'EOPNOTSUPP', errno.ENOSYS))
                if error.errno in unavailable or getattr(error, 'winerror', None) == 1314:
                    self.skipTest('symlink creation privilege or filesystem support is unavailable')
                raise
            with self.assertRaises(OracleError):subject.verify_inputs(self.staged,self.nonce)
        finally:path.unlink(missing_ok=True)

    def test_missing_symlink_capability_does_not_skip_other_inventory_checks(self):
        case=RuntimeBundleTests('test_symlink_rejected')
        with mock.patch.object(Path, 'symlink_to', side_effect=OSError(errno.EPERM, 'unavailable')):
            with self.assertRaises(unittest.SkipTest):case.test_symlink_rejected()
            # Ordinary unlisted-file rejection still executes on this host.
            self.test_unlisted_file_rejected()
        with mock.patch.object(Path, 'symlink_to', side_effect=OSError(errno.EIO, 'unexpected IO')):
            with self.assertRaises(OSError):case.test_symlink_rejected()

    def test_changed_manifest_nonce_and_provenance_rejected(self):
        with self.assertRaises(OracleError):subject.verify_inputs(self.staged,'d'*32)
        bad=dict(self.provenance,sources={})
        with self.assertRaises(OracleError):subject.validate_source_identity(bad)
        path=self.staged/subject.MANIFEST;raw=path.read_bytes()
        try:
            value=json.loads(raw);value['dependencies']['pyuca']='0'
            path.chmod(0o644);path.write_bytes(subject._json(value))
            with self.assertRaises(OracleError):subject.verify_inputs(self.staged,self.nonce)
        finally:path.write_bytes(raw);path.chmod(0o444)

    def test_runtime_preimport_is_rejected(self):
        with mock.patch.dict(sys.modules,{'pyuca':object()}):
            with self.assertRaises(OracleError):subject.activate_runtime(self.staged)

    def test_source_file_count_and_depth_rejected_before_materialization(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();package=root/'yadinassi';package.mkdir()
            for i in range(513): (package/f'file{i}.py').write_text('')
            with self.assertRaises(OracleError):subject._source_runtime(root)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/'yadinassi';path.mkdir()
            for i in range(subject.MAX_DEPTH + 1):
                path=path/'deep';path.mkdir()
            with self.assertRaises(OracleError):subject._source_runtime(root)

    def test_unknown_staged_directory_rejected_before_descent(self):
        unknown=self.staged/'unknown';unknown.mkdir()
        original=subject.os.scandir
        def bounded(path):
            if Path(path) == unknown: raise AssertionError('descended into unknown directory')
            return original(path)
        try:
            with mock.patch.object(subject.os,'scandir',side_effect=bounded):
                with self.assertRaises(OracleError):subject.staged_hashes(self.staged)
        finally:unknown.rmdir()

    def test_cache_directory_skipped_without_descent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();cache=root/'__pycache__';cache.mkdir()
            (cache/'untrusted.py').write_text('not inspected')
            original=subject.os.scandir
            def bounded(path):
                if Path(path) == cache: raise AssertionError('descended into cache directory')
                return original(path)
            with mock.patch.object(subject.os,'scandir',side_effect=bounded):
                self.assertEqual(list(subject._walk(root,max_files=1,max_directories=1,skip_cache=True)),[])

    def dependency_fixture(self, record, *, metadata=None, payloads=None):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name).resolve();info=root/'prompt_toolkit-3.0.53.dist-info';info.mkdir()
        metadata = b'Name: prompt_toolkit\nVersion: 3.0.53\n\n' if metadata is None else metadata
        (info/'METADATA').write_bytes(metadata)
        (info/'RECORD').write_bytes(record)
        for name,raw in (payloads or {}).items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        distribution=mock.Mock()
        for name in ('files','metadata','version'):
            setattr(type(distribution),name,mock.PropertyMock(side_effect=AssertionError('eager metadata API used')))
        distribution.locate_file.side_effect=lambda name: root if name == '' else self.fail('untrusted locator call')
        self.last_distribution=distribution
        with mock.patch.object(subject,'DEPENDENCIES',{'prompt-toolkit':'3.0.53'}), \
             mock.patch.object(subject.importlib.metadata,'distribution',return_value=distribution):
            return subject._dependencies()

    def valid_record_prefix(self):
        import base64
        raw=b'Name: prompt_toolkit\nVersion: 3.0.53\n\n'
        digest=base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        return (f'prompt_toolkit-3.0.53.dist-info/METADATA,sha256={digest},{len(raw)}\n'
                'prompt_toolkit-3.0.53.dist-info/RECORD,,\n').encode()

    def test_private_direct_url_never_read_or_bundled(self):
        # No private file exists: success proves its payload is never read/stat'ed.
        record=self.valid_record_prefix()+b'prompt_toolkit-3.0.53.dist-info/direct_url.json,,\n'
        files=self.dependency_fixture(record)
        self.assertFalse(any(Path(name).name in subject.PRIVATE_INSTALLER_FILES for name in files))
        self.last_distribution.locate_file.assert_called_once_with('')

    def test_pth_and_outside_distribution_paths_rejected_before_payload_read(self):
        for name in ('prompt_toolkit/inject.pth', 'prompt_toolkit-3.0.53.dist-info/inject.pth',
                     '../outside.py', 'outsideroot/module.py'):
            with self.subTest(name=name), mock.patch.object(subject,'_read',wraps=subject._read) as read:
                with self.assertRaises(OracleError):self.dependency_fixture((name+',,\n').encode())
                self.last_distribution.locate_file.assert_called_once_with('')
                self.assertEqual([call.args[0].name for call in read.call_args_list],['METADATA','RECORD'])

    def test_record_size_line_and_all_rows_bounded_including_skipped(self):
        for raw in (b'x'*(subject.MAX_RECORD_BYTES+1),
                    b'x'*(subject.MAX_RECORD_LINE+1)+b'\n',
                    b''.join(f'prompt_toolkit/__pycache__/x{i}.pyc,,\n'.encode()
                             for i in range(subject.MAX_RECORD_ROWS+1))):
            with self.subTest(length=len(raw)):
                with self.assertRaises(OracleError):self.dependency_fixture(raw)
                self.last_distribution.locate_file.assert_called_once_with('')

    def test_dependency_version_metadata_limit_uniqueness_and_bad_record_hash(self):
        for metadata in (b'Name: prompt_toolkit\nVersion: 0\n',
                         b'Name: prompt_toolkit\nVersion: 3.0.53\nVersion: 3.0.53\n',
                         b'Name: wrong\nVersion: 3.0.53\n',
                         b'Name: prompt_toolkit\nName: prompt_toolkit\nVersion: 3.0.53\n',
                         b'X'*(subject.MAX_METADATA_BYTES+1)):
            with self.subTest(length=len(metadata)):
                with self.assertRaises(OracleError):self.dependency_fixture(b'',metadata=metadata)
        bad=('prompt_toolkit/__init__.py,sha256='+'A'*43+',4\n').encode()
        with self.assertRaises(OracleError):
            self.dependency_fixture(bad,payloads={'prompt_toolkit/__init__.py':b'pass'})


if __name__ == '__main__':unittest.main()
