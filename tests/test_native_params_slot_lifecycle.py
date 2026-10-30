"""Constructed bytes through existing session/freeze/cleanup, not native evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import test_native_catalog_description_rows_lifecycle as old
import test_native_params_slot_policy as facts
import test_native_params_slot_observer as bytes_fixture
import params_slot_policy as policy
import params_slot_observer as reader
import catalog_description_physical
import protocol

class ByteBackend(old.ByteBackend):
    compare_params_slot_state = old.old.old.old.fixture.stage.Native.compare_params_slot_state
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.params_slots=True;self.description_policy=policy
    def observe(self,identifier,designer):
        if identifier in policy.TARGETS:return self.observe_record_state(identifier,designer)
        return old.old.old.old.fixture.FixtureNative.observe(self,identifier,designer)
    def freeze(self,database,identifier):
        old.old.old.old.fixture.FixtureNative.freeze(self,database,identifier)
        rows=[bytes_fixture.f.named_row()]
        if identifier=='applied':rows += [bytes_fixture.link(1)]
        value=bytes_fixture.source(rows,head=2 if identifier=='applied' else 0)
        writer=self.artifacts/'synthetic_producer';writer.mkdir();(writer/'1Cv8.1CD').write_bytes(value.full_bytes())
        return old.old.old.old.fixture.stage.Native.freeze(self,writer,identifier)
    def observe_record_state(self,identifier,designer):
        result=super().observe_record_state(identifier,designer)
        if self.fault in ('origin','postimage') and identifier=='updated':self.record_pending[2][self.fault]['sha256']='0'*64
        return result

@unittest.skipUnless(old.old.old.old.POSIX,'requires POSIX frozen descriptor boundary')
class ParamsLifecycleTests(unittest.TestCase):
    def setUp(self):old.old.old.old.normalize_owners(self)
    def run_case(self,case='description8',fault=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        provenance=facts.provenance();report=policy.empty_report(facts.NONCE,provenance,description_case=case)
        backend=ByteBackend(Path(tmp.name).resolve(),provenance,case,fault)
        controller=old.old.old.old.fixture.stage.Controller(backend,report);backend.controller=controller
        return controller.run(),backend
    def test_two_independent_graphs_after_same_session_postimages(self):
        for case in policy.CASES:
            with mock.patch.object(reader,'observe',wraps=reader.observe) as read, \
                 mock.patch.object(catalog_description_physical,'read_description_rows',side_effect=AssertionError('no public parity reader')):
                report,backend=self.run_case(case)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(read.call_count,2)
            states=report['params_slot_measurement']['states']
            self.assertEqual([s['snapshot'] for s in states],['updated','applied'])
            self.assertEqual([s['observation']['later_one_count'] for s in states],[0,1])
            self.assertEqual(states[1]['observation']['linked_nonzero_count'],1)
            self.assertEqual(len({s['observe_token'] for s in states}),2)
            self.assertIn(('redump','applied',2),backend.events)
            report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
            policy.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=report['provenance'],final=True)
            self.assertIsNone(backend.record_pending);self.assertFalse(list(backend.artifacts.iterdir()))
    def test_token_origin_postimage_fail_closed(self):
        for fault in ('token','origin','postimage','applied_postimage'):
            with self.subTest(fault=fault):
                report,backend=self.run_case(fault=fault)
                self.assertEqual(report['status'],'failed',report)
                self.assertIsNone(report['params_slot_measurement'])
                self.assertTrue(report['cleanup']['native_processes_stopped'])
                self.assertTrue(report['cleanup']['raw_files_removed'])
                self.assertFalse(list(backend.artifacts.iterdir()))
    def test_reader_failure_and_cleanup_failure_scrub(self):
        for fault in ('reader','cleanup'):
            original=reader.observe
            def observed(read_at,size,**kwargs):
                if fault=='reader':raise ValueError('private error must never appear')
                result=original(read_at,size,**kwargs)
                return result
            patch=mock.patch.object(ByteBackend,'cleanup',return_value=(False,False)) if fault=='cleanup' else mock.patch.object(reader,'observe',observed)
            with patch:report,_=self.run_case()
            self.assertEqual(report['status'],'failed');self.assertIsNone(report['params_slot_measurement'])
            self.assertNotIn('private error',protocol.encode(report).decode())
            if fault=='cleanup':self.assertEqual(report['failed_stage'],'cleanup')

    def test_private_description_uuid_not_selectors_or_parity(self):
        for fault in ('uuid','native_differs'):
            report,_=self.run_case(fault=fault)
            self.assertEqual(report['status'],'ok',report)
            self.assertEqual(report['params_slot_measurement']['runtime_support'],'not_claimed')
