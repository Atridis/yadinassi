"""An explicit typed reference grant never expands scalar source profiles."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_types import BSLCatalogReference
from yadinassi.configuration_business_profile import import_business_configuration
from yadinassi.configuration_reference_profile import import_reference_configuration, REFERENCE_SOURCE_ISSUE, REFERENCE_PROFILE
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.configuration_catalog import CatalogObjectSession
from yadinassi.configuration_document import DocumentObjectSession
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

ROOT = Path(__file__).resolve().parents[1] / 'examples/configuration-reference-application'
def sources(): return {p.relative_to(ROOT).as_posix():p.read_bytes() for p in ROOT.rglob('*') if p.is_file()}


class ReferenceProfileTests(unittest.TestCase):
    def test_source_has_three_typed_reference_placements(self):
        imported = import_reference_configuration(sources())
        product = next(c for c in imported.catalogs if c.name == 'Products')
        order = imported.documents[0]
        self.assertEqual(product.fields[-1].kind,'catalog_ref')
        self.assertEqual(order.fields[-1].kind,'catalog_ref')
        self.assertEqual(order.tabular_sections[0].fields[0].kind,'catalog_ref')
        self.assertTrue(imported.activation_issues[0].startswith(REFERENCE_SOURCE_ISSUE+':'))

    def test_old_business_grant_refuses_reference_source(self):
        with self.assertRaises(ValueError): import_business_configuration(sources())

    def test_unknown_reference_target_refuses(self):
        files=sources();files['Documents/Orders.xml']=files['Documents/Orders.xml'].replace(b'CatalogRef.Products',b'CatalogRef.Unknown')
        with self.assertRaises(ValueError): import_reference_configuration(files)

    def test_source_only_templates_require_live_reference_owner(self):
        files=sources(); imported=import_reference_configuration(files)
        forms=load_configuration_forms(files,catalog_schemas=imported.catalogs,document_schemas=imported.documents,reference_catalogs=imported.catalogs)
        definition=forms.resolve('Document.Orders.Form.Card')
        self.assertEqual(len(definition.reference_slots),2)
        with self.assertRaises(ValueError): definition.create_server()

    def test_ordinary_create_cannot_acquire_reference_grant(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'db.sqlite'
            with self.assertRaises(BackendError): SQLiteCatalogBackend.create(path,import_reference_configuration(sources()))
            self.assertFalse(path.exists())

    def test_forged_runtime_rejected_before_create(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'db.sqlite'; imported=import_reference_configuration(sources())
            with self.assertRaises(BackendError):
                SQLiteCatalogBackend.create(path,replace(imported,module_runtime=None,common_modules=()),_source_profile=REFERENCE_PROFILE)
            self.assertFalse(path.exists())

    def test_new_database_reopens_exact_source(self):
        files=sources()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'db.sqlite'
            SQLiteCatalogBackend.create_reference_application(path,files).close()
            with closing(SQLiteCatalogBackend(path)) as db:
                self.assertEqual(db.storage_version,7);self.assertEqual(db.export_configuration(),files)

    def test_catalog_form_materializes_real_typed_empty_reference(self):
        self.check_form('Catalog.Products.Form.Card')

    def test_document_header_and_rows_materialize_real_typed_references(self):
        self.check_form('Document.Orders.Form.Card')

    def check_form(self,name):
        files=sources(); imported=import_reference_configuration(files)
        forms=load_configuration_forms(files,catalog_schemas=imported.catalogs,document_schemas=imported.documents,reference_catalogs=imported.catalogs)
        definition=forms.resolve(name)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'db.sqlite';SQLiteCatalogBackend.create_reference_application(path,files).close()
            with closing(SQLiteDBContext(path)) as context:
                owned=(DocumentObjectSession(context,definition.document_schema,files,reference_fields=True) if definition.document_schema else CatalogObjectSession(context,definition.catalog_schema,files,reference_fields=True))
                server=definition.create_server(database_context=context,object_session=owned)
                self.addCleanup(server.session.interpreter.close)
                for slot,column,target in definition.reference_slots:
                    if not column:
                        value=server.session.form._data[slot.casefold()]
                        self.assertIs(type(value),BSLCatalogReference);self.assertTrue(value.is_empty())
