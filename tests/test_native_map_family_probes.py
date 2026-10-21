"""Second bounded map experiment: VM coverage, not native expectations.

Historical complete-output and complete-source gates remain unchanged and red.
No expected iteration, hash, bucket, growth or serialization order is encoded.
"""
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

from scripts import native_1c_full_host as full
from tests.native_observations import extract_payload
from yadinassi import ast
from yadinassi.maps import BSLMap, BSLFixedMap
from yadinassi.parser import parse
from yadinassi.serialization import value_from_string_internal
from yadinassi.values import BSLType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "integrational_tests/tests/collections.bsl"
BEGIN = "// BEGIN TEMPORARY NATIVE MAP FAMILY PROBES v1\n"
END = "// END TEMPORARY NATIVE MAP FAMILY PROBES v1\n"
PREFIX_SIZE = 245870
PREFIX_SHA256 = "70dfefabf9466e1d8d3e00e844f931a7b8f005ed110d74049e07fbfed8fbbc72"
NAMESPACE = "target-map-family.v1."
ORDERS = ("NUBST", "NBSTU")
KINDS = ("map", "readback", "fixed", "fixed-readback")
CHECKPOINTS = (5, 13, 14, 29, 30, 59, 60, 64)
SUPPLEMENTS = (
    ("minus1p5", "-1.5"), ("minus0p5", "-0.5"),
    ("plus0p5", "0.5"), ("plus1p5", "1.5"),
    ("plus13p5", "13.5"), ("plus26p5", "26.5"),
    ("u32-minus1", "4294967295"), ("u32", "4294967296"),
    ("u32-plus1", "4294967297"), ("u64-minus1", "18446744073709551615"),
    ("u64", "18446744073709551616"),
)


def number_cases():
    for label, value in [(str(n), str(n)) for n in range(-30, 31)] + list(SUPPLEMENTS):
        for order in ORDERS:
            yield NAMESPACE + f"number.{label}.{order}", Decimal(value)


def growth_cases():
    for label, number in (("zero", Decimal(0)), ("minus1", Decimal(-1))):
        for order in ORDERS:
            yield NAMESPACE + f"growth.{label}.{order}", number, order


def snapshots():
    for label, number in number_cases():
        yield label, number, 5
    for label, number, _ in growth_cases():
        for size in CHECKPOINTS:
            yield f"{label}.grow.{size}", number, size
        for phase in ("deleted", "cleared", "fresh"):
            yield f"{label}.{phase}.5", number, 5


def mutation_labels():
    for label, _, order in growth_cases():
        for phase, sizes in (("grow", range(1, 65)), ("deleted", (5,)),
                             ("cleared", range(1, 6)), ("fresh", range(1, 6))):
            for size in sizes:
                identifiers = set(order[:size]) if size < 5 else expected_ids(size)
                yield f"{label}.{phase}.{size}.iteration", identifiers


def expected_ids(size):
    return set("UBNST") | {f"F{n}" for n in range(2, size - 3)}


def expected_keys(number, size):
    return list(zip("UBNST", (None, False, number, "0", BSLType.NUMBER))) + [
        (f"F{n}", Decimal(n)) for n in range(2, size - 3)]


class MapFamilySourceTests(unittest.TestCase):
    def test_entire_original_prefix_and_only_one_terminal_appendix(self):
        # Only Git CRLF transport is normalized; include all original bytes/BOM.
        source = SOURCE.read_bytes().replace(b"\r\n", b"\n")
        prefix, appendix = source.split(BEGIN.encode())
        self.assertTrue(prefix.endswith(b"\n\n"))
        prefix = prefix[:-1]  # Exactly one leading blank line belongs to appendix.
        self.assertEqual(len(prefix), PREFIX_SIZE)
        self.assertEqual(hashlib.sha256(prefix).hexdigest(), PREFIX_SHA256)
        self.assertEqual(source.count(BEGIN.encode()), 1)
        self.assertEqual(source.count(END.encode()), 1)
        self.assertTrue(appendix.endswith(END.encode()))
        self.assertLess(len(appendix), 16_000)
        self.assertNotIn(b"target-probes.v1", source)

    def test_full_source_and_top_level_appendix_parse_without_new_routines(self):
        source = SOURCE.read_text(encoding="utf-8-sig")
        self.assertTrue(parse(source, str(SOURCE)))
        appendix = source.split(BEGIN, 1)[1]
        nodes = parse(appendix, str(SOURCE))
        self.assertTrue(nodes)
        self.assertFalse(any(isinstance(node, ast.Routine) for node in nodes))
        self.assertNotRegex(appendix, r"(?im)^\s*(?:Процедура|Функция|Procedure|Function)\s")

    def test_bounded_grid_is_complete_and_disjoint(self):
        numeric = list(number_cases())
        self.assertEqual(len(numeric), 144)
        self.assertEqual(len({number for _, number in numeric}), 72)
        self.assertEqual(len(list(growth_cases())), 4)
        self.assertEqual(len(list(snapshots())), 188)
        self.assertEqual(len(list(mutation_labels())), 300)
        # Growth filler keys must never replace any base numeric key.
        for _, number, _ in growth_cases():
            self.assertNotIn(number, map(Decimal, range(2, 61)))


class MapFamilyExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs, cls.seconds = {}, {}
        env = os.environ.copy()
        env.update(YADINASSI_TIMEZONE="Etc/UTC", TZ="Etc/UTC", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        for name in full.SCENARIOS:
            script = ROOT / "integrational_tests/tests" / (name + ".bsl")
            started = time.monotonic()
            result = subprocess.run([sys.executable, "-I", "-c", full.EXECUTE_SCRIPT,
                                     str(ROOT), str(script)], cwd=ROOT, env=env,
                                    capture_output=True, timeout=full.CASE_SECONDS)
            cls.seconds[name] = time.monotonic() - started
            if result.returncode or result.stderr:
                raise AssertionError(f"{name} did not execute cleanly: {result.stderr.decode('utf-8', 'replace')}")
            cls.outputs[name] = result.stdout
        cls.text = cls.outputs["collections"].decode("utf-8")

    def test_all_six_cases_fit_unchanged_time_and_output_budgets(self):
        self.assertEqual(full.CASE_SECONDS, 10)
        self.assertEqual(full.MAX_FILE, 1_048_576)
        self.assertEqual(full.MAX_TOTAL, 2_097_152)
        self.assertEqual(tuple(self.outputs), full.SCENARIOS)
        for name, data in self.outputs.items():
            with self.subTest(name=name):
                self.assertLess(len(data), full.MAX_FILE)
                self.assertLess(self.seconds[name], full.CASE_SECONDS)
        self.assertLess(len(self.outputs["collections"]), 750_000)
        self.assertLess(sum(map(len, self.outputs.values())), full.MAX_TOTAL)
        self.assertTrue(self.text.endswith(NAMESPACE + "complete: [ok]\n"))

    def test_every_historical_collections_output_byte_remains_prefix(self):
        # Supplemental prefix assertion, never an exception in a full comparator.
        expected = (ROOT / "integrational_tests/output/collections.out").read_bytes().replace(b"\r\n", b"\n")
        before, appendix = self.outputs["collections"].split((NAMESPACE + "begin: [ok]\n").encode())
        self.assertEqual(before, expected)
        self.assertTrue(appendix)
        self.assertNotEqual(self.outputs["collections"], expected)

    def test_all_1246_labels_present_once_without_extra_probe_labels(self):
        actual = re.findall(r"^(target-map-family\.v1\.[^:\n]+): \[", self.text, re.MULTILINE)
        expected = {NAMESPACE + "begin", NAMESPACE + "complete"}
        expected.update(label for label, _ in mutation_labels())
        expected.update(label + ".cleared.empty" for label, _, _ in growth_cases())
        expected.update(label + "." + kind + ".payload" for label, _, _ in snapshots() for kind in KINDS)
        expected.update(label + ".summary" for label, _, _ in snapshots())
        self.assertEqual(len(expected), 1246)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(set(actual), expected)

    def test_every_mutation_reports_each_current_id_once_without_assuming_order(self):
        for label, expected in mutation_labels():
            with self.subTest(label=label):
                actual = extract_payload(self.text, label).split(",")
                self.assertEqual(len(actual), len(expected))
                self.assertEqual(set(actual), expected)
        for label, _, _ in growth_cases():
            self.assertEqual(extract_payload(self.text, label + ".cleared.empty"), '{"N",0}')

    def test_four_raw_streams_preserve_exact_typed_bindings_at_all_checkpoints(self):
        # Decode to inspect contents, but do NOT rewrite/order-compare raw streams.
        for label, number, size in snapshots():
            for kind in KINDS:
                with self.subTest(label=label, kind=kind):
                    payload = extract_payload(self.text, label + "." + kind + ".payload")
                    self.assertIn("\n", payload)  # Unflattened container stream.
                    restored = value_from_string_internal(payload)
                    expected_type = BSLMap if kind in ("map", "readback") else BSLFixedMap
                    self.assertIs(type(restored), expected_type)
                    pairs = list(restored)
                    self.assertEqual(len(pairs), size)
                    self.assertEqual({pair.value for pair in pairs}, expected_ids(size))
                    by_id = {pair.value: pair.key for pair in pairs}
                    for identifier, key in expected_keys(number, size):
                        self.assertIs(type(by_id[identifier]), type(key))
                        self.assertEqual(by_id[identifier], key)
                        self.assertEqual(restored.get(key), identifier)

    def test_summary_has_all_four_direct_sequences_counts_and_typed_checks(self):
        for label, _, size in snapshots():
            with self.subTest(label=label):
                sections = extract_payload(self.text, label + ".summary").split("|")
                self.assertEqual(len(sections), 4)
                for section, kind in zip(sections, KINDS):
                    prefix, sequence = section.split(";ids=")
                    self.assertEqual(prefix, kind + f';count={size};type={{"B",1}};lookup={{"B",1}};entries={{"B",1}}')
                    identifiers = sequence.split(",")
                    self.assertEqual(len(identifiers), size)
                    self.assertEqual(set(identifiers), expected_ids(size))


if __name__ == "__main__":
    unittest.main()
