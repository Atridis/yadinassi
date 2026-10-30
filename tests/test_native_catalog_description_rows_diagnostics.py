"""Invented applied faults: finite diagnostics only after frozen evidence matches."""
import json
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock
import test_native_catalog_description_rows_lifecycle as lifecycle
import catalog_description_rows as policy
import catalog_description_physical as reader
import catalog_binding_reader as loader
import snapshots
import protocol
c=loader.catalog_module

@unittest.skipUnless(lifecycle.old.old.old.POSIX,'POSIX frozen descriptor boundary')
class DescriptionDiagnosticsTests(lifecycle.RowsLifecycleTests):
    def apply_fault(self,error,*,boundary=None,reader_value=None,cleanup=False):
        count=[0];read=reader.read_description_rows;inspect=snapshots.inspect_frozen_catalog
        def fail_read(*a,**kw):
            count[0]+=1
            if count[0]==3:
                if reader_value is not None:return reader_value
                raise error
            return read(*a,**kw)
        def guarded(path,**kw):
            if count[0]!=2:return inspect(path,**kw)
            if boundary=='mutate':
                callback=kw['read_catalog']
                def mutate(*a,**opts):
                    result=callback(*a,**opts)
                    target=path/'1Cv8.1CD';target.chmod(0o600)
                    raw=bytearray(target.read_bytes());raw[16]^=1;target.write_bytes(raw);target.chmod(0o400)
                    return result
                kw['read_catalog']=mutate
            measured,result=inspect(path,**kw)
            if boundary=='digest':measured={**measured,'sha256':'0'*64}
            if boundary=='substitute':result=object()
            if boundary=='different':raise c.UnsupportedLayout('recordlock_mismatch')
            if boundary=='cleanup':raise snapshots.OracleError('snapshot_changed')
            return measured,result
        with mock.patch.object(reader,'read_description_rows',fail_read),mock.patch.object(snapshots,'inspect_frozen_catalog',guarded),\
             mock.patch.object(policy,'wrap_failure',wraps=policy.wrap_failure) as wrap:
            report,backend=self.run_case()
        self.assertEqual(report['status'],'failed',report)
        self.assertEqual(report['failed_stage'],'apply_cf')
        self.assertEqual(report['snapshots'][-1]['id'],'applied')
        self.assertEqual([x['id'] for x in report['comparisons']],['create','update','load_cf'])
        self.assertIsNone(report['description_measurement'])
        self.assertFalse(list(backend.artifacts.iterdir()))
        self.assertEqual(count[0],3)
        self.assertEqual(wrap.call_count,1)
        return report,wrap.call_args.args[0]

    def test_distinct_reader_causes_now_finite_same_object_after_integrity(self):
        for error,category,code in (
            (c.UnsupportedLayout('declaration_mismatch'),'unsupported_layout','declaration_mismatch'),
            (c.UnsupportedLayout('nonreserved_free_slot'),'unsupported_layout','nonreserved_free_slot'),
            (c.ResourceLimit('record_slots'),'resource_limit','record_slots'),
            (ValueError('PRIVATE EXCEPTION VALUE'),'unclassified','unknown_exception')):
            with self.subTest(code=code):
                report,observed=self.apply_fault(error)
                self.assertIs(observed,error)
                self.assertEqual(report['failure_kind'],'unexpected_failure')
                self.assertEqual(report['description_failure'],dict(snapshot='applied',phase='public_reader',category=category,code=code))
                self.assertNotIn(b'PRIVATE',protocol.encode(report))
                report['cleanup'].update(container_removed=True,private_staging_removed=True)
                policy.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=report['provenance'],final=True)

    def test_superseding_integrity_and_forged_results_never_claim_reader_reason(self):
        for boundary in ('mutate','digest','substitute','different','cleanup'):
            with self.subTest(boundary=boundary):
                error=c.UnsupportedLayout('declaration_mismatch')
                report,observed=self.apply_fault(error,boundary=boundary)
                self.assertIsNot(observed,error)
                diagnostic=report.get('description_failure')
                if diagnostic:
                    self.assertNotEqual(diagnostic['phase'],'public_reader')
                    self.assertNotEqual(diagnostic['code'],'declaration_mismatch')
                    self.assertNotEqual(diagnostic['code'],'recordlock_mismatch')
        report,_=self.apply_fault(None,reader_value=object())
        self.assertEqual(report['description_failure']['category'],'unclassified')
        self.assertEqual(report['description_failure']['phase'],'postimage')

    def test_adapter_and_parity_separate_from_physical_admission(self):
        for code in ('metadata_profile','one_active_row'):
            report,_=self.apply_fault(policy.DescriptionAdapterError(code))
            self.assertEqual(report['description_failure'],dict(snapshot='applied',phase='adapter',category='adapter',code=code))
        for fault,code in (('uuid','typed_uuid'),('native_differs','description'),('applied_width','metadata')):
            report,_=self.run_case(fault=fault)
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['description_failure']['phase'],'comparison')
            self.assertEqual(report['description_failure']['category'],'parity')
            self.assertEqual(report['description_failure']['code'],code)
            self.assertIsNone(report['description_measurement'])

    def test_success_has_no_failure_diagnostic(self):
        report,_=self.run_case()
        self.assertEqual(report['status'],'ok')
        self.assertNotIn('description_failure',report)

    def test_real_budget_failure_poisoned_graph_and_no_extra_public_read(self):
        count=[0];graphs=[];original=reader.read_description_rows
        initializer=c._CatalogBindingGraph.__init__
        def init(graph,*a,**kw):initializer(graph,*a,**kw);graphs.append(graph)
        def bounded(*a,**kw):
            count[0]+=1
            if count[0]==3:kw['limits']=replace(kw['limits'],max_output_bytes=3000000)
            return original(*a,**kw)
        with mock.patch.object(c._CatalogBindingGraph,'__init__',init),mock.patch.object(reader,'read_description_rows',bounded):
            report,_=self.run_case()
        self.assertEqual(count[0],3);self.assertEqual(len(graphs),3)
        self.assertTrue(graphs[-1].failed)
        self.assertEqual(report['failed_stage'],'apply_cf')
        self.assertEqual(report['description_failure']['category'],'resource_limit')
        self.assertEqual(report['description_failure']['phase'],'public_reader')
        self.assertIsNone(report['description_measurement'])

    def test_failed_native_cleanup_discards_even_known_diagnostic(self):
        original=lifecycle.ByteBackend.cleanup
        def unsafe(backend):
            original(backend)
            return False,True
        with mock.patch.object(lifecycle.ByteBackend,'cleanup',unsafe):
            report,_=self.run_case(fault='uuid')
        self.assertEqual(report['status'],'failed')
        self.assertIsNone(report['description_measurement'])
        self.assertNotIn('description_failure',report)
