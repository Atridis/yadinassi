"""Test the distributed executable outside the source tree and without PYTHONPATH."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


# Explicit goldens are shared by the source CLI tests and the frozen checks.
# They are not calculated with the implementation under test or a float oracle.
DIVISION_EXAMPLES = [
    ('1 / 3', '0,333333333333333333333333333'),
    ('2 / 3', '0,666666666666666666666666667'),
    ('1 / 0.3', '3,333333333333333333'),
    ('0.1 / 3', '0,033333333333333333333333333333333333'),
    ('-1 / 6', '-0,166666666666666666666666667'),
    ('1 / -6', '-0,166666666666666666666666667'),
    ('-1 / -6', '0,166666666666666666666666667'),
    ('Number("1.0000000000") / Number("3.0000000000")',
     '0,333333333333333333333333333'),
    ('0.000 / 3', '0'),
    ('1 / 3000000000', '0,000000000333333333333333333333333333'),
    ('1 / 0.0000000003', '3\u00a0333\u00a0333\u00a0333,333333333'),
    ('Number("123456789012345678901234567890.123456789") / 7',
     '17\u00a0636\u00a0684\u00a0144\u00a0620\u00a0811\u00a0271\u00a0604\u00a0938\u00a0270,'
     '017636684142857142857142857142857143'),
    ('stored', '0,142857142857142857142857143'),
    ('stored / 3', '0,047619047619047619047619047666666666666666666666666667'),
]
DIVISION_TIE = 'Деление: точная половина на границе округления пока не поддерживается в Yadinassi'
DIVISION_LIMIT = 'Деление: превышен предел ресурсов Yadinassi (4096 десятичных разрядов)'
DIVISION_FAILURES = [
    ('1 / 0', 'Деление на ноль'),
    ('1 / -0.000', 'Деление на ноль'),
    ('1 / 268435456', DIVISION_TIE),
    ('-1 / 268435456', DIVISION_TIE),
    ('3 / 268435456', DIVISION_TIE),
    ('-3 / 268435456', DIVISION_TIE),
    ('Number("1e1000000") / 3', DIVISION_LIMIT),
    ('Number("1e-1000000") / 3', DIVISION_LIMIT),
    ('1 / Number("1e1000000")', DIVISION_LIMIT),
    ('1 / Number("1e-1000000")', DIVISION_LIMIT),
]
DIVISION_PROGRAM = 'stored = 1 / 7;\n'
DIVISION_OUTPUT = ''
for _expression, _display in DIVISION_EXAMPLES:
    _canonical = _display.replace('\u00a0', '').replace(',', '.')
    DIVISION_PROGRAM += (f'value = {_expression};\nMessage(value);\n'
                         f'Message(value = Number("{_canonical}"));\n'
                         'Message(Number(String(value)) = value);\n')
    DIVISION_OUTPUT += _display + '\nДа\nДа\n'
DIVISION_PROGRAM += ('Message(TypeOf(value) = Тип("Число"));\n'
                     'Message(stored = Number("0.142857142857142857142857143"));\n'
                     'Message(stored / 3 <> 1 / 21);\nvalue = stored;\n')
DIVISION_OUTPUT += 'Да\nДа\nДа\n'
for _expression, _message in DIVISION_FAILURES:
    DIVISION_PROGRAM += (f'Try\nvalue = {_expression};\nExcept\n'
                         f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                         'EndTry;\nMessage(value = stored);\n')
    DIVISION_OUTPUT += 'Да\nДа\n'
DIVISION_PROGRAM += 'Message(value); Message(TypeOf(value)); Message(1 / 8);\n'
DIVISION_OUTPUT += '0,142857142857142857142857143\nЧисло\n0,125\n'


# Only presentation rounds beyond 324 fractional positions for abs(value) < 1.
# Build the source text here; keep the expected output compact and test value
# preservation separately from the deliberately lossy String roundtrip.
_LONG_VALUE = '0.' + '3' * 324 + '6'
_LONG_TEXT = '0,' + '3' * 323 + '4'
DIVISION_PROGRAM += (
    f'longValue = Number("{_LONG_VALUE}"); negative = -longValue;\n'
    f'Message(String(longValue) = "{_LONG_TEXT}"); Message(StrLen(String(longValue)));\n'
    f'Message(String(negative) = "-{_LONG_TEXT}"); Message(StrLen(String(negative)));\n'
    f'Message(-negative = longValue); Message(longValue = Number("{_LONG_VALUE}"));\n'
    'Message(Number(String(longValue)) <> longValue); text = "saved";\n')
DIVISION_OUTPUT += 'Да\n326\nДа\n327\nДа\nДа\nДа\n'
PRESENTATION_FAILURES = (
    ('Number("5e-325")', 'Представление числа: точная половина на границе 324 позиций '
     'пока не поддерживается в Yadinassi'),
    ('Number("1.' + '3' * 325 + '")', 'Представление числа: более 324 дробных позиций '
     'при модуле не меньше 1 пока не поддерживается в Yadinassi'),
    ('Number("1e4096")', 'Представление числа: превышен предел ресурсов Yadinassi '
     '(4096 десятичных разрядов)'),
)
for _expression, _message in PRESENTATION_FAILURES:
    DIVISION_PROGRAM += (f'Try\ntext = String({_expression});\nExcept\n'
                         f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                         'EndTry;\nMessage(text = "saved");\n')
    DIVISION_OUTPUT += 'Да\nДа\n'


def check_division(executable: str, *, directory: Path, env: dict) -> None:
    """Exercise the division contract in the isolated frozen executable."""
    directory.mkdir()
    source = directory / 'Деление.bsl'
    source.write_text(DIVISION_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, DIVISION_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], DIVISION_PROGRAM),
              ([], DIVISION_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, DIVISION_OUTPUT, ''):
            raise AssertionError(f'Failed division {arguments!r}: {result!r}')

    module = directory / 'Доли.bsl'
    module.write_text(
        'Function Divide(a, b) Export\nReturn a / b;\nEndFunction\n'
        'Function Seventh() Export Return 1 / 7; EndFunction\n', encoding='utf-8-sig')
    importer = directory / 'ИмпортДеления.bsl'
    importer.write_text(
        '// #Импорт Доли.bsl\nvalue = Доли.Seventh();\n'
        'Message(value); Message(Доли.Divide(value, 3));\n'
        'Message(Доли.Divide(1, 0.3)); Message(TypeOf(value));\n'
        'Message(value = Number("0.142857142857142857142857143"));\n'
        'Try value = Доли.Divide(1, 268435456); Except Message("caught"); EndTry;\n'
        'Message(value); Message(Доли.Divide(1, 8));\n', encoding='utf-8-sig')
    import_output = ('0,142857142857142857142857143\n'
                     '0,047619047619047619047619047666666666666666666666666667\n'
                     '3,333333333333333333\nЧисло\nДа\ncaught\n'
                     '0,142857142857142857142857143\n0,125\n')
    for path in (importer, importer.relative_to(directory.parent)):
        result = subprocess.run([executable, str(path)], capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, import_output, ''):
            raise AssertionError(f'Failed imported division {path!r}: {result!r}')

    # One diagnostic of each kind must have the right location on every route;
    # all sign and exponent variants above are additionally checked as catchable.
    for expression, message in (DIVISION_FAILURES[index] for index in (0, 2, 6)):
        error_code = f'value = 1 / 7;\nvalue = {expression};\n'
        source.write_text(error_code, encoding='utf-8-sig')
        importer.write_text('// #Импорт Доли.bsl\nДоли.Divide(' +
                            expression.replace(' / ', ', ') + ');\n', encoding='utf-8-sig')
        errors = [([flag, error_code], None, '', '<команда>:2:')
                  for flag in ('-c', '-с', '--command')]
        errors += [([str(source)], None, '', str(source) + ':2:'),
                   (['-'], error_code, '', '<stdin>:2:'),
                   ([], error_code + 'value\nTypeOf(value)\n1 / 8\n/exit\n',
                    '0,142857142857142857142857143\nЧисло\n0,125\n', '<консоль>:1:')]
        for path in (importer, importer.relative_to(directory.parent)):
            errors.append(([str(path)], None, '', str(module.resolve()) + ':2:'))
        for arguments, stdin, stdout, location in errors:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed division diagnostics {arguments!r}: {result!r}')
    # A bare REPL value is presented by the console, outside a BSL String call.
    # Its presentation failure must still be source-aware and allow the next input.
    for expression, message in PRESENTATION_FAILURES:
        code = ('value = 1 / 7;\n' + expression + '\n'
                'value\nTypeOf(value)\n1 / 8\n/exit\n')
        result = subprocess.run([executable], input=code, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode != 1
                or result.stdout != '0,142857142857142857142857143\nЧисло\n0,125\n'
                or '<консоль>:1:' not in result.stderr or message not in result.stderr
                or 'Traceback' in result.stderr):
            raise AssertionError(f'Failed bare presentation recovery {expression!r}: {result!r}')
    print('Binary division passed: exact rounded values, stored/redivided values, types, '
          'BOM files, imports, all command flags, stdin, console, bounded presentation, ties and resource limits')


NUMERIC_HELPERS_PROGRAM = 'Сообщить(ЗначениеВСтрокуВнутр(Цел(-12.99)));\nMessage(ValueToStringInternal(iNt(0.99)));\nvalue = Number("12345678901234567890123456789012345678901234567890.9");\nMessage(ValueToStringInternal(Int(value)));\nTry Int(Undefined); Except Message("integer-caught"); EndTry;\nMessage(TypeOf(Int(1 / 3)));\nMessage(ValueToStringInternal(Int(True)));\nMessage(ValueToStringInternal(Цел("12.75")));\nMessage(ValueToStringInternal(Мин(2, True)));\nMessage(ValueToStringInternal(Max(False, 0)));\nMessage(ValueToStringInternal(mIn(7, -2, 0, -1)));\nMessage(ValueToStringInternal(МАКС(-7, 2, 0, 1)));\nTry Min(2, "10"); Except Message("mixed-caught"); EndTry;\nMessage(ValueToStringInternal(Max("a", "A")));\nMessage(ValueToStringInternal(Min("az", "Aa")));\nMessage(ValueToStringInternal(Min("ё", "е")));\nMessage("a" < "A");\n'
NUMERIC_HELPERS_OUTPUT = '{"N",-12}\n{"N",0}\n{"N",12345678901234567890123456789012345678901234567890}\ninteger-caught\nЧисло\n{"N",1}\n{"N",12}\n{"B",1}\n{"B",0}\n{"N",-2}\n{"N",2}\nmixed-caught\n{"S","A"}\n{"S","Aa"}\n{"S","е"}\nДа\n'


def check_numeric_helpers(executable: str, *, directory: Path, env: dict) -> None:
    """Owner-derived numeric helpers and shared string collation."""
    directory.mkdir()
    source = directory / 'ЦелаяЧасть.bsl'
    source.write_text(NUMERIC_HELPERS_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, NUMERIC_HELPERS_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], NUMERIC_HELPERS_PROGRAM),
              ([], NUMERIC_HELPERS_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, NUMERIC_HELPERS_OUTPUT, ''):
            raise AssertionError(f'Failed integer part {arguments!r}: {result!r}')
    print('Binary numeric helpers passed: aliases, signs, long coefficient, coercion, winning types, ties, '
          'BOM file, command flags, stdin, console and catchable error')


COMPARISON_PROGRAM = r'''
Message(True = 1); Message(0 = False); Message(True <> 1);
Message(0.5 < True); Message(False <= 0); Message(1 >= True);
Message(True > 0.999999999999999999999999999999999);
Message(1.000000000000000000000000000000001 > True);
Message(-1 < False); Message(False > -1);
m = New Map; m[True] = "boolean"; m[1] = "number";
Message(m.Count()); Message(m[True]); Message(m[1]);
Try
    invalid = True < "1";
Except
    Message("comparison-error");
EndTry;
Message(Истина = 1); Message(Ложь = 0);
'''
COMPARISON_OUTPUT = ('Да\nДа\nНет\nДа\nДа\nДа\nДа\nДа\nДа\nДа\n'
                     '2\nboolean\nnumber\ncomparison-error\nДа\nДа\n')


def check_numeric_boolean_comparisons(executable: str, *, directory: Path, env: dict) -> None:
    directory.mkdir()
    source = directory / 'Сравнения.bsl'
    source.write_text(COMPARISON_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, COMPARISON_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], COMPARISON_PROGRAM),
              ([], COMPARISON_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, COMPARISON_OUTPUT, ''):
            raise AssertionError(f'Failed Number/Boolean comparison {arguments!r}: {result!r}')
    print('Binary Number/Boolean comparisons passed: six operators, exact values, typed keys, CLI and recovery')


# Owner-observed Round results, shared with the source entrypoint tests. Internal
# number payloads preserve exact coefficients without presentation grouping.
ROUNDING_EXAMPLES = [
    ('оКр(1.5)', '2'), ('rOuNd(-1.5)', '-2'),
    ('Round(1.5, 0, 0)', '1'), ('Окр(-1.5, 0, 0)', '-1'),
    ('Round(-1.5001, 0, 0)', '-2'), ('Round(-1.4999, 0, 1)', '-1'),
    ('Окр(12.345, 2)', '12.35'), ('Round(1250, -2)', '1300'),
    ('Round(-1250, -2, 0)', '-1200'), ('Round(12.345, 1.9)', '12.3'),
    ('Round(1250, -1.9)', '1250'), ('Round(1.5, 0, 0.9)', '1'),
    ('Round(1.5, 0, -1)', '2'), ('Round(1.5, 0, 2)', '2'),
    ('Round(-1.5, 0, RoundMode.Round15as10)', '-1'),
    ('Окр(1.5, 0, РежимОкругления.Окр15как20)', '2'),
    ('Round(Number("123456789012345678901234567890.5"))',
     '123456789012345678901234567891'),
]
ROUNDING_FAILURES = [
    ('Round(Undefined)', 'Невозможно преобразовать значение в число'),
    ('Round(12.345, Undefined)', 'Невозможно преобразовать значение в число'),
    ('Round(1.5, 0, True)', 'Окр: ожидается число или значение РежимОкругления'),
    ('Round(1.5, 0, "1")', 'Окр: ожидается число или значение РежимОкругления'),
    ('Round(1.5, 0, Undefined)', 'Окр: ожидается число или значение РежимОкругления'),
]
ROUNDING_PROGRAM = ''
ROUNDING_OUTPUT = ''
for _expression, _number in ROUNDING_EXAMPLES:
    ROUNDING_PROGRAM += f'Message(ValueToStringInternal({_expression}));\n'
    ROUNDING_OUTPUT += '{"N",' + _number + '}\n'
ROUNDING_PROGRAM += ('Message(TypeOf(Round(1.5)));\n'
                     'low = RoundMode.Round15as10; high = РежимОкругления.Окр15как20;\n'
                     'Message(low = РежимОкругления.Окр15как10);\n'
                     'Message(high = RoundMode.Round15as20);\n')
ROUNDING_OUTPUT += 'Число\nДа\nДа\n'
for _name, _index, _display in [('low', '0', 'Округлять 15 как 10'),
                               ('high', '1', 'Округлять 15 как 20')]:
    ROUNDING_PROGRAM += (f'Message(String({_name})); Message(TypeOf({_name}));\n'
                         f'Message(ValueToStringInternal({_name}));\n'
                         f'restored = ValueFromStringInternal(ValueToStringInternal({_name}));\n'
                         f'Message(restored = {_name});\n'
                         'Message(TypeOf(restored) = Type("RoundMode"));\n'
                         'Message(ValueToStringInternal(Round(-1.5, 0, restored)));\n')
    ROUNDING_OUTPUT += (_display + '\nРежимОкругления\n'
                        '{"#",32c82ccd-fef3-4070-beb5-b9c52afc781d,' + _index + '}\n'
                        'Да\nДа\n{"N",-' + ('1' if _index == '0' else '2') + '}\n')
ROUNDING_PROGRAM += ('kind = Type("RoundMode"); Message(ValueToStringInternal(kind));\n'
                     'Message(ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(kind)) = '
                     'Тип("РежимОкругления"));\nvalue = Round(12.345, 2);\n')
ROUNDING_OUTPUT += '{"T",32c82ccd-fef3-4070-beb5-b9c52afc781d}\nДа\n'
for _expression, _message in ROUNDING_FAILURES:
    ROUNDING_PROGRAM += (f'Try value = {_expression}; Except\n'
                         f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                         'EndTry; Message(value = 12.35);\n')
    ROUNDING_OUTPUT += 'Да\nДа\n'
ROUNDING_PROGRAM += 'Message(ValueToStringInternal(Окр(-1.5)));\n'
ROUNDING_OUTPUT += '{"N",-2}\n'


# Assert membership and behavior without assuming the native enumeration order.
ROUNDING_PROGRAM += '''
seen = New Map;
For Each mode In RoundMode Do
    seen.Insert(mode, Round(1.5, 0, mode));
    Message(ValueFromStringInternal(ValueToStringInternal(mode)) = mode);
EndDo;
Message(seen.Count());
Message(seen[РежимОкругления.Окр15как10]);
Message(seen[РежимОкругления.Окр15как20]);
count = 0;
Для Каждого outer Из РежимОкругления Цикл
    Для Каждого inner Из RoundMode Цикл count = count + 1; Прервать; КонецЦикла;
    Продолжить; count = 100;
КонецЦикла;
Сообщить(count);
Try
    For Each value In RoundMode.Round15as10 Do EndDo;
Except
    Message("individual-mode-not-iterable");
EndTry;
count = 0;
For Each mode In RoundMode Do count = count + 1; EndDo;
Message(count);
'''
ROUNDING_OUTPUT += 'Да\nДа\n2\n1\n2\n2\nindividual-mode-not-iterable\n2\n'


def check_rounding(executable: str, *, directory: Path, env: dict) -> None:
    """Native-backed Round values, enum codecs and failed-assignment recovery."""
    directory.mkdir()
    source = directory / 'Округление.bsl'
    source.write_text(ROUNDING_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, ROUNDING_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], ROUNDING_PROGRAM),
              ([], ROUNDING_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, ROUNDING_OUTPUT, ''):
            raise AssertionError(f'Failed rounding {arguments!r}: {result!r}')
    for expression, message in ROUNDING_FAILURES:
        code = f'value = Round(12.345, 2);\nvalue = {expression};\n'
        result = subprocess.run([executable], input=code + 'value\nОкр(-1.5)\n/exit\n',
                                capture_output=True, encoding='utf-8', cwd=directory.parent,
                                env=env, timeout=30)
        if (result.returncode != 1 or result.stdout != '12,35\n-2\n'
                or '<консоль>:1:' not in result.stderr or message not in result.stderr
                or 'Traceback' in result.stderr):
            raise AssertionError(f'Failed rounding recovery {expression!r}: {result!r}')
    print('Binary rounding passed: aliases, signs, precision, numeric/enum modes, exact long '
          'coefficient, enum/type codecs, BOM file, command flags, stdin and console recovery')


def check_internal_serialization(executable: str, *, directory: Path, env: dict) -> None:
    """All runtime codecs, graph copying and presentation in the frozen binary."""
    directory.mkdir()
    code = ('value = 1234.500;\n'
            'Message(ЗначениеВСтрокуВнутр(value));\n'
            'Message(value);\n'
            'Message(ValueToStringInternal(1 / 3));\n'
            'Message(ValueToStringInternal(True));\n'
            'Message(ValueToStringInternal(0));\n'
            'Message(ValueFromStringInternal(ValueToStringInternal(value)));\n'
            'Message(ТипЗнч(ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(value))));\n'
            'Try ValueFromStringInternal("unknown"); Except Message("caught-input"); EndTry;\n'
            'Message(ValueFromStringInternal(ValueToStringInternal(7)));\n')
    expected = ('{"N",1234.5}\n1\u00a0234,5\n'
                '{"N",0.333333333333333333333333333}\n{"B",1}\n{"N",0}\n'
                '1\u00a0234,5\nЧисло\ncaught-input\n7\n')
    code += ('record = New Structure("Code", 7); values = New Array;\n'
             'values.Add(Undefined); values.Add(True); values.Add(1); values.Add("Ёж🙂");\n'
             'values.Add(New Array); values.Add(New FixedArray(New Array));\n'
             'values.Add(record); values.Add(New FixedStructure(record));\n'
             'values.Add(New Map); values.Add(New FixedMap(New Map));\n'
             'values.Add(Type("Number")); For Each pair In record Do values.Add(pair); EndDo;\n'
             'For Each item In values Do\n'
             ' restored = ValueFromStringInternal(ValueToStringInternal(item));\n'
             ' Message(TypeOf(restored) = TypeOf(item));\n'
             'EndDo;\n'
             'Message(ValueToStringInternal("Ёж🙂"));\n'
             'references = New Array; references.Add(record); references.Add(record);\n'
             'copies = ValueFromStringInternal(ValueToStringInternal(references));\n'
             'copies[0].Code = 9; Message(copies[1].Code); Message(record.Code);\n'
             'references.Add(references);\n'
             'Try ValueToStringInternal(references); Except Message("cycle-caught"); EndTry;\n'
             'Message(TypeOf(ValueFromStringInternal(ValueToStringInternal(Undefined))));\n')
    expected += 'Да\n' * 12 + '{"S","Ёж"\\d83d"\\de42"}\n7\n7\ncycle-caught\nНе определено\n'
    source = directory / 'Сериализация.bsl'
    source.write_text(code, encoding='utf-8-sig')
    cases = [([flag, code], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], code), ([], code + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Failed internal serialization {arguments!r}: {result!r}')
    print('Binary internal serialization passed: all12types, UTF16, graph copying, cycles, external presentation, '
          'inverse roundtrip, aliases, BOM file, command flags, stdin, console and error recovery')


def check_numeric_presentation(executable: str, *, directory: Path, env: dict) -> None:
    """Check the native NBSP grouping and decimal-comma contract before the native sample gate.

    This is not a substitute for native comparison: main() still requires the
    untouched owner-provided basic output, including its arithmetic precision.
    """
    directory.mkdir()
    code = '''value = nUmBeR("-1234.5000");
mEsSaGe(value); сОоБщИтЬ(сТрОкА(value));
Message("value=" + value); Message(чИсЛо("1\u00a0234,5000"));
Message(String(-0.000)); Message(String(1000.000));
Message(TypeOf(value) = Тип("Число"));
Message(Number(String(value)) = value);
Message(Найти(value, ",")); Message(StrReplace(value, ",", "."));
Message(StrConcat(StrSplit(value, ","), "|")); Message(СтрДлина(value));
exact = Number("123456789012345678901234567890.123456789");
Message(exact); Message(Number(String(exact)) = exact);
Message(Number("+12\u00a0345")); Message(Number("-123\u00a0456,000100"));
Message(Number("1\u00a0234\u00a0567")); Message(Number("001\u00a0234,5000"));
Message(String("1234.5000"));
'''
    expected = ('-1\u00a0234,5\n-1\u00a0234,5\nvalue=-1\u00a0234,5\n'
                '1\u00a0234,5\n0\n1\u00a0000\nДа\nДа\n7\n'
                '-1\u00a0234.5\n-1\u00a0234|5\n8\n'
                '123\u00a0456\u00a0789\u00a0012\u00a0345\u00a0678'
                '\u00a0901\u00a0234\u00a0567\u00a0890,123456789\nДа\n'
                '12\u00a0345\n-123\u00a0456,0001\n1\u00a0234\u00a0567\n1\u00a0234,5\n1234.5000\n')
    invalid = ['1,2.3', '1.2,3', '1,,2', '1,2,3', '1 234,5', 'NaN', 'Infinity',
               '1,', ',5', '1,2e3', '1_000,25', '1,2_5', '١,٢', '12\u00a034,5',
               '1234\u00a0567', '1\u00a02345', '1\u00a0\u00a0234',
               '1\u00a0234.5', '1\u00a0234,5e2', '1\u202f234,5',
               '1\u00a0234 567,5', '1\u00a0٢٣٤,5']
    for value in invalid:
        code += (f'Try\nvalue = Number("{value}");\nExcept\n'
                 'Message("caught");\nEndTry;\n')
    code += 'Message(value); Message(TypeOf(value));\n'
    expected += 'caught\n' * len(invalid) + '-1\u00a0234,5\nЧисло\n'
    source = directory / 'ПредставлениеЧисел.bsl'
    source.write_text(code, encoding='utf-8-sig')
    module = directory / 'Числа.bsl'
    module.write_text(
        'Function Parse(text) Export Return Число(text); EndFunction\n'
        'Function Present(value) Export Return Строка(value); EndFunction\n'
        'Procedure Show(value) Export Message(value); EndProcedure\n'
        'Function Fail() Export\nReturn Number("12\u00a034,5");\nEndFunction\n',
        encoding='utf-8-sig')
    importer = directory / 'ИмпортЧисел.bsl'
    importer.write_text(
        '// #Импорт Числа.bsl\nvalue = Числа.Parse("-1\u00a0234,5000");\n'
        'Message(TypeOf(value)); Message(value); Числа.Show(value);\n'
        'Message(Числа.Present(value)); Message("value=" + value);\n'
        'Message(Number(Числа.Present(value)) = value);\n'
        'Try Числа.Fail(); Except Message("caught"); EndTry;\n'
        'Message(Числа.Parse("0.125"));\n', encoding='utf-8-sig')
    import_expected = ('Число\n-1\u00a0234,5\n-1\u00a0234,5\n-1\u00a0234,5\n'
                       'value=-1\u00a0234,5\nДа\ncaught\n0,125\n')
    cases = [([flag, code], None, expected) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None, expected), (['-'], code, expected),
              ([], code + '/exit\n', expected)]
    for path in (importer, importer.relative_to(directory.parent)):
        cases.append(([str(path)], None, import_expected))
    for arguments, stdin, stdout in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, stdout, ''):
            raise AssertionError(f'Failed numeric presentation {arguments!r}: {result!r}')
    error_code = 'value = Number("1\u00a0234,5");\nvalue = Number("12\u00a034,5");\n'
    error_file = directory / 'ОшибкаЧисла.bsl'
    error_file.write_text(error_code, encoding='utf-8-sig')
    error_import = directory / 'ОшибкаИмпортаЧисла.bsl'
    error_import.write_text('// #Импорт Числа.bsl\nЧисла.Fail();\n', encoding='utf-8-sig')
    errors = [([flag, error_code], None, '', '<команда>:2:')
              for flag in ('-c', '-с', '--command')]
    errors += [([str(error_file)], None, '', str(error_file) + ':2:'),
               (['-'], error_code, '', '<stdin>:2:'),
               ([], error_code + 'value\nTypeOf(value)\nNumber("0,125")\n/exit\n',
                '1\u00a0234,5\nЧисло\n0,125\n', '<консоль>:1:')]
    for path in (error_import, error_import.relative_to(directory.parent)):
        errors.append(([str(path)], None, '', str(module.resolve()) + ':5:'))
    for arguments, stdin, stdout, location in errors:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                or 'Невозможно преобразовать значение в число' not in result.stderr
                or 'Traceback' in result.stderr):
            raise AssertionError(f'Failed numeric diagnostics {arguments!r}: {result!r}')
    print('Binary numeric presentation passed: NBSP grouping, decimal comma, exact roundtrip, aliases, '
          'BOM files, imports, all command flags, stdin, console, and error recovery')


def main() -> None:
    # Redirected Windows output can default to cp1252, which cannot encode BSL text.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    executable = str(Path(sys.argv[1]).resolve())
    expected = (ROOT / "tests" / "fixtures" / "basic.out").read_text(encoding="utf-8")
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    env["PYTHONIOENCODING"] = "utf-8"
    # The bundled interpreter must work without finding Python on PATH.
    env["PATH"] = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32" if os.name == "nt" else "/usr/bin:/bin"
    with tempfile.TemporaryDirectory(prefix="yadinassi-smoke-") as temporary:
        # Imports use resolved paths in diagnostics. Keep direct-file paths and
        # the subprocess cwd canonical too (e.g. macOS /var, Windows aliases,
        # and a symlink or a noncanonical path supplied through TMPDIR).
        temporary = str(Path(temporary).resolve())
        check_numeric_presentation(executable, directory=Path(temporary) / "numeric", env=env)
        check_division(executable, directory=Path(temporary) / "division", env=env)
        check_numeric_helpers(executable, directory=Path(temporary) / "integer-part", env=env)
        check_rounding(executable, directory=Path(temporary) / "rounding", env=env)
        check_numeric_boolean_comparisons(executable, directory=Path(temporary) / "comparisons", env=env)
        check_internal_serialization(executable, directory=Path(temporary) / "serialization", env=env)
        sample = Path(temporary) / "пример.bsl"
        sample.write_bytes((ROOT / "integrational_tests" / "tests" / "basic.bsl").read_bytes())
        module = Path(temporary) / "Побочное.bsl"
        module.write_text('#Область ПубличныйИнтерфейс\n#Если Клиент Тогда\n&НаКлиенте\n'
                          'Функция ПолучитьСумму(А, Б = 2) Экспорт\n'
                          '#Область Вычисление\nВозврат А + Б;\n#КонецОбласти\n'
                          'КонецФункции\n#Иначе\n&AtServer\ninvalid !!!\n'
                          '#КонецЕсли\n#КонецОбласти\n', encoding="utf-8-sig")
        importer = Path(temporary) / "Основное.bsl"
        importer.write_text('// #Импорт Побочное.bsl\n'
                            'Сообщить(Побочное.ПолучитьСумму(1));', encoding="utf-8")
        project = Path(temporary) / "project"
        nested = project / "Справочник"
        deeper = nested / "Вложенное"
        deeper.mkdir(parents=True)
        (nested / module.name).write_bytes(module.read_bytes())
        (deeper / "Другое.bsl").write_text(
            'Функция Ответ() Экспорт Возврат "вложенный"; КонецФункции',
            encoding="utf-8-sig")
        nested_importer = project / "Основное.bsl"
        nested_importer.write_text(
            '// #Импорт Справочник.Побочное.bsl\n'
            '// #Импорт Справочник.Вложенное.Другое.bsl\n'
            'Сообщить(справочник.ПОБОЧНОЕ.получитьсумму(1, 2));\n'
            'Сообщить(СПРАВОЧНИК.вложенное.ДРУГОЕ.ответ());', encoding="utf-8-sig")
        directory_importer = project / "Каталог.bsl"
        directory_importer.write_text(
            '// #Импорт Справочник\n'
            '// #Импорт Справочник.Вложенное\n'
            'Сообщить(Справочник.Побочное.ПолучитьСумму(1, 2));\n'
            'Сообщить(Справочник.Вложенное.Другое.Ответ());', encoding="utf-8")
        client_code = ('#If AtClient And Not Server Then\n&AtClient\n'
                       'Function F() Return 42; EndFunction\nMessage(F());\n'
                       '#Else\n// #Импорт Missing.bsl\nunsupported !!!\n#EndIf\n')
        region_code = ('#Область Модуль\nФункция Ответ()\n'
                       '    #Область Тело\n    Возврат 42;\n    #КонецОбласти\n'
                       'КонецФункции\nСообщить(Ответ());\n#КонецОбласти\n')
        region_file = Path(temporary) / 'Области.bsl'
        region_file.write_text(region_code, encoding='utf-8-sig')
        region_error_module = Path(temporary) / 'ОшибкаОбласти.bsl'
        region_error_module.write_text(
            '#Область API\nФункция Ответ() Экспорт\n#Область Тело\n'
            'Возврат 1 / 0;\n#КонецОбласти\nКонецФункции\n#КонецОбласти\n',
            encoding='utf-8-sig')
        region_error_main = Path(temporary) / 'ОшибкаИмпортаОбласти.bsl'
        region_error_main.write_text(
            '// #Импорт ОшибкаОбласти.bsl\nСообщить(ОшибкаОбласти.Ответ());\n',
            encoding='utf-8')
        exception_module = Path(temporary) / "Ошибки.bsl"
        exception_module.write_text(
            'Процедура Выполнить() Экспорт\n'
            'Попытка\nВызватьИсключение "из модуля";\n'
            'Исключение\nВызватьИсключение;\nКонецПопытки;\nКонецПроцедуры',
            encoding="utf-8-sig")
        exception_main = Path(temporary) / "Обработка.bsl"
        exception_main.write_text(
            '// #Импорт Ошибки.bsl\nПопытка\nОшибки.Выполнить();\n'
            'Исключение\nСообщить(ОписаниеОшибки());\nКонецПопытки;\n',
            encoding="utf-8")
        exception_code = ('Попытка\nСообщить(1 / 0);\nИсключение\n'
                          'Сообщить("обработано");\nКонецПопытки;\n')
        string_code = ('Сообщить(СтрСоединить(СтрРазделить("ёж,;бор", ",;", Ложь), " / "));\n'
                       'Сообщить(ВРег(СокрЛП(" ёж ")));\n'
                       'Сообщить(Сред("A🙂B", 2, 2)); Сообщить(СтрДлина("A🙂B"));\n'
                       'Сообщить(Найти("A🙂B", "B"));\n'
                       'Сообщить(СтрЗаменить("aaa", "a", "x"));\n'
                       'Сообщить(Лев("🙂", 1) + Прав("🙂", 1));\n')
        string_output = "ёж / бор\nЁЖ\n🙂\n4\n4\nxxx\n🙂\n"
        string_file = Path(temporary) / "Строки.bsl"
        string_file.write_text(string_code, encoding="utf-8-sig")
        structure_code = ('с = Новый Структура("Имя,Count", "ёж", 7); '
                          'с["ИМЯ"] = "бор"; Перем результат; '
                          'Сообщить(с.Свойство("имя", результат)); Сообщить(результат); '
                          'Сообщить(с.Count); Сообщить(с.Count()); '
                          'с.Удалить("Count"); '
                          'Для Каждого пара Из с Цикл '
                          'Сообщить(пара.Ключ + ":" + пара.Значение); КонецЦикла; '
                          'с.Property("нет", результат); Сообщить(результат = Undefined); '
                          'Попытка с.Нет = 1; Исключение Сообщить("обработано"); КонецПопытки; '
                          'Сообщить(Строка(с));\n')
        structure_output = "Да\nбор\n7\n2\nИмя:бор\nДа\nобработано\nСтруктура\n"
        structure_file = Path(temporary) / "Структуры.bsl"
        structure_file.write_text(structure_code, encoding="utf-8-sig")
        map_code = '''Данные = Новый Соответствие;
Данные.Вставить(Истина, "булево");
Данные[1] = "число";
Данные["Имя"] = "верх";
Данные["имя"] = "низ";
Данные[Неопределено] = "пустой ключ";
Ключ = Новый Массив;
Данные.Вставить(Ключ, 7);
Ключ.Добавить(1);
Сообщить(Данные.Количество());
Сообщить(Данные[Истина]);
Сообщить(Данные.Получить(1));
Сообщить(Данные["Имя"] + ":" + Данные["имя"]);
Сообщить(Данные[Неопределено]);
Сообщить(Данные[Ключ]);
Сообщить(Данные[Новый Массив] = Неопределено);
Посещено = 0;
Для Каждого Пара Из Данные Цикл
    Посещено = Посещено + 1;
КонецЦикла;
Сообщить(Посещено);
Попытка
    Пара.Значение = 99;
Исключение
    Сообщить("только чтение");
КонецПопытки;
Данные.Удалить(Ключ);
Данные.Удалить("нет");
Сообщить(Данные.Количество());
Данные.Очистить();
Сообщить(Данные.Количество());
Сообщить(Строка(Данные));
'''
        map_output = ("6\nбулево\nчисло\nверх:низ\nпустой ключ\n7\nДа\n6\n"
                      "только чтение\n5\n0\nСоответствие\n")
        map_file = Path(temporary) / "Соответствия.bsl"
        map_file.write_text(map_code, encoding="utf-8-sig")
        type_code = '''Сообщить(ТипЗнч(Неопределено));
Message(TypeOf(True));
Сообщить(ТипЗнч(12.5));
Message(TypeOf("ёж"));
Сообщить(ТипЗнч(Новый Массив));
Message(TypeOf(New Structure));
Сообщить(ТипЗнч(Новый Соответствие));
Message(TypeOf(Type("Number")));
kind = тИп("чИсЛо");
Message(kind = tYpE("nUmBeR"));
Message(kind = "Число");
Message(TypeOf(True) = kind);
values = New Array;
values.Add(kind);
s = New Structure("Kind", values[0]);
m = New Map;
m[s.Kind] = Type("String");
m["Число"] = "строковый ключ";
Message(m[TypeOf(42)]);
Message(m["Число"]);
Message(m.Count());
Message(values.Find(TypeOf(1)));
For Each pair In s Do
    Message(TypeOf(pair));
EndDo;
For Each pair In m Do
    Message(ТипЗнч(pair) = Type("kEyAnDvAlUe"));
EndDo;
Try
    Type("Date");
Except
    Message("неизвестный тип");
EndTry;
Try
    TypeOf(Message);
Except
    Message("внешнее значение");
EndTry;
Message(TypeOf(kind) = Тип("Тип"));
'''
        type_output = ('Не определено\nБулево\nЧисло\nСтрока\nМассив\nСтруктура\n'
                       'Соответствие\nТип\nДа\nНет\nНет\nСтрока\nстроковый ключ\n'
                       '2\n0\nКлючИЗначение\nДа\nДа\nнеизвестный тип\nвнешнее значение\nДа\n')
        type_file = Path(temporary) / 'Типы.bsl'
        type_file.write_text(type_code, encoding='utf-8-sig')
        type_module = Path(temporary) / 'ТипыМодуля.bsl'
        type_module.write_text(
            'Function Failure() Export\nReturn Type("Date");\nEndFunction\n'
            'Function Kind(Val value) Export Return TypeOf(value); EndFunction\n'
            'Function Mapping() Export\n'
            'm = New Map; m[Тип("Число")] = Тип("Строка"); Return m;\nEndFunction\n',
            encoding='utf-8-sig')
        type_importer = Path(temporary) / 'ИмпортТипов.bsl'
        type_importer.write_text(
            '// #Импорт ТипыМодуля.bsl\n'
            'm = ТипыМодуля.Mapping(); Сообщить(m[TypeOf(1)]);\n'
            'Сообщить(ТипыМодуля.Kind(m[Type("Number")]));\n'
            'Try\nТипыМодуля.Failure();\nExcept\n'
            'Message(ErrorDescription());\nEndTry;\n'
            'Message(TypeOf(1) = Тип("Число"));\n', encoding='utf-8')
        type_error_importer = Path(temporary) / 'ОшибкаИмпортаТипов.bsl'
        type_error_importer.write_text(
            '// #Импорт ТипыМодуля.bsl\nТипыМодуля.Failure();\n', encoding='utf-8')
        type_error_file = (Path(temporary) / 'ОшибкаТипа.bsl').resolve()
        type_error_file.write_text('// строка перед ошибкой\nTypeOf(Message);\n', encoding='utf-8-sig')
        fixed_code = '''source = New Array(2);
source[0] = 4; source[1] = 8;
a = Новый ФиксированныйМассив(source);
source[0] = 99; source.Add(12);
Message(a.Count()); Message(a.UBound());
Сообщить(a.Получить(0)); Message(a.Get(1));
Message(a.Найти(8)); Message(a.Find(99) = Undefined);
sum = 0;
For Each item In a Do sum = sum + item; EndDo;
Message(sum);
s = New FixedStructure("Name,Count", "снимок", 7);
Message(s.NAME); Message(s["name"]); Message(s.Count); Message(s.Количество());
Var value;
Message(s.Property("nAmE", value)); Message(value);
Message(s.Свойство("Missing", value)); Message(value = Undefined);
sourceRecord = New Structure("Name", "источник");
recordSnapshot = Новый ФиксированнаяСтруктура(sourceRecord);
sourceRecord.Name = "изменено"; sourceRecord.Insert("Extra", 1);
Message(recordSnapshot.Name); Message(recordSnapshot.Count());
visited = 0;
For Each pair In s Do
    visited = visited + 1;
    Message(TypeOf(pair) = Type("КлючИЗначение"));
EndDo;
Message(visited);
sourceMap = New Map;
sourceMap[True] = "булево"; sourceMap[1] = "число";
m = Новый ФиксированноеСоответствие(sourceMap);
sourceMap[1] = "изменено"; sourceMap.Insert(2, 3);
Message(m.Количество()); Message(m.Get(True)); Message(m.Получить(1));
Message(m.Get("missing") = Undefined);
visited = 0;
For Each pair In m Do visited = visited + 1; EndDo;
Message(visited);
copyArray = New Array(a); copyArray[0] = 20; copyArray.Add(30);
copyRecord = New Structure(s); copyRecord.Name = "копия";
copyMap = New Map(m); copyMap[1] = "копия"; copyMap.Insert(2, 2);
Message(a[0]); Message(copyArray.Count());
Message(s.Name); Message(copyRecord.Name); Message(m[1]); Message(copyMap.Count());
Message(TypeOf(a)); Message(TypeOf(s)); Message(TypeOf(m));
Message(TypeOf(a) = Тип("фИкСиРоВаНнЫйМаСсИв"));
Message(TypeOf(s) = Type("fIxEdStRuCtUrE"));
Message(TypeOf(m) = Тип("ФиксированноеСоответствие"));
Message(Type("FixedArray") = Тип("ФиксированныйМассив"));
Message(Type("FixedMap") = Тип("ФиксированноеСоответствие"));
Message(TypeOf(copyArray)); Message(TypeOf(copyRecord)); Message(TypeOf(copyMap));
'''
        fixed_output = ('2\n1\n4\n8\n1\nДа\n12\nснимок\nснимок\n7\n2\nДа\nснимок\nНет\nДа\n'
                        'источник\n1\nДа\nДа\n2\n2\nбулево\nчисло\nДа\n2\n4\n3\nснимок\nкопия\n'
                        'число\n3\nФиксированныйМассив\nФиксированнаяСтруктура\n'
                        'ФиксированноеСоответствие\nДа\nДа\nДа\nДа\nДа\nМассив\nСтруктура\nСоответствие\n')
        fixed_mutations = ['a[0] = 1', 's.Name = "changed"', 's["Name"] = "changed"',
                           'm[1] = "changed"', 'a.Add(1)', 'a.Добавить(1)',
                           'a.Set(0, 1)', 'a.Установить(0, 1)', 'a.Insert(0, 1)',
                           'a.Вставить(0, 1)', 'a.Delete(0)', 'a.Удалить(0)',
                           'a.Clear()', 'a.Очистить()', 's.Insert("Extra", 1)',
                           's.Вставить("Extra", 1)', 's.Delete("Name")', 's.Удалить("Name")',
                           's.Clear()', 's.Очистить()', 'm.Insert(1, 1)', 'm.Вставить(1, 1)',
                           'm.Delete(1)', 'm.Удалить(1)', 'm.Clear()', 'm.Очистить()']
        # Native collections.out observes reference identity for equality,
        # mutable-array Find and map keys, even with equal snapshot contents.
        for name, constructor in [('a', 'New FixedArray(New Array(a))'),
                                  ('s', 'New FixedStructure(New Structure(s))'),
                                  ('m', 'New FixedMap(New Map(m))')]:
            fixed_code += f'''alias = {name}; other = {constructor};
Message({name} = alias); Message({name} <> alias);
Message({name} = other); Message({name} <> other);
values = New Array; values.Add({name});
Message(values.Find(alias)); Message(values.Find(other) = Undefined);
keys = New Map; keys.Insert({name}, 1);
Message(keys.Get(alias)); Message(keys.Get(other) = Undefined);
keys.Insert(other, 2); Message(keys.Count()); Message(keys.Get({name}));
fixedKeys = New FixedMap(keys); keys.Delete(alias);
Message(keys.Count()); Message(fixedKeys.Get({name})); Message(fixedKeys.Get(other));
'''
            fixed_output += 'Да\nНет\nНет\nДа\n0\nДа\n1\nДа\n2\n1\n1\n1\n2\n'
        fixed_code += '''leaf = New Array(1); leaf[0] = 5;
branch = New Array; branch.Add(leaf);
nested = New Array; nested.Add(branch);
frozenNested = New FixedArray(nested);
Message(TypeOf(frozenNested[0]) = Type("FixedArray"));
Message(TypeOf(frozenNested[0][0]) = Type("FixedArray"));
leaf[0] = 6; Message(frozenNested[0][0][0]); Message(leaf[0]);
repeatedLeaf = New Array(1); repeatedLeaf[0] = 11;
fixedLeaf = New FixedArray(repeatedLeaf);
repeated = New Array; repeated.Add(fixedLeaf); repeated.Add(fixedLeaf);
copyRepeated = New Array(New FixedArray(repeated));
Message(TypeOf(copyRepeated[0]) = Type("Array"));
copyRepeated[0][0] = 12;
Message(copyRepeated[0][0]); Message(copyRepeated[1][0]); Message(fixedLeaf[0]);
words = New Array; words.Add("а"); words.Add("б");
fixedWords = New FixedArray(words);
Message(StrConcat(fixedWords, ";")); Message(СтрСоединить(fixedWords, ";"));
'''
        fixed_output += 'Да\nДа\n5\n6\nДа\n12\n11\n11\nа;б\nа;б\n'
        fixed_mutations += ['New FixedArray(a)', 'New FixedStructure(s)', 'New FixedMap(m)',
                            'frozenNested[0][0][0] = 7', 'Message(m["missing"])']
        for action in fixed_mutations:
            fixed_code += f'Try\n{action};\nExcept\nMessage("blocked");\nEndTry;\n'
        fixed_code += ('Message(a[0]); Message(s.Name); Message(m[1]); '
                       'Message(frozenNested[0][0][0]); Message(leaf[0]);\n')
        fixed_output += 'blocked\n' * len(fixed_mutations) + '4\nснимок\nчисло\n5\n6\n'
        fixed_file = Path(temporary) / 'Фиксированные.bsl'
        fixed_file.write_text(fixed_code, encoding='utf-8-sig')
        fixed_module = project / 'Снимки.bsl'
        fixed_module.write_text(
            'Procedure Fail() Export\na = New FixedArray(New Array(1));\na[0] = 9;\nEndProcedure\n'
            'Function Values() Export Return New FixedArray(New Array(2)); EndFunction\n'
            'Function Record() Export Return New FixedStructure("Name", "из модуля"); EndFunction\n'
            'Function Lookup() Export\n'
            'm = New Map; m["key"] = 42; Return New FixedMap(m);\nEndFunction\n',
            encoding='utf-8-sig')
        fixed_importer = project / 'ИмпортСнимков.bsl'
        fixed_importer.write_text(
            '// #Импорт Снимки.bsl\n'
            'a = Снимки.Values(); s = Снимки.Record(); m = Снимки.Lookup();\n'
            'Message(a.Count()); Message(s.Name); Message(m["key"]);\n'
            'Message(TypeOf(a)); Message(TypeOf(s)); Message(TypeOf(m));\n'
            'Try\nСнимки.Fail();\nExcept\nMessage(ErrorDescription());\nEndTry;\n'
            'Message("продолжено");\n', encoding='utf-8-sig')
        fixed_import_output = ('2\nиз модуля\n42\nФиксированныйМассив\nФиксированнаяСтруктура\n'
                               'ФиксированноеСоответствие\n' + str(fixed_module.resolve()) +
                               ':3:1: Элементы фиксированного массива недоступны для записи\nпродолжено\n')
        fixed_error_importer = project / 'ОшибкаИмпортаСнимков.bsl'
        fixed_error_importer.write_text('// #Импорт Снимки.bsl\nСнимки.Fail();\n', encoding='utf-8')
        fixed_error_file = project / 'ОшибкаСнимка.bsl'
        fixed_error_file.write_text('s = New FixedStructure("Name", 1);\ns.Name = 2;\n', encoding='utf-8-sig')
        cases = [
            ([str(fixed_file)], None, fixed_output, 0),
            (['-c', fixed_code], None, fixed_output, 0),
            (['-'], fixed_code, fixed_output, 0),
            ([], fixed_code + '/exit\n', fixed_output, 0),
            ([str(fixed_importer)], None, fixed_import_output, 0),
            ([str(Path('project') / fixed_importer.name)], None, fixed_import_output, 0),
            ([str(type_file)], None, type_output, 0),
            (['-c', type_code], None, type_output, 0),
            (['-'], type_code, type_output, 0),
            ([], type_code + '/exit\n', type_output, 0),
            ([str(type_importer)], None,
             f'Строка\nТип\n{type_module.resolve()}:2:12: Тип не поддерживается: Date\nДа\n', 0),
            ([str(region_file)], None, '42\n', 0),
            (['-c', region_code], None, '42\n', 0),
            (['-'], region_code, '42\n', 0),
            ([], region_code + '/exit\n', '42\n', 0),
            (['-c', '#Region Example\nMessage(42);\n#EndRegion\n'], None, '42\n', 0),
            ([str(map_file)], None, map_output, 0),
            (["-c", map_code], None, map_output, 0),
            (["-"], map_code, map_output, 0),
            ([], map_code + '/exit\n', map_output, 0),
            ([str(structure_file)], None, structure_output, 0),
            (["-c", structure_code], None, structure_output, 0),
            (["-"], structure_code, structure_output, 0),
            ([], structure_code + '/exit\n', structure_output, 0),
            ([str(string_file)], None, string_output, 0),
            (["-c", string_code], None, string_output, 0),
            (["-"], string_code, string_output, 0),
            ([], string_code + '/exit\n', string_output, 0),
            ([str(exception_main)], None, str(exception_module.resolve()) + ":3:1: из модуля\n", 0),
            (["-c", exception_code], None, "обработано\n", 0),
            (["-"], exception_code, "обработано\n", 0),
            ([], exception_code + '/exit\n', "обработано\n", 0),

            (["-c", client_code], None, "42\n", 0),
            (["-"], client_code, "42\n", 0),
            ([], client_code + '/exit\n', "42\n", 0),
            ([str(directory_importer)], None, "3\nвложенный\n", 0),

            ([str(importer)], None, "3\n", 0),
            ([str(nested_importer)], None, "3\nвложенный\n", 0),
            ([str(Path("project") / nested_importer.name)], None, "3\nвложенный\n", 0),
            ([str(sample)], None, expected, 0),
            (["-c", 'Сообщить("Привет")'], None, "Привет\n", 0),
            (["-с", 'Сообщить("Кириллица")'], None, "Кириллица\n", 0),
            ([], 'х = 40;\nЕсли Истина Тогда\nх = х + 2;\nКонецЕсли;\nСообщить(х);\n/exit\n', "42\n", 0),
            (["-"], 'Сообщить("stdin")', "stdin\n", 0),
            (["-c", "Сообщить(1 / 0)"], None, "", 1),
        ]
        for arguments, stdin, stdout, code in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding="utf-8", cwd=temporary, env=env, timeout=30)
            if result.returncode != code or result.stdout != stdout:
                raise AssertionError(f"Failed {arguments!r}: {result!r}")
            if code == 0 and result.stderr:
                raise AssertionError(result.stderr)
            if code and ("Деление на ноль" not in result.stderr or "Traceback" in result.stderr):
                raise AssertionError(result.stderr)
        fixed_errors = [
            (['-c', 'a = New FixedArray(New Array);\nNew FixedArray(a);'], None, '',
             '<команда>:2:1:', 'ФиксированныйМассив ожидает массив'),
            (['-c', 's = New FixedStructure;\nNew FixedStructure(s);'], None, '',
             '<команда>:2:1:', 'ФиксированнаяСтруктура ожидает строку свойств или структуру'),
            (['-'], 'm = New FixedMap(New Map);\nNew FixedMap(m);\n', '',
             '<stdin>:2:1:', 'ФиксированноеСоответствие ожидает соответствие'),
            (['-c', 'm = New FixedMap(New Map);\nMessage(m["missing"]);'], None, '',
             '<команда>:2:', 'Ключ фиксированного соответствия не найден'),
            (['-c', 'a = New FixedArray(New Array(1));\na[0] = 2;'], None, '',
             '<команда>:2:', 'недоступны для записи'),
            (['-'], 'm = New FixedMap(New Map);\nm[1] = 2;\n', '',
             '<stdin>:2:', 'недоступны для записи'),
            (['-c', 'New FixedArray(1);'], None, '', '<команда>:1:', 'ожидает массив'),
            (['-c', 'New FixedStructure(1);'], None, '', '<команда>:1:', 'ожидает строку свойств или структуру'),
            (['-c', 'New FixedMap(1);'], None, '', '<команда>:1:', 'ожидает соответствие'),
            (['-c', 'a = New FixedArray(New Array);\na.Add(1);'], None, '',
             '<команда>:2:', 'не найдено: Add'),
            ([str(fixed_error_file.resolve())], None, '', str(fixed_error_file.resolve()) + ':2:1:',
             'недоступно для записи'),
            ([str(Path('project') / fixed_error_file.name)], None, '',
             str(Path('project') / fixed_error_file.name) + ':2:1:', 'недоступно для записи'),
            ([str(fixed_error_importer)], None, '', str(fixed_module.resolve()) + ':3:',
             'недоступны для записи'),
            ([str(Path('project') / fixed_error_importer.name)], None, '',
             str(fixed_module.resolve()) + ':3:', 'недоступны для записи'),
            ([], 'a = New FixedArray(\nNew Array(2));\na[0] = 9;\n'
             'a.Count()\n(a[0] = Undefined)\nTypeOf(a)\n/exit\n',
             '2\nДа\nФиксированныйМассив\n', '<консоль>:1:', 'недоступны для записи'),
        ]
        for arguments, stdin, stdout, location, message in fixed_errors:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=temporary, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed fixed-collection diagnostics {arguments!r}: {result!r}')
        type_errors = [
            (['-c', 'Type("Date");'], None, '', '<команда>:1:', 'Тип не поддерживается: Date'),
            (['-c', 'Тип(1);'], None, '', '<команда>:1:', 'Имя типа должно быть строкой'),
            (['-c', 'TypeOf(Message);'], None, '', '<команда>:1:',
             'ТипЗнч для этого значения пока не поддерживается'),
            (['-'], 'Тип("Дата");\n', '', '<stdin>:1:', 'Тип не поддерживается: Дата'),
            ([str(type_error_file)], None, '', str(type_error_file) + ':2:',
             'ТипЗнч для этого значения пока не поддерживается'),
            ([str(type_error_importer)], None, '', str(type_module.resolve()) + ':2:',
             'Тип не поддерживается: Date'),
            ([], 'kind = Type("Number");\nkind = Type("Date");\n'
             'kind\nTypeOf(kind)\n/exit\n', 'Число\nТип\n', '<консоль>:1:',
             'Тип не поддерживается: Date'),
        ]
        for arguments, stdin, stdout, location, message in type_errors:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=temporary, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed type diagnostics {arguments!r}: {result!r}')
        unfinished_region = '#Область Незавершенная\nСообщить("рано");\n'
        region_errors = [
            (['-c', '#EndRegion'], None, '<команда>:1:', '#Область'),
            (['-c', '#Область'], None, '<команда>:1:', '#Область'),
            (['-c', '#Region Name extra'], None, '<команда>:1:', '#Область'),
            (['-c', '#Область Имя\n#КонецОбласти хвост'], None,
             '<команда>:2:', '#КонецОбласти'),
            (['-c', unfinished_region], None, '<команда>:1:', '#КонецОбласти'),
            (['-'], unfinished_region, '<stdin>:1:', '#КонецОбласти'),
            ([], unfinished_region, '<консоль>:1:', '#КонецОбласти'),
            ([str(region_error_main)], None, str(region_error_module.resolve()) + ':4:',
             'Деление на ноль'),
        ]
        for arguments, stdin, location, message in region_errors:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=temporary, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed region diagnostics {arguments!r}: {result!r}')
        if os.name != "nt":
            from console_check import check_console

            check_console([executable], cwd=temporary, env=env)
            print("Binary terminal tests passed: cursor editing, history, multiline input, region continuation, type values, fixed collections, numeric presentation, rounding, division and error recovery")
    print("Binary smoke tests passed: rounding, division, numeric presentation, fixed collections, type values, maps, structures, strings/UTF-16, file, sibling/nested/directory imports, exceptions, client compilation, regions, -c, -с, console, stdin, errors")


if __name__ == "__main__":
    main()
