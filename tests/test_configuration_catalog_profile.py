"""Explicit generic form activation and durable source pins, not native evidence."""
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID

from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration, import_catalog_forms_configuration
from yadinassi.configuration_catalog_profile import CATALOG_FORMS_SOURCE_ISSUE
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.database_context import SQLiteDBContext
from yadinassi.metadata import BSLCatalogMetadataCollection
from yadinassi.catalogs import BSLCatalogs
from yadinassi.catalog_object_preparation import CatalogWriteRefused

CATALOG = UUID('21000000-0000-0000-0000-000000000001')
FORM = UUID('21000000-0000-0000-0000-000000000002')


def catalog_form_sources():
    head = '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" version="2.20">'
    files = {
        'Configuration.xml': head + '<Configuration uuid="21000000-0000-0000-0000-000000000003"><Properties><Name>OwnedForms</Name></Properties><ChildObjects><Catalog>Items</Catalog></ChildObjects></Configuration></MetaDataObject>',
        'Catalogs/Items.xml': head + f'<Catalog uuid="{CATALOG}"><Properties><Name>Items</Name><CodeLength>8</CodeLength><DescriptionLength>64</DescriptionLength><DefaultObjectForm>Catalog.Items.Form.Card</DefaultObjectForm></Properties><ChildObjects><Form>Card</Form></ChildObjects></Catalog></MetaDataObject>',
        'Catalogs/Items/Forms/Card.xml': head + f'<Form uuid="{FORM}"><Properties><Name>Card</Name><FormType>Managed</FormType></Properties></Form></MetaDataObject>',
        'Catalogs/Items/Forms/Card/Ext/Form.xml': '<Form xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" version="2.17"><Title>Item</Title><Attributes><Attribute name="Object" id="1"><Type><v8:Type>cfg:CatalogObject.Items</v8:Type></Type><MainAttribute>true</MainAttribute></Attribute></Attributes><ChildItems><InputField name="DescriptionInput" id="1"><DataPath>Object.Description</DataPath></InputField></ChildItems></Form>',
        'Catalogs/Items/Ext/ObjectModule.bsl': 'Процедура ПередЗаписью(Отказ)\nНаименование = СокрЛП(Наименование);\nЕсли Наименование = "blocked" Тогда Отказ = Истина; КонецЕсли;\nКонецПроцедуры',
    }
    return {key: value.encode() for key, value in files.items()}


class CatalogFormsProfileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'forms.sqlite'

    def create(self, files=None):
        backend = SQLiteCatalogBackend.create_catalog_forms(self.path, catalog_form_sources() if files is None else files)
        self.addCleanup(backend.close)
        return backend

    def object(self):
        context = SQLiteDBContext(self.path)
        self.addCleanup(context.close)
        catalogs = BSLCatalogs(BSLCatalogMetadataCollection(context), context)
        return catalogs.get_index('Items').create_item()

    def test_explicit_profile_pins_original_files_and_schema(self):
        files = catalog_form_sources()
        files['Catalogs/Items.xml'] = files['Catalogs/Items.xml'].replace(
            b'<ChildObjects>', b'<ChildObjects><Attribute uuid="21000000-0000-0000-0000-000000000004"><Properties><Name>Amount</Name><Type xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema"><v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>8</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers></Type></Properties></Attribute>')
        imported = import_catalog_forms_configuration(files)
        self.assertEqual(imported.catalogs[0].fields[0].kind, 'number')
        self.assertTrue(imported.activation_issues[0].startswith(CATALOG_FORMS_SOURCE_ISSUE + ':'))
        backend = self.create(files)
        self.assertEqual(backend.export_configuration(), files)
        self.assertEqual(backend.storage_version, 6)
        with self.assertRaises(BackendError): SQLiteCatalogBackend.create(self.path.with_name('ordinary.sqlite'), imported)

    def test_default_import_does_not_activate_declared_forms(self):
        with self.assertRaises(ValueError): import_configuration(catalog_form_sources())

    def test_unknown_file_rejected(self):
        files = catalog_form_sources(); files['Ext/SessionModule.bsl'] = b'// not admitted'
        with self.assertRaises(ValueError): import_catalog_forms_configuration(files)

    def test_missing_default_form_rejected(self):
        files = catalog_form_sources()
        files['Catalogs/Items.xml'] = files['Catalogs/Items.xml'].replace(b'<DefaultObjectForm>Catalog.Items.Form.Card</DefaultObjectForm>', b'')
        with self.assertRaises(ValueError): import_catalog_forms_configuration(files)

    def test_unknown_metadata_property_not_cleared(self):
        files = catalog_form_sources()
        files['Catalogs/Items.xml'] = files['Catalogs/Items.xml'].replace(b'<CodeLength>', b'<Magic>true</Magic><CodeLength>')
        with self.assertRaises(ValueError): import_catalog_forms_configuration(files)

    def test_unsupported_object_call_rejected_before_activation(self):
        files = catalog_form_sources(); files['Catalogs/Items/Ext/ObjectModule.bsl'] = 'Процедура ПередЗаписью(Отказ)\nЭтотОбъект.Записать();\nКонецПроцедуры'.encode()
        with self.assertRaises(ValueError): import_catalog_forms_configuration(files)

    def test_unsupported_dead_object_branch_rejected(self):
        files = catalog_form_sources(); files['Catalogs/Items/Ext/ObjectModule.bsl'] = 'Процедура ПередЗаписью(Отказ)\nЕсли Ложь Тогда Выполнить("x"); КонецЕсли;\nКонецПроцедуры'.encode()
        with self.assertRaises(ValueError): import_catalog_forms_configuration(files)

    def test_object_preparation_is_mandatory_on_write(self):
        self.create().close(); obj = self.object()
        obj.set_member('Code', '1'); obj.set_member('Description', '  normalized  '); obj.write()
        ref = obj.get_member('Ref'); fresh = ref.get_object(ref)
        self.assertEqual(fresh.get_member('Description'), 'normalized')

    def test_object_preparation_can_refuse_write(self):
        self.create().close(); obj = self.object()
        obj.set_member('Code', '1'); obj.set_member('Description', 'blocked')
        with self.assertRaises(CatalogWriteRefused): obj.write()
        self.assertTrue(obj.is_new())

    def test_generic_profile_does_not_authorize_legacy_demo_form_adapter(self):
        backend = self.create()
        self.assertEqual(backend.active_form_catalogs(), ())
        self.assertEqual(backend.read_form_source(CATALOG).identity.form_id, FORM)

    def test_source_replacement_rejected_on_reopen_even_with_updated_file_hash(self):
        self.create().close()
        content = catalog_form_sources()['Catalogs/Items/Forms/Card/Ext/Form.xml'].replace(b'<Title>Item</Title>', b'<Title>Changed</Title>')
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (content, sha256(content).hexdigest(), 'Catalogs/Items/Forms/Card/Ext/Form.xml'))
        with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)

    def test_source_replacement_rejected_by_existing_backend(self):
        backend = self.create()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE configuration_file SET content=? WHERE path='Catalogs/Items/Ext/ObjectModule.bsl'", (b'changed',))
        with self.assertRaises(BackendError): backend.begin_read()
