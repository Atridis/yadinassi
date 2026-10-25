"""Offline synthetic host evidence, not a claim of execution on native 1C."""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest

import test_native_1c_full_host as host_fixture
from test_native_client_probe import process_diagnostics, suite
from test_native_1c_smoke import smoke

full = host_fixture.full
OUTPUT_KEYS = {"output_sha256", "output_size", "message_count"}


class ClientCollectionsHostTests(unittest.TestCase):
    def setUp(self):
        # Deliberately not historical collections output: acceptance must use fresh bytes.
        self.payload = b"fresh collections\n" * 865 + b"message with\nembedded newline\n"
        self.envelope, self.inputs, self.modules = host_fixture.fixture(self.payload)
        self.inputs[full.CLIENT_SOURCE] = "c" * 64
        self.modules.update(client_probe="d" * 64, client_collections="e" * 64)
        stage = self.envelope["report"]["stage3"]
        self.server = stage["cases"][full.SCENARIOS.index("collections")]
        self.inputs[full.COLLECTIONS_SOURCE] = full.COLLECTIONS_SOURCE_SHA256
        self.server["source_sha256"] = full.COLLECTIONS_SOURCE_SHA256
        self.server["message_count"] = 866  # Messages need not equal physical lines.
        self.client = {"status": "ok", "failure_kind": "none", "source_sha256": "c" * 64,
                       "module_sha256": "d" * 64, "roundtrip_sha256": "d" * 64,
                       "process_diagnostics": process_diagnostics(),
                       **dict.fromkeys(full.CLIENT_FLAGS, True)}
        stage["client_probe"] = self.client
        self.collections = {**copy.deepcopy(self.client), "source_sha256": self.inputs[full.COLLECTIONS_SOURCE],
                      "module_sha256": "e" * 64, "roundtrip_sha256": "e" * 64,
                      **{key: self.server[key] for key in OUTPUT_KEYS}}
        stage["client_collections"] = self.collections

    def validate(self, envelope=None, *, client_collections=True, client_dates=False, watchdog_check=False):
        return full.validate_envelope(host_fixture.encode(self.envelope if envelope is None else envelope),
            host_fixture.NONCE, self.inputs, self.modules, smoke.validate_report,
            client_collections=client_collections, client_dates=client_dates, watchdog_check=watchdog_check)

    def failure(self):
        self.envelope["report"].update(status="stage3_failed", native_tests_completed=False)
        self.envelope["report"]["stage3"].update(status="failed", failure_kind="process_failed")
        self.envelope["outputs"] = []

    @staticmethod
    def unreached():
        return {**suite.empty_client_report(), **dict.fromkeys(OUTPUT_KEYS)}

    def watchdog(self):
        record = {**copy.deepcopy(self.client), "completed": False, "process_exited": False,
                  "witness_verified": False, "timeout_verified": True}
        self.envelope["report"]["stage3"]["client_watchdog"] = record
        return record

    def dates(self):
        stage = self.envelope["report"]["stage3"]
        server = stage["cases"][full.SCENARIOS.index("dates")]
        server["message_count"] = 185
        self.modules["client_dates"] = "f" * 64
        record = {**copy.deepcopy(self.client), "source_sha256": self.inputs[full.DATES_SOURCE],
                  "module_sha256": "f" * 64, "roundtrip_sha256": "f" * 64,
                  **{key: server[key] for key in OUTPUT_KEYS}}
        stage["client_dates"] = record
        return record

    def test_fresh_multiline_bytes_and_only_six_public_outputs(self):
        report, outputs = self.validate()
        self.assertEqual(outputs["collections"], self.payload)
        self.assertEqual(list(outputs), list(full.SCENARIOS))
        self.assertEqual(report["stage3"]["client_collections"]["message_count"], 866)
        self.assertEqual(len(self.inputs), 24)
        self.assertEqual(len(full.ARTIFACT_FILES), 7)
        self.assertNotIn("fresh collections", json.dumps(report))

    def test_opt_in_is_exact_and_legacy_schema_stays_unchanged(self):
        with self.assertRaises(full.FullError):
            self.validate(client_collections=False)
        self.envelope["report"]["stage3"].pop("client_collections")
        self.validate(client_collections=False)
        with self.assertRaises(full.FullError):
            self.validate()

    def test_requires_fixed_client_input_and_generated_module_identity(self):
        self.modules.pop("client_collections")
        with self.assertRaises(full.FullError):
            self.validate()

        self.modules["client_collections"] = "e" * 64
        self.inputs.pop(full.CLIENT_SOURCE)
        self.envelope["report"]["stage3"].pop("client_probe")
        with self.assertRaises(full.FullError):
            self.validate()

    def test_matching_source_claims_cannot_replace_the_reviewed_collections_source(self):
        self.inputs[full.COLLECTIONS_SOURCE] = "0" * 64
        self.server["source_sha256"] = "0" * 64
        self.collections["source_sha256"] = "0" * 64
        with self.assertRaises(full.FullError):
            self.validate()

    def test_rejects_missing_extra_fields_invalid_types_and_false_completion(self):
        edits = [lambda d: d.update(raw_output="PRIVATE"), lambda d: d.update(status="failed"),
                 lambda d: d.update(failure_kind="timeout"), lambda d: d.update(source_sha256="0" * 64),
                 lambda d: d.update(module_sha256="b" * 64), lambda d: d.update(roundtrip_sha256="b" * 64)]
        for key in self.collections:
            edits.append(lambda d, key=key: d.pop(key))
        for key in full.CLIENT_FLAGS:
            for value in (False, 1, None):
                edits.append(lambda d, key=key, value=value: d.update({key: value}))
        for key in OUTPUT_KEYS:
            for value in (None, True, -1, "PRIVATE", 1_048_577):
                edits.append(lambda d, key=key, value=value: d.update({key: value}))
        for edit in edits:
            envelope = copy.deepcopy(self.envelope)
            edit(envelope["report"]["stage3"]["client_collections"])
            with self.subTest(edit=edit), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_metadata_is_bound_to_fresh_server_collections_not_another_case(self):
        for key, value in (("output_sha256", "f" * 64), ("output_size", 8633), ("message_count", 99)):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["client_collections"][key] = value
            with self.subTest(key=key), self.assertRaises(full.FullError):
                self.validate(envelope)

        # Another successful case's bytes are not a substitute for collections.
        alternate = b"different server case\n"
        other = self.envelope["report"]["stage3"]["cases"][-1]
        other.update(output_sha256=full.digest(alternate), output_size=len(alternate), message_count=866)
        self.envelope["outputs"][-1].update(sha256=full.digest(alternate), size=len(alternate),
                                          data_b64=base64.b64encode(alternate).decode())
        self.validate()
        self.collections.update({key: other[key] for key in OUTPUT_KEYS})
        with self.assertRaises(full.FullError):
            self.validate()

    def test_matching_but_wrong_server_and_client_message_counts_are_rejected(self):
        for count in (0, 841, 852, 865, 867, 32768, True, "866"):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["cases"][full.SCENARIOS.index("collections")]["message_count"] = count
            envelope["report"]["stage3"]["client_collections"]["message_count"] = count
            with self.subTest(count=count), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_transport_tampering_missing_extra_reordered_and_trailing_byte(self):
        edits = [lambda d: d["outputs"].pop(), lambda d: d["outputs"].reverse(),
                 lambda d: d["outputs"].append(copy.deepcopy(d["outputs"][-1])),
                 lambda d: d["outputs"][-1].update(name="client_collections.out"),
                 lambda d: d["report"]["stage3"]["cases"].reverse(),
                 lambda d: d.update(nonce="0" * 32)]
        for edit in edits:
            envelope = copy.deepcopy(self.envelope)
            edit(envelope)
            with self.subTest(edit=edit), self.assertRaises(full.FullError):
                self.validate(envelope)
        # Even updating transport metadata cannot replace bytes already witnessed.
        entry = self.envelope["outputs"][0]
        changed = self.payload + b" "
        entry.update(size=len(changed), sha256=full.digest(changed), data_b64=base64.b64encode(changed).decode())
        with self.assertRaises(full.FullError):
            self.validate()

    def test_failed_record_can_have_no_or_complete_identity_but_never_output_metadata(self):
        self.failure()
        for identity in (False, True):
            record = self.unreached()
            record.update(status="failed", failure_kind="process_failed")
            if identity:
                record.update(**{key: self.collections[key] for key in full.CLIENT_HASHES})
            self.envelope["report"]["stage3"]["client_collections"] = record
            self.assertEqual(self.validate()[1], {})
            for key in OUTPUT_KEYS:
                record[key] = self.collections[key]
                with self.subTest(key=key), self.assertRaises(full.FullError):
                    self.validate()
                record[key] = None
            record.update(**{key: self.collections[key] for key in OUTPUT_KEYS})
            with self.assertRaises(full.FullError):
                self.validate()

    def test_probe_collections_watchdog_order_and_suite_completion(self):
        self.watchdog()
        self.validate(watchdog_check=True)
        self.failure()
        self.envelope["report"]["stage3"]["client_collections"] = self.unreached()
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=True)

        self.envelope["report"]["stage3"]["client_watchdog"] = {
            **suite.empty_client_report(), "timeout_verified": False}
        self.validate(watchdog_check=True)
        self.envelope["report"]["stage3"]["client_collections"] = self.collections
        self.envelope["report"]["stage3"]["client_probe"] = suite.empty_client_report()
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=True)

    def test_dates_and_collections_are_independent_exact_opt_ins_with_fixed_execution_order(self):
        self.dates()
        self.watchdog()
        self.validate(client_dates=True, watchdog_check=True)
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=True)
        self.failure()
        stage = self.envelope["report"]["stage3"]
        stage["client_watchdog"] = {**suite.empty_client_report(), "timeout_verified": False}
        stage["client_dates"] = self.unreached()
        with self.assertRaises(full.FullError):
            self.validate(client_dates=True, watchdog_check=True)
        stage["client_collections"] = self.unreached()
        self.validate(client_dates=True, watchdog_check=True)
        self.dates()
        self.validate(client_dates=True, watchdog_check=True)
        stage["client_collections"] = self.collections
        self.validate(client_dates=True, watchdog_check=True)

    def test_unreached_suite_keeps_all_requested_records_empty(self):
        self.dates()
        self.watchdog()
        report = self.envelope["report"]
        report.update(status="stage2_failed", native_tests_completed=False,
                      runtime_version=None, runtime_version_source="not_measured",
                      security_settings_changed=None)
        report["stage2"].update(status="failed", failed_stage="load", failure_kind="process_failed",
            actual_version=None, version_source="not_measured", simple_output_sha256=None,
            security_settings_state="unverified", protection_observation=smoke.DIAGNOSTICS.empty_protection_observation(),
            **dict.fromkeys(smoke.STAGE_FLAGS, False))
        report["stage3"] = suite.empty_report(host_fixture.NONCE, client_probe=True,
            client_dates=True, client_collections=True, watchdog_check=True)
        self.envelope["outputs"] = []
        self.validate(client_dates=True, watchdog_check=True)
        report["stage3"]["client_collections"] = self.collections
        with self.assertRaises(full.FullError):
            self.validate(client_dates=True, watchdog_check=True)

    def test_failed_server_prevents_collections_even_if_probe_is_forged_ok(self):
        self.failure()
        self.server.update(status="failed", **dict.fromkeys(OUTPUT_KEYS))
        self.envelope["report"]["stage3"]["failed_case"] = "collections"
        with self.assertRaises(full.FullError):
            self.validate()

    def test_unreached_collections_cannot_prove_success_or_retain_metadata(self):
        self.envelope["report"]["stage3"]["client_collections"] = self.unreached()
        with self.assertRaises(full.FullError):
            self.validate()
        self.failure()
        self.validate()
        self.envelope["report"]["stage3"]["client_collections"]["message_count"] = 0
        with self.assertRaises(full.FullError):
            self.validate()

    def test_duplicate_trailing_json_nonfinite_and_stale_stage_nonce_fail_closed(self):
        raw = host_fixture.encode(self.envelope)
        malformed = [raw + b" PRIVATE", raw.replace(b'"message_count":866', b'"message_count":866,"message_count":866'),
                     raw.replace(b'"message_count":866', b'"message_count":NaN')]
        for value in malformed:
            with self.subTest(value=value[:30]), self.assertRaises(full.FullError):
                full.validate_envelope(value, host_fixture.NONCE, self.inputs, self.modules,
                                       smoke.validate_report, client_collections=True)
        self.envelope["report"]["stage3"]["nonce"] = "0" * 32
        with self.assertRaises(full.FullError):
            self.validate()

    def test_nonquiet_diagnostic_cannot_be_promoted_to_success(self):
        for diagnostic in (process_diagnostics(stage="before_probe"),
                           process_diagnostics(reason="unverified"),
                           process_diagnostics(reason="unexpected_processes", classes={"other": 1})):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["client_collections"]["process_diagnostics"] = diagnostic
            with self.subTest(diagnostic=diagnostic), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_legacy_four_record_finite_caps_stay_unchanged(self):
        dates = self.dates()
        self.watchdog()
        self.failure()
        self.envelope["report"]["stage3"]["failure_kind"] = "unexpected_failure"
        watchdog = self.envelope["report"]["stage3"]["client_watchdog"]
        watchdog.update(status="failed", failure_kind="unexpected_failure", timeout_verified=False,
                        process_diagnostics=process_diagnostics(stage="before_probe", reason="unexpected_processes",
                            classes={"native": 100, "display": 26, "session_bus": 26, "shell": 26,
                                     "python": 26, "other": 26, "unreadable": 26}, zombie_count=256))
        # Largest numeric widths with both parity records, under the aggregate cap.
        for case in self.envelope["report"]["stage3"]["cases"]:
            case.update(output_size=209715, message_count=32768)
        self.envelope["report"]["stage3"]["cases"][1]["message_count"] = 185
        dates.update(output_size=209715, message_count=185)
        self.server.update(output_size=1048576, message_count=866)
        self.collections.update(output_size=1048576, message_count=866)
        self.envelope["report"].update(python_version="99.99.999")
        self.envelope["report"]["configuration_format"].update(
            schema_version="99.999.999.999", element_count=4096, known_elements=sorted(smoke.KNOWN_ELEMENTS))
        self.validate(client_dates=True, watchdog_check=True)
        self.assertLessEqual(len(host_fixture.encode(self.envelope["report"]["stage3"])), 8192)
        self.assertLessEqual(len(host_fixture.encode(self.envelope["report"])), 32768)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "stage3.json"
            suite.write_report(path, self.envelope["report"]["stage3"])
            self.assertLessEqual(path.stat().st_size, 8192)
        self.assertEqual(suite.MAX_STAGE_REPORT, 8192)
        self.assertEqual(full.MAX_REPORT, 32768)


    def values_record(self):
        stage = self.envelope["report"]["stage3"]
        server = stage["cases"][full.SCENARIOS.index("values")]
        self.inputs[full.VALUES_SOURCE] = full.VALUES_SOURCE_SHA256
        server.update(source_sha256=full.VALUES_SOURCE_SHA256, message_count=402)
        self.modules["client_values"] = "9" * 64
        record = {**copy.deepcopy(self.client), "source_sha256": full.VALUES_SOURCE_SHA256,
                  "module_sha256": "9" * 64, "roundtrip_sha256": "9" * 64,
                  **{key: server[key] for key in OUTPUT_KEYS}}
        stage["client_values"] = record
        return record

    @staticmethod
    def compact(stage):
        result = copy.deepcopy(stage)
        result["schema"] = 2
        for key in full.CLIENT_WIRE_RECORDS:
            if key in result:
                record = result[key]
                record["hashes"] = [record.pop(name) for name in full.CLIENT_WIRE_HASHES]
                record["proof"] = [record.pop(name) for name in full.CLIENT_WIRE_PROOF]
        return result

    def validate_all(self, envelope=None):
        return full.validate_envelope(host_fixture.encode(self.envelope if envelope is None else envelope),
            host_fixture.NONCE, self.inputs, self.modules, smoke.validate_report,
            client_dates=True, client_values=True, client_collections=True, watchdog_check=True)

    def all_clients(self):
        self.dates()
        self.values_record()
        self.watchdog()
        return self.envelope["report"]["stage3"]

    def test_compact_five_records_roundtrip_is_lossless_and_reports_named_evidence(self):
        stage = self.all_clients()
        named = copy.deepcopy(stage)
        compact = self.compact(stage)
        self.assertEqual(len(host_fixture.encode(named)) - len(host_fixture.encode(compact)), 480)
        self.assertEqual(suite.encode_stage_wire(named), compact)
        self.assertEqual(suite.decode_stage_wire(compact), named)
        self.assertEqual(full.decode_stage3_wire(compact), named)
        self.assertEqual(stage, named)  # Neither decoder nor fixture mutates callers.
        self.envelope["report"]["stage3"] = compact
        report, outputs = self.validate_all()
        self.assertEqual(report["stage3"], named)
        self.assertEqual(outputs["collections"], self.payload)
        self.assertNotIn('"hashes"', json.dumps(report))
        self.assertNotIn('"proof"', json.dumps(report))
        self.assertEqual(len(self.inputs), 24)
        self.assertEqual(full.ARTIFACT_FILES, tuple(name + ".out" for name in full.SCENARIOS) + ("provenance.json",))

    def test_compact_decoder_rejects_corruption_missing_hybrids_types_and_extra_fields(self):
        named = self.all_clients()
        baseline = self.compact(named)
        edits = [lambda d: d.update(schema=True), lambda d: d.update(schema="2"),
                 lambda d: d.update(schema=3), lambda d: d.update(schema=1),
                 lambda d: d.pop("client_collections"),
                 lambda d: d.update(client_probe=named["client_probe"]),
                 lambda d: d["client_collections"].update(source_sha256=full.COLLECTIONS_SOURCE_SHA256),
                 lambda d: d["client_collections"].update(entered=True),
                 lambda d: d["client_collections"].update(extra="PRIVATE")]
        for key in full.CLIENT_WIRE_RECORDS:
            edits.append(lambda d, key=key: d.pop(key))
            for field in ("hashes", "proof"):
                edits.append(lambda d, key=key, field=field: d[key].pop(field))
                for value in (None, {}, "PRIVATE", [], [True], [True] * 6):
                    edits.append(lambda d, key=key, field=field, value=value: d[key].update({field: value}))
            for index in range(3):
                for value in (True, 1, "A" * 64, "0" * 63, "PRIVATE", None):
                    edits.append(lambda d, key=key, index=index, value=value: d[key]["hashes"].__setitem__(index, value))
            for index in range(5):
                for value in (0, 1, None, "true"):
                    edits.append(lambda d, key=key, index=index, value=value: d[key]["proof"].__setitem__(index, value))
        for edit in edits:
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"] = copy.deepcopy(baseline)
            edit(envelope["report"]["stage3"])
            with self.subTest(edit=edit), self.assertRaises(full.FullError):
                self.validate_all(envelope)

    def test_compact_hash_source_order_and_watchdog_proof_positions_are_bound(self):
        compact = self.compact(self.all_clients())
        for key in full.CLIENT_WIRE_RECORDS:
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"] = copy.deepcopy(compact)
            hashes = envelope["report"]["stage3"][key]["hashes"]
            hashes[0], hashes[1] = hashes[1], hashes[0]
            with self.subTest(key=key), self.assertRaises(full.FullError):
                self.validate_all(envelope)
        for left, right in ((0, 1), (1, 3), (3, 4)):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"] = copy.deepcopy(compact)
            proof = envelope["report"]["stage3"]["client_watchdog"]["proof"]
            proof[left], proof[right] = proof[right], proof[left]
            with self.subTest(left=left, right=right), self.assertRaises(full.FullError):
                self.validate_all(envelope)

    def test_compact_five_record_maximum_valid_failure_budget_remains_bounded(self):
        stage = self.all_clients()
        self.failure()
        stage["failure_kind"] = "unexpected_failure"
        watchdog = stage["client_watchdog"]
        watchdog.update(status="failed", failure_kind="unexpected_failure", timeout_verified=False,
                        process_diagnostics=process_diagnostics(stage="before_probe", reason="unexpected_processes",
                            classes={"native": 100, "display": 26, "session_bus": 26, "shell": 26,
                                     "python": 26, "other": 26, "unreadable": 26}, zombie_count=256))
        for case in stage["cases"]:
            case.update(output_size=209715, message_count=32768)
        for name, count in (("dates", 185), ("values", 402), ("collections", 866)):
            case = stage["cases"][full.SCENARIOS.index(name)]
            case.update(message_count=count)
            stage["client_" + name].update(message_count=count, output_size=209715)
        stage["cases"][0]["output_size"] = 1048576
        stage["client_collections"]["output_size"] = 1048576
        self.envelope["report"].update(python_version="99.99.999")
        self.envelope["report"]["configuration_format"].update(
            schema_version="99.999.999.999", element_count=4096, known_elements=sorted(smoke.KNOWN_ELEMENTS))
        compact = self.compact(stage)
        self.assertGreater(len(host_fixture.encode(stage)), 8192)
        self.assertLessEqual(len(host_fixture.encode(compact)), 8192)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "stage3.json"
            suite.write_report(path, stage)
            wire = path.read_bytes()
            self.assertLessEqual(len(wire), 8192)
            self.assertEqual(full.decode_stage3_wire(full.strict_json(wire, 8192)), stage)
            self.assertEqual(suite.decode_stage_wire(json.loads(wire)), stage)
        self.envelope["report"]["stage3"] = compact
        report, outputs = self.validate_all()
        self.assertEqual(report["stage3"], stage)
        self.assertEqual(outputs, {})
        self.assertLessEqual(len(host_fixture.encode(report)), 32768)
        self.assertEqual(suite.MAX_STAGE_REPORT, 8192)
        self.assertEqual(full.MAX_STAGE_REPORT, 8192)
        self.assertEqual(full.MAX_REPORT, 32768)

    def test_compact_failed_and_unreached_records_preserve_every_proof_value(self):
        stage = self.all_clients()
        self.failure()
        stage["client_watchdog"] = {**suite.empty_client_report(), "timeout_verified": False}
        stage["client_collections"] = self.unreached()
        for failed in (False, True):
            record = stage["client_collections"]
            if failed:
                record.update(status="failed", failure_kind="module_mismatch", entered=True,
                              **{key: self.collections[key] for key in full.CLIENT_HASHES})
            compact = self.compact(stage)
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"] = compact
            report, outputs = self.validate_all(envelope)
            self.assertEqual(report["stage3"], stage)
            self.assertEqual(outputs, {})
        bad = self.compact(stage)
        bad["client_collections"]["proof"][-1] = True
        envelope["report"]["stage3"] = bad
        with self.assertRaises(full.FullError):
            self.validate_all(envelope)

    def test_compact_values_must_complete_before_collections(self):
        stage = self.all_clients()
        self.failure()
        stage["client_watchdog"] = {**suite.empty_client_report(), "timeout_verified": False}
        stage["client_values"] = self.unreached()
        self.envelope["report"]["stage3"] = self.compact(stage)
        with self.assertRaises(full.FullError):
            self.validate_all()
        stage["client_collections"] = self.unreached()
        self.envelope["report"]["stage3"] = self.compact(stage)
        self.validate_all()

    def test_compact_stage_over_limit_fails_before_expansion(self):
        compact = self.compact(self.all_clients())
        compact["client_collections"]["failure_kind"] = "x" * 8192
        with self.assertRaisesRegex(ValueError, "stage wire limit"):
            full.decode_stage3_wire(compact)


if __name__ == "__main__":
    unittest.main()
