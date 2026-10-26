"""Closed exact stored-byte chain routes and synthetic postimages; no native execution."""
from __future__ import annotations
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'scripts'),str(ROOT/'tests')]
import inputs
import config_blob_chain as policy
import protocol
import record_observation as metadata
import snapshots
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_record_route as old
from test_native_1c_db_oracle_catalog_reader import normalize_owners
from test_native_1c_db_oracle_config_blob_chain_policy import source
from test_native_1c_db_oracle_config_entry_reference_reader import row
from test_native_1c_db_oracle_config_blob_chain_policy import identity,evidence,fixture
NONCE,TOKEN=old.NONCE,old.TOKEN
host=old.host


class ConfigBlobChainRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))

    def test_exact_inventory_and_mutually_exclusive_old_lanes(self):
        self.assertEqual(tuple(map(len,(inputs.LEGACY_V3_SOURCE_FILES,inputs.SOURCE_FILES,
            inputs.RECORD_SOURCE_FILES,inputs.ROW_SOURCE_FILES,inputs.CONFIG_BLOB_CHAIN_SOURCE_FILES))),(18,20,21,23,23))
        self.assertEqual(set(inputs.CONFIG_BLOB_CHAIN_SOURCE_FILES), set(inputs.RECORD_SOURCE_FILES)|{policy.MODULE_SOURCE,policy.FRAMING_READER_SOURCE})
        self.assertNotIn('scripts/native_1c_db_oracle/params_observation.py',inputs.CONFIG_BLOB_CHAIN_SOURCE_FILES)
        for options in ({},{'record_metadata':True},{'record_reader':True},{'params_transport':True},
                        {'params_extraction':True},{'dbnames_identity':True},{'config_transport':True},{'config_framing':True},{'config_marker_census':True},{'config_zero_marker_filename':True},{'config_entry_reference':True},{'config_blob_chain':True}):
            staged=self.root/('stage'+str(len(list(self.root.iterdir()))))
            provenance=identity(); provenance['sources']=inputs.source_hashes(ROOT,**options)
            inputs.stage_inputs(ROOT,staged,NONCE,provenance,**options)
            self.assertEqual(inputs.verify_inputs(staged,NONCE,**options),provenance)
            self.assertEqual((staged/'config_blob_chain.py').exists(),bool(options.get('config_blob_chain')))
            if options.get('config_blob_chain'):
                self.assertEqual(json.loads((staged/'invocation.json').read_text(encoding='utf-8'))['schema'],12)
                command=host.container_command(staged,'onec-db-oracle-'+'a'*32,NONCE,**options)
                self.assertEqual(command[-1],'--config-blob-chain-observation')
                for wrong in ({},{'record_metadata':True},{'record_reader':True},{'params_transport':True},
                              {'params_extraction':True},{'dbnames_identity':True},{'config_transport':True},{'config_framing':True},{'config_marker_census':True},{'config_zero_marker_filename':True},{'config_entry_reference':True}):
                    with self.assertRaises(OracleError): inputs.verify_inputs(staged,NONCE,**wrong)
        for name in ('record_metadata','record_reader','params_transport','params_extraction','dbnames_identity','config_transport','config_framing','config_marker_census','config_zero_marker_filename','config_entry_reference'):
            with self.assertRaises(OracleError): inputs.inventory(config_blob_chain=True,**{name:True})
        for bad in (1,None,'true'):
            with self.assertRaises(OracleError): inputs.inventory(config_blob_chain=bad)

    def test_invocation_admission_rejects_stale_missing_extra_or_tampered_fields(self):
        staged=self.root/'admission'
        provenance=identity(); provenance['sources']=inputs.source_hashes(ROOT,config_blob_chain=True)
        inputs.stage_inputs(ROOT,staged,NONCE,provenance,config_blob_chain=True)
        old.writable(staged)
        invocation=staged/'invocation.json'; original=json.loads(invocation.read_text(encoding='utf-8'))
        mutations=(lambda v:v.update(schema=4), lambda v:v.update(schema=9), lambda v:v.update(schema=10), lambda v:v.update(schema=11),
            lambda v:v.update(lane=inputs.CONFIG_ENTRY_REFERENCE_LANE),
            lambda v:v.update(lane=inputs.CONFIG_ZERO_MARKER_FILENAME_LANE),
            lambda v:v.update(lane=inputs.CONFIG_MARKER_CENSUS_LANE),
            lambda v:v.update(lane=inputs.PARAMS_LANE),
            lambda v:v.update(nonce='e'*32), lambda v:v.update(extra='PRIVATE'),
            lambda v:v.pop('lane'),
            lambda v:v['provenance']['sources'].pop(policy.MODULE_SOURCE),
            lambda v:v['provenance']['sources'].update({policy.MODULE_SOURCE:'f'*64}),
            lambda v:v['provenance']['sources'].update({'unexpected.py':'f'*64}))
        for mutate in mutations:
            value=copy.deepcopy(original); mutate(value)
            invocation.write_bytes(protocol.encode(value))
            with self.assertRaises(OracleError): inputs.verify_inputs(staged,NONCE,config_blob_chain=True)
        invocation.write_bytes(protocol.encode(original))
        self.assertEqual(inputs.verify_inputs(staged,NONCE,config_blob_chain=True),provenance)

    def test_exact_cold_staged_core_read_and_final_report_validator(self):
        staged=self.root/'cold'
        provenance=identity();provenance['sources']=inputs.source_hashes(ROOT,config_blob_chain=True)
        inputs.stage_inputs(ROOT,staged,NONCE,provenance,config_blob_chain=True)
        self.assertEqual(len(provenance['sources']),23)
        for excluded in ('config_entry_reference.py','config_zero_marker_filename.py','config_marker_census.py','config_framing.py','config_observation.py','params_observation.py','params_extraction.py',
                         'dbnames_identity.py','filedb_named_file.py','filedb_dbnames.py','filedb_records.py'):
            self.assertFalse((staged/excluded).exists())
        env={key:value for key,value in os.environ.items()
             if key.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP')}
        data=source([row(marker=1),row('PRIVATE'),row('')])
        code=('import sys,json;sys.path.insert(0,sys.argv[1]);import config_blob_chain as p;'
            'raw=sys.stdin.buffer.read();o=p.read_projection(lambda a,n:raw[a:a+n],len(raw),limits=p.reader.CatalogLimits());'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);'
            'print(json.dumps(o,sort_keys=True))')
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(staged)],
            input=data.full_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),policy.read_projection(data.read_at,data.size,
            limits=policy.reader.CatalogLimits()))
        self.assertNotIn(b'PRIVATE',result.stdout)
        report,_=fixture();report['provenance']=copy.deepcopy(provenance)
        report['provenance']['actual_version']=protocol.VERSION
        report['config_blob_chain']=policy.bind_capture(evidence(),report)
        report['cleanup'].update(container_removed=True,private_staging_removed=True)
        report['accepted']=True
        code=('import sys,json;sys.path.insert(0,sys.argv[1]);import config_blob_chain as p;'
            'r=json.loads(sys.stdin.buffer.read());p.validate_report(p.encode(r),nonce=r["nonce"],'
            'provenance=r["provenance"],final=True);'
            'assert not any(n=="yadinassi" or n.startswith("yadinassi.") for n in sys.modules);print("validated")')
        result=subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(staged)],
            input=protocol.encode(report),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stderr,b'')
        self.assertIn(result.stdout,(b'validated\n',b'validated\r\n'))

    def test_missing_tampered_or_extra_staged_reader_rejected_at_invocation_admission(self):
        staged=self.root/'physical-admission'
        provenance=identity();provenance['sources']=inputs.source_hashes(ROOT,config_blob_chain=True)
        inputs.stage_inputs(ROOT,staged,NONCE,provenance,config_blob_chain=True)
        old.writable(staged)
        core=staged/'config_framing_reader.py';original=core.read_bytes()
        for mode in ('modified','missing','foreign'):
            if mode=='modified': core.write_bytes(original+b'\n')
            elif mode=='missing': core.unlink()
            else: (staged/'config_observation.py').write_bytes(b'not admitted')
            with self.subTest(mode=mode):
                with self.assertRaises(OracleError):
                    inputs.verify_inputs(staged,NONCE,config_blob_chain=True)
                # Command construction checks membership; runtime invocation
                # admission binds content hashes before selecting the policy.
                if mode!='modified':
                    with self.assertRaises(OracleError):
                        host.container_command(staged,'onec-db-oracle-'+'a'*32,NONCE,config_blob_chain=True)
            core.write_bytes(original)
            if mode=='foreign': (staged/'config_observation.py').unlink()
        self.assertEqual(inputs.verify_inputs(staged,NONCE,config_blob_chain=True),provenance)

    def test_host_cli_selects_only_requested_lane_and_rejects_combinations(self):
        with mock.patch.object(host,'ROOT',self.root), mock.patch.object(host,'run_oracle',return_value={'accepted':False}) as run, \
             mock.patch.object(host,'export_report'), mock.patch.dict(os.environ,{},clear=True), \
             contextlib.redirect_stdout(__import__('io').StringIO()),contextlib.redirect_stderr(__import__('io').StringIO()):
            self.assertEqual(host.main(['--execute-approved-image','--file-db-oracle','--config-blob-chain-observation']),1)
            self.assertEqual(run.call_args.kwargs,{'config_blob_chain':True})
            for flag in ('--record-reader-validation','--record-metadata-observation',
                         '--params-transport-observation','--params-dbnames-extraction','--dbnames-identity-validation','--config-transport-observation','--config-framing-observation','--config-slot-marker-observation','--config-zero-marker-filename-observation','--config-entry-reference-observation'):
                with self.assertRaises(SystemExit): host.main(['--execute-approved-image','--file-db-oracle','--config-blob-chain-observation',flag])


    def test_runtime_main_selects_new_policy_without_native_execution(self):
        result,_=fixture();output=__import__('io').BytesIO()
        def controller(backend,report):
            self.assertEqual(report['schema'],15)
            self.assertIn('config_blob_chain',report)
            self.assertEqual(report['framing_validation'],'not_accepted')
            return __import__('types').SimpleNamespace(run=lambda:result)
        with mock.patch.object(sys,'argv',['run.py','--invocation-nonce',NONCE,'--config-blob-chain-observation']), \
             mock.patch.object(inputs,'verify_inputs',return_value=identity()) as verify, \
             mock.patch.object(fixtures.stage,'Native') as native, \
             mock.patch.object(fixtures.stage,'Controller',side_effect=controller), \
             mock.patch.object(sys,'stdout',__import__('types').SimpleNamespace(buffer=output)):
            self.assertEqual(fixtures.stage.main(),0)
        self.assertEqual(native.call_args.kwargs,{'config_blob_chain':True})
        self.assertEqual(verify.call_args.kwargs,{'config_blob_chain':True})
        self.assertEqual(json.loads(output.getvalue())['lane'],policy.LANE)
        self.assertTrue(output.getvalue().endswith(b'\n'))
        for argv in (['run.py','--invocation-nonce',NONCE,'--config-blob-chain-observation','--params-transport-observation'],
                     ['run.py','--invocation-nonce',NONCE,'--config-blob-chain-observation=1']):
            with mock.patch.object(sys,'argv',argv),mock.patch.object(fixtures.stage,'Native') as native:
                self.assertEqual(fixtures.stage.main(),2);native.assert_not_called()

    @unittest.skipIf(os.name=='nt','POSIX shell launcher')
    def test_shell_launcher_forwards_exact_flag_and_no_extra_arguments(self):
        stub=self.root/'python3'
        stub.write_bytes(b"#!/bin/sh\nprintf '%s\\n' \"$@\"\n");stub.chmod(0o755)
        command=['/bin/bash',str(ROOT/'scripts/native_1c_db_oracle/probe.sh'),'--invocation-nonce',NONCE]
        for flags,wanted in (([],0),(['--config-blob-chain-observation'],0),
                (['--config-blob-chain-observation','--params-transport-observation'],2),
                (['--config-blob-chain-observation','--config-slot-marker-observation'],2),
                (['--config-blob-chain-observation','--config-zero-marker-filename-observation'],2),
                (['--config-blob-chain-observation','--config-entry-reference-observation'],2),
                (['--config-blob-chain-observation=1'],2)):
            completed=subprocess.run(command+flags,env={'PATH':str(self.root)},
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(completed.returncode,wanted)
            self.assertEqual(completed.stderr,b'')
            expected=('\n'.join(['-B','/oracle/run.py','--invocation-nonce',NONCE]+flags)+'\n').encode('ascii')
            self.assertEqual(completed.stdout,expected if wanted==0 else b'')


@unittest.skipIf(os.name=='nt','POSIX anchored frozen postimage boundary')
class ConfigBlobChainPostimageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.artifacts=self.root/'artifacts'; self.artifacts.mkdir()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root)); normalize_owners(self)
        self.seed=self.artifacts/'seed'; self.seed.mkdir(); self.pre=source([row(marker=1),row('before')]); self.post=source([row(marker=1),row('after'),row('extra'),
            row(raw=b'\0\xd8',units=65535,marker=255)])
        (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed,self.artifacts/'baseline',quiescent=lambda:True)
        self.native=fixtures.stage.Native(NONCE,identity(),config_blob_chain=True)
        self.native.root=self.root; self.native.artifacts=self.artifacts; self.native.stage='baseline'
        self.native.quiescent=lambda:True; self.native.budgets=mock.Mock(); self.calls=[]
        def enterprise(database,operation,*,token):
            self.calls.append((database,operation,token)); (database/'1Cv8.1CD').write_bytes(self.post.full_bytes())
            return old.marker(token)
        self.native.enterprise=enterprise

    def test_real_same_descriptor_projection_uses_closed_postimage_and_removes_both_clones(self):
        with mock.patch.object(policy,'read_projection',wraps=policy.read_projection) as read:
            result=self.native.observe_record_metadata('baseline')
        read.assert_called_once(); self.assertEqual(len(self.calls),1)
        self.assertEqual(self.calls[0][:2],(self.artifacts/'auditor',metadata.OPERATION))
        self.assertEqual(result['reader']['candidate_slots'],4)
        self.assertEqual((result['reader']['validated_zero_count'],result['reader']['nonempty_filenames'],
                          result['reader']['later_other_count']),(2,2,1))
        self.assertEqual(result['postimage']['sha256'],hashlib.sha256(self.post.full_bytes()).hexdigest())
        self.assertNotEqual(result['origin']['sha256'],result['postimage']['sha256'])
        self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(),self.pre.full_bytes())
        self.assertFalse((self.artifacts/'auditor').exists());self.assertFalse((self.artifacts/'auditor_frozen').exists())
        report=policy.empty_report(NONCE,identity());report['provenance']['actual_version']=protocol.VERSION
        report['snapshots']=[{'id':'baseline','physical':self.native.physical_summary(self.artifacts/'baseline'/'1Cv8.1CD')}]
        capture=policy.bind_capture(result,report); self.assertEqual(capture['reader'],result['reader'])

    def test_changed_postimage_digest_and_nonquiescence_reject_without_capture(self):
        original=snapshots.inspect_frozen_catalog
        def changed(*args,**kwargs):
            summary,result=original(*args,**kwargs);summary['sha256']='e'*64;return summary,result
        with mock.patch.object(snapshots,'inspect_frozen_catalog',side_effect=changed), self.assertRaises(policy.ObservationFailure):
            self.native.observe_record_metadata('baseline')
        self.native.quiescent=lambda:False
        with self.assertRaises(OracleError): self.native.observe_record_metadata('baseline')
        self.assertFalse((self.artifacts/'auditor').exists());self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_new_field_failures_discard_observation_and_remove_both_private_clones(self):
        cases=(( [row(marker=1),row('PRIVATE',marker=255)],'config_reference_no_part_zero_witness'),
               ( [row(marker=1),row(''),row('PRIVATE',marker=1)],'config_reference_no_part_zero_witness'),
               ( [row(marker=1),row('good'),row(raw=b'\0\xd8',units=1)],'config_filename_encoding'),
               ( [row(marker=1),row('good'),row(units=129)],'config_filename_length'),
               ( [row(marker=1),row('good'),row('last',length=2)],'config_chain_length'),
               ( [row(marker=1),row('good'),row('last',part_raw=b'\xff'*6)],'config_partno_encoding'),
               ( [row(marker=1),row('good'),row('last',part=4096)],'config_partno_limit'),
               ( [row(marker=1),row('no witness',part=1)],'config_reference_no_part_zero_witness'))
        for rows,code in cases:
            self.post=source(rows)
            with self.subTest(code=code),self.assertRaises(policy.ObservationFailure) as error:
                self.native.observe_record_metadata('baseline')
            self.assertEqual(error.exception.code,code)
            self.assertNotIn('PRIVATE',str(error.exception))
            self.assertFalse((self.artifacts/'auditor').exists())
            self.assertFalse((self.artifacts/'auditor_frozen').exists())
            self.assertEqual((self.artifacts/'baseline'/'1Cv8.1CD').read_bytes(),self.pre.full_bytes())


class ConfigBlobChainHostCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))
        self.work=self.root/'work';self.work.mkdir()
        self.identity=identity();self.identity['sources']=inputs.source_hashes(ROOT,config_blob_chain=True)
        self.events=[]

    def invoke(self, *, native_cleanup=(True,True), container_bad=False, staging_bad=False, source_changed=False):
        report,_=fixture(cleanup=native_cleanup)
        report['provenance']=copy.deepcopy(self.identity);report['provenance']['actual_version']=protocol.VERSION
        if report['status']=='ok': report['config_blob_chain']=policy.bind_capture(evidence(),report)
        def provenance(**kwargs):
            self.assertEqual(kwargs,{'config_blob_chain':True})
            self.assertNotIn('GHCR_TOKEN',os.environ);self.assertNotIn('GHCR_USER',os.environ)
            self.events.append('provenance');value=copy.deepcopy(self.identity)
            if source_changed and self.events.count('provenance')>1: value['tree']='e'*40
            return value
        def silent(args,env,seconds,input_bytes=None):
            self.assertNotIn('GHCR_TOKEN',os.environ);self.assertNotIn('PRIVATE-SECRET',json.dumps(args))
            self.events.append(args[1])
        def bounded(args,env,seconds,limit):
            self.events.append(args[1])
            if args[1]=='image': return 0,b'linux/amd64|0'
            if args[1]=='ps': return 0,b'still-live' if container_bad else b''
            self.assertEqual(args[1],'run');self.assertEqual(args[-1],'--config-blob-chain-observation')
            self.assertEqual((seconds,limit),(2400,32768))
            return (0 if report['status']=='ok' else 1),protocol.encode(report)
        class LeftoverDirectory:
            def __init__(self,**kwargs): self.name=tempfile.mkdtemp(**kwargs)
            def __enter__(self): return self.name
            def __exit__(self,*args): return False
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ,{'GHCR_USER':'Atridis','GHCR_TOKEN':'PRIVATE-SECRET'},clear=True))
            stack.enter_context(mock.patch.object(host,'provenance',side_effect=provenance))
            stack.enter_context(mock.patch.object(host.uuid,'uuid4',return_value=__import__('types').SimpleNamespace(hex=NONCE)))
            stack.enter_context(mock.patch.object(host.smoke,'run_silent',side_effect=silent))
            stack.enter_context(mock.patch.object(host.smoke,'bounded_run',side_effect=bounded))
            popen=stack.enter_context(mock.patch.object(host.smoke.subprocess,'Popen',side_effect=AssertionError('real process forbidden')))
            run=stack.enter_context(mock.patch.object(host.smoke.subprocess,'run',side_effect=AssertionError('real process forbidden')))
            if staging_bad: stack.enter_context(mock.patch.object(host.tempfile,'TemporaryDirectory',LeftoverDirectory))
            result=host.run_oracle(self.work,config_blob_chain=True)
            popen.assert_not_called();run.assert_not_called()
        policy.validate_report(protocol.encode(result),nonce=NONCE,provenance=self.identity,final=True)
        self.assertNotIn(b'PRIVATE-SECRET',protocol.encode(result))
        return result

    def test_all_four_cleanup_gates_and_source_recheck(self):
        result=self.invoke();self.assertTrue(result['accepted']);self.assertTrue(all(result['cleanup'].values()))
        self.assertEqual(self.events,['provenance','login','pull','image','run','rm','ps','provenance'])
        for kwargs in ({'container_bad':True},{'staging_bad':True},{'source_changed':True},
                       {'native_cleanup':(False,True)},{'native_cleanup':(True,False)}):
            self.events.clear();result=self.invoke(**kwargs)
            self.assertFalse(result['accepted']);self.assertIsNone(result['config_blob_chain'])
            self.assertEqual(result['artifacts'],[])
            old.writable(self.work)
            for child in self.work.iterdir(): shutil.rmtree(child)


if __name__=='__main__': unittest.main()
