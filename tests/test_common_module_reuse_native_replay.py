"""Recovered source-bound client replay; earlier PASS results are not inherited."""
import hashlib,json,sys,unittest
from pathlib import Path
from yadinassi.configuration_runtime import ConfigurationApplication
from configuration_runtime_fixture import module_files
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from common_module_reuse_packet import route,packet,SOURCE_SHA256,FORM_SHA256,MODULES_SHA256
NATIVE=ROOT/'tests/fixtures/native_common_module_reuse_43130157790.json'
def application():
    raw=packet();text=raw['Launcher/Forms/Main/Ext/Form/Module.bsl'].decode('utf-8-sig')
    source='Var Calls, SessionToken, RequestToken;\n'+text[text.index('Function Bit(Value)'):text.index('Procedure FirstEvent() Export')].replace('&AtClient','')
    files=module_files(application=source)
    for name in ('ReuseSession','ReuseRequest'):
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',('<CommonModule>'+name+'</CommonModule></ChildObjects>').encode())
        for suffix in ('.xml','/Ext/Module.bsl'):
            path='CommonModules/'+name+suffix;files[path]=raw[path]
    app=ConfigurationApplication.from_files(files);app.start();return app
class NativeReplay(unittest.TestCase):
    def test_source_binding(self):
        value=json.loads(NATIVE.read_bytes());self.assertEqual(value['run_id'],43130157790)
        self.assertEqual(value['head_sha'],'e27ab7a56a0b3295ad7ac9a69ccf48fecd701d18')
        for key,wanted in [('source_sha256',SOURCE_SHA256),('form_sha256',FORM_SHA256),('modules_sha256',MODULES_SHA256),('module_sha256',route.module_digest())]:self.assertEqual(value[key],wanted)
        wire=''.join(f'CM{i}={v}|' for i,v in enumerate(value['observations'],1)).encode();self.assertEqual(hashlib.sha256(wire).hexdigest(),value['output_sha256']);self.assertEqual(len(value['observations']),16)
def case(number):
    def test(self):
        app=application();self.addCleanup(app.close,force=True)
        if number==16:
            app.interpreter.execute('Observe(15)')
            actual=app.interpreter.execute('Bit(SessionToken=ReuseSession.Token("lifetime"))+":"+Bit(RequestToken=ReuseRequest.Token("lifetime"))')
        else:actual=app.interpreter.execute('Observe('+str(number)+')')
        self.assertEqual(actual,json.loads(NATIVE.read_bytes())['observations'][number-1])
    return test
for number in range(1,17):setattr(NativeReplay,'test_native_%02d'%number,case(number))
