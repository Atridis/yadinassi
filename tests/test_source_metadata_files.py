"""File-backed metadata identities do not load forms or execute commands."""
import unittest
from test_source_metadata import xml
from test_source_metadata_children import embedded
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_metadata import SourceMetadataRoot


class SourceMetadataFilesTests(unittest.TestCase):
    def files(self, children='<Form>Edit</Form><Template>Print</Template><Command>Open</Command>'):
        return {'Configuration.xml': xml('Configuration', 'Demo', children='<Catalog>Items</Catalog>'),
                'Catalogs/Items.xml': xml('Catalog', 'Items', children=children),
                'Catalogs/Items/Forms/Edit.xml': xml('Form', 'Edit'),
                'Catalogs/Items/Templates/Print.xml': xml('Template', 'Print'),
                'Catalogs/Items/Commands/Open.xml': xml('Command', 'Open')}

    def root(self, files=None):
        return SourceMetadataRoot(import_source(self.files() if files is None else files))

    def test_file_families_identity_and_bilingual_names(self):
        root = self.root()
        for family, ru, name in [('Form', 'Форма', 'Edit'), ('Template', 'Макет', 'Print'), ('Command', 'Команда', 'Open')]:
            obj = root.find_by_full_name('Catalog.Items.' + family + '.' + name)
            self.assertIs(obj, root.find_by_full_name('Справочник.Items.' + ru + '.' + name))
            self.assertEqual(obj.full_name(), 'Справочник.Items.' + ru + '.' + name)

    def test_inline_and_file_command_preserve_order(self):
        files = self.files('<Command>Open</Command>' + embedded('Command', 'Other'))
        root = self.root(files)
        self.assertEqual([x._name for x in root.find_by_full_name('Catalog.Items').get_member('Commands')], ['Open', 'Other'])

    def test_missing_file_explicit(self):
        files = self.files(); del files['Catalogs/Items/Forms/Edit.xml']
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.root(files).find_by_full_name('Catalog.Items.Form.Edit')

    def test_undeclared_file_explicit(self):
        files = self.files(children='')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.root(files).find_by_full_name('Catalog.Items.Form.Edit')

    def test_file_name_mismatch_explicit(self):
        files = self.files(); files['Catalogs/Items/Forms/Edit.xml'] = xml('Form', 'Other')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            self.root(files).find_by_full_name('Catalog.Items.Form.Edit')

    def test_wrong_file_family_explicit(self):
        files = self.files(); files['Catalogs/Items/Forms/Edit.xml'] = xml('Role', 'Edit')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.root(files).find_by_full_name('Catalog.Items.Form.Edit')

    def test_duplicate_mixed_command_name_rejected(self):
        files = self.files('<Command>Open</Command>' + embedded('Command', 'open'))
        with self.assertRaisesRegex(ValueError, 'ambiguous metadata name'):
            self.root(files).find_by_full_name('Catalog.Items').get_member('Commands')

    def test_mixed_command_uuid_collision_rejected(self):
        # Same UUID, distinct names, in either declaration order.
        inline = embedded('Command', 'Open').replace('>Open<', '>Other<')
        for children in ('<Command>Open</Command>' + inline, inline + '<Command>Open</Command>'):
            files = self.files(children)
            with self.assertRaisesRegex(ValueError, 'duplicate embedded metadata identity'):
                self.root(files).find_by_full_name('Catalog.Items').get_member('Commands')

    def test_root_does_not_gain_object_forms(self):
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            self.root().get_member('Forms')

    def test_no_executable_or_storage_capability(self):
        root = self.root()
        for family, name in [('Form', 'Edit'), ('Template', 'Print'), ('Command', 'Open')]:
            obj = root.find_by_full_name('Catalog.Items.' + family + '.' + name)
            with self.assertRaises(ValueError): obj.get_member('Execute')
            with self.assertRaises(ValueError): obj.set_member('Name', 'Other')
