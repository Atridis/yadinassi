"""Whole failure-only report envelope with exact23 closure, all gates and newline."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'tests')]
import config_root_diagnostic as policy
import inputs
import protocol
import snapshots
import test_native_1c_db_oracle_record_budget as old
import test_native_1c_db_oracle_readback_budget as previous
import test_native_1c_db_oracle_config_root_diagnostic_policy as fixtures
wire=old.wire


def report_envelope():
    # Every independent lifecycle maximum is retained, even though a baseline
    # failure cannot have completed all snapshots/comparisons/artifacts. This is
    # a conservative rectangle, not a fabricated valid successful report.
    value=previous.report_envelope()
    for key in set(value)-set(protocol.empty_report(fixtures.NONCE,fixtures.identity()))-{'rejected_basename','failure_context'}:
        del value[key]
    current=policy.empty_report(fixtures.NONCE,fixtures.identity())
    for key in policy.EXTRA_KEYS:value[key]=current[key]
    value.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=fixtures.identity())
    value['provenance']['actual_version']=protocol.VERSION
    # Failure-only states; no old success/positive-transport verdict is needed.
    for key in ('reader_validation','observation_validation','decompression_validation'):
        value[key]=old.longest(('not_run','failed'))
    return value


def failure_bound():
    return len(wire({'schema':policy.CAPTURE_SCHEMA,'status':'failed',
        'category':old.longest(policy.DIAGNOSTICS),
        'code':old.longest(code for codes in policy.DIAGNOSTICS.values() for code in codes)}))


def proof_results():
    rectangle=len(wire(report_envelope()))
    pairs=[{'schema':policy.CAPTURE_SCHEMA,'status':'failed','category':category,'code':code}
        for category,codes in policy.DIAGNOSTICS.items() for code in codes]
    return {'source_count':len(inputs.CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES),
        'failure_capture_valid_pair_max':max(len(wire(p)) for p in pairs),
        'failure_capture_rectangle':failure_bound(),
        'failure_capture_rectangle_with_newline':failure_bound()+1,
        'capture_cap':policy.MAX_CAPTURE_BYTES,'projection_cap_unchanged_no_projection':policy.MAX_PROJECTION_BYTES,
        'report_without_capture':rectangle,
        'report_with_full_capture_cap_and_newline':rectangle-4+policy.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES,'margin':protocol.MAX_REPORT_BYTES-(rectangle-4+policy.MAX_CAPTURE_BYTES+1),
        'private_marker_conditional_bound':previous.private_marker_bound(),
        'maximum_diagnostic_category_length':max(map(len,policy.DIAGNOSTICS)),
        'maximum_diagnostic_code_length':max(len(code) for codes in policy.DIAGNOSTICS.values() for code in codes),
        'diagnostic_pair_count':len(pairs),
        'diagnostic_vocabulary_sha256':hashlib.sha256(wire({k:sorted(v) for k,v in sorted(policy.DIAGNOSTICS.items())})).hexdigest()}


class ConfigRootDiagnosticBudgetTests(unittest.TestCase):
    def test_complete_report_not_partial_failure_payload_budget(self):
        result=proof_results();value=report_envelope()
        self.assertEqual((len(value['stages']),len(value['snapshots']),len(value['comparisons']),len(value['artifacts'])),(13,11,5,3))
        self.assertEqual(len(value['cleanup']),4);self.assertTrue(all(v is False for v in value['cleanup'].values()))
        self.assertEqual(set(value)-set(protocol.empty_report(fixtures.NONCE,fixtures.identity())),policy.EXTRA_KEYS|{'rejected_basename','failure_context'})
        self.assertLessEqual(result['report_with_full_capture_cap_and_newline'],protocol.MAX_REPORT_BYTES)
        self.assertLessEqual(result['private_marker_conditional_bound'],protocol.MAX_REPORT_BYTES)
        self.assertEqual((policy.SCHEMA,policy.CAPTURE_SCHEMA,policy.MAX_PROJECTION_BYTES,policy.MAX_CAPTURE_BYTES,protocol.MAX_REPORT_BYTES),(21,22,2048,12288,32768))
        self.assertLessEqual(result['failure_capture_rectangle'],policy.MAX_CAPTURE_BYTES)
        self.assertEqual((result['failure_capture_valid_pair_max'],result['failure_capture_rectangle'],result['diagnostic_pair_count']),(110,118,137))

    def test_every_finite_pair_final_report_fits_and_never_accepts(self):
        template=fixtures.final_report();bound=proof_results()
        for category,codes in policy.DIAGNOSTICS.items():
            for code in codes:
                value=copy.deepcopy(template);value['config_root_diagnostic'].update(category=category,code=code)
                policy.validate_report(wire(value),nonce=fixtures.NONCE,provenance=value['provenance'],final=True)
                self.assertFalse(value['accepted']);self.assertEqual(value['status'],'failed')
                self.assertLessEqual(len(wire(value['config_root_diagnostic'])),bound['failure_capture_valid_pair_max'])
                self.assertLessEqual(len(wire(value))+1,bound['report_with_full_capture_cap_and_newline'])
        self.assertEqual(len(wire(report_envelope()))-4+12288+1,bound['report_with_full_capture_cap_and_newline'])

    def test_all_sources_lifecycle_context_and_artifact_fields_are_retained(self):
        value=report_envelope()
        self.assertEqual(set(value['provenance']['sources']),set(inputs.CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES))
        self.assertEqual(len(value['provenance']['sources']),23)
        self.assertTrue(all(len(v)==64 for v in value['provenance']['sources'].values()))
        self.assertEqual(value['provenance']['actual_version'],protocol.VERSION);self.assertEqual(value['provenance']['image'],protocol.IMAGE)
        for key,expected in (('stages',protocol.STAGES),('snapshots',protocol.SNAPSHOTS),('comparisons',protocol.COMPARISONS),('artifacts',protocol.ARTIFACTS)):
            self.assertEqual([v['id'] for v in value[key]],list(expected))
        for stage in value['stages']:
            self.assertEqual(set(stage['checks']),set(protocol.CHECKS[stage['id']]))
            self.assertTrue(all(v is False for v in stage['checks'].values()))
        for snapshot in value['snapshots']:
            self.assertIs(snapshot['quiescent'],False);self.assertIs(snapshot['copy_verified'],False)
        for comparison in value['comparisons']:
            for key,sample in comparison['physical']['byte_windows'].items():
                if key.endswith('_sample'):self.assertEqual(sample,[snapshots.MAX_FILE_BYTES]*snapshots.MAX_SAMPLES)
        self.assertEqual(set(value['failure_context']),{'operation','site','bsl_phase','region','reason','entry_class','entry_shape'})
        self.assertTrue(all(v=='X'*128 for v in value['failure_context'].values()))
        self.assertEqual((len(value['rejected_basename']),value['config_root_diagnostic']),(52,None))
        domains=set(protocol.STAGES)|set(protocol.FAILURES)|set(protocol.COMMAND_STAGES)|set(policy.metadata.PHASES)|{policy.FAILURE_KIND,'enterprise_'+policy.OPERATION}
        for domain in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,protocol.INVENTORY_REGIONS,protocol.INVENTORY_REASONS,snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES):domains.update(domain)
        self.assertTrue(all(type(v) is str and v.isascii() and len(v)<=128 for v in domains))

    def test_old_vocabulary_difference_is_exactly_three_removals_four_additions(self):
        import config_root_reference as old_policy
        pairs=lambda p:{(c,x) for c,codes in p.DIAGNOSTICS.items() for x in codes}
        before,after=pairs(old_policy),pairs(policy)
        self.assertEqual(before-after,{('structural_rejection','config_root_grammar'),('unsupported_layout','config_root_missing_selected_target'),('unsupported_layout','config_root_empty_target')})
        self.assertEqual(after-before,{('structural_rejection',v) for v in fixtures.GATES}|{('diagnostic_stop',fixtures.COMPLETE)})

    def test_pinned_whole_envelope(self):
        self.assertEqual(proof_results(),EXPECTED)


EXPECTED = {'source_count': 23, 'failure_capture_valid_pair_max': 110, 'failure_capture_rectangle': 118, 'failure_capture_rectangle_with_newline': 119, 'capture_cap': 12288, 'projection_cap_unchanged_no_projection': 2048, 'report_without_capture': 19102, 'report_with_full_capture_cap_and_newline': 31387, 'report_cap': 32768, 'margin': 1381, 'private_marker_conditional_bound': 8931, 'maximum_diagnostic_category_length': 26, 'maximum_diagnostic_code_length': 37, 'diagnostic_pair_count': 137, 'diagnostic_vocabulary_sha256': 'bcf5aad43e0898a09c10f43c0b67bdfd69c6df65d9689203eed6c8dfe469dedf'}
if __name__=='__main__':unittest.main()
