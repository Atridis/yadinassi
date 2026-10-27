"""EXCLUDE source-order measurement: synthetic/local output is not native evidence."""
import hashlib
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from scripts.native_historical_replay import (
    FILL_EXCLUDE_PROBE_BLOCKS,
    FILL_EXCLUDE_ORDER_PROBE_BLOCKS,
    without_fill_exclude_probes,
    without_fill_exclude_order_probes,
)
from yadinassi import Interpreter
from yadinassi.native_targets import (
    LINUX_8_3_27_1508, WINDOWS_8_3_27_2342, current_native_target,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = 'e877033fbe8cd8d113aec6b77892f1bb737db9b465b13ad1c4f5786ae4e50232'
CHECKPOINT_SHA = 'fef5af9c34d3af7ae73e427ac1e846c539246530aa9bcd5858932fc397754ed9'
SOURCE_SHA = 'bae7fc1e006a68f9fba17800e5332d68bbcb028996e7f9b29d45ecf4b4759ada'
POSITIONS = ('first', 'between')
LABELS = tuple('fill.exclude-source-order.source-only.' + value for value in POSITIONS)
LAST_LABEL = 'fill.exclude-missing.source-only.missing'
LOCALS = ('Приемник', 'Источник', 'Статус', 'ЗначениеMissing', 'ЕстьMissing')
PRESENTATION = ('Процедура Показать(Знач Метка, Знач Значение)\n'
                'Сообщить(Метка + ": [" + Значение + "]");\nКонецПроцедуры\n')


def block(text, markers):
    start, end = markers
    return text.split(start, 1)[1].split(end, 1)[0]


def source_sha(text):
    return hashlib.sha256(text.encode('utf-8-sig')).hexdigest()


class FillExcludeOrderCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes()
        cls.source = cls.raw.decode('utf-8-sig').replace('\r\n', '\n')
        cls.checkpoint = without_fill_exclude_order_probes(cls.source)
        cls.base = without_fill_exclude_probes(cls.source)
        cls.helper = block(cls.source, FILL_EXCLUDE_ORDER_PROBE_BLOCKS[0])
        cls.body = block(cls.source, FILL_EXCLUDE_ORDER_PROBE_BLOCKS[1])
        cls.old_helper = block(cls.source, FILL_EXCLUDE_PROBE_BLOCKS[0])

    def test_exact_source_and_nested_historical_inverses(self):
        # Explicit checkout transport normalization only, never BSL/data cleanup.
        self.assertEqual(hashlib.sha256(self.raw.replace(b'\r\n', b'\n')).hexdigest(), SOURCE_SHA)
        self.assertEqual(source_sha(self.source), SOURCE_SHA)
        for raw in (self.source.encode('utf-8-sig'),
                    self.source.replace('\n', '\r\n').encode('utf-8-sig')):
            with self.subTest(crlf=b'\r\n' in raw):
                text = raw.decode('utf-8-sig').replace('\r\n', '\n')
                checkpoint = without_fill_exclude_order_probes(text)
                self.assertEqual(source_sha(checkpoint), CHECKPOINT_SHA)
                self.assertEqual(source_sha(without_fill_exclude_probes(text)), BASE_SHA)
                self.assertEqual(without_fill_exclude_probes(checkpoint), self.base)
        # Every byte of both original blocks is retained, not regenerated.
        for markers in FILL_EXCLUDE_PROBE_BLOCKS:
            self.assertEqual(block(self.source, markers), block(self.checkpoint, markers))

    def test_inverses_reject_missing_duplicate_and_reordered_boundaries(self):
        for markers in FILL_EXCLUDE_ORDER_PROBE_BLOCKS:
            start, end = markers
            mutants = (
                self.source.replace(start, '', 1),
                self.source.replace(end, '', 1),
                self.source.replace(start, start + start, 1),
                self.source.replace(end, end + end, 1),
                self.source.replace(start + block(self.source, markers) + end, '', 1),
            )
            # Swap without a placeholder present in the source.
            before, rest = self.source.split(start, 1)
            body, after = rest.split(end, 1)
            mutants += (before + end + body + start + after,)
            for index, mutant in enumerate(mutants):
                self.assertNotEqual(mutant, self.source)
                for inverse in (without_fill_exclude_order_probes, without_fill_exclude_probes):
                    with self.subTest(marker=start, mutation=index, inverse=inverse.__name__):
                        with self.assertRaises(ValueError):
                            inverse(mutant)

    def test_inverses_reject_helper_body_and_unrelated_source_drift(self):
        replacements = (
            ('"Missing,First,Last,Copy", 40, 10, 20, 30', '"First,Missing,Last,Copy", 10, 40, 20, 30'),
            ('"First,Missing,Last,Copy", 10, 40, 20, 30', '"First,Last,Missing,Copy", 10, 20, 40, 30'),
            ('Перем Приемник, Источник, Статус, ЗначениеMissing, ЕстьMissing;',
             'Перем Приемник, Источник, Статус, ЗначениеMissing;'),
            ('FillPropertyValues(Приемник, Источник, Неопределено, "Missing");',
             'FillPropertyValues(Приемник, Источник, Неопределено, "Missing,First");'),
            ('ЗначениеВСтрокуВнутр(Приемник.Copy)', 'ЗначениеВСтрокуВнутр(Приемник.First)'),
        )
        mutants = []
        for old, new in replacements:
            self.assertIn(old, self.helper)
            mutants.append(self.source.replace(self.helper, self.helper.replace(old, new, 1), 1))
        mutants += [
            self.source.replace(self.body, self.body.replace('"first"', '"last"', 1), 1),
            self.source.replace(self.body, ''.join(reversed(self.body.splitlines(keepends=True))), 1),
            self.source.replace('array.shift', 'array.changed', 1),
            '\ufeff\ufeff' + self.source,
            self.source + '\n',
            self.source + ' ',
            self.source.replace('\n', '\r', 1),
        ]
        for index, mutant in enumerate(mutants):
            self.assertNotEqual(mutant, self.source)
            for inverse in (without_fill_exclude_order_probes, without_fill_exclude_probes):
                with self.subTest(mutation=index, inverse=inverse.__name__):
                    with self.assertRaises(ValueError):
                        inverse(mutant)

    def test_exact_two_case_matrix_explicit_locals_and_caught_observer_shape(self):
        self.assertEqual(self.body, ''.join(f'ПроверитьПозициюИсключения("{position}");\n'
                                           for position in POSITIONS))
        declarations = re.findall(r'^\s*Перем ([^;]+);$', self.helper, re.MULTILINE)
        self.assertEqual(declarations, [', '.join(LOCALS)])
        self.assertIn('Приемник = Новый Структура("First,Last,Copy", 1, 2, 3);', self.helper)
        self.assertIn('Источник = Новый Структура("Missing,First,Last,Copy", 40, 10, 20, 30);', self.helper)
        self.assertIn('Источник = Новый Структура("First,Missing,Last,Copy", 10, 40, 20, 30);', self.helper)
        self.assertEqual(self.helper.count('Новый Структура('), 3)
        self.assertEqual(self.helper.count('FillPropertyValues('), 1)
        attempt = self.helper.split('    Попытка\n', 1)[1].split('    Исключение\n', 1)[0]
        self.assertEqual(attempt,
                         '        FillPropertyValues(Приемник, Источник, Неопределено, "Missing");\n')
        after = self.helper.split('    КонецПопытки;\n', 1)[1]
        self.assertIn('ЗначениеMissing = Неопределено;\n', after)
        self.assertIn('ЕстьMissing = Приемник.Свойство("Missing", ЗначениеMissing);', after)
        self.assertEqual(re.findall(r'ЗначениеВСтрокуВнутр\(([^)]+)\)', after),
                         ['Приемник.First', 'Приемник.Last', 'Приемник.Copy',
                          'Приемник.Количество(', 'ЕстьMissing', 'ЗначениеMissing'])
        self.assertIn('Показать("fill.exclude-source-order.source-only." + Позиция, Статус', after)
        for excluded in ('ОписаниеОшибки', 'Фиксированная', 'Запрос', '\t', 'Удалить', 'СокрЛП'):
            self.assertNotIn(excluded, self.helper + self.body)
        # The old last-position case is reused, not duplicated as a new probe.
        self.assertIn('Источник.Вставить("Missing", 40);', self.old_helper)
        self.assertNotIn('ПроверитьПозициюИсключения("last")', self.source)

    def test_each_invocation_constructs_fresh_structures_and_keeps_outer_locals(self):
        retained = []
        expected_orders = (
            ('missing', 'first', 'last', 'copy'),
            ('first', 'missing', 'last', 'copy'),
            ('missing', 'first', 'last', 'copy'),
        )

        def observe_and_mutate(target, source, include, exclude):
            self.assertIsNone(include)
            self.assertEqual(exclude, 'Missing')
            self.assertEqual(tuple(source._items), expected_orders[len(retained)])
            self.assertEqual([value for _, value in target._items.values()], [1, 2, 3])
            self.assertEqual({key: value for key, (_, value) in source._items.items()},
                             {'first': 10, 'last': 20, 'copy': 30, 'missing': 40})
            for previous in retained:
                self.assertIsNot(target, previous[0])
                self.assertIsNot(source, previous[1])
            retained.append((target, source))
            target._items['copy'] = ('Copy', target._items['copy'][1] * 100)
            source._items['copy'] = ('Copy', source._items['copy'][1] * 100)
            raise ValueError('synthetic failure after mutation')

        outer = ''.join(f'{name} = "outer-{index}";\n' for index, name in enumerate(LOCALS))
        observer = ''.join(f'Сообщить({name});\n' for name in LOCALS)
        probe = PRESENTATION + self.helper + outer + self.body + 'ПроверитьПозициюИсключения("first");\n' + observer
        rows = []
        with patch('yadinassi.runtime.fill_property_values', observe_and_mutate):
            Interpreter(rows.append).execute(probe)
        self.assertEqual(len(retained), 3)
        self.assertEqual(rows[-5:], [f'outer-{index}' for index in range(5)])
        for row in rows[:3]:
            self.assertTrue(row.endswith('[error;{"N",1};{"N",2};{"N",300};{"N",3};{"B",0};{"U"}]'), row)

    def test_full_841_and_852_prefixes_survive_on_both_interpreter_targets(self):
        for target in (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508):
            with self.subTest(target=target):
                outputs = []
                for text, count in ((self.base, 841), (self.checkpoint, 852), (self.source, 973)):
                    rows = []
                    Interpreter(rows.append, native_target=target).execute(text)
                    self.assertEqual(len(rows), count)
                    outputs.append(rows)
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
        self.assertEqual(current_native_target(), WINDOWS_8_3_27_2342)

    def test_three_synthetic_policies_are_distinguished_without_native_expectations(self):
        # Deliberately synthetic alternatives, not assertions about 1C's internals.
        def upfront_validation(target, source, include, exclude):
            self.assertIsNone(include)
            self.assertEqual(exclude, 'Missing')
            raise ValueError('synthetic missing target property')

        def copy_then_validate(target, source, include, exclude):
            self.assertIsNone(include)
            self.assertEqual(exclude, 'Missing')
            for key, (name, _) in tuple(target._items.items()):
                if key in source._items:
                    target._items[key] = name, source._items[key][1]
            raise ValueError('synthetic missing target property')

        def source_insertion_order_traversal(target, source, include, exclude):
            self.assertIsNone(include)
            self.assertEqual(exclude, 'Missing')
            for key, (_, value) in source._items.items():
                if key not in target._items:
                    raise ValueError('synthetic missing target property')
                target._items[key] = target._items[key][0], value

        probe = (PRESENTATION + self.old_helper + self.helper + self.body
                 + 'ПроверитьСписокИсключения("source-only.missing", "source-only", "Missing");\n')
        results = []
        for policy in (upfront_validation, copy_then_validate, source_insertion_order_traversal):
            rows = []
            with patch('yadinassi.runtime.fill_property_values', policy):
                Interpreter(rows.append).execute(probe)
            self.assertEqual(tuple(row.split(':', 1)[0] for row in rows), LABELS + (LAST_LABEL,))
            results.append(rows)
        self.assertEqual(len({tuple(rows) for rows in results}), 3)
        # The old last-only case cannot distinguish these two alternatives.
        self.assertEqual(results[1][2], results[2][2])
        self.assertNotEqual(results[1][:2], results[2][:2])
        # A first-only case cannot distinguish upfront from traversal either.
        self.assertEqual(results[0][0], results[2][0])
        self.assertNotEqual(results[0][1], results[2][1])
        expected_states = (
            ((1, 2, 3), (1, 2, 3), (1, 2, 3)),
            ((10, 20, 30), (10, 20, 30), (10, 20, 30)),
            ((1, 2, 3), (10, 2, 3), (10, 20, 30)),
        )
        for rows, states in zip(results, expected_states):
            for row, state in zip(rows, states):
                fields = ';'.join('{"N",' + str(value) + '}' for value in state)
                self.assertTrue(row.endswith('[error;' + fields + ';{"N",3};{"B",0};{"U"}]'), row)


if __name__ == '__main__':
    unittest.main()
