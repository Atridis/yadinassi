"""Source-only missing EXCLUDE names: synthetic policies are not native evidence."""
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.native_historical_replay import (
    FILL_EXCLUDE_PROBE_BLOCKS, without_fill_exclude_probes,
    without_fill_exclude_order_probes,
)
from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, current_native_target

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_SHA = 'fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9'
BASE_SHA = 'e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232'
CASES = tuple((variant + '.' + label, variant, value)
              for variant in ('target-only', 'source-only', 'neither')
              for label, value in (('missing', 'Missing'), ('missing-first', 'Missing,First'),
                                   ('first-missing', 'First,Missing'))) + (
    ('control.first', 'neither', 'First'), ('control.first-last', 'neither', 'First,Last'))

class FillExcludeCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        # Keep the original 11-case matrix and observer unchanged. The two later
        # source-order probes have their own tests and are removed byte-exactly.
        cls.source = without_fill_exclude_order_probes(current)
        cls.original = without_fill_exclude_probes(cls.source)
        cls.helper = cls.source.split(FILL_EXCLUDE_PROBE_BLOCKS[0][0])[1].split(FILL_EXCLUDE_PROBE_BLOCKS[0][1])[0]
        cls.body = cls.source.split(FILL_EXCLUDE_PROBE_BLOCKS[1][0])[1].split(FILL_EXCLUDE_PROBE_BLOCKS[1][1])[0]

    def test_exact_841_inverse_and_rejection_of_source_drift(self):
        self.assertEqual(hashlib.sha256(self.source.encode('utf-8-sig')).hexdigest(), CHECKPOINT_SHA)
        for text in (self.source, self.source.replace('\n', '\r\n').replace('\r\n', '\n')):
            self.assertEqual(hashlib.sha256(without_fill_exclude_probes(text).encode('utf-8-sig')).hexdigest(), BASE_SHA)
        for text in ('\ufeff\ufeff' + self.source, self.source + '\n', self.source.replace('array.shift', 'array.changed', 1),
                     self.source.replace(FILL_EXCLUDE_PROBE_BLOCKS[0][1], '// changed\n', 1),
                     self.source + FILL_EXCLUDE_PROBE_BLOCKS[1][0]):
            with self.assertRaises(ValueError):
                without_fill_exclude_probes(text)

    def test_exact_matrix_and_fresh_mutable_composition(self):
        self.assertEqual(self.body, ''.join(f'ПроверитьСписокИсключения("{label}", "{variant}", "{value}");\n'
                                          for label, variant, value in CASES))
        for setup in ('Приемник = Новый Структура("First,Last,Copy", 1, 2, 3);',
                      'Источник = Новый Структура("First,Last,Copy", 10, 20, 30);',
                      'Приемник.Вставить("Missing", 4);', 'Источник.Вставить("Missing", 40);'):
            self.assertIn(setup, self.helper)
        self.assertEqual(self.helper.count('FillPropertyValues('), 1)
        self.assertIn('FillPropertyValues(Приемник, Источник, Неопределено, Список);', self.helper)
        after = self.helper.split('КонецПопытки;')[1]
        for item in ('Приемник.First', 'Приемник.Last', 'Приемник.Copy', 'Приемник.Количество()', 'ЕстьMissing', 'ЗначениеMissing'):
            self.assertIn(f'ЗначениеВСтрокуВнутр({item})', after)
        self.assertIn('Приемник.Свойство("Missing", ЗначениеMissing)', after)
        for excluded in ('ОписаниеОшибки', 'Фиксированная', 'Запрос', '\t', 'Удалить', 'СокрЛП'):
            self.assertNotIn(excluded, self.helper + self.body)

    def test_full_current_source_preserves_every_old_record_for_both_targets(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            old, new = [], []
            Interpreter(old.append, native_target=target).execute(self.original)
            Interpreter(new.append, native_target=target).execute(self.source)
            self.assertEqual(len(old), 841)
            self.assertEqual(len(new), 852)
            self.assertEqual(new[:841], old)
            self.assertEqual([row.split(':', 1)[0] for row in new[841:]],
                             ['fill.exclude-missing.' + label for label, _, _ in CASES])
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
        self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)

    def test_observer_distinguishes_ignored_names_and_partial_failure(self):
        # Competing synthetic policies test observation power, not 1C semantics.
        def ignored(target, source, include, exclude):
            self.assertIsNone(include)
            for key, (name, value) in tuple(target._items.items()):
                if key in source._items and name not in exclude.split(','):
                    target._items[key] = name, source._items[key][1]
        def partial(target, source, include, exclude):
            self.assertIsNone(include)
            name, value = source._items['copy']
            target._items['copy'] = name, value
            raise ValueError('synthetic failure')
        # Execute only the real new helper and original presentation helper.
        presentation = 'Процедура Показать(Знач Метка, Знач Значение)\nСообщить(Метка + ": [" + Значение + "]");\nКонецПроцедуры\n'
        source = presentation + self.helper + self.body
        results = []
        for policy in (ignored, partial):
            rows = []
            with patch('yadinassi.runtime.fill_property_values', policy):
                Interpreter(rows.append).execute(source)
            self.assertEqual(len(rows), 11)
            results.append(rows)
        self.assertIn('[ok;{"N",10};{"N",20};{"N",30}', results[0][0])
        self.assertIn('[error;{"N",1};{"N",2};{"N",30}', results[1][0])
        self.assertNotEqual(*results)

if __name__ == '__main__':
    unittest.main()
