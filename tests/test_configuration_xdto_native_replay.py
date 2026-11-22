import hashlib
import json
import unittest
from configuration_xdto_fixture import ROOT, files
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported


def replay_source(linked, number):
    folder=ROOT/'scripts'/('configuration_xdto_linked_behavior' if linked else 'configuration_xdto_behavior')
    source=(folder/'observe.bsl').read_text(encoding='utf-8').split('\nFor CaseNo = 1 To 12 Do')[0]
    return source+f'\nStage="";Message(ObserveCase({number},Stage));'


class CoreNativeReplay(unittest.TestCase):
    linked=False
    native_run=43086017286
    def fixture(self):
        suffix='_linked' if self.linked else ''
        return json.loads((ROOT/'tests'/'fixtures'/f'native_configuration_xdto{suffix}_{self.native_run}.json').read_text(encoding='utf-8'))
    def test_source_evidence_identity(self):
        f=self.fixture();report=f['artifact_report'];stage=report['native_report']['stage3']
        attributes=(ROOT/'.gitattributes').read_text(encoding='utf-8')
        for path in ('scripts/native_1c_configuration_xdto_profile.py',
                     'scripts/native_1c_bootstrap/configuration_xdto_suite.py'):
            self.assertIn(path+' text eol=lf',attributes.splitlines())
        self.assertEqual(f['run_id'],self.native_run)
        self.assertEqual(len(f['observations']),12)
        raw=(json.dumps(f['observations'],ensure_ascii=True,separators=(',',':'))+'\n').encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),f['output_sha256'])
        self.assertEqual(len(raw),f['output_size'])
        self.assertEqual(stage['partial_observations'],[[i+1,v] for i,v in enumerate(f['observations'])])
        self.assertEqual(f['source_sha256'],stage['source_sha256'])
        self.assertEqual(report['trusted_input_sha256'],stage['input_sha256'])
        self.assertEqual(report['nonce'],stage['nonce'])
        self.assertTrue(report['native_measurement_accepted'])
        for path,digest in f['input_sha256'].items():
            if 'configuration_xdto' in path:
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
    def replay(self,number):
        # The native probe executes BSL in a loaded configuration, not in the
        # separate scalar ConfigurationApplication command envelope.
        sources=files(self.linked)
        sources['Ext/ManagedApplicationModule.bsl']=b''
        out=[];app=SourceApplication(import_source(sources),output=out.append)
        self.addCleanup(app.close);self.assertTrue(app.start())
        app.interpreter.execute(replay_source(self.linked,number))
        self.assertEqual(out,[self.fixture()['observations'][number-1]])

class LinkedNativeReplay(CoreNativeReplay):
    linked=True
    native_run=43089477510


class ConfigurationCommandIsolationTests(unittest.TestCase):
    def test_unadmitted_native_probe_cannot_silently_switch_to_source_application(self):
        out=[];app=ConfigurationApplication.from_files(files(),output=out.append)
        self.addCleanup(app.close,force=True);app.start()
        # This routine-bearing XDTO program is outside today's scalar command
        # admission. Do not fall through to another application on refusal.
        with self.assertRaisesRegex(PythonDirectUnsupported, 'direct configuration commands'):
            app.execute(replay_source(False,6))
        self.assertEqual(out,[])

for number in range(1,13):
    setattr(CoreNativeReplay,f'test_native_{number:02}',lambda self,n=number:self.replay(n))
