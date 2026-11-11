"""Prepared imports never replace live byte, profile or schema admission."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from business_configuration_fixture import sources
from yadinassi.catalog_backend import BackendError
from yadinassi.catalogs import BSLCatalogs
from yadinassi.database_context import SQLiteDBContext
from yadinassi.metadata import BSLCatalogMetadataCollection
from yadinassi.prepared_source import PreparedSource
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class PreparedSourceTests(unittest.TestCase):
    def test_fixed_positive_entry_is_not_replaced_by_an_unadmitted_candidate(self):
        cache = PreparedSource(); first = ('admitted',)
        self.assertIsNone(cache.lookup(('one',)))
        cache.remember(('one',), first)
        cache.remember(('two',), ('different candidate',))
        self.assertIs(cache.lookup(('one',)), first)
        self.assertIsNone(cache.lookup(('two',)))
        cache.clear(); self.assertIsNone(cache.lookup(('one',)))

    def test_no_negative_result_or_mutable_key(self):
        cache = PreparedSource()
        for key, value in (([], ()), ((), None)):
            with self.assertRaises(TypeError): cache.remember(key, value)
        self.assertIsNone(cache.lookup(()))


class PreparedBusinessAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)/'business.sqlite'; self.files = sources()
        self.backend = SQLiteCatalogBackend.create_business_application(self.path, self.files)
        self.addCleanup(self.backend.close)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(sql, args); connection.commit()

    def test_ten_saved_scalar_reads_do_not_reimport_or_compile(self):
        context = SQLiteDBContext(self.path); self.addCleanup(context.close)
        manager = BSLCatalogs(BSLCatalogMetadataCollection(context), context).get_index('Items')
        obj = manager.create_item(); obj.set_member('Code', '1'); obj.set_member('Description', 'kept'); obj.write()
        reference = obj.get_member('Ref')
        with patch('yadinassi.configuration_business_profile.business_configuration') as importer, \
                patch('yadinassi.configuration_forms.compile_form_module') as compiler:
            for _ in range(10): self.assertEqual(reference.get_member('Description'), 'kept')
            importer.assert_not_called(); compiler.assert_not_called()

    def test_reads_exports_and_form_preparation_reuse_positive_import(self):
        from test_configuration_catalog_profile import CATALOG
        with patch('yadinassi.configuration_business_profile.business_configuration') as importer:
            for _ in range(3):
                with closing(self.backend.begin_read()) as view: self.assertEqual(len(view.catalogs()), 1)
                with closing(self.backend.begin_document_read()) as view: self.assertEqual(len(view.documents()), 1)
                self.assertEqual(self.backend.export_configuration(), self.files)
                self.assertEqual(self.backend.read_form_source(CATALOG).identity.database_id, self.backend.database_id)
            importer.assert_not_called()

    def test_each_backend_reimports_and_does_not_share_positive_state(self):
        from yadinassi.configuration_business_profile import business_configuration
        with patch('yadinassi.configuration_business_profile.business_configuration', wraps=business_configuration) as importer:
            with closing(SQLiteCatalogBackend(self.path)) as second:
                self.assertEqual(importer.call_count, 1)
                self.assertIsNot(second._prepared_source, self.backend._prepared_source)
                with closing(second.begin_read()): pass
                self.assertEqual(importer.call_count, 1)

    def test_close_clears_retained_configuration(self):
        self.assertIsNotNone(self.backend._prepared_source._entry)
        self.backend.close(); self.assertIsNone(self.backend._prepared_source._entry)
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_actual_content_is_still_hashed_on_each_begin(self):
        self.mutate("UPDATE configuration_file SET content=x'00' WHERE path='Configuration.xml'")
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_stored_digest_is_not_an_authority(self):
        self.mutate("UPDATE configuration_file SET sha256=? WHERE path='Configuration.xml'", ('0'*64,))
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_rehashed_changed_source_same_generation_is_refused(self):
        path = 'CommonModules/Tools/Ext/Module.bsl'; raw = self.files[path]+b'\n// changed'
        old = self.backend._prepared_source._entry
        self.mutate('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (raw, sha256(raw).hexdigest(), path))
        with self.assertRaises(BackendError): self.backend.begin_read()
        self.assertIs(self.backend._prepared_source._entry, old)
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_generation_change_is_not_hidden_by_cached_source(self):
        self.mutate('UPDATE database_info SET generation=generation+1')
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_profile_change_is_refused_before_reuse(self):
        self.mutate("UPDATE database_info SET activation_issues='[]'")
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_metadata_change_same_source_is_refused(self):
        self.mutate("UPDATE catalog_schema SET name='Altered'")
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_sql_schema_change_is_refused(self):
        self.mutate('ALTER TABLE document_record ADD COLUMN unexpected TEXT')
        with self.assertRaises(BackendError): self.backend.begin_read()

    def test_failed_import_is_not_published(self):
        self.backend._prepared_source.clear()
        with patch('yadinassi.configuration_business_profile.business_configuration', side_effect=ValueError('refused')):
            with self.assertRaises(BackendError): self.backend.begin_read()
        self.assertIsNone(self.backend._prepared_source._entry)
        with closing(self.backend.begin_read()): pass
        self.assertIsNotNone(self.backend._prepared_source._entry)

    def test_interrupted_import_is_not_published(self):
        self.backend._prepared_source.clear()
        with patch('yadinassi.configuration_business_profile.business_configuration', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.backend.begin_read()
        self.assertIsNone(self.backend._prepared_source._entry)
        with closing(self.backend.begin_read()): pass

    def test_failed_schema_admission_does_not_publish_parsed_candidate(self):
        self.backend._prepared_source.clear()
        self.mutate("UPDATE catalog_schema SET name='Altered'")
        with self.assertRaises(BackendError): self.backend.export_configuration()
        self.assertIsNone(self.backend._prepared_source._entry)


class PreparedProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)/'profile.sqlite'

    def assert_profile_reused(self, create, files, target):
        backend = create(self.path, files); self.addCleanup(backend.close)
        with patch(target) as importer, patch('yadinassi.configuration_forms.compile_form_module') as compiler:
            for _ in range(3):
                with closing(backend.begin_read()): pass
                self.assertEqual(backend.export_configuration(), files)
            importer.assert_not_called(); compiler.assert_not_called()

    def test_reference_profile_retains_typed_grant(self):
        from test_configuration_reference_profile import sources as reference_sources
        self.assert_profile_reused(SQLiteCatalogBackend.create_reference_application, reference_sources(),
            'yadinassi.configuration_reference_profile.reference_configuration')

    def test_document_form_profile_reuses_admission(self):
        from document_form_fixture import sources as document_sources
        self.assert_profile_reused(SQLiteCatalogBackend.create_document_forms, document_sources(),
            'yadinassi.configuration_document_profile.import_document_forms_configuration')

    def test_catalog_form_profile_reuses_admission(self):
        from test_configuration_catalog_profile import catalog_form_sources
        self.assert_profile_reused(SQLiteCatalogBackend.create_catalog_forms, catalog_form_sources(),
            'yadinassi.configuration_xml._demo_configuration')

    def test_posting_core_reuses_import_not_recorder_validation(self):
        from test_configuration_posting import source
        from yadinassi.configuration_posting import import_posting_configuration, PROFILE
        from yadinassi.sqlite_recorder_movements import RecorderMovementPort
        config = import_posting_configuration(source(), posting_runtime=PROFILE)
        backend = SQLiteCatalogBackend.create_posting(self.path, config); self.addCleanup(backend.close)
        with patch('yadinassi.sqlite_posting_profile.import_variant') as importer:
            for _ in range(3):
                with closing(backend.begin_read()): pass
            importer.assert_not_called()
        with patch.object(RecorderMovementPort, '_require', side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError): backend.begin_read()

    def test_posting_forms_reuse_full_variant_not_core_projection(self):
        from posting_application_fixture import source
        from yadinassi.configuration_posting_application import import_posting_application, PROFILE
        files = source(); config = import_posting_application(files, posting_runtime=PROFILE)
        backend = SQLiteCatalogBackend.create_posting(self.path, config); self.addCleanup(backend.close)
        with patch('yadinassi.sqlite_posting_profile.import_variant') as importer, \
                patch('yadinassi.configuration_forms.compile_form_module') as compiler:
            for _ in range(3):
                with closing(backend.begin_read()): pass
            importer.assert_not_called(); compiler.assert_not_called()
        path = 'PostingApplication.xml'; changed = files[path]+b'\n'
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (changed, sha256(changed).hexdigest(), path)); db.commit()
        with self.assertRaises(BackendError): backend.begin_read()
        self.assertEqual(backend.posting_configuration.profile, PROFILE)
