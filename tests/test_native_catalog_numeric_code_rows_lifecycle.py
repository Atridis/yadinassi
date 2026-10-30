"""Invented Number images through real observer freeze/cleanup; no native claim."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_readback as base
import test_native_catalog_numeric_code_rows_policy as facts
import test_native_catalog_numeric_code_physical as physical
import catalog_numeric_code_rows_policy as policy
import catalog_numeric_code_rows_reader as reader
import protocol

class ByteBackend(base.ByteBackend):
    compare_description_state=base.fixture.stage.Native.compare_description_state
    compare_numeric_code_state=base.fixture.stage.Native.compare_numeric_code_state
    _clear_numeric_private_state=base.fixture.stage.Native._clear_numeric_private_state
    def cleanup(self):
        self._clear_numeric_private_state()
        return super().cleanup()
    def __init__(self,root,provenance,case='number3',fault=None):
        super().__init__(root,provenance)
        self.numeric_rows=True;self.numeric_case=case;self.description_case=None;self.description_rows=False
        self.description_policy=policy;self.description_witness=None
        self.record_policy=None;self.record_module=None;self.catalog_binding=False;self.catalog_field_matrix=False
        self.observation=None;self.fault=fault
    def freeze(self,database,identifier):
        base.fixture.FixtureNative.freeze(self,database,identifier)
        payload=64 if self.dbs[identifier]['applied']==2 else 32
        if self.fault=='applied_width' and identifier=='applied':payload=32
        edit=(lambda ds:ds[:4]+[('_CODE','N',0,7,0,'CS')]+ds[5:])if self.fault=='unresolved'else None
        value=physical.source(facts.measurement.CASES[self.numeric_case][0],123,payload,edit=edit)
        writer=self.artifacts/'synthetic_producer';writer.mkdir();(writer/'1Cv8.1CD').write_bytes(value.full_bytes())
        return base.fixture.stage.Native.freeze(self,writer,identifier)
    def observe(self,identifier,designer):
        if identifier in policy.TARGETS:return self.observe_record_state(identifier,designer)
        value=base.fixture.FixtureNative.observe(self,identifier,designer)
        if value['count']:value['code']='observed_number'
        return value
    def enterprise(self,database,operation,*,token=None):
        identifier=self.clone_origins[database];self.event('enterprise',operation,identifier)
        logical=base.fixture.FixtureNative.observe(self,identifier,self.dbs[identifier]['designer'])
        if logical['count']:logical['code']='observed_number'
        result=dict(schema=1,nonce=self.nonce,token=token,operation=operation,status='ok',actual_version=protocol.VERSION,
            user='NativeOracleCRUD',role_verified=True,users_verified=False,nonprivileged=True,
            metadata_version=logical['applied_version'],payload_length=logical['payload_length'],amount_digits=9,amount_scale=2,
            **{k:logical[k]for k in('count','code','payload','amount','deletion_mark','same_reference')})
        policy.marker(protocol.encode(result),nonce=self.nonce,token=token,operation=operation)
        self.description_witness=facts.witness(self.numeric_case,self.nonce,'f'*32 if self.fault=='token'else token,
            present=logical['count']==1,payload=logical['payload_length'],code='124'if self.fault=='native_differs'else'123',
            identifier='11111111-1111-1111-1111-111111111111'if self.fault=='uuid'else'52525252-5252-5252-5252-525252525252')
        path=database/'1Cv8.1CD';raw=bytearray(path.read_bytes());raw[16]=ord('Q');path.write_bytes(raw)
        return result
    def observe_record_state(self,identifier,designer):
        result=super().observe_record_state(identifier,designer)
        if identifier=='applied' and self.fault in('origin','postimage'):self.record_pending[2][self.fault]['sha256']='0'*64
        return result

@unittest.skipUnless(base.POSIX,'requires existing POSIX frozen descriptor boundary')
class NumericLifecycleTests(unittest.TestCase):
    def setUp(self):base.normalize_owners(self)
    def run_case(self,case='number3',fault=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        provenance=facts.provenance();report=policy.empty_report(base.NONCE,provenance,numeric_case=case)
        backend=ByteBackend(Path(temp.name).resolve(),provenance,case,fault)
        controller=base.fixture.stage.Controller(backend,report);backend.controller=controller
        return controller.run(),backend
    def test_three_generic_reads_after_same_observer_with_payload_migration(self):
        for case in policy.CASES:
            calls=[];original=reader.read_numeric_code_rows
            def read(read_at,size,**kw):calls.append(set(kw));return original(read_at,size,**kw)
            with mock.patch.object(reader,'read_numeric_code_rows',read):report,backend=self.run_case(case)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(calls,[{'catalog_name','limits'}]*3)
            states=report['numeric_code_rows_measurement']['states']
            self.assertEqual([x['snapshot']for x in states],list(policy.TARGETS))
            self.assertEqual(len({x['observe_token']for x in states}),4)
            self.assertIsNone(states[0]['comparison'])
            self.assertIn(('redump','applied',2),backend.events)
            report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
            policy.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=report['provenance'],final=True)
            self.assertIsNone(backend.record_pending);self.assertFalse(list(backend.artifacts.iterdir()))
    def test_stale_uuid_metadata_and_postimages_fail_scrub(self):
        for fault in('token','uuid','origin','postimage','applied_width'):
            with self.subTest(fault=fault):
                report,backend=self.run_case(fault=fault)
                self.assertEqual(report['status'],'failed',report)
                self.assertIsNone(report['numeric_code_rows_measurement'])
                self.assertIsNone(backend.description_witness)
                self.assertIsNone(backend.record_pending)
                self.assertFalse(list(backend.artifacts.iterdir()))
    def test_code_difference_or_unresolved_layout_fails_closed(self):
        for fault in ('native_differs','unresolved'):
            report,backend=self.run_case(fault=fault)
            self.assertEqual(report['status'],'failed')
            self.assertIsNone(report['numeric_code_rows_measurement'])
            self.assertIsNone(backend.description_witness)
            self.assertIsNone(backend.record_pending)

    def test_freeze_and_reader_failures_scrub_private_state(self):
        stage=base.fixture.stage
        original=stage.freeze_database
        for fault in ('freeze','quiescence','reader'):
            def freeze(source,target,**kw):
                if target.name=='record_observer_frozen':
                    if fault=='freeze':raise RuntimeError('synthetic freeze failure')
                    if fault=='quiescence':kw['quiescent']=lambda:False
                return original(source,target,**kw)
            with self.subTest(fault=fault),mock.patch.object(stage,'freeze_database',freeze):
                with mock.patch.object(reader,'read_numeric_code_rows',side_effect=RuntimeError('synthetic reader failure')) if fault=='reader' else mock.patch.object(reader,'read_numeric_code_rows',wraps=reader.read_numeric_code_rows):
                    report,backend=self.run_case()
                self.assertEqual(report['status'],'failed')
                self.assertIsNone(report['numeric_code_rows_measurement'])
                self.assertIsNone(backend.description_witness)
                self.assertIsNone(backend.record_pending)
                self.assertFalse(list(backend.artifacts.iterdir()))

    def test_real_native_cleanup_clears_numeric_state_even_when_cleanup_fails(self):
        native=base.fixture.stage.Native.__new__(base.fixture.stage.Native)
        native.numeric_case='number3';native.description_witness=object();native.record_pending=object()
        native.baseline=None;native.services=[];native.initial=None
        native.root=mock.Mock();native.root.exists.side_effect=OSError('synthetic cleanup failure')
        self.assertEqual(native.cleanup(),(True,False))
        self.assertIsNone(native.description_witness);self.assertIsNone(native.record_pending)
        native.numeric_case=None;value=object();native.description_witness=value;native.record_pending=value
        native._clear_numeric_private_state()
        self.assertIs(native.description_witness,value);self.assertIs(native.record_pending,value)
