"""Complete CONFIG framing observation report envelope, including all sources, gates and newline."""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'tests')]
import inputs
import config_framing as policy
import protocol
import snapshots
import test_native_1c_db_oracle_record_budget as old
import test_native_1c_db_oracle_readback_budget as previous
import test_native_1c_db_oracle_config_framing_policy as fixtures

wire=old.wire


def projection_envelope():
    value=fixtures.projection()
    # Maximal decimal widths under the complete consistent count equations.
    value.update(data_logical_bytes=4096*301,blob_logical_bytes=snapshots.MAX_FILE_BYTES,
        slots=4096,active_slots=4095,empty_filenames=2047,nonempty_filenames=2048,
        max_filename_units=128)
    policy.validate_projection(value)
    return value


def capture_skeleton():
    report,_=fixtures.fixture()
    value=copy.deepcopy(report['config_framing']);value['reader']=None
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
    return {'source_count':len(inputs.CONFIG_FRAMING_SOURCE_FILES),'projection_envelope':len(wire(projection_envelope())),
        'capture_skeleton':skeleton,'capture_with_full_projection_cap':skeleton-4+policy.MAX_PROJECTION_BYTES,
        'failure_capture':failure_bound(),'capture_cap':policy.MAX_CAPTURE_BYTES,
        'report_without_capture':report,'report_with_full_capture_cap_and_newline':report-4+policy.MAX_CAPTURE_BYTES+1,
        'report_cap':protocol.MAX_REPORT_BYTES,'margin':protocol.MAX_REPORT_BYTES-(report-4+policy.MAX_CAPTURE_BYTES+1),
        'private_marker_conditional_bound':previous.private_marker_bound()}


class ConfigFramingBudgetTests(unittest.TestCase):
    def test_complete_bound_not_partial_payload_budget(self):
        result=proof_results(); value=report_envelope()
        self.assertEqual((len(value['stages']),len(value['snapshots']),len(value['comparisons']),len(value['artifacts'])),(13,11,5,3))
        self.assertEqual(len(value['cleanup']),4); self.assertTrue(all(v is False for v in value['cleanup'].values()))
        self.assertEqual(set(value)-set(protocol.empty_report(fixtures.NONCE,fixtures.identity())),
                         policy.EXTRA_KEYS|{'rejected_basename','failure_context'})
        self.assertLessEqual(result['projection_envelope'],policy.MAX_PROJECTION_BYTES)
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

    def test_pinned_complete_envelopes(self):
        self.assertEqual(proof_results(), EXPECTED)


EXPECTED = {'source_count': 23, 'projection_envelope': 455, 'capture_skeleton': 941,
    'capture_with_full_projection_cap': 2985, 'failure_capture': 114, 'capture_cap': 12288,
    'report_without_capture': 19049, 'report_with_full_capture_cap_and_newline': 31334,
    'report_cap': 32768, 'margin': 1434, 'private_marker_conditional_bound': 8931}

if __name__=='__main__': unittest.main()
