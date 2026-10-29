"""Invented two-pattern bytes through real six-readback lifecycle; not native evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_1c_db_oracle_catalog_readonly_lifecycle as old
import catalog_reference_identity as policy
from catalog_reference_native import ReferenceWitness
import inputs
import protocol


class ByteBackend(old.ByteBackend):
    def __init__(self,root,provenance,*,case='distinct_a',fault=None):
        super().__init__(root,provenance)
        self.record_policy=policy;self.reference_case=case;self.reference_witness=None;self.reference_installation=None;self.fault=fault
        # This invented backend models the independently rendered seed artifact.
        self.reference_module_sha256=policy.rendered_module_sha256(self.nonce,case) if fault!='module' else '0'*64

    def freeze(self,database,identifier):
        original=old.row
        canonical=bytes.fromhex(policy.CASE_UUIDS[self.reference_case].replace('-',''))
        physical=canonical[::-1] if self.fault=='permutation' and identifier=='updated' else canonical
        def row(*args,**kwargs):
            raw=original(*args,**kwargs)
            return raw[:17]+physical+raw[33:]
        with mock.patch.object(old,'row',row):return super().freeze(database,identifier)

    def enterprise(self,database,operation,*,token=None):
        value=super().enterprise(database,operation,token=token)
        if operation=='observe':
            present=self.clone_origins[database]!='baseline'
            witness=ReferenceWitness('ok',present,present,'EFT'*4 if present else 'EFT'*3+'NNN',
                'TFE'*4 if present else 'TFE'*3+'NNN',policy.CASE_UUIDS[self.reference_case] if present else '')
            if self.clone_origins[database]=='created':self.reference_installation=(witness,'e'*64,'e'*32)
            self.reference_witness=(witness,'a'*64, 'f'*32 if self.fault=='token' else token)
        return value

    def observe_record_state(self,identifier,designer):
        value=super().observe_record_state(identifier,designer)
        if self.fault in ('origin','postimage') and identifier=='created':
            self.record_pending[2][self.fault]['sha256']='0'*64
        return value


def run_fixture(test,**kwargs):
    temp=tempfile.TemporaryDirectory();test.addCleanup(temp.cleanup)
    provenance=old.identity();provenance['sources']={key:'c'*64 for key in inputs.CATALOG_REFERENCE_SOURCE_FILES}
    case=kwargs.get('case','distinct_a')
    report=policy.empty_report(old.old.NONCE,provenance,reference_case=case)
    backend=ByteBackend(Path(temp.name).resolve(),provenance,**kwargs)
    controller=old.old.fixture.stage.Controller(backend,report);backend.controller=controller
    return controller.run(),backend


@unittest.skipUnless(old.old.POSIX,'requires descriptor-relative POSIX operations')
class ReferenceLifecycleTests(unittest.TestCase):
    def setUp(self):old.old.normalize_owners(self)

    def test_two_cases_six_selector_only_reads_and_cleanup(self):
        for case in policy.CASES:
            calls=[];original=old.coordinator.read_catalog_binding
            def read(read_at,size,**kwargs):
                calls.append(set(kwargs));return original(read_at,size,**kwargs)
            with mock.patch.object(old.coordinator,'read_catalog_binding',read):report,backend=run_fixture(self,case=case)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(calls,[{'catalog_name','limits'}]*6)
            report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
            policy.validate_report(protocol.encode(report),nonce=old.old.NONCE,provenance=report['provenance'],final=True)
            self.assertEqual(report['record_readback']['states'][1]['reference']['permutation'],list(range(16)))
            self.assertFalse(report['record_readback']['states'][1]['reference']['hypothesis_match'])
            self.assertIsNone(backend.record_pending);self.assertFalse(list(backend.artifacts.iterdir()))

    def test_state_token_images_and_cross_state_mapping_fail_closed(self):
        for fault in ('token','origin','postimage','permutation','module'):
            with self.subTest(fault=fault):
                report,backend=run_fixture(self,fault=fault)
                self.assertEqual(report['status'],'failed',report)
                self.assertTrue(report['cleanup']['native_processes_stopped'])
                self.assertTrue(report['cleanup']['raw_files_removed'])
                self.assertFalse(list(backend.artifacts.iterdir()))

if __name__=='__main__':unittest.main()
