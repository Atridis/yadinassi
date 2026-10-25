"""Real synthetic bytes -> actual pinned reader -> strict finite report.

The native API/CRUD producer is simulated, never evidence of a 1C execution.
Filesystem freeze/hash/descriptor reads and row decoding are the production seam.
"""
from __future__ import annotations
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage'), str(ROOT/'tests')]
import inputs
import protocol
import record_observation as observation
import record_validation as policy
import snapshots
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixture
from test_native_1c_db_oracle_catalog_reader import normalize_owners, POSIX
import test_filedb_records as producer

NONCE = fixture.NONCE
READER = policy.load_reader(ROOT/'yadinassi/storage/filedb_records.py')


def identity():
    value = fixture.provenance()
    value['sources'] = {path: 'c'*64 for path in inputs.ROW_SOURCE_FILES}
    return value


def native_projection():
    logical = (('Ссылка',''), ('ВерсияДанных',''), ('ПометкаУдаления',''),
        ('ИмяПредопределенныхДанных',''), ('Код',''),
        ('Payload','Справочник.NativeOracleItems.Реквизит.Payload'),
        ('Amount','Справочник.NativeOracleItems.Реквизит.Amount'))
    return {'schema':1, 'target':observation.TARGET, 'table':{'storage_name':'Synthetic',
        'logical_name':'Справочник.NativeOracleItems','metadata_name':'Справочник.NativeOracleItems',
        'fields':[{'storage_name':declaration[0], 'logical_name':names[0], 'metadata_name':names[1],
                   'type_text':''} for declaration,names in zip(producer.DECLARATIONS,logical)]}}


class ByteBackend(fixture.FixtureNative):
    """Synthetic native producer; production observer/freezer/comparator methods."""
    temporary_clone = fixture.stage.Native.temporary_clone
    observe_record_state = fixture.stage.Native.observe_record_state
    observe_record_metadata = fixture.stage.Native.observe_record_metadata
    prepare_record_profile = fixture.stage.Native.prepare_record_profile
    remove = fixture.stage.Native.remove
    physical_summary = fixture.stage.Native.physical_summary

    def __init__(self, root, provenance, *, mutate_image=None, format_item=0, fail=None):
        super().__init__(provenance, fail)
        self.root=root; self.artifacts=root/'artifacts'; self.artifacts.mkdir()
        self.nonce=NONCE; self.stage='preflight'; self.observation=observation
        self.record_policy=policy; self.record_module=READER; self.record_pending=None
        self.record_names=self.record_profile=None; self.reader_attempted=False
        self.clone_origins={}; self.tokens=0; self.reservations=[]
        self.mutate_image=mutate_image; self.format_item=format_item

    def begin_stage(self, stage): self.stage=stage
    def quiescent(self): return True
    def remaining(self): return 120
    def command_context(self, operation): return contextlib.nullcontext()
    def budgets(self, reserve=0): self.reservations.append(reserve); return snapshots.budget_check(self.artifacts,reserve)

    def freeze(self, database, identifier):
        super().freeze(database,identifier)
        logical=self.dbs[identifier]['row']
        rows=[] if logical is None else [producer.row(logical[0], b'\x10\x00\x00\x01\x25'
            if logical[1]=='1.25' else b'\x00\x00\x00\x02\x50')]
        raw=producer.source(rows,format_item=self.format_item).full_bytes()
        if self.mutate_image == (identifier,'origin_value') and rows:
            raw=producer.source([producer.row('WRONG')],format_item=self.format_item).full_bytes()
        if self.mutate_image == (identifier,'origin_count'):
            raw=producer.source([],format_item=self.format_item).full_bytes()
        writer=self.artifacts/'synthetic_producer'; writer.mkdir(); (writer/'1Cv8.1CD').write_bytes(raw)
        return fixture.stage.Native.freeze(self,writer,identifier)

    def clone(self, identifier, label):
        if label=='writer': return super().clone(identifier,label)
        self.event('clone',identifier,label)
        path=self.artifacts/label
        self.budgets(self.physical_summary(self.artifacts/identifier/'1Cv8.1CD')['bytes'])
        snapshots.clone_database(self.artifacts/identifier,path,budget_root=self.artifacts)
        self.clone_origins[path]=identifier
        return path

    def redump(self,database,designer): self.event('redump',self.clone_origins[database],designer)

    def observe(self, identifier, designer):
        if identifier in policy.TARGETS: return self.observe_record_state(identifier,designer)
        return super().observe(identifier,designer)

    def enterprise(self,database,operation,*,token=None):
        identifier=self.clone_origins[database]
        self.event('enterprise',operation,identifier)
        value={'schema':1,'nonce':NONCE,'token':token,'operation':operation,'status':'ok',
            'actual_version':protocol.VERSION,'user':'NativeOracleSetup','role_verified':True,
            'users_verified':True,'nonprivileged':True,'metadata_version':1,
            'payload_length':32,'amount_digits':9,'amount_scale':2,
            **{name:None for name in ('count','code','payload','amount','deletion_mark','same_reference')}}
        if operation==observation.OPERATION:
            value['record_metadata']=native_projection()
            if self.fail=='mapping': value['record_metadata']['table']['fields'][5]['logical_name']='Wrong'
            observation.marker(protocol.encode(value),nonce=NONCE,token=token)
        else:
            logical=super().observe(identifier,1)
            value.update({name:logical[name] for name in ('count','code','payload','amount','deletion_mark','same_reference')})
            value.update(user='NativeOracleCRUD',users_verified=False)
            protocol.marker(protocol.encode(value),nonce=NONCE,token=token,operation='observe')
        # A real session need not leave bytes identical. Opaque header change is safe.
        path=database/'1Cv8.1CD'; raw=bytearray(path.read_bytes()); raw[16]=ord('Q'); path.write_bytes(raw)
        if self.mutate_image==(identifier,'observer_value') and operation=='observe':
            path.write_bytes(producer.source([producer.row('WRONG')]).full_bytes())
        return value

    def compare(self,*names):
        self.event('compare',*names)
        return snapshots.compare_files(*(self.artifacts/name/'1Cv8.1CD' for name in names))

    def compare_pair(self,*names):
        self.event('compare_pair',*names)
        return snapshots.compare_pair(*(self.artifacts/name/'1Cv8.1CD' for name in names))

    def compare_record_state(self, identifier, report):
        if self.mutate_image in ((identifier,'origin_binding'),(identifier,'postimage_binding')):
            key = self.mutate_image[1].removesuffix('_binding')
            self.record_pending[2][key]['sha256'] = 'f'*64
        return fixture.stage.Native.compare_record_state(self, identifier, report)

    def cleanup(self):
        self.event('cleanup')
        for path in list(self.artifacts.iterdir()): self.remove(path)
        return self.clean


def run_fixture(test, **kwargs):
    temp=tempfile.TemporaryDirectory(); test.addCleanup(temp.cleanup)
    value=identity(); report=policy.empty_report(NONCE,value)
    backend=ByteBackend(Path(temp.name),value,**kwargs)
    controller=fixture.stage.Controller(backend,report); backend.controller=controller
    return controller.run(),backend


@unittest.skipUnless(POSIX, 'requires descriptor-relative POSIX file operations')
class ProducerReaderReportTests(unittest.TestCase):
    def setUp(self): normalize_owners(self)

    def validate(self,report,final=False):
        return policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=report['provenance'],final=final)

    def test_actual_reader_full_lifecycle_and_opaque_postimage_difference(self):
        report,backend=run_fixture(self)
        self.assertEqual(report['status'],'ok',report)
        self.validate(report)
        report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
        self.validate(report,True)
        self.assertEqual(len(report['stages']),13);self.assertEqual(len(report['snapshots']),11)
        self.assertEqual(report['record_validation'],policy.VERDICT)
        capture=report['record_readback']
        self.assertEqual([s['snapshot'] for s in capture['states']],list(policy.TARGETS))
        self.assertTrue(all(s['origin_sha256']!=s['observer_sha256'] for s in capture['states']))
        self.assertEqual([event for event in backend.events if event[0]=='enterprise'],[
            ('enterprise','observe','baseline'),('enterprise',observation.OPERATION,'baseline'),
            ('enterprise','observe','created'),('enterprise','observe','updated')])
        self.assertIsNone(backend.record_pending)
        self.assertFalse(list(backend.artifacts.iterdir()))
        self.assertTrue(any(backend.reservations))
        raw=protocol.encode(capture)
        for forbidden in (b'RRRR',b'VVVV',b'PPPP',b'WRONG',b'raw_descriptor',b'placements',b'Files'):
            self.assertNotIn(forbidden,raw)

    def test_origin_and_observer_values_and_count_are_each_genuine(self):
        for mutation in (('created','origin_value'),('updated','origin_value'),
                         ('created','origin_count'),('created','observer_value')):
            with self.subTest(mutation=mutation):
                report,backend=run_fixture(self,mutate_image=mutation)
                self.assertEqual(report['status'],'failed')
                self.assertEqual(report['failure_kind'],policy.FAILURE_KIND)
                self.assertEqual(report['record_validation'],'failed')
                self.assertNotIn('metadata',report['record_readback'])
                self.validate(report)
                self.assertFalse(list(backend.artifacts.iterdir()))

    def test_format_failure_is_tiny_finite_and_not_adaptive(self):
        for value,code in ((1,'format_integer_nonzero'),('0','format_string_zero'),
                           ('PRIVATE_SECRET','format_string_other'),(('PRIVATE',123),'format_list')):
            with self.subTest(code=code):
                report,backend=run_fixture(self,format_item=value)
                self.assertEqual(report['failure_kind'],policy.FAILURE_KIND,report)
                self.assertEqual(report['record_readback'],{'schema':7,'status':'failed',
                    'category':'unsupported_layout','code':code})
                self.validate(report)
                self.assertNotIn(b'PRIVATE',protocol.encode(report))
                self.assertFalse(list(backend.artifacts.iterdir()))

    def test_private_original_and_postimage_binding_must_match_read_descriptor(self):
        for state in policy.TARGETS:
            for image in ('origin_binding','postimage_binding'):
                with self.subTest(state=state,image=image):
                    report,backend=run_fixture(self,mutate_image=(state,image))
                    self.assertEqual(report['status'],'failed')
                    self.assertNotEqual(report['record_validation'],policy.VERDICT)
                    self.assertIsNone(report['record_readback'])
                    self.validate(report)
                    self.assertFalse(list(backend.artifacts.iterdir()))

    def test_pending_baseline_removed_on_mapping_and_native_lifecycle_failures(self):
        for fail in ('mapping','create','export_cf'):
            with self.subTest(fail=fail):
                report,backend=run_fixture(self,fail=fail)
                self.assertEqual(report['status'],'failed')
                self.validate(report)
                self.assertFalse(list(backend.artifacts.iterdir()))
                self.assertNotEqual(report['record_validation'],policy.VERDICT)

    def test_success_transport_binding_and_cleanup_mutations_reject(self):
        good,_=run_fixture(self)
        good['cleanup'].update(container_removed=True,private_staging_removed=True);good['accepted']=True
        edits=[lambda r:r['record_readback']['states'][1].update(origin_sha256='f'*64),
               lambda r:r['record_readback']['states'][1].update(observe_token=r['record_readback']['metadata']['token']),
               lambda r:r['record_readback'].update(profile_sha256='f'*64),
               lambda r:r['record_readback'].update(record_reader_source_sha256='f'*64),
               lambda r:r['record_readback']['metadata']['native']['table']['fields'][5].update(logical_name='Wrong'),
               lambda r:r.update(schema=5),lambda r:r.update(record_observation={})]
        for key in good['cleanup']: edits.append(lambda r,key=key:r['cleanup'].__setitem__(key,False))
        for edit in edits:
            value=copy.deepcopy(good);edit(value)
            with self.assertRaises((OracleError,policy.ReadbackFailure)): self.validate(value,True)

    def test_late_cleanup_discards_all_capture_and_success(self):
        for key in ('native_processes_stopped','raw_files_removed','container_removed','private_staging_removed'):
            report,_=run_fixture(self)
            report['cleanup'].update(container_removed=True,private_staging_removed=True)
            report['cleanup'][key]=False
            report.update(status='failed',failed_stage='cleanup',failure_kind='cleanup_unverified',accepted=False,artifacts=[])
            report['stages'][-1].update(status='failed',checks={name:report['cleanup'][name]
                for name in ('native_processes_stopped','raw_files_removed')})
            policy.discard_capture(report,final=True)
            self.assertIsNone(report['record_readback']);self.validate(report,True)

    def test_format_diagnostic_dropped_after_host_cleanup_failure(self):
        report,_=run_fixture(self,format_item='0')
        report['cleanup'].update(container_removed=False,private_staging_removed=True)
        policy.discard_capture(report,final=True)
        self.assertIsNone(report['record_readback'])


class PureAdmissionTests(unittest.TestCase):
    def test_private_row_errors_keep_exact_class_code_discipline(self):
        pairs=((policy.filedb_catalog.InvalidStructure,'table_data_header_role','structural_rejection'),
               (policy.filedb_catalog.UnsupportedLayout,'missing_table_data_header','unsupported_layout'))
        for kind,code,category in pairs:
            failure=policy.reader_failure(kind(code))
            self.assertEqual((failure.category,failure.code),(category,code))
            wrong=policy.filedb_catalog.UnsupportedLayout if kind is policy.filedb_catalog.InvalidStructure else policy.filedb_catalog.InvalidStructure
            class Forged(kind): pass
            for error in (wrong(code),Forged(code),kind('PRIVATE_UNKNOWN')):
                with self.assertRaises(OracleError) as caught: policy.reader_failure(error)
                self.assertEqual(caught.exception.kind,'unexpected_failure')

    def test_explicit_profile_does_not_learn_format_or_offsets(self):
        measured=producer.source()
        catalog=policy.filedb_catalog.read_catalog(measured.read_at,measured.size)
        native=native_projection();_,physical=observation.project_catalog(catalog,native)
        names,profile=policy.mapping_profile({'native':native,'reader':physical},READER)
        self.assertIs(type(profile.format_item),int);self.assertEqual(profile.format_item,0)
        self.assertEqual(profile.record_size,127);self.assertEqual(names['payload'],'TEXT')
        self.assertEqual(tuple(x.offset for x in profile.placements),(17,1,33,34,50,56,122))
        for mutate in (lambda p:p['table']['fields'].reverse(),
                       lambda p:p['table']['fields'][1].update(length=16),
                       lambda p:p['table'].update(record_lock_token='1')):
            bad=copy.deepcopy(physical);mutate(bad)
            with self.assertRaises(policy.ReadbackFailure): policy.mapping_profile({'native':native,'reader':bad},READER)

    def test_core_loader_reuses_pinned_catalog_exception_and_limit_identity(self):
        self.assertIs(READER.CatalogLimits,policy.filedb_catalog.CatalogLimits)
        self.assertIs(READER.UnsupportedLayout,policy.filedb_catalog.UnsupportedLayout)

    def test_historical_validators_do_not_accept_new_lane(self):
        report=policy.empty_report(NONCE,identity())
        for validator in (observation.validate_report,policy.comparison.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=report['provenance'])

if __name__=='__main__':unittest.main()
