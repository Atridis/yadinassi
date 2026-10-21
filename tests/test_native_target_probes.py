"""Temporary probe coverage/budgets, not native results or replacement goldens.

Historical full-output/source-integrity assertions stay unchanged and red
while the diagnostic appendix is present.
"""
import hashlib
import itertools
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

from scripts import native_1c_full_host as full
from tests.native_observations import extract_payload
from yadinassi import ast
from yadinassi.parser import parse


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrational_tests/tests/collections.bsl"
BEGIN = "// BEGIN TEMPORARY NATIVE TARGET PROBES v1\n"
END = "// END TEMPORARY NATIVE TARGET PROBES v1\n"
PREFIX_SIZE = 245870
PREFIX_SHA256 = "70dfefabf9466e1d8d3e00e844f931a7b8f005ed110d74049e07fbfed8fbbc72"
NAMESPACE = "target-probes.v1."
VARIANTS = ("base", "n-one", "n-negative", "type-string", "type-boolean")
SMALL_ORDERS = ("UBNST", "TSNBU", "NTUBS", "TNUBS", "SNBTU", "BUSTN")
DIRECTIONS = ("forward", "reverse")
MAP_SUFFIXES = tuple(kind + "." + field for kind in ("map", "fixed")
                     for field in ("payload", "roundtrip.type", "roundtrip.count", "roundtrip.payload"))
MAP_SUFFIXES += tuple(kind + ".bindings" for kind in ("map", "readback", "fixed", "fixed-readback"))


def map_cases():
    for variant in VARIANTS:
        orders = ("".join(p) for p in itertools.permutations("UBNST")) if variant == "base" else SMALL_ORDERS
        for order in orders:
            yield NAMESPACE + "map." + variant + "." + order


def fill_cases():
    for parts in itertools.product(("source", "target", "both"), ("first", "middle", "last"),
                                   DIRECTIONS, DIRECTIONS, ("mutable", "fixed")):
        yield NAMESPACE + "fill." + ".".join(parts)


def sort_cases():
    for size, insertion, direction, repeat in itertools.product(range(15, 19),
            ("forward", "reverse", "interleaved"), ("asc", "desc", "asc-id-desc", "desc-id-asc"), (1, 2)):
        yield f"{NAMESPACE}sort.{size}.{insertion}.{direction}.pass{repeat}", size


class TargetProbeSourceTests(unittest.TestCase):
    def test_append_only_historical_prefix_and_unique_terminal_markers(self):
        # Git may expand source LF to CRLF on Windows. Check the complete
        # original repository byte stream, including BOM; never normalize output.
        raw = SOURCE.read_bytes()
        source = raw.replace(b"\r\n", b"\n")
        prefix, appendix = source.split(BEGIN.encode())
        self.assertTrue(prefix.endswith(b"\n\n"))
        prefix = prefix[:-1]  # The appendix owns exactly one leading blank line.
        self.assertEqual(len(prefix), PREFIX_SIZE)
        self.assertEqual(hashlib.sha256(prefix).hexdigest(), PREFIX_SHA256)
        self.assertEqual(source.count(BEGIN.encode()), 1)
        self.assertEqual(source.count(END.encode()), 1)
        self.assertTrue(appendix.endswith(END.encode()))
        self.assertLess(len(appendix), 20_000)

    def test_full_module_and_top_level_appendix_parse_without_new_routines(self):
        source = SOURCE.read_text(encoding="utf-8-sig")
        self.assertTrue(parse(source, str(SOURCE)))
        appendix = source.split(BEGIN, 1)[1]
        nodes = parse(appendix, str(SOURCE))
        self.assertTrue(nodes)
        self.assertFalse(any(isinstance(node, ast.Routine) for node in nodes))
        self.assertNotRegex(appendix, r"(?im)^\s*(?:Процедура|Функция|Procedure|Function)\s")
        # Exactly the static 5! list, not five nested runtime permutation loops.
        encoded = appendix.split("ДиагПерестановки = ", 1)[1].split(";", 1)[0]
        orders = "".join(re.findall(r'"([UBNST|]+)"', encoded)).split("|")
        self.assertEqual(orders, ["".join(p) for p in itertools.permutations("UBNST")])


class TargetProbeExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = {}
        # Same driver and per-case wall-time ceiling as native host comparison,
        # with portable subprocess transport for Windows test hosts.
        # These are VM outputs: actual Docker/native evidence is still required.
        env = os.environ.copy()
        env.update(YADINASSI_TIMEZONE="Etc/UTC", TZ="Etc/UTC", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        for name in full.SCENARIOS:
            script = ROOT / "integrational_tests/tests" / (name + ".bsl")
            result = subprocess.run([sys.executable, "-I", "-c", full.EXECUTE_SCRIPT,
                                     str(ROOT), str(script)], cwd=ROOT, env=env,
                                    capture_output=True, timeout=full.CASE_SECONDS)
            if result.returncode != 0 or result.stderr:
                raise AssertionError(f"{name} did not execute cleanly: {result.stderr.decode('utf-8', 'replace')}")
            cls.outputs[name] = result.stdout
        cls.text = cls.outputs["collections"].decode("utf-8")

    def test_six_complete_cases_fit_unchanged_output_and_time_budgets(self):
        self.assertEqual(full.CASE_SECONDS, 10)
        self.assertEqual(full.MAX_FILE, 1_048_576)
        self.assertEqual(full.MAX_TOTAL, 2_097_152)
        self.assertEqual(tuple(self.outputs), full.SCENARIOS)
        for name, data in self.outputs.items():
            with self.subTest(name=name):
                self.assertLess(len(data), full.MAX_FILE)
        self.assertLess(sum(map(len, self.outputs.values())), full.MAX_TOTAL)
        self.assertTrue(self.text.endswith(NAMESPACE + "complete: [ok]\n"))

    def test_historical_records_are_still_exact_before_diagnostics(self):
        # Supplemental append-only check, NOT an exception in either complete
        # native comparator. Both complete comparators remain strict.
        expected = (ROOT / "integrational_tests/output/collections.out").read_text(encoding="utf-8")
        prefix, appendix = self.text.split(NAMESPACE + "begin: [ok]\n", 1)
        self.assertEqual(prefix, expected)
        self.assertTrue(appendix)
        self.assertNotEqual(self.text, expected)

    def test_all_1901_labels_present_exactly_once_and_no_extra_probe_labels(self):
        actual = re.findall(r"^(target-probes\.v1\.[^:\n]+): \[", self.text, re.MULTILINE)
        expected = {NAMESPACE + item for item in ("begin", "map.complete", "fill.complete", "sort.complete", "complete")}
        expected.update(label + "." + suffix for label in map_cases() for suffix in MAP_SUFFIXES)
        expected.update(fill_cases())
        expected.update(label for label, _ in sort_cases())
        self.assertEqual(len(expected), 1901)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(set(actual), expected)

    def test_map_typed_bindings_survive_both_copies_without_assuming_stream_order(self):
        expected = '{"N",5};' + ";".join(key + '={"S","' + key + '"}' for key in "UBNST")
        for label in map_cases():
            with self.subTest(label=label):
                for kind in ("map", "readback", "fixed", "fixed-readback"):
                    self.assertEqual(extract_payload(self.text, label + "." + kind + ".bindings"), expected)
                for kind in ("map", "fixed"):
                    for field in ("roundtrip.type", "roundtrip.count"):
                        self.assertEqual(extract_payload(self.text, label + "." + kind + "." + field), "true")
                    for field in ("payload", "roundtrip.payload"):
                        self.assertTrue(extract_payload(self.text, label + "." + kind + "." + field))

    def test_fill_always_reports_status_and_every_target_field_even_after_error(self):
        for label in fill_cases():
            with self.subTest(label=label):
                payload = extract_payload(self.text, label)
                self.assertRegex(payload, r"^(?:ok|error);size=.*;ProbeName=.*;ProbeNumber=.*;hasMissing=.*;Missing=.+$")
                # Do not freeze a mutation policy before native evidence.
                for field in ("size", "ProbeName", "ProbeNumber", "hasMissing", "Missing"):
                    self.assertEqual(payload.count(";" + field + "="), 1)

    def test_sort_reports_all_ids_and_row_identity_without_predicting_tie_order(self):
        for label, size in sort_cases():
            with self.subTest(label=label):
                payload = extract_payload(self.text, label)
                prefix, sequence = payload.split(";ids=", 1)
                self.assertEqual(prefix, 'ok;identity={"B",1}')
                identifiers = [int(value) for value in sequence.split(",")]
                self.assertEqual(sorted(identifiers), list(range(1, size + 1)))


if __name__ == "__main__":
    unittest.main()
