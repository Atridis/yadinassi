"""Date foundation backed by the owner's unchanged 50-observation checkpoint.

NativeDateEvidenceTests replays the actual 1C fixture. Other tests exercise the
explicit standalone subset and its defensive boundaries; they do not claim new
native evidence for malformed input, resource limits, or unobserved ranges.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
import re
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.dates import (
    BSLDate, UnsupportedDateRange, component, date, date_difference,
    literal_date, shift_date,
)
from yadinassi.errors import BSLRuntimeError, IncompleteInput
from yadinassi.syntax.lexer import Lexer
from yadinassi.maps import BSLFixedMap, BSLMap
from yadinassi.syntax.parser import parse, parse_expression
from yadinassi.serialization import (
    FORMAT_ERROR, value_from_string_internal as read,
    value_to_string_internal as write,
)
from yadinassi.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.type_values import type_by_name, type_of
from yadinassi.value_checks import value_is_filled
from yadinassi.values import BSLArray, BSLFixedArray, BSLObject, BSLType, equal, to_string


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'integrational_tests/tests/dates.bsl'
NATIVE = ROOT / 'tests/fixtures/native_windows/dates.out'
DATE_UUID = 'aae38c48-a877-411c-a6d3-fbaa1f83c4bd'
DATE_PAYLOAD = '{"D",20240229123456}'
BASE_TEXT = '20240229123456'
FIELDS = ('year', 'month', 'day', 'hour', 'minute', 'second')


def parts(*values):
    return date(*(Decimal(str(value)) for value in values))


def array(*items):
    result = BSLArray()
    for item in items:
        result.add(item)
    return result


def mapping(*entries):
    result = BSLMap()
    for key, value in entries:
        result.insert(key, value)
    return result


def quote(text):
    return '"' + text.replace('"', '""').replace('\n', '\n|') + '"'


def normalize_transport(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')


class NativeDateEvidenceTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        native = normalize_transport(NATIVE.read_text(encoding='utf-8-sig'))
        # These assertions own the complete foundation through its required marker;
        # the unchanged strict native comparator owns the entire expanded file.
        marker = 'date.checkpoint.complete: [ok]\n'
        cls.native = native[:native.index(marker) + len(marker)]

    def record(self, label):
        matches = re.findall(
            r'^date\.' + re.escape(label) + r': \[(.*?)\](?=\ndate\.|\n?\Z)',
            self.native, re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(matches), 1, label)
        return matches[0]

    def test_complete_native_checkpoint_matches_all_127_lines(self):
        before = {path: path.read_bytes() for path in
                  (SOURCE, NATIVE, ROOT / 'integrational_tests/meta.md')}
        output = []
        text = SOURCE.read_text(encoding='utf-8-sig')
        marker = 'Сообщить("date.checkpoint.complete: [ok]");'
        foundation = text[:text.index(marker) + len(marker)]
        Interpreter(output=output.append).execute(foundation, str(SOURCE))
        actual = ''.join(normalize_transport(message) + '\n' for message in output)
        self.assertEqual(len(output), 51)  # 50 observations plus the completion marker.
        self.assertEqual(len(self.native.splitlines()), 127)
        self.assertEqual(len(re.findall(r'^date\.', self.native, re.MULTILINE)), 51)
        self.assertEqual(output[-1], 'date.checkpoint.complete: [ok]')
        self.assertMultiLineEqual(actual, self.native)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_native_constructor_literal_and_type_identity_witnesses(self):
        for label in ('construct.parts', 'construct.canonical', 'literal.full',
                      'literal.punctuation', 'codec.roundtrip', 'precision.codec'):
            self.assertEqual(self.record(label), DATE_PAYLOAD)
        for label in ('codec.type-ru', 'codec.type-en', 'codec.typeof', 'codec.type-roundtrip'):
            self.assertEqual(self.record(label), '{"T",' + DATE_UUID + '}')
        for label in ('construct.ymdh', 'construct.ymdhm', 'construct.omitted',
                      'construct.nonleap', 'construct.zero-year', 'construct.excess-year',
                      'literal.short-time', 'literal.invalid', 'arithmetic.reversed'):
            self.assertEqual(self.record(label), 'error')
        self.assertEqual(write(date(BASE_TEXT)), self.record('construct.parts'))
        self.assertEqual(write(type_of(date(BASE_TEXT))), self.record('codec.typeof'))

    def test_native_fractional_seconds_and_roundtrip_are_distinct(self):
        base = date(BASE_TEXT)
        for text, expected, label in (
                ('0.0001', '0.0001', '0-0001'), ('0.00005', '0.0001', '0-00005'),
                ('0.00015', '0.0002', '0-00015'), ('-0.0001', '-0.0001', 'neg0-0001'),
                ('-0.00005', '-0.0001', 'neg0-00005'),
                ('-0.00015', '-0.0002', 'neg0-00015')):
            with self.subTest(delta=text):
                difference = date_difference(shift_date(base, Decimal(text)), base)
                self.assertEqual(difference, Decimal(expected))
                self.assertEqual(write(difference), self.record('precision.delta-' + label))
        restored = read(write(shift_date(base, Decimal('0.1234'))))
        self.assertEqual(write(date_difference(restored, base)), self.record('precision.roundtrip'))
        self.assertEqual(self.record('construct.fraction'), '{"N",0}')


class DateConstructorTests(unittest.TestCase):
    def test_three_and_six_component_forms_and_strict_canonical_forms(self):
        samples = [
            ((1, 1, 1), '00010101000000'), ((2024, 2, 29), '20240229000000'),
            ((2024, 2, 29, 12, 34, 56), BASE_TEXT),
            ((9999, 12, 31, 23, 59, 59), '99991231235959'),
        ]
        for components, canonical in samples:
            with self.subTest(components=components):
                value = parts(*components)
                self.assertIs(type(value), BSLDate)
                self.assertEqual(value, date(canonical))
                self.assertEqual(write(value), '{"D",' + canonical + '}')
                self.assertIs(type(value.ticks), int)
        self.assertEqual(date('20240229'), parts(2024, 2, 29))

    def test_fractional_seconds_truncate_in_constructor_without_tick_rounding(self):
        base = date(BASE_TEXT)
        for second in ('56.0001', '56.5', '56.9', '56.99999'):
            self.assertEqual(parts(2024, 2, 29, 12, 34, second), base)
        self.assertEqual(parts(2024, 2, 29, 12, 34, '59.99999'),
                         date('20240229123459'))
        self.assertEqual(parts('2024.000', '2.0', '29.00'), date('20240229'))

    def test_fractional_nonsecond_components_are_explicitly_unsupported(self):
        values = [Decimal(value) for value in (2024, 2, 29, 12, 34, 56)]
        for index in range(5):
            arguments = values.copy()
            arguments[index] = Decimal(str(values[index]) + '.1')
            with self.subTest(component=index), self.assertRaises((TypeError, ValueError)):
                date(*arguments)

    def test_calendar_validation_does_not_normalize_invalid_components(self):
        invalid = [
            (0, 1, 1), (10000, 1, 1), (2024, 0, 1), (2024, 13, 1),
            (2024, 1, 0), (2024, 1, 32), (2023, 2, 29), (1900, 2, 29),
            (2024, 4, 31), (2024, 2, 29, -1, 0, 0),
            (2024, 2, 29, 24, 0, 0), (2024, 2, 29, 0, -1, 0),
            (2024, 2, 29, 0, 60, 0), (2024, 2, 29, 0, 0, -1),
            (2024, 2, 29, 0, 0, 60),
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                parts(*arguments)
        self.assertEqual(parts(2000, 2, 29), date('20000229'))

    def test_string_constructor_does_not_accept_literal_or_localized_syntax(self):
        for text in ('', '2024', '2024022912', '202402291234', '202402291234560',
                     ' 20240229', '20240229 ', '2024-02-29', '29.02.2024',
                     '20240229\x00', '２０２４０２２９', '٢٠٢٤٠٢٢٩',
                     '+20240229', '20240229.0', '20240230', '00000101',
                     '20240229246000', '20240229235960'):
            with self.subTest(text=text), self.assertRaises((TypeError, ValueError)):
                date(text)

    def test_wrong_arity_and_non_native_component_types_are_rejected(self):
        for arguments in ((), (Decimal(2024),), (Decimal(2024), Decimal(2)),
                          tuple(Decimal(1) for _ in range(4)),
                          tuple(Decimal(1) for _ in range(5)),
                          tuple(Decimal(1) for _ in range(7))):
            with self.subTest(arguments=arguments), self.assertRaises((TypeError, ValueError)):
                date(*arguments)
        for value in (None, True, False, 2024, 2024.0, [], {}, object(), date(BASE_TEXT)):
            for arguments in ((value,), (value, Decimal(2), Decimal(29))):
                with self.subTest(kind=type(value)), self.assertRaises((TypeError, ValueError)):
                    date(*arguments)
        for text in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
            for index in range(6):
                arguments = [Decimal(value) for value in (2024, 2, 29, 12, 34, 56)]
                arguments[index] = Decimal(text)
                with self.subTest(text=text, index=index), self.assertRaises((TypeError, ValueError)):
                    date(*arguments)

    def test_literal_payload_lengths_and_separator_filtering(self):
        for payload, expected in (
                ('20240229', '20240229000000'), ('202402291234', '20240229123400'),
                (BASE_TEXT, BASE_TEXT), ('2024-02-29 12:34:56', BASE_TEXT),
                ('2024/02/29', '20240229000000'), ('2024.02.29 12:34', '20240229123400')):
            with self.subTest(payload=payload):
                self.assertEqual(literal_date(payload), date(expected))
        for payload in ('', '----', '2024022', '202402291', '2024022912',
                        '20240229123', '2024022912345', '202402291234567',
                        '20230229', '２０２４０２２９', '٢٠٢٤٠٢٢٩'):
            with self.subTest(payload=payload), self.assertRaises((TypeError, ValueError)):
                literal_date(payload)

    def test_date_is_an_immutable_value_with_same_tick_equality_and_hash(self):
        first = date(BASE_TEXT)
        second = parts(2024, 2, 29, 12, 34, 56)
        later = shift_date(first, Decimal('0.0001'))
        self.assertIsNot(first, second)
        self.assertTrue(equal(first, second))
        self.assertEqual(hash(first), hash(second))
        self.assertEqual(len({first, second, later}), 2)
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            first.ticks = 0
        with self.assertRaises((FrozenInstanceError, AttributeError, TypeError)):
            del first.ticks
        self.assertEqual(first, date(BASE_TEXT))
        for other in (None, False, True, Decimal(first.ticks), first.ticks,
                      BASE_TEXT, BSLType.NUMBER, BSLArray()):
            self.assertFalse(equal(first, other))
            self.assertFalse(equal(other, first))


class DateArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.base = date(BASE_TEXT)

    def test_tick_quantization_is_half_away_from_zero(self):
        cases = [('0', '0'), ('-0.00000', '0'), ('0.00001', '0'),
                 ('0.000049999', '0'), ('0.00005', '0.0001'),
                 ('0.0001', '0.0001'), ('0.000149999', '0.0001'),
                 ('0.00015', '0.0002'), ('0.99995', '1'),
                 ('0.4', '0.4'), ('0.5', '0.5'), ('0.6', '0.6'),
                 ('1.23455', '1.2346'), ('123456.78905', '123456.7891')]
        for source, expected in cases:
            for negative in (False, True):
                delta = Decimal(source)
                result = Decimal(expected)
                if negative:
                    delta, result = delta.copy_negate(), result.copy_negate()
                with self.subTest(delta=delta):
                    shifted = shift_date(self.base, delta)
                    self.assertIs(type(shifted), BSLDate)
                    self.assertEqual(date_difference(shifted, self.base), result)
                    self.assertEqual(date_difference(self.base, shifted), result.copy_negate())

    def test_integer_tick_deltas_accumulate_without_float_drift(self):
        value = self.base
        for _ in range(1000):
            value = shift_date(value, Decimal('0.0001'))
        self.assertEqual(value.ticks - self.base.ticks, 1000)
        self.assertEqual(date_difference(value, self.base), Decimal('0.1'))
        for _ in range(1000):
            value = shift_date(value, Decimal('-0.0001'))
        self.assertEqual(value, self.base)

    def test_gregorian_calendar_rollovers_against_independent_datetime_oracle(self):
        for canonical in ('00010101000000', '16000228235959', '19000228235959',
                          '19991231235959', '20000228235959', '20000229235959',
                          '20240229235959', '20241231235959', '99991230235959'):
            source = datetime.strptime(canonical, '%Y%m%d%H%M%S')
            for seconds in (-86401, -1, 0, 1, 86400):
                try:
                    target = source + timedelta(seconds=seconds)
                except OverflowError:
                    continue
                expected = (f'{target.year:04}{target.month:02}{target.day:02}'
                            f'{target.hour:02}{target.minute:02}{target.second:02}')
                with self.subTest(canonical=canonical, seconds=seconds):
                    result = shift_date(date(canonical), Decimal(seconds))
                    self.assertEqual(write(result), '{"D",' + expected + '}')
                    self.assertEqual(date_difference(result, date(canonical)), Decimal(seconds))

    def test_difference_spans_entire_supported_range_exactly(self):
        minimum, maximum = date('00010101000000'), date('99991231235959')
        expected = Decimal('315537897599')
        self.assertEqual(date_difference(maximum, minimum), expected)
        self.assertEqual(date_difference(minimum, maximum), expected.copy_negate())
        self.assertEqual(date_difference(shift_date(minimum, Decimal('0.0001')), minimum),
                         Decimal('0.0001'))

    def test_components_and_presentation_ignore_subsecond_storage(self):
        for suffix in ('0', '0.0001', '0.5', '0.9999'):
            value = shift_date(self.base, Decimal(suffix))
            self.assertEqual(tuple(component(value, name) for name in FIELDS),
                             tuple(Decimal(n) for n in (2024, 2, 29, 12, 34, 56)))
            self.assertTrue(all(type(component(value, name)) is Decimal for name in FIELDS))
            self.assertEqual(to_string(value), '29.02.2024 12:34:56')
        previous = shift_date(self.base, Decimal('-0.0001'))
        self.assertEqual(component(previous, 'second'), Decimal(55))
        self.assertEqual(write(previous), '{"D",20240229123455}')
        self.assertEqual(to_string(date('00010101000000')), '01.01.0001 0:00:00')
        self.assertFalse(value_is_filled(date('00010101000000')))
        self.assertTrue(value_is_filled(shift_date(date('00010101000000'), Decimal('0.0001'))))

    def test_host_decimal_context_cannot_round_or_signal_any_date_operation(self):
        minimum, maximum = date('00010101000000'), date('99991231235959')
        with localcontext() as context:
            context.prec, context.Emax, context.Emin = 1, 1, -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(parts(2024, 2, 29, 12, 34, '56.9'), self.base)
            shifted = shift_date(self.base, Decimal('123456.78905'))
            self.assertEqual(date_difference(shifted, self.base), Decimal('123456.7891'))
            self.assertEqual(date_difference(maximum, minimum), Decimal('315537897599'))
            self.assertEqual(component(shifted, 'year'), Decimal(2024))
            self.assertEqual(read(write(self.base)), self.base)
            self.assertFalse(any(context.flags.values()))

    def test_nonfinite_and_non_native_arithmetic_arguments_fail(self):
        for invalid in (None, True, False, '1', 1, 1.0, object(),
                        Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity')):
            with self.subTest(kind=type(invalid)), self.assertRaises((TypeError, ValueError)):
                shift_date(self.base, invalid)
        for invalid in (None, True, Decimal(1), BASE_TEXT, 1, object()):
            for operation in (lambda: shift_date(invalid, Decimal(1)),
                              lambda: date_difference(invalid, self.base),
                              lambda: date_difference(self.base, invalid),
                              lambda: component(invalid, 'year')):
                with self.subTest(kind=type(invalid)), self.assertRaises((TypeError, ValueError)):
                    operation()


class DateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_bilingual_constructor_component_and_type_aliases(self):
        for name in ('Date', 'Дата', 'dAtE', 'дАтА'):
            self.assertEqual(self.vm.execute(f'{name}(2024, 2, 29, 12, 34, 56)'), date(BASE_TEXT))
        self.vm.execute('value = Дата(2024, 2, 29, 12, 34, 56);')
        for aliases, expected in ((('Year', 'Год'), 2024), (('Month', 'Месяц'), 2),
                                  (('Day', 'День'), 29), (('Hour', 'Час'), 12),
                                  (('Minute', 'Минута'), 34), (('Second', 'Секунда'), 56)):
            for name in aliases:
                for alias in (name, name.swapcase()):
                    self.assertEqual(self.vm.execute(alias + '(value)'), Decimal(expected))
        for alias in ('Date', 'Дата', 'DATE', 'дата'):
            self.assertIs(self.vm.execute('Type(' + quote(alias) + ')'), BSLType.DATE)
        self.assertIs(self.vm.execute('ТипЗнч(value)'), BSLType.DATE)

    def test_operators_and_comparisons_use_full_ticks(self):
        self.vm.execute('base = Date(2024, 2, 29, 12, 34, 56); later = base + 0.0001;')
        for expression in ('base = Date("20240229123456")', 'later <> base',
                           'base < later', 'base <= later', 'later > base',
                           'later >= base', 'base <= base', 'base >= base',
                           'base <> 0', '0 <> base'):
            self.assertIs(self.vm.execute('(' + expression + ')'), True, expression)
        for expression in ('base = 0', '0 = base', 'base = False', 'base = Undefined'):
            self.assertIs(self.vm.execute('(' + expression + ')'), False, expression)
        self.assertEqual(self.vm.execute('later - base'), Decimal('0.0001'))
        self.assertEqual(self.vm.execute('later - 0.0001'), self.vm.variables['base'])
        self.assertEqual(self.vm.execute('base - -0.00005'), self.vm.variables['later'])
        self.assertEqual(self.vm.execute('base + -0.00005'),
                         shift_date(date(BASE_TEXT), Decimal('-0.0001')))

    def test_date_is_a_global_function_not_a_new_constructor(self):
        for expression in ('New Date', 'Новый Дата', 'New Date(2024, 2, 29)',
                           'New("Date")', 'New(Type("Date"))', 'New (Type("Дата"))'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)

    def test_unsupported_operators_and_host_reflection_do_not_leak(self):
        self.vm.execute('value = Date(2024, 2, 29);')
        for expression in ('1 + value', '1 - value', 'value + value', 'value * 1',
                           'value / 1', 'value % 1', '+value', '-value', 'Not value',
                           'Boolean(value)', 'Number(value)', 'value < 1', '1 < value',
                           'value > "20240229"', 'value()', 'value[0]', 'value.Year',
                           'value.ticks', 'value.__class__', 'value.__dict__',
                           'value.isoformat()', 'value.get_member("ticks")'):
            with self.subTest(expression=expression), self.assertRaises(BSLRuntimeError):
                self.vm.execute(expression)
        for code in ('value.ticks = 1;', 'If value Then Message(1); EndIf;',
                     'For Each item In value Do Message(item); EndDo;'):
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)

    def test_literals_parse_in_expressions_defaults_eval_and_execute(self):
        self.assertEqual(self.vm.execute("'2024-02-29 12:34:56'"), date(BASE_TEXT))
        self.assertEqual(self.vm.execute("('20240229' + 86400) - '20240229'"), Decimal(86400))
        self.vm.execute("""
            Function ReadDefault(Val value = '20240229123456') Return value; EndFunction
            Function Advance(value = '20240229123456') value = value + 1; Return value; EndFunction
            first = ReadDefault(); second = ReadDefault();
            advanced = Advance(); unchanged = ReadDefault(); again = Advance();
        """)
        self.assertEqual(self.vm.variables['first'], date(BASE_TEXT))
        self.assertEqual(self.vm.variables['second'], date(BASE_TEXT))
        self.assertEqual(self.vm.variables['advanced'], date('20240229123457'))
        self.assertEqual(self.vm.variables['again'], date('20240229123457'))
        self.assertEqual(self.vm.variables['unchanged'], date(BASE_TEXT))
        self.assertEqual(self.vm.execute('Eval(' + quote("'20240229123456'") + ')'), date(BASE_TEXT))
        self.vm.execute('executed = Undefined; Execute(' + quote("executed = '202402291234' + 56;") + ');')
        self.assertEqual(self.vm.variables['executed'], date(BASE_TEXT))

    def test_unterminated_literal_requests_more_input_at_original_location(self):
        for source in ("'", "'20240229", "saved = 1;\nvalue = '20240229"):
            with self.subTest(source=source), self.assertRaises(IncompleteInput) as caught:
                parse(source, '/virtual/dates.bsl')
            self.assertEqual(caught.exception.source, '/virtual/dates.bsl')
            self.assertNotIn('Traceback', str(caught.exception))
        with self.assertRaises(IncompleteInput):
            parse("Function F(x = '20240229")

    def test_invalid_complete_literals_are_parse_errors_before_side_effects(self):
        for literal in ("''", "'20230229'", "'2024022912'", "'202402291234567'",
                        "'00000101'", "'２０２４０２２９'"):
            self.vm.execute('saved = 0;')
            with self.subTest(literal=literal), self.assertRaises(BSLError) as caught:
                self.vm.execute('saved = 1; value = ' + literal + ';')
            self.assertNotIsInstance(caught.exception, IncompleteInput)
            self.assertEqual(self.vm.variables['saved'], Decimal(0))
        self.assertEqual(self.vm.execute("'20240229'"), date('20240229'))

    def test_dynamic_literal_failures_are_catchable_and_recover(self):
        for text in ("'20240229", "'20230229'", "'2024022912'", "'20240229' 1"):
            for name in ('Eval', 'Execute'):
                self.vm.execute('saved = 7; caught = False;')
                body = text if name == 'Eval' else 'saved = ' + text + ';'
                call = name + '(' + quote(body) + ')'
                code = 'saved = ' + call + ';' if name == 'Eval' else call + ';'
                self.vm.execute('Try ' + code + ' Except caught = True; EndTry;')
                self.assertTrue(self.vm.variables['caught'])
                self.assertEqual(self.vm.variables['saved'], Decimal(7))
        self.assertEqual(self.vm.execute('Eval("Date(2024, 2, 29)")'), date('20240229'))

    def test_literal_tokens_do_not_consume_comments_strings_or_following_operators(self):
        self.assertEqual(self.vm.execute('"\'20230229\'"'), "'20230229'")
        self.assertEqual(self.vm.execute("'20240229' // 'unfinished"), date('20240229'))
        self.assertEqual(self.vm.execute("'20240229'+1-'20240229'"), Decimal(1))
        tokens = Lexer("'20240229'; next = 1;", 'dates.bsl').tokens()
        self.assertEqual((tokens[0].line, tokens[0].column, tokens[0].source), (1, 1, 'dates.bsl'))
        self.assertEqual(tokens[1].kind, ';')
        self.assertEqual(type(parse_expression("'20240229'").value), BSLDate)

    def test_constructor_failures_preserve_target_and_recover(self):
        for expression in ('Date()', 'Date(2024, 2)', 'Date(2024, 2, 29, 12)',
                           'Date(2024, 2, 29, 12, 34)', 'Date(2024, 2, 29, , , 56)',
                           'Date(2023, 2, 29)', 'Date("2024-02-29")', 'Year(0)',
                           'Second()', 'Month(Date(2024, 2, 29), 1)'):
            self.vm.execute('saved = 7; caught = False;')
            with self.subTest(expression=expression):
                self.vm.execute('Try saved = ' + expression + '; Except caught = True; EndTry;')
                self.assertTrue(self.vm.variables['caught'])
                self.assertEqual(self.vm.variables['saved'], Decimal(7))
        self.assertEqual(self.vm.execute('Year(Date(2024, 2, 29))'), Decimal(2024))

    def test_registration_is_interpreter_local_and_does_not_rewrite_other_alias(self):
        self.vm.register_function('Date', lambda *arguments: 'override')
        self.assertEqual(self.vm.execute('Date(2024, 2, 29)'), 'override')
        self.assertEqual(self.vm.execute('Дата(2024, 2, 29)'), date('20240229'))
        self.assertEqual(Interpreter().execute('Date(2024, 2, 29)'), date('20240229'))


class DateCollectionAndCodecTests(unittest.TestCase):
    def test_type_identity_and_codec_use_the_native_date_uuid(self):
        value = date(BASE_TEXT)
        self.assertIs(type_of(value), BSLType.DATE)
        self.assertIs(type_by_name('Date'), BSLType.DATE)
        self.assertIs(type_by_name('Дата'), BSLType.DATE)
        self.assertEqual(write(BSLType.DATE), '{"T",' + DATE_UUID + '}')
        self.assertIs(read('{"T",' + DATE_UUID + '}'), BSLType.DATE)
        self.assertIs(type(read(DATE_PAYLOAD)), BSLDate)
        self.assertEqual(read(DATE_PAYLOAD), value)
        self.assertEqual(write(read(DATE_PAYLOAD)), DATE_PAYLOAD)

    def test_subseconds_survive_memory_but_are_deliberately_lost_in_stream(self):
        base = date(BASE_TEXT)
        for text in ('0.0001', '0.1234', '0.5', '0.9999'):
            value = shift_date(base, Decimal(text))
            self.assertNotEqual(value, base)
            self.assertEqual(write(value), DATE_PAYLOAD)
            self.assertEqual(read(write(value)), base)
            self.assertEqual(date_difference(value, read(write(value))), Decimal(text))

    def test_array_find_and_fixed_snapshot_use_tick_equality(self):
        base = date(BASE_TEXT)
        later = shift_date(base, Decimal('0.0001'))
        for collection in (array(base, later), BSLFixedArray(array(base, later))):
            self.assertEqual(collection.find(date(BASE_TEXT)), Decimal(0))
            self.assertEqual(collection.find(shift_date(date(BASE_TEXT), Decimal('0.0001'))), Decimal(1))
            self.assertIsNone(collection.find(Decimal(base.ticks)))
            self.assertIsNone(collection.find(BASE_TEXT))

    def test_map_keys_are_typed_values_not_identity_or_whole_second_payloads(self):
        base = date(BASE_TEXT)
        later = shift_date(base, Decimal('0.0001'))
        values = mapping((base, 'old'), (date(BASE_TEXT), 'replacement'),
                         (later, 'later'), (Decimal(base.ticks), 'number'),
                         (BASE_TEXT, 'text'), (False, 'boolean'))
        self.assertEqual(len(list(values)), 5)
        for collection in (values, BSLFixedMap(values), BSLMap(BSLFixedMap(values))):
            self.assertEqual(collection.get(date(BASE_TEXT)), 'replacement')
            self.assertEqual(collection.get(shift_date(date(BASE_TEXT), Decimal('0.0001'))), 'later')
            self.assertEqual(collection.get(Decimal(base.ticks)), 'number')
            self.assertEqual(collection.get(BASE_TEXT), 'text')
            self.assertEqual(collection.get(False), 'boolean')
        values.delete(date(BASE_TEXT))
        self.assertIsNone(values.get(base))
        self.assertEqual(values.get(later), 'later')

    def test_all_mutable_and_fixed_collection_codecs_accept_dates(self):
        base = date(BASE_TEXT)
        values = [array(base), BSLFixedArray(array(base)),
                  BSLStructure('When', base), BSLFixedStructure('When', base),
                  mapping((base, base)), BSLFixedMap(mapping((base, base))),
                  BSLKeyAndValue(base, base)]
        for value in values:
            with self.subTest(kind=type(value)):
                encoded = write(value)
                self.assertIn(DATE_PAYLOAD, encoded)
                restored = read(encoded)
                self.assertIs(type(restored), type(value))
                self.assertEqual(write(restored), encoded)
        restored = read(write(mapping((base, 'present'))))
        self.assertEqual(restored.get(date(BASE_TEXT)), 'present')

    def test_bsl_collection_indexing_find_fixed_copy_and_codec_roundtrip(self):
        vm = Interpreter()
        vm.execute('''
            original = Date(2024, 2, 29, 12, 34, 56); values = New Array;
            values.Add(original); values.Add(original + 0.0001);
            fixed = New FixedArray(values);
            record = New FixedStructure("When", fixed[0]);
            map = New Map; map.Insert(original, "first");
            map[Date("20240229123456")] = "second";
            frozen = New FixedMap(map);
            restored = ValueFromStringInternal(ValueToStringInternal(frozen));
        ''')
        self.assertEqual(vm.execute('values.Find(Date("20240229123456"))'), Decimal(0))
        self.assertEqual(vm.execute('fixed.Find(original + 0.0001)'), Decimal(1))
        self.assertTrue(vm.execute('(record.When = original)'))
        self.assertEqual(vm.execute('map.Count()'), Decimal(1))
        self.assertEqual(vm.execute('restored[Date("20240229123456")]'), 'second')

    def test_invalid_date_stream_shapes_fail_with_format_error(self):
        for payload in ('{"D"}', '{"D",}', '{"d",20240229123456}',
                        '{"D","20240229123456"}', '{"D",20240229}',
                        '{"D",202402291234}', '{"D",202402291234560}',
                        '{"D",+20240229123456}', '{"D",-20240229123456}',
                        '{"D",20240229123456.0}', '{"D",2.0240229123456e13}',
                        '{"D",2024-02-29T12:34:56}', '{"D",２０２４０２２９１２３４５６}',
                        '{"D",00000101000000}', '{"D",20230229000000}',
                        '{"D",20240229240000}', '{"D",20240229235960}',
                        '{"D",20240229123456,0}', '{"D",{20240229123456}}'):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, re.escape(FORMAT_ERROR)):
                read(payload)
        self.assertEqual(read(DATE_PAYLOAD), date(BASE_TEXT))


class DateUnprovenRangeTests(unittest.TestCase):
    def setUp(self):
        self.minimum = date('00010101000000')
        self.maximum = date('99991231235959')
        self.low = shift_date(self.minimum, Decimal(-1))
        self.high = shift_date(self.maximum, Decimal(1))

    def test_observed_scalar_endpoint_serialization_is_not_a_guessed_clamp(self):
        for boundary, endpoint in ((self.low, self.minimum), (self.high, self.maximum)):
            self.assertIs(type(boundary), BSLDate)
            self.assertIs(type_of(boundary), BSLType.DATE)
            self.assertEqual(write(boundary), write(endpoint))
            restored = read(write(boundary))
            self.assertEqual(restored, endpoint)
            self.assertEqual(date_difference(restored, endpoint), Decimal(0))

    def test_unknown_boundary_values_refuse_host_comparison_hash_and_presentation(self):
        for boundary in (self.low, self.high):
            for other in (boundary, self.minimum, self.maximum, Decimal(0), None, False, 'date'):
                for operation in (lambda: boundary == other, lambda: boundary != other,
                                  lambda: equal(boundary, other), lambda: equal(other, boundary)):
                    with self.subTest(boundary=write(boundary), other=type(other)), \
                            self.assertRaises(UnsupportedDateRange):
                        operation()
            for operation in (lambda: hash(boundary), lambda: str(boundary),
                              lambda: to_string(boundary), lambda: value_is_filled(boundary)):
                with self.assertRaises(UnsupportedDateRange):
                    operation()

    def test_unknown_boundaries_refuse_components_arithmetic_and_map_keys(self):
        for boundary in (self.low, self.high):
            for field in FIELDS:
                with self.assertRaises(UnsupportedDateRange):
                    component(boundary, field)
            for operation in (lambda: shift_date(boundary, Decimal(0)),
                              lambda: shift_date(boundary, Decimal(1)),
                              lambda: date_difference(boundary, self.minimum),
                              lambda: date_difference(self.maximum, boundary),
                              lambda: mapping((boundary, 'unknown')),
                              lambda: BSLMap().get(boundary),
                              lambda: BSLMap().delete(boundary),
                              lambda: BSLFixedMap(BSLMap()).get(boundary),
                              lambda: BSLArray().find(boundary),
                              lambda: BSLFixedArray(BSLArray()).find(boundary)):
                with self.assertRaises(UnsupportedDateRange):
                    operation()

    def test_unknown_boundary_nested_serialization_is_not_native_evidence(self):
        for boundary in (self.low, self.high):
            for value in (array(boundary), BSLFixedArray(array(boundary)),
                          BSLStructure('When', boundary), BSLFixedStructure('When', boundary),
                          mapping(('When', boundary)), BSLFixedMap(mapping(('When', boundary))),
                          BSLKeyAndValue('When', boundary), BSLKeyAndValue(boundary, None)):
                with self.subTest(container=type(value)), self.assertRaises(UnsupportedDateRange):
                    write(value)

    def test_fractional_crossings_and_final_partial_second_remain_unsupported(self):
        for original, delta in ((self.minimum, '-0.0001'), (self.minimum, '-1.0001'),
                                (self.maximum, '0.0001'), (self.maximum, '0.5'),
                                (self.maximum, '1.0001'),
                                (shift_date(self.minimum, Decimal('0.0001')), '-1'),
                                (shift_date(self.maximum, Decimal('-0.0001')), '1')):
            with self.subTest(delta=delta), self.assertRaises(UnsupportedDateRange):
                shift_date(original, Decimal(delta))

    def test_larger_integer_overshoots_are_not_inferred_from_one_second_probes(self):
        for original, delta in ((self.minimum, '-2'), (self.minimum, '-86400'),
                                (self.maximum, '2'), (self.maximum, '86400')):
            with self.subTest(delta=delta), self.assertRaises(UnsupportedDateRange):
                shift_date(original, Decimal(delta))

    def test_fractional_crossings_cannot_become_known_by_rounding_to_whole_seconds(self):
        base = date(BASE_TEXT)
        for magnitude in ('0.99995', '1.00001'):
            for original, negative in ((self.minimum, True), (self.maximum, False)):
                delta = Decimal(magnitude)
                if negative:
                    delta = delta.copy_negate()
                with self.subTest(delta=delta), self.assertRaises(UnsupportedDateRange):
                    shift_date(original, delta)
                # Identical inputs are safe away from the boundary and still
                # follow the established four-decimal half-away quantum.
                expected = Decimal(-1 if negative else 1)
                self.assertEqual(date_difference(shift_date(base, delta), base), expected)

    def test_runtime_boundary_errors_are_catchable_for_all_comparison_directions(self):
        vm = Interpreter()
        vm.variables['unknown'] = self.low
        vm.execute('boundaryMap = New Map;')
        expressions = ['String(unknown)', 'ValueIsFilled(unknown)', 'Year(unknown)',
                       'unknown + 0', 'unknown - Date(1, 1, 1)', 'Date(1, 1, 1) - unknown',
                       'boundaryMap.Get(unknown)']
        for operator in ('=', '<>', '<', '<=', '>', '>='):
            for other in ('unknown', 'Date(1, 1, 1)', '0', 'Undefined', 'False', '"date"'):
                expressions.extend((f'unknown {operator} {other}', f'{other} {operator} unknown'))
        for expression in expressions:
            with self.subTest(expression=expression):
                vm.execute('saved = 7; caught = False; Try saved = ' + expression +
                           '; Except caught = True; EndTry;')
                self.assertTrue(vm.variables['caught'])
                self.assertEqual(vm.variables['saved'], Decimal(7))
        self.assertIs(vm.execute('TypeOf(unknown)'), BSLType.DATE)
        self.assertEqual(vm.execute('ValueToStringInternal(unknown)'), '{"D",00010101000000}')


class DateDefensiveTests(unittest.TestCase):
    def test_extreme_decimal_metadata_fails_without_expanding_exponents(self):
        base = date(BASE_TEXT)
        for text in ('1e1000000', '-1e1000000'):
            value = Decimal(text)
            for operation in (lambda: shift_date(base, value),
                              lambda: date(value, Decimal(1), Decimal(1)),
                              lambda: date(Decimal(2024), Decimal(2), Decimal(29),
                                           Decimal(12), Decimal(34), value)):
                with self.subTest(text=text), self.assertRaises((TypeError, ValueError)):
                    operation()

    def test_extremely_small_deltas_are_quantized_without_allocating_huge_powers(self):
        base = date(BASE_TEXT)
        for text in ('1e-1000000', '-1e-1000000', '0e1000000', '-0e-1000000'):
            self.assertEqual(shift_date(base, Decimal(text)), base)
        self.assertEqual(parts(2024, 2, 29, 12, 34, '1e-1000000'),
                         date('20240229123400'))

    def test_date_resource_limits_reject_oversized_coefficients_and_literal_payloads(self):
        long_number = Decimal((0, (1,) + (0,) * 4096, -4096))
        for operation in (lambda: shift_date(date(BASE_TEXT), long_number),
                          lambda: date(long_number, Decimal(1), Decimal(1)),
                          lambda: literal_date('-' * 4097 + BASE_TEXT)):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                operation()

    def test_host_tick_constructor_rejects_invalid_types_and_out_of_range_values(self):
        maximum = date('99991231235959').ticks
        for ticks in (True, False, None, Decimal(0), 0.0, '0', -1, maximum + 1):
            with self.subTest(ticks=ticks), self.assertRaises((TypeError, ValueError)):
                BSLDate(ticks)
        self.assertEqual(BSLDate(0), date('00010101000000'))
        self.assertEqual(BSLDate(maximum), date('99991231235959'))

    def test_hostile_values_never_run_conversion_or_iteration_hooks(self):
        calls = []

        class Hostile:
            def __str__(self):
                calls.append('str')
                raise AssertionError('Host conversion must not run')

            def __int__(self):
                calls.append('int')
                raise AssertionError('Host conversion must not run')

            def __iter__(self):
                calls.append('iter')
                raise AssertionError('Host iteration must not run')

        hostile = Hostile()
        base = date(BASE_TEXT)
        for operation in (lambda: date(hostile), lambda: literal_date(hostile),
                          lambda: date(hostile, Decimal(1), Decimal(1)),
                          lambda: shift_date(base, hostile), lambda: shift_date(hostile, Decimal(1)),
                          lambda: date_difference(hostile, base), lambda: component(hostile, 'year'),
                          lambda: type_of(hostile), lambda: write(hostile), lambda: read(hostile)):
            with self.assertRaises((TypeError, ValueError)):
                operation()
        self.assertEqual(calls, [])

    def test_string_and_decimal_subclasses_cannot_replace_validation(self):
        class HostString(str):
            def __str__(self):
                raise AssertionError('str called')

            def __iter__(self):
                raise AssertionError('iter called')

        class HostNumber(Decimal):
            def is_finite(self):
                raise AssertionError('is_finite called')

            def as_tuple(self):
                raise AssertionError('as_tuple called')

        for function in (date, literal_date, read):
            with self.assertRaises((TypeError, ValueError)):
                function(HostString(BASE_TEXT))
        for operation in (lambda: date(HostNumber(2024), Decimal(2), Decimal(29)),
                          lambda: shift_date(date(BASE_TEXT), HostNumber(1))):
            with self.assertRaises((TypeError, ValueError)):
                operation()

    def test_arbitrary_host_metaclass_is_not_mistaken_for_a_date(self):
        calls = []

        class PretendDate(type):
            def __eq__(cls, other):
                calls.append('type equality')
                raise AssertionError('Host metaclass equality must not run')

            def __hash__(cls):
                calls.append('type hash')
                raise AssertionError('Host metaclass hash must not run')

        class HostObject(BSLObject, metaclass=PretendDate):
            pass

        value = HostObject()
        for operation in (lambda: type_of(value), lambda: write(value),
                          lambda: date(value), lambda: shift_date(value, Decimal(1))):
            with self.assertRaises((TypeError, ValueError)):
                operation()
        collection = mapping((value, 'host'))
        self.assertEqual(collection.get(value), 'host')
        self.assertIsNone(collection.get(date(BASE_TEXT)))
        vm = Interpreter()
        vm.variables['host'] = value
        vm.variables['native'] = date(BASE_TEXT)
        for expression in ('(native = host)', '(host = native)'):
            self.assertIs(vm.execute(expression), False)
        for expression in ('native < host', 'host < native', 'native > host', 'host > native'):
            with self.assertRaises(BSLRuntimeError):
                vm.execute(expression)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
