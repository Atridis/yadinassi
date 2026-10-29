"""Source-only INCLUDE matrix: local predictions never substitute native evidence."""
import hashlib
from pathlib import Path
import unittest

from scripts.native_historical_replay import without_fill_exclude_probes, without_fill_include_probes, FILL_INCLUDE_PROBE_BLOCKS

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'b3bf181de84a575335ce7e4794ced459ad252eb7853cc42095fb62521dc6a409'
CASES = (
    ('control', 'First,Last'), ('empty', ''), ('space', ' '), ('comma', ','),
    ('leading-empty', ',First,Last'), ('middle-empty', 'First,,Last'),
    ('trailing-empty', 'First,Last,'), ('leading-space', ' First,Last'),
    ('before-comma-space', 'First ,Last'), ('around-last-space', 'First, Last '),
    ('missing', 'First,Missing,Last'), ('spaced-missing', 'First, Missing ,Last'),
    ('middle-space', 'First, ,Last'),
)

class FillIncludeCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = without_fill_exclude_probes((ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig'))
        cls.original = without_fill_include_probes(cls.source)

    def test_exact_828_source_inverse_and_transport_only_normalization(self):
        for raw in (self.source.encode('utf-8-sig'), self.source.replace('\n', '\r\n').encode('utf-8-sig')):
            restored = without_fill_include_probes(raw.decode('utf-8-sig').replace('\r\n', '\n'))
            self.assertEqual(hashlib.sha256(restored.encode('utf-8-sig')).hexdigest(), BASE_SHA)
        for mutant in ('\ufeff\ufeff' + self.source, self.source + '\n', self.source.replace('array.shift', 'array.changed', 1),
                       self.source.replace(FILL_INCLUDE_PROBE_BLOCKS[0][1], '// changed\n', 1),
                       self.source + FILL_INCLUDE_PROBE_BLOCKS[1][0]):
            with self.assertRaises(ValueError):
                without_fill_include_probes(mutant)

    def test_exact_bounded_matrix_and_fresh_mutable_setup(self):
        helper = self.source.split(FILL_INCLUDE_PROBE_BLOCKS[0][0])[1].split(FILL_INCLUDE_PROBE_BLOCKS[0][1])[0]
        body = self.source.split(FILL_INCLUDE_PROBE_BLOCKS[1][0])[1].split(FILL_INCLUDE_PROBE_BLOCKS[1][1])[0]
        self.assertEqual(body, ''.join(f'ПроверитьСписокВключения("{name}", "{value}");\n' for name, value in CASES))
        self.assertIn('Приемник = Новый Структура("First,Last", 1, 2);', helper)
        self.assertIn('Источник = Новый Структура("First,Last", 10, 20);', helper)
        self.assertEqual(helper.count('FillPropertyValues('), 1)
        self.assertIn('FillPropertyValues(Приемник, Источник, Список);', helper)
        after = helper.split('КонецПопытки;')[1]
        for field in ('First', 'Last'):
            self.assertIn(f'ЗначениеВСтрокуВнутр(Приемник.{field})', after)
        self.assertNotIn('ОписаниеОшибки', helper)  # Stable class, not localized prose.
        for excluded in ('Фиксированная', 'Запрос', '\t', 'Удалить', 'СокрЛП'):
            self.assertNotIn(excluded, helper + body)


if __name__ == '__main__':
    unittest.main()
