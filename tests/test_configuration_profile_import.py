"""Host profile selection and no-execution preflight, not new native evidence."""
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.errors import BSLError
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_profile_import import (
    LEGACY, POSTING, POSTING_FORMS, ACCUMULATION, PROFILES,
    prepare_files, prepare_directory, create_prepared,
)
from yadinassi.configuration_diagnostics import ImportRefusal
from yadinassi.database_context import SQLiteDBContext
from yadinassi.configuration_xml import import_configuration
from sqlite_catalog_fixture import configuration_files
from test_configuration_posting import source as posting_source
from test_configuration_accumulation import source as accumulation_source
from posting_application_fixture import source as forms_source

ROOT = Path(__file__).resolve().parents[1]
MODULE = 'Documents/Order/Ext/ObjectModule.bsl'


class ConfigurationProfileImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT.parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def sources(self):
        return ((LEGACY, configuration_files(), 2), (POSTING, posting_source(), 13),
                (POSTING_FORMS, forms_source(), 13), (ACCUMULATION, accumulation_source(), 14))

    def test_four_explicit_profiles_report_without_storage_or_execution(self):
        for profile, files, version in self.sources():
            with self.subTest(profile=profile), ExitStack() as stack:
                stack.enter_context(patch('sqlite3.connect', side_effect=AssertionError('connection')))
                stack.enter_context(patch('os.open', side_effect=AssertionError('file allocation')))
                stack.enter_context(patch.object(Interpreter, 'execute', side_effect=AssertionError('execution')))
                prepared = prepare_files(files, profile=profile)
                report = prepared.report()
                self.assertTrue(report['ready']); self.assertEqual(report['storage_format'], version)
                self.assertEqual(dict(prepared.files), files)
                self.assertEqual(report['source_files'], len(files))
                self.assertNotIn('configuration', report)
                self.assertNotIn('handlers', report)
                self.assertEqual(report['diagnostics'], [])

    def test_creation_reopen_preserves_exact_source_each_profile(self):
        for profile, files, version in self.sources():
            with self.subTest(profile=profile):
                path = self.root / (profile + '.sqlite')
                prepared = prepare_files(files, profile=profile)
                with create_prepared(path, prepared) as context:
                    self.assertEqual(context.backend.format_version, version)
                    self.assertEqual(context.backend.export_configuration(), files)
                with SQLiteDBContext(path) as reopened:
                    self.assertEqual(reopened.backend.export_configuration(), files)

    def test_legacy_default_matches_existing_import(self):
        files = configuration_files()
        result = prepare_files(files)
        self.assertEqual(result.profile, LEGACY)
        self.assertEqual(result.configuration, import_configuration(files))

    def test_wrong_profile_never_falls_back(self):
        for profile, files, _ in self.sources():
            for wrong in PROFILES:
                if wrong == profile: continue
                # Legacy may preserve unsupported families as inactive issues;
                # that is not ready or permission to select another profile.
                with self.subTest(source=profile, selected=wrong):
                    try: prepared = prepare_files(files, profile=wrong)
                    except (ValueError, BackendError): continue
                    self.assertFalse(prepared.report()['ready'])

    def test_profile_options_are_explicit_and_closed(self):
        for profile in (POSTING, POSTING_FORMS, ACCUMULATION):
            for options in ({'activate': False}, {'numbering_policy': 'decimal_v1'},
                            {'module_runtime': 'managed-client-server-v1'}):
                with self.subTest(profile=profile, options=options), self.assertRaises(ImportRefusal):
                    prepare_files({}, profile=profile, **options)
        for profile in ('auto', '', None, True):
            with self.subTest(profile=profile), self.assertRaises(ImportRefusal):
                prepare_files({}, profile=profile)

    def test_preflight_rejects_unknown_extra_source_no_stripping(self):
        for profile, files, _ in self.sources():
            files['Ext/SessionModule.bsl'] = b'Message("private initializer");'
            with self.subTest(profile=profile):
                try: prepared = prepare_files(files, profile=profile)
                except ValueError: continue
                self.assertFalse(prepared.report()['ready'])
                self.assertNotIn('private initializer', str(prepared.report()))

    def test_inactive_legacy_is_archive_not_execution(self):
        files = configuration_files(); files['Ext/ManagedApplicationModule.bsl'] = b'Message("DO NOT RUN");'
        original = import_configuration(files)
        active = prepare_files(files)
        self.assertFalse(active.report()['ready'])
        self.assertEqual(active.configuration.activation_issues, original.activation_issues)
        inactive = prepare_files(files, activate=False)
        self.assertTrue(inactive.report()['ready'])
        self.assertEqual(inactive.configuration.activation_issues, original.activation_issues)
        with create_prepared(self.root/'inactive.sqlite', inactive) as context:
            self.assertFalse(context.backend.activated)
            with self.assertRaises(BackendError): context.require_active()

    def test_blocked_activation_never_allocates_file(self):
        files = configuration_files(); files['Ext/SessionModule.bsl'] = b'Message(1);'
        prepared = prepare_files(files)
        destination = self.root/'refused.sqlite'
        with self.assertRaises(ImportRefusal): create_prepared(destination, prepared)
        self.assertFalse(destination.exists())

    def test_bad_handler_signature_refused_before_create_for_all_posting_profiles(self):
        for profile, files, _ in self.sources()[1:]:
            files[MODULE] = b'Procedure Posting(Cancel) EndProcedure'
            with self.subTest(profile=profile), self.assertRaises(ImportRefusal) as caught:
                prepare_files(files, profile=profile)
            self.assertEqual(caught.exception.diagnostic.code, 'handler_signature_unsupported')
            self.assertEqual(caught.exception.diagnostic.file, MODULE)
            self.assertEqual(caught.exception.diagnostic.stage, 'compile')

    def test_source_snapshot_does_not_reopen_changed_directory(self):
        source = self.root/'source'; source.mkdir()
        files = posting_source()
        for name, raw in files.items():
            p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        prepared = prepare_directory(source, profile=POSTING)
        (source/MODULE).write_bytes(b'PRIVATE BROKEN SOURCE')
        with create_prepared(self.root/'stable.sqlite', prepared) as context:
            self.assertEqual(context.backend.export_configuration(), files)
        with self.assertRaises((ValueError, BSLError)): prepare_directory(source, profile=POSTING)

    def test_prepared_configuration_is_not_a_capability(self):
        good = prepare_files(posting_source(), profile=POSTING)
        forged = replace(good, configuration=object(), diagnostics=(), format_version=14)
        with create_prepared(self.root/'revalidated.sqlite', forged) as context:
            self.assertEqual(context.backend.format_version, 13)
        files = dict(good.files); files[MODULE] = b'Procedure Posting(Cancel) EndProcedure'
        forged = replace(good, files=tuple(files.items()))
        with self.assertRaises(ValueError): create_prepared(self.root/'bad.sqlite', forged)
        self.assertFalse((self.root/'bad.sqlite').exists())

    def test_existing_destination_never_overwritten(self):
        path = self.root/'exists.sqlite';path.write_bytes(b'sentinel')
        prepared = prepare_files(posting_source(), profile=POSTING)
        with self.assertRaises(BackendError): create_prepared(path, prepared)
        self.assertEqual(path.read_bytes(), b'sentinel')

    def test_legacy_crud_through_created_context(self):
        with create_prepared(self.root/'legacy.sqlite', prepare_files(configuration_files())) as context:
            values=[];vm=Interpreter(database_context=context, output=values.append)
            try:
                vm.execute('O=Catalogs.Products.CreateItem();O.Code="1";O.Text="saved";O.Write();Message(Catalogs.Products.FindByCode("1").Text);')
                self.assertEqual(values, ['saved'])
            finally:vm.close()

    def test_posting_repost_unpost_through_created_context(self):
        files=posting_source()
        files[MODULE]=b'Procedure Posting(Cancel,Mode) S=RegisterRecords.Rows;S.Write=True;R=S.Add();R.Key=1;R.Amount=7;EndProcedure'
        with create_prepared(self.root/'posting.sqlite',prepare_files(files,profile=POSTING)) as context:
            values=[];vm=Interpreter(database_context=context,output=values.append)
            try:
                vm.execute('O=Documents.Order.CreateDocument();O.Number="1";O.Date=Date(2024,1,1);O.Write(DocumentWriteMode.Posting);Message(O.Posted);O.Write(DocumentWriteMode.UndoPosting);Message(O.Posted);')
                self.assertEqual(values,['Да','Нет'])
            finally:vm.close()

    def test_accumulation_balance_turnovers_through_created_context(self):
        files=accumulation_source()
        files[MODULE]=b'Procedure Posting(Cancel,Mode) S=RegisterRecords.Rows;S.Write=True;R=S.Add();R.Item="A";R.Amount=7.25;R.Period=Date(2024,1,1);EndProcedure'
        with create_prepared(self.root/'accumulation.sqlite',prepare_files(files,profile=ACCUMULATION)) as context:
            values=[];vm=Interpreter(database_context=context,output=values.append)
            try:
                vm.execute('O=Documents.Order.CreateDocument();O.Number="1";O.Date=Date(2024,1,1);O.Write(DocumentWriteMode.Posting);Q=New Query("SELECT AmountBalance FROM AccumulationRegister.Rows.Balance(&At)");Q.SetParameter("At",Date(2024,1,2));S=Q.Execute().Select();S.Next();Message(S.AmountBalance);Q=New Query("SELECT AmountTurnover FROM AccumulationRegister.Rows.Turnovers(&Start,&Finish)");Q.SetParameter("Start",Date(2024,1,1));Q.SetParameter("Finish",Date(2024,1,1));S=Q.Execute().Select();S.Next();Message(S.AmountTurnover);')
                self.assertEqual(values,['7,25','7,25'])
            finally:vm.close()

    def test_deterministic_storage_budget_checked_before_file_creation(self):
        from yadinassi import sqlite_catalog
        with patch.object(sqlite_catalog, '_MAX_CONFIG_BYTES', 1):
            with self.assertRaises(ValueError): prepare_files(configuration_files())
        from yadinassi import sqlite_documents
        for profile, files, _ in self.sources()[1:]:
            with self.subTest(profile=profile), patch.object(sqlite_documents, '_MAX_TOTAL', 1):
                with self.assertRaises(ImportRefusal) as caught: prepare_files(files, profile=profile)
                self.assertEqual(caught.exception.diagnostic.stage, 'storage')
        self.assertEqual(list(self.root.iterdir()), [])
