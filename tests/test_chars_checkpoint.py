"""Bounded native-first Chars instrumentation, not predicted native semantics."""
import hashlib
from pathlib import Path
import unittest
import sys
import tempfile
from unittest.mock import patch

from scripts.native_historical_replay import (
    CHARS_PROBE_BLOCKS, HISTORICAL_VALUES_BLOB, HISTORICAL_VALUES_OUTPUT_BLOB,
    git_blob, historical_values_source, without_chars_probes,
)
from yadinassi import Interpreter, ast
from yadinassi.parser import parse, parse_expression

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
OUTPUT = ROOT / 'tests/fixtures/native_windows/values.out'
SOURCE_SHA256 = '5fd00b472332044f4bae4c12973bcc66c074b27f7c98fe58b21b149088166fff'


class CharsCheckpointTests(unittest.TestCase):
    def test_unique_blocks_source_binding_and_exact_original_reconstruction(self):
        raw = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA256)
        text = raw.decode()
        for start, end in CHARS_PROBE_BLOCKS:
            self.assertEqual(text.count(start), 1)
            self.assertEqual(text.count(end), 1)
        restored = historical_values_source(raw, OUTPUT.read_bytes())
        self.assertEqual(git_blob(restored), HISTORICAL_VALUES_BLOB)
        self.assertEqual(git_blob(OUTPUT.read_bytes().replace(b'\r\n', b'\n')),
                         HISTORICAL_VALUES_OUTPUT_BLOB)
        self.assertEqual(restored.decode(), without_chars_probes(text))
        self.assertNotIn('chars.', restored.decode())
        self.assertEqual(len(restored.splitlines()), 651)
        self.assertEqual(len(restored), 57351)

    def test_changed_original_source_output_or_boundaries_fail_closed(self):
        raw = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        output = OUTPUT.read_bytes()
        for changed in (raw + b'\n', raw.replace(b'NULL', b'Null', 1),
                        raw.replace(CHARS_PROBE_BLOCKS[0][0].encode(), b'', 1),
                        raw + CHARS_PROBE_BLOCKS[1][1].encode()):
            with self.subTest(source=changed[-80:]), self.assertRaises(ValueError):
                historical_values_source(changed, output)
        for changed in (output + b'\n', output[:-1], output.replace(b'null.', b'nulL.', 1)):
            with self.assertRaises(ValueError):
                historical_values_source(raw, changed)

    def test_all_helpers_precede_body_and_alias_matrix_is_bounded(self):
        statements = parse(SOURCE.read_text(encoding="utf-8"))
        started = False
        expressions = {}
        for node in statements:
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
            else:
                started = True
            if (isinstance(node, ast.ExpressionStatement)
                    and isinstance(node.expression, ast.Call)
                    and isinstance(node.expression.callee, ast.Name)
                    and node.expression.callee.name == 'НаблюдатьСимволы'):
                label, expression = [a.value for a in node.expression.arguments]
                self.assertNotIn(label, expressions)
                self.assertLess(len(expression), 100)
                self.assertNotRegex(expression, r'[\r\n]')
                parse_expression(expression)
                expressions[label] = expression
        self.assertEqual(len(expressions), 98)
        for member in ('cr', 'vtab', 'nbsp', 'lf', 'ff', 'tab'):
            for language in ('ru', 'en'):
                for operation in ('member', 'write'):
                    self.assertIn(f'{operation}.{member}.{language}', expressions)
            for language in ('ru', 'en'):
                for operation in ('read', 'case', 'write'):
                    self.assertIn(f'index.{operation}.{member}.{language}', expressions)
            for operation in ('alias', 'case', 'codec', 'xml'):
                self.assertIn(f'{operation}.{member}', expressions)

    def test_projection_format_is_safe_without_requiring_namespace_support(self):
        text = SOURCE.read_text(encoding="utf-8")
        helpers = text.split('// Значение, тип и настоящий прямой/обратный кодек.', 1)[0]
        output = []
        vm = Interpreter(output.append)
        vm.execute(helpers)
        for code in (9, 10, 11, 12, 13, 160):
            vm.execute(f'НаблюдатьСимволы("control-{code}", "ПроекцияСимвола(Символ({code}))");')
        self.assertEqual(len(output), 6)
        for line in output:
            self.assertIn('value=array(3)', line)
            self.assertTrue(all(ord(c) >= 32 for c in line))
        # Native serializers can return multiline array representations. The
        # selected compact formatter only serializes scalar numeric/Boolean leaves.
        self.assertIn('Запись = ПоляКомпактныхТипов(Результат, "value");', helpers)
        body = text.split(CHARS_PROBE_BLOCKS[1][0], 1)[1]
        for label in ('missing', 'call.member', 'call.namespace', 'index.string', 'index.number'):
            self.assertIn(f'НаблюдатьСимволы("{label}", "ПроекцияСимвола(', body)

    def test_all_original_observations_remain_mandatory_and_new_errors_are_isolated(self):
        raw = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        original, current = [], []
        Interpreter(original.append).execute(historical_values_source(raw, OUTPUT.read_bytes()).decode())
        Interpreter(current.append).execute(raw.decode())
        self.assertEqual(len(original), 261)
        self.assertEqual(len(current), 361)
        # Instrumentation only. Native CI separately compares every current record.
        self.assertEqual(current[:261], original)
        self.assertEqual(current[319], 'chars.checkpoint.complete: [ok]')
        self.assertEqual(current[-1], 'chars.index.checkpoint.complete: [ok]')
        # Removing only the supplemental helper/observations restores the exact
        # native-verified 320-record source, not an interpreter-derived oracle.
        baseline = raw.decode()
        for start, end in (('// Begin Chars indexed write helper.\n',
                            '// End Chars indexed write helper.\n'),
                           ('// Begin Chars index supplement.\n',
                            '// End Chars index supplement.\n')):
            self.assertEqual(baseline.count(start), 1)
            self.assertEqual(baseline.count(end), 1)
            a, b = baseline.index(start), baseline.index(end) + len(end)
            baseline = baseline[:a] + baseline[b:]
        self.assertEqual(hashlib.sha256(baseline.encode()).hexdigest(),
                         '09277b567be373c16772a7b7c2b2d9372873c655f54b59874da533b32f6d1622')
        previous = []
        Interpreter(previous.append).execute(baseline)
        self.assertEqual(len(previous), 320)
        self.assertEqual(current[:320], previous)
        self.assertTrue(all(x.startswith('chars.') for x in current[261:]))
        self.assertTrue(all(not any(ord(c) < 32 for c in x) for x in current[261:]))


    def test_checkpoint_with_crlf_checkout_and_non_utf8_default_encoding(self):
        source_bytes = SOURCE.read_bytes().replace(b'\r\n', b'\n')
        output_bytes = OUTPUT.read_bytes().replace(b'\r\n', b'\n')
        read_text = Path.read_text
        def windows_default(path, *args, **kwargs):
            if not args and 'encoding' not in kwargs:
                kwargs['encoding'] = 'cp1252'
            return read_text(path, *args, **kwargs)
        methods = [name for name in unittest.defaultTestLoader.getTestCaseNames(CharsCheckpointTests)
                   if name != self._testMethodName]
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'values.bsl', Path(directory) / 'values.out'
            source.write_bytes(source_bytes.replace(b'\n', b'\r\n'))
            output.write_bytes(output_bytes.replace(b'\n', b'\r\n'))
            with patch.object(sys.modules[__name__], 'SOURCE', source), \
                    patch.object(sys.modules[__name__], 'OUTPUT', output), \
                    patch.object(Path, 'read_text', windows_default):
                result = unittest.TestResult()
                unittest.TestSuite(CharsCheckpointTests(name) for name in methods).run(result)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.failures, [])


if __name__ == '__main__':
    unittest.main()
