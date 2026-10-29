"""Independent full-envelope majorant; not evidence of native writer behavior."""
import unittest
from unittest import mock

import test_native_1c_db_oracle_catalog_readonly_budget as previous
import catalog_reference_identity as policy
import inputs
import protocol

wire = previous.wire
longest = previous.metadata_budget.longest


def capture_envelope():
    capture = previous.capture_envelope()
    capture.update(schema=policy.CAPTURE_SCHEMA, profile_id=policy.PROFILE_ID,
                   rendered_module_sha256="f" * 64,
                   installation={"status":"succeeded","token":"e"*32,"witness_sha256":"e"*64})
    for state in capture["states"]:
        present = state["snapshot"] != "baseline"
        state["reference"] = {
            "witness_sha256": "f" * 64,
            "before": "E" * 12 if present else "E" * 9 + "NNN",
            "after": "E" * 12 if present else "E" * 9 + "NNN",
            "before_present": present, "after_present": present,
            "permutation": list(range(16)) if present else None,
            "hypothesis_match": False if present else None,
        }
    return capture


def failure_bound():
    return len(wire({"schema": policy.CAPTURE_SCHEMA, "status": "failed",
                     "category": longest(policy.DIAGNOSTICS),
                     "code": longest(code for codes in policy.DIAGNOSTICS.values() for code in codes)}))


def report_envelope():
    report = previous.report_envelope()
    report.update(schema=policy.SCHEMA, lane=policy.LANE,
                  reference_case=longest(policy.CASES))
    report["failure_kind"] = longest((*protocol.FAILURES, policy.FAILURE_KIND,
                                      policy.metadata.FAILURE_KIND))
    report["provenance"]["sources"] = {name: "c" * 64 for name in inputs.CATALOG_REFERENCE_SOURCE_FILES}
    for name, verdict in (("mapping_validation", policy.MAPPING_VERDICT),
                          ("layout_validation", policy.LAYOUT_VERDICT),
                          ("record_validation", policy.VERDICT)):
        report[name] = longest(("not_run", "failed", "discarded", verdict))
    return report


def aggregate_envelope():
    return {'schema':41,'lane':policy.LANE,'status':'measured',
        'commit':'f'*40,'tree':'f'*40,'source_manifest_sha256':'f'*64,
        'profile_sha256':'f'*64,'actual_version':protocol.VERSION,
        'cases':[{'case':case,'report_sha256':'f'*64,'permutation':list(range(16)),
                  'hypothesis_match':False} for case in policy.CASES],
        'permutations_agree':False,'codec_approved':False,'native_compatibility':'not_claimed'}


def proof_results():
    return {
        "sources": len(inputs.CATALOG_REFERENCE_SOURCE_FILES),
        "success_capture": len(wire(capture_envelope())),
        "failure_capture": failure_bound(),
        "capture_cap": policy.MAX_CAPTURE_BYTES,
        # record_readback=null is replaced with its *full admitted* byte cap.
        "report_with_full_capture_cap_and_newline": len(wire(report_envelope())) - 4 + policy.MAX_CAPTURE_BYTES + 1,
        "report_cap": protocol.MAX_REPORT_BYTES,
        "private_marker": previous.previous.private_marker_bound(),
    }


class CatalogReferenceIdentityBudgetTests(unittest.TestCase):
    def test_aggregate_has_independent_small_bound_not_nested_reports(self):
        import test_native_catalog_reference_identity as fixture
        a=fixture.fixture();b=fixture.fixture('distinct_b',nonce='b'*32)
        actual=policy.aggregate_reports(protocol.encode(a),protocol.encode(b),provenance=a['provenance'])
        envelope=aggregate_envelope()
        self.assertEqual(set(actual),set(envelope))
        self.assertLessEqual(len(wire(actual)),len(wire(envelope)))
        self.assertLessEqual(len(wire(envelope)),2048)
        self.assertNotIn('record_readback',actual)
        self.assertEqual([set(x) for x in actual['cases']],[set(x) for x in envelope['cases']])

    def test_complete_cap_majorants(self):
        facts = proof_results()
        self.assertEqual((policy.SCHEMA, policy.CAPTURE_SCHEMA), (39, 40))
        self.assertEqual(facts, {"sources": 40, "success_capture": 3469,
            "failure_capture": 118, "capture_cap": 12288,
            "report_with_full_capture_cap_and_newline": 32551,
            "report_cap": 32768, "private_marker": 8931})
        self.assertEqual((facts["capture_cap"], facts["report_cap"]), (12288, 32768))
        self.assertLessEqual(facts["success_capture"], facts["capture_cap"])
        self.assertLessEqual(facts["failure_capture"], facts["capture_cap"])
        self.assertLessEqual(facts["report_with_full_capture_cap_and_newline"], facts["report_cap"])
        self.assertLessEqual(facts["private_marker"], facts["report_cap"])
        self.assertIsNone(report_envelope()["record_readback"])

    def test_all_lifecycle_collections_and_reference_fields_charged(self):
        report = report_envelope()
        self.assertEqual([len(report[key]) for key in ("stages", "snapshots", "comparisons", "artifacts", "cleanup")],
                         [13, 11, 5, 3, 4])
        self.assertEqual(set(report["failure_context"]), set(previous.context_domains()))
        self.assertEqual(set(report["provenance"]["sources"]), set(inputs.CATALOG_REFERENCE_SOURCE_FILES))
        capture = capture_envelope()
        self.assertEqual(set(capture["audit"]), policy.metadata.BINDING_KEYS)
        self.assertEqual([state["snapshot"] for state in capture["states"]], list(policy.TARGETS))
        self.assertEqual(len(capture["rendered_module_sha256"]), 64)
        for state in capture["states"]:
            policy._validate_reference(state["reference"], state["snapshot"])
        # A bijection always has the same wire length; false dominates true.
        self.assertGreater(len(wire(False)), len(wire(True)))
        self.assertEqual(len(wire(list(range(16)))), len(wire(policy.TOOL1CD)))

    def test_future_inventory_and_diagnostic_growth_is_charged(self):
        before = len(wire(report_envelope()))
        source = "new/source.py"
        with mock.patch.object(inputs, "CATALOG_REFERENCE_SOURCE_FILES",
                               {**inputs.CATALOG_REFERENCE_SOURCE_FILES, source: source}):
            self.assertEqual(len(wire(report_envelope())) - before,
                             len(wire({source: "c" * 64})) - 1)
        with mock.patch.object(protocol, "CONTEXT_SITES", set(protocol.CONTEXT_SITES) | {"x" * 200}):
            self.assertEqual(len(wire(report_envelope())) - before, 191)
