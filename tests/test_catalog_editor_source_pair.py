"""Fresh coherent source-pair reads, not cached execution authority."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_imported_product_editor as fixture
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogBackend


class SourcePairTests(unittest.TestCase):
    setUp = fixture.ImportedProductEditorTests.setUp

    def test_pair_matches_old_apis_and_verifies_once_per_call(self):
        backend = self.app.backend
        identity = self.editor.schema.identity
        form = backend.read_form_source(identity)
        policy = backend.catalog_write_preparation(identity, expected=form.identity)
        with patch.object(backend, '_demo_source_snapshot', wraps=backend._demo_source_snapshot) as read:
            self.assertEqual(backend.read_catalog_editor_source(identity), (form, policy))
            self.assertEqual(read.call_count, 1)
            self.assertEqual(backend.read_catalog_editor_source(identity, expected=form.identity), (form, policy))
            self.assertEqual(read.call_count, 2)
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            backend.read_catalog_editor_source(identity, expected=replace(form.identity, database_id=uuid4()))
        with self.assertRaisesRegex(BackendError, 'invalid_input'):
            backend.read_catalog_editor_source(identity, expected=object())

    def test_old_form_reader_does_not_request_write_policy(self):
        with patch.object(self.app.backend, 'catalog_write_preparation', side_effect=AssertionError):
            self.assertIsNotNone(self.app.backend.read_form_source(self.editor.schema.identity))

    def test_policy_change_invalidates_editor(self):
        with patch.object(self.app.backend, 'read_catalog_editor_source',
                          return_value=(self.editor._source_record, 'changed')):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                self.editor._verify_source()
        self.assertTrue(self.editor._source_stale)

    def test_custom_backend_does_not_synthesize_unverified_pair(self):
        class Custom(CatalogBackend):
            def read_form_source(self, *args, **kwargs):
                raise AssertionError('must not fall back')
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            Custom().read_catalog_editor_source(uuid4())

class OtherProfilePairTests(unittest.TestCase):
    def test_main_demo_pair_and_ddl_recheck(self):
        import test_main_demo_host as main
        f = main.MainDemoHostTests(); f.setUp(); self.addCleanup(f.doCleanups)
        backend = f.host.owner.backend
        identity = next(c.identity for c in f.config.catalogs if c.name == 'Номенклатура')
        form = backend.read_form_source(identity)
        policy = backend.catalog_write_preparation(identity, expected=form.identity)
        with patch.object(backend, '_main_demo_source_snapshot', wraps=backend._main_demo_source_snapshot) as read:
            self.assertEqual(backend.read_catalog_editor_source(identity), (form, policy))
            self.assertEqual(read.call_count, 1)
        with patch('yadinassi.db.sqlite.sqlite_main_demo_profile.validate_main_demo_ddl', side_effect=BackendError('schema_changed')):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                backend.read_catalog_editor_source(identity)

    def test_inert_policy_none_and_fresh_source_drift(self):
        import test_inert_configuration_sources as inert
        f = inert.InertSourceStorageTests(); f.setUp(); self.addCleanup(f.doCleanups)
        form = f.backend.read_form_source(inert.CATALOG)
        self.assertEqual(f.backend.read_catalog_editor_source(inert.CATALOG), (form, None))
        f.change_source(inert.MPATH, f.files[inert.MPATH] + b'// drift')
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            f.backend.read_catalog_editor_source(inert.CATALOG)
