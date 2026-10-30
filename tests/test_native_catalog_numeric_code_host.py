"""Fixed source staging, closed CLI and authenticated Description8 handoff."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest import mock
import test_native_catalog_reference_route as old
import test_native_catalog_numeric_code_policy as facts
import inputs
import protocol
host=old.host

class NumericCodeHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.addCleanup(lambda:old.old.old.writable(self.root))
    def test_real_host_missing_credentials_failure_uses_selected_policy(self):
        for rows,schema in ((True,59),):
            prov=facts.provenance();prov['actual_version']=None
            prov['sources']=inputs.source_hashes(old.old.ROOT,numeric_case='number3')
            with mock.patch.object(host,'provenance',return_value=prov),mock.patch.dict(os.environ,{},clear=True):
                report=host.run_oracle(self.root,numeric_case='number3')
            self.assertEqual(report['schema'],schema)
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['failure_kind'],'registry_credentials_missing')
            self.assertIsNone(report['numeric_code_measurement'])
            self.assertTrue(all(report['cleanup'].values()))
    def test_mode_types_exclusion_unknown_flags_and_current_source_change(self):
        for options in ({'params_slots':True}, {'numeric_case':'number3','params_slots':1},
                        {'numeric_case':'number3','params_slots':True,'description_rows':True},
                        {'numeric_case':'number3','params_slots':True,'reference_case':'distinct_a'}):
            with self.subTest(options=options),self.assertRaises(Exception):inputs.inventory(**options)
        for args in (['--catalog-numeric-code','foreign'],['--catalog-numeric-code-3'],
                     ['--catalog-numeric-code','number3','--catalog-description-rows','number3']):
            with mock.patch.object(host,'run_oracle') as run,self.assertRaises(SystemExit):host.main(args)
            run.assert_not_called()
        current=inputs.source_hashes(old.old.ROOT,numeric_case='number3')
        self.assertEqual(set(current),set(inputs.CATALOG_NUMERIC_CODE_SOURCE_FILES))
        self.assertEqual(len(current),42)

    def test_exact_stage_and_source_bound_flags(self):
        for case in ('number3','number6'):
            prov=facts.provenance();prov['actual_version']=None;prov['sources']=inputs.source_hashes(old.old.ROOT,numeric_case=case)
            stage=self.root/case
            inputs.stage_inputs(old.old.ROOT,stage,facts.NONCE,prov,numeric_case=case)
            self.assertEqual(inputs.verify_inputs(stage,facts.NONCE,numeric_case=case),prov)
            data=protocol.decode((stage/'invocation.json').read_bytes())
            self.assertEqual(set(data),{'schema','lane','nonce','provenance','numeric_case'})
            self.assertEqual((data['schema'],data['numeric_case']),(30,case))
            command=host.container_command(stage,'onec-db-oracle-'+'a'*32,facts.NONCE,numeric_case=case)
            self.assertEqual(command[-1],'--catalog-numeric-code-'+case.removeprefix('number'))
            with self.assertRaises(Exception):inputs.verify_inputs(stage,facts.NONCE,reference_case='distinct_a',reference_rows=True)
            program="""import sys
from pathlib import Path, PureWindowsPath
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
import catalog_numeric_code_policy, catalog_numeric_code_physical
modules=catalog_numeric_code_physical.loader._load_storage(project_rows=True)
for module in modules.values():
    if Path(module.__file__).resolve().parent != root:raise SystemExit(1)
from catalog_numeric_code_measurement import transform
transform((root/'metadata/Catalog.xml').read_bytes(),name='metadata/Catalog.xml',case='number3')
transform((root/'modules/NativeOracleServer.bsl').read_bytes(),name='modules/NativeOracleServer.bsl',case='number3')
"""
            completed=subprocess.run([sys.executable,'-I','-B','-c',program,str(stage)],capture_output=True)
            self.assertEqual(completed.returncode,0,completed.stderr.decode())
            # Cold FINAL first: no helper/reader import may preinitialize policy state.
            report=facts.fixture(case);report['provenance']={**prov,'actual_version':protocol.VERSION}
            final_path=self.root/(case+'-final.json');final_path.write_bytes(protocol.encode(report))
            cold="""import sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import catalog_numeric_code_policy
raw=Path(sys.argv[2]).read_bytes();report=json.loads(raw)
catalog_numeric_code_policy.validate_report(raw,nonce=report['nonce'],provenance=report['provenance'],final=True)
"""
            completed=subprocess.run([sys.executable,'-I','-B','-c',cold,str(stage),str(final_path)],capture_output=True)
            self.assertEqual(completed.returncode,0,completed.stderr.decode())
            hook=stage/'modules/CatalogNumericCodeObservation.bsl';hook.chmod(0o600);hook.write_bytes(hook.read_bytes()+b'\n')
            with self.assertRaises(Exception):inputs.verify_inputs(stage,facts.NONCE,numeric_case=case)
    @unittest.skipUnless(old.DESCRIPTOR_HANDOFF,'POSIX no-follow handoff')
    def test_same_run_case_digest_and_exact_artifact(self):
        report=facts.fixture();raw=protocol.encode(report)+b'\n'
        parent=self.root/'native-db-oracle';parent.mkdir();path=parent/'numeric_code3.json';path.write_bytes(raw)
        info=self.root.stat();identity=(info.st_dev,info.st_ino)
        env={'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','NUMERIC_CODE3_RUN_ID':'123',
             'NUMERIC_CODE3_RUN_ATTEMPT':'2','NUMERIC_CODE3_SHA256':hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'provenance',return_value=report['provenance']),mock.patch.dict(os.environ,env,clear=True):
            self.assertEqual(host.validate_numeric_code3(identity),raw)
            self.assertEqual(host.main(['--validate-numeric-code3']),0)
            for key in env:
                with mock.patch.dict(os.environ,{key:'bad'}):
                    with self.assertRaises(Exception):host.validate_numeric_code3(identity)
            (parent/'extra.json').write_bytes(b'{}')
            with self.assertRaises(Exception):host.validate_numeric_code3(identity)
            (parent/'extra.json').unlink()
            path.unlink();path.symlink_to(parent/'other')
            with self.assertRaises(Exception):host.validate_numeric_code3(identity)
    def test_description_cli_routes_only_selected_case(self):
        for case in ('number3','number6'):
            report=facts.fixture(case,nonce='b'*32 if case=='number6' else facts.NONCE)
            prior=protocol.encode(facts.fixture())+b'\n'
            with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'run_oracle',return_value=report) as run,\
                 mock.patch.object(host,'export_report') as export,mock.patch.object(host,'validate_numeric_code3',return_value=prior),\
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2'},clear=True):
                self.assertEqual(host.main(['--execute-approved-image','--file-db-oracle','--catalog-numeric-code',case,'--output',str(host.NUMERIC_CODE_OUTPUTS[case])]),0)
                self.assertEqual(run.call_args.kwargs,{'numeric_case':case})
                self.assertEqual(export.call_args_list[0].kwargs['output'],host.NUMERIC_CODE_OUTPUTS[case])
                self.assertEqual(export.call_count,1 if case=='number3' else 2)

    def test_windows_output_spelling_keeps_strict_guard(self):
        outputs={case:PureWindowsPath('native-db-oracle')/(case.replace('number','numeric_code')+'.json') for case in ('number3','number6')}
        for case in outputs:
            report=facts.fixture(case,nonce='b'*32 if case=='number6' else facts.NONCE)
            prior=protocol.encode(facts.fixture())+b'\n'
            with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'NUMERIC_CODE_OUTPUTS',outputs),\
                 mock.patch.object(host,'run_oracle',return_value=report) as run,\
                 mock.patch.object(host,'export_report') as export,mock.patch.object(host,'validate_numeric_code3',return_value=prior),\
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2'},clear=True):
                prefix=['--execute-approved-image','--file-db-oracle','--catalog-numeric-code',case,'--output']
                for wrong in ('native-db-oracle/'+case.replace('number','numeric_code')+'.json',str(outputs[case].with_name('other.json'))):
                    with self.assertRaises(SystemExit) as caught:host.main(prefix+[wrong])
                    self.assertEqual(caught.exception.code,2)
                    run.assert_not_called();export.assert_not_called()
                self.assertEqual(host.main(prefix+[str(outputs[case])]),0)
                self.assertEqual(run.call_args.kwargs,{'numeric_case':case})
                self.assertEqual(export.call_args_list[0].kwargs['output'],outputs[case])

if __name__=='__main__':unittest.main()
