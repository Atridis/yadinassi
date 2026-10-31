"""Real opt-in staging/CLI/probe boundaries with synthetic reports; no native run."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import test_native_catalog_zero_code_host as old
import test_native_catalog_zero_code_probe as probe
import test_native_catalog_zero_code_rows_policy as facts
import inputs
import protocol
import run as container
host = old.host
ROOT = Path(__file__).resolve().parents[1]


class ZeroRowsIntegrationTests(unittest.TestCase):
    setUp = old.NumericCodeHostTests.setUp

    def test_exact_inventory_and_strict_boolean_selection(self):
        before = set(inputs.CATALOG_ZERO_CODE_SOURCE_FILES)
        after = set(inputs.CATALOG_ZERO_CODE_ROWS_SOURCE_FILES)
        self.assertEqual(len(after),43)
        self.assertEqual(before-after,{'scripts/native_1c_db_oracle/catalog_zero_code_policy.py'})
        self.assertEqual(after-before,{'scripts/native_1c_db_oracle/catalog_zero_code_rows_policy.py',
                                      'scripts/native_1c_db_oracle/catalog_zero_code_rows_reader.py'})
        self.assertEqual(set(inputs.source_hashes(ROOT,zero_case='zero0',zero_rows=True)),after)
        for options in ({'zero_rows':True},{'zero_case':'zero0','zero_rows':1},
                        {'zero_case':'zero0','zero_rows':None},
                        {'zero_case':'zero0','zero_rows':True,'numeric_case':'number3'},
                        {'zero_case':'zero0','zero_rows':True,'description_rows':True}):
            with self.subTest(options=options):
                with self.assertRaises(Exception):inputs.inventory(**options)
                with self.assertRaises(Exception):container.Native(facts.NONCE,facts.provenance(),**options)
        for bad in (1,None,'true'):
            with self.assertRaises(Exception):host.validate_zero_code0((0,0),zero_rows=bad)
            with self.assertRaises(Exception):host.read_zero_code0((0,0),zero_rows=bad)

    def test_stage_container_cold_import_and_exact_probe_argv(self):
        for case in ('zero0','zero8'):
            prov=facts.provenance();prov['actual_version']=None
            prov['sources']=inputs.source_hashes(ROOT,zero_case=case,zero_rows=True)
            stage=self.root/case
            inputs.stage_inputs(ROOT,stage,facts.NONCE,prov,zero_case=case,zero_rows=True)
            self.assertEqual(inputs.verify_inputs(stage,facts.NONCE,zero_case=case,zero_rows=True),prov)
            invocation=protocol.decode((stage/'invocation.json').read_bytes())
            self.assertEqual(set(invocation),{'schema','lane','nonce','provenance','zero_case'})
            self.assertEqual((invocation['schema'],invocation['lane'],invocation['zero_case']),
                             (33,inputs.CATALOG_ZERO_CODE_ROWS_LANE,case))
            with self.assertRaises(Exception):inputs.verify_inputs(stage,facts.NONCE,zero_case=case)
            command=host.container_command(stage,'onec-db-oracle-'+'a'*32,facts.NONCE,zero_case=case,zero_rows=True)
            self.assertEqual(command[-1],'--catalog-zero-code-rows-'+case.removeprefix('zero'))
            result=probe.dispatch(command[-3:])
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.splitlines(),['-B','/oracle/run.py',*command[-3:]])
            report=facts.fixture(case);report['provenance']={**prov,'actual_version':protocol.VERSION}
            final_path=self.root/(case+'-final.json');final_path.write_bytes(protocol.encode(report))
            program='''import sys,json
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root))
import catalog_zero_code_rows_policy as p
raw=Path(sys.argv[2]).read_bytes();report=json.loads(raw)
p.validate_report(raw,nonce=report['nonce'],provenance=report['provenance'],final=True)
import catalog_zero_code_rows_reader, run
run.INPUTS=root
report['accepted']=False
report['cleanup'].update(container_removed=False,private_staging_removed=False)
run.Controller.run=lambda self:report
sys.argv=['run.py','--invocation-nonce',report['nonce'],'--catalog-zero-code-rows-'+report['zero_case'].removeprefix('zero')]
if run.main()!=0:raise SystemExit(1)
'''
            completed=subprocess.run([sys.executable,'-I','-B','-c',program,str(stage),str(final_path)],capture_output=True)
            self.assertEqual(completed.returncode,0,completed.stderr.decode())
            self.assertEqual(protocol.decode(completed.stdout)['schema'],68)
            policy=stage/'catalog_zero_code_rows_reader.py';policy.chmod(0o600);policy.write_bytes(policy.read_bytes()+b'\n')
            with self.assertRaises(Exception):inputs.verify_inputs(stage,facts.NONCE,zero_case=case,zero_rows=True)

    def test_probe_rejects_unknown_rows_cases_and_extra_flags(self):
        for args in (['--invocation-nonce',facts.NONCE,'--catalog-zero-code-rows-17'],
                     ['--invocation-nonce',facts.NONCE,'--catalog-zero-code-rows-0','extra'],
                     ['--invocation-nonce','A'*32,'--catalog-zero-code-rows-0']):
            result=probe.dispatch(args)
            self.assertEqual(result.returncode,2)
            self.assertEqual(result.stdout,'')

    def test_selected_missing_credentials_failure(self):
        prov=facts.provenance();prov['actual_version']=None
        prov['sources']=inputs.source_hashes(ROOT,zero_case='zero0',zero_rows=True)
        with mock.patch.object(host,'provenance',return_value=prov),mock.patch.dict(os.environ,{},clear=True):
            report=host.run_oracle(self.root,zero_case='zero0',zero_rows=True)
        self.assertEqual(report['schema'],68)
        self.assertEqual(report['failure_kind'],'registry_credentials_missing')
        self.assertIsNone(report['zero_code_rows_measurement'])
        self.assertTrue(all(report['cleanup'].values()))

    def test_host_cli_routes_selected_case_and_aggregate(self):
        for case in ('zero0','zero8'):
            report=facts.fixture(case,nonce='b'*32 if case=='zero8' else facts.NONCE)
            prior=protocol.encode(facts.fixture('zero0'))+b'\n'
            with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'run_oracle',return_value=report) as execute, \
                 mock.patch.object(host,'export_report') as export,mock.patch.object(host,'validate_zero_code0',return_value=prior) as validate, \
                 mock.patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2'},clear=True):
                self.assertEqual(host.main(['--execute-approved-image','--file-db-oracle','--catalog-zero-code-rows',case,
                                            '--output',str(host.ZERO_CODE_ROWS_OUTPUTS[case])]),0)
                self.assertEqual(execute.call_args.kwargs,{'zero_case':case,'zero_rows':True})
                self.assertEqual(export.call_args_list[0].kwargs['output'],host.ZERO_CODE_ROWS_OUTPUTS[case])
                self.assertEqual(export.call_count,1 if case=='zero0' else 2)
                if case=='zero8':
                    self.assertEqual(validate.call_args.kwargs,{'zero_rows':True})
                    self.assertEqual(export.call_args_list[1].kwargs['output'],host.ZERO_CODE_ROWS_AGGREGATE)
                else:validate.assert_not_called()
        for args in (['--catalog-zero-code-rows','foreign'],['--catalog-zero-code-rows-0'],
                     ['--catalog-zero-code-rows','zero0','--catalog-zero-code','zero0']):
            with mock.patch.object(host,'run_oracle') as execute,self.assertRaises(SystemExit):host.main(args)
            execute.assert_not_called()

    @unittest.skipUnless(old.old.DESCRIPTOR_HANDOFF,'POSIX no-follow handoff')
    def test_rows_handoff_digest_case_source_and_exact_filename(self):
        report=facts.fixture('zero0');raw=protocol.encode(report)+b'\n'
        parent=self.root/'native-db-oracle';parent.mkdir()
        path=parent/host.ZERO_CODE_ROWS_OUTPUTS['zero0'].name;path.write_bytes(raw)
        info=self.root.stat();identity=(info.st_dev,info.st_ino)
        env={'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','ZERO_CODE_ROWS0_RUN_ID':'123',
             'ZERO_CODE_ROWS0_RUN_ATTEMPT':'2','ZERO_CODE_ROWS0_SHA256':hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(host,'ROOT',self.root),mock.patch.object(host,'provenance',return_value=report['provenance']) as provenance, \
             mock.patch.dict(os.environ,env,clear=True):
            self.assertEqual(host.validate_zero_code0(identity,zero_rows=True),raw)
            self.assertEqual(provenance.call_args.kwargs,{'zero_case':'zero8','zero_rows':True})
            self.assertEqual(host.main(['--validate-zero-code-rows0']),0)
            for key in env:
                with mock.patch.dict(os.environ,{key:'bad'}):
                    with self.assertRaises(Exception):host.validate_zero_code0(identity,zero_rows=True)
            with self.assertRaises(Exception):host.validate_zero_code0(identity)
            changed={**report['provenance'],'sources':dict(report['provenance']['sources'])}
            changed['sources'][next(iter(changed['sources']))]='d'*64
            with mock.patch.object(host,'provenance',return_value=changed):
                with self.assertRaises(Exception):host.validate_zero_code0(identity,zero_rows=True)
            (parent/'zero_code0.json').write_bytes(raw)
            with self.assertRaises(Exception):host.validate_zero_code0(identity,zero_rows=True)
            (parent/'zero_code0.json').unlink()
            for bad in (b'{}',protocol.encode(facts.fixture('zero8'))):
                path.write_bytes(bad);os.environ['ZERO_CODE_ROWS0_SHA256']=hashlib.sha256(bad).hexdigest()
                with self.assertRaises(Exception):host.validate_zero_code0(identity,zero_rows=True)
            path.unlink();path.symlink_to(parent/'other')
            with self.assertRaises(Exception):host.validate_zero_code0(identity,zero_rows=True)

if __name__=='__main__':unittest.main()
