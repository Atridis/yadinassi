from contextlib import redirect_stdout, redirect_stderr, contextmanager
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from yadinassi import cli
from yadinassi.cli import main
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_import import load_configuration_directory
from sqlite_catalog_fixture import configuration_files

# Test-only failure localization. Never print exception text, paths or arguments.
_PHASES = frozenset({'import', 'create', 'close'})
_CODES = frozenset({'unsupported', 'invalid_input', 'not_found', 'conflict',
    'busy', 'closed', 'integrity', 'storage_error', 'uncertain_commit',
    'schema_changed', 'duplicate_code', 'duplicate_identity'})
_REASONS = frozenset({'invalid configuration directory',
    'unexpected system directory alias', 'directory depth bound',
    'directory aliases unsupported', 'configuration source unavailable',
    'configuration directory bound', 'configuration directory entry bound',
    'unsafe configuration path', 'configuration reparse point unsupported',
    'unsupported configuration file', 'configuration file bound',
    'configuration source changed'})
_ERRNOS = frozenset({1, 2, 5, 9, 13, 16, 17, 20, 22, 28, 30})


def _diagnostic_call(records, phase, operation, *args, **kwargs):
    if phase not in _PHASES:
        raise AssertionError('unknown diagnostic phase')
    try:
        return operation(*args, **kwargs)
    except (BackendError, ValueError, OSError) as error:
        family, code, errno = 'unknown', 'unknown', None
        if type(error) is BackendError:
            family = 'BackendError'
            candidate = error.__dict__.get('code')
            if type(candidate) is str and candidate in _CODES:
                code = candidate
        elif type(error) is ValueError:
            family = 'ValueError'
            values = error.args
            if type(values) is tuple and len(values) == 1:
                candidate = values[0]
                if type(candidate) is str and candidate in _REASONS:
                    code = candidate
        elif type(error) in (OSError, PermissionError, FileNotFoundError,
                             FileExistsError, NotADirectoryError, IsADirectoryError):
            family = 'OSError'
            candidate = error.errno
            if type(candidate) is int and candidate in _ERRNOS:
                errno = candidate
        if len(records) < 3:
            records.append((phase, family, code, errno))
        raise


@contextmanager
def _creation_diagnostics(records):
    import yadinassi.configuration_import as reader
    original_import = reader.load_configuration_directory
    original_create = cli.SQLiteDBContext.create
    original_close = cli.SQLiteDBContext.close
    with mock.patch.object(reader, 'load_configuration_directory',
            side_effect=lambda *a, **k: _diagnostic_call(records, 'import', original_import, *a, **k)), \
         mock.patch.object(cli.SQLiteDBContext, 'create',
            side_effect=lambda *a, **k: _diagnostic_call(records, 'create', original_create, *a, **k)), \
         mock.patch.object(cli.SQLiteDBContext, 'close', autospec=True,
            side_effect=lambda *a, **k: _diagnostic_call(records, 'close', original_close, *a, **k)):
        yield


class ConfigurationImportCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'xml';self.source.mkdir();self.database=self.root/'application.sqlite'
        for path,content in configuration_files().items():
            target=self.source/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    def tearDown(self):self.temp.cleanup()
    def run_cli(self,args):
        out,err=StringIO(),StringIO();diagnostics=[]
        with _creation_diagnostics(diagnostics),redirect_stdout(out),redirect_stderr(err):result=main(args)
        return result,out.getvalue(),err.getvalue(),tuple(diagnostics)
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
        canonical = str(self.source.resolve())
        # Canonical spelling is not an alias test: Windows may expand 8.3 names.
        with mock.patch.object(reader.os, 'lstat', return_value=directory), mock.patch.object(reader.os.path, 'realpath', return_value=canonical), mock.patch.object(reader.sys, 'platform', 'win32'):
            self.assertEqual(reader._host_directory(self.root/'OWNED~1'), canonical)
        with mock.patch.object(reader.sys, 'platform', 'darwin'), mock.patch.object(reader, 'Path', PurePosixPath), mock.patch.object(reader.os.path, 'abspath', posixpath.abspath), mock.patch.object(reader.os, 'lstat', return_value=directory), mock.patch.object(reader.os.path, 'realpath', side_effect=lambda p: '/private/var' if str(p) == '/var' else str(p)):
            self.assertEqual(reader._host_directory('/var/folders/owned'), '/private/var/folders/owned')
        with mock.patch.object(reader.sys, 'platform', 'darwin'), mock.patch.object(reader, 'Path', PurePosixPath), mock.patch.object(reader.os.path, 'abspath', posixpath.abspath), mock.patch.object(reader.os.path, 'realpath', return_value='/unexpected'):
            with self.assertRaisesRegex(ValueError, 'unexpected system'):
                reader._host_directory('/var/folders/owned')
        for mode, attributes in ((stat.S_IFLNK | 0o777, 0), (stat.S_IFDIR | 0o700, 0x400)):
            with self.subTest(mode=mode, attributes=attributes), mock.patch.object(reader.sys, 'platform', 'linux'), mock.patch.object(reader.os, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_file_attributes=attributes)):
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

    def test_diagnostic_phases_preserve_exception_identity_and_single_call(self):
        for phase, error, expected in (
            ('import', ValueError('configuration source changed'), ('ValueError', 'configuration source changed', None)),
            ('create', BackendError('storage_error'), ('BackendError', 'storage_error', None)),
            ('close', OSError(13, 'PRIVATE error', '/PRIVATE/path'), ('OSError', 'unknown', 13)),
        ):
            with self.subTest(phase=phase):
                records=[];operation=mock.Mock(side_effect=error)
                with self.assertRaises(type(error)) as caught:
                    _diagnostic_call(records, phase, operation)
                self.assertIs(caught.exception,error)
                operation.assert_called_once_with()
                self.assertEqual(records,[(phase,*expected)])

    def test_diagnostic_unknown_values_are_private_and_bounded(self):
        class Hostile(ValueError):
            def __str__(self):raise AssertionError('exception text accessed')
            def __getattribute__(self,name):
                if name in ('args','code','errno'):raise AssertionError('subclass hook accessed')
                return super().__getattribute__(name)
        records=[]
        for error in (Hostile('PRIVATE'),ValueError('/PRIVATE/path'),OSError(9999,'PRIVATE','/PRIVATE')):
            with self.assertRaises(type(error)):
                _diagnostic_call(records,'import',mock.Mock(side_effect=error))
        self.assertNotIn('PRIVATE',repr(records))
        self.assertEqual(records,[('import','unknown','unknown',None),
            ('import','ValueError','unknown',None),('import','OSError','unknown',None)])
        with self.assertRaises(ValueError):
            _diagnostic_call(records,'import',mock.Mock(side_effect=ValueError('PRIVATE')))
        self.assertEqual(len(records),3)

    def test_diagnostic_scope_restores_methods_and_cli_failure(self):
        import yadinassi.configuration_import as reader
        original_import=reader.load_configuration_directory
        original_create=cli.SQLiteDBContext.create.__func__
        original_close=cli.SQLiteDBContext.close
        error=ValueError('configuration source unavailable')
        with mock.patch.object(reader,'load_configuration_directory',side_effect=error) as failed:
            result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source)])
            failed.assert_called_once()
        self.assertEqual(result,(1,'','yadinassi: configuration import refused: code=source_unavailable; stage=schema\n',
            (('import','ValueError','configuration source unavailable',None),)))
        self.assertIs(reader.load_configuration_directory,original_import)
        self.assertIs(cli.SQLiteDBContext.create.__func__,original_create)
        self.assertIs(cli.SQLiteDBContext.close,original_close)
        self.assertFalse(self.database.exists())
