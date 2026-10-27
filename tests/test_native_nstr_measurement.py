"""NStr instrumentation and source contracts only; no native semantic answers."""
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import unittest
from unittest import mock

from yadinassi import BSLError, Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse
from scripts.native_historical_replay import (
    without_nstr_discriminators, without_nstr_probes,
    without_text_document_probes, without_uuid_probes,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '16bd5c91f17225906ef9e9e579371b8884eff74dafd67167b06e5a2dda2e55d5'
INITIAL_SHA = '9e1af33c93352aebf9166bf5f702f526f221df7e9945ba139ccbc3d1fd0a34e4'
PRIOR_SHA = 'be2cdd08643e14747c4375d6f2f8a9f995c88e8ef028470fc29066329eeece76'
HELPERS_SHA = '0352208da1154f8a1b25002825c63537d909fac4c5a2b27a213213d1c4a00768'
CALLS_SHA = '89b5e03a9d59b7fcf6cb365f2890768fdeb1b609b45a9d51dfa261e7670079b5'
HELPER_START = '// Begin bounded NStr helpers (measurement only; no native answers).\n'
HELPER_END = '// End bounded NStr helpers.\n\n'
CALL_START = '// Begin bounded NStr observations (measurement only; no native answers).\n'
CALL_END = '// End bounded NStr observations.\n'
DISCRIMINATOR_START = '// Begin bounded NStr discriminators (measurement only; no native answers).\n'
DISCRIMINATOR_END = '// End bounded NStr discriminators.\n'
DISCRIMINATOR_SHA = '07e24e027342efbeb9bb05c0bc106b846e7782f9a30cd9aebe70e819e77e021f'
LABELS = (
    'alias.ru.ru', 'alias.ru.en', 'alias.en.ru', 'alias.en.en', 'order.ru',
    'order.en', 'spaces', 'tabs', 'empty.template', 'empty.ru', 'empty.en',
    'separator.trailing', 'separator.double', 'quote.apostrophe', 'quote.double',
    'content.semicolon.equals', 'unicode', 'language.upper', 'language.mixed',
    'language.missing', 'language.missing.reordered', 'duplicate.first',
    'duplicate.reordered', 'duplicate.case', 'malformed.unquoted',
    'malformed.unterminated', 'malformed.no.equals', 'malformed.trailing',
    'language.omitted', 'language.empty', 'language.undefined', 'language.number',
    'language.boolean', 'language.null', 'template.number', 'template.undefined',
    'default.reordered.omitted', 'default.reordered.empty',
    'default.reordered.undefined', 'default.reordered.null',
    'default.enonly.omitted', 'default.enonly.empty', 'default.enonly.undefined',
    'default.enonly.null', 'default.enonly.explicit',
    'coercion.number.value', 'coercion.number.string',
    'coercion.boolean.value', 'coercion.boolean.string',
)
# Independently stated INPUT lengths, not expected selected values or grammar.
TEMPLATE_UNITS = (13, 13, 13, 13, 13, 13, 27, 15, 0, 12, 12, 14, 14, 20,
                  15, 17, 17, 13, 13, 13, 13, 20, 20, 20, 11, 12, 12, 14,
                  13, 13, 13, 13, 13, 13, None, None,
                  13, 13, 13, 13, 6, 6, 6, 6, 6, 12, 12, 13, 13)


def source_bytes():
    raw = (ROOT / 'integrational_tests/tests/values.bsl').read_bytes()
    return raw.replace(b'\r\n', b'\n') if os.name == 'nt' else raw


def fragments():
    source = source_bytes().decode('utf-8')
    helpers = HELPER_START + source.split(HELPER_START)[1].split(HELPER_END)[0] + HELPER_END
    calls = CALL_START + source.split(CALL_START)[1]
    return helpers, calls


def records():
    result = []
    for line in fragments()[1].splitlines():
        if line in tuple(marker.rstrip('\n') for marker in
                         (CALL_START, CALL_END, DISCRIMINATOR_START, DISCRIMINATOR_END)):
            continue
        if not line.startswith('НаблюдатьНСтр('):
            raise AssertionError('Unexpected NStr observation statement')
        fields = re.findall(r'"((?:[^"]|"")*)"', line)
        if len(fields) != 2:
            raise AssertionError('NStr observation arity changed')
        result.append(tuple(value.replace('""', '"') for value in fields))
    return result


def quote(text):
    return '"' + text.replace('"', '""') + '"'


class NStrInstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)
        self.vm.execute(fragments()[0])

    def observe(self, label, expression):
        self.vm.execute('НаблюдатьНСтр(' + quote(label) + ', ' + quote(expression) + ');')

    def test_matrix_has_only_fixed_input_expressions_no_expected_answers(self):
        helpers, calls = fragments()
        parse(helpers + calls)
        rows = records()
        self.assertEqual(tuple(label for label, _ in rows), LABELS)
        self.assertEqual(len(set(LABELS)), 49)
        for label, expression in rows:
            statements = parse(expression)
            self.assertEqual(len(statements), 1)
            call = statements[0].expression
            self.assertIsInstance(call, ast.Call)
            self.assertIsInstance(call.callee, ast.Name)
            self.assertIn(call.callee.name, ('НСтр', 'NStr'))
            self.assertLess(len(label), 40)
            def fixed_input(node):
                if isinstance(node, ast.Literal):
                    return
                if isinstance(node, ast.Binary) and node.operator == '+':
                    fixed_input(node.left)
                    fixed_input(node.right)
                    return
                if (isinstance(node, ast.Call) and isinstance(node.callee, ast.Name)
                        and node.callee.name == 'Символ' and len(node.arguments) == 1
                        and isinstance(node.arguments[0], ast.Literal)
                        and node.arguments[0].value == Decimal(9)):
                    return
                if (isinstance(node, ast.Call) and isinstance(node.callee, ast.Name)
                        and node.callee.name == 'Строка' and len(node.arguments) == 1
                        and isinstance(node.arguments[0], ast.Literal)
                        and (node.arguments[0].value is True or
                             (type(node.arguments[0].value) is Decimal
                              and node.arguments[0].value == Decimal(1)))):
                    return
                self.fail('Nonliteral or unexpected executable NStr input')
            for argument in call.arguments:
                fixed_input(argument)
            for forbidden in ('Сообщить', 'ОписаниеОшибки', 'ЗначениеВСтрокуВнутр',
                              'Выполнить', 'Новый', 'Найти', 'Лев('):
                self.assertNotIn(forbidden, expression)
        self.assertEqual(helpers.count('Вычислить(Выражение)'), 1)
        self.assertNotIn('Выполнить(', helpers)
        self.assertNotIn('ОписаниеОшибки', helpers)

    def test_fixed_inputs_and_lengths_arrive_without_prediction_or_conversion(self):
        # This host-only witness records arguments, never interprets NStr syntax.
        seen = []
        def witness(*arguments):
            seen.append(arguments)
            return 'harness-only'
        self.vm.register_function('НСтр', witness)
        self.vm.register_function('NStr', witness)
        self.vm.execute(fragments()[1])
        self.assertEqual(len(seen), 49)
        self.assertEqual(len(self.output), 49)
        actual = tuple(len(args[0].encode('utf-16-le')) // 2 if type(args[0]) is str else None
                       for args in seen)
        self.assertEqual(actual, TEMPLATE_UNITS)
        self.assertLessEqual(max(n for n in actual if n is not None), 27)
        self.assertEqual(seen[13][0], "ru='O''Brien';en='B'")
        self.assertEqual(seen[14][0], 'ru=\'A"B\';en=\'B\'')
        self.assertEqual(seen[15][0], "ru='A;B=C';en='B'")
        self.assertEqual(seen[16][0], "ru='Я😀é';en='B'")
        self.assertEqual(seen[28], ("ru='А';en='B'",))
        self.assertEqual(seen[29][1], '')
        self.assertIsNone(seen[30][1])
        self.assertEqual(seen[31][1], Decimal(1))
        self.assertIs(seen[32][1], True)
        self.assertEqual(type(seen[33][1]).__name__, 'BSLNull')
        self.assertIs(type(seen[34][0]), Decimal)
        self.assertIsNone(seen[35][0])
        for offset, template in ((36, "en='B';ru='А'"), (40, "en='B'")):
            self.assertEqual(seen[offset], (template,))
            self.assertEqual(seen[offset + 1], (template, ''))
            self.assertEqual(seen[offset + 2], (template, None))
            self.assertEqual(seen[offset + 3][0], template)
            self.assertEqual(type(seen[offset + 3][1]).__name__, 'BSLNull')
        self.assertEqual(seen[44], ("en='B'", 'en'))
        self.assertEqual(seen[45], ("1='N';ru='R'", Decimal(1)))
        self.assertEqual(seen[46], ("1='N';ru='R'", '1'))
        self.assertEqual(seen[47], ("Да='T';ru='R'", True))
        self.assertEqual(seen[48], ("Да='T';ru='R'", 'Да'))

    def test_discriminators_compare_independent_inputs_not_observed_results(self):
        rows = dict(records())
        for group, template in (('reordered', "en='B';ru='А'"), ('enonly', "en='B'")):
            for suffix, argument in (('omitted', None), ('empty', '""'),
                                     ('undefined', 'Неопределено'), ('null', 'Null')):
                expected = 'НСтр(' + quote(template)
                expected += ')' if argument is None else ', ' + argument + ')'
                self.assertEqual(rows['default.' + group + '.' + suffix], expected)
        self.assertEqual(rows['default.enonly.explicit'], 'НСтр("en=\'B\'", "en")')
        for kind, template, argument in (('number', "1='N';ru='R'", '1'),
                                         ('boolean', "Да='T';ru='R'", 'Истина')):
            self.assertEqual(rows['coercion.' + kind + '.value'],
                             'НСтр(' + quote(template) + ', ' + argument + ')')
            self.assertEqual(rows['coercion.' + kind + '.string'],
                             'НСтр(' + quote(template) + ', Строка(' + argument + '))')

    def test_utf16_projection_is_lossless_including_empty_controls_and_astral(self):
        for value, expected in (('', 'S0:'), ('A', 'S1:0041'),
                                ('A\r\nБ😀', 'S6:0041000d000a0411d83dde00'),
                                ('é', 'S2:00650301'), ('\ud800', 'S1:d800')):
            self.vm.variables['probe'] = value
            self.assertEqual(self.vm.execute('КодыНСтр(probe)'), expected)
        for value in ('x' * 64, '😀' * 32):
            self.vm.variables['probe'] = value
            self.assertTrue(self.vm.execute('КодыНСтр(probe)').startswith('S64:'))
        for value in ('x' * 65, '😀' * 33, None, True, Decimal(1)):
            self.vm.variables['probe'] = value
            with self.assertRaises(BSLError):
                self.vm.execute('КодыНСтр(probe)')

    def test_action_failure_and_observer_failure_do_not_conflate_or_hide_next(self):
        self.observe('action', 'SyntheticMissingFunction()')
        self.observe('wrongtype', '1')
        self.observe('overflow', quote('x' * 65))
        self.observe('empty', '""')
        self.observe('next', '"A"')
        self.assertEqual(self.output, [
            'nstr.action: [action-error]', 'nstr.wrongtype: [observer-error]',
            'nstr.overflow: [observer-error]', 'nstr.empty: [ok|S0:]',
            'nstr.next: [ok|S1:0041]',
        ])
        self.assertNotIn('SyntheticMissingFunction', ''.join(self.output))


class NStrSourceContracts(unittest.TestCase):
    def test_exact_source_and_inverse_chain_preserve_every_old_byte(self):
        import test_native_1c_full_stage as f
        raw = source_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA)
        helpers, calls = fragments()
        self.assertEqual(hashlib.sha256(helpers.encode()).hexdigest(), HELPERS_SHA)
        initial_calls, discriminator_calls = calls.split(DISCRIMINATOR_START)
        self.assertEqual(hashlib.sha256(initial_calls.encode()).hexdigest(), CALLS_SHA)
        self.assertEqual(hashlib.sha256((DISCRIMINATOR_START + discriminator_calls).encode()).hexdigest(),
                         DISCRIMINATOR_SHA)
        self.assertEqual(len(raw.splitlines()), 1225)
        initial = without_nstr_discriminators(raw.decode()).encode()
        self.assertEqual(hashlib.sha256(initial).hexdigest(), INITIAL_SHA)
        self.assertTrue(raw.startswith(initial))
        self.assertLess(len(raw) - len(initial), 2500)
        previous = without_nstr_probes(raw.decode()).encode()
        self.assertEqual(hashlib.sha256(previous).hexdigest(), PRIOR_SHA)
        self.assertLess(len(initial) - len(previous), 7500)
        self.assertEqual(hashlib.sha256(without_text_document_probes(raw.decode()).encode()).hexdigest(),
                         '0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c')
        self.assertEqual(hashlib.sha256(without_uuid_probes(raw.decode()).encode()).hexdigest(),
                         'dbf750d20ac7db3dba1df2e67d2e2cfc54c361c991d132d616bbe2d956a6ca12')
        self.assertEqual((f.suite.CLIENT_VALUES_MESSAGE_COUNT,
                          f.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT), (534, 973))

    def test_live_adapter_preserves_complete_input_and_rejects_every_old_source(self):
        import test_native_1c_full_stage as f
        raw = source_bytes()
        template = (ROOT / f.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt':
            template = template.replace(b'\r\n', b'\n')
        module = f.suite.client_values_module(raw, template)
        self.assertIn(fragments()[1].encode(), module)
        for label, expression in records():
            self.assertIn(quote(expression).encode(), module)
        mutants = (raw + b'\n', raw[:-1], raw.replace(b'\n', b'\r\n'),
                   b'\xef\xbb\xbf' + raw, raw.replace(b'alias.ru.ru', b'alias.ru.rx'),
                   raw.replace(b'default.enonly.omitted', b'default.enonly.changed'),
                   without_nstr_discriminators(raw.decode()).encode(),
                   without_nstr_probes(raw.decode()).encode(),
                   without_text_document_probes(raw.decode()).encode(),
                   without_uuid_probes(raw.decode()).encode())
        for mutated in mutants:
            with self.subTest(sha=hashlib.sha256(mutated).hexdigest()):
                with self.assertRaises(f.suite.FullError):
                    f.suite.client_values_module(mutated, template)
                with self.assertRaises(ValueError):
                    without_nstr_discriminators(mutated.decode())

    def test_new_shape_guards_reject_mutants_even_when_raw_hash_is_rebound(self):
        import test_native_1c_full_stage as f
        raw = source_bytes()
        template = (ROOT / f.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt':
            template = template.replace(b'\r\n', b'\n')
        for old, new in (('Функция КодыНСтр(', 'Функция ДругаяПроекция('),
                         ('Процедура НаблюдатьНСтр(', 'Процедура ДругаяПроба('),
                         ('[action-error]', '[guessed-success]'),
                         ('[observer-error]', '[action-error]')):
            mutant = raw.replace(old.encode(), new.encode(), 1)
            self.assertNotEqual(mutant, raw)
            with mock.patch.object(f.suite, 'CLIENT_VALUES_SOURCE_SHA256',
                                   hashlib.sha256(mutant).hexdigest()):
                with self.assertRaises(f.suite.FullError):
                    f.suite.client_values_module(mutant, template)

    def test_historical_harness_inverses_stay_isolated_and_exact(self):
        import test_native_1c_full_stage as f
        from test_native_async_fixture import (
            without_nstr_measurement, historical_nstr_values_module,
            without_nstr_discriminator_measurement, historical_nstr_discriminator_values_module,
            historical_text_document_values_module, historical_uuid_values_module,
        )
        raw = source_bytes()
        template = (ROOT / f.suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt':
            template = template.replace(b'\r\n', b'\n')
        initial = historical_nstr_discriminator_values_module(raw, template)
        self.assertIn('Количество() >= 521'.encode(), initial)
        self.assertIn(b'nstr.', initial)
        self.assertNotIn(b'default.enonly.', initial)
        old = historical_nstr_values_module(raw, template)
        self.assertEqual(hashlib.sha256(old).hexdigest(),
                         'f605e0bf895250133a7a7bc11599c756dd997ff1218dc78f5f58e4ec8897b95b')
        self.assertNotIn(b'nstr.', old)
        self.assertIn('Количество() >= 485'.encode(), old)
        self.assertEqual(hashlib.sha256(historical_text_document_values_module(raw, template)).hexdigest(),
                         '433a2db811bab637ab666e5a0cbdeb9eeeffd158534b223dfa34f0389b9cc282')
        self.assertEqual(hashlib.sha256(historical_uuid_values_module(raw, template)).hexdigest(),
                         '814858ce2af10afc86882ec719a19f41589effabb71b83882d94d6077d90e824')
        for host, path in ((True, 'scripts/native_1c_full_host.py'),
                           (False, 'scripts/native_1c_bootstrap/full_suite.py')):
            source = (ROOT / path).read_text(encoding='utf-8')
            restored = without_nstr_discriminator_measurement(source, host=host)
            expected = ('d6923fe683a0e566d834d41dd2d42a8f586f6439fd77490fa8840a499a49450c'
                        if host else 'd73687d65388de24f197c3146b10432ca2ecd45841c3c3ce7521cc8b3840154b')
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), expected)
            without_nstr_measurement(source, host=host)
            with self.assertRaises(AssertionError):
                without_nstr_measurement(source + '\n', host=host)
            with self.assertRaises(AssertionError):
                without_nstr_discriminator_measurement(restored, host=host)

    def test_unchanged_caps_and_lossless_record_bound(self):
        import test_native_1c_full_stage as f
        self.assertEqual((f.suite.MAX_STAGE_REPORT, f.suite.MAX_REPORT,
                          f.suite.MAX_OUTPUT, f.suite.MAX_TOTAL,
                          f.suite.MAX_TRANSPORT, f.suite.MAX_RESULT),
                         (8192, 32768, 1048576, 2097152, 3145728, 2097152))
        # Max label <40, ASCII S64: plus exactly 4 digits per UTF-16 unit;
        # full record including LF fits312 bytes, no raw/partial payload escapes.
        self.assertEqual(len('nstr.' + 'x' * 39 + ': [ok|S64:' + 'f' * 256 + ']\n'), 312)
        self.assertEqual(13 * 312, 4056)
        self.assertEqual(49 * 312, 15288)
        self.assertLess(49 * 312, f.suite.MAX_OUTPUT // 64)


if __name__ == '__main__':
    unittest.main()
