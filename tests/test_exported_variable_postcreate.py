"""Source-only post-Create probes; local execution is not native evidence."""
import hashlib
from pathlib import Path
import re
import tempfile
import unittest

from scripts.native_historical_replay import (
    EXPORTED_POSTCREATE_DIRECTIVE, EXPORTED_POSTCREATE_BASE_BLOB,
    EXPORTED_POSTCREATE_BASE_SHA256, EXPORTED_POSTCREATE_PROBE_BLOCKS,
    EXPORTED_CONTEXT_BASE_BLOB, EXPORTED_VARIABLE_BASE_BLOB,
    HISTORICAL_FUNCTIONS_BLOB, git_blob, without_exported_postcreate_probes,
    without_exported_context_probes, without_exported_variable_probes,
    without_extended_exception_probes, without_trailing_omitted_probes,
)
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from yadinassi.native_targets import WINDOWS_8_3_27_2342, LINUX_8_3_27_1508

ROOT = Path(__file__).resolve().parents[1]


def checkout_source(path):
    # Git may check text out with CRLF. Bind the canonical source, not its
    # checkout transport; preserve every byte other than CRLF pairs.
    return path.read_bytes().replace(b'\r\n', b'\n')


class ExportedPostCreateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = without_trailing_omitted_probes(checkout_source(
            ROOT / 'integrational_tests/tests/functions.bsl').decode('utf-8')).encode('utf-8')
        cls.source = cls.raw.decode('utf-8')
        cls.previous = without_exported_postcreate_probes(cls.source)

    def test_real_checkout_lf_crlf_read_path_keeps_exact_source_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'functions.bsl'
            for ending in (b'\n', b'\r\n'):
                transported = self.raw.replace(b'\n', ending)
                if ending == b'\r\n':
                    self.assertNotEqual(transported, self.raw)
                    self.assertIn(b'\r\n', transported)
                path.write_bytes(transported)
                self.assertEqual(path.read_bytes(), transported)
                canonical = checkout_source(path)
                self.assertEqual(canonical, self.raw)
                self.assertEqual(without_exported_postcreate_probes(canonical.decode()), self.previous)
                path.write_bytes(transported + b'\r')
                self.assertNotEqual(checkout_source(path), canonical)
                with self.assertRaises(ValueError):
                    without_exported_postcreate_probes(checkout_source(path).decode())

    def test_exact_full136_inverse_and_historical_chain(self):
        self.assertTrue(self.raw.startswith(EXPORTED_POSTCREATE_DIRECTIVE.encode()))
        self.assertNotIn(b'\r', self.raw)
        raw = self.previous.encode()
        self.assertEqual(git_blob(raw), EXPORTED_POSTCREATE_BASE_BLOB)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPORTED_POSTCREATE_BASE_SHA256)
        self.assertEqual(EXPORTED_POSTCREATE_BASE_SHA256,
                         'c6b33e07818ce7e4abd8153feb3d8538d48737d5a543312b18f1fb8e7c5a65cd')
        for inverse, blob in ((without_exported_context_probes, EXPORTED_CONTEXT_BASE_BLOB),
                              (without_exported_variable_probes, EXPORTED_VARIABLE_BASE_BLOB),
                              (without_extended_exception_probes, HISTORICAL_FUNCTIONS_BLOB)):
            self.assertEqual(inverse(self.source), inverse(self.previous))
            self.assertEqual(git_blob(inverse(self.source).encode()), blob)

    def test_actual_lf_crlf_transport_and_mutations(self):
        for ending in ('\n', '\r\n'):
            transported = self.source.replace('\n', ending)
            if ending == '\r\n':
                self.assertIn('\r\n', transported)
            normalize = lambda text: text.replace('\r\n', '\n')
            self.assertEqual(without_exported_postcreate_probes(normalize(transported)), self.previous)
            mutants = [transported + ending,
                       transported.replace('МодульноеВычисления', 'ChangedVariable', 1),
                       transported.replace('NativePostCreate:', 'NativePostCreate :', 1),
                       ending + transported,
                       transported + EXPORTED_POSTCREATE_DIRECTIVE.replace('\n', ending)]
            for start, end in EXPORTED_POSTCREATE_PROBE_BLOCKS:
                for boundary in (start, end):
                    actual = boundary.replace('\n', ending)
                    mutants.extend((transported.replace(actual, '', 1), transported + actual))
            for mutant in mutants:
                self.assertNotEqual(mutant, transported)
                with self.assertRaises(ValueError):
                    without_exported_postcreate_probes(normalize(mutant))

    def test_eighteen_guarded_observations_use_actual_passed_receiver(self):
        start, end = EXPORTED_POSTCREATE_PROBE_BLOCKS[1]
        helper = self.source.split(start)[1].split(end)[0]
        self.assertTrue(helper.startswith('Procedure ExportProbeAfterCreate(Val PublicObject) Export\n'))
        self.assertIn('    ExportProbePublicObject = PublicObject;\n', helper)
        original = re.findall(r'^ObserveExportProbe\("([^\"]+)", "(.*)"\);$', self.previous, re.M)
        actual = re.findall(r'^    ObserveExportProbe\("([^\"]+)", "(.*)"\);$', helper, re.M)
        self.assertEqual(len(original), 15)
        self.assertEqual(len(actual), 18)
        for (label, code), (new_label, new_code) in zip(original, actual):
            self.assertEqual(new_label, 'post-create.' + label)
            self.assertEqual(new_code, code.replace('ThisObject', 'ExportProbePublicObject')
                             .replace('ЭтотОбъект', 'ExportProbePublicObject'))
        self.assertEqual(actual[15:], [
            ('post-create.receiver-identity', 'Result = ExportProbePublicObject = ThisObject;'),
            ('post-create.self-read', 'Result = ThisObject.ExportProbeValue;'),
            ('post-create.self-write', 'ThisObject.ExportProbeValue = 61; Result = ExportProbePublicObject.ExportProbeValue;'),
        ])
        start, end = EXPORTED_POSTCREATE_PROBE_BLOCKS[0]
        self.assertEqual(self.source.split(start)[1].split(end)[0], 'Var ExportProbePublicObject;\n')

    def test_static_declarations_precede_helpers_and_body(self):
        started_body = started_helpers = False
        for node in parse(self.source):
            if isinstance(node, ast.Var):
                self.assertFalse(started_helpers or started_body)
            elif isinstance(node, ast.Routine):
                self.assertFalse(started_body)
                started_helpers = True
            else:
                started_body = True
        self.assertEqual(self.source.count('ExportProbeAfterCreate('), 1)

    def test_full_source_does_not_invoke_entrypoint_in_module_body(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            previous, current = [], []
            Interpreter(previous.append, native_target=target).execute(self.previous)
            Interpreter(current.append, native_target=target).execute(self.source)
            self.assertEqual(len(current), 136)
            self.assertEqual(current, previous)
            self.assertFalse(any('post-create.' in row for row in current))
        # Module execution alone never invokes the explicit post-Create entrypoint.
        # The separate protocol tests exercise that second phase.


if __name__ == '__main__':
    unittest.main()
