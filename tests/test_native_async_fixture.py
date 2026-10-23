"""Offline source contracts only; no claim of native BSL compilation/execution."""
import ast
import hashlib
import json
import re
from pathlib import Path

import unittest

REPOSITORY = Path(__file__).resolve().parents[1]
SNIPPET = REPOSITORY / 'scripts' / 'native_1c_bootstrap' / 'full_suite.py'
# Independent frozen inventory/DAG, not derived from the implementation's constants.
FROZEN_SPEC = {'slots': [4, 3, 5, 3, 4, 7, 3, 3],
 'cases': [{'id': 0,
            'required': [10, 11, 12, 13, 14, 15, 16, 17, 18],
            'edges': [[10, 11],
                      [11, 12],
                      [10, 13],
                      [13, 14],
                      [12, 14],
                      [14, 15],
                      [15, 16],
                      [16, 17],
                      [17, 18]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 1,
            'required': [10, 11, 12, 13, 14, 15, 16, 17, 25, 26],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 25],
                      [25, 26],
                      [26, 13],
                      [13, 14],
                      [14, 17],
                      [10, 15],
                      [15, 16],
                      [16, 17]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 2,
            'required': [10,
                         11,
                         12,
                         13,
                         14,
                         15,
                         16,
                         17,
                         18,
                         19,
                         20,
                         21,
                         22,
                         23,
                         24,
                         25,
                         26,
                         27,
                         28],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 25],
                      [25, 26],
                      [26, 13],
                      [13, 14],
                      [14, 22],
                      [10, 15],
                      [15, 16],
                      [16, 17],
                      [17, 18],
                      [18, 27],
                      [27, 28],
                      [28, 19],
                      [19, 20],
                      [20, 23],
                      [16, 21],
                      [21, 22],
                      [22, 23],
                      [23, 24]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 3,
            'required': [10, 13, 16],
            'edges': [[10, 11],
                      [10, 12],
                      [11, 13],
                      [12, 13],
                      [13, 14],
                      [13, 15],
                      [14, 16],
                      [15, 16],
                      [16, 17],
                      [16, 18]],
            'choices': [[11, 12], [14, 15], [17, 18]],
            'error_slot_phases': [[0, 3], [1, 4], [2, 5]]},
           {'id': 4,
            'required': [10, 11, 12, 13, 14, 15, 16, 19],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 13],
                      [11, 14],
                      [14, 16],
                      [10, 15],
                      [15, 16],
                      [16, 17],
                      [16, 18],
                      [17, 19],
                      [18, 19],
                      [13, 19]],
            'choices': [[17, 18]],
            'error_slot_phases': []},
           {'id': 5,
            'required': [10, 11, 12, 13, 14, 15, 16],
            'edges': [[10, 11], [11, 12], [12, 13], [13, 14], [14, 16], [10, 15], [15, 16]],
            'choices': [],
            'error_slot_phases': []},
           {'id': 6,
            'required': [10, 11, 12],
            'edges': [[10, 11],
                      [11, 12],
                      [10, 13],
                      [12, 14],
                      [13, 15],
                      [15, 16],
                      [15, 17],
                      [12, 16],
                      [12, 17],
                      [16, 18],
                      [17, 18],
                      [18, 19],
                      [18, 20],
                      [12, 19],
                      [12, 20]],
            'choices': [[13, 14], [16, 17], [19, 20]],
            'error_slot_phases': [[0, 0], [1, 1], [2, 2]]},
           {'id': 7,
            'required': [10, 11, 12, 13, 14, 15, 16, 17, 18],
            'edges': [[10, 11],
                      [11, 12],
                      [12, 13],
                      [13, 14],
                      [14, 15],
                      [15, 16],
                      [16, 17],
                      [17, 18]],
            'choices': [],
            'error_slot_phases': [[2, 6]]}]}


def literal_sources():
    tree = ast.parse(SNIPPET.read_text(encoding='utf-8'))
    names = ('ASYNC_TEMPLATE', 'ASYNC_CASE_SOURCES', 'ASYNC_FIXTURE_SHA256')
    result = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    assert target.id not in result
                    result[target.id] = ast.literal_eval(node.value)
    assert set(result) == set(names)
    return result


def make_fixture():
    sources = literal_sources()
    # Test the repository generator definition in an isolated namespace. This is
    # offline test code only: production host extraction must not execute staged
    # code, and the independent host protocol tests cover that boundary.
    namespace = dict(sources)
    import json
    namespace.update(hashlib=hashlib, json=json)
    class FullError(Exception):
        pass
    namespace['FullError'] = FullError
    namespace['generated_module'] = lambda raw: raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').encode('utf-8-sig')
    tree = ast.parse(SNIPPET.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'async_client_module')
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SNIPPET), 'exec'), namespace)
    return namespace


def routine(source, name):
    # BSL mixed-case routine declarations, deliberately no BSL execution here.
    pattern = (r'(?im)^\s*(?:Асинх\s+|Async\s+)?(?:Процедура|Функция|Procedure|Function)\s+'
               + re.escape(name) + r'\([^\n]*\)\s*\n(.*?)^\s*(?:КонецПроцедуры|КонецФункции|EndProcedure|EndFunction)\s*$')
    match = re.search(pattern, source, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)
    assert match, name
    return match.group(1)



class AsyncFixtureSourcesTest(unittest.TestCase):
    def test_entry_failure_log_is_finite_private_stage_only(self):
        handler = routine(make_fixture()['ASYNC_TEMPLATE'], 'ПриОткрытии')
        stages = re.findall(r'ЭтапВхода = "([a-z]+)";', handler)
        self.assertEqual(stages, ['request', 'witness', 'initialize', 'entered', 'root'])
        operations = ['АсинхЗапрос = AsyncReadRequest(ЭтапВхода);',
                      'АсинхКонтекст = АсинхКонтекстПробы();',
                      'АсинхТрасса = Новый Массив;',
                      'АсинхЗаписатьВход();', 'АсинхКореньПробы();']
        for index, (stage, operation) in enumerate(zip(stages, operations)):
            start = handler.index('ЭтапВхода = "' + stage + '";')
            self.assertLess(start, handler.index(operation))
            if index + 1 < len(stages):
                self.assertLess(handler.index(operation), handler.index('ЭтапВхода = "' + stages[index + 1] + '";'))
        catch = handler.split('Исключение', 1)[1]
        self.assertEqual(re.findall(r'Сообщить\(([^\n]+)\);', catch),
                         ['"ASYNC-ENTRY-FAILURE:" + ЭтапВхода'])
        for forbidden in ('ОписаниеОшибки(', 'ИнформацияОбОшибке(',
                          'ЗавершитьРаботуСистемы(', 'АсинхЗаписатьЗавершение('):
            self.assertNotIn(forbidden, handler)

    def test_request_substages_are_fixed_by_reference_without_semantic_changes(self):
        from test_native_async_protocol import suite
        template = make_fixture()['ASYNC_TEMPLATE']
        body = routine(template, 'AsyncReadRequest')
        labels = ['request_open', 'request_object', 'request_key', 'request_value',
                  'request_end', 'request_fields', 'request_nonce', 'request_paths']
        all_labels = ['request', 'witness', 'initialize', 'entered', 'root', *labels]
        self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS,
                         {'ASYNC-ENTRY-FAILURE:' + label: 13 + index
                          for index, label in enumerate(all_labels)})
        self.assertIn('Function AsyncReadRequest(ЭтапВхода)\n', template)
        self.assertEqual(re.findall(r'ЭтапВхода = "([a-z_]+)";', body), labels)
        operations = ['Reader = New JSONReader;', 'Request = New Structure;',
                      'AsyncExpectToken(Reader, JSONValueType.PropertyName);',
                      'If Key = "schema" Or Key = "version" Then',
                      'AsyncExpectToken(Reader, JSONValueType.ObjectEnd);',
                      'If Not Request.Property("schema")', 'If StrLen(Request.nonce)',
                      'If StrLen(Request.entered)']
        for index, (label, operation) in enumerate(zip(labels, operations)):
            start = body.index('ЭтапВхода = "' + label + '";')
            self.assertLess(start, body.index(operation))
            if index + 1 < len(labels):
                self.assertLess(body.index(operation), body.index('ЭтапВхода = "' + labels[index + 1] + '";'))
            self.assertEqual(suite.ASYNC_ENTRY_LOG_MARKERS['ASYNC-ENTRY-FAILURE:' + label], 18 + index)
        restored = re.sub(r'^\s*ЭтапВхода = "request_[a-z]+";\n', '', template, flags=re.M)
        restored = restored.replace('Function AsyncReadRequest(ЭтапВхода)', 'Function AsyncReadRequest()')
        restored = restored.replace('АсинхЗапрос = AsyncReadRequest(ЭтапВхода);', 'АсинхЗапрос = AsyncReadRequest();')
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'a6df293877c28a19eb70d8bdddcd784145584af874a01886e82e5ea1289c3994')
        cases = make_fixture()['ASYNC_CASE_SOURCES']
        self.assertEqual(hashlib.sha256(json.dumps(cases, ensure_ascii=False,
                         separators=(',', ':')).encode()).hexdigest(),
                         '09edb17d68c0ff7a5462498b132afa5c2b202912abdcb48e33ae1c676a39c075')

    def test_sources_are_literal_and_generator_is_fixed(self):
        fixture = make_fixture()
        assert isinstance(fixture['ASYNC_TEMPLATE'], str)
        assert type(fixture['ASYNC_CASE_SOURCES']) is tuple
        assert len(fixture['ASYNC_CASE_SOURCES']) == 8
        assert all(type(item) is str for item in fixture['ASYNC_CASE_SOURCES'])
        template = fixture['ASYNC_TEMPLATE']
        assert template.count('__ASYNC_CASE_ID__') == 1
        assert template.count('__ASYNC_CASE_SOURCE__') == 1
        hashes = set()
        for case in range(8):
            result = fixture['async_client_module'](case)
            expected = (template.replace('__ASYNC_CASE_ID__', str(case))
                        .replace('__ASYNC_CASE_SOURCE__', fixture['ASYNC_CASE_SOURCES'][case])).encode('utf-8-sig')
            assert result == expected
            assert b'__ASYNC_CASE_' not in result
            hashes.add(hashlib.sha256(result).hexdigest())
        assert len(hashes) == 8


    def test_case_selector_rejects_nonexact_integer(self):
        fixture = make_fixture()
        for invalid in [True, False, -1, 8, 1.0, '0', None, [], {}, b'1']:
            with self.assertRaises(fixture['FullError']):
                fixture['async_client_module'](invalid)


    def test_generator_rejects_mutated_placeholder_and_literal_types(self):
        fixture = make_fixture()
        original = fixture['ASYNC_TEMPLATE']
        for changed in (original + '__ASYNC_CASE_ID__', original.replace('__ASYNC_CASE_SOURCE__', ''), b'bad'):
            fixture['ASYNC_TEMPLATE'] = changed
            with self.assertRaises(fixture['FullError']):
                fixture['async_client_module'](0)
        fixture['ASYNC_TEMPLATE'] = original
        fixture['ASYNC_CASE_SOURCES'] = tuple(['__ASYNC_CASE_SOURCE__'] * 8)
        with self.assertRaises(fixture['FullError']):
            fixture['async_client_module'](0)


    def test_root_owns_completion_and_only_exit(self):
        fixture = make_fixture()
        template = fixture['ASYNC_TEMPLATE']
        on_open = routine(template, 'ПриОткрытии')
        assert 'АсинхКореньПробы();' in on_open
        assert on_open.index('АсинхЗаписатьВход();') < on_open.index('АсинхКореньПробы();')
        assert 'ЗавершитьРаботуСистемы' not in on_open
        assert 'АсинхЗаписатьЗавершение' not in on_open
        root = routine(template, 'АсинхКореньПробы')
        assert template.count('ЗавершитьРаботуСистемы(Ложь);') == 1
        assert root.index('Результат = Ждать Тест;') < root.index('АсинхСобытие(3);')
        assert root.index('Отброшено = Ждать АсинхОжидания[Индекс];') < root.index('АсинхЗаписатьЗавершение(2, 12);')
        assert root.index('АсинхСобытие(4);') < root.index('АсинхЗаписатьЗавершение(1, 0);')
        assert root.index('АсинхЗаписатьЗавершение(1, 0);') < root.index('ЗавершитьРаботуСистемы(Ложь);')
        terminal = routine(template, 'АсинхЗаписатьЗавершение')
        assert terminal.index('Если АсинхЗавершено') < terminal.index('АсинхЗавершено = Истина;')
        assert terminal.count('АсинхЗапрос.completed') == 1
        assert template.count('Запись.ОткрытьФайл(АсинхЗапрос.completed, "UTF-8", Ложь);') == 1
        assert 'Если Статус <> 1 Тогда' in terminal


    def test_no_executable_request_or_server_path(self):
        fixture = make_fixture()
        source = fixture['ASYNC_TEMPLATE'] + ''.join(fixture['ASYNC_CASE_SOURCES'])
        # Strip comments and strings before forbidden identifier scan.
        cleaned = re.sub(r'"(?:""|[^"\n])*"', '""', source)
        cleaned = re.sub(r'//[^\n]*', '', cleaned)
        assert not re.search(r'(?i)\b(?:Eval|Execute|Вычислить|Выполнить)\s*\(', cleaned)
        assert not re.search(r'(?i)&(?:НаСервере|AtServer)', cleaned)
        assert 'ExportProbeAfterCreate' not in source
        assert 'NativePostCreate' not in source
        request = routine(fixture['ASYNC_TEMPLATE'], 'AsyncReadRequest')
        assert 'For Index = 1 To 5 Do' in request
        assert 'If Request.Property(Key)' in request
        assert 'JSONValueType.PropertyName' in request
        assert 'JSONValueType.ObjectEnd' in request
        assert 'If Reader.Read() Then Raise' in request
        assert 'Key = "case"' not in request
        assert 'Key = "code"' not in request
        assert 'Key = "procedure"' not in request


    def test_values_are_exact_bounded_and_nonstringified(self):
        fixture = make_fixture()
        capture = routine(fixture['ASYNC_TEMPLATE'], 'АсинхСохранить')
        for type_name in ('Неопределено', 'Null', 'Булево', 'Число', 'Строка', 'Обещание'):
            assert f'Тип("{type_name}")' in capture
        assert 'Данные <> Цел(Данные)' in capture
        assert 'Данные < -999999 Или Данные > 999999' in capture
        assert 'Словарь.Найти(Данные)' in capture
        assert '7,17,11,12,21,22,31,33' in capture
        assert not re.search(r'(?i)\b(?:Строка|String|Формат|Format)\s*\(', capture)
        assert 'АсинхНесовместимо = Истина;' in capture


    def test_error_fields_are_guarded_and_keep_saved_error(self):
        fixture = make_fixture()
        capture = routine(fixture['ASYNC_TEMPLATE'], 'АсинхСохранитьОшибку')
        for field in ('Description', 'Code', 'AdditionalInformation', 'Cause', 'ModuleName', 'LineNumber', 'InitialString'):
            assert re.search(r'Попытка [^\n]*СохраненнаяОшибка\.' + field + r'[^\n]*Исключение КонецПопытки;', capture)
        assert 'ИнформацияОбОшибке()' not in capture
        assert 'ErrorInfo()' not in capture
        assert 'СохраненнаяОшибка.IsErrorOfCategory(ErrorCategory.ConfigurationError)' in capture
        assert 'Категория = АсинхПара(3, 1)' in capture
        assert 'Категория = АсинхПара(0, Null)' in capture
        assert 'АсинхОшибки.Количество() >= 3' in capture
        bounded = routine(fixture['ASYNC_TEMPLATE'], 'АсинхПоле')
        assert 'СтрДлина(Данные) > 512' in bounded
        assert 'GetBinaryDataFromString(Данные, "UTF-8", Ложь).Size() > 512' in bounded
        assert 'Тип("ИнформацияОбОшибке")' in bounded
        assert not re.search(r'(?i)\b(?:Строка|String|Формат|Format)\s*\(', bounded)


    def test_fixed_event_vocab_and_slots_match_frozen_spec(self):
        fixture = make_fixture()
        import json
        spec = FROZEN_SPEC
        for case, source in enumerate(fixture['ASYNC_CASE_SOURCES']):
            events = [int(x) for x in re.findall(r'АсинхСобытие\((\d+)\)', source)]
            # Common 0,1,3,4 are emitted by the pinned template, 2 by each test.
            expected = {2, *spec['cases'][case]['required']}
            expected.update(e for choice in spec['cases'][case]['choices'] for e in choice)
            if case == 6:
                expected.update((15, 18))  # Only when the rejecting call returns.
            assert set(events) == expected
            assert len(events) == len(set(events))
            assert f"АсинхНачатьТест({spec['slots'][case]});" in source
            assert len(spec['cases'][case]['required']) + len(spec['cases'][case]['choices']) + 5 <= 24


    def test_leaves_siblings_and_inner_are_retained_and_joined(self):
        fixture = make_fixture()
        cases = fixture['ASYNC_CASE_SOURCES']
        assert 'Лист = АсинхЛист();\n    АсинхУдержать(Лист);' in cases[1]
        assert 'АсинхЛистЗначение = Ждать Лист;' in cases[1]
        siblings = cases[2]
        for branch in ('А', 'Б'):
            assert f'{branch} = АсинхВетвь{branch}();\n    АсинхУдержать({branch});' in siblings
            assert f'Значение{branch} = Ждать {branch};' in siblings
        assert siblings.count('АсинхСбой = Истина;') == 3
        assert 'ПовторА = Ждать А;' in siblings
        inner = cases[4]
        assert 'АсинхУдержать(АсинхВнутреннее);' in inner
        assert inner.index('ВнутреннийРезультат = Ждать АсинхВнутреннее;') > inner.index('АсинхСобытие(18);')
        assert 'АсинхСобытие(19);' in inner
        assert 'Пока' not in inner


    def test_scalar_and_rejection_paths_do_not_normalize_errors(self):
        fixture = make_fixture()
        scalar = fixture['ASYNC_CASE_SOURCES'][3]
        for slot, phase in enumerate((3, 4, 5)):
            assert f'АсинхСохранитьОшибку({slot}, {phase}, Ошибка);' in scalar
        reject = fixture['ASYNC_CASE_SOURCES'][6]
        assert 'Если ВызовВернулся Тогда' in reject
        for slot in range(3):
            assert f'АсинхСохранитьОшибку({slot}, {slot}, Ошибка);' in reject
        assert '"ASYNC-REJECT", КатегорияОшибки.ОшибкаКонфигурации' in reject
        assert '"ASYNC-CODE", "ASYNC-DETAIL", Неопределено' in reject


    def test_val_and_english_grammar_are_distinct(self):
        fixture = make_fixture()
        parameters = fixture['ASYNC_CASE_SOURCES'][5]
        assert 'АсинхПараметры(Первый, Знач Второй, Знач МассивДанных, ПоУмолчанию = 7)' in parameters
        assert 'АсинхСохранить(2, ПервыйФакт);' in parameters
        assert 'АсинхСохранить(3, ВторойФакт);' in parameters
        english = fixture['ASYNC_CASE_SOURCES'][7]
        assert 'AsYnC FuNcTiOn' in english
        assert 'Return AsyncAddOne((aWaIt Leaf));' in english
        handled = routine(english, 'AsyncHandledProcedure')
        assert not re.search(r'(?i)\b(?:Await|Ждать)\b', re.sub(r'//[^\n]*', '', handled))
        assert handled.index('АсинхСобытие(16);') < handled.index('АсинхСобытие(17);')
        assert 'AsyncHandledProcedure();\n    АсинхСобытие(18);' in english


    def test_every_module_declaration_is_client_only(self):
        fixture = make_fixture()
        for case, body in enumerate(fixture['ASYNC_CASE_SOURCES']):
            source = fixture['ASYNC_TEMPLATE'] + body
            # Each variable/routine declaration has its own client directive.
            # No declaration may inherit a server/default compilation context.
            declarations = list(re.finditer(
                r'(?im)^\s*(?:(?:Асинх|Async)\s+)?'
                r'(?:Перем|Var|Функция|Процедура|Function|Procedure)\b', source))
            self.assertGreater(len(declarations), 3)
            for declaration in declarations:
                previous = source[:declaration.start()].rstrip().splitlines()[-1].strip()
                self.assertIn(previous.casefold(), ('&наклиенте', '&atclient'), (case, previous))
            directives = re.findall(r'(?im)^\s*&([^\n]+)', source)
            self.assertTrue(all(d.casefold() in ('наклиенте', 'atclient') for d in directives))
            self.assertEqual(re.findall(r'(?im)^\s*#([^\n]+)', source),
                             ['Если Клиент Тогда', 'Иначе', 'КонецЕсли'])

    def test_all_native_calls_and_constructors_have_closed_inventory(self):
        fixture = make_fixture()
        source = fixture['ASYNC_TEMPLATE'] + ''.join(fixture['ASYNC_CASE_SOURCES'])
        # Fixed snippets have no multiline strings. Remove strings/comments in
        # one pass so quoted comment markers cannot hide executable code.
        cleaned = re.sub(r'"(?:""|[^"\n])*"|//[^\n]*', '', source)
        declared = set(re.findall(
            r'(?im)^\s*(?:(?:Асинх|Async)\s+)?'
            r'(?:Функция|Процедура|Function|Procedure)\s+(\w+)\(', cleaned))
        calls = set(re.findall(r'(?u)(?<![\w])(\w+)\s*\(', cleaned)) - declared
        expected = {
            'Close', 'ErrorInfo', 'GetBinaryDataFromString', 'Insert',
            'IsErrorOfCategory', 'Mid', 'OpenFile', 'Property', 'Raise', 'Read',
            'Size', 'StrFind', 'StrLen', 'Type', 'TypeOf', 'ВызватьИсключение',
            'Добавить', 'Если', 'ЗавершитьРаботуСистемы', 'Закрыть', 'ЗаписатьJSON',
            'ИначеЕсли', 'ИнформацияОбОшибке', 'Количество', 'Найти', 'ОткрытьФайл',
            'Сообщить', 'СтрДлина', 'СтрРазделить', 'Структура', 'Тип', 'ТипЗнч', 'Цел',
        }
        self.assertEqual(calls, expected)
        self.assertEqual(set(re.findall(r'(?i)\b(?:Новый|New)\s+(\w+)', cleaned)),
                         {'Массив', 'Структура', 'Structure', 'JSONReader', 'ЗаписьJSON'})
        # Synchronous transport is outside the measured Async cases; no native
        # UI/network/file async producer, timer, notification or detached task.
        io_lines = [line.strip() for line in source.splitlines()
                    if re.search(r'\.(?:OpenFile|ОткрытьФайл)\(', line)]
        self.assertEqual(io_lines, [
            'Reader.OpenFile(LaunchParameter);',
            'Запись.ОткрытьФайл(АсинхЗапрос.entered, "UTF-8", Ложь);',
            'Запись.ОткрытьФайл(АсинхЗапрос.completed, "UTF-8", Ложь);',
        ])

    def test_every_created_function_promise_is_retained_and_awaited(self):
        fixture = make_fixture()
        for case, body in enumerate(fixture['ASYNC_CASE_SOURCES']):
            source = fixture['ASYNC_TEMPLATE'] + body
            names = set(re.findall(r'(?im)^\s*(?:Асинх|Async)\s+'
                                   r'(?:Функция|Function)\s+(\w+)\(', source))
            creation_count = 0
            for name in names:
                creations = list(re.finditer(
                    r'(?m)^\s*(\w+) = ' + re.escape(name) + r'\([^\n]*\);\n', source))
                self.assertEqual(len(creations), 1, (case, name))
                for creation in creations:
                    creation_count += 1
                    variable = creation.group(1)
                    self.assertTrue(source[creation.end():].lstrip().startswith(
                        f'АсинхУдержать({variable});'), (case, name, variable))
                    self.assertRegex(source, r'(?i)(?:Ждать|Await)\s+' + re.escape(variable) + r'\b')
            # The failure drain is finite: five statically unique function calls
            # at most, all earlier producers are in this retained registry.
            self.assertLessEqual(creation_count, 5)
            procedures = set(re.findall(r'(?im)^\s*(?:Асинх|Async)\s+'
                                        r'(?:Процедура|Procedure)\s+(\w+)\(', source))
            self.assertEqual(procedures, {'АсинхКореньПробы'} |
                             ({'AsyncHandledProcedure'} if case == 7 else set()))

    def test_generator_hash_pin_rejects_any_unreviewed_source_mutation(self):
        fixture = make_fixture()
        template = fixture['ASYNC_TEMPLATE']
        cases = fixture['ASYNC_CASE_SOURCES']
        fixture['ASYNC_TEMPLATE'] = template.replace('&НаКлиенте', '&НаСервере', 1)
        with self.assertRaises(fixture['FullError']):
            fixture['async_client_module'](0)
        fixture['ASYNC_TEMPLATE'] = template
        for index in range(8):
            altered = list(cases)
            altered[index] += '\n// unreviewed modification\n'
            fixture['ASYNC_CASE_SOURCES'] = tuple(altered)
            # Every requested case binds the entire fixed inventory, not only
            # the selected case's source.
            with self.assertRaises(fixture['FullError']):
                fixture['async_client_module']((index + 1) % 8)
        fixture['ASYNC_CASE_SOURCES'] = cases
        fixture['ASYNC_FIXTURE_SHA256'] = '0' * 64
        with self.assertRaises(fixture['FullError']):
            fixture['async_client_module'](0)

    def test_implementation_inventory_and_dag_match_independent_freeze(self):
        tree = ast.parse(SNIPPET.read_text(encoding='utf-8'))
        names = {'ASYNC_SLOTS', 'ASYNC_REQUIRED', 'ASYNC_EDGES'}
        values = {node.targets[0].id: ast.literal_eval(node.value)
                  for node in tree.body if isinstance(node, ast.Assign)
                  and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                  and node.targets[0].id in names}
        self.assertEqual(set(values), names)
        self.assertEqual(values['ASYNC_SLOTS'], tuple(FROZEN_SPEC['slots']))
        self.assertEqual(values['ASYNC_REQUIRED'],
                         tuple(tuple(case['required']) for case in FROZEN_SPEC['cases']))
        self.assertEqual(values['ASYNC_EDGES'],
                         tuple(tuple(tuple(edge) for edge in case['edges'])
                               for case in FROZEN_SPEC['cases']))


    def test_category_membership_false_is_not_unavailable(self):
        capture = routine(make_fixture()['ASYNC_TEMPLATE'], 'АсинхСохранитьОшибку')
        guarded = re.search(
            r'Попытка\s*// Category membership[^\n]*\n(.*?)Исключение КонецПопытки;',
            capture, re.DOTALL).group(1)
        expected = (
            'Если СохраненнаяОшибка.IsErrorOfCategory(ErrorCategory.ConfigurationError) Тогда\n'
            '    Категория = АсинхПара(3, 1);\n'
            'Иначе\n'
            '    Категория = АсинхПара(3, 2);\n'
            'КонецЕсли;'
        )
        self.assertEqual('\n'.join(line[8:] if line.startswith('        ') else line
                                   for line in guarded.strip('\n').splitlines()).strip(), expected)
        self.assertLess(capture.index('Категория = АсинхПара(0, Null);'),
                        capture.index('СохраненнаяОшибка.IsErrorOfCategory'))
        self.assertEqual(capture.count('Категория = АсинхПара('), 3)

    def test_category_three_way_projection_keeps_exact_distinct_fingerprints(self):
        from test_native_async_protocol import full, private_error, suite
        fingerprints = set()
        for category, public_tag in (([3, 1], 1), ([3, 2], 2), ([0, None], 3)):
            with self.subTest(category=category):
                descriptor = private_error(6)
                descriptor['category'] = category
                raw = json.dumps(descriptor, sort_keys=True, separators=(',', ':'),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8')
                expected = [6, 2, 2, 2, public_tag, 0, hashlib.sha256(raw).hexdigest()]
                self.assertEqual(suite._async_private_error(descriptor), expected)
                self.assertEqual(full.validate_async_private_descriptor(descriptor), expected)
                fingerprints.add(expected[-1])
        self.assertEqual(len(fingerprints), 3)

    def test_fixture_and_all_host_module_pins_match_independent_bytes(self):
        from test_native_async_protocol import full
        fixture = literal_sources()
        template, cases = fixture['ASYNC_TEMPLATE'], fixture['ASYNC_CASE_SOURCES']
        aggregate = hashlib.sha256(json.dumps([template, cases], ensure_ascii=False,
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(aggregate, fixture['ASYNC_FIXTURE_SHA256'])
        identity = {
            'template': hashlib.sha256(template.encode('utf-8')).hexdigest(),
            'modules': [hashlib.sha256(template.replace('__ASYNC_CASE_ID__', str(index))
                        .replace('__ASYNC_CASE_SOURCE__', case).encode('utf-8-sig')).hexdigest()
                        for index, case in enumerate(cases)],
        }
        self.assertEqual(identity, full.ASYNC_EXPECTED_IDENTITY)
        self.assertEqual(identity, full.async_source_identity(SNIPPET.read_bytes()))


if __name__ == "__main__":
    unittest.main()
