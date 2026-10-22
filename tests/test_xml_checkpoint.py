"""Packaging of native XML observations, never predictions of their 1C results."""
from dataclasses import fields, is_dataclass
from decimal import Decimal
from pathlib import Path
import unittest

from integrational_tests.test_launcher import collect_scripts
from yadinassi import Interpreter, ast
from yadinassi.parser import parse, parse_expression
from yadinassi.values import BSLObject, HostFunction

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/values.bsl'
HELPERS_START = '// Нативный checkpoint скалярного XML.'
BODY_START = '// Скалярный XML: наблюдения без заранее заданных ответов.'
NULL_BODY = '// Значение, тип и настоящий прямой/обратный кодек.'
FINAL = 'xml.checkpoint.complete: [ok]'


def historical_source():
    from scripts.native_historical_replay import historical_values_source
    output = ROOT / 'tests/fixtures/native_windows/values.out'
    return historical_values_source(SOURCE.read_bytes(), output.read_bytes()).decode('utf-8')


def source():
    # Test the unchanged XML block independently of later pending themes.
    from scripts.smoke_test import pending_types_checkpoint
    return pending_types_checkpoint(historical_source())[0]


def helpers():
    return source().split(NULL_BODY, 1)[0]


def calls():
    return [node.expression for node in parse(source())
            if isinstance(node, ast.ExpressionStatement)
            and isinstance(node.expression, ast.Call)
            and isinstance(node.expression.callee, ast.Name)
            and node.expression.callee.name == 'НаблюдатьXML']


def expressions():
    return {call.arguments[0].value: call.arguments[1].value for call in calls()}


class XMLCheckpointTests(unittest.TestCase):
    def test_same_six_thematic_files(self):
        self.assertEqual({p.stem for p in collect_scripts(SOURCE.parent)},
                         {'functions', 'strings', 'collections', 'numbers', 'dates', 'values'})

    def test_unique_bounded_parseable_observations(self):
        self.assertEqual(len(calls()), 62)
        self.assertEqual(len(expressions()), 62)
        for call in calls():
            self.assertEqual(len(call.arguments), 2)
            label, expression = [argument.value for argument in call.arguments]
            self.assertRegex(label, r'^[a-z0-9.-]+$')
            self.assertLess(len(expression), 200, label)
            self.assertNotRegex(expression, r'[\r\n]')
            self.assertNotRegex(expression, r'(?i)\b(?:Import|Execute|Eval|While|For|Goto)\b')
            parse_expression(expression)

    def test_all_helpers_precede_main_code_and_null_block_still_precedes_xml(self):
        started = False
        names = []
        for node in parse(source()):
            if isinstance(node, ast.Routine):
                self.assertFalse(started, node.name)
                names.append(node.name)
            else:
                started = True
        self.assertEqual(names, ['НаблюдатьNull', 'ВложенныйNull', 'ПоискNull', 'КлючNull',
                                 'НаблюдатьXML', 'ПрочитатьДатуXML', 'КругXML', 'КодыXML',
                                 'УправляющиеXML', 'ГраницыXML', 'ОчисткаXML'])
        self.assertLess(source().index(HELPERS_START), source().index(NULL_BODY))
        self.assertLess(source().index('Сообщить("null.checkpoint.complete: [ok]");'),
                        source().index(BODY_START))
        self.assertTrue(source().rstrip().endswith('Сообщить("' + FINAL + '");'))

    def test_full_program_reaches_both_markers_and_preserves_native_null_prefix(self):
        output = []
        Interpreter(output=output.append).execute(source())
        self.assertEqual(output[40], 'null.checkpoint.complete: [ok]')
        expected = (ROOT / 'tests/fixtures/native_windows/values.out').read_text(encoding='utf-8')
        # The output can later gain native XML records; only this known block is compared.
        marker = 'null.checkpoint.complete: [ok]\n'
        self.assertEqual(expected.count(marker), 1)
        expected = expected.split(marker, 1)[0] + marker
        self.assertEqual('\n'.join(output[:41]) + '\n', expected)
        self.assertEqual(len(output), 104)
        self.assertEqual(output[-1], FINAL)
        observed = output[41:-1]
        self.assertEqual([line.split(': [', 1)[0] for line in observed],
                         ['xml.' + label for label in expressions()])
        for line in observed:
            self.assertRegex(line, r'(?s)^xml\.[a-z0-9.-]+: \[(?:error|serialize-error|\{.*\})\]$')

    def test_error_paths_do_not_hide_following_observations(self):
        output = []
        vm = Interpreter(output=output.append)
        vm.register_function('HostOnly', lambda: object())
        vm.execute(helpers() + '''
НаблюдатьXML("missing", "NoSuchFunction()");
НаблюдатьXML("syntax", "@");
НаблюдатьXML("unserializable", "HostOnly()");
НаблюдатьXML("next", "2 + 3");
''')
        self.assertEqual(output, ['xml.missing: [error]', 'xml.syntax: [error]',
                                 'xml.unserializable: [serialize-error]',
                                 'xml.next: [{"N",5}]'])

    def test_number_matrix_distinguishes_lexical_questions(self):
        probes = expressions()
        for label in ('zero', 'negative-zero', 'decimal', 'negative-small', 'precision', 'tiny'):
            self.assertTrue(probes['number.write.' + label].startswith('XMLString('))
        for label in ('plus-leading', 'minus-zero', 'leading-point', 'trailing-point',
                      'exponent', 'exponent-upper', 'space', 'tab', 'comma', 'empty', 'nan'):
            self.assertIn('number.read.' + label, probes)
        self.assertIn('123456789012345678901234567890.123456789', probes['number.write.precision'])
        self.assertIn('0.000000000000000000000000001', probes['number.write.tiny'])

    def test_date_matrix_records_fraction_and_timezone_discriminators(self):
        probes = expressions()
        for label in ('minimum', 'leap', 'fraction', 'maximum'):
            self.assertIn('date.write.' + label, probes)
        for label in ('plain', 'date-only', 'utc', 'offset-east', 'offset-west', 'fraction',
                      'fraction-tie', 'fraction-carry', 'midnight24', 'invalid-day'):
            self.assertTrue(probes['date.read.' + label].startswith('ПрочитатьДатуXML('))
        self.assertIn('+03:00', probes['date.read.offset-east'])
        self.assertIn('-05:30', probes['date.read.offset-west'])
        self.assertIn('.12345', probes['date.read.fraction-tie'])
        self.assertIn('.99995', probes['date.read.fraction-carry'])

    def test_fraction_addendum_distinguishes_rounding_without_expected_answers(self):
        probes = expressions()
        labels = [label for label in probes if label.startswith('date.fraction.')]
        self.assertEqual(len(labels), 10)
        for token in ('.4999', '.5', '.5001', '.9994', '.9995', '.9999', '.99994', '.99996'):
            self.assertTrue(any(token + '\"' in probes[label] for label in labels), token)
        self.assertIn('12:34:57.5', probes['date.fraction.odd-second-half'])
        self.assertIn('23:59:59.99995', probes['date.fraction.day-carry'])
        self.assertIn('+ 0.5', probes['date.write.half'])
        self.assertIn('+ 0.9999', probes['date.write.near-carry'])

    def test_date_helper_keeps_delta_in_addition_to_coarser_codec(self):
        vm = Interpreter()
        vm.execute(helpers())
        sample = vm.execute('Date(2024,2,29,12,34,56) + 0.1234')
        calls_seen = []
        def synthetic_reader(kind, text):
            calls_seen.append((kind, text))
            return sample
        vm.register_function('XMLЗначение', synthetic_reader)
        result = vm.execute('ПрочитатьДатуXML("synthetic")')
        self.assertIs(result.get('Value'), sample)
        self.assertEqual(result.get('Delta'), Decimal('0.1234'))
        self.assertEqual(len(calls_seen), 1)
        self.assertEqual(calls_seen[0][1], 'synthetic')

    def test_roundtrip_helper_observes_type_equality_and_nested_codec(self):
        vm = Interpreter()
        vm.execute(helpers())
        sample = Decimal('12.3400')
        seen = []
        vm.register_function('XMLСтрока', lambda value: seen.append(value) or 'synthetic')
        vm.register_function('XMLЗначение', lambda kind, text: sample)
        result = vm.execute('КругXML(12.3400)')
        self.assertEqual(seen, [sample])
        self.assertEqual(result.get('XML'), 'synthetic')
        self.assertEqual(result.get('Value'), sample)
        self.assertTrue(result.get('Equal'))
        self.assertEqual(result.get('Restored').get('Value'), sample)
        self.assertEqual(result.get('Restored').get('Text'), 'synthetic')

    def test_control_and_unicode_inputs_are_bounded_and_output_as_codes(self):
        vm = Interpreter()
        vm.execute(helpers())
        self.assertEqual(vm.execute('КодыXML(УправляющиеXML())').items,
                         [Decimal(n) for n in (0, 1, 8, 9, 10, 11, 12, 13, 14, 31,
                                              32, 127, 132, 133, 134, 159, 160)])
        self.assertEqual(vm.execute('КодыXML(ГраницыXML())').items,
                         [Decimal(n) for n in (55295, 55357, 56832, 57344, 64976,
                                              65533, 65534, 65535, 55296, 65, 56320)])
        self.assertEqual(vm.execute('КодыXML("")').items, [])
        self.assertEqual(vm.execute('КодыXML("😀")').items, [Decimal(55357), Decimal(56832)])
        # A host stub tests safe packaging only, not native XML validity semantics.
        calls_seen = []
        class SyntheticManager(BSLObject):
            def get_member(self, name):
                if name.casefold() not in ('удалитьнедопустимыесимволыxml',
                                          'deletedisallowedxmlcharacters'):
                    return super().get_member(name)
                def observe(text, version):
                    calls_seen.append((name, text, version))
                    return '\t😀'
                return HostFunction(name, observe)
        manager = SyntheticManager()
        vm.execute("Перем ОбработкаСтрокиXML, XMLStringProcessing;")
        vm.variables['обработкастрокиxml'] = manager
        vm.variables['xmlstringprocessing'] = manager
        output = []
        vm.output = output.append
        vm.execute('НаблюдатьXML("synthetic", "ОчисткаXML(ГраницыXML(), ""1.1"")");')
        self.assertEqual(len(output), 1)
        self.assertNotIn('\t', output[0])
        self.assertNotIn('😀', output[0])
        self.assertIn('55357', output[0])
        self.assertIn('56832', output[0])
        self.assertEqual([entry[0] for entry in calls_seen],
                         ['УдалитьНедопустимыеСимволыXML', 'DeleteDisallowedXMLCharacters'])
        self.assertEqual([entry[2] for entry in calls_seen], ['1.1', '1.1'])
        self.assertEqual(calls_seen[0][1], vm.execute('ГраницыXML()'))

    def test_cleanup_api_is_deferred_before_native_module_compilation(self):
        routine = next(node for node in parse(source())
                       if isinstance(node, ast.Routine) and node.name == 'ОчисткаXML')
        def walk(value):
            if is_dataclass(value):
                yield value
                for field in fields(value):
                    yield from walk(getattr(value, field.name))
            elif isinstance(value, (tuple, list)):
                for item in value:
                    yield from walk(item)
        calls_in_helper = [node for node in walk(routine) if isinstance(node, ast.Call)
                           and isinstance(node.callee, ast.Name)]
        unavailable = {'удалитьнедопустимыесимволыxml', 'deletedisallowedxmlcharacters'}
        all_helper_calls = [node for node in walk(parse(helpers()))
                            if isinstance(node, ast.Call) and isinstance(node.callee, ast.Name)]
        self.assertFalse(any(node.callee.name.casefold() in unavailable
                             for node in walk(parse(helpers()))
                             if isinstance(node, ast.Call)
                             and isinstance(node.callee, (ast.Name, ast.Attribute))))
        # Every other direct call already exists in owner-confirmed scenarios,
        # or names a helper declared in this same module.
        declared = {node.name.casefold() for node in parse(helpers())
                    if isinstance(node, ast.Routine)}
        established = {'вычислить', 'сообщить', 'значениевстрокувнутр',
                       'значениеизстрокивнутр', 'xmlзначение', 'xmlстрока',
                       'тип', 'типзнч', 'дата', 'стрдлина', 'кодсимвола', 'символ'}
        self.assertLessEqual({call.callee.name.casefold() for call in all_helper_calls},
                             declared | established)
        deferred = [call for call in calls_in_helper if call.callee.name == 'Вычислить']
        self.assertEqual([call.arguments[0].value for call in deferred],
                         ['ОбработкаСтрокиXML.УдалитьНедопустимыеСимволыXML(Текст, Версия)',
                          'XMLStringProcessing.DeleteDisallowedXMLCharacters(Текст, Версия)'])
        # A platform without this API must still reach subsequent observations.
        output = []
        vm = Interpreter(output=output.append)
        vm.execute("Перем ОбработкаСтрокиXML, XMLStringProcessing;")
        vm.variables["обработкастрокиxml"] = BSLObject()
        vm.variables["xmlstringprocessing"] = BSLObject()
        vm.execute(helpers() + '''
НаблюдатьXML("unavailable", "ОчисткаXML(ГраницыXML(), ""1.0"")");
НаблюдатьXML("following", "XMLString(True)");
''')
        self.assertEqual(output, ['xml.unavailable: [error]', 'xml.following: [{"S","true"}]'])

    def test_manager_metadata_probes_are_protected_and_do_not_assume_a_codec(self):
        probes = expressions()
        self.assertEqual(probes['manager.types'],
                         'New Structure("RU,EN", TypeOf(ОбработкаСтрокиXML), TypeOf(XMLStringProcessing))')
        self.assertEqual(probes['manager.write'], 'ValueToStringInternal(XMLStringProcessing)')
        self.assertEqual(probes['manager.inverse'],
                         'ValueFromStringInternal(ValueToStringInternal(ОбработкаСтрокиXML))')
        output = []
        vm = Interpreter(output=output.append)
        vm.execute(helpers())
        vm.execute("Перем ОбработкаСтрокиXML, XMLStringProcessing;")
        # Host object intentionally has no supported internal codec. Both
        # observation errors are isolated, not replaced by a guessed record.
        vm.variables['xmlstringprocessing'] = BSLObject()
        vm.variables['обработкастрокиxml'] = vm.variables['xmlstringprocessing']
        for label in ('manager.write', 'manager.inverse'):
            expression = probes[label].replace('"', '""')
            vm.execute('НаблюдатьXML("' + label + '", "' + expression + '");')
        vm.execute('НаблюдатьXML("after-manager", "1 + 1");')
        self.assertEqual(output, ['xml.manager.write: [error]', 'xml.manager.inverse: [error]',
                                 'xml.after-manager: [{"N",2}]'])

    def test_cleanup_covers_both_versions_defaults_and_invalid_inputs(self):
        probes = expressions()
        for family in ('controls', 'unicode'):
            for version in ('1.0', '1.1'):
                self.assertIn('"' + version + '"', probes['clean.' + family + '.' + version])
        for label in ('default', 'separated-surrogates', 'literal-markup', 'bad-version',
                      'nonstring', 'undefined-version'):
            self.assertIn('clean.' + label, probes)
        for label in ('default', 'bad-version', 'nonstring', 'undefined-version'):
            self.assertIn('XMLStringProcessing.DeleteDisallowedXMLCharacters(', probes['clean.' + label])
        self.assertIn('Символ(55296) + Символ(0) + Символ(56320)',
                      probes['clean.separated-surrogates'])

    def test_no_external_state_unbounded_loops_or_locale_error_strings(self):
        text = source().split(HELPERS_START, 1)[1]
        self.assertNotRegex(text, r'\b(?:Пока|Перейти|Выполнить|ОписаниеОшибки|ТекущаяДата|CurrentDate)\b')
        self.assertEqual(text.count('Вычислить('), 3)
        self.assertEqual(text.count('Для Позиция = 1 По СтрДлина(Текст) Цикл'), 1)
        self.assertEqual(source().count('xml.checkpoint.complete'), 1)
        self.assertNotRegex(source(), r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
        self.assertNotIn('\x00', source())

    def test_execution_does_not_write_native_outputs_or_metadata(self):
        paths = list((ROOT / 'tests/fixtures/native_windows').rglob('*'))
        paths += [ROOT / 'integrational_tests/meta.md', ROOT / 'tests/fixtures/basic.out']
        before = {p: p.read_bytes() for p in paths if p.is_file()}
        Interpreter(output=lambda message: None).execute(source())
        after_paths = list((ROOT / 'tests/fixtures/native_windows').rglob('*'))
        after_paths += [ROOT / 'integrational_tests/meta.md', ROOT / 'tests/fixtures/basic.out']
        self.assertEqual(before, {p: p.read_bytes() for p in after_paths if p.is_file()})


if __name__ == '__main__':
    unittest.main()
