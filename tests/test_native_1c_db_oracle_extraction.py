"""Closed Phase-B policy and owned synthetic extraction, never native evidence."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage'),
                str(ROOT/'scripts'), str(ROOT/'tests')]
import comparison
import inputs
import params_extraction as policy
import params_observation as phase_a
import protocol
import record_observation as metadata
import record_validation
import snapshots
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_record_route as old
from test_native_1c_db_oracle_catalog_reader import normalize_owners
from test_filedb_catalog import Source, P, u32
from test_filedb_records import serialize

NONCE, TOKEN = old.NONCE, old.TOKEN
host = old.host


def identity():
    result = fixtures.provenance()
    result['sources'] = {name: 'c'*64 for name in inputs.EXTRACTION_SOURCE_FILES}
    return result


def projection():
    return {'schema': 1, 'target': policy.TARGET, 'profile_id': policy.PROFILE_ID,
        'profile_sha256': policy.PROFILE_SHA256, 'packed_bytes': 10, 'packed_sha256': 'd'*64,
        'plain_bytes': 5, 'plain_sha256': hashlib.sha256(b'hello').hexdigest()}


def evidence(token=TOKEN):
    return {'marker': old.marker(token), 'origin': {'nonce': NONCE, 'token': token, 'clone': 'auditor',
        **{key: fixtures.physical('baseline')[key] for key in ('bytes', 'sha256')}},
        'postimage': {'bytes': 20*P, 'sha256': 'e'*64}, 'reader': projection()}


class Backend(fixtures.FixtureNative):
    def observe_record_metadata(self, identifier):
        self.event('record_metadata', identifier)
        return evidence()


def fixture(fail=None, cleanup=(True, True)):
    provenance = identity(); report = policy.empty_report(NONCE, provenance)
    backend = Backend(provenance, fail); backend.clean = cleanup
    controller = fixtures.stage.Controller(backend, report); backend.controller = controller
    return controller.run(), backend


def source(payload=b'hello', *, declarations=None, lock='0', format_item=0):
    """Independent stored-block raw-DEFLATE fixture, not native expected bytes."""
    value = Source(page_count=20)
    fields = policy.DECLARATIONS if declarations is None else declarations
    description = serialize(('PARAMS', format_item, ('Fields', *fields), ('Indexes',),
                             ('Recordlock', lock), ('Files', 5, 8, 9))).encode('utf-8')
    value.catalog((2,)); value.chain(tuple(range(2, 2+(len(description)+249)//250)), description)
    packed = b'\x01' + len(payload).to_bytes(2,'little') + (65535-len(payload)).to_bytes(2,'little') + payload
    assert len(packed)<=250
    def number(n,digits): return bytes.fromhex('1'+str(n).zfill(digits)+'0')
    row = bytearray(301)
    row[1:3] = (7).to_bytes(2,'little'); row[3:17] = 'DBNames'.encode('utf-16le')
    row[259:276] = b'X'*17  # Dates and attributes remain uninterpreted.
    row[276:287] = number(len(packed),20)
    row[287:295] = u32(1)+u32(len(packed)); row[295:301] = number(0,10)
    data = b'\x01'+b'R'*300+row
    for header_page, data_page, length in ((5,10,len(data)),(8,11,512)):
        page=value.page(header_page)
        page[:24]=b'\x1c\xfd\0\0'+bytes(12)+length.to_bytes(8,'little')
        page[24:28]=u32(data_page)
    value.page(10)[:len(data)]=data
    value.page(11)[256:262]=u32(0)+len(packed).to_bytes(2,'little')
    value.page(11)[262:262+len(packed)]=packed
    return value


class ExtractionPolicyTests(unittest.TestCase):
    def check(self, report, final=False):
        return policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity(), final=final)

    def test_projection_is_exact_bounded_and_profile_bound(self):
        self.assertEqual(policy.validate_projection(projection()),projection())
        mutations=[lambda v:v.update(raw='PRIVATE'),lambda v:v.update(target='PARAMS'),
            lambda v:v.update(profile_id='guessed'),lambda v:v.update(profile_sha256='f'*64),
            lambda v:v.update(packed_sha256='PRIVATE'),lambda v:v.update(plain_sha256='g'*64),
            lambda v:v.update(schema=True)]
        for key in ('packed_bytes','plain_bytes'):
            for invalid in (True,-1,1.0,'1',None,policy.MAX_PLAIN_BYTES+1):
                mutations.append(lambda v,k=key,x=invalid:v.update({k:x}))
        mutations.append(lambda v:v.update(packed_bytes=0))
        for change in mutations:
            value=projection();change(value)
            with self.assertRaises(OracleError): policy.validate_projection(value)
        value=projection();value['plain_bytes']=0
        self.assertEqual(policy.validate_projection(value),value)
        self.assertEqual(hashlib.sha256(protocol.encode(dict(sorted(policy.PROFILE_DESCRIPTION.items())))).hexdigest(),policy.PROFILE_SHA256)
        self.assertEqual(policy.PROFILE_DESCRIPTION['declarations'],policy.DECLARATIONS)
        self.assertEqual(policy.PROFILE_DESCRIPTION['record_size'],301)
        self.assertEqual(policy.PROFILE_SHA256,'ca94afd765180b3b7464c06c536deec41864768eb1ed437e015edd38bb6ad99b')

    def test_capture_has_only_actual_extraction_claim_and_exact_source_binding(self):
        report,backend=fixture();self.check(report)
        capture=report['params_extraction']
        self.assertEqual((report['schema'],capture['schema']),(8,9))
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertEqual(report['reader_validation'],policy.VERDICT)
        self.assertEqual(report['extraction_validation'],policy.VERDICT)
        for key in ('observation_validation','layout_validation','mapping_validation'):self.assertEqual(report[key],'not_run')
        self.assertEqual(report['native_byte_equivalence'],'not_observed')
        self.assertEqual(report['native_compatibility'],'not_claimed')
        self.assertNotIn('native',capture);self.assertNotIn(b'Uninterpreted',protocol.encode(report))
        for key in ('token','nonce','source_manifest_sha256','reader_source_sha256','policy_source_sha256','extractor_source_sha256'):
            changed=copy.deepcopy(report);changed['params_extraction'][key]='PRIVATE'
            with self.assertRaises(OracleError):self.check(changed)
        for key in ('bytes','sha256'):
            changed=evidence();changed['origin'][key]=1 if key=='bytes' else 'f'*64
            with self.assertRaises(OracleError):policy.bind_capture(changed,report)
        for validator in (protocol.validate_report,comparison.validate_report,metadata.validate_report,
                          record_validation.validate_report,phase_a.validate_report):
            with self.assertRaises(OracleError):validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        for key in ('raw','path','rows','filename','native'):
            changed=copy.deepcopy(report);changed['params_extraction']['reader'][key]='PRIVATE'
            with self.assertRaises(OracleError):self.check(changed)

    def test_every_post_capture_failure_discards_success(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed);self.check(report)
            self.assertIsNone(report['params_extraction'])
            self.assertEqual(report['extraction_validation'],'discarded')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup);self.check(report)
            self.assertIsNone(report['params_extraction']);self.assertEqual(report['artifacts'],[])
        for error in (policy.ObservationFailure('unsupported_layout','dbnames_profile_mismatch'),
                      OracleError('timeout'),AssertionError('PRIVATE')):
            provenance=identity();report=policy.empty_report(NONCE,provenance)
            backend=Backend(provenance);backend.reader_attempted=True
            backend.observe_record_metadata=mock.Mock(side_effect=error)
            controller=fixtures.stage.Controller(backend,report);backend.controller=controller
            result=controller.run();self.check(result)
            self.assertEqual(result['reader_validation'],'failed');self.assertNotIn(b'PRIVATE',protocol.encode(result))
            for gate in ('container_removed','private_staging_removed'):
                late=copy.deepcopy(result);late['cleanup'].update(container_removed=True,private_staging_removed=True)
                late['cleanup'][gate]=False
                host.fail_report(late,'cleanup_unverified','cleanup',preserve_primary=True)
                self.check(late,final=True);self.assertIsNone(late['params_extraction'])

    def test_no_forged_success_or_old_failure_kind_and_no_old_policy_widening(self):
        report,_=fixture()
        for change in (lambda r:r.update(params_extraction=None),lambda r:r.update(extraction_validation='not_run'),
                lambda r:r.update(lane=phase_a.LANE),lambda r:r.update(schema=True),
                lambda r:r.update(mapping_validation='validated'),lambda r:r.update(native_byte_equivalence='observed'),
                lambda r:r['params_extraction']['postimage'].update(sha256='PRIVATE'),
                lambda r:r['params_extraction']['postimage'].update(bytes=True),
                lambda r:r['provenance']['sources'].pop(policy.EXTRACTOR_SOURCE)):
            changed=copy.deepcopy(report);change(changed)
            with self.assertRaises(OracleError):self.check(changed)
        for kind,code in ((policy.reader.InvalidStructure,'dbnames_duplicate'),
                          (policy.reader.UnsupportedLayout,'dbnames_part'),
                          (policy.reader.ResourceLimit,'transport_plain_bytes')):
            self.assertEqual(policy.reader_failure(kind(code)).code,code)
            for previous in (comparison,metadata,record_validation,phase_a):
                with self.assertRaises(OracleError):previous.reader_failure(kind(code))
        class Derived(policy.reader.InvalidStructure):pass
        for error in (Derived('dbnames_duplicate'),policy.reader.InvalidStructure('PRIVATE')):
            with self.assertRaises(OracleError):policy.reader_failure(error)


class ExtractionReaderTests(unittest.TestCase):
    def test_core_profile_placements_match_independent_literal_recipe(self):
        module=policy.load_reader(Path(policy.reader.__file__).with_name('filedb_named_file.py'))
        profile=module.DBNamesProfile(policy.DECLARATIONS,'0',0)
        recipe=policy.PROFILE_DESCRIPTION
        self.assertEqual(profile.identifier,recipe['id'])
        self.assertEqual(profile.framing,recipe['framing_policy'])
        self.assertEqual(profile.recordlock,recipe['recordlock'])
        self.assertEqual(profile.format_item,recipe['format_item'])
        self.assertEqual(profile.record_size,recipe['record_size'])
        self.assertEqual(profile.placements,tuple(zip(recipe['offsets'],recipe['widths'])))
        self.assertEqual(module.DBNAMES_DECLARATIONS,recipe['declarations'])

    def read(self,value):
        return policy.read_projection(value.read_at,value.size,limits=policy.reader.CatalogLimits())

    def test_real_callback_extracts_only_bounded_counts_and_digests(self):
        for payload in (b'hello',b'',b'private opaque content'):
            value=source(payload);result=self.read(value)
            self.assertEqual(result['plain_bytes'],len(payload))
            self.assertEqual(result['plain_sha256'],hashlib.sha256(payload).hexdigest())
            self.assertEqual(result['packed_bytes'],len(payload)+5)
            self.assertEqual(set(result),set(projection()))
            self.assertEqual(result['profile_sha256'],policy.PROFILE_SHA256)
            self.assertIn((5*P,P),value.calls);self.assertIn((8*P,P),value.calls)
        self.assertNotIn(b'private opaque content',protocol.encode(result))

    def test_exact_profile_rechecked_before_selected_file_reads(self):
        for changes in ({'declarations':tuple(reversed(policy.DECLARATIONS))},{'lock':'1'},{'format_item':1}):
            value=source(**changes)
            with self.assertRaises(policy.reader.CatalogError):self.read(value)
            self.assertFalse([offset for offset,length in value.calls if offset>=5*P])

    def test_staged_callback_is_stdlib_only(self):
        value=source()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();target=root/'inputs'
            provenance=identity();provenance['sources']=inputs.source_hashes(ROOT,params_extraction=True)
            try:
                inputs.stage_inputs(ROOT,target,NONCE,provenance,params_extraction=True)
                code=("import sys,json;sys.path.insert(0,sys.argv[1]);import params_extraction as p;"
                    "raw=sys.stdin.buffer.read();result=p.read_projection(lambda o,n:raw[o:o+n],len(raw),limits=p.reader.CatalogLimits());"
                    "assert not any(n=='yadinassi' or n.startswith('yadinassi.') for n in sys.modules);"
                    "sys.stdout.buffer.write(json.dumps(result,separators=(',',':')).encode('ascii')+b'\\n')")
                env={key:value for key,value in os.environ.items() if key.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP')}
                completed=subprocess.run([sys.executable,'-I','-B','-S','-c',code,str(target)],input=value.full_bytes(),
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=30)
                self.assertEqual(completed.returncode,0,completed.stderr)
                self.assertEqual(json.loads(completed.stdout),self.read(value))
            finally:old.writable(root)


class ExtractionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))

    def test_exact_inventory_and_mutually_exclusive_old_lanes(self):
        self.assertEqual(tuple(map(len,(inputs.LEGACY_V3_SOURCE_FILES,inputs.SOURCE_FILES,
            inputs.RECORD_SOURCE_FILES,inputs.ROW_SOURCE_FILES,inputs.PARAMS_SOURCE_FILES,inputs.EXTRACTION_SOURCE_FILES))),(18,20,21,23,22,24))
        for options in ({},{'record_metadata':True},{'record_reader':True},{'params_transport':True},{'params_extraction':True}):
            staged=self.root/('stage'+str(len(list(self.root.iterdir()))))
            provenance=identity(); provenance['sources']=inputs.source_hashes(ROOT,**options)
            inputs.stage_inputs(ROOT,staged,NONCE,provenance,**options)
            self.assertEqual(inputs.verify_inputs(staged,NONCE,**options),provenance)
            self.assertEqual((staged/'params_extraction.py').exists(),bool(options.get('params_extraction')))
            self.assertEqual((staged/'filedb_named_file.py').exists(),bool(options.get('params_extraction')))
            self.assertEqual((staged/'params_observation.py').exists(),bool(options.get('params_transport') or options.get('params_extraction')))
            if options.get('params_extraction'):
                self.assertEqual(json.loads((staged/'invocation.json').read_text(encoding='utf-8'))['schema'],5)
                command=host.container_command(staged,'onec-db-oracle-'+'a'*32,NONCE,**options)
                self.assertEqual(command[-1],'--params-dbnames-extraction')
                for wrong in ({},{'record_metadata':True},{'record_reader':True},{'params_transport':True}):
                    with self.assertRaises(OracleError): inputs.verify_inputs(staged,NONCE,**wrong)
        for name in ('record_metadata','record_reader','params_transport'):
            with self.assertRaises(OracleError): inputs.inventory(params_extraction=True,**{name:True})
        for bad in (1,None,'true'):
            with self.assertRaises(OracleError): inputs.inventory(params_extraction=bad)

    def test_host_cli_selects_only_requested_lane_and_rejects_combinations(self):
        with mock.patch.object(host,'ROOT',self.root), mock.patch.object(host,'run_oracle',return_value={'accepted':False}) as run, \
             mock.patch.object(host,'export_report'), mock.patch.dict(os.environ,{},clear=True), \
             contextlib.redirect_stdout(__import__('io').StringIO()),contextlib.redirect_stderr(__import__('io').StringIO()):
            self.assertEqual(host.main(['--execute-approved-image','--file-db-oracle','--params-dbnames-extraction']),1)
            self.assertEqual(run.call_args.kwargs,{'params_extraction':True})
            for flag in ('--record-reader-validation','--record-metadata-observation','--params-transport-observation'):
                with self.assertRaises(SystemExit): host.main(['--execute-approved-image','--file-db-oracle','--params-dbnames-extraction',flag])

    def test_runtime_main_selects_new_policy_without_native_execution(self):
        result,_=fixture();output=__import__('io').BytesIO()
        def controller(backend,report):
            self.assertEqual(report['schema'],8)
            self.assertIn('params_extraction',report)
            return __import__('types').SimpleNamespace(run=lambda:result)
        with mock.patch.object(sys,'argv',['run.py','--invocation-nonce',NONCE,'--params-dbnames-extraction']), \
             mock.patch.object(inputs,'verify_inputs',return_value=identity()) as verify, \
             mock.patch.object(fixtures.stage,'Native') as native, \
             mock.patch.object(fixtures.stage,'Controller',side_effect=controller), \
             mock.patch.object(sys,'stdout',__import__('types').SimpleNamespace(buffer=output)):
            self.assertEqual(fixtures.stage.main(),0)
        self.assertEqual(native.call_args.kwargs,{'params_extraction':True})
        self.assertEqual(verify.call_args.kwargs,{'params_extraction':True})
        self.assertEqual(json.loads(output.getvalue())['lane'],policy.LANE)
        self.assertTrue(output.getvalue().endswith(b'\n'))
        for argv in (['run.py','--invocation-nonce',NONCE,'--params-dbnames-extraction','--params-transport-observation'],
                     ['run.py','--invocation-nonce',NONCE,'--params-dbnames-extraction=1']):
            with mock.patch.object(sys,'argv',argv),mock.patch.object(fixtures.stage,'Native') as native:
                self.assertEqual(fixtures.stage.main(),2);native.assert_not_called()

    @unittest.skipIf(os.name=='nt','POSIX shell launcher')
    def test_shell_launcher_forwards_exact_flag_and_no_extra_arguments(self):
        stub=self.root/'python3'
        stub.write_bytes(b"#!/bin/sh\nprintf '%s\\n' \"$@\"\n");stub.chmod(0o755)
        command=['/bin/bash',str(ROOT/'scripts/native_1c_db_oracle/probe.sh'),'--invocation-nonce',NONCE]
        for flags,wanted in (([],0),(['--params-dbnames-extraction'],0),
                (['--params-dbnames-extraction','--params-transport-observation'],2),
                (['--params-dbnames-extraction=1'],2)):
            completed=subprocess.run(command+flags,env={'PATH':str(self.root)},
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(completed.returncode,wanted)
            self.assertEqual(completed.stderr,b'')
            expected=('\n'.join(['-B','/oracle/run.py','--invocation-nonce',NONCE]+flags)+'\n').encode('ascii')
            self.assertEqual(completed.stdout,expected if wanted==0 else b'')


@unittest.skipIf(os.name=='nt','POSIX anchored frozen postimage boundary')
class ExtractionPostimageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.artifacts=self.root/'artifacts'; self.artifacts.mkdir()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root)); normalize_owners(self)
        self.seed=self.artifacts/'seed'; self.seed.mkdir(); self.pre=source(b'before'); self.post=source(b'after')
        (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed,self.artifacts/'baseline',quiescent=lambda:True)
        self.native=fixtures.stage.Native(NONCE,identity(),params_extraction=True)
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
        self.assertEqual(result['reader']['plain_sha256'],hashlib.sha256(b'after').hexdigest())
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

    def test_controller_consumes_real_producer_before_completing_baseline(self):
        native = self.native
        physical = snapshots.file_summary(self.artifacts/'baseline'/'1Cv8.1CD',
            header_decoder=fixtures.stage.database_header_facts)

        class Bridge(fixtures.FixtureNative):
            # Preceding native setup/logical observations are synthetic. The
            # producer, summaries, clone/freeze, reader, binder and Controller
            # remain real; only the native enterprise boundary is stubbed by setUp.
            def begin_stage(inner, name):
                native.begin_stage(name)
                if name == 'create':
                    inner.bound = copy.deepcopy(inner.controller.report['params_extraction'])
                    inner.completed = copy.deepcopy(inner.controller.report['stages'][2])
                    raise OracleError('timeout')  # Never enter later native work.

            def freeze(inner, database, identifier):
                assert identifier == 'baseline'
                return physical

            def observe(inner, identifier, designer):
                assert (identifier, designer) == ('baseline', 1)
                return protocol.expected_logical('baseline')

            def observe_record_metadata(inner, identifier):
                return native.observe_record_metadata(identifier)

        provenance = identity(); native.provenance = provenance
        report = policy.empty_report(NONCE, provenance)
        backend = Bridge(provenance); backend.bound = None; backend.completed = None
        controller = fixtures.stage.Controller(backend, report); backend.controller = controller
        result = controller.run()
        policy.validate_report(protocol.encode(result), nonce=NONCE, provenance=provenance)
        self.assertTrue(native.reader_attempted)
        self.assertEqual(result['failed_stage'], 'create')
        self.assertEqual(result['failure_kind'], 'timeout')
        self.assertEqual(backend.bound['status'], policy.VERDICT)
        self.assertEqual(backend.completed['status'], 'ok')
        self.assertTrue(all(backend.completed['checks'].values()))
        # The deliberate later failure still discards the just-bound projection.
        self.assertIsNone(result['params_extraction'])
        self.assertEqual(result['extraction_validation'], 'discarded')
        self.assertEqual(result['reader_validation'], 'discarded')

    def test_prelaunch_changed_origin_rejects_without_native_call(self):
        original=self.native.clone
        def clone(*args):
            result=original(*args); (result/'1Cv8.1CD').write_bytes(self.post.full_bytes()); return result
        self.native.clone=clone
        with self.assertRaises(policy.ObservationFailure) as caught: self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.code,'origin_changed'); self.assertEqual(self.calls,[])

    def test_changed_postimage_rejects_and_removes_private_clones(self):
        original=snapshots.inspect_frozen_catalog
        def inspect(*args,**kwargs):
            summary,catalog=original(*args,**kwargs); summary['sha256']='e'*64; return summary,catalog
        with mock.patch.object(snapshots,'inspect_frozen_catalog',side_effect=inspect), self.assertRaises(policy.ObservationFailure) as caught:
            self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.code,'postimage_changed')
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())

    def test_remove_failure_deadline_and_wrong_scope_never_return_evidence(self):
        with self.assertRaises(OracleError): self.native.observe_record_metadata('created')
        self.native.stage='create'
        with self.assertRaises(OracleError): self.native.observe_record_metadata('baseline')
        self.assertEqual(self.calls,[]); self.native.stage='baseline'; self.native.deadline=0
        with self.assertRaises(OracleError) as caught: self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.kind,'timeout')
        self.assertFalse((self.artifacts/'auditor').exists()); self.assertFalse((self.artifacts/'auditor_frozen').exists())
        self.native.deadline=__import__('time').monotonic()+60
        original=self.native.remove
        def remove(path):
            if path.name=='auditor_frozen': raise OracleError('cleanup_unverified')
            return original(path)
        self.native.remove=remove
        with self.assertRaises(OracleError) as caught: self.native.observe_record_metadata('baseline')
        self.assertEqual(caught.exception.kind,'cleanup_unverified')


    def test_native_metadata_names_do_not_select_or_expose_payload(self):
        previous=self.native.enterprise
        def enterprise(*args,**kwargs):
            value=previous(*args,**kwargs)
            value['record_metadata']['table']['storage_name']='PoisonedNotParams'
            value['record_metadata']['table']['fields'][0]['storage_name']='PoisonedNotFilename'
            return value
        self.native.enterprise=enterprise
        evidence=self.native.observe_record_metadata('baseline')
        self.assertEqual(evidence['reader']['plain_sha256'],hashlib.sha256(b'after').hexdigest())
        report=policy.empty_report(NONCE,identity());report['provenance']['actual_version']=protocol.VERSION
        report['snapshots']=[{'id':'baseline','physical':self.native.physical_summary(self.artifacts/'baseline'/'1Cv8.1CD')}]
        capture=policy.bind_capture(evidence,report)
        self.assertNotIn(b'Poisoned',protocol.encode(capture))
        self.assertNotIn(b'after',protocol.encode(capture))



class ExtractionHostCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))
        self.work=self.root/'work';self.work.mkdir()
        self.identity=identity();self.identity['sources']=inputs.source_hashes(ROOT,params_extraction=True)
        self.events=[]

    def invoke(self, *, native_cleanup=(True,True), container_bad=False, staging_bad=False, source_changed=False):
        report,_=fixture(cleanup=native_cleanup)
        report['provenance']=copy.deepcopy(self.identity);report['provenance']['actual_version']=protocol.VERSION
        if report['status']=='ok': report['params_extraction']=policy.bind_capture(evidence(),report)
        def provenance(**kwargs):
            self.assertEqual(kwargs,{'params_extraction':True})
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
            self.assertEqual(args[1],'run');self.assertEqual(args[-1],'--params-dbnames-extraction')
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
            result=host.run_oracle(self.work,params_extraction=True)
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
            self.assertFalse(result['accepted']);self.assertIsNone(result['params_extraction'])
            self.assertEqual(result['artifacts'],[])
            old.writable(self.work)
            for child in self.work.iterdir(): shutil.rmtree(child)


if __name__=='__main__': unittest.main()
