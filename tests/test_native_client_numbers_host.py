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


class ClientNumbersHostTests(unittest.TestCase):
    def setUp(self):
        # Deliberately not historical numbers output: acceptance must use fresh bytes.
        self.payload = b"fresh numbers\n" * 349 + b"message with\nembedded newline\n"
        self.envelope, self.inputs, self.modules = host_fixture.fixture(self.payload)
        self.inputs[full.CLIENT_SOURCE] = "c" * 64
        self.modules.update(client_probe="d" * 64, client_numbers="e" * 64)
        stage = self.envelope["report"]["stage3"]
        self.server = stage["cases"][full.SCENARIOS.index("numbers")]
        self.inputs[full.NUMBERS_SOURCE] = full.NUMBERS_SOURCE_SHA256
        self.server["source_sha256"] = full.NUMBERS_SOURCE_SHA256
        self.server["message_count"] = 350  # Messages need not equal physical lines.
        self.client = {"status": "ok", "failure_kind": "none", "source_sha256": "c" * 64,
                       "module_sha256": "d" * 64, "roundtrip_sha256": "d" * 64,
                       "process_diagnostics": process_diagnostics(),
                       **dict.fromkeys(full.CLIENT_FLAGS, True)}
        stage["client_probe"] = self.client
        self.numbers = {**copy.deepcopy(self.client), "source_sha256": self.inputs[full.NUMBERS_SOURCE],
                      "module_sha256": "e" * 64, "roundtrip_sha256": "e" * 64,
                      **{key: self.server[key] for key in OUTPUT_KEYS}}
        self.numbers["conversion_verified"] = True
        stage["client_numbers"] = self.numbers

    def validate(self, envelope=None, *, client_numbers=True, client_dates=False, watchdog_check=False):
        return full.validate_envelope(host_fixture.encode(self.envelope if envelope is None else envelope),
            host_fixture.NONCE, self.inputs, self.modules, smoke.validate_report,
            client_numbers=client_numbers, client_dates=client_dates, watchdog_check=watchdog_check)

    def failure(self):
        self.envelope["report"].update(status="stage3_failed", native_tests_completed=False)
        self.envelope["report"]["stage3"].update(status="failed", failure_kind="process_failed")
        self.envelope["outputs"] = []

    @staticmethod
    def unreached():
        return {**suite.empty_numbers_report()}

    def watchdog(self):
        record = {**copy.deepcopy(self.client), "completed": False, "process_exited": False,
                  "witness_verified": False, "timeout_verified": True}
        self.envelope["report"]["stage3"]["client_watchdog"] = record
        return record

    def dates(self):
        stage = self.envelope["report"]["stage3"]
        server = stage["cases"][full.SCENARIOS.index("dates")]
        server["message_count"] = 100
        self.modules["client_dates"] = "f" * 64
        record = {**copy.deepcopy(self.client), "source_sha256": self.inputs[full.DATES_SOURCE],
                  "module_sha256": "f" * 64, "roundtrip_sha256": "f" * 64,
                  **{key: server[key] for key in OUTPUT_KEYS}}
        stage["client_dates"] = record
        return record

    def test_fresh_multiline_bytes_and_only_six_public_outputs(self):
        report, outputs = self.validate()
        self.assertEqual(outputs["numbers"], self.payload)
        self.assertEqual(list(outputs), list(full.SCENARIOS))
        self.assertEqual(report["stage3"]["client_numbers"]["message_count"], 350)
        self.assertEqual(len(self.inputs), 24)
        self.assertEqual(len(full.ARTIFACT_FILES), 7)
        self.assertNotIn("fresh numbers", json.dumps(report))

    def test_opt_in_is_exact_and_legacy_schema_stays_unchanged(self):
        with self.assertRaises(full.FullError):
            self.validate(client_numbers=False)
        self.envelope["report"]["stage3"].pop("client_numbers")
        self.validate(client_numbers=False)
        with self.assertRaises(full.FullError):
            self.validate()

    def test_requires_fixed_client_input_and_generated_module_identity(self):
        self.modules.pop("client_numbers")
        with self.assertRaises(full.FullError):
            self.validate()

        self.modules["client_numbers"] = "e" * 64
        self.inputs.pop(full.CLIENT_SOURCE)
        self.envelope["report"]["stage3"].pop("client_probe")
        with self.assertRaises(full.FullError):
            self.validate()

    def test_matching_source_claims_cannot_replace_the_reviewed_numbers_source(self):
        self.inputs[full.NUMBERS_SOURCE] = "0" * 64
        self.server["source_sha256"] = "0" * 64
        self.numbers["source_sha256"] = "0" * 64
        with self.assertRaises(full.FullError):
            self.validate()

    def test_rejects_missing_extra_fields_invalid_types_and_false_completion(self):
        edits = [lambda d: d.update(raw_output="PRIVATE"), lambda d: d.update(status="failed"),
                 lambda d: d.update(failure_kind="timeout"), lambda d: d.update(source_sha256="0" * 64),
                 lambda d: d.update(module_sha256="b" * 64), lambda d: d.update(roundtrip_sha256="b" * 64)]
        for key in self.numbers:
            edits.append(lambda d, key=key: d.pop(key))
        for key in full.CLIENT_FLAGS:
            for value in (False, 1, None):
                edits.append(lambda d, key=key, value=value: d.update({key: value}))
        for key in OUTPUT_KEYS:
            for value in (None, True, -1, "PRIVATE", 1_048_577):
                edits.append(lambda d, key=key, value=value: d.update({key: value}))
        for edit in edits:
            envelope = copy.deepcopy(self.envelope)
            edit(envelope["report"]["stage3"]["client_numbers"])
            with self.subTest(edit=edit), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_conversion_proof_is_required_and_strictly_boolean(self):
        for value in (False, None, 0, 1, "true"):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["client_numbers"]["conversion_verified"] = value
            with self.assertRaises(full.FullError):
                self.validate(envelope)
        self.failure()
        self.envelope["report"]["stage3"]["client_numbers"] = self.unreached()
        self.envelope["report"]["stage3"]["client_numbers"]["conversion_verified"] = True
        with self.assertRaises(full.FullError):
            self.validate()

    def test_metadata_is_bound_to_fresh_server_numbers_not_another_case(self):
        for key, value in (("output_sha256", "f" * 64), ("output_size", 8633), ("message_count", 99)):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["client_numbers"][key] = value
            with self.subTest(key=key), self.assertRaises(full.FullError):
                self.validate(envelope)

        # Another successful case's bytes are not a substitute for numbers.
        alternate = b"different server case\n"
        other = self.envelope["report"]["stage3"]["cases"][0]
        other.update(output_sha256=full.digest(alternate), output_size=len(alternate), message_count=350)
        self.envelope["outputs"][0].update(sha256=full.digest(alternate), size=len(alternate),
                                          data_b64=base64.b64encode(alternate).decode())
        self.validate()
        self.numbers.update({key: other[key] for key in OUTPUT_KEYS})
        with self.assertRaises(full.FullError):
            self.validate()

    def test_matching_but_wrong_server_and_client_message_counts_are_rejected(self):
        for count in (0, 349, 262, 32768, True, "350"):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["cases"][full.SCENARIOS.index("numbers")]["message_count"] = count
            envelope["report"]["stage3"]["client_numbers"]["message_count"] = count
            with self.subTest(count=count), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_transport_tampering_missing_extra_reordered_and_trailing_byte(self):
        edits = [lambda d: d["outputs"].pop(), lambda d: d["outputs"].reverse(),
                 lambda d: d["outputs"].append(copy.deepcopy(d["outputs"][-1])),
                 lambda d: d["outputs"][-1].update(name="client_numbers.out"),
                 lambda d: d["report"]["stage3"]["cases"].reverse(),
                 lambda d: d.update(nonce="0" * 32)]
        for edit in edits:
            envelope = copy.deepcopy(self.envelope)
            edit(envelope)
            with self.subTest(edit=edit), self.assertRaises(full.FullError):
                self.validate(envelope)
        # Even updating transport metadata cannot replace bytes already witnessed.
        entry = self.envelope["outputs"][-1]
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
                record.update(**{key: self.numbers[key] for key in full.CLIENT_HASHES})
            self.envelope["report"]["stage3"]["client_numbers"] = record
            self.assertEqual(self.validate()[1], {})
            for key in OUTPUT_KEYS:
                record[key] = self.numbers[key]
                with self.subTest(key=key), self.assertRaises(full.FullError):
                    self.validate()
                record[key] = None
            record.update(**{key: self.numbers[key] for key in OUTPUT_KEYS})
            with self.assertRaises(full.FullError):
                self.validate()

    def test_probe_numbers_watchdog_order_and_suite_completion(self):
        self.watchdog()
        self.validate(watchdog_check=True)
        self.failure()
        self.envelope["report"]["stage3"]["client_numbers"] = self.unreached()
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=True)

        self.envelope["report"]["stage3"]["client_watchdog"] = {
            **suite.empty_client_report(), "timeout_verified": False}
        self.validate(watchdog_check=True)
        self.envelope["report"]["stage3"]["client_numbers"] = self.numbers
        self.envelope["report"]["stage3"]["client_probe"] = suite.empty_client_report()
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=True)

    def test_dates_and_numbers_are_independent_exact_opt_ins_with_fixed_execution_order(self):
        self.dates()
        self.watchdog()
        self.validate(client_dates=True, watchdog_check=True)
        with self.assertRaises(full.FullError):
            self.validate(watchdog_check=True)
        self.failure()
        stage = self.envelope["report"]["stage3"]
        stage["client_watchdog"] = {**suite.empty_client_report(), "timeout_verified": False}
        stage["client_dates"] = suite.empty_dates_report()
        with self.assertRaises(full.FullError):
            self.validate(client_dates=True, watchdog_check=True)
        stage["client_numbers"] = self.unreached()
        self.validate(client_dates=True, watchdog_check=True)
        self.dates()
        self.validate(client_dates=True, watchdog_check=True)
        self.numbers["conversion_verified"] = True
        stage["client_numbers"] = self.numbers
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
            client_dates=True, client_numbers=True, watchdog_check=True)
        self.envelope["outputs"] = []
        self.validate(client_dates=True, watchdog_check=True)
        report["stage3"]["client_numbers"] = self.numbers
        with self.assertRaises(full.FullError):
            self.validate(client_dates=True, watchdog_check=True)

    def test_failed_server_prevents_numbers_even_if_probe_is_forged_ok(self):
        self.failure()
        self.server.update(status="failed", **dict.fromkeys(OUTPUT_KEYS))
        self.envelope["report"]["stage3"]["failed_case"] = "numbers"
        with self.assertRaises(full.FullError):
            self.validate()

    def test_unreached_numbers_cannot_prove_success_or_retain_metadata(self):
        self.envelope["report"]["stage3"]["client_numbers"] = self.unreached()
        with self.assertRaises(full.FullError):
            self.validate()
        self.failure()
        self.validate()
        self.envelope["report"]["stage3"]["client_numbers"]["message_count"] = 0
        with self.assertRaises(full.FullError):
            self.validate()

    def test_duplicate_trailing_json_nonfinite_and_stale_stage_nonce_fail_closed(self):
        raw = host_fixture.encode(self.envelope)
        malformed = [raw + b" PRIVATE", raw.replace(b'"message_count":350', b'"message_count":350,"message_count":350'),
                     raw.replace(b'"message_count":350', b'"message_count":NaN')]
        for value in malformed:
            with self.subTest(value=value[:30]), self.assertRaises(full.FullError):
                full.validate_envelope(value, host_fixture.NONCE, self.inputs, self.modules,
                                       smoke.validate_report, client_numbers=True)
        self.envelope["report"]["stage3"]["nonce"] = "0" * 32
        with self.assertRaises(full.FullError):
            self.validate()

    def test_nonquiet_diagnostic_cannot_be_promoted_to_success(self):
        for diagnostic in (process_diagnostics(stage="before_probe"),
                           process_diagnostics(reason="unverified"),
                           process_diagnostics(reason="unexpected_processes", classes={"other": 1})):
            envelope = copy.deepcopy(self.envelope)
            envelope["report"]["stage3"]["client_numbers"]["process_diagnostics"] = diagnostic
            with self.subTest(diagnostic=diagnostic), self.assertRaises(full.FullError):
                self.validate(envelope)

    def test_worst_case_finite_stage_and_report_caps_stay_unchanged(self):
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
        self.envelope["report"]["stage3"]["cases"][1]["message_count"] = 100
        dates.update(output_size=209715, message_count=100)
        self.server.update(output_size=1048576, message_count=350)
        self.numbers.update(output_size=1048576, message_count=350)
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


class AllNumbersClientHostTests(unittest.TestCase):
    def test_all_six_clients_bind_fresh_evidence_and_fit_wire(self):
        import test_native_client_collections_host as c
        fixture = c.ClientCollectionsHostTests()
        fixture.setUp()
        stage = fixture.all_clients()
        server = stage["cases"][full.SCENARIOS.index("numbers")]
        fixture.inputs[full.NUMBERS_SOURCE] = full.NUMBERS_SOURCE_SHA256
        server.update(source_sha256=full.NUMBERS_SOURCE_SHA256, message_count=350)
        fixture.modules["client_numbers"] = "9" * 64
        stage["client_numbers"] = dict(copy.deepcopy(fixture.client),
            source_sha256=full.NUMBERS_SOURCE_SHA256, module_sha256="9" * 64,
            roundtrip_sha256="9" * 64, conversion_verified=True,
            **{key: server[key] for key in OUTPUT_KEYS})
        named = copy.deepcopy(stage)
        wire = suite.encode_stage_wire(stage)
        self.assertLessEqual(len(host_fixture.encode(wire)), 8192)
        fixture.envelope["report"]["stage3"] = wire
        args = dict(watchdog_check=True, client_dates=True, client_values=True,
                    client_collections=True, client_numbers=True)
        report, outputs = full.validate_envelope(host_fixture.encode(fixture.envelope),
            host_fixture.NONCE, fixture.inputs, fixture.modules, smoke.validate_report, **args)
        self.assertEqual(report["stage3"], named)
        self.assertEqual(set(outputs), set(full.SCENARIOS))
        self.assertEqual(len(fixture.inputs), 24)
        for predecessor in ("client_values", "client_collections"):
            altered = copy.deepcopy(fixture.envelope)
            altered["report"]["stage3"] = copy.deepcopy(named)
            altered["report"]["stage3"][predecessor] = suite.empty_values_report()
            with self.assertRaises(full.FullError):
                full.validate_envelope(host_fixture.encode(altered), host_fixture.NONCE,
                    fixture.inputs, fixture.modules, smoke.validate_report, **args)


if __name__ == "__main__":
    unittest.main()
