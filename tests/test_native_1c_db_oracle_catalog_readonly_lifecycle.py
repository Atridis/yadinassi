"""Invented files through actual six-readback producer; not native evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_readback as old
import test_catalog_binding_integration as bytes_fixture
import test_native_1c_db_oracle_catalog_attribute_binding as config_fixture
import catalog_readonly_binding as policy
import catalog_binding_reader as coordinator
import inputs
import protocol
from test_filedb_catalog import u32
from test_filedb_records import row


def identity():
    result=old.identity();result['sources']={p:'c'*64 for p in inputs.CATALOG_BINDING_SOURCE_FILES}
    return result


_old_native_projection=old.native_projection

def native_projection():
    value=_old_native_projection();table=value['table'];table['storage_name']='_Reference19'
    names=('_IDRRef','_Version','_Marked','_PredefinedID','_Code','_Fld62','_Fld741')
    for field,name in zip(table['fields'],names):field['storage_name']=name
    return value


class ByteBackend(old.ByteBackend):
    def __init__(self,root,provenance,**kwargs):
        super().__init__(root,provenance,**kwargs)
        self.catalog_binding=True;self.catalog_field_matrix=True
        self.record_policy=policy;self.record_module=coordinator
        self.identity_manifest=config_fixture.manifest();self.identity_baseline_verified=True

    def freeze(self,database,identifier):
        old.fixture.FixtureNative.freeze(self,database,identifier)
        logical=self.dbs[identifier]['row'];value=bytes_fixture.source()
        rows=b'' if logical is None else row(logical[0],b'\x10\x00\x00\x01\x25'
            if logical[1]=='1.25' else b'\x00\x00\x00\x02\x50')
        if self.mutate_image==(identifier,'origin_value') and rows:rows=row('WRONG')
        if self.mutate_image==(identifier,'origin_count'):rows=b''
        data=b'\x01'+b'R'*126+rows
        value.page(40)[16:24]=len(data).to_bytes(8,'little')
        value.page(43)[:]=bytes(len(value.page(43)));value.page(43)[:len(data)]=data
        writer=self.artifacts/'synthetic_producer';writer.mkdir();(writer/'1Cv8.1CD').write_bytes(value.full_bytes())
        return old.fixture.stage.Native.freeze(self,writer,identifier)

    def enterprise(self,database,operation,*,token=None):
        mutation=self.mutate_image;self.mutate_image=None
        try:
            with mock.patch.object(old,'native_projection',native_projection):
                result=super().enterprise(database,operation,token=token)
        finally:self.mutate_image=mutation
        identifier=self.clone_origins[database]
        if mutation==(identifier,'observer_value') and operation=='observe':
            path=database/'1Cv8.1CD';raw=bytearray(path.read_bytes())
            raw[43*8192+127:43*8192+254]=row('WRONG');path.write_bytes(raw)
        return result


def run_fixture(test,**kwargs):
    temp=tempfile.TemporaryDirectory();test.addCleanup(temp.cleanup)
    provenance=identity();report=policy.empty_report(old.NONCE,provenance)
    backend=ByteBackend(Path(temp.name).resolve(),provenance,**kwargs)
    controller=old.fixture.stage.Controller(backend,report);backend.controller=controller
    return controller.run(),backend


@unittest.skipUnless(old.POSIX,'requires descriptor-relative POSIX operations')
class BindingLifecycleTests(unittest.TestCase):
    def setUp(self):old.normalize_owners(self)

    def test_actual_six_independent_binding_reads_and_final_report(self):
        calls=[];original=coordinator.read_catalog_binding
        def observed(read_at,size,**kwargs):
            calls.append(set(kwargs));return original(read_at,size,**kwargs)
        with mock.patch.object(coordinator,'read_catalog_binding',observed):report,backend=run_fixture(self)
        self.assertEqual(report['status'],'ok',report)
        self.assertEqual(calls,[{'catalog_name','limits'}]*6)
        report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
        policy.validate_report(protocol.encode(report),nonce=old.NONCE,provenance=report['provenance'],final=True)
        self.assertEqual([x['snapshot'] for x in report['record_readback']['states']],list(policy.TARGETS))
        self.assertIsNone(backend.record_pending);self.assertFalse(list(backend.artifacts.iterdir()))
        raw=protocol.encode(report['record_readback'])
        for forbidden in (b'Payload',b'Amount',b'_FLD',b'_Reference',b'alpha',b'beta',b'raw_descriptor',b'placements'):
            self.assertNotIn(forbidden,raw)

    def test_both_image_values_and_count_are_checked_and_cleanup_preserved(self):
        for identifier,mutation in (('created','origin_value'),('updated','observer_value'),('created','origin_count')):
            with self.subTest(identifier=identifier,mutation=mutation):
                report,backend=run_fixture(self,mutate_image=(identifier,mutation))
                self.assertEqual(report['status'],'failed',report)
                self.assertEqual(report['failure_kind'],policy.FAILURE_KIND)
                self.assertTrue(report['cleanup']['native_processes_stopped'])
                self.assertTrue(report['cleanup']['raw_files_removed'])
                self.assertFalse(list(backend.artifacts.iterdir()))
