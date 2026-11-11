from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import cli
from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.configuration_profile_import import LEGACY, POSTING, POSTING_FORMS, ACCUMULATION
from sqlite_catalog_fixture import configuration_files
from test_configuration_posting import source as posting_source
from test_configuration_accumulation import source as accumulation_source
from posting_application_fixture import source as forms_source

ROOT=Path(__file__).resolve().parents[1]


class ConfigurationProfileCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.database=self.root/'application.sqlite'

    def write(self,files):
        for name,raw in files.items():
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

    def run_cli(self,args):
        out=StringIO();err=StringIO()
        with redirect_stdout(out),redirect_stderr(err):code=cli.main(args)
        return code,out.getvalue(),err.getvalue()

    def test_check_json_is_read_only(self):
        self.write(accumulation_source())
        result=self.run_cli(['--check-xml',str(self.source),'--source-profile',ACCUMULATION,'--report-json'])
        self.assertEqual(result[0],0,result);report=json.loads(result[1])
        self.assertEqual(report['profile'],ACCUMULATION);self.assertTrue(report['ready'])
        self.assertEqual(list(self.root.iterdir()),[self.source])
        self.assertEqual(result[2],'')

    def test_check_plain_human_summary(self):
        self.write(configuration_files())
        result=self.run_cli(['--check-xml',str(self.source)])
        self.assertEqual(result[0],0,result);self.assertIn('preflight ready: legacy',result[1])
        self.assertFalse(self.database.exists())

    def test_cli_create_each_explicit_profile(self):
        for index,(profile,source) in enumerate(((LEGACY,configuration_files),(POSTING,posting_source),(POSTING_FORMS,forms_source),(ACCUMULATION,accumulation_source))):
            with self.subTest(profile=profile):
                self.source=self.root/('source'+str(index));self.source.mkdir();files=source();self.write(files)
                path=self.root/('database'+str(index)+'.sqlite')
                result=self.run_cli(['--create-db',str(path),'--import-xml',str(self.source),'--source-profile',profile])
                self.assertEqual(result,(0,'Created SQLite database.\n',''))
                with SQLiteDBContext(path) as context:
                    self.assertEqual(context.backend.format_version,2 if profile==LEGACY else 14 if profile==ACCUMULATION else 13)
                    self.assertEqual(context.backend.export_configuration(),files)

    def test_wrong_profile_failure_has_no_destination(self):
        self.write(accumulation_source())
        result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source),'--source-profile',POSTING])
        self.assertEqual(result[0],1);self.assertIn('configuration import refused',result[2]);self.assertFalse(self.database.exists())

    def test_error_report_json_has_no_raw_source_or_host_path(self):
        self.write({'Configuration.xml':b'<PRIVATE_SECRET'})
        result=self.run_cli(['--check-xml',str(self.source),'--report-json'])
        self.assertEqual(result[0],1);report=json.loads(result[1]);self.assertFalse(report['ready'])
        self.assertEqual(report['diagnostics'][0]['file'],'Configuration.xml')
        self.assertNotIn(str(self.root),result[1]);self.assertNotIn('PRIVATE_SECRET',result[1]);self.assertEqual(result[2],'')

    def test_create_refusal_explains_safe_reason(self):
        self.write({'Configuration.xml':b'<!DOCTYPE x><x/>'})
        result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source)])
        self.assertEqual(result[0],1);self.assertIn('code=xml_dtd_forbidden',result[2])
        self.assertIn('file=Configuration.xml',result[2]);self.assertFalse(self.database.exists())

    def test_check_never_executes_stored_initializer(self):
        files=configuration_files();files['Ext/ManagedApplicationModule.bsl']=b'Message("SECRET INITIALIZER");'
        self.write(files)
        result=self.run_cli(['--check-xml',str(self.source),'--report-json'])
        self.assertEqual(result[0],1);self.assertNotIn('SECRET INITIALIZER',result[1]+result[2])
        self.assertTrue(all(d['stage']=='activation' for d in json.loads(result[1])['diagnostics']))
        inactive=self.run_cli(['--check-xml',str(self.source),'--inactive','--report-json'])
        self.assertEqual(inactive[0],0);self.assertFalse(json.loads(inactive[1])['activated'])

    def test_exclusive_flags_cannot_mix_check_execution_creation_or_demo(self):
        base=['--check-xml',str(self.source)]
        for suffix in (['-c','Message(1);'],['--f',str(self.database)],['--create-db',str(self.database)],
                       ['--import-xml',str(self.source)],['--create-demo-db',str(self.database)]):
            with self.subTest(suffix=suffix),redirect_stderr(StringIO()),self.assertRaises(SystemExit) as caught:
                cli.main(base+suffix)
            self.assertEqual(caught.exception.code,2)
        self.assertFalse(self.database.exists())

    def test_profile_and_json_options_require_import_actions(self):
        for args in (['--source-profile',POSTING],['--report-json'],['--source-profile',POSTING,'-c','Message(1);']):
            with self.subTest(args=args),redirect_stderr(StringIO()),self.assertRaises(SystemExit) as caught:cli.main(args)
            self.assertEqual(caught.exception.code,2)

    def test_profile_inactive_rejected_without_creation(self):
        self.write(posting_source())
        result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source),'--source-profile',POSTING,'--inactive'])
        self.assertEqual(result[0],1);self.assertIn('profile_options_unsupported',result[2]);self.assertFalse(self.database.exists())

    def test_uncertain_creation_keeps_existing_recovery_message(self):
        self.write(posting_source())
        with patch.object(SQLiteDBContext,'create_posting',side_effect=BackendError('uncertain_commit')):
            result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source),'--source-profile',POSTING])
        self.assertEqual(result[0],1);self.assertIn('outcome uncertain',result[2]);self.assertIn('preserve',result[2])
        self.assertNotIn(str(self.root),result[2])

    def test_create_close_failure_is_not_reclassified_as_source_refusal(self):
        self.write(configuration_files())
        class Context:
            def close(self):raise BackendError('storage_error')
        with patch.object(SQLiteDBContext,'create',return_value=Context()):
            result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source)])
        self.assertEqual(result[0],1);self.assertIn('preserve and inspect',result[2]);self.assertNotIn('import refused',result[2])

    def test_missing_source_directory_uses_safe_read_reason(self):
        result=self.run_cli(['--check-xml',str(self.root/'absent'),'--report-json'])
        self.assertEqual(result[0],1);diagnostic=json.loads(result[1])['diagnostics'][0]
        self.assertEqual((diagnostic['code'],diagnostic['stage']),('source_unavailable','read'))
        self.assertNotIn(str(self.root),result[1])

    def test_existing_destination_not_overwritten_through_cli(self):
        self.write(accumulation_source());self.database.write_bytes(b'owned sentinel')
        result=self.run_cli(['--create-db',str(self.database),'--import-xml',str(self.source),'--source-profile',ACCUMULATION])
        self.assertEqual(result[0],1);self.assertEqual(self.database.read_bytes(),b'owned sentinel')
