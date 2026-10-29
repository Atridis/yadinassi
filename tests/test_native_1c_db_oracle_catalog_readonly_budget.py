"""Independent complete finite37/38 envelopes, not a native writer guarantee."""
import unittest
from unittest import mock
import test_native_1c_db_oracle_readback_budget as previous
import test_native_1c_db_oracle_record_budget as metadata_budget
import catalog_readonly_binding as policy
import inputs
import protocol
import snapshots

wire=previous.wire


def capture_envelope():
    audit=metadata_budget.bound_capture_skeleton()
    audit={key:audit[key] for key in policy.metadata.BINDING_KEYS}
    return {'schema':policy.CAPTURE_SCHEMA,'status':'matched','profile_id':policy.PROFILE_ID,
        'profile_sha256':'f'*64,'record_reader_source_sha256':'f'*64,'audit':audit,
        'identity_manifest_sha256':'f'*64,'catalog_count':3,'attribute_count':2,
        'states':[{'snapshot':identifier,'origin_sha256':'f'*64,'observe_token':'d'*32,
            'observer_bytes':snapshots.MAX_FILE_BYTES,'observer_sha256':'f'*64,
            'origin_framing':metadata_budget.longest(policy.FRAMINGS),
            'observer_framing':metadata_budget.longest(policy.FRAMINGS),
            'verdict':policy.STATE_VERDICT,'binding_verdict':policy.MAPPING_VERDICT}
            for identifier in policy.TARGETS]}


def failure_bound():
    return len(wire({'schema':policy.CAPTURE_SCHEMA,'status':'failed',
        'category':metadata_budget.longest(policy.DIAGNOSTICS),
        'code':metadata_budget.longest(code for codes in policy.DIAGNOSTICS.values() for code in codes)}))


def finite_diagnostic_domain():
    domain=set(protocol.STAGES)|set(protocol.FAILURES)|{policy.FAILURE_KIND,policy.metadata.FAILURE_KIND}
    domain.update(protocol.COMMAND_STAGES);domain.add('enterprise_'+policy.OPERATION)
    for values in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,policy.metadata.PHASES,
                   protocol.INVENTORY_REGIONS,protocol.INVENTORY_REASONS,
                   snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES):domain.update(values)
    return domain


def context_domains():
    # validate_report delegates through metadata._mapped_failure_context to
    # protocol.validate_failure_context. Include raw metadata operation/phase
    # values before that validated mapping, plus null where it is admitted.
    return {
        'operation': set(protocol.COMMAND_STAGES) | {'enterprise_' + policy.metadata.OPERATION},
        'site': set(protocol.CONTEXT_SITES),
        'bsl_phase': set(protocol.BSL_PHASES) | set(policy.metadata.PHASES) | {None},
        'region': set(protocol.INVENTORY_REGIONS) | {None},
        'reason': set(protocol.INVENTORY_REASONS) | {None},
        'entry_class': set(snapshots.ENTRY_CLASSES),
        'entry_shape': set(snapshots.ENTRY_SHAPES),
    }


def report_envelope():
    report=previous.report_envelope()
    report.update(schema=policy.SCHEMA,lane=policy.LANE)
    # Every diagnostic uses an exhaustive production-validated finite domain.
    # Exact wire lengths include JSON quoting/escaping and nullable members.
    # Independent maxima may coexist even if cross-field rules reject that mix.
    # Future enum growth changes this proof, never the production size caps.
    report['failed_stage']=metadata_budget.longest((*protocol.STAGES,None))
    report['failure_kind']=metadata_budget.longest((*protocol.FAILURES,policy.FAILURE_KIND,policy.metadata.FAILURE_KIND))
    report['failure_context'] = {key:metadata_budget.longest(values)
                                 for key,values in context_domains().items()}
    report['provenance']['sources']={name:'c'*64 for name in inputs.CATALOG_BINDING_SOURCE_FILES}
    for name,verdict in (('mapping_validation',policy.MAPPING_VERDICT),
                         ('layout_validation',policy.LAYOUT_VERDICT),('record_validation',policy.VERDICT)):
        report[name]=metadata_budget.longest(('not_run','failed','discarded',verdict))
    return report


def proof_results():
    report=len(wire(report_envelope()))-4+policy.MAX_CAPTURE_BYTES+1
    return {'sources':len(inputs.CATALOG_BINDING_SOURCE_FILES),
        'success_capture':len(wire(capture_envelope())), 'failure_capture':failure_bound(),
        'capture_cap':policy.MAX_CAPTURE_BYTES,
        'report_with_full_capture_cap_and_newline':report,'report_cap':protocol.MAX_REPORT_BYTES,
        'private_marker':previous.private_marker_bound(),
        'finite_diagnostic_token_bytes':max(map(len,finite_diagnostic_domain()))}


class CatalogReadonlyBudgetTests(unittest.TestCase):
    def test_complete_cap_majorants(self):
        facts=proof_results()
        self.assertEqual((policy.SCHEMA,policy.CAPTURE_SCHEMA),(37,38))
        self.assertEqual(facts,{'sources':37,'success_capture':2443,'failure_capture':118,
            'capture_cap':12288,'report_with_full_capture_cap_and_newline':32137,
            'report_cap':32768,'private_marker':8931,'finite_diagnostic_token_bytes':64})
        self.assertLessEqual(facts['success_capture'],12288)
        self.assertLessEqual(facts['failure_capture'],12288)
        self.assertLessEqual(facts['report_with_full_capture_cap_and_newline'],32768)
        self.assertLessEqual(facts['private_marker'],32768)
        self.assertEqual((policy.MAX_CAPTURE_BYTES,protocol.MAX_REPORT_BYTES),(12288,32768))

    def test_all_finite_domains_and_all_lifecycle_collections_charged(self):
        report=report_envelope()
        self.assertEqual(len(report['stages']),13);self.assertEqual(len(report['snapshots']),11)
        self.assertEqual(len(report['comparisons']),5);self.assertEqual(len(report['artifacts']),3)
        self.assertEqual(len(report['cleanup']),4)
        for stage in report['stages']:self.assertTrue(all(x is False for x in stage['checks'].values()))
        domains=set(protocol.STAGES)|set(protocol.FAILURES)|{policy.FAILURE_KIND,policy.metadata.FAILURE_KIND}
        domains.update(protocol.COMMAND_STAGES);domains.add('enterprise_'+policy.OPERATION)
        for domain in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,policy.metadata.PHASES,
                       protocol.INVENTORY_REGIONS,protocol.INVENTORY_REASONS,
                       snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES):domains.update(domain)
        self.assertTrue(all(type(x) is str and x.isascii() and len(x)<=128 for x in domains))
        for comparison in report['comparisons']:
            for key,value in comparison['physical']['byte_windows'].items():
                if key.endswith('_sample'):self.assertEqual(len(value),snapshots.MAX_SAMPLES)

    def test_capture_count_fields_state_and_audit_coverage(self):
        capture=capture_envelope()
        self.assertEqual(set(capture['audit']),policy.metadata.BINDING_KEYS)
        self.assertEqual(len(capture['states']),3)
        self.assertEqual([s['snapshot'] for s in capture['states']],list(policy.TARGETS))
        for state in capture['states']:
            self.assertEqual(state['binding_verdict'],policy.MAPPING_VERDICT)
            self.assertEqual(state['verdict'],policy.STATE_VERDICT)
        self.assertEqual((capture['catalog_count'],capture['attribute_count']),(3,2))


class ClosedDiagnosticEnvelopeTests(unittest.TestCase):
    def test_all_context_domains_wire_lengths_and_future_growth(self):
        domains = context_domains()
        self.assertEqual({key:max(len(wire(value)) for value in values)
                          for key,values in domains.items()},
                         {'operation':34,'site':11,'bsl_phase':19,'region':12,
                          'reason':19,'entry_class':19,'entry_shape':25})
        self.assertEqual(set(report_envelope()['failure_context']),set(domains))
        for values in domains.values():
            self.assertTrue(all(value is None or (type(value) is str and value.isascii())
                                for value in values))
        before = len(wire(report_envelope()))
        with mock.patch.object(protocol, 'CONTEXT_SITES', set(protocol.CONTEXT_SITES)|{'x'*200}):
            self.assertEqual(len(wire(report_envelope()))-before,191)

    def test_context_validator_rejects_each_outside_domain_and_wrong_type(self):
        # Exercise the exact mapping/validator called by the binding report.
        operation = 'enterprise_' + policy.metadata.OPERATION
        base = {'operation':operation,'site':'result','bsl_phase':None,
                'region':None,'reason':None}
        entry = {'operation':'snapshot_freeze','site':'operation','bsl_phase':None,
                 'region':None,'reason':None,'entry_class':next(iter(snapshots.ENTRY_CLASSES)),
                 'entry_shape':next(iter(snapshots.ENTRY_SHAPES))}
        policy.metadata._mapped_failure_context(base,'baseline')
        policy.metadata._mapped_failure_context(entry,'baseline')
        for key in context_domains():
            for invalid in ('x'*128,0,True,[],{}):
                value = dict(entry if key.startswith('entry_') else base)
                value[key] = invalid
                with self.subTest(key=key,value=invalid):
                    with self.assertRaises(protocol.OracleError):
                        policy.metadata._mapped_failure_context(value,'baseline')
