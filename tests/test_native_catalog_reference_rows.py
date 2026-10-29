"""Complete invented images through typed native policy; no native claim."""
from dataclasses import replace
import copy
import hashlib
import io
import os
import shutil
import types
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from uuid import UUID

import test_native_catalog_reference_codec as old
import test_native_catalog_codec_seed as seed
import test_native_catalog_reference_codec_budget as budget
import catalog_reference_rows as policy
import inputs
import protocol
from contract import source_binding

ROOT = Path(__file__).resolve().parents[1]
adapter = old.lifecycle.old.coordinator


def fixture(case='distinct_a', nonce=None):
    report = old.fixture(case, nonce)
    report.update(schema=45,lane=policy.LANE,record_validation=policy.VERDICT)
    report['provenance']['sources'] = {key:'c'*64 for key in inputs.CATALOG_ROWS_SOURCE_FILES}
    capture=report['record_readback']
    capture.update(schema=46,profile_id=policy.PROFILE_ID,profile_sha256=policy.PROFILE_SHA256)
    capture['audit']['source_manifest_sha256']=source_binding(report['provenance'])
    for state in capture['states']:
        state['projection']='NN' if state['snapshot']=='baseline' else 'TT'
    return report


def validate(report):
    return policy.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=report['provenance'],final=True)


class ByteBackend(old.ByteBackend):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.record_policy=policy
        self.reference_codec=False
        self.reference_rows=True


def run_fixture(test,**kwargs):
    temp=tempfile.TemporaryDirectory();test.addCleanup(temp.cleanup)
    provenance=fixture()['provenance']
    report=policy.empty_report(old.lifecycle.old.old.NONCE,provenance,reference_case=kwargs.get('case','distinct_a'))
    backend=ByteBackend(Path(temp.name).resolve(),provenance,**kwargs)
    controller=old.lifecycle.old.old.fixture.stage.Controller(backend,report);backend.controller=controller
    return controller.run(),backend


class RowsPolicyTests(unittest.TestCase):
    def test_closed_inventory_profile_complete_pair(self):
        a,b=fixture(),fixture('distinct_b','b'*32)
        validate(a)
        aggregate=policy.aggregate_reports(protocol.encode(a),protocol.encode(b),provenance=a['provenance'])
        self.assertEqual((aggregate['schema'],aggregate['projected_comparisons'],aggregate['codec_comparisons']),(47,8,16))
        self.assertTrue(aggregate['rows_verified'])
        self.assertEqual(len(inputs.CATALOG_ROWS_SOURCE_FILES),43)
        self.assertEqual(inputs.inventory(reference_case='distinct_a',reference_rows=True),inputs.CATALOG_ROWS_SOURCE_FILES)
        for flags in ({'reference_rows':True},{'reference_case':'distinct_a','reference_rows':True,'reference_codec':True},{'reference_case':'distinct_a','reference_rows':1}):
            with self.assertRaises(Exception):inputs.inventory(**flags)
        with self.assertRaises(Exception):old.validate(a)
        with self.assertRaises(Exception):validate(old.fixture())

    def test_missing_or_false_coverage_and_source_fail(self):
        for index in range(3):
            for bad in (None,True,'N','TTT','FF','NN' if index else 'TT'):
                report=fixture();report['record_readback']['states'][index]['projection']=bad
                with self.assertRaises(Exception):validate(report)
            report=fixture();del report['record_readback']['states'][index]['projection']
            with self.assertRaises(Exception):validate(report)
        for name in (policy.MODULE_SOURCE,policy.READER_SOURCE,policy.CODEC_SOURCE):
            report=fixture();del report['provenance']['sources'][name]
            with self.assertRaises(Exception):validate(report)
        report=fixture();report['record_readback']['states'][1]['codec']='TTTF'
        with self.assertRaises(Exception):validate(report)

    def test_container_main_selects_only_new_fixed_policy(self):
        for case in policy.CASES:
            report=fixture(case)
            report['accepted']=False
            report['cleanup'].update(container_removed=False,private_staging_removed=False)
            out=io.BytesIO()
            stage=seed.fixture.stage
            with mock.patch.object(stage.sys,'argv',['run.py','--invocation-nonce',report['nonce'],
                    '--catalog-reference-rows-'+case.replace('_','-')]), \
                 mock.patch.object(inputs,'verify_inputs',return_value=report['provenance']) as verify, \
                 mock.patch.object(stage,'Native') as native, \
                 mock.patch.object(stage,'Controller') as controller, \
                 mock.patch.object(stage.sys,'stdout',types.SimpleNamespace(buffer=out)):
                controller.return_value.run.return_value=report
                self.assertEqual(stage.main(),0)
            self.assertEqual(verify.call_args.kwargs,{'reference_case':case,'reference_rows':True})
            self.assertEqual(native.call_args.kwargs,{'reference_case':case,'reference_rows':True})
            self.assertEqual(controller.call_args.args[1]['schema'],45)
            self.assertEqual(protocol.decode(out.getvalue()),report)

    def test_unchanged_caps_full_envelope(self):
        envelope=budget.report_envelope()
        envelope.update(schema=45,lane=policy.LANE,record_validation=policy.VERDICT)
        envelope['provenance']['sources']={key:'c'*64 for key in inputs.CATALOG_ROWS_SOURCE_FILES}
        bound=len(budget.previous.wire(envelope))-4+policy.MAX_CAPTURE_BYTES+1
        capture=budget.capture_envelope()
        capture.update(schema=46,profile_id=policy.PROFILE_ID,profile_sha256=policy.PROFILE_SHA256)
        for state in capture['states']:state['projection']='NN' if state['snapshot']=='baseline' else 'TT'
        self.assertEqual(bound,28788)
        self.assertEqual(len(budget.previous.wire(capture)),3545)
        self.assertLessEqual(bound,32768)
        self.assertLessEqual(len(budget.previous.wire(capture)),8192)
        self.assertEqual(policy.MAX_CAPTURE_BYTES,8192)
        self.assertEqual(protocol.MAX_REPORT_BYTES,32768)
        actual=fixture()['record_readback']
        self.assertEqual(set(capture),set(actual))
        for a,b in zip(actual['states'],capture['states']):self.assertEqual(set(a),set(b))
        report=fixture();report['record_readback']['overflow']='x'*8192
        with self.assertRaises(Exception) as caught:validate(report)
        self.assertEqual(str(caught.exception),'artifact_limit')


@unittest.skipUnless(old.lifecycle.old.old.POSIX,'requires descriptor-relative POSIX operations')
class RowsLifecycleTests(unittest.TestCase):
    def setUp(self):old.lifecycle.old.old.normalize_owners(self)

    def test_actual_typed_api_once_per_image_both_cases(self):
        for case in policy.CASES:
            original=adapter.read_catalog_rows
            calls=[]
            def read(read_at,size,**kwargs):
                calls.append(set(kwargs));return original(read_at,size,**kwargs)
            with mock.patch.object(adapter,'read_catalog_rows',side_effect=read), mock.patch.object(adapter,'read_catalog_binding',side_effect=AssertionError('raw fallback')):
                report,backend=run_fixture(self,case=case)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(calls,[{'catalog_name','limits'}]*6)
            self.assertEqual([s['projection'] for s in report['record_readback']['states']],['NN','TT','TT'])
            self.assertEqual([s['codec'] for s in report['record_readback']['states']],['NNNN','TTTT','TTTT'])
            report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
            validate(report)
            self.assertFalse(list(backend.artifacts.iterdir()))

    def test_wrong_typed_uuid_detached_missing_reordered_rows_fail(self):
        original=adapter.read_catalog_rows
        for mode in ('uuid','detached','missing','duplicate','reordered','wrong_type'):
            def altered(*a,**k):
                result=original(*a,**k)
                if not result.rows:return result
                row=result.rows[0]
                if mode=='uuid':row=replace(row,reference_uuid=UUID(int=0))
                elif mode=='detached':row=replace(row,physical_record=replace(row.physical_record))
                elif mode=='wrong_type':return adapter._raw_rows_view(result)
                elif mode=='reordered':
                    other=replace(row.physical_record,slot=row.physical_record.slot+1)
                    return replace(result,records=replace(result.records,rows=(row.physical_record,other)),
                        rows=(replace(row,physical_record=other),row))
                rows=() if mode=='missing' else (row,row) if mode=='duplicate' else (row,)
                return replace(result,rows=rows)
            with mock.patch.object(adapter,'read_catalog_rows',side_effect=altered), mock.patch.object(old.codec,'decode_catalog_reference_uuid',wraps=old.codec.decode_catalog_reference_uuid) as raw_codec:
                report,backend=run_fixture(self)
            self.assertEqual(report['status'],'failed',report)
            self.assertFalse(report['accepted'])
            self.assertEqual(raw_codec.call_count,1 if mode=='uuid' else 0)
            self.assertTrue(report['cleanup']['raw_files_removed'])
            self.assertFalse(list(backend.artifacts.iterdir()))
            report['cleanup'].update(container_removed=True,private_staging_removed=True)
            validate(report)

    def test_bad_digest_prevents_projection_check(self):
        for fault in ('origin','postimage','token','module'):
            with mock.patch.object(policy,'verify_projection',wraps=policy.verify_projection) as verified:
                report,backend=run_fixture(self,fault=fault)
            self.assertEqual(report['status'],'failed')
            # baseline comparisons occur before created-image faults; module
            # faults fail even earlier. Corrupt postimage permits origin only.
            expected=0 if fault in ('module','token') else 3 if fault=='postimage' else 2
            self.assertEqual(verified.call_count,expected)

    def test_projection_budget_failure_is_fail_closed(self):
        runtime=adapter._load_storage(project_rows=True)['catalog_reader']
        with mock.patch.object(runtime,'_project_rows',side_effect=runtime.catalog_module.ResourceLimit('output_bytes')):
            report,backend=run_fixture(self)
        self.assertEqual(report['status'],'failed')
        self.assertFalse(list(backend.artifacts.iterdir()))


class RowsSeedTests(seed.CodecSeedTests):
    def backend(self,case):
        # Reuse actual seed fixture but select the real fixed new policy.
        original=seed.fixture.stage.Native
        def native(*a,**k):
            k.pop('reference_codec');k['reference_rows']=True
            return original(*a,**k)
        with mock.patch.object(seed.fixture.stage,'Native',side_effect=native):
            return super().backend(case)

    def test_real_seed_both_cases_hashes_module_and_builds_manifest(self):
        with mock.patch.object(seed,'policy',policy):super().test_real_seed_both_cases_hashes_module_and_builds_manifest()

    def test_missing_alias_reproduces_failure_after_dump_before_import(self):
        with mock.patch.object(seed,'policy',policy):super().test_missing_alias_reproduces_failure_after_dump_before_import()

    def test_every_runtime_record_policy_attribute_is_present(self):
        with mock.patch.object(seed,'policy',policy):super().test_every_runtime_record_policy_attribute_is_present()


class StagedRowsTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'real bash dispatch boundary')
    def test_actual_probe_shell_dispatch_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); stub=root/'python3'; log=root/'argv'
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$DISPATCH_LOG"\n')
            stub.chmod(0o755)
            env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ.get('PATH',''),DISPATCH_LOG=str(log))
            probe=ROOT/'scripts/native_1c_db_oracle/probe.sh'
            for case in ('a','b'):
                flag='--catalog-reference-rows-distinct-'+case
                result=subprocess.run([shutil.which('bash'),str(probe),'--invocation-nonce','a'*32,flag],env=env)
                self.assertEqual(result.returncode,0)
                self.assertEqual(log.read_text().splitlines(),['-B','/oracle/run.py','--invocation-nonce','a'*32,flag])
                log.unlink()
            for flag in ('--catalog-reference-rows-distinct-c','--catalog-reference-rows','--catalog-reference-rows-distinct-a extra'):
                result=subprocess.run([shutil.which('bash'),str(probe),'--invocation-nonce','a'*32,flag],env=env)
                self.assertEqual(result.returncode,2)
                self.assertFalse(log.exists())


    def test_real_staged_exact_sibling_loader_cold_and_missing_codec(self):
        import test_catalog_rows as image_fixture
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);stage=directory/'stage';image=directory/'image'
            image.write_bytes(image_fixture.source().full_bytes())
            provenance=fixture()['provenance']
            provenance['sources']=inputs.source_hashes(ROOT,reference_case='distinct_a',reference_rows=True)
            inputs.stage_inputs(ROOT,stage,'a'*32,provenance,reference_case='distinct_a',reference_rows=True)
            code='''import pathlib,sys,types
sys.path.insert(0,sys.argv[1])
import catalog_binding_reader as adapter
raw=pathlib.Path(sys.argv[2]).read_bytes()
result=adapter.read_catalog_rows(lambda o,n:raw[o:o+n],len(raw),catalog_name='NativeOracleItems')
assert str(result.rows[0].reference_uuid)=='00112233-4455-4677-8899-aabbccddeeff'
view=adapter._raw_rows_view(result)
assert view.records is result.records
foreign=types.ModuleType('foreign');foreign.__file__='/not/the/codec.py'
sys.modules[adapter._PACKAGE+'.catalog_reference_uuid']=foreign
try:adapter._load_storage(project_rows=True)
except ValueError:pass
else:raise AssertionError('foreign codec admitted')
print('STAGED_ROWS_OK')
'''
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(stage),str(image)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,'STAGED_ROWS_OK\n')
            stage.chmod(0o755);(stage/'catalog_reference_uuid.py').chmod(0o644);(stage/'catalog_reference_uuid.py').unlink()
            result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(stage),str(image)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('binding_reader_sources',result.stderr)
            with self.assertRaises(Exception):inputs.verify_inputs(stage,'a'*32,reference_case='distinct_a',reference_rows=True)
