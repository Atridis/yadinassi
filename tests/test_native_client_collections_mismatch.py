"""Offline finite mismatch metadata tests; these are not native output evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_native_client_collections_host as fixtures

full = fixtures.full
suite = fixtures.suite


class CollectionsMismatchHostTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ClientCollectionsHostTests()
        self.fixture.setUp()
        self.record = self.fixture.collections
        self.server = self.fixture.server
        self.record.update(status="failed", failure_kind="output_mismatch", witness_verified=False,
                           **dict.fromkeys(fixtures.OUTPUT_KEYS))
        self.record["mismatch"] = self.metadata()

    @staticmethod
    def metadata():
        return {"count": 2, "first": 3, "ordinals": [3, 7],
                "client_sha256": "1" * 64, "server_sha256": "2" * 64,
                "client_size": 11, "server_size": 12}

    def validate(self, record=None):
        return full.validate_client_collections(self.record if record is None else record,
            full.COLLECTIONS_SOURCE_SHA256, self.fixture.modules["client_collections"], self.server)

    def test_complete_mismatch_metadata_is_preserved_without_acceptance(self):
        before = copy.deepcopy(self.record)
        self.assertEqual(self.validate(), before)
        self.assertEqual(self.record, before)
        self.assertFalse(self.record["witness_verified"])
        for name in fixtures.OUTPUT_KEYS:
            self.assertIsNone(self.record[name])

    def test_optional_legacy_null_or_absent_metadata_remains_valid(self):
        for value in (None, "absent"):
            record = copy.deepcopy(self.record)
            if value is None:
                record["mismatch"] = None
            else:
                del record["mismatch"]
            self.assertEqual(self.validate(record), record)

    def test_metadata_rejects_unknown_missing_and_non_dict_shapes(self):
        bad = [[], True, 1, "PRIVATE"]
        metadata = self.metadata()
        bad.extend({key: value for key, value in metadata.items() if key != omitted}
                   for omitted in metadata)
        bad.append(dict(metadata, raw="PRIVATE"))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(dict(self.record, mismatch=value))

    def test_counts_ordinals_sizes_and_digests_reject_bad_types_and_bounds(self):
        edits = []
        for key in ("count", "first"):
            for value in (True, False, None, 0, -1, 903, 1.0, "1"):
                edits.append((key, value))
        for key in ("client_size", "server_size"):
            for value in (True, False, None, 0, -1, full.MAX_FILE + 1, 1.0, "1"):
                edits.append((key, value))
        for key in ("client_sha256", "server_sha256"):
            for value in (None, True, 1, "A" * 64, "a" * 63, "PRIVATE"):
                edits.append((key, value))
        for value in (None, True, (), "PRIVATE", [], [3], [3, 7, 9], [7, 3], [3, 3],
                      [3, 903], [0, 7], [True, 7], [3, 7.0], [3, "7"], [4, 7]):
            edits.append(("ordinals", value))
        for key, value in edits:
            metadata = dict(self.metadata(), **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(dict(self.record, mismatch=metadata))
        for edits in ({"client_sha256": "2" * 64}, {"count": 901},
                      {"count": 17, "ordinals": list(range(3, 18)) + [902]}):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                self.validate(dict(self.record, mismatch=dict(self.metadata(), **edits)))

    def test_exact_first_sixteen_ordinal_prefix_is_bounded(self):
        for count, first in ((1, 902), (16, 887), (17, 886), (902, 1)):
            metadata = dict(self.metadata(), count=count, first=first,
                            ordinals=list(range(first, first + min(count, 16))))
            self.validate(dict(self.record, mismatch=metadata))

    def test_metadata_requires_complete_identity_execution_and_failure_context(self):
        edits = [("status", "ok"), ("status", "not_started"), ("failure_kind", "timeout"),
                 ("failure_kind", "process_failed"), ("witness_verified", True)]
        edits += [(key, False) for key in ("entered", "completed", "process_exited", "quiet")]
        edits += [(key, None) for key in full.CLIENT_HASHES]
        edits += [(key, "a" * 64) for key in full.CLIENT_HASHES]
        edits += [(key, 1) for key in fixtures.OUTPUT_KEYS]
        for key, value in edits:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(dict(self.record, **{key: value}))
        for key, value in (("stage", "before_probe"), ("reason", "unverified")):
            record = copy.deepcopy(self.record)
            record["process_diagnostics"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate(record)
        for key, value in (("status", "failed"), ("message_count", 901),
                           ("message_count", True), ("source_sha256", "a" * 64)):
            server = dict(self.server, **{key: value})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                full.validate_client_collections(self.record, full.COLLECTIONS_SOURCE_SHA256,
                    self.fixture.modules["client_collections"], server)

    def test_metadata_cannot_be_smuggled_into_other_client_records(self):
        for validator in (full.validate_client_probe, full.validate_client_watchdog):
            record = dict(self.fixture.client, mismatch=self.metadata())
            if validator is full.validate_client_watchdog:
                record["timeout_verified"] = False
            with self.subTest(validator=validator), self.assertRaises(ValueError):
                validator(record, "c" * 64, "d" * 64)

    def test_diagnostic_envelope_requires_all_prior_cases_and_unreached_watchdog(self):
        stage = self.fixture.all_clients()
        self.fixture.failure()
        stage["failure_kind"] = "output_mismatch"
        successful_watchdog = copy.deepcopy(stage["client_watchdog"])
        stage["client_watchdog"] = dict(suite.empty_client_report(), timeout_verified=False)
        baseline = copy.deepcopy(self.fixture.envelope)
        for name in ("client_probe", "client_dates", "client_values", "client_watchdog"):
            envelope = copy.deepcopy(baseline)
            record = (successful_watchdog if name == "client_watchdog" else
                      suite.empty_client_report() if name == "client_probe" else self.fixture.unreached())
            envelope["report"]["stage3"][name] = record
            with self.subTest(name=name), self.assertRaises(full.FullError):
                self.fixture.validate_all(envelope)
        for index, name in enumerate(full.SCENARIOS):
            envelope = copy.deepcopy(baseline)
            case = envelope["report"]["stage3"]["cases"][index]
            case.update(status="failed", **dict.fromkeys(fixtures.OUTPUT_KEYS))
            envelope["report"]["stage3"]["failed_case"] = name
            with self.subTest(name=name), self.assertRaises(full.FullError):
                self.fixture.validate_all(envelope)

    def test_maximum_diagnostic_failure_roundtrips_within_unchanged_caps(self):
        stage = self.fixture.all_clients()
        self.fixture.failure()
        stage["failure_kind"] = "output_mismatch"
        stage["client_watchdog"] = dict(suite.empty_client_report(), timeout_verified=False)
        # Max-sized counters and bounded configuration evidence elsewhere remain
        # present, not dropped to make room for the finite diagnostic.
        for case in stage["cases"]:
            case.update(output_size=209715, message_count=32768)
        for name, count in (("dates", 185), ("values", 534), ("collections", 902)):
            case = stage["cases"][full.SCENARIOS.index(name)]
            case["message_count"] = count
            if name != "collections":
                stage["client_" + name].update(output_size=209715, message_count=count)
        self.server["output_size"] = full.MAX_FILE
        self.record["mismatch"] = dict(self.metadata(), count=698, first=100,
            ordinals=list(range(100, 116)), client_size=full.MAX_FILE, server_size=full.MAX_FILE)
        self.fixture.envelope["report"].update(python_version="99.99.999")
        self.fixture.envelope["report"]["configuration_format"].update(
            schema_version="99.999.999.999", element_count=4096,
            known_elements=sorted(fixtures.smoke.KNOWN_ELEMENTS))
        compact = suite.encode_stage_wire(stage)
        wire = fixtures.host_fixture.encode(compact)
        self.assertLessEqual(len(wire), 8192)
        self.assertEqual(full.decode_stage3_wire(compact), stage)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            suite.write_report(path, stage)
            self.assertLessEqual(path.stat().st_size, 8192)
            self.assertEqual(suite.decode_stage_wire(json.loads(path.read_bytes())), stage)
        self.fixture.envelope["report"]["stage3"] = compact
        report, outputs = self.fixture.validate_all()
        self.assertEqual(outputs, {})
        self.assertEqual(report["stage3"], stage)
        self.assertFalse(report["native_tests_completed"])
        self.assertLessEqual(len(fixtures.host_fixture.encode(report)), 32768)
        self.assertEqual((suite.MAX_STAGE_REPORT, full.MAX_STAGE_REPORT, full.MAX_REPORT), (8192, 8192, 32768))


if __name__ == "__main__":
    unittest.main()
