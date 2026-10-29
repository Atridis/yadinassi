"""Constructed bytes through real frozen observer and controller lifecycle."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_catalog_readonly_lifecycle as old
import test_native_catalog_description_physical as physical
import catalog_description_measurement as witness_module
import catalog_description_policy as policy
import catalog_description_physical as reader
import inputs
import protocol

class ByteBackend(old.ByteBackend):
    compare_description_state = old.old.fixture.stage.Native.compare_description_state
    def __init__(self,root,provenance,case='description8',fault=None):
        super().__init__(root,provenance)
        self.description_case=case;self.description_policy=policy;self.description_witness=None
        self.record_policy=None;self.record_module=None;self.catalog_binding=False;self.catalog_field_matrix=False
        self.observation=None;self.fault=fault
    def freeze(self,database,identifier):
        old.old.fixture.FixtureNative.freeze(self,database,identifier)
        logical=self.dbs[identifier]['row']
        length,create,update=witness_module.CASES[self.description_case]
        text=create if identifier=='created' else update
        value=physical.source(length,text)
        # Baseline image is never claimed as one-active; observer witness proves absence.
        if logical is None:
            value.page(40)[16:24]=(145 if length==8 else 163).to_bytes(8,'little')
        writer=self.artifacts/'synthetic_producer';writer.mkdir();(writer/'1Cv8.1CD').write_bytes(value.full_bytes())
        return old.old.fixture.stage.Native.freeze(self,writer,identifier)
    def enterprise(self,database,operation,*,token=None):
        result=super().enterprise(database,operation,token=token)
        if operation=='observe':
            identifier=self.clone_origins[database]
            length,created,updated=witness_module.CASES[self.description_case]
            present=self.dbs[identifier]['row'] is not None
            text=created if identifier=='created' else updated
            if self.fault=='native_differs':text='unexpected'
            data=dict(schema=2,nonce=self.nonce,token=token or 'e'*32,case=self.description_case,
                operation='observe',present=present,actual_description=text if present else '')
            if self.fault=='token':data['token']='f'*32
            self.description_witness=witness_module.validate_witness(json.dumps(data).encode(),
                nonce=self.nonce,token=data['token'],case=self.description_case,operation='observe')
        return result
    def observe_record_state(self,identifier,designer):
        result=super().observe_record_state(identifier,designer)
        if self.fault in ('origin','postimage') and identifier=='created':
            self.record_pending[2][self.fault]['sha256']='0'*64
        return result

@unittest.skipUnless(old.old.POSIX,'requires POSIX frozen descriptor boundary')
class DescriptionLifecycleTests(unittest.TestCase):
    def setUp(self):old.old.normalize_owners(self)
    def run_case(self,case='description8',fault=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        provenance=old.identity();provenance['sources']={key:'c'*64 for key in inputs.CATALOG_DESCRIPTION_SOURCE_FILES}
        report=policy.empty_report(old.old.NONCE,provenance,description_case=case)
        backend=ByteBackend(Path(tmp.name).resolve(),provenance,case,fault)
        controller=old.old.fixture.stage.Controller(backend,report);backend.controller=controller
        return controller.run(),backend
    def test_two_postimage_only_reads_same_observer_witness_and_cleanup(self):
        for case in witness_module.CASES:
            calls=[];original=reader.read_description
            def read(read_at,size,**kwargs):calls.append(set(kwargs));return original(read_at,size,**kwargs)
            with mock.patch.object(reader,'read_description',read):report,backend=self.run_case(case)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(calls,[{'catalog_name','limits'}]*2)
            report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
            policy.validate_report(protocol.encode(report),nonce=old.old.NONCE,provenance=report['provenance'],final=True)
            self.assertIsNone(backend.record_pending)
            self.assertFalse(list(backend.artifacts.iterdir()))
    def test_stale_token_and_image_digests_fail_and_scrub(self):
        for fault in ('token','origin','postimage'):
            report,backend=self.run_case(fault=fault)
            self.assertEqual(report['status'],'failed',report)
            self.assertIsNone(report['description_measurement'])
            self.assertFalse(list(backend.artifacts.iterdir()))
    def test_different_actual_readback_remains_measurement(self):
        report,_=self.run_case(fault='native_differs')
        self.assertEqual(report['status'],'ok',report)
        self.assertEqual(report['description_measurement']['states'][1]['comparison']['status'],'readback_differs')

if __name__=='__main__':unittest.main()
