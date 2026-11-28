"""Reference reuse ends at the owned form validation phase, not the form."""
from contextlib import closing
from contextvars import copy_context
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.configuration.configuration_catalog import CatalogObjectSession
from yadinassi.configuration.configuration_document import DocumentObjectSession
from yadinassi.configuration.configuration_forms import load_configuration_forms
from yadinassi.configuration.configuration_reference_profile import import_reference_configuration
from yadinassi.configuration.demos.inventory_host_operations import InventoryRootOperations
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.forms.form_references import active_reference_read, reference_batch
from yadinassi.forms.form_tables import validate_table_data

import test_configuration_inventory_app as fixture
from test_configuration_reference_profile import sources as reference_sources


class OwnedFormReferenceReadTests(unittest.TestCase):
    def form(self, count=3):
        app = fixture.InventoryApplicationTests()
        self.addCleanup(app.doCleanups)
        app.setUp()
        entry, record = app.seed_saved_lines(count)
        opened = app.open_saved_result(entry, record)
        self.assertIsNone(opened['error'], opened)
        identity = opened['session']
        session = app.broker.sessions[identity][0].session
        table = next(iter(session.form._tables.values()))
        column = next(column for column in table.schema.columns if column.name == 'Product')
        value = table._rows[0]._data['product']
        return app, identity, session, table, column.value_type, value

    def test_reuses_distinct_admitted_bindings_only_inside_one_closed_phase(self):
        app, identity, session, table, descriptor, value = self.form()
        backend = app.broker.objects[identity].context.backend
        scope = descriptor.scope
        counts = []
        reference_read = InventoryRootOperations._reference_read.__wrapped__.__code__
        prior = sys.getprofile()
        def profile(frame, event, _):
            if event == 'call' and frame.f_code is reference_read:
                counts.append(1)
        sys.setprofile(profile)
        try:
            with reference_batch(scope):
                first = scope.encode(descriptor.target, value)
                second = scope.encode(descriptor.target, value)
                validate_table_data(session.form)
                self.assertEqual(first, second)
            self.assertIsNone(backend._active)
        finally:
            sys.setprofile(prior)
        # A contextmanager resumes once to close the same read snapshot.
        self.assertEqual(counts, [1, 1])
        self.assertEqual(len(table._rows), 3)

    def test_copied_phase_cannot_reuse_caption_after_external_write(self):
        app, _, _, _, descriptor, value = self.form()
        scope = descriptor.scope
        with reference_batch(scope):
            before = scope.encode(descriptor.target, value)
            copied = copy_context()
            leaked = active_reference_read(scope)
            self.assertIsNotNone(leaked)
        self.assertIsNone(copied.run(active_reference_read, scope))
        with self.assertRaisesRegex(ValueError, 'expired form reference batch'):
            leaked.view()
        with closing(SQLiteDBContext(app.path)) as context:
            with closing(Interpreter(database_context=context, output=lambda _: None)) as vm:
                vm.execute('R=Catalogs.Products.FindByCode("P1").GetObject();'
                           'R.Description="Renamed after phase";R.Write();')
        after = copied.run(scope.encode, descriptor.target, value)
        self.assertEqual(before['key'], after['key'])
        self.assertNotEqual(before['text'], after['text'])
        self.assertEqual(after['text'], 'Renamed after phase')

    def test_changed_source_is_rejected_before_table_validation_can_publish(self):
        app, identity, session, table, descriptor, value = self.form()
        before = tuple(table._rows)
        backend = app.broker.objects[identity].context.backend
        with reference_batch(descriptor.scope):
            descriptor.scope.encode(descriptor.target, value)
        with closing(sqlite3.connect(app.path)) as peer:
            peer.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'", (b'invalid bytes',))
            peer.commit()
        with self.assertRaises(BackendError):
            validate_table_data(session.form)
        self.assertIsNone(backend._active)
        self.assertEqual(tuple(table._rows), before)
        self.assertTrue(all(not row._removed for row in before))

    def test_ordinary_catalog_and_document_share_the_admitted_reference_path(self):
        files = reference_sources()
        config = import_reference_configuration(files)
        forms = load_configuration_forms(files, catalog_schemas=config.catalogs,
                                         document_schemas=config.documents, reference_catalogs=config.catalogs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ref.sqlite'
            SQLiteCatalogBackend.create_reference_application(path, files).close()
            with closing(SQLiteDBContext(path)) as context:
                with closing(Interpreter(database_context=context, output=lambda _: None)) as vm:
                    vm.execute('C=Catalogs.Categories.CreateItem(); C.Code="A"; C.Description="Ordinary category"; C.Write();')
                for name in ('Catalog.Products.Form.Card', 'Document.Orders.Form.Card'):
                    with self.subTest(name=name):
                        definition = forms.resolve(name)
                        if definition.document_schema is not None:
                            owner = DocumentObjectSession(context, definition.document_schema, files, reference_fields=True)
                        else:
                            owner = CatalogObjectSession(context, definition.catalog_schema, files, reference_fields=True)
                        server = definition.create_server(database_context=context, object_session=owner)
                        with closing(server.session.interpreter):
                            scope = server.session.reference_scope
                            target, identity, _ = next(row for row in definition.reference_targets if row[2] == 'Categories')
                            manager = server.session.interpreter._catalogs._manager_by_metadata_uuid(identity)
                            value = manager.find_by_code('A')
                            with reference_batch(scope):
                                batch = active_reference_read(scope)
                                self.assertIsNotNone(batch)
                                packet = scope.encode(target, value)
                                self.assertEqual(packet['text'], 'Ordinary category')
                                self.assertEqual(scope.encode(target, value), packet)
                                self.assertIs(batch.view(), context.backend._active)
                            self.assertIsNone(context.backend._active)
