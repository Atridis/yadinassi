"""Exact complete replay of audited PR88 native exception observations."""
import hashlib
import json
from pathlib import Path
import unittest

from yadinassi import Interpreter
from scripts.native_historical_replay import without_exported_variable_probes


ROOT = Path(__file__).resolve().parents[1]


class NativeExtendedExceptionTests(unittest.TestCase):
    def test_all_116_native_records_are_source_bound_and_exact(self):
        fixture = json.loads((ROOT / 'tests/fixtures/extended_exceptions_linux.json').read_text(encoding='utf-8'))
        source = (ROOT / 'integrational_tests/tests/functions.bsl').read_bytes()
        # Checkout EOL transport is not a semantic output normalization.
        source = without_exported_variable_probes(
            source.replace(b'\r\n', b'\n').decode('utf-8')).encode('utf-8')
        historical = (ROOT / 'tests/fixtures/native_windows/functions.out').read_bytes()
        historical = historical.replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(source).hexdigest(), fixture['source_sha256'])
        self.assertEqual(hashlib.sha256(historical).hexdigest(), fixture['historical_output_sha256'])
        self.assertEqual(len(historical.splitlines()), fixture['historical_records'])
        self.assertEqual(len(fixture['records']), 28)
        expected = historical + ('\n'.join(fixture['records']) + '\n').encode('utf-8')
        self.assertEqual(hashlib.sha256(expected).hexdigest(), fixture['complete_output_sha256'])
        output = []
        Interpreter(output.append, native_target=fixture['native_target']).execute(source.decode('utf-8'))
        actual = ('\n'.join(output) + '\n').encode('utf-8')
        self.assertEqual(len(output), fixture['total_records'])
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
