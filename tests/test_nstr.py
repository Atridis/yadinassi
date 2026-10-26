"""Local NStr grammar/profile/resource policy; finite native witnesses are separate."""
from datetime import datetime
from decimal import Decimal
import locale
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi import strings
from yadinassi.native_targets import LINUX_8_3_27_1508, WINDOWS_8_3_27_2342
from yadinassi.values import BSLArray, NULL


class NStrLocalPolicyTests(unittest.TestCase):
    def test_both_aliases_case_variants_and_string_result(self):
        vm = Interpreter(lambda _: None)
        for name in ('НСтр', 'нСтР', 'NStr', 'nStR'):
            actual = vm.execute(name + '("en=\'second\';ru=\'first\'", "RU")')
            self.assertIs(type(actual), str)
            self.assertEqual(actual, 'first')

    def test_arbitrary_payloads_are_selected_not_captured_answer_lookups(self):
        for value in ('sun', 'новое', 'A;B=C', '😀e\u0301', '\r\n', '"quoted"'):
            source = "en='other';ru='" + value + "'"
            self.assertEqual(strings.nstr(source), value)
            self.assertEqual(strings.nstr(source, 'en'), 'other')
            self.assertEqual(strings.nstr(source, 'de'), '')

    def test_fixed_ru_profile_applies_only_to_empty_or_omitted_language(self):
        source = "en='English';ru='Русский'"
        self.assertEqual(strings.nstr(source), 'Русский')
        for value in ('', None, NULL):
            self.assertEqual(strings.nstr(source, value), 'Русский')
            self.assertEqual(strings.nstr("en='only'", value), '')
        for value in (' ', '\t', ' ru', 'ru ', 'en-US', '1'):
            self.assertEqual(strings.nstr(source, value), '')
        self.assertEqual(strings.nstr(source, 'EN'), 'English')
        self.assertEqual(strings.nstr("en='only'", 'en'), 'only')

    def test_default_never_reads_environment_system_locale_or_native_target(self):
        with patch.dict(os.environ, {'LANG': 'en_US.UTF-8', 'LANGUAGE': 'de',
                                     'LC_ALL': 'de_DE.UTF-8', 'SystemLanguage': 'EN',
                                     'YADINASSI_TIMEZONE': 'Etc/UTC'}), \
                patch.object(locale, 'getlocale', side_effect=AssertionError('locale lookup')), \
                patch.object(locale, 'setlocale', side_effect=AssertionError('locale mutation')):
            for target in (LINUX_8_3_27_1508, WINDOWS_8_3_27_2342):
                vm = Interpreter(lambda _: None, native_target=target)
                self.assertEqual(vm.execute('NStr("en=\'not default\';ru=\'profile\'")'), 'profile')

    def test_first_case_insensitive_duplicate_including_empty_wins(self):
        for source, expected in (("ru='first';RU='second'", 'first'),
                                 ("RU='second';ru='first'", 'second'),
                                 ("ru='';Ru='later'", ''),
                                 ("Да='first';да='later'", 'first')):
            code = 'да' if source.startswith('Да') else 'rU'
            self.assertEqual(strings.nstr(source, code), expected)

    def test_ascii_and_cyrillic_alphabet_case_without_unicode_expansion(self):
        self.assertEqual(strings.nstr("Ёж='animal';abc='latin'", 'ёЖ'), 'animal')
        self.assertEqual(strings.nstr("Ёж='animal';abc='latin'", 'ABC'), 'latin')
        for code in ('1', '_', 'ru1', 'ru_ru', 'ru-RU', 'ß', 'Σ', 'e\u0301'):
            self.assertEqual(strings.nstr(code + "='outside';ru='inside'", 'ru'), '')

    def test_horizontal_space_and_separators_do_not_modify_quoted_payload(self):
        source = " ;\tRU \t= \t'  preserved\t ' ; ; en='other';\t;"
        self.assertEqual(strings.nstr(source, 'ru'), '  preserved\t ')
        self.assertEqual(strings.nstr(' ; ; \t'), '')
        self.assertEqual(strings.nstr(''), '')

    def test_unquoted_local_grammar_trims_only_outer_space_and_tab(self):
        self.assertEqual(strings.nstr(' ru = \t bare = text \t; en=other ', 'ru'), 'bare = text')
        self.assertEqual(strings.nstr('ru=;en=other'), '')
        self.assertEqual(strings.nstr('ru=plain\u00a0'), 'plain\u00a0')
        self.assertEqual(strings.nstr('ru=;ru=later'), '')

    def test_doubled_apostrophes_are_unescaped_once(self):
        self.assertEqual(strings.nstr("ru='O''Reilly';en='x'"), "O'Reilly")
        self.assertEqual(strings.nstr("ru='''''';en='x'"), "''")
        self.assertEqual(strings.nstr("en='x'';=y';ru='selected'"), 'selected')

    def test_full_input_validation_rejects_early_and_late_malformed_entries(self):
        for source in ("ru='selected';en='bad'X", "ru='selected';en'bad'",
                       "ru='selected';en='unterminated", "ru='selected';en=bad'quote",
                       "bad'prefix;ru='selected'", "1='bad';ru='selected'",
                       "ru='selected';ru='unterminated", "ru='''", "ru'x'",
                       "ru='selected';\nen='outside grammar'"):
            with self.subTest(source=source):
                self.assertEqual(strings.nstr(source, 'ru'), '')
                self.assertEqual(strings.nstr(source, 'de'), '')

    def test_exact_admitted_scalars_use_existing_bounded_string_policy(self):
        # False/other Number values are local policy extensions, not additional
        # positive native coercion observations. Numeric codes remain invalid.
        self.assertEqual(strings.nstr("Да='yes';Нет='no'", True), 'yes')
        self.assertEqual(strings.nstr("Да='yes';Нет='no'", False), 'no')
        for value in (Decimal(0), Decimal(2), Decimal('-1.25'), True, False, None, NULL):
            self.assertEqual(strings.nstr(value, 'ru'), '')
        for value in (Decimal(0), Decimal(2), Decimal('-1.25')):
            self.assertEqual(strings.nstr("ru='not numeric'", value), '')
        for value in (Decimal('NaN'), Decimal('Infinity'), Decimal('1e1000000')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                strings.nstr(value, 'ru')

    def test_unsupported_types_never_execute_arbitrary_string_hooks(self):
        called = []
        class Poison:
            def __str__(self):
                called.append('str')
                raise AssertionError('arbitrary string hook')
        class StringSubclass(str):
            def __str__(self):
                called.append('subclass')
                raise AssertionError('subclass hook')
        values = (Poison(), StringSubclass('ru'), [], {}, BSLArray(), datetime(2024, 1, 1),
                  1, 1.0, b'ru', object())
        for value in values:
            with self.subTest(kind=type(value).__name__), self.assertRaises(TypeError):
                strings.nstr(value, 'ru')
            with self.subTest(kind=type(value).__name__), self.assertRaises(TypeError):
                strings.nstr("ru='x'", value)
        self.assertEqual(called, [])

    def test_arity_and_bad_objects_fail_without_poisoning_next_call(self):
        vm = Interpreter(lambda _: None)
        for expression in ('NStr()', 'NStr("", "ru", "en")', 'NStr(, "ru")',
                           'NStr(New Array, "ru")', 'NStr("ru=ok", New Structure)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute(expression)
            self.assertEqual(vm.execute('NStr("ru=ok")'), 'ok')

    def test_hostile_metaclass_equality_and_hash_hooks_never_admit_objects(self):
        called = []
        class MatchesAnyType(type):
            def __eq__(cls, other):
                called.append('metaclass equality')
                return True
            def __hash__(cls):
                raise AssertionError('metaclass hash hook')
        class RaisesOnEquality(type):
            def __eq__(cls, other):
                raise AssertionError('metaclass equality hook')
            def __hash__(cls):
                raise AssertionError('metaclass hash hook')
        for meta in (MatchesAnyType, RaisesOnEquality):
            class Hostile(metaclass=meta):
                def __str__(self):
                    called.append('arbitrary string')
                    return "ru='injected'"
            for value in (Hostile(), Hostile):
                with self.assertRaises(TypeError):
                    strings.nstr(value, 'ru')
                with self.assertRaises(TypeError):
                    strings.nstr("ru='selected'", value)
        self.assertEqual(called, [])

    def test_primitive_subclasses_cannot_spoof_exact_types_via_metaclass_equality(self):
        called = []
        class MatchesAnyType(type):
            def __eq__(cls, other):
                called.append('metaclass equality')
                return True
            def __hash__(cls):
                raise AssertionError('metaclass hash hook')
        class StringSubclass(str, metaclass=MatchesAnyType):
            def __str__(self):
                called.append('string subclass hook')
                return 'ru'
        class DecimalSubclass(Decimal, metaclass=MatchesAnyType):
            def is_zero(self):
                called.append('decimal presentation hook')
                return True
            def __str__(self):
                called.append('decimal string hook')
                return 'ru'
        for value in (StringSubclass("ru='injected'"), DecimalSubclass(1)):
            with self.assertRaises(TypeError):
                strings.nstr(value, 'ru')
            with self.assertRaises(TypeError):
                strings.nstr("ru='selected'", value)
        self.assertEqual(called, [])

    def test_code_limit_is_independent_and_applies_even_after_a_match(self):
        limit = strings._NSTR_MAX_CODE_UNITS
        self.assertEqual(limit, 128)
        code = 'r' * limit
        self.assertEqual(strings.nstr(code + "='bounded'", code), 'bounded')
        for source, language in (("ru='x'", code + 'r'),
                                 (code + "r='x'", 'ru'),
                                 ("ru='first';" + code + "r='later'", 'ru')):
            with self.assertRaises(ValueError):
                strings.nstr(source, language)

    def test_template_utf16_limit_is_explicit_not_the_observer_limit(self):
        limit = strings._NSTR_MAX_TEMPLATE_UNITS
        self.assertEqual(limit, 1_000_000)
        payload = 'x' * (limit - 5)
        self.assertEqual(len(strings.nstr("ru='" + payload + "'")), len(payload))
        with self.assertRaises(ValueError):
            strings.nstr("ru='" + payload + "x'")
        self.assertEqual(strings.nstr("ru='" + 'x' * 65 + "'"), 'x' * 65)
        astral = '😀' * ((limit - 6) // 2) + 'x'
        self.assertEqual(strings.nstr("ru='" + astral + "'"), astral)
        with self.assertRaises(ValueError):
            strings.nstr("ru='" + astral + "x'")

    def test_unicode_units_are_not_normalized_or_dropped(self):
        for value in ('e\u0301', '\u00e9', '\ud800', '\udfff', '\ud83d\ude00', '😀'):
            actual = strings.nstr("ru='" + value + "'")
            self.assertEqual(actual.encode('utf-16-le', 'surrogatepass'),
                             value.encode('utf-16-le', 'surrogatepass'))

    def test_scan_work_grows_linearly_without_timing_assertions(self):
        def work(source):
            events = 0
            def trace(frame, event, arg):
                nonlocal events
                if event == 'line' and frame.f_code.co_filename == strings.__file__:
                    events += 1
                return trace
            previous = sys.gettrace()
            try:
                sys.settrace(trace)
                strings.nstr(source)
            finally:
                sys.settrace(previous)
            return events
        for source in (lambda n: "ru='" + 'x' * n + "';en='tail'",
                       lambda n: "ru='first';" + "en='skip';" * n + "ru='last'",
                       lambda n: "ru='" + "''" * n + "'",
                       lambda n: "ru='first';en='" + 'x' * n):
            small, large = work(source(128)), work(source(256))
            self.assertGreater(large, small)
            self.assertLessEqual(large, small * 2 + 100)

    def test_imported_modules_repeated_calls_and_eval_keep_fixed_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Words.bsl').write_text('Function Pick() Export\n'
                'Return NStr("en=other;ru=module");\nEndFunction', encoding='utf-8')
            vm = Interpreter(lambda _: None)
            self.assertEqual(vm.execute('// #Import Words.bsl\nWords.Pick()',
                                        str(root / 'Main.bsl')), 'module')
            self.assertEqual(vm.execute('Words.Pick()'), 'module')
            self.assertEqual(vm.execute('Eval("NStr(""en=other;ru=eval"")")'), 'eval')

    def test_server_and_dual_contexts_share_no_mutable_default_state(self):
        output = []
        vm = Interpreter(output.append)
        vm.execute('''
&AtServer
Function ServerWord()
    Return NStr("en=server-other;ru=server");
EndFunction
&AtClientAtServerNoContext
Function DualWord()
    Return NStr("en=dual-other;ru=dual");
EndFunction
&AtServer
Function ServerDual()
    Return DualWord();
EndFunction
Message(NStr("en=client-other;ru=client"));
Message(ServerWord()); Message(DualWord()); Message(ServerDual());
Message(NStr("en=explicit;ru=not-selected", "en")); Message(ServerWord());
''')
        self.assertEqual(output, ['client', 'server', 'dual', 'dual', 'explicit', 'server'])


if __name__ == '__main__':
    unittest.main()
