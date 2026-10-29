"""One fresh-VM replay per exact historical source/target, not cached output.

Synthetic interpreter predictions remain separate from native fixture oracles.
"""
from pathlib import Path
import unittest

from scripts.native_historical_replay import (
    without_fill_include_probes, without_fill_exclude_probes,
    without_fill_exclude_order_probes,
)
from yadinassi import Interpreter
from yadinassi.native_targets import (
    WINDOWS_8_3_27_2342, LINUX_8_3_27_1508, current_native_target,
)
from test_fill_include_checkpoint import CASES as INCLUDE_CASES
from test_fill_exclude_checkpoint import CASES as EXCLUDE_CASES
from test_fill_exclude_order_checkpoint import LABELS, LAST_LABEL

ROOT = Path(__file__).resolve().parents[1]


class FillHistoricalReplayMatrixTests(unittest.TestCase):
    def test_exact_historical_sources_preserve_all_records_on_both_targets(self):
        current = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        checkpoint = without_fill_exclude_order_probes(current)
        base = without_fill_exclude_probes(checkpoint)
        original = without_fill_include_probes(base)
        results = {}
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            outputs = []
            for text, count in ((original, 828), (base, 841), (checkpoint, 852), (current, 1023)):
                with self.subTest(target=target, records=count):
                    rows = []
                    Interpreter(rows.append, native_target=target).execute(text)
                    self.assertEqual(len(rows), count)
                    outputs.append(rows)
            old, new = outputs[:2]
            self.assertEqual(len(old), 828)
            self.assertEqual(new[:828], old)
            self.assertEqual(len(new), 841)
            self.assertEqual([row.split(':', 1)[0] for row in new[828:]],
                             ['fill.include-normalization.' + name for name, _ in INCLUDE_CASES])
            for row in new[828:]:
                self.assertRegex(row, r': \[(ok|error);\{"N",(?:1|10)\};\{"N",(?:2|20)\}\]$')
            results[target] = new[828:]
            old, new = outputs[1:3]
            self.assertEqual(len(old), 841)
            self.assertEqual(len(new), 852)
            self.assertEqual(new[:841], old)
            self.assertEqual([row.split(':', 1)[0] for row in new[841:]],
                             ['fill.exclude-missing.' + label for label, _, _ in EXCLUDE_CASES])
            # Linux source-only states are measured in runs39836204865 and
            # 40048537592. Windows/default retain their earlier upfront guard;
            # the separate runtime fixture binds all thirteen native records.
            for index, row in enumerate(new[841:850]):
                presence = '{"B",1};{"N",4}' if index < 3 else '{"B",0};{"U"}'
                count = 4 if index < 3 else 3
                first, last, copied = 1, 2, 3
                if target == LINUX_8_3_27_1508 and 3 <= index < 6:
                    first, last, copied = (10 if index == 3 else 1), 20, 30
                self.assertTrue(row.endswith(f'[error;{{"N",{first}}};{{"N",{last}}};{{"N",{copied}}};{{"N",{count}}};{presence}]'), row)
            self.assertTrue(new[-2].endswith('[ok;{"N",1};{"N",20};{"N",30};{"N",3};{"B",0};{"U"}]'))
            self.assertTrue(new[-1].endswith('[ok;{"N",1};{"N",2};{"N",30};{"N",3};{"B",0};{"U"}]'))
            outputs = outputs[1:]
            self.assertEqual(outputs[1][:841], outputs[0])
            self.assertEqual(outputs[2][:841], outputs[0])
            self.assertEqual(outputs[2][:852], outputs[1])
            self.assertEqual(outputs[2][844].split(':', 1)[0], LAST_LABEL)
            self.assertEqual(tuple(row.split(':', 1)[0] for row in outputs[2][852:854]), LABELS)
            # Shape only here. The separate runtime tests bind these states
            # to the independently audited native run40048537592 fixture.
            for row in outputs[2][852:854]:
                self.assertRegex(row, r': \[(?:ok|error);\{"N",-?\d+\};\{"N",-?\d+\};'
                                      r'\{"N",-?\d+\};\{"N",\d+\};\{"B",[01]\};'
                                      r'(?:\{"U"\}|\{"N",-?\d+\})\]$')
        # Existing behavior only. Neither target's predictions are new native evidence.
        self.assertIn('error;{"N",10};{"N",2}', results[WINDOWS_8_3_27_2342][10])
        self.assertIn('error;{"N",1};{"N",20}', results[LINUX_8_3_27_1508][10])
        self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)


if __name__ == '__main__':
    unittest.main()
