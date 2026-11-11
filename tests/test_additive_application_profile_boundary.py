"""Application grants never become implicit migration authority."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_evolution import canonical
from yadinassi.configuration_application_profile import import_application_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi import sqlite_migration_plan as migration
from yadinassi import sqlite_configuration_update as update
from test_configuration_application_profile import application_sources


class AdditiveApplicationProfileBoundaryTests(unittest.TestCase):
    def test_application_grant_is_not_plain_additive_source(self):
        configuration = import_application_configuration(application_sources())
        with self.assertRaises(BackendError) as caught:
            canonical(configuration)
        self.assertEqual(caught.exception.code, 'unsupported')

    def test_application_storage_refuses_transaction_migration_before_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'application.sqlite'
            backend = SQLiteCatalogBackend.create_application(path, application_sources())
            backend.close()
            before = path.read_bytes()
            with patch.object(migration, '_open', side_effect=AssertionError('writer must not open')):
                with self.assertRaises(BackendError) as caught:
                    migration.prepare(path, maintenance=True)
            self.assertEqual(caught.exception.code, 'unsupported')
            self.assertEqual(path.read_bytes(), before)

    def test_application_target_refused_before_storage_or_ddl(self):
        configuration = import_application_configuration(application_sources())
        with patch('yadinassi.sqlite_catalog.SQLiteCatalogBackend', side_effect=AssertionError('storage must not open')):
            with self.assertRaises(BackendError) as caught:
                update.prepare('unopened.sqlite', configuration, maintenance=True)
        self.assertEqual(caught.exception.code, 'unsupported')
