"""Packet checkout/locale regressions; no relaxation of native file security."""
import errno
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/native_1c_db_oracle'))
from catalog_read_packet import probe, batch


class CatalogReadPortabilityTests(unittest.TestCase):
    def test_observer_generation_does_not_use_host_ansi_codec(self):
        original = Path.read_text
        calls = []
        def ansi(path, *args, **kwargs):
            calls.append((path.name, kwargs.get('encoding')))
            kwargs.setdefault('encoding', 'cp1252')
            return original(path, *args, **kwargs)
        setup = probe.fresh_setup()
        with mock.patch.object(Path, 'read_text', new=ansi):
            for block in ('identity', 'types', 'errors'):
                self.assertIn('Функция', probe.render(setup, block))
            self.assertIn('Функция', probe.render_fresh(setup))
            self.assertIn('Функция', batch.observer())
            self.assertIn('Функция', batch.render_setup(batch.fresh(), 'one'))
        self.assertTrue(calls)
        self.assertTrue(all(encoding == 'utf-8' for name, encoding in calls if name == 'observer.bsl'))

    @unittest.skipUnless(shutil.which('git'), 'actual autocrlf checkout requires git')
    def test_actual_autocrlf_checkout_preserves_packet_bytes(self):
        packet = Path('scripts/native_1c_db_oracle/catalog_read_packet')
        files = [p.relative_to(ROOT) for p in (ROOT/packet).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); source = root/'source'; source.mkdir()
            for relative in (Path('.gitattributes'), *files):
                target = source/relative; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT/relative).read_bytes())
            def git(*args):
                return subprocess.run(['git', *args], cwd=source, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            git('init', '-q'); git('config', 'core.autocrlf', 'false'); git('add', '.')
            git('-c', 'user.name=Packet checkout test', '-c',
                'user.email=packet-checkout@example.invalid', 'commit', '-qm', 'fixture')
            checkout = root/'checkout'
            git('clone', '-q', '--no-hardlinks', '-c', 'core.autocrlf=true', str(source), str(checkout))
            for relative in files:
                with self.subTest(path=relative):
                    self.assertEqual(hashlib.sha256((checkout/relative).read_bytes()).digest(),
                                     hashlib.sha256((ROOT/relative).read_bytes()).digest())

    def test_windows_static_bundle_bridge_is_scoped_and_cold_child_uses_it(self):
        from types import SimpleNamespace
        import test_catalog_read_native as tests
        original = tests.inputs.runtime._read
        with mock.patch.object(tests, 'os', SimpleNamespace(name='nt')):
            try:
                tests.CatalogStagingTests.setUpClass()
                self.assertIs(tests.inputs.runtime._read, tests.static_bundle_bytes)
                case = tests.CatalogStagingTests('test_isolated_child_import_and_public_runtime')
                result = unittest.TestResult(); case.run(result)
                self.assertEqual(result.errors, [])
                self.assertEqual(result.failures, [])
            finally:
                tests.CatalogStagingTests.doClassCleanups()
        self.assertIs(tests.inputs.runtime._read, original)

    def test_diagnostic_fixture_resolves_indirect_temporary_ancestor(self):
        from test_catalog_read_diagnostics import CatalogReadDiagnosticsTests
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); actual = root/'actual'; actual.mkdir()
            alias = root/'alias'
            try:
                alias.symlink_to(actual, target_is_directory=True)
            except OSError as error:
                if error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP) or getattr(error, 'winerror', None) == 1314:
                    self.skipTest('symlink privilege/capability unavailable')
                raise
            with mock.patch.object(tempfile, 'tempdir', str(alias)):
                case = CatalogReadDiagnosticsTests('test_one_readonly_compile_and_finite_projection')
                result = unittest.TestResult(); case.run(result)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.failures, [])
            self.assertEqual(result.testsRun, 1)

if __name__ == '__main__': unittest.main()
