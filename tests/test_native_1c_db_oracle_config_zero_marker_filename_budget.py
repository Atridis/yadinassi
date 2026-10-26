"""Complete zero-marker filename-field report bounds, including all sources, gates and newline."""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'tests')]
import inputs
import config_zero_marker_filename as policy
import protocol
import snapshots
import test_native_1c_db_oracle_record_budget as old
import test_native_1c_db_oracle_readback_budget as previous
import test_native_1c_db_oracle_config_zero_marker_filename_policy as fixtures

wire=old.wire


def projection_envelope():
    value=fixtures.projection()
    # Maximal decimal widths under the complete consistent count equations.
    value.update(data_logical_bytes=4096*301,blob_logical_bytes=snapshots.MAX_FILE_BYTES,
        candidate_slots=4096,first_marker_class='one',later_zero_count=2000,
        later_one_count=1000,later_other_count=1095,validated_zero_count=2000,
        empty_filenames=1000,nonempty_filenames=1000,max_filename_units=128)
    policy.validate_projection(value)
    return value


def capture_skeleton():
    report,_=fixtures.fixture()
    value=copy.deepcopy(report['config_zero_marker_filename']);value['reader']=None
    value['origin']['bytes']=value['postimage']['bytes']=snapshots.MAX_FILE_BYTES
    return value


def failure_bound():
    return len(wire({'schema':policy.CAPTURE_SCHEMA,'status':'failed',
        'category':old.longest(policy.DIAGNOSTICS),
        'code':old.longest(code for codes in policy.DIAGNOSTICS.values() for code in codes)}))


def report_envelope():
    value=previous.report_envelope()
    for key in set(value)-set(protocol.empty_report(fixtures.NONCE,fixtures.identity()))-{'rejected_basename','failure_context'}:
        del value[key]
    current=policy.empty_report(fixtures.NONCE,fixtures.identity())
    for key in policy.EXTRA_KEYS: value[key]=current[key]
    value.update(schema=policy.SCHEMA,lane=policy.LANE,provenance=fixtures.identity())
    value['provenance']['actual_version']=protocol.VERSION
    for key in ('reader_validation','observation_validation'):
        value[key]=old.longest(('not_run','failed','discarded',policy.VERDICT))
    return value


def proof_results():
    skeleton=len(wire(capture_skeleton()))
    report=len(wire(report_envelope()))
    return {'source_count':len(inputs.CONFIG_ZERO_MARKER_FILENAME_SOURCE_FILES),'projection_envelope':len(wire(projection_envelope())),
        'capture_skeleton':skeleton,
        'capture_with_projection_envelope':skeleton-4+len(wire(projection_envelope())),
        'capture_with_full_projection_cap':skeleton-4+policy.MAX_PROJECTION_BYTES,
        'failure_capture':failure_bound(),'capture_cap':policy.MAX_CAPTURE_BYTES,
        'report_without_capture':report,'report_with_full_capture_cap_and_newline':report-4+policy.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES,'margin':protocol.MAX_REPORT_BYTES-(report-4+policy.MAX_CAPTURE_BYTES+1),
        'private_marker_conditional_bound':previous.private_marker_bound()}


class ConfigZeroMarkerFilenameBudgetTests(unittest.TestCase):
    def test_complete_bound_not_partial_payload_budget(self):
        result=proof_results(); value=report_envelope()
        self.assertEqual((len(value['stages']),len(value['snapshots']),len(value['comparisons']),len(value['artifacts'])),(13,11,5,3))
        self.assertEqual(len(value['cleanup']),4); self.assertTrue(all(v is False for v in value['cleanup'].values()))
        self.assertEqual(set(value)-set(protocol.empty_report(fixtures.NONCE,fixtures.identity())),
                         policy.EXTRA_KEYS|{'rejected_basename','failure_context'})
        self.assertLessEqual(result['projection_envelope'],policy.MAX_PROJECTION_BYTES)
        self.assertLessEqual(result['capture_with_projection_envelope'],result['capture_with_full_projection_cap'])
        self.assertLessEqual(result['capture_with_full_projection_cap'],policy.MAX_CAPTURE_BYTES)
        self.assertLessEqual(result['report_with_full_capture_cap_and_newline'],protocol.MAX_REPORT_BYTES)
        self.assertLessEqual(result['private_marker_conditional_bound'],protocol.MAX_REPORT_BYTES)
        for category,codes in policy.DIAGNOSTICS.items():
            for code in codes:
                failure={'schema':policy.CAPTURE_SCHEMA,'status':'failed','category':category,'code':code}
                self.assertLessEqual(len(wire(failure)),result['failure_capture'])
        domains=set(protocol.STAGES)|set(protocol.FAILURES)|{policy.FAILURE_KIND,'enterprise_'+policy.OPERATION}
        for domain in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,protocol.INVENTORY_REGIONS,protocol.INVENTORY_REASONS,
                       snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES): domains.update(domain)
        self.assertTrue(all(type(v) is str and v.isascii() and len(v)<=128 for v in domains))

    def test_projection_counter_maxima_have_a_capacity_consistent_witness(self):
        value=projection_envelope()
        # The separate projection upper bound permits MAX_FILE for either length.
        # A same-width witness also satisfies the capture's combined-length gate.
        value['blob_logical_bytes']=snapshots.MAX_FILE_BYTES-value['data_logical_bytes']-10*8192
        policy.validate_projection(value)
        self.assertLessEqual(value['data_logical_bytes']+value['blob_logical_bytes'],snapshots.MAX_FILE_BYTES)
        self.assertEqual(len(wire(value)),len(wire(projection_envelope())))
        self.assertEqual(value['candidate_slots'],1+value['later_zero_count']+value['later_one_count']+value['later_other_count'])
        self.assertEqual(value['validated_zero_count'],value['empty_filenames']+value['nonempty_filenames'])
        self.assertEqual(value['validated_zero_count'],value['later_zero_count'])
        self.assertGreater(value['nonempty_filenames'],0)

    def test_pinned_complete_envelopes(self):
        self.assertEqual(proof_results(), EXPECTED)


EXPECTED = {'source_count':23, 'projection_envelope':593, 'capture_skeleton':954,
    'capture_with_projection_envelope':1543, 'capture_with_full_projection_cap':2998,
    'failure_capture':116, 'capture_cap':12288, 'report_without_capture':19138,
    'report_with_full_capture_cap_and_newline':31423, 'report_cap':32768, 'margin':1345,
    'private_marker_conditional_bound':8931}

if __name__=='__main__': unittest.main()
