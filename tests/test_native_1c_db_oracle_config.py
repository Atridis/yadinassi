"""CONFIG declarations: independently assembled synthetic bytes and mocked lifecycle, never native evidence."""
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
import config_observation as policy
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
    result['sources'] = {name: 'c'*64 for name in inputs.CONFIG_SOURCE_FILES}
    return result


def projection(count=7):
    return {'schema': 1, 'target': 'CONFIG', 'framing_validation': 'not_observed',
        'root_identity': 'not_observed', 'table': {'name': 'CONFIG',
        'record_lock_token': '1', 'format_class': 'integer_zero',
        'fields': [dict(zip(('name', 'type_token', 'nullability', 'length', 'precision', 'case_token'),
                           (name, 'UNKNOWN', 0, 32, 0, 'CS'))) for name in policy.FIELD_NAMES[:count]],
        'data_logical_bytes': 1, 'blob_logical_bytes': 256, 'table_data_initial_byte': 'one'}}


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


def source(*, count=7, first=b'\x01', format_item=0, names=None, lock='1', blob_length=256, table_name='CONFIG'):
    value = Source(page_count=20)
    fields = tuple((name, 'UNKNOWN', 0, 32, 0, 'CS') for name in (names or policy.FIELD_NAMES[:count]))
    description = serialize((table_name, format_item, ('Fields', *fields), ('Indexes',),
                             ('Recordlock', lock), ('Files', 5, 8, 9))).encode('utf-8')
    value.catalog((2,)); value.chain(tuple(range(2, 2+(len(description)+249)//250)), description)
    for header_page, data_page, length in ((5, 10, len(first)), (8, 11, blob_length)):
        header = value.page(header_page)
        header[:24] = b'\x1c\xfd\0\0' + bytes(12) + length.to_bytes(8, 'little')
        header[24:28] = u32(data_page)
    value.page(10)[:len(first)] = first
    value.page(11)[:] = b'Q'*P  # This body must never be read.
    return value


class ConfigPolicyTests(unittest.TestCase):
    def check(self, report, final=False):
        return policy.validate_report(protocol.encode(report), nonce=NONCE, provenance=identity(), final=final)

    def test_complete_fixed_ordered_declarations_and_only_finite_classes(self):
        for count, first, length in itertools.product((6, 7), policy.BYTE_CLASSES, (0, 1)):
            value = projection(count); value['table'].update(table_data_initial_byte=first, data_logical_bytes=length)
            if (first == 'unavailable') == (length == 0):
                self.assertEqual(policy.validate_projection(value), value)
            else:
                with self.assertRaises(OracleError): policy.validate_projection(value)
        for raw, wanted in ((0,'integer_zero'), (1,'integer_nonzero'), (-1,'integer_nonzero'),
                ('0','string_zero'), ('SECRET','string_other'), (('SECRET',),'list'), (True,'other')):
            self.assertEqual(policy.format_class(raw), wanted)

    def test_projection_rejects_unknown_names_order_raw_values_and_unbounded_scalars(self):
        mutations = [lambda v: v.update(secret='PRIVATE'), lambda v: v['table'].update(pointer=9),
            lambda v: v['table']['fields'].reverse(),
            lambda v: v['table']['fields'][0].update(name='PRIVATE'),
            lambda v: v['table'].update(record_lock_token='PRIVATE!'),
            lambda v: v['table'].update(format_class='PRIVATE')]
        for key in ('type_token','case_token'):
            mutations.extend(lambda v,k=key,x=x: v['table']['fields'][0].update({k:x})
                             for x in ('X'*9, 'é', '"', None, 0))
        for key in ('nullability','length','precision'):
            mutations.extend(lambda v,k=key,x=x: v['table']['fields'][0].update({k:x})
                             for x in (True, -1, 65536, 1.0, '1'))
        for mutation in mutations:
            value=projection(); mutation(value)
            with self.subTest(mutation=mutation), self.assertRaises(OracleError): policy.validate_projection(value)
        value=projection(); value['table']['fields']=value['table']['fields'][:5]
        with self.assertRaises(OracleError): policy.validate_projection(value)
        value=projection(); value['table']['name']='config'
        for field in value['table']['fields']: field['name']=field['name'].lower()
        self.assertEqual(policy.validate_projection(value),value)

    def test_bound_capture_exact_sources_tokens_origin_and_no_native_payload(self):
        report, backend = fixture(); self.check(report)
        capture=report['config_observation']
        self.assertEqual((report['schema'],capture['schema']),(10,11))
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertNotIn('native',capture); self.assertNotIn(b'Uninterpreted',protocol.encode(report))
        for key in ('extraction_validation','layout_validation','mapping_validation'): self.assertEqual(report[key],'not_run')
        for key in ('token','nonce','source_manifest_sha256','reader_source_sha256','policy_source_sha256'):
            changed=copy.deepcopy(report); changed['config_observation'][key]='PRIVATE'
            with self.assertRaises(OracleError): self.check(changed)
        for key in ('bytes','sha256'):
            changed=evidence(); changed['origin'][key]=1 if key=='bytes' else 'f'*64
            with self.assertRaises(OracleError): policy.bind_capture(changed,report)
        for validator in (protocol.validate_report,comparison.validate_report,metadata.validate_report,record_validation.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        changed=copy.deepcopy(report); changed['config_observation']['reader']['table']['raw']='PRIVATE'
        with self.assertRaises(OracleError): self.check(changed)

    def test_no_framing_root_or_applied_semantic_claim_can_be_injected(self):
        for key in ('framing_validation', 'root_identity'):
            for replacement in ('observed', True, None, {'private': 'value'}):
                value=projection(); value[key]=replacement
                with self.assertRaises(OracleError): policy.validate_projection(value)
        value=projection(); value['target']='CONFIGSAVE'
        with self.assertRaises(OracleError): policy.validate_projection(value)
        report,_=fixture()
        for claim in ('layout_validation','extraction_validation','mapping_validation','native_compatibility'):
            value=copy.deepcopy(report); value[claim]='matched'
            with self.assertRaises(OracleError): self.check(value)

    def test_missing_extra_stale_and_tampered_capture_fields_reject(self):
        report,_=fixture()
        for path in ((), ('config_observation',), ('config_observation','reader'),
                     ('config_observation','reader','table')):
            for extra in (False,True):
                value=copy.deepcopy(report); target=value
                for key in path: target=target[key]
                if extra: target['unexpected']='PRIVATE'
                else: del target[next(iter(target))]
                with self.assertRaises(OracleError): self.check(value)
        mutations=(
            lambda v: v.update(schema=7),
            lambda v: v.update(lane='owned_params_transport_observation_v1'),
            lambda v: v['config_observation'].update(schema=8),
            lambda v: v['config_observation']['postimage'].update(storage_version=[8,2,14,0]),
            lambda v: v['config_observation']['postimage'].update(page_size=4096),
            lambda v: v['config_observation']['origin'].update(snapshot='after_apply'),
            lambda v: v['config_observation'].update(policy_source_sha256='f'*64),
        )
        for mutate in mutations:
            value=copy.deepcopy(report); mutate(value)
            with self.assertRaises(OracleError): self.check(value)
        for mode in ('missing','extra','replaced'):
            value=copy.deepcopy(report); sources=value['provenance']['sources']
            if mode in ('missing','replaced'): sources.pop(policy.MODULE_SOURCE)
            if mode in ('extra','replaced'): sources['scripts/native_1c_db_oracle/params_observation.py']='c'*64
            with self.assertRaises(OracleError):
                policy.validate_report(protocol.encode(value),nonce=NONCE,provenance=value['provenance'])

    def test_all_later_failures_and_native_cleanup_discard_capture(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed); self.check(report)
            self.assertIsNone(report['config_observation'])
            self.assertEqual(report['observation_validation'],'discarded')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup); self.check(report)
            self.assertIsNone(report['config_observation']); self.assertEqual(report['artifacts'],[])
        for error in (policy.ObservationFailure('unsupported_layout','declaration_token'),
                      OracleError('timeout'), AssertionError('PRIVATE')):
            provenance=identity(); report=policy.empty_report(NONCE,provenance)
            backend=Backend(provenance); backend.reader_attempted=True
            backend.observe_record_metadata=mock.Mock(side_effect=error)
            controller=fixtures.stage.Controller(backend,report); backend.controller=controller
            result=controller.run(); self.check(result)
            self.assertEqual(result['reader_validation'],'failed'); self.assertNotIn(b'PRIVATE',protocol.encode(result))
            for gate in ('container_removed','private_staging_removed'):
                late=copy.deepcopy(result); late['cleanup'].update(container_removed=True,private_staging_removed=True)
                late['cleanup'][gate]=False
                host.fail_report(late,'cleanup_unverified','cleanup',preserve_primary=True)
                self.check(late,final=True); self.assertIsNone(late['config_observation'])

    def test_exact_helper_failure_policy_does_not_widen_older_lanes(self):
        for kind,code in ((policy.reader.InvalidStructure,'table_blob_header_role'),
                          (policy.reader.UnsupportedLayout,'missing_table_blob_header')):
            self.assertEqual(policy.reader_failure(kind(code)).code,code)
            for old_policy in (comparison,metadata,record_validation):
                with self.assertRaises(OracleError): old_policy.reader_failure(kind(code))


class ConfigReaderTests(unittest.TestCase):
    def read(self, value):
        return policy.read_projection(value.read_at,value.size,limits=policy.reader.CatalogLimits())

    def test_real_reader_maps_both_files_but_reads_only_first_data_byte(self):
        for count, first in itertools.product((6,7),(b'',b'\0',b'\1',b'\x89')):
            value=source(count=count,first=first); result=self.read(value)
            wanted={b'':'unavailable',b'\0':'zero',b'\1':'one',b'\x89':'other'}[first]
            self.assertEqual(result['table']['table_data_initial_byte'],wanted)
            self.assertEqual((result['table']['data_logical_bytes'],result['table']['blob_logical_bytes']),(len(first),256))
            self.assertEqual([call for call in value.calls if call[0]>=10*P],[(10*P,1)] if first else [])
            self.assertIn((5*P,P),value.calls); self.assertIn((8*P,P),value.calls)
            self.assertNotIn(b'Q',protocol.encode(result))

    def test_configsave_or_other_table_is_not_a_fallback(self):
        for table_name in ('CONFIGSAVE','PARAMS','OTHER'):
            value=source(table_name=table_name)
            with self.assertRaises(policy.ObservationFailure): self.read(value)
            self.assertNotIn((5*P,P),value.calls)
            self.assertNotIn((8*P,P),value.calls)

    def test_duplicate_selected_table_is_rejected_before_data_open(self):
        value=source()
        original=policy.reader.CatalogReader.read_catalog
        def duplicated(reader):
            catalog=original(reader)
            return __import__('dataclasses').replace(catalog,tables=catalog.tables+catalog.tables)
        with mock.patch.object(policy.reader.CatalogReader,'read_catalog',duplicated):
            with self.assertRaises(policy.ObservationFailure): self.read(value)
        self.assertNotIn((5*P,P),value.calls)
        self.assertNotIn((8*P,P),value.calls)

    def test_staged_real_reader_is_stdlib_only(self):
        value=source()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); target=root/'inputs'
            provenance=identity(); provenance['sources']=inputs.source_hashes(ROOT,config_transport=True)
            try:
                inputs.stage_inputs(ROOT,target,NONCE,provenance,config_transport=True)
                code = ("import sys,json;sys.path.insert(0,sys.argv[1]);import config_observation as p;"
                    "raw=sys.stdin.buffer.read();result=p.read_projection(lambda o,n:raw[o:o+n],len(raw),limits=p.reader.CatalogLimits());"
                    "assert not any(n=='yadinassi' or n.startswith('yadinassi.') for n in sys.modules);"
                    "sys.stdout.buffer.write(json.dumps(result,separators=(',',':')).encode('ascii')+b'\\n')")
                env={key:value for key,value in os.environ.items() if key.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP')}
                completed=subprocess.run([sys.executable,'-I','-B','-S','-c',code,str(target)],input=value.full_bytes(),
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=30)
                self.assertEqual(completed.returncode,0,completed.stderr)
                self.assertEqual(json.loads(completed.stdout),self.read(value))
            finally:
                old.writable(root)

    def test_unknown_declarations_reject_before_selected_file_reads(self):
        for changes in ({'count':5},{'names':('PRIVATE',*policy.FIELD_NAMES[1:])},{'lock':'PRIVATE!'}):
            value=source(**changes)
            with self.assertRaises(OracleError): self.read(value)
            self.assertFalse([offset for offset,length in value.calls if offset>=5*P])

    def test_missing_corrupt_and_overlapping_blob_headers_fail_closed(self):
        for mutate in (lambda value: value.page(8).__setitem__(slice(0,2),b'xx'),
                       lambda value: value.page(8).__setitem__(slice(24,28),u32(10)),
                       lambda value: value.page(8).__setitem__(slice(24,28),u32(9))):
            value=source(); mutate(value)
            with self.assertRaises(policy.reader.CatalogError): self.read(value)
            self.assertNotIn((10*P,1),value.calls)


class ConfigRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))

    def test_exact_inventory_and_mutually_exclusive_old_lanes(self):
        self.assertEqual(tuple(map(len,(inputs.LEGACY_V3_SOURCE_FILES,inputs.SOURCE_FILES,
            inputs.RECORD_SOURCE_FILES,inputs.ROW_SOURCE_FILES,inputs.CONFIG_SOURCE_FILES))),(18,20,21,23,22))
        self.assertEqual(set(inputs.CONFIG_SOURCE_FILES), set(inputs.RECORD_SOURCE_FILES)|{policy.MODULE_SOURCE})
        self.assertNotIn('scripts/native_1c_db_oracle/params_observation.py',inputs.CONFIG_SOURCE_FILES)
        for options in ({},{'record_metadata':True},{'record_reader':True},{'params_transport':True},
                        {'params_extraction':True},{'dbnames_identity':True},{'config_transport':True}):
            staged=self.root/('stage'+str(len(list(self.root.iterdir()))))
            provenance=identity(); provenance['sources']=inputs.source_hashes(ROOT,**options)
            inputs.stage_inputs(ROOT,staged,NONCE,provenance,**options)
            self.assertEqual(inputs.verify_inputs(staged,NONCE,**options),provenance)
            self.assertEqual((staged/'config_observation.py').exists(),bool(options.get('config_transport')))
            if options.get('config_transport'):
                self.assertEqual(json.loads((staged/'invocation.json').read_text(encoding='utf-8'))['schema'],7)
                command=host.container_command(staged,'onec-db-oracle-'+'a'*32,NONCE,**options)
                self.assertEqual(command[-1],'--config-transport-observation')
                for wrong in ({},{'record_metadata':True},{'record_reader':True},{'params_transport':True},
                              {'params_extraction':True},{'dbnames_identity':True}):
                    with self.assertRaises(OracleError): inputs.verify_inputs(staged,NONCE,**wrong)
        for name in ('record_metadata','record_reader','params_transport','params_extraction','dbnames_identity'):
            with self.assertRaises(OracleError): inputs.inventory(config_transport=True,**{name:True})
        for bad in (1,None,'true'):
            with self.assertRaises(OracleError): inputs.inventory(config_transport=bad)

    def test_invocation_admission_rejects_stale_missing_extra_or_tampered_fields(self):
        staged=self.root/'admission'
        provenance=identity(); provenance['sources']=inputs.source_hashes(ROOT,config_transport=True)
        inputs.stage_inputs(ROOT,staged,NONCE,provenance,config_transport=True)
        old.writable(staged)
        invocation=staged/'invocation.json'; original=json.loads(invocation.read_text(encoding='utf-8'))
        mutations=(lambda v:v.update(schema=4), lambda v:v.update(lane=inputs.PARAMS_LANE),
            lambda v:v.update(nonce='e'*32), lambda v:v.update(extra='PRIVATE'),
            lambda v:v.pop('lane'),
            lambda v:v['provenance']['sources'].pop(policy.MODULE_SOURCE),
            lambda v:v['provenance']['sources'].update({policy.MODULE_SOURCE:'f'*64}),
            lambda v:v['provenance']['sources'].update({'unexpected.py':'f'*64}))
        for mutate in mutations:
            value=copy.deepcopy(original); mutate(value)
            invocation.write_bytes(protocol.encode(value))
            with self.assertRaises(OracleError): inputs.verify_inputs(staged,NONCE,config_transport=True)
        invocation.write_bytes(protocol.encode(original))
        self.assertEqual(inputs.verify_inputs(staged,NONCE,config_transport=True),provenance)

    def test_host_cli_selects_only_requested_lane_and_rejects_combinations(self):
        with mock.patch.object(host,'ROOT',self.root), mock.patch.object(host,'run_oracle',return_value={'accepted':False}) as run, \
             mock.patch.object(host,'export_report'), mock.patch.dict(os.environ,{},clear=True), \
             contextlib.redirect_stdout(__import__('io').StringIO()),contextlib.redirect_stderr(__import__('io').StringIO()):
            self.assertEqual(host.main(['--execute-approved-image','--file-db-oracle','--config-transport-observation']),1)
            self.assertEqual(run.call_args.kwargs,{'config_transport':True})
            for flag in ('--record-reader-validation','--record-metadata-observation',
                         '--params-transport-observation','--params-dbnames-extraction','--dbnames-identity-validation'):
                with self.assertRaises(SystemExit): host.main(['--execute-approved-image','--file-db-oracle','--config-transport-observation',flag])


    def test_runtime_main_selects_new_policy_without_native_execution(self):
        result,_=fixture();output=__import__('io').BytesIO()
        def controller(backend,report):
            self.assertEqual(report['schema'],10)
            self.assertIn('config_observation',report)
            return __import__('types').SimpleNamespace(run=lambda:result)
        with mock.patch.object(sys,'argv',['run.py','--invocation-nonce',NONCE,'--config-transport-observation']), \
             mock.patch.object(inputs,'verify_inputs',return_value=identity()) as verify, \
             mock.patch.object(fixtures.stage,'Native') as native, \
             mock.patch.object(fixtures.stage,'Controller',side_effect=controller), \
             mock.patch.object(sys,'stdout',__import__('types').SimpleNamespace(buffer=output)):
            self.assertEqual(fixtures.stage.main(),0)
        self.assertEqual(native.call_args.kwargs,{'config_transport':True})
        self.assertEqual(verify.call_args.kwargs,{'config_transport':True})
        self.assertEqual(json.loads(output.getvalue())['lane'],policy.LANE)
        self.assertTrue(output.getvalue().endswith(b'\n'))
        for argv in (['run.py','--invocation-nonce',NONCE,'--config-transport-observation','--params-transport-observation'],
                     ['run.py','--invocation-nonce',NONCE,'--config-transport-observation=1']):
            with mock.patch.object(sys,'argv',argv),mock.patch.object(fixtures.stage,'Native') as native:
                self.assertEqual(fixtures.stage.main(),2);native.assert_not_called()

    @unittest.skipIf(os.name=='nt','POSIX shell launcher')
    def test_shell_launcher_forwards_exact_flag_and_no_extra_arguments(self):
        stub=self.root/'python3'
        stub.write_bytes(b"#!/bin/sh\nprintf '%s\\n' \"$@\"\n");stub.chmod(0o755)
        command=['/bin/bash',str(ROOT/'scripts/native_1c_db_oracle/probe.sh'),'--invocation-nonce',NONCE]
        for flags,wanted in (([],0),(['--config-transport-observation'],0),
                (['--config-transport-observation','--params-transport-observation'],2),
                (['--config-transport-observation=1'],2)):
            completed=subprocess.run(command+flags,env={'PATH':str(self.root)},
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(completed.returncode,wanted)
            self.assertEqual(completed.stderr,b'')
            expected=('\n'.join(['-B','/oracle/run.py','--invocation-nonce',NONCE]+flags)+'\n').encode('ascii')
            self.assertEqual(completed.stdout,expected if wanted==0 else b'')


@unittest.skipIf(os.name=='nt','POSIX anchored frozen postimage boundary')
class ConfigPostimageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.artifacts=self.root/'artifacts'; self.artifacts.mkdir()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root)); normalize_owners(self)
        self.seed=self.artifacts/'seed'; self.seed.mkdir(); self.pre=source(first=b'\0'); self.post=source(first=b'\1')
        (self.seed/'1Cv8.1CD').write_bytes(self.pre.full_bytes())
        snapshots.freeze_database(self.seed,self.artifacts/'baseline',quiescent=lambda:True)
        self.native=fixtures.stage.Native(NONCE,identity(),config_transport=True)
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
        self.assertEqual(result['reader']['table']['table_data_initial_byte'],'one')
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


class ConfigHostCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup); self.addCleanup(lambda:old.writable(self.root))
        self.work=self.root/'work';self.work.mkdir()
        self.identity=identity();self.identity['sources']=inputs.source_hashes(ROOT,config_transport=True)
        self.events=[]

    def invoke(self, *, native_cleanup=(True,True), container_bad=False, staging_bad=False, source_changed=False):
        report,_=fixture(cleanup=native_cleanup)
        report['provenance']=copy.deepcopy(self.identity);report['provenance']['actual_version']=protocol.VERSION
        if report['status']=='ok': report['config_observation']=policy.bind_capture(evidence(),report)
        def provenance(**kwargs):
            self.assertEqual(kwargs,{'config_transport':True})
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
            self.assertEqual(args[1],'run');self.assertEqual(args[-1],'--config-transport-observation')
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
            result=host.run_oracle(self.work,config_transport=True)
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
            self.assertFalse(result['accepted']);self.assertIsNone(result['config_observation'])
            self.assertEqual(result['artifacts'],[])
            old.writable(self.work)
            for child in self.work.iterdir(): shutil.rmtree(child)


if __name__=='__main__': unittest.main()
