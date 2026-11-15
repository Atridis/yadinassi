import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source_metadata import SourceMetadataRoot
from yadinassi.configuration_source_runtime import SourceApplication


def package(reference='Language.English', code=b''):
    xml = ('<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Configuration uuid="00000000-0000-0000-0000-000000000001"><Properties><Name>Demo</Name><DefaultLanguage>'+reference+'</DefaultLanguage></Properties><ChildObjects><Language>English</Language></ChildObjects></Configuration></MetaDataObject>').encode()
    language = b'<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"><Language uuid="00000000-0000-0000-0000-000000000002"><Properties><Name>English</Name><LanguageCode>en</LanguageCode></Properties></Language></MetaDataObject>'
    return source(code, {'Configuration.xml':xml,'Languages/English.xml':language})


class SourceLanguageMetadataTests(unittest.TestCase):
    def test_reference_resolves_to_existing_collection_object(self):
        metadata = SourceMetadataRoot(package())
        language = metadata.get_member('DefaultLanguage')
        self.assertIs(language, metadata.get_member('Languages').find('English'))
        self.assertEqual(language.get_member('LanguageCode'), 'en')

    def test_russian_aliases(self):
        language = SourceMetadataRoot(package()).get_member('ОсновнойЯзык')
        self.assertEqual(language.get_member('КодЯзыка'), 'en')
        self.assertEqual(language.full_name(), 'Язык.English')

    def test_missing_reference_does_not_select_first_language(self):
        with self.assertRaisesRegex(ValueError, 'not declared'):
            SourceMetadataRoot(package('Language.Absent')).get_member('DefaultLanguage')

    def test_wrong_family_empty_and_malformed_are_not_guessed(self):
        for text in ('', 'Catalog.English', 'English', 'Language.English.Other'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                SourceMetadataRoot(package(text)).get_member('DefaultLanguage')

    def test_startup_reads_source_selected_language(self):
        output = []
        app = SourceApplication(package(code=b'Procedure OnStart() Message(Metadata.DefaultLanguage.LanguageCode); EndProcedure'), output=output.append)
        try:
            self.assertTrue(app.start())
            self.assertEqual(output, ['en'])
        finally: app.close()
