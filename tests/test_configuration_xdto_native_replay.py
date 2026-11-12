import hashlib
import json
import unittest
from configuration_xdto_fixture import ROOT, files
from yadinassi.configuration_runtime import ConfigurationApplication

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
        out=[];app=ConfigurationApplication.from_files(files(self.linked),output=out.append)
        self.addCleanup(app.close,force=True);app.start()
        folder=ROOT/'scripts'/('configuration_xdto_linked_behavior' if self.linked else 'configuration_xdto_behavior')
        source=(folder/'observe.bsl').read_text(encoding='utf-8').split('\nFor CaseNo = 1 To 12 Do')[0]
        app.execute(source+f'\nStage="";Message(ObserveCase({number},Stage));')
        self.assertEqual(out,[self.fixture()['observations'][number-1]])

class LinkedNativeReplay(CoreNativeReplay):
    linked=True
    native_run=43089477510

for number in range(1,13):
    setattr(CoreNativeReplay,f'test_native_{number:02}',lambda self,n=number:self.replay(n))
