from contextlib import redirect_stdout, redirect_stderr, contextmanager
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi.cli import main
from yadinassi.configuration_import import load_configuration_directory
from sqlite_catalog_fixture import configuration_files

class ConfigurationImportCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'xml';self.source.mkdir();self.database=self.root/'application.sqlite'
        for path,content in configuration_files().items():
            target=self.source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    def tearDown(self):self.temp.cleanup()
    def run_cli(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err):result=main(args)
        return result,out.getvalue(),err.getvalue()
    def test_create_write_reopen_and_plain_script(self):
        self.assertEqual(self.run_cli(['-c','Message(2+3);'])[:2],(0,'5\n'))
        self.assertFalse(self.database.exists())
        result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source)])
        self.assertEqual(result[0],0,result)
        self.assertEqual(self.run_cli(['--f',str(self.database),'-c','O=Catalogs.Products.CreateItem();O.Code="10";O.Text="saved";O.Write();Message(O.IsNew());'])[:2],(0,'Нет\n'))
        self.assertEqual(self.run_cli(['--f',str(self.database),'-c','Message(Catalogs.Products.FindByCode("10").Text);'])[:2],(0,'saved\n'))
    def test_missing_open_and_existing_create_do_not_write(self):
        self.assertEqual(self.run_cli(['--f',str(self.database),'-c','Message(1);'])[0],1)
        self.assertFalse(self.database.exists())
        self.database.write_bytes(b'owned sentinel');before=self.database.read_bytes()
        self.assertEqual(self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source)])[0],1)
        self.assertEqual(self.database.read_bytes(),before)
    def test_inactive_code_archive_does_not_execute(self):
        module=self.source/'Ext/ManagedApplicationModule.bsl';module.parent.mkdir();module.write_text('Message("MUST NOT RUN");',encoding='utf-8')
        result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source),'--inactive'])
        self.assertEqual(result[0],0,result);self.assertNotIn('MUST NOT RUN',result[1]);self.assertIn('Activation issue:',result[1])
        result=self.run_cli(['--f',str(self.database),'-c','Message("MUST NOT RUN");'])
        self.assertEqual(result[0],1);self.assertNotIn('MUST NOT RUN',result[1]+result[2])
    def test_import_rejects_symlink_and_entity_without_creating_database(self):
        target=self.source/'linked.xml'
        try:target.symlink_to(self.source/'Configuration.xml')
        except (OSError,NotImplementedError):self.skipTest('symlink not available')
        with self.assertRaises(ValueError):load_configuration_directory(self.source)
        target.unlink()
        (self.source/'Configuration.xml').write_bytes(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>')
        self.assertEqual(self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source)])[0],1)
        self.assertFalse(self.database.exists())
    def test_creation_flags_are_explicit_exclusive_pair(self):
        for args in (['--create-db',str(self.database)],['--import-xml',str(self.source)],['--inactive'],['--create-db',str(self.database),'--import-xml',str(self.source),'-c','Message(1);']):
            with self.subTest(args=args),redirect_stderr(StringIO()),self.assertRaises(SystemExit) as error:main(args)
            self.assertEqual(error.exception.code,2)
        self.assertFalse(self.database.exists())

    def test_directory_entry_bound_precedes_file_inspection(self):
        import yadinassi.configuration_import as reader
        @contextmanager
        def entries(path):
            # No file methods: overflow must be rejected before any stat/read.
            yield iter([object()] * (reader.MAX_FILES + 1))
        with mock.patch.object(reader.os, 'scandir', entries):
            with self.assertRaisesRegex(ValueError, '^configuration directory entry bound$'):
                reader.load_configuration_directory(self.source)
        self.assertFalse(self.database.exists())

    def test_host_directory_canonical_spelling_and_closed_system_aliases(self):
        import os
        import stat
        from types import SimpleNamespace
        from pathlib import PurePosixPath
        import posixpath
        import yadinassi.configuration_import as reader
        directory = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0)
        # Canonical spelling is not an alias test: Windows may expand 8.3 names.
        with mock.patch.object(reader.os, 'lstat', return_value=directory), mock.patch.object(reader.os.path, 'realpath', return_value=str(self.source.resolve())), mock.patch.object(reader.sys, 'platform', 'win32'):
            self.assertEqual(reader._host_directory(self.root/'OWNED~1'), str(self.source.resolve()))
        with mock.patch.object(reader.sys, 'platform', 'darwin'), mock.patch.object(reader, 'Path', PurePosixPath), mock.patch.object(reader.os.path, 'abspath', posixpath.abspath), mock.patch.object(reader.os, 'lstat', return_value=directory), mock.patch.object(reader.os.path, 'realpath', side_effect=lambda p: '/private/var' if str(p) == '/var' else str(p)):
            self.assertEqual(reader._host_directory('/var/folders/owned'), '/private/var/folders/owned')
        with mock.patch.object(reader.sys, 'platform', 'darwin'), mock.patch.object(reader, 'Path', PurePosixPath), mock.patch.object(reader.os.path, 'abspath', posixpath.abspath), mock.patch.object(reader.os.path, 'realpath', return_value='/unexpected'):
            with self.assertRaisesRegex(ValueError, 'unexpected system'):
                reader._host_directory('/var/folders/owned')
        for mode, attributes in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFDIR | 0o700, 0x400)):
            with self.subTest(mode=mode, attributes=attributes), mock.patch.object(reader.os, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_file_attributes=attributes)):
                with self.assertRaisesRegex(ValueError, 'aliases unsupported'):
                    reader._host_directory(self.source)

    def test_fresh_stat_not_windows_direntry_identity_cache(self):
        import os
        import yadinassi.configuration_import as reader
        real_scandir = os.scandir
        class Entry:
            def __init__(self, entry):self.path=entry.path;self.name=entry.name
            def stat(self, **kwargs):raise AssertionError('DirEntry identity is not portable')
        @contextmanager
        def scan(path):
            with real_scandir(path) as iterator:
                yield iter([Entry(entry) for entry in iterator])
        with mock.patch.object(reader.os, 'scandir', scan):
            self.assertEqual(reader.load_configuration_directory(self.source).name, 'OwnedApplication')

    def test_directory_symlink_and_file_hardlink_remain_refused(self):
        import os
        linked=self.root/'alias'
        try:linked.symlink_to(self.source, target_is_directory=True)
        except (OSError,NotImplementedError):pass
        else:
            with self.assertRaisesRegex(ValueError,'aliases unsupported'):
                load_configuration_directory(linked)
            linked.unlink()
        try:os.link(self.source/'Configuration.xml', self.source/'hardlink.xml')
        except (OSError,NotImplementedError):self.skipTest('hardlinks unavailable')
        with self.assertRaisesRegex(ValueError,'unsupported configuration file'):
            load_configuration_directory(self.source)
