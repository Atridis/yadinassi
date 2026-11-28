"""Fresh recovery gate: original native observations plus closed application scope."""
import hashlib,json,unittest
from pathlib import Path
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
from yadinassi.runtime import Interpreter
from configuration_runtime_fixture import module_files
ROOT=Path(__file__).resolve().parents[1];ASSETS=ROOT/'scripts/common_template_behavior'
FIXTURE=ROOT/'tests/fixtures/native_common_templates_43083042989.json'

def files(application=''):
    result=module_files(application=application)
    for name,suffix in [('OwnedText','txt'),('OwnedBinary','bin')]:
        result['Configuration.xml']=result['Configuration.xml'].replace(b'</ChildObjects>',('<CommonTemplate>'+name+'</CommonTemplate></ChildObjects>').encode())
        result['CommonTemplates/'+name+'.xml']=(ASSETS/(name+'.xml')).read_bytes()
        result['CommonTemplates/'+name+'/Ext/Template.'+suffix]=(ASSETS/(name+'.'+suffix)).read_bytes()
    return result

def observation_files():
    # Preserve the actual native observation routine, not its acquisition
    # driver. The per-case tests call the original routine directly.
    source=(ASSETS/'observe.bsl').read_text(encoding='utf-8').split('For CaseNo = 1 To 12 Do')[0]
    return files(source)


def application():
    value=ConfigurationApplication.from_files(observation_files());value.start();return value


def source_application():
    value=SourceApplication(import_source(observation_files()))
    value.start()
    return value

class NativeReplay(unittest.TestCase):
    def test_source_binding(self):
        f=json.loads(FIXTURE.read_bytes());stage=f['summary']['native_report']['stage3']
        self.assertEqual(f['run_id'],'43083042989');self.assertEqual(stage['record_count'],12)
        self.assertEqual(hashlib.sha256((ASSETS/'observe.bsl').read_bytes()).hexdigest(),stage['source_sha256'])
        wire=(json.dumps(f['observations'],separators=(',',':'))+'\n').encode('ascii')
        self.assertEqual(hashlib.sha256(wire).hexdigest(),stage['output_sha256'])
        self.assertEqual(stage['module_sha256'],stage['module_verified_sha256'])
        self.assertEqual(f['observations'],[x[1] for x in stage['partial_observations']])

def native_case(n):
    def test(self):
        value=source_application();self.addCleanup(value.close)
        self.assertEqual(value.interpreter.execute('ObserveCase('+str(n)+', "")'),json.loads(FIXTURE.read_bytes())['observations'][n-1])
    return test
for n in range(1,13):setattr(NativeReplay,'test_native_%02d'%n,native_case(n))

class Admission(unittest.TestCase):
    def test_exact_source_preserved(self):
        source=files();c=import_configuration(source,module_runtime=MODULE_RUNTIME)
        self.assertEqual(source,{f.path:f.content for f in c.files});self.assertEqual(len(c.common_templates),2)
    def test_missing_resource(self):
        source=files();del source['CommonTemplates/OwnedBinary/Ext/Template.bin']
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_wrong_kind(self):
        source=files();key='CommonTemplates/OwnedText.xml';source[key]=source[key].replace(b'TextDocument',b'SpreadsheetDocument')
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_resource_without_profile(self):
        with self.assertRaises(ValueError):import_configuration(files())
    def test_no_generic_binary_grant(self):
        source=files();source['Elsewhere/secret.bin']=b'123'
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_orphan_resource(self):
        source=files();source['CommonTemplates/Absent/Ext/Template.bin']=b'\xff'
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_invalid_text_encoding(self):
        source=files();source['CommonTemplates/OwnedText/Ext/Template.txt']=b'\xff'
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_inventory_forgery(self):
        for replacement in [b'<CommonTemplate x="y">OwnedText</CommonTemplate>',b'<CommonTemplate>OwnedText<X/></CommonTemplate>']:
            source=files();source['Configuration.xml']=source['Configuration.xml'].replace(b'<CommonTemplate>OwnedText</CommonTemplate>',replacement)
            with self.subTest(replacement=replacement),self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_metadata_forgery(self):
        for replacement in [b'<Unknown/>',b'<ChildObjects><X/></ChildObjects>']:
            source=files();key='CommonTemplates/OwnedText.xml';source[key]=source[key].replace(b'</CommonTemplate>',replacement+b'</CommonTemplate>')
            with self.subTest(replacement=replacement),self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
    def test_standalone_no_grant(self):
        with self.assertRaises(Exception):Interpreter().execute('GetCommonTemplate("OwnedText")')
    def test_prepared_no_grant(self):
        value=ConfigurationApplication.from_files(files());self.addCleanup(value.close,force=True)
        with self.assertRaises(Exception):value.interpreter.execute('GetCommonTemplate("OwnedText")')
    def test_closed_no_grant(self):
        value=application();value.close(force=True)
        with self.assertRaises(Exception):value.interpreter.execute('GetCommonTemplate("OwnedText")')
    def test_cross_application_metadata_refused(self):
        a=source_application();b=source_application();self.addCleanup(a.close);self.addCleanup(b.close)
        meta=a.interpreter.execute('Metadata.CommonTemplates.OwnedText')
        with self.assertRaises(ValueError):b.common_templates.get(b.interpreter,meta)
    def test_metadata_identity(self):
        value=source_application();self.addCleanup(value.close)
        self.assertIs(value.interpreter.execute('Metadata.FindByFullName("CommonTemplate.OwnedText")'),value.interpreter.execute('Metadata.CommonTemplates.OwnedText'))
    def test_binary_return_is_fresh(self):
        value=application();self.addCleanup(value.close,force=True)
        self.assertIsNot(value.common_templates.get(value.interpreter,'OwnedBinary'),value.common_templates.get(value.interpreter,'OwnedBinary'))
    def test_bounds(self):
        source=files();source['CommonTemplates/OwnedBinary/Ext/Template.bin']=b'x'*(1024*1024+1)
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(source)
