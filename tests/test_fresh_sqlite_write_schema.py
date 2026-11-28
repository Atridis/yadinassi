"""Exercise real fresh database builders across SQLite storage families."""
from contextlib import ExitStack, closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from scripts.benchmark_extended_layers import database
from yadinassi.configuration.configuration_accumulation import import_accumulation_configuration
from yadinassi.configuration.configuration_inventory_application import import_inventory_application
from yadinassi.configuration.configuration_posting_application import import_posting_application
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
import inventory_application_fixture
import posting_application_fixture
import test_sqlite_accumulation_profile as accumulation
import test_sqlite_catalog_backend as catalogs
import test_sqlite_register_integration as registers


class FreshSQLiteWriteSchemaTests(unittest.TestCase):
    def assert_current_schema(self, path):
        with closing(sqlite3.connect(path)) as db:
            names = {name for (name,) in db.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'")}
        self.assertTrue({'database_info', 'catalog_schema'} <= names)
        # A document named Receipt can have ordinary physical data tables;
        # suffix below refers only to the former write infrastructure.
        self.assertFalse({name for name in names if name.endswith('_receipt')
                          or name == 'configuration_receipt_epoch'})

    def test_current_builders_create_business_tables_only(self):
        with ExitStack() as stack:
            directory = Path(stack.enter_context(TemporaryDirectory()))
            from yadinassi.configuration.configuration_inventory_application import PROFILE as INVENTORY
            from yadinassi.configuration.configuration_posting_application import PROFILE as POSTING
            cases = (
                ('catalog', SQLiteCatalogBackend.create, catalogs.configuration()),
                ('register', SQLiteCatalogBackend.create, registers.configuration()),
                ('posting', SQLiteCatalogBackend.create_posting,
                 import_posting_application(posting_application_fixture.source(), posting_runtime=POSTING)),
                ('accumulation', SQLiteCatalogBackend.create_accumulation,
                 import_accumulation_configuration(accumulation.accumulation_source(),
                                                   accumulation_runtime=accumulation.PROFILE)),
                ('inventory', SQLiteCatalogBackend.create_inventory_application,
                 import_inventory_application(inventory_application_fixture.source(),
                                              inventory_runtime=INVENTORY)),
            )
            for name, create, config in cases:
                with self.subTest(name=name):
                    path = directory / (name + '.sqlite')
                    stack.enter_context(closing(create(path, config)))
                    self.assert_current_schema(path)
            path, *_ = database(stack)
            self.assert_current_schema(path)
