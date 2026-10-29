"""Fixed source staging, closed CLI and authenticated Description8 handoff."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_catalog_reference_route as old
import test_native_catalog_description_policy as facts
import inputs
import protocol
host=old.host

class DescriptionHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.addCleanup(lambda:old.old.old.writable(self.root))
    def test_exact_stage_and_source_bound_flags(self):
        for case in ('description8','description17'):
            prov=facts.provenance();prov['actual_version']=None;prov['sources']=inputs.source_hashes(old.old.ROOT,description_case=case)
            stage=self.root/case
            inputs.stage_inputs(old.old.ROOT,stage,facts.NONCE,prov,description_case=case)
            self.assertEqual(inputs.verify_inputs(stage,facts.NONCE,description_case=case),prov)
            data=protocol.decode((stage/'invocation.json').read_bytes())
            self.assertEqual(set(data),{'schema','lane','nonce','provenance','description_case'})
            self.assertEqual((data['schema'],data['description_case']),(27,case))
            command=host.container_command(stage,'onec-db-oracle-'+'a'*32,facts.NONCE,description_case=case)
            self.assertEqual(command[-1],'--catalog-description-'+case.removeprefix('description'))
            with self.assertRaises(Exception):inputs.verify_inputs(stage,facts.NONCE,reference_case='distinct_a',reference_rows=True)
            program="""import sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
import catalog_description_policy, catalog_description_measurement, catalog_description_physical
modules=catalog_description_physical.loader._load_storage()
for module in modules.values():
    if Path(module.__file__).resolve().parent != root:raise SystemExit(1)
from catalog_description_measurement import transform
transform((root/'metadata/Catalog.xml').read_bytes(),name='metadata/Catalog.xml',case='description8')
transform((root/'modules/NativeOracleServer.bsl').read_bytes(),name='modules/NativeOracleServer.bsl',case='description8')
"""
            completed=subprocess.run([sys.executable,'-I','-B','-c',program,str(stage)],capture_output=True)
            self.assertEqual(completed.returncode,0,completed.stderr.decode())
            hook=stage/'modules/CatalogDescriptionObservation.bsl';hook.chmod(0o600);hook.write_bytes(hook.read_bytes()+b'\n')
            with self.assertRaises(Exception):inputs.verify_inputs(stage,facts.NONCE,description_case=case)
    @unittest.skipUnless(old.DESCRIPTOR_HANDOFF,'POSIX no-follow handoff')
    def test_same_run_case_digest_and_exact_artifact(self):
        report=facts.fixture();raw=protocol.encode(report)+b'\n'
        parent=self.root/'native-db-oracle';parent.mkdir();path=parent/'description8.json';path.write_bytes(raw)
        info=self.root.stat();identity=(info.st_dev,info.st_ino)
        env={'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','DESCRIPTION8_RUN_ID':'123',
             'DESCRIPTION8_RUN_ATTEMPT':'2','DESCRIPTION8_SHA256':hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'provenance',return_value=report['provenance']),mock.patch.dict(os.environ,env,clear=True):
            self.assertEqual(host.validate_description8(identity),raw)
            self.assertEqual(host.main(['--validate-description8']),0)
            for key in env:
                with mock.patch.dict(os.environ,{key:'bad'}):
                    with self.assertRaises(Exception):host.validate_description8(identity)
            (parent/'extra.json').write_bytes(b'{}')
            with self.assertRaises(Exception):host.validate_description8(identity)
            (parent/'extra.json').unlink()
            path.unlink();path.symlink_to(parent/'other')
            with self.assertRaises(Exception):host.validate_description8(identity)
    def test_description_cli_routes_only_selected_case(self):
        for case in ('description8','description17'):
            report=facts.fixture(case,nonce='b'*32 if case=='description17' else facts.NONCE)
            prior=protocol.encode(facts.fixture())+b'\n'
            with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'run_oracle',return_value=report) as run,\
                 mock.patch.object(host,'export_report') as export,mock.patch.object(host,'validate_description8',return_value=prior),\
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2'},clear=True):
                self.assertEqual(host.main(['--execute-approved-image','--file-db-oracle','--catalog-description',case,'--output','native-db-oracle/'+case+'.json']),0)
                self.assertEqual(run.call_args.kwargs,{'description_case':case})
                self.assertEqual(export.call_args_list[0].kwargs['output'],host.DESCRIPTION_OUTPUTS[case])
                self.assertEqual(export.call_count,1 if case=='description8' else 2)

if __name__=='__main__':unittest.main()
