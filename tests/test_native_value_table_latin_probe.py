"""Check the new capture's framing/data locally, not native collation."""
from contextlib import closing, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest

from yadinassi import Interpreter

_SOURCE = Path(__file__).resolve().parents[1] / 'integrational_tests/manual_probes/value_table_latin_sort.bsl'
_PREFIX = 'value-table.latin-sort.v1'
_KEYS = ('ß', 'Á', ' ', 'ą', 'A', 'ñ', 'a\u0301', 'ä', 'c', 'a ', 'â', 'a-',
         'ł', 'à', 'a', 'á', 'ã', 'č', '-', 'a\u0308', 'å', 'l', 'n', 'ss', 'ö', 'ü')


class NativeValueTableLatinProbeTests(unittest.TestCase):
    def test_capture_preserves_exact_unicode_keys_and_row_identity(self):
        output = StringIO()
        with closing(Interpreter()) as vm, redirect_stdout(output):
            vm.execute(_SOURCE.read_text(encoding='utf-8'))
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[-1], f'{_PREFIX}|complete')
        expected = list(enumerate(_KEYS, 1))
        actual_ids = []
        labels = ('input', 'asc', 'desc', 'asc-id-asc', 'asc-id-desc')
        self.assertEqual(len(lines), len(labels) + 1)
        for label, line in zip(labels, lines):
            with self.subTest(order=label):
                prefix, actual_label, *pairs, marker = line.split('|')
                self.assertEqual((prefix, actual_label, marker), (_PREFIX, label, 'same-rows'))
                decoded = []
                for pair in pairs:
                    identifier, codes = pair.split(':')
                    decoded.append((int(identifier), ''.join(chr(int(code)) for code in codes.split('+'))))
                self.assertCountEqual(decoded, expected)
                if label == 'input':
                    self.assertEqual(decoded, expected)
                actual_ids.append([identifier for identifier, _ in decoded])
        self.assertNotEqual(actual_ids[1], actual_ids[0])
        self.assertNotEqual(actual_ids[1], actual_ids[2])
