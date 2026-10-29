"""Full source/lifecycle envelope bound, without raising existing byte caps."""
import unittest
import test_native_catalog_reference_identity_budget as previous
import test_native_catalog_reference_codec as fixture
import catalog_reference_codec as policy
import inputs
import protocol


def report_envelope():
    report = previous.report_envelope()
    report.update(schema=policy.SCHEMA,lane=policy.LANE,record_validation=policy.VERDICT)
    report['provenance']['sources'] = {key:'c'*64 for key in inputs.CATALOG_CODEC_SOURCE_FILES}
    return report


def capture_envelope():
    capture = previous.capture_envelope()
    capture.update(schema=policy.CAPTURE_SCHEMA,profile_id=policy.PROFILE_ID,
                   profile_sha256=policy.PROFILE_SHA256)
    for state in capture['states']:
        state['codec'] = 'NNNN' if state['snapshot'] == 'baseline' else 'TTTT'
    return capture


class CodecBudgetTests(unittest.TestCase):
    def test_full_capture_cap_and_all_42_sources_fit_original_report_cap(self):
        bound = len(previous.wire(report_envelope())) - 4 + policy.MAX_CAPTURE_BYTES + 1
        self.assertEqual(len(inputs.CATALOG_CODEC_SOURCE_FILES),42)
        self.assertEqual(bound,28667)
        self.assertLessEqual(bound,protocol.MAX_REPORT_BYTES)
        self.assertEqual(protocol.MAX_REPORT_BYTES,32768)
        self.assertEqual(policy.MAX_CAPTURE_BYTES,8192)
        self.assertEqual(len(previous.wire(capture_envelope())),3492)
        self.assertLessEqual(len(previous.wire(capture_envelope())),policy.MAX_CAPTURE_BYTES)
        self.assertEqual([len(report_envelope()[key]) for key in ('stages','snapshots','comparisons','artifacts','cleanup')], [13,11,5,3,4])

    def test_capture_keys_and_fixed_position_coverage_match_real_schema(self):
        actual = fixture.fixture()['record_readback']
        envelope = capture_envelope()
        self.assertEqual(set(actual),set(envelope))
        for a,b in zip(actual['states'],envelope['states']):
            self.assertEqual(set(a),set(b))
        self.assertLessEqual(len(previous.wire(actual)),len(previous.wire(envelope)))

    def test_aggregate_is_bounded_and_never_embeds_reports(self):
        a,b=fixture.fixture(),fixture.fixture('distinct_b','b'*32)
        result=policy.aggregate_reports(protocol.encode(a),protocol.encode(b),provenance=a['provenance'])
        self.assertLessEqual(len(previous.wire(result)),2048)
        self.assertEqual(len(result['cases']),2)
        self.assertNotIn('record_readback',result)
        self.assertEqual(set(result['cases'][0]),{'case','report_sha256'})

    def test_new_capture_overflow_rejected_without_changing_old_cap(self):
        report = fixture.fixture()
        report['record_readback']['overflow'] = 'x' * policy.MAX_CAPTURE_BYTES
        with self.assertRaises(Exception) as raised:
            fixture.validate(report)
        self.assertEqual(str(raised.exception), 'artifact_limit')
        self.assertEqual(previous.policy.MAX_CAPTURE_BYTES,12288)
