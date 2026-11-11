"""Full forms15 preparation stays separate from core15, rows and UI execution."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from inventory_application_fixture import source, MANIFEST, DOC_FORM, DOC_MODULE
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_inventory_application import (
    InventoryApplicationConfiguration, PROFILE, import_inventory_application, validated_core)
from yadinassi.configuration_accumulation_references import PROFILE as CORE_PROFILE
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'yadinassi.configuration_inventory_application.import_inventory_application'


class PreparedInventoryFormsAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'forms.sqlite'
        self.files = source()
        self.config = import_inventory_application(self.files, inventory_runtime=PROFILE)
        self.backend = SQLiteCatalogBackend.create_inventory_application(self.path, self.config)
        self.addCleanup(self.backend.close)

    def read(self):
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(view.database_id, self.backend.database_id)

    def sql(self, statement, values=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(statement, values); db.commit()

    def mutate_source(self, path, raw):
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                 (raw, sha256(raw).hexdigest(), path))

    def assert_refusal_and_repair(self, path, raw):
        entry = self.backend._prepared_source._entry
        self.mutate_source(path, raw)
        with self.assertRaises(BackendError): self.read()
        self.assertIs(self.backend._prepared_source._entry, entry)
        self.mutate_source(path, self.files[path])
        with patch(TARGET) as importer:
            self.read(); importer.assert_not_called()

    def test_twenty_three_snapshots_reuse_full_form_import_and_compilation(self):
        with patch(TARGET) as importer, patch('yadinassi.configuration_forms.compile_form_module') as compiler:
            for _ in range(23): self.read()
            importer.assert_not_called(); compiler.assert_not_called()
        retained = self.backend._prepared_source._entry.value
        self.assertIs(type(retained), InventoryApplicationConfiguration)
        self.assertEqual(dict(retained.files), self.files)
        self.assertEqual(retained.commands, self.config.commands)
        self.assertEqual(retained.reports, self.config.reports)
        self.assertNotEqual(retained.source_digest, retained.core_projection_digest)

    def test_core_projection_in_positive_entry_cannot_authorize_full_variant(self):
        original = self.backend._prepared_source._entry
        self.backend._prepared_source._entry = replace(original, value=validated_core(self.config))
        with self.assertRaises(BackendError): self.read()
        self.backend._prepared_source._entry = original; self.read()

    def test_forms_source_does_not_enter_original_core_creator(self):
        other = self.path.with_name('wrong.sqlite')
        with self.assertRaises(BackendError): SQLiteCatalogBackend.create_inventory(other, self.config)
        self.assertFalse(other.exists())

    def test_full_marker_cannot_be_switched_to_core_with_same_bytes(self):
        self.sql('UPDATE inventory_profile SET profile=?', (CORE_PROFILE,))
        with self.assertRaises(BackendError): self.read()
        self.sql('UPDATE inventory_profile SET profile=?', (PROFILE,)); self.read()

    def test_unknown_marker_does_not_use_either_variant(self):
        self.sql("UPDATE inventory_profile SET profile='accumulation-reference-forms-v2'")
        with patch(TARGET) as importer, self.assertRaises(BackendError): self.read()
        importer.assert_not_called()

    def test_rehashed_manifest_change_is_not_hidden_by_unchanged_core_projection(self):
        self.assert_refusal_and_repair(MANIFEST, self.files[MANIFEST] + b'\n')

    def test_rehashed_form_definition_change_is_not_hidden_by_unchanged_catalogs(self):
        self.assert_refusal_and_repair(DOC_FORM, self.files[DOC_FORM] + b'\n')

    def test_rehashed_form_module_change_is_not_hidden_by_unchanged_handler(self):
        self.assert_refusal_and_repair(DOC_MODULE, self.files[DOC_MODULE] + b'\n// changed\n')

    def test_actual_form_bytes_are_checked_before_cache_lookup(self):
        self.sql('UPDATE configuration_file SET content=? WHERE path=?', (b'<bad/>', DOC_FORM))
        with patch(TARGET) as importer, self.assertRaises(BackendError): self.read()
        importer.assert_not_called()

    def test_failed_full_variant_import_is_not_published(self):
        self.backend._prepared_source.clear()
        with patch(TARGET, side_effect=ValueError('rejected')), self.assertRaises(BackendError): self.read()
        self.assertIsNone(self.backend._prepared_source._entry)
        self.read()

    def test_backend_reopen_is_cold_and_close_clears_full_variant(self):
        with patch(TARGET, wraps=import_inventory_application) as importer:
            other = SQLiteCatalogBackend(self.path)
            try:
                self.assertEqual(importer.call_count, 1)
                with closing(other.begin_read()): pass
                self.assertEqual(importer.call_count, 1)
                self.assertIsNot(other._prepared_source, self.backend._prepared_source)
            finally: other.close()
        self.assertIsNone(other._prepared_source._entry)

    def test_recorder_fields_remain_live_for_full_variant(self):
        with patch('yadinassi.sqlite_accumulation_movements.AccumulationMovementPort._require', side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError): self.read()
        self.read()
