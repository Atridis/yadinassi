"""Offline full-collections adapter contracts, not evidence of native 1C parity."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from yadinassi import BSLError, Interpreter
import test_native_1c_full_stage as fixtures

suite = fixtures.suite
ROOT = fixtures.REPOSITORY
NONCE = fixtures.NONCE
COUNT = 1021
DECLARATIONS = (8, 36, 64, 80, 113, 145, 154, 163, 168, 198, 217, 222, 238, 242, 249, 257, 265, 274, 338, 342, 358, 411, 491, 513, 534, 561, 584, 594, 598, 622, 636, 641, 649, 661, 685, 726, 741, 755, 924, 937, 1027, 1038, 1044, 1050, 1063, 1074, 1120, 1152, 1276, 1286, 1292, 1302, 1326, 1364, 1393, 1408, 1441, 1451, 1487, 1496, 1504, 1523, 1533, 1555, 1563, 1593, 1636, 1675, 1718, 1739, 1795, 1815, 1850, 1871, 1918, 1945, 1953, 1973, 2000, 2011, 2018, 2055, 2067, 2154, 2161, 2181, 2192, 2208, 2234, 2253, 2266, 2295, 2309, 2317, 2340, 2350, 2358, 2399, 2409, 2428, 2462, 2481, 2489, 2511, 2520, 2526, 2532, 2539, 2546, 2552, 2557, 2562, 2567, 2578, 2584, 2693, 2720, 2733, 2824, 2858, 2868, 2897, 2923, 2969, 3027, 3047, 3100, 3110, 3129, 3152, 3211, 3220, 3224, 3229, 3265, 3284, 3306, 3314, 3368, 3395, 3427)
SITES = (164, 602, 613, 615, 618, 4330, 4368, 4418, 4448, 4461, 4472, 4480, 4485, 4508, 4510, 4542)
CAPTURE = 'КоллекцииКлиентЗахват'
VARIABLES = ('Выход', 'КоллекцииКлиентСообщения', 'КоллекцииКлиентСимволы')
LOCAL_DECLARATIONS = {
    'Функция КонструкторИндексовПробы(Знач Вид)\n': '    Перем Объект;\n',
    'Функция КодекИндексовПробы(Знач Вид)\n': '    Перем Объект;\n',
    'Функция ПоляСпискаПробы(Знач Список)\n': '    Перем Элементы;\n',
    'Функция КодекСпискаПробы(Знач Вид)\n': '    Перем Объект;\n',
}


def interpreter_module(module: str) -> str:
    """Private offline shim for the three form-variable directives, not statements.

    Standalone supports client routines, but not client-decorated form variables.
    Strip exactly those three directives only in this test copy. Production keeps
    all three, and the native compiler/round-trip/witness establishes actual context.
    """
    for name in VARIABLES:
        annotated = '&НаКлиенте\nПерем ' + name + ';\n'
        if module.count(annotated) != 1:
            raise AssertionError('missing or duplicated form-variable declaration')
        module = module.replace(annotated, 'Перем ' + name + ';\n', 1)
    return module


class ClientCollectionsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.source_path = ROOT / 'integrational_tests/tests/collections.bsl'
        self.template_path = ROOT / suite.CLIENT_SOURCE
        self.source = self.source_path.read_bytes()
        self.template = self.template_path.read_bytes()
        # Offline fixtures model the LF-pinned Linux executor under Git autocrlf.
        # Never normalize production input or edit repository source fixtures.
        if os.name == 'nt':
            self.source = self.source.replace(b'\r\n', b'\n')
            self.template = self.template.replace(b'\r\n', b'\n')
        self.template = suite.client_parity_template(self.template)

    def module(self):
        return suite.client_collections_module(self.source, self.template).decode('utf-8-sig')

    def vm(self):
        vm = Interpreter(output=lambda _: self.fail('adapter leaked a native message'))
        vm.execute(interpreter_module(self.module()))
        return vm

    def test_source_template_and_message_count_are_pinned(self):
        self.assertEqual(suite.digest(self.source),
                         '0f36f76a44f63f9623a3c204c5cace3dd4d4328b4465f3bb002f660fc96e684b')
        self.assertEqual(suite.digest(self.template),
                         '4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328')
        self.assertEqual(suite.digest(self.source), suite.CLIENT_COLLECTIONS_SOURCE_SHA256)
        self.assertEqual(suite.digest(self.template), suite.CLIENT_COLLECTIONS_TEMPLATE_SHA256)
        self.assertEqual(suite.CLIENT_COLLECTIONS_MESSAGE_COUNT, COUNT)
        generated = suite.client_collections_module(self.source, self.template)
        self.assertTrue(generated.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r', generated)

    def test_offline_crlf_checkout_canonicalization_does_not_relax_production(self):
        # Simulate a Windows checkout on every platform, only in the test copy.
        crlf = self.source.replace(b'\n', b'\r\n')
        canonical = crlf.replace(b'\r\n', b'\n')
        self.assertEqual(suite.digest(canonical), suite.CLIENT_COLLECTIONS_SOURCE_SHA256)
        self.assertEqual(suite.client_collections_module(canonical, self.template),
                         suite.client_collections_module(self.source, self.template))
        with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
            suite.client_collections_module(crlf, self.template)

    def test_historical_exclude_sources_cannot_claim_current_native_route(self):
        from scripts.native_historical_replay import (
            without_fill_exclude_order_probes, without_fill_exclude_probes,
        )
        for inverse in (without_fill_exclude_order_probes, without_fill_exclude_probes):
            source = inverse(self.source.decode('utf-8-sig')).encode('utf-8-sig')
            with self.subTest(inverse=inverse.__name__), self.assertRaisesRegex(
                    suite.FullError, '^invalid_input$'):
                suite.client_collections_module(source, self.template)

    def test_descriptor_helper_pins_fail_under_rebased_hash(self):
        lines = self.source.splitlines(keepends=True)
        for index in (2693, 2718, 2720, 2731, 2733, 2820, 4542):
            changed = lines.copy()
            changed[index] = b'// removed descriptor source pin\n'
            source = b''.join(changed)
            with self.subTest(index=index), mock.patch.object(
                    suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256', suite.digest(source)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_collections_module(source, self.template)

    def test_fill_include_helper_pins_fail_under_rebased_hash(self):
        lines = self.source.splitlines(keepends=True)
        for index in (64, 76):
            changed = lines.copy()
            changed[index] = b'// removed INCLUDE helper source pin\n'
            source = b''.join(changed)
            with self.subTest(index=index), mock.patch.object(
                    suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256', suite.digest(source)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_collections_module(source, self.template)

    def test_exclude_observer_and_order_pins_fail_with_raw_or_rebased_hash(self):
        # These exact source-only observations remain byte-strict even when a
        # future edit deliberately updates only the outer source hash.
        mutants = (
            ('Missing,First,Last,Copy', 'First,Missing,Last,Copy'),
            ('First,Missing,Last,Copy', 'First,Last,Missing,Copy'),
            ('Неопределено, "Missing");', 'Неопределено, "First");'),
            ('Перем Приемник, Источник, Статус, ЗначениеMissing, ЕстьMissing;',
             'Перем Приемник, Источник, Статус, ЗначениеMissing;'),
            ('ЗначениеВСтрокуВнутр(Приемник.Copy)', 'ЗначениеВСтрокуВнутр(Приемник.Last)'),
            ('ПроверитьПозициюИсключения("first");', 'ПроверитьПозициюИсключения("between");'),
            ('ПроверитьПозициюИсключения("between");', 'ПроверитьПозициюИсключения("first");'),
            ('// End FillPropertyValues EXCLUDE source-order discriminator helpers.', '// removed'),
            ('// End FillPropertyValues EXCLUDE checkpoint observations.', '// removed'),
            ('Приемник.Вставить("Missing", 4);', 'Приемник.Вставить("Missing", 5);'),
        )
        for before, after in mutants:
            source = self.source.replace(before.encode(), after.encode(), 1)
            self.assertNotEqual(source, self.source)
            for rebase in (False, True):
                with self.subTest(before=before, rebase=rebase), mock.patch.object(
                        suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256',
                        suite.digest(source) if rebase else suite.digest(self.source)):
                    with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                        suite.client_collections_module(source, self.template)

    def test_raw_source_tampering_is_rejected_without_normalization(self):
        lines = self.source.splitlines(keepends=True)
        swapped = lines.copy()
        swapped[357], swapped[358] = swapped[358], swapped[357]
        removed_helper = lines[:19] + lines[26:]
        mutants = [
            b''.join(lines[:357] + lines[358:]),
            b''.join(lines[:357] + [lines[357]] + lines[357:]),
            b''.join(swapped), b''.join(removed_helper),
            b''.join(lines[:19] + lines[19:26] + lines[19:]),
            self.source + b'\n', self.source[:-1],
            self.source.replace('Массив'.encode(), 'МассивПодмена'.encode(), 1),
            self.source.replace(b'[error]', b'[ok]', 1),
            self.source.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + self.source,
            self.source.replace('Сообщить('.encode(), 'Message('.encode(), 1),
            self.source + '\n&НаСервере\nПроцедура Вызов()\nКонецПроцедуры\n'.encode(),
            self.source + '\nВызватьНаСервере();\n'.encode(),
        ]
        for source in mutants:
            with self.subTest(digest=suite.digest(source)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_collections_module(source, self.template)

    def test_template_changes_and_substitution_are_rejected(self):
        marker = '&НаКлиенте\nФункция ВычислитьПробу()\n'.encode()
        mutants = [
            self.template + b'\n', self.template.replace(b'6 * 7', b'42'),
            self.template.replace('НаКлиенте'.encode(), 'НаСервере'.encode(), 1),
            self.template.replace(b'"client"', b'"server"', 1),
            self.template.replace(marker, b'', 1),
            self.template + marker + 'КонецФункции\n'.encode(),
            self.template.replace(b'\n', b'\r\n'), b'\xef\xbb\xbf' + self.template,
            self.source,
        ]
        for template in mutants:
            with self.subTest(digest=suite.digest(template)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_collections_module(self.source, template)
        with self.assertRaises(suite.FullError):
            suite.client_collections_module(self.template, self.source)

    def test_structure_and_case_insensitive_collisions_fail_even_if_hash_is_rebased(self):
        # Future source rebasing must deliberately revisit these shape checks too.
        lines = self.source.splitlines(keepends=True)
        replacements = [(4, 'Процедура Подмена()\n'.encode()),
                        (2688, 'КонецПроцедуры\n'.encode()),
                        (164, lines[164].replace('Строка'.encode(), 'String'.encode())),
                        (3505, lines[3506]),
                        (1, 'Перем ДругойВыход;\n'.encode()),
                        (3, '#Область Другая\n'.encode()),
                        (190, '#Если Клиент Тогда\n'.encode()),
                        (0, '&НаКлиенте\n'.encode()),
                        (0, '&НаСервере\n'.encode()),
                        (0, '#Если Сервер Тогда\n'.encode())]
        replacements += [(0, ('// ' + name.swapcase() + '\n').encode())
                         for name in (CAPTURE, *VARIABLES[1:], 'КоллекцииКлиентВыполнить')]
        for index, replacement in replacements:
            changed = lines.copy()
            changed[index] = replacement
            source = b''.join(changed)
            with self.subTest(index=index, replacement=replacement):
                with mock.patch.object(suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256', suite.digest(source)):
                    with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                        suite.client_collections_module(source, self.template)
        for replacement in ('// коллекцииклиентзахват\n',
                            '&НаКлиенте\nФункция ВычислитьПробу()\nКонецФункции\n'):
            template = self.template + replacement.encode()
            with mock.patch.object(suite, 'CLIENT_COLLECTIONS_TEMPLATE_SHA256', suite.digest(template)):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_collections_module(self.source, template)

    def test_global_region_helper_and_site_additions_fail_under_rebased_hash(self):
        lines = self.source.splitlines(keepends=True)
        mutants = [
            b''.join(lines[:2] + ['Перем Второй;\n'.encode()] + lines[2:]),
            self.source.replace('Перем Выход;'.encode(), 'Перем Выход Экспорт;'.encode()),
            self.source.replace('#Region FixedCollectionProbes'.encode(), b'#Region Other'),
            self.source.replace('#EndRegion'.encode(), b'#EndIf', 1),
            self.source.replace('КонецФункции'.encode(), 'КонецПроцедуры'.encode(), 1),
            self.source.replace('Сообщить('.encode(), 'сообщить('.encode(), 1),
            self.source.replace('Показать("'.encode(), 'КоллекцииКлиентЗахват("'.encode(), 1),
        ]
        for source in mutants:
            self.assertNotEqual(source, self.source)
            with self.subTest(digest=suite.digest(source)):
                with mock.patch.object(suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256', suite.digest(source)):
                    with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                        suite.client_collections_module(source, self.template)
        template = self.template + '// вЫхОд collision\n'.encode()
        with mock.patch.object(suite, 'CLIENT_COLLECTIONS_TEMPLATE_SHA256', suite.digest(template)):
            with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                suite.client_collections_module(self.source, template)

    def test_reverse_generated_source_preserves_all_lines_regions_and_global(self):
        module = self.module()
        original = self.source.decode('utf-8-sig')
        start = module.index(original.splitlines(keepends=True)[0])
        end = module.index('КонецПроцедуры\n\n&НаКлиенте\nФункция ВычислитьПробу()', start)
        restored = module[start:end]
        self.assertEqual(restored.count('&НаКлиенте\n'), len(DECLARATIONS) + 1)
        self.assertEqual(restored.count(CAPTURE + '('), len(SITES))
        restored = restored.replace('&НаКлиенте\n', '')
        for helper, declaration in LOCAL_DECLARATIONS.items():
            self.assertEqual(restored.count(helper + declaration), 1)
            restored = restored.replace(helper + declaration, helper, 1)
        restored = restored.replace('Процедура КоллекцииКлиентВыполнить()\n', '')
        restored = restored.replace(CAPTURE + '(', 'Сообщить(')
        first, rest = restored.split('\n', 1)
        restored = first + '\nПерем Выход;\n' + rest
        self.assertEqual(restored.encode('utf-8-sig'), self.source)
        self.assertEqual(len(restored.splitlines()), 4846)
        self.assertEqual(len(re.findall(r'^#', restored, re.M)), 16)
        self.assertEqual(module.count('Перем Выход;'), 1)
        self.assertTrue(module.startswith('&НаКлиенте\nПерем Выход;\n'))
        self.assertLess(module.index('Перем Выход;'), module.index('Процедура'))
        self.assertIn('Вычислить(', restored)
        self.assertIn('Выполнить(', restored)

    def test_all_declarations_and_calls_are_direct_client_only_without_new_conversion(self):
        module = self.module()
        declarations = re.findall(r'^([^\n]+)\n((?:Процедура|Функция|Перем) [^\n]+)', module, re.M)
        self.assertEqual(len(declarations), 150)
        self.assertTrue(all(directive == '&НаКлиенте' for directive, _ in declarations))
        self.assertNotIn('&НаСервере', module)
        self.assertNotIn('Сообщить(', module)
        for conversion in (r'(?<!\w)Строка\(', r'(?<!\w)String\('):
            self.assertEqual(re.findall(conversion, module),
                             re.findall(conversion, self.source.decode()))
        self.assertIn('КоллекцииКлиентСообщения.Добавить(Текст);', module)
        self.assertIn('КоллекцииКлиентСообщения.Количество() >= 1021', module)
        self.assertIn(f'> {(suite.MAX_OUTPUT - COUNT) // 4}', module)
        self.assertIn('КоллекцииКлиентВыполнить();', module)
        self.assertIn('Возврат КоллекцииКлиентСообщения;', module)
        self.assertEqual(module.count('ВычислитьПробу();'), 1)
        self.assertEqual(module.count(CAPTURE + '('), len(SITES) + 1)

    def test_only_four_pinned_helper_locals_shadow_form_context(self):
        module = self.module()
        self.assertEqual(module.count('    Перем Объект;\n'), 3)
        self.assertEqual(module.count('    Перем Элементы;\n'), 1)
        for helper, declaration in LOCAL_DECLARATIONS.items():
            self.assertEqual(module.count('&НаКлиенте\n' + helper + declaration), 1)
            self.assertEqual(self.source.decode().count(helper), 1)
            self.assertNotIn(helper + declaration, self.source.decode())
        self.assertNotIn('    Перем Выход;', module)
        self.assertNotIn('Перем Объект;\n&НаКлиенте', module)

    def test_form_context_globals_are_not_overwritten_by_source_helpers(self):
        expected = []
        Interpreter(output=expected.append).execute(self.source.decode())
        vm = Interpreter(output=lambda _: self.fail('adapter leaked a native message'))
        vm.execute('Перем Объект; Перем Элементы; '
                   'Объект = "form-object-sentinel"; Элементы = "form-items-sentinel";')
        vm.execute(interpreter_module(self.module()))
        captured = list(vm.execute('ВычислитьПробу()'))
        self.assertEqual(captured, expected)
        self.assertEqual(len(captured), 1021)
        self.assertEqual(vm.execute('Объект'), 'form-object-sentinel')
        self.assertEqual(vm.execute('Элементы'), 'form-items-sentinel')

    def test_missing_hygiene_reproduces_ambient_name_binding_leak(self):
        # Offline control models writable form names, not native read-only errors.
        # Removing only the four additions must make the two collisions visible.
        module = self.module()
        for helper, declaration in LOCAL_DECLARATIONS.items():
            module = module.replace(helper + declaration, helper, 1)
        vm = Interpreter(output=lambda _: self.fail('control leaked a message'))
        vm.execute('Перем Объект; Перем Элементы; '
                   'Объект = "form-object-sentinel"; Элементы = "form-items-sentinel";')
        vm.execute(interpreter_module(module))
        vm.execute('КодекИндексовПробы("empty")')
        vm.execute('ПоляСпискаПробы(Новый СписокЗначений)')
        self.assertNotEqual(vm.execute('Объект'), 'form-object-sentinel')
        self.assertNotEqual(vm.execute('Элементы'), 'form-items-sentinel')

    def test_witness_writer_and_onopen_are_byte_unchanged(self):
        module = self.module()
        harness = self.template.decode()
        witness = harness[:harness.index('&НаКлиенте\nФункция ВычислитьПробу()')]
        suffix = harness[harness.index('&НаКлиенте\nПроцедура ЗаписатьПробу'):]
        self.assertIn(witness, module)
        self.assertTrue(module.endswith(suffix))
        self.assertNotIn('Значения.Добавить(6 * 7);', module)

    def test_complete_interpreter_capture_matches_unmodified_source_without_filtering(self):
        before = {path: path.read_bytes() for path in (self.source_path, self.template_path)}
        expected = []
        Interpreter(output=expected.append).execute(self.source.decode())
        captured = list(self.vm().execute('ВычислитьПробу()'))
        self.assertEqual(len(expected), COUNT)
        self.assertEqual(len(captured), COUNT)
        self.assertTrue(all(type(item) is str for item in captured))
        self.assertEqual(captured, expected)  # Every string, including protected error paths.
        self.assertEqual(suite.serialize_messages(captured), suite.serialize_messages(expected))
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_capture_repeated_execution_resets_without_reusing_previous_results(self):
        vm = self.vm()
        first = vm.execute('ВычислитьПробу()')
        expected = list(first)
        second = vm.execute('ВычислитьПробу()')
        self.assertIsNot(first, second)
        self.assertEqual(list(first), expected)
        self.assertEqual(list(second), expected)
        self.assertEqual(len(expected), COUNT)

    def test_capture_rejects_non_strings_before_conversion_or_mutation(self):
        vm = self.vm()
        vm.execute('КоллекцииКлиентСообщения = Новый Массив; КоллекцииКлиентСимволы = 0;')
        for value in ('1', 'Истина', 'Неопределено', 'Null', 'Новый Массив'):
            with self.subTest(value=value):
                with self.assertRaises(BSLError):
                    vm.execute(f'{CAPTURE}({value});')
                self.assertEqual(vm.execute('КоллекцииКлиентСообщения.Количество()'), 0)
                self.assertEqual(vm.execute('КоллекцииКлиентСимволы'), 0)
        vm.execute(f'{CAPTURE}(" Привет " + Символ(13) + Символ(10) + "конец ");')
        self.assertEqual(list(vm.execute('КоллекцииКлиентСообщения')), [' Привет \r\nконец '])

    def test_capture_message_and_character_limits_fail_before_mutation(self):
        vm = self.vm()
        vm.execute('КоллекцииКлиентСообщения = Новый Массив; КоллекцииКлиентСимволы = 0;')
        vm.execute(f'Для i = 1 По {COUNT} Цикл {CAPTURE}(""); КонецЦикла;')
        with self.assertRaises(BSLError):
            vm.execute(f'{CAPTURE}("");')
        self.assertEqual(vm.execute('КоллекцииКлиентСообщения.Количество()'), COUNT)
        budget = (suite.MAX_OUTPUT - COUNT) // 4
        vm.execute('КоллекцииКлиентСообщения = Новый Массив; '
                   f'КоллекцииКлиентСимволы = {budget - 1};')
        vm.execute(f'{CAPTURE}("я");')
        with self.assertRaises(BSLError):
            vm.execute(f'{CAPTURE}("я");')
        self.assertEqual(list(vm.execute('КоллекцииКлиентСообщения')), ['я'])
        self.assertEqual(vm.execute('КоллекцииКлиентСимволы'), budget)


class ClientCollectionsMarkerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / 'marker.json'
        if os.name == 'nt':
            reader = mock.patch.object(suite, 'secure_bytes', fixtures.portable_fixture_bytes)
            reader.start()
            self.addCleanup(reader.stop)

    def record(self, values=None, phase='completed'):
        return {'schema': 1, 'nonce': NONCE, 'phase': phase, 'witness': 'client',
                'values': [f'line {i}' for i in range(COUNT)] if values is None else values}

    def read(self, record, phase='completed'):
        self.path.write_text(json.dumps(record), encoding='utf-8')
        return suite.client_collections_marker(self.path, NONCE, phase)

    def test_empty_report_adds_finite_mismatch_with_independent_mutable_diagnostics(self):
        first = suite.empty_collections_report()
        self.assertEqual(first, {**suite.empty_dates_report(), 'mismatch': None})
        self.assertEqual(first['status'], 'not_started')
        self.assertIsNone(first['output_sha256'])
        self.assertIsNone(first['output_size'])
        self.assertIsNone(first['message_count'])
        self.assertIsNot(first['process_diagnostics'], suite.empty_collections_report()['process_diagnostics'])

    def test_entered_empty_and_completed_exact_string_count(self):
        entered = self.record([], 'entered')
        self.assertEqual(self.read(entered, 'entered'), entered)
        completed = self.record()
        self.assertEqual(self.read(completed), completed)
        self.assertEqual(self.read(self.record([''] * COUNT))['values'], [''] * COUNT)

    def test_missing_extra_wrong_types_and_schema_fail_closed(self):
        edits = [lambda r: r['values'].pop(), lambda r: r['values'].append('extra'),
                 lambda r: r['values'].__setitem__(0, 1),
                 lambda r: r['values'].__setitem__(0, True),
                 lambda r: r['values'].__setitem__(0, None),
                 lambda r: r['values'].__setitem__(0, []),
                 lambda r: r['values'].__setitem__(0, {}),
                 lambda r: r.update(values=None), lambda r: r.update(values={}),
                 lambda r: r.update(schema=True), lambda r: r.update(schema=1.0),
                 lambda r: r.update(schema=2), lambda r: r.update(witness='server'),
                 lambda r: r.update(witness=True), lambda r: r.update(nonce='0' * 32),
                 lambda r: r.update(phase='error'), lambda r: r.update(extra=1)]
        edits += [lambda r, key=key: r.pop(key)
                  for key in ('schema', 'nonce', 'phase', 'witness', 'values')]
        for edit in edits:
            record = self.record()
            edit(record)
            with self.subTest(edit=edit):
                with self.assertRaisesRegex(suite.FullError, '^invalid_result$'):
                    self.read(record)
        for record, phase in ((self.record(['unexpected'], 'entered'), 'entered'),
                              (self.record([], 'completed'), 'completed'),
                              (self.record(), 'entered'),
                              (self.record([], 'entered'), 'completed')):
            with self.assertRaises(suite.FullError):
                self.read(record, phase)

    def test_reordered_multiline_and_trailing_space_values_are_preserved(self):
        original = self.record()
        changed = self.record()
        changed['values'].reverse()
        accepted = self.read(changed)
        self.assertEqual(accepted, changed)
        self.assertNotEqual(suite.serialize_messages(accepted['values']),
                            suite.serialize_messages(original['values']))
        changed['values'][:6] = ['first\r\nsecond', '', ' Привет\rworld ', '\\n\\r',
                                 'trailing  ', 'last\n']
        accepted = self.read(changed)
        self.assertEqual(accepted, changed)
        self.assertTrue(suite.serialize_messages(accepted['values']).startswith(
            'first\nsecond\n\n Привет\nworld \n\\n\\r\ntrailing  \nlast\n\n'.encode()))

    def test_trailing_bytes_duplicate_keys_invalid_unicode_nonfinite_and_depth_fail(self):
        data = json.dumps(self.record()).encode()
        bad = [data + b' garbage', data + b'{}', data[:-1], b'[]', b'null', b'\xff',
               data.replace(b'line 0', b'\\ud800'), data.replace(b'line 0', b'\\udfff'),
               data.replace(b'line 0', b'\xff'),
               data.replace(b'"line 0"', b'NaN'),
               data.replace(b'"line 0"', b'Infinity'), b'[' * 20 + b']' * 20]
        for key in ('schema', 'nonce', 'phase', 'witness', 'values'):
            value = self.record()[key]
            field = json.dumps(key).encode() + b': ' + json.dumps(value).encode()
            bad.append(data.replace(field, field + b', ' + field, 1))
        for raw in bad:
            with self.subTest(raw=raw[:60]):
                self.path.write_bytes(raw)
                with self.assertRaises(suite.FullError):
                    suite.client_collections_marker(self.path, NONCE, 'completed')

    def test_byte_bound_includes_one_lf_per_message_and_multibyte_utf8(self):
        values = [''] * COUNT
        values[0] = 'a' * (suite.MAX_OUTPUT - COUNT)
        self.assertEqual(len(suite.serialize_messages(self.read(self.record(values))['values'])),
                         suite.MAX_OUTPUT)
        for first in (values[0] + 'a', 'я' * (suite.MAX_OUTPUT // 2),
                      '😀' * (suite.MAX_OUTPUT // 4),
                      '\r\n' * (suite.MAX_OUTPUT // 2 + 1)):
            with self.subTest(length=len(first)):
                with self.assertRaises(suite.FullError):
                    self.read(self.record([first] + [''] * (COUNT - 1)))

    def test_private_json_envelope_cap_is_independent_of_decoded_output_cap(self):
        record = self.record(['\x00' * (suite.MAX_RESULT // 6)] + [''] * (COUNT - 1))
        self.assertLess(len(suite.serialize_messages(record['values'])), suite.MAX_OUTPUT)
        with self.assertRaises(suite.FullError):
            self.read(record)

    def test_invalid_requested_nonce_phase_and_replayed_nonce_fail(self):
        self.read(self.record())
        for nonce, phase in ((NONCE, 'error'), ('../bad', 'completed'),
                             ('A' * 32, 'completed'), ('0' * 31, 'completed'),
                             (None, 'completed')):
            with self.subTest(nonce=nonce, phase=phase):
                with self.assertRaisesRegex(suite.FullError, '^invalid_input$'):
                    suite.client_collections_marker(self.path, nonce, phase)
        with self.assertRaisesRegex(suite.FullError, '^invalid_result$'):
            suite.client_collections_marker(self.path, 'f' * 32, 'completed')

    def test_missing_empty_directory_and_oversize_fail_closed(self):
        with self.assertRaises(suite.FullError):
            suite.client_collections_marker(self.path, NONCE, 'completed')
        for raw in (b'', b' ' * (suite.MAX_RESULT + 1)):
            self.path.write_bytes(raw)
            with self.assertRaises(suite.FullError):
                suite.client_collections_marker(self.path, NONCE, 'completed')
        with self.assertRaises(suite.FullError):
            suite.client_collections_marker(self.path.parent, NONCE, 'completed')


if __name__ == '__main__':
    unittest.main()
