"""Fixed String defaults measured in PR82 native run 39769351606."""
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import unittest

from scripts.native_historical_replay import without_fixed_string_probes, without_service_filled_probes
from yadinassi import Interpreter
from yadinassi.serialization import value_from_string_internal, value_to_string_internal
from yadinassi.type_descriptions import BSLTypeDescription as TD
from yadinassi.type_qualifiers import BSLAllowedLength as AL, BSLStringQualifiers as SQ
from yadinassi.values import BSLType

ROOT = Path(__file__).resolve().parents[1]


class FixedStringDefaultTests(unittest.TestCase):
    def test_separately_measured_defaults_and_explicit_values(self):
        cases = [(1, AL.FIXED, ' '), (4, AL.FIXED, '    '),
                 (0, AL.FIXED, ''), (4, AL.VARIABLE, '')]
        for length, mode, expected in cases:
            description = TD('String', None, SQ(D(length), mode))
            for alias in ('AdjustValue', 'ПривестиЗначение', 'aDjUsTvAlUe'):
                method = description.get_member(alias)
                with self.subTest(length=length, mode=mode, alias=alias):
                    self.assertEqual(method(), expected)
                    self.assertEqual(method(None), expected)
                    self.assertEqual(method(''), expected)
                    self.assertIs(type(method()), str)
                    self.assertEqual(value_to_string_internal(method()),
                                     '{"S","' + expected + '"}')

    def test_restored_description_retains_qualified_default_without_mutation(self):
        description = TD('String', None, SQ(D(4), AL.FIXED))
        encoded = value_to_string_internal(description)
        restored = value_from_string_internal(encoded)
        self.assertIsNot(restored, description)
        for item in (description, restored):
            self.assertEqual(item.adjust_value(), '    ')
            self.assertEqual(item.adjust_value(None), '    ')
            self.assertEqual(item.adjust_value(''), '    ')
            self.assertEqual(item.adjust_value('ab'), 'ab  ')
            self.assertEqual(item.adjust_value('abcdef'), 'abcd')
            self.assertEqual(item.get_types().items, [BSLType.STRING])
            self.assertEqual(value_to_string_internal(item), encoded)

    def test_entire_live_source_matches_all_measured_fixed_default_records(self):
        source = (ROOT / 'integrational_tests/tests/values.bsl').read_text(encoding='utf-8')
        fixture = json.loads((ROOT / 'tests/fixtures/fixed_string_default_linux.json').read_text(encoding='utf-8'))
        self.assertEqual(fixture['native_run'], 39769351606)
        self.assertEqual(fixture['contexts'], ['server', 'managed-client'])
        self.assertEqual(hashlib.sha256(without_service_filled_probes(source).encode()).hexdigest(), fixture['source_sha256'])
        previous, actual = [], []
        Interpreter(previous.append).execute(without_fixed_string_probes(source))
        Interpreter(actual.append).execute(source)
        self.assertEqual(len(previous), 361)
        self.assertEqual(len(actual), 402)
        self.assertEqual(actual[:361], previous)
        self.assertEqual(actual[361:377], fixture['records'])
        self.assertEqual(len(fixture['records']), 16)
        self.assertTrue(all('[error]' not in item and '[serialize-error]' not in item
                            for item in fixture['records']))

    def test_composite_defaults_and_ambiguous_explicit_conversions_stay_bounded(self):
        description = TD('String,Number', None, SQ(D(4), AL.FIXED))
        self.assertIsNone(description.adjust_value())
        with self.assertRaisesRegex(ValueError, 'пока не поддерживается'):
            description.adjust_value(None)
        # A matching explicit String still uses the already-supported qualifier.
        self.assertEqual(description.adjust_value(''), '    ')

    def test_local_qualifier_budget_is_preserved_not_a_native_maximum(self):
        description = TD('String', None, SQ(D(1_000_000), AL.FIXED))
        value = description.adjust_value()
        self.assertEqual(len(value), 1_000_000)
        self.assertEqual(value.strip(' '), '')
        with self.assertRaisesRegex(ValueError, 'ресурсов Yadinassi'):
            SQ(D(1_000_001), AL.FIXED)
