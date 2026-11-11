"""Reference application source grants do not imply additive configuration authority."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_configuration_reference_profile import sources
from test_document_configuration_xml import document_files
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_reference_profile import import_reference_configuration
from yadinassi.configuration_evolution import canonical
from yadinassi.configuration_xml import import_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_configuration_update import prepare


class AdditiveReferenceProfileBoundaryTests(unittest.TestCase):
    def test_reference_grant_target_refused_before_storage(self):
        target = import_reference_configuration(sources())
        with patch('yadinassi.sqlite_catalog.SQLiteCatalogBackend', side_effect=AssertionError('storage must not open')):
            with self.assertRaises(BackendError) as caught: prepare('unopened.sqlite', target, maintenance=True)
        self.assertEqual(caught.exception.code, 'unsupported')

    def test_removing_marker_does_not_make_reference_source_canonical(self):
        target = replace(import_reference_configuration(sources()), activation_issues=())
        with self.assertRaises(BackendError): canonical(target)

    def test_reference_grant_source_refuses_update_without_mutation(self):
        files = sources()
        target = import_configuration(document_files(catalogs=False, fields=False))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'forms.sqlite'
            SQLiteCatalogBackend.create_reference_application(path, files).close()
            before = path.read_bytes()
            with self.assertRaises(BackendError) as caught: prepare(path, target, maintenance=True)
            self.assertEqual(caught.exception.code, 'unsupported')
            self.assertEqual(path.read_bytes(), before)
            backend = SQLiteCatalogBackend(path)
            try:
                self.assertEqual(backend.format_version, 7)
                self.assertEqual(backend.export_configuration(), files)
            finally: backend.close()
