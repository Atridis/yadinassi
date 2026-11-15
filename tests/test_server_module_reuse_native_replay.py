"""Source-bound replay of measured local/file-mode server reuse only."""
import hashlib,json,sys,unittest
from pathlib import Path
from yadinassi.configuration_runtime import ConfigurationApplication
from configuration_runtime_fixture import module_files
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from server_module_reuse_packet import route,packet,SOURCE_SHA256,FORM_SHA256
NATIVE=ROOT/'tests/fixtures/native_server_module_reuse_43165393593.json'
def application_files():
    raw=packet();text=raw['Launcher/Forms/Main/Ext/Form/Module.bsl'].decode('utf-8-sig')
    source='Var Calls, ClientToken, SessionToken, RequestToken;\n'+text[text.index('Function Bit(Value)'):text.index('Procedure FirstEvent() Export')].replace('&AtClient','')
    files=module_files(application=source)
    for name in ('ServerSession','ServerRequest','CachedServerCall','ServerInspector'):
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',('<CommonModule>'+name+'</CommonModule></ChildObjects>').encode())
        for suffix in ('.xml','/Ext/Module.bsl'):
            path='CommonModules/'+name+suffix;files[path]=raw[path]
    return files

def application():
    app=ConfigurationApplication.from_files(application_files());app.start();return app

class NativeServerReuseReplay(unittest.TestCase):
    def test_source_binding(self):
        value=json.loads(NATIVE.read_bytes());self.assertEqual(value['run_id'],43165393593)
        self.assertEqual(value['head_sha'],'7e51023d47f98dfeeb44f07357ecb5223312e3bd')
        for key,wanted in [('source_sha256',SOURCE_SHA256),('form_sha256',FORM_SHA256),('module_sha256',route.module_digest())]:self.assertEqual(value[key],wanted)
        wire=''.join(f'SR{i}={v}|' for i,v in enumerate(value['observations'],1)).encode()
        self.assertEqual(hashlib.sha256(wire).hexdigest(),value['output_sha256'])
        self.assertEqual(len(wire),value['output_size'])
        self.assertEqual(len(value['observations']),16)

def case(number):
    def test(self):
        app=application();self.addCleanup(app.close,force=True)
        first=app.execute('Results=New Array;For I=1 To 15 Do Results.Add(Observe(I));EndDo;Results').items
        last=app.execute('Bit(ClientToken=CachedServerCall.Token("lifetime"))+":"+Bit(SessionToken=ServerInspector.SessionToken("lifetime"))+":"+Bit(RequestToken=ServerInspector.RequestToken("lifetime"))')
        actual=(*first,last)[number-1]
        self.assertEqual(actual,json.loads(NATIVE.read_bytes())['observations'][number-1])
    return test
for number in range(1,17):setattr(NativeServerReuseReplay,'test_native_%02d'%number,case(number))
