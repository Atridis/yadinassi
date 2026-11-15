import unittest
from test_configuration_source_runtime import source
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError


class SourceMetadataPropertyTests(unittest.TestCase):
    def run_source(self, variant, code):
        s=source(('Procedure OnStart()\n'+code+'\nEndProcedure').encode())
        files={f.path:f.content for f in s.files}
        if variant is not None:
            files['Configuration.xml']=files['Configuration.xml'].replace(b'</Properties>',('<ScriptVariant>'+variant+'</ScriptVariant></Properties>').encode())
        out=[];app=SourceApplication(import_source(files),output=out.append);self.addCleanup(app.close)
        app.start();return out

    def test_english_xml_identity(self):
        self.assertEqual(self.run_source('English','Message(Metadata.ScriptVariant=Metadata.ObjectProperties.ScriptVariant["English"]);'),['Да'])

    def test_russian_not_forced_english(self):
        self.assertEqual(self.run_source('Russian','Message(Metadata.ScriptVariant=Metadata.ObjectProperties.ScriptVariant.English);'),['Нет'])

    def test_russian_aliases(self):
        self.assertEqual(self.run_source('Russian','Message(Метаданные.ВариантВстроенногоЯзыка=Метаданные.СвойстваОбъектов.ВариантВстроенногоЯзыка["Русский"]);'),['Да'])

    def test_missing_property_not_guessed(self):
        with self.assertRaisesRegex(BSLError,'absent or ambiguous'):self.run_source(None,'Message(Metadata.ScriptVariant);')

    def test_unknown_xml_value(self):
        with self.assertRaisesRegex(BSLError,'unknown source ScriptVariant'):self.run_source('Future','Message(Metadata.ScriptVariant);')

    def test_unknown_domain_value(self):
        with self.assertRaises(BSLError):self.run_source('English','Message(Metadata.ObjectProperties.ScriptVariant["Future"]);')

    def test_read_only_domain(self):
        with self.assertRaises(BSLError):self.run_source('English','Metadata.ObjectProperties.ScriptVariant.English=42;')

    def test_unsupported_property_explicit(self):
        with self.assertRaisesRegex(BSLError,'enumeration is not supported'):self.run_source('English','Message(Metadata.ObjectProperties.Future);')


class SourceCompatibilityModeTests(unittest.TestCase):
    def run_source(self, value, code):
        s=source(('Procedure OnStart()\n'+code+'\nEndProcedure').encode())
        files={f.path:f.content for f in s.files}
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</Properties>',('<CompatibilityMode>'+value+'</CompatibilityMode></Properties>').encode())
        out=[];app=SourceApplication(import_source(files),output=out.append);self.addCleanup(app.close)
        app.start();return out

    def test_source_identity_and_canonical_text(self):
        self.assertEqual(self.run_source('Version8_3_24','Message(Metadata.CompatibilityMode=Metadata.ObjectProperties.CompatibilityMode.Version8_3_24); Message(Metadata.CompatibilityMode);'),['Да','Version8_3_24'])

    def test_dontuse_not_inferred_from_target(self):
        self.assertEqual(self.run_source('DontUse','Message(Metadata.CompatibilityMode=Metadata.ObjectProperties.CompatibilityMode.DontUse);'),['Да'])

    def test_general_version_digit_extraction(self):
        self.assertEqual(self.run_source('Version8_3_24','M=Metadata.CompatibilityMode; Message(StrConcat(StrSplit(M, StrConcat(StrSplit(M,"1234567890",False),""),False),"."));'),['8.3.24'])

    def test_future_unknown_stays_error(self):
        with self.assertRaisesRegex(BSLError,'unknown source CompatibilityMode'):
            self.run_source('FutureMode','Message(Metadata.CompatibilityMode);')

    def test_russian_domain_aliases(self):
        self.assertEqual(self.run_source('Version8_3_24','Message(Метаданные.РежимСовместимости=Метаданные.СвойстваОбъектов.РежимСовместимости.Версия8_3_24);'),['Да'])
