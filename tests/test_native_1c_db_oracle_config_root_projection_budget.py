"""Complete exact chain report bounds, including every source, gate and newline."""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'tests')]
import inputs
import config_root_reference_projection as policy
import protocol
import snapshots
import test_native_1c_db_oracle_record_budget as old
import test_native_1c_db_oracle_readback_budget as previous
import test_native_1c_db_oracle_config_root_projection_policy as fixtures

wire=old.wire


def projection_envelope():
    # Conservative rectangular envelope: each independently bounded integer has
    # its widest admitted decimal spelling. Simultaneous maxima need not satisfy
    # conservation; over-approximation makes this an unconditional finite bound.
    value=fixtures.projection()
    value.update(data_logical_bytes=4096*301,blob_logical_bytes=snapshots.MAX_FILE_BYTES,
        candidate_slots=4096,max_filename_units=128)
    for key in COUNTERS: value[key]=4095
    value.update(total_stored_bytes_read=4194304,total_chain_blocks=32768,maximum_chain_hops=8192,
        zero_payload_block_count=32768,plain_entry_count=4095,deflate_entry_count=4095,
        positive_decoded_entry_count=4095,plain_content_bytes=4194304,inflated_content_bytes=8388608,
        inflate_call_count=16384)
    return value


COUNTERS=('later_zero_count','later_one_count','later_other_count','validated_zero_count',
    'empty_filenames','nonempty_filenames','selected_reference_count','reference_excluded_count',
    'empty_name_excluded_count','selected_part_zero_count','selected_part_nonzero_count',
    'completed_chain_count','multi_block_chain_count')


def capture_skeleton():
    report,_=fixtures.fixture()
    value=copy.deepcopy(report['config_root_reference_projection']);value['reader']=None
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
    value['decompression_validation']=old.longest(('not_run','failed','discarded',policy.DECOMPRESSION_VERDICT))
    return value


def proof_results():
    skeleton=len(wire(capture_skeleton()))
    report=len(wire(report_envelope()))
    return {'source_count':len(inputs.CONFIG_ROOT_REFERENCE_PROJECTION_SOURCE_FILES),'projection_envelope':len(wire(projection_envelope())),
        'capture_skeleton':skeleton,
        'capture_with_projection_envelope':skeleton-4+len(wire(projection_envelope())),
        'capture_with_full_projection_cap':skeleton-4+policy.MAX_PROJECTION_BYTES,
        'failure_capture':failure_bound(),'capture_cap':policy.MAX_CAPTURE_BYTES,
        'report_without_capture':report,'report_with_full_capture_cap_and_newline':report-4+policy.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES,'margin':protocol.MAX_REPORT_BYTES-(report-4+policy.MAX_CAPTURE_BYTES+1),
        'private_marker_conditional_bound':previous.private_marker_bound()}


class ConfigRootProjectionBudgetTests(unittest.TestCase):
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
        domains=set(protocol.STAGES)|set(protocol.FAILURES)|set(protocol.COMMAND_STAGES)|set(policy.metadata.PHASES)|{policy.FAILURE_KIND,'enterprise_'+policy.OPERATION}
        for domain in (protocol.CONTEXT_SITES,protocol.BSL_PHASES,protocol.INVENTORY_REGIONS,protocol.INVENTORY_REASONS,
                       snapshots.ENTRY_CLASSES,snapshots.ENTRY_SHAPES): domains.update(domain)
        self.assertTrue(all(type(v) is str and v.isascii() and len(v)<=128 for v in domains))

    def test_rectangular_projection_bound_covers_real_witness(self):
        bound=projection_envelope(); value=fixtures.projection()
        policy.validate_projection(value)
        self.assertEqual(set(value), set(bound))
        for key in value:
            if type(value[key]) is int:
                self.assertLessEqual(len(str(value[key])), len(str(bound[key])))
            else: self.assertEqual(value[key], bound[key])
        self.assertLessEqual(len(wire(value)),len(wire(bound)))
        self.assertEqual({k for k,v in bound.items() if type(v) is int},
            set(COUNTERS)|{'schema','candidate_stride','candidate_slots','data_logical_bytes',
              'blob_logical_bytes','max_filename_units','total_stored_bytes_read','total_chain_blocks',
              'maximum_chain_hops','zero_payload_block_count','plain_entry_count','deflate_entry_count',
              'positive_decoded_entry_count','plain_content_bytes','inflated_content_bytes','inflate_call_count',
              'projected_root_count','resolved_target_count','positive_target_count'})

    def test_pinned_complete_envelopes(self):
        self.assertEqual(proof_results(), EXPECTED)


EXPECTED = {'source_count': 24, 'projection_envelope': 1709, 'capture_skeleton': 959, 'capture_with_projection_envelope': 2664, 'capture_with_full_projection_cap': 3003, 'failure_capture': 118, 'capture_cap': 12288, 'report_without_capture': 19346, 'report_with_full_capture_cap_and_newline': 31631, 'report_cap': 32768, 'margin': 1137, 'private_marker_conditional_bound': 8931}

if __name__=='__main__': unittest.main()
