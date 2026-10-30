"""Synthetic public typed read at same-session postimages, including applied64."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_catalog_description_lifecycle as old
import test_native_catalog_description_rows_policy as facts
import catalog_description_rows as policy
import catalog_description_physical as reader
import catalog_description_measurement as measurement
import protocol

class ByteBackend(old.ByteBackend):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.description_rows=True;self.description_policy=policy
    def observe(self,identifier,designer):
        if identifier in policy.TARGETS:return self.observe_record_state(identifier,designer)
        return super().observe(identifier,designer)
    def freeze(self,database,identifier):
        old.old.old.fixture.FixtureNative.freeze(self,database,identifier)
        length,created,updated=measurement.CASES[self.description_case]
        payload=64 if self.dbs[identifier]['applied']==2 else 32
        if self.fault=='applied_width' and identifier=='applied':payload=32
        value=old.physical.source(length,created if identifier=='created' else updated,payload)
        writer=self.artifacts/'synthetic_producer';writer.mkdir();(writer/'1Cv8.1CD').write_bytes(value.full_bytes())
        return old.old.old.fixture.stage.Native.freeze(self,writer,identifier)
    def enterprise(self,database,operation,*,token=None):
        identifier=self.clone_origins[database]
        self.event('enterprise',operation,identifier)
        logical=old.old.old.fixture.FixtureNative.observe(self,identifier,self.dbs[identifier]['designer'])
        result=dict(schema=1,nonce=self.nonce,token=token,operation=operation,status='ok',actual_version=protocol.VERSION,
            user='NativeOracleCRUD',role_verified=True,users_verified=False,nonprivileged=True,
            metadata_version=logical['applied_version'],payload_length=logical['payload_length'],amount_digits=9,amount_scale=2,
            **{k:logical[k] for k in ('count','code','payload','amount','deletion_mark','same_reference')})
        protocol.marker(protocol.encode(result),nonce=self.nonce,token=token,operation=operation)
        _,created,updated=measurement.CASES[self.description_case]
        present=logical['count']==1;text=created if identifier=='created' else updated
        if self.fault=='native_differs':text='different'
        data=dict(schema=3,nonce=self.nonce,token=token,case=self.description_case,operation=operation,present=present,
            actual_description=text if present else '',actual_uuid=facts.NATIVE_UUID if present else '')
        if self.fault=='uuid' and present:data['actual_uuid']='11111111-1111-1111-1111-111111111111'
        if self.fault=='token':data['token']='f'*32
        self.description_witness=measurement.validate_witness(json.dumps(data).encode(),nonce=self.nonce,
            token=data['token'],case=self.description_case,operation=operation,rows=True)
        path=database/'1Cv8.1CD';raw=bytearray(path.read_bytes());raw[16]=ord('Q');path.write_bytes(raw)
        return result
    def observe_record_state(self,identifier,designer):
        result=super().observe_record_state(identifier,designer)
        if identifier=='applied' and self.fault=='applied_postimage':self.record_pending[2]['postimage']['sha256']='0'*64
        return result

@unittest.skipUnless(old.old.old.POSIX,'requires POSIX frozen descriptor boundary')
class RowsLifecycleTests(unittest.TestCase):
    def setUp(self):old.old.old.normalize_owners(self)
    def run_case(self,case='description8',fault=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        provenance=facts.provenance();report=policy.empty_report(old.old.old.NONCE,provenance,description_case=case)
        backend=ByteBackend(Path(temp.name).resolve(),provenance,case,fault)
        controller=old.old.old.fixture.stage.Controller(backend,report);backend.controller=controller
        return controller.run(),backend
    def test_three_public_typed_postimage_reads_and_applied64(self):
        for case in measurement.CASES:
            calls=[];original=reader.read_description_rows
            def read(read_at,size,**kwargs):calls.append(set(kwargs));return original(read_at,size,**kwargs)
            with mock.patch.object(reader,'read_description_rows',read),mock.patch.object(reader,'read_description',side_effect=AssertionError('old reader')):
                report,backend=self.run_case(case)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(calls,[{'catalog_name','limits'}]*3)
            states=report['description_measurement']['states']
            self.assertEqual([s['snapshot'] for s in states],list(policy.TARGETS))
            self.assertEqual([s['comparison']['physical']['payload_length'] for s in states[1:]],[32,32,64])
            self.assertEqual(len({s['observe_token'] for s in states}),4)
            self.assertIn(('redump','applied',2),backend.events)
            report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
            policy.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=report['provenance'],final=True)
            self.assertIsNone(backend.record_pending);self.assertFalse(list(backend.artifacts.iterdir()))
    def test_all_mismatches_fail_closed_with_cleanup(self):
        for fault in ('uuid','native_differs','token','origin','postimage','applied_postimage','applied_width'):
            with self.subTest(fault=fault):
                report,backend=self.run_case(fault=fault)
                self.assertEqual(report['status'],'failed',report)
                self.assertIsNone(report['description_measurement'])
                self.assertTrue(report['cleanup']['native_processes_stopped'])
                self.assertTrue(report['cleanup']['raw_files_removed'])
                self.assertFalse(list(backend.artifacts.iterdir()))
