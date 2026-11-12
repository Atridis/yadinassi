"""Точный UI-допуск единой демо без выдачи generic grant русским формам."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_main_demo_configuration import source
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.ui.main_demo import document_forms, require_backend


class MainDemoUIAdmissionTests(unittest.TestCase):
    def config(self):
        return import_main_demo_configuration(source(), profile=PROFILE)

    def backend(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        context = SQLiteDBContext.create_main_demo(Path(temporary.name) / 'demo.sqlite', self.config())
        self.addCleanup(context.close)
        return context.backend

    def test_projection_grants_documents_and_declared_common_forms_not_catalogs(self):
        config = self.config()
        forms = document_forms(config)
        self.assertEqual(set(forms.forms), {'document.receipt.form.card', 'document.issue.form.card', 'commonform.operationdraft', 'commonform.draftdetails'})
        for definition in forms.forms.values():
            self.assertIsNone(definition.catalog_schema)
            if not definition.name.startswith("CommonForm."):
                self.assertIn(definition.document_schema, config.documents)
            else:
                self.assertIsNone(definition.document_schema)
        self.assertFalse(any(name.startswith('catalog.') for name in forms.forms))

    def test_source_witness_retains_all_original_bytes_and_is_immutable(self):
        config = self.config()
        forms = document_forms(config)
        self.assertEqual(dict(forms.source_files), source())
        self.assertEqual(len(forms.source_files), 44)
        self.assertEqual(forms.source_files['Configuration.xml'], source()['Configuration.xml'])
        digest = sha256()
        for path, raw in sorted(source().items()):
            digest.update(path.encode('utf-8') + b'\0' + raw + b'\0')
        self.assertEqual(forms.source_sha256, digest.hexdigest())
        with self.assertRaises(TypeError):
            forms.source_files['Configuration.xml'] = b'changed'
        self.assertEqual(dict(config.files), source())

    def test_original_catalog_module_drift_cannot_hide_behind_document_projection(self):
        config = self.config()
        files = dict(config.files)
        path = 'Catalogs/Номенклатура/Ext/ObjectModule.bsl'
        files[path] += b'\n'
        with self.assertRaises(ValueError):
            document_forms(replace(config, files=tuple(sorted(files.items()))))

    def test_forged_schema_and_old_profile_cannot_get_document_grant(self):
        config = self.config()
        for forged in (replace(config, catalogs=()), replace(config, profile='inventory-enum-forms-v1')):
            with self.subTest(profile=forged.profile), self.assertRaises(ValueError):
                document_forms(forged)

    def test_backend_accepts_exact_reopened_full_source(self):
        backend = self.backend()
        expected = self.config()
        self.assertEqual(require_backend(backend), expected)
        with SQLiteDBContext(backend.path) as reopened:
            self.assertEqual(require_backend(reopened.backend), expected)

    def test_foreign_backend_properties_are_not_touched(self):
        class Foreign:
            @property
            def accumulation_configuration(self):
                raise AssertionError('foreign property accessed')
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            require_backend(Foreign())

    def test_closed_backend_is_refused(self):
        backend = self.backend()
        backend.close()
        with self.assertRaisesRegex(BackendError, 'closed'):
            require_backend(backend)

    def test_wrong_profile_and_forged_canonical_configuration_are_refused(self):
        backend = self.backend()
        config = backend.accumulation_configuration
        for forged, code in ((replace(config, profile='inventory-enum-v1'), 'unsupported'),
                             (replace(config, catalog_handlers=()), 'schema_changed')):
            with patch.object(backend, 'accumulation_configuration', forged):
                with self.assertRaisesRegex(BackendError, code):
                    require_backend(backend)

    def test_exported_source_drift_is_refused_even_with_cached_configuration(self):
        backend = self.backend()
        changed = dict(backend.accumulation_configuration.files)
        changed['Catalogs/Номенклатура/Ext/ObjectModule.bsl'] += b'\n'
        with patch.object(backend, 'export_configuration', return_value=changed):
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                require_backend(backend)
