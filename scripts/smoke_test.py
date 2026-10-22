"""Test the distributed executable outside the source tree and without PYTHONPATH."""

import os
import hashlib
from datetime import datetime, timezone
import re
import time
from pathlib import Path
import subprocess
import sys
import tempfile


if __package__:
    from .native_historical_replay import historical_collections_source, historical_values_source
else:
    from native_historical_replay import historical_collections_source, historical_values_source

ROOT = Path(__file__).resolve().parents[1]


# Date values below come from the owner's native dates.out checkpoint. In
# particular, arithmetic retains ticks while the internal Date stream loses them.
DATE_EXAMPLES = [
    ('dAtE(2024, 2, 29, 12, 34, 56)', '{"D",20240229123456}'),
    ('дАтА(2024, 2, 29)', '{"D",20240229000000}'),
    ('Date("20240229123456")', '{"D",20240229123456}'),
    ('Дата("20240229")', '{"D",20240229000000}'),
    ("'20240229'", '{"D",20240229000000}'),
    ("'202402291234'", '{"D",20240229123400}'),
    ("'20240229123456'", '{"D",20240229123456}'),
    ("'2024-02-29 12:34:56'", '{"D",20240229123456}'),
    ('Date(2024, 2, 29, 12, 34, 56.9) - baseDate', '{"N",0}'),
    ('Date(1, 1, 1)', '{"D",00010101000000}'),
    ('Date(9999, 12, 31, 23, 59, 59)', '{"D",99991231235959}'),
    ('Type("Date")', '{"T",aae38c48-a877-411c-a6d3-fbaa1f83c4bd}'),
    ('Тип("Дата")', '{"T",aae38c48-a877-411c-a6d3-fbaa1f83c4bd}'),
    ('TypeOf(baseDate)', '{"T",aae38c48-a877-411c-a6d3-fbaa1f83c4bd}'),
    ('ValueFromStringInternal(ValueToStringInternal(baseDate))', '{"D",20240229123456}'),
    ('ValueFromStringInternal(ValueToStringInternal(Type("Date")))',
     '{"T",aae38c48-a877-411c-a6d3-fbaa1f83c4bd}'),
    ('String(baseDate)', '{"S","29.02.2024 12:34:56"}'),
    ('Строка(Date(1, 1, 1))', '{"S","01.01.0001 0:00:00"}'),
    ('ValueIsFilled(Date(1, 1, 1))', '{"B",0}'),
    ('ЗначениеЗаполнено(Date(1, 1, 1, 0, 0, 1))', '{"B",1}'),
    ('Date(2024, 2, 29, 23, 59, 59) + 1', '{"D",20240301000000}'),
    ('Date(2024, 3, 1) - 1', '{"D",20240229235959}'),
    ('Date(2024, 3, 1) - Date(2024, 2, 28)', '{"N",172800}'),
    ('Date(1, 1, 1) - 1', '{"D",00010101000000}'),
    ('Date(9999, 12, 31, 23, 59, 59) + 1', '{"D",99991231235959}'),
    ('Date(2024, 2, 29) = Date("20240229")', '{"B",1}'),
    ('Date(2024, 2, 29) < Date(2024, 3, 1)', '{"B",1}'),
    ('Date(1, 1, 1) = 0', '{"B",0}'),
    ('(baseDate + 0.0001) - baseDate', '{"N",0.0001}'),
    ('(baseDate + 0.00005) - baseDate', '{"N",0.0001}'),
    ('(baseDate + 0.00015) - baseDate', '{"N",0.0002}'),
    ('(baseDate + -0.0001) - baseDate', '{"N",-0.0001}'),
    ('(baseDate + -0.00005) - baseDate', '{"N",-0.0001}'),
    ('(baseDate + -0.00015) - baseDate', '{"N",-0.0002}'),
    ('baseDate + 0.1234', '{"D",20240229123456}'),
    ('ValueFromStringInternal(ValueToStringInternal(baseDate + 0.1234)) - baseDate', '{"N",0}'),
    ('(baseDate + 0.4) - baseDate', '{"N",0.4}'),
    ('(baseDate + 0.5) - baseDate', '{"N",0.5}'),
    ('(baseDate + 0.6) - baseDate', '{"N",0.6}'),
    ('(baseDate - 0.4) - baseDate', '{"N",-0.4}'),
    ('(baseDate - 0.5) - baseDate', '{"N",-0.5}'),
    ('(baseDate - 0.6) - baseDate', '{"N",-0.6}'),
    ('Second(baseDate + 0.5)', '{"N",56}'),
]
for _english, _russian, _value in [('Year', 'Год', 2024), ('Month', 'Месяц', 2),
                                  ('Day', 'День', 29), ('Hour', 'Час', 12),
                                  ('Minute', 'Минута', 34), ('Second', 'Секунда', 56)]:
    DATE_EXAMPLES += [(f'{name}(baseDate)', '{"N",' + str(_value) + '}')
                     for name in (_english, _russian)]

# Whole-second values and numbering below are observed in the owner's 48-case
# calendar append. Numeric deltas witness fractions that the D codec discards.
for _unit, _suffix, _begin, _end in (
        ('Minute', 'Минуты', '20240229123400', '20240229123459'),
        ('Hour', 'Часа', '20240229120000', '20240229125959'),
        ('Day', 'Дня', '20240229000000', '20240229235959'),
        ('Week', 'Недели', '20240226000000', '20240303235959'),
        ('Month', 'Месяца', '20240201000000', '20240229235959'),
        ('Quarter', 'Квартала', '20240101000000', '20240331235959'),
        ('Year', 'Года', '20240101000000', '20241231235959')):
    for _name, _value in (('BegOf' + _unit, _begin), ('Начало' + _suffix, _begin),
                          ('EndOf' + _unit, _end), ('Конец' + _suffix, _end)):
        DATE_EXAMPLES += [(f'{_name}(baseDate + 0.1234)', '{"D",' + _value + '}'),
                          (f'{_name}(baseDate + 0.1234) - Date("{_value}")', '{"N",0}')]
for _name in ('AddMonth', 'ДобавитьМесяц'):
    DATE_EXAMPLES += [
        (f'{_name}(Date(2024,1,31,12,34,56) + 0.1234,1)', '{"D",20240229123456}'),
        (f'{_name}(Date(2024,1,31,12,34,56) + 0.1234,1) - baseDate', '{"N",0}'),
        (f'{_name}(baseDate + 0.1234,0) - baseDate', '{"N",0}'),
        (f'{_name}(Date(2024,5,15),1.5)', '{"D",20240615000000}'),
        (f'{_name}(Date(2024,5,15),-1.5)', '{"D",20240415000000}'),
        (f'{_name}(Date(1,1,1),-1)', '{"D",00010101000000}'),
        (f'{_name}(Date(9999,12,31,23,59,59),1)', '{"D",00010101000000}'),
    ]
for _name in ('WeekOfYear', 'НеделяГода'):
    DATE_EXAMPLES += [(f'{_name}(Date(2016,1,4))', '{"N",2}'),
                      (f'{_name}(Date(2021,2,1))', '{"N",6}'),
                      (f'{_name}(Date(2024,3,3))', '{"N",9}'),
                      (f'{_name}(Date(2024,3,4))', '{"N",10}')]
for _name in ('WeekDay', 'ДеньНедели'):
    DATE_EXAMPLES += [(f'{_name}(Date(2024,3,3))', '{"N",7}'),
                      (f'{_name}(Date(2024,3,4))', '{"N",1}')]
for _name in ('DayOfYear', 'ДеньГода'):
    DATE_EXAMPLES += [(f'{_name}(baseDate)', '{"N",60}'),
                      (f'{_name}(Date(2024,12,31))', '{"N",366}')]
DATE_EXAMPLES += [('EndOfWeek(Date(9999,12,31,23,59,59))', '{"D",99991231235959}')]

DATE_FAILURES = [
    ('BegOfDay(0)', 'Ожидается дата'),
    ('AddMonth(Date(2024,2,29), Undefined)', 'ДобавитьМесяц: ожидается конечное число месяцев'),
    ('WeekOfYear(Date(1,1,1) - 1)', 'после выхода за диапазон известно только скалярное'),
    ('String(AddMonth(Date(1,1,1),-1))', 'после выхода за диапазон известно только скалярное'),
    ('EndOfWeek(Date(9999,12,30))', 'КонецНедели: непроверенный выход за диапазон даты'),

    ('Date(2024, 2, 29, 12)', 'Дата: ожидается строка или 3 либо 6 числовых компонентов'),
    ('Date(2024, 2, 29, 12, 34)', 'Дата: ожидается строка или 3 либо 6 числовых компонентов'),
    ('Date(2024, 2, 29, , , 56)', 'Пропуск аргументов встроенных функций, методов и конструкторов'),
    ('Date(True, 2, 29)', 'Дата: компоненты должны быть конечными числами'),
    ('Date("202402291234")', 'Дата: ожидается каноническая запись даты'),
    ('Date(0, 1, 1)', 'Дата: компонент вне диапазона'),
    ('Date(10000, 1, 1)', 'Дата: компонент вне диапазона'),
    ('1 + Date(2024, 2, 29)', 'Ожидается число'),
    ('Date(2024, 2, 29) + True', 'Арифметика даты: ожидается число секунд'),
    ('Year(1)', 'Ожидается дата'),
    ('New Date', 'Тип не определен: Date'),
    ('String(Date(1, 1, 1) - 1)', 'после выхода за диапазон известно только скалярное'),
    ('Year(Date(9999, 12, 31, 23, 59, 59) + 1)',
     'после выхода за диапазон известно только скалярное'),
    ('(Date(1, 1, 1) - 1) + 0', 'после выхода за диапазон известно только скалярное'),
    ('(Date(1, 1, 1) - 1) = Date(1, 1, 1)',
     'после выхода за диапазон известно только скалярное'),
]
DATE_PROGRAM = 'baseDate = Date(2024, 2, 29, 12, 34, 56);\n'
DATE_OUTPUT = ''
for _expression, _stream in DATE_EXAMPLES:
    DATE_PROGRAM += f'Message(ValueToStringInternal({_expression}));\n'
    DATE_OUTPUT += _stream + '\n'
DATE_PROGRAM += '''mapping = New Map;
mapping.Insert(baseDate, "first");
mapping.Insert(Date(2024, 2, 29, 12, 34, 56), "second");
restored = ValueFromStringInternal(ValueToStringInternal(mapping));
Message(mapping.Count()); Message(mapping.Get(baseDate));
Message(restored.Count()); Message(restored.Get(baseDate));
Function DefaultDate(value = '20240229123456')
Return value;
EndFunction
Message(ValueToStringInternal(DefaultDate()));
Message(ValueToStringInternal(DefaultDate('20240229')));
savedDate = baseDate;
'''
DATE_OUTPUT += '1\nsecond\n1\nsecond\n{"D",20240229123456}\n{"D",20240229000000}\n'
for _expression, _message in DATE_FAILURES:
    DATE_PROGRAM += (f'Try savedDate = {_expression}; Except\n'
                     f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                     'EndTry; Message(savedDate = baseDate);\n')
    DATE_OUTPUT += 'Да\nДа\n'
DATE_PROGRAM += '''Try savedDate = Date(2023, 2, 29); Except Message("nonleap-caught"); EndTry;
Message(savedDate = baseDate); Message(ValueToStringInternal(savedDate));
'''
DATE_OUTPUT += 'nonleap-caught\nДа\n{"D",20240229123456}\n'

DATE_MODULE = '''Function DefaultDate(value = '20240229123456') Export
Return value;
EndFunction
Function Shift(value, seconds) Export
Return value + seconds;
EndFunction
Function Failure() Export
Return Year(1);
EndFunction
'''
DATE_IMPORT_PROGRAM = '''// #Импорт Даты.bsl
value = Даты.DefaultDate(); Message(TypeOf(value));
Message(ValueToStringInternal(value));
Message(ValueToStringInternal(Даты.DefaultDate('20240229')));
shifted = Даты.Shift(value, 0.00015);
Message(ValueToStringInternal(shifted - value));
Message(ValueToStringInternal(ValueFromStringInternal(ValueToStringInternal(shifted)) - value));
Try value = Даты.Failure(); Except Message("date-import-caught"); EndTry;
Message(ValueToStringInternal(value));
Message(ValueToStringInternal(Даты.Shift(value, 1)));
'''
DATE_IMPORT_OUTPUT = ('Дата\n{"D",20240229123456}\n{"D",20240229000000}\n'
                      '{"N",0.0002}\n{"N",0}\ndate-import-caught\n'
                      '{"D",20240229123456}\n{"D",20240229123457}\n')


def check_dates(executable: str, *, directory: Path, env: dict) -> None:
    """Date checkpoint across frozen inputs, imports and recoverable failures."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'КалендарныеДаты.bsl'
    source.write_text(DATE_PROGRAM, encoding='utf-8-sig')
    module = directory / 'Даты.bsl'
    module.write_text(DATE_MODULE, encoding='utf-8-sig')
    importer = directory / 'ИмпортДат.bsl'
    importer.write_text(DATE_IMPORT_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, DATE_PROGRAM], None, DATE_OUTPUT) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None, DATE_OUTPUT), (['-'], DATE_PROGRAM, DATE_OUTPUT),
              ([], DATE_PROGRAM + '/exit\n', DATE_OUTPUT)]
    cases += [([str(path)], None, DATE_IMPORT_OUTPUT)
              for path in (importer, importer.relative_to(directory.parent))]
    for arguments, stdin, expected in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Failed Date checkpoint {arguments!r}: {result!r}')
    for expression, message in DATE_FAILURES:
        code = f'savedDate = Date(2024, 2, 29);\nsavedDate = {expression};\n'
        source.write_text(code, encoding='utf-8-sig')
        errors = [([flag, code], None, '', '<команда>:2:') for flag in ('-c', '-с', '--command')]
        errors += [([str(source)], None, '', str(source.resolve()) + ':2:'),
                   (['-'], code, '', '<stdin>:2:'),
                   ([], code + 'ValueToStringInternal(savedDate)\n/exit\n',
                    '{"D",20240229000000}\n', '<консоль>:1:')]
        for arguments, stdin, stdout, location in errors:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed Date diagnostic {arguments!r}: {result!r}')
    importer.write_text('// #Импорт Даты.bsl\nДаты.Failure();\n', encoding='utf-8-sig')
    for path in (importer, importer.relative_to(directory.parent)):
        result = subprocess.run([executable, str(path)], capture_output=True, encoding='utf-8',
                                cwd=directory.parent, env=env, timeout=30)
        if (result.returncode != 1 or result.stdout or str(module.resolve()) + ':8:' not in result.stderr
                or 'Ожидается дата' not in result.stderr or 'Traceback' in result.stderr):
            raise AssertionError(f'Failed imported Date diagnostic {path!r}: {result!r}')
    for literal, message in [("'2024022912'", 'Дата: ожидается каноническая запись даты'),
                             ("'20240229", 'Незавершенный литерал даты')]:
        code = '// строка перед ошибкой\nsavedDate = ' + literal
        source.write_text(code, encoding='utf-8-sig')
        errors = [([flag, code], None, '<команда>:2:') for flag in ('-c', '-с', '--command')]
        errors += [([str(source)], None, str(source.resolve()) + ':2:'),
                   (['-'], code, '<stdin>:2:')]
        for arguments, stdin, location in errors:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed Date literal diagnostic {arguments!r}: {result!r}')
    code = ("savedDate = Date(2024, 2, 29);\nsavedDate = '20240229\n"
            'ValueToStringInternal(savedDate)\nsavedDate = Date(\n2024, 2, 29, 12, 34, 56);\n'
            'ValueToStringInternal(savedDate)\n/exit\n')
    result = subprocess.run([executable], input=code, capture_output=True,
                            encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
    if (result.returncode != 1 or result.stdout != '{"D",20240229000000}\n{"D",20240229123456}\n'
            or '<консоль>:1:' not in result.stderr or 'Traceback' in result.stderr
            or 'Перенос строки в литерале даты не поддерживается' not in result.stderr):
        raise AssertionError(f'Failed incomplete Date literal recovery: {result!r}')
    print('Binary Date checks passed: native literals, constructors, ticks, lossy codec, components, '
          'calendar periods/month shifts/week numbering, BOM files, imports/defaults, command flags, stdin, console and guarded errors')


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


CHARACTER_PROGRAM = '''
Message(cHaR("65")); Сообщить(сИмВоЛ(1046));
Message(ValueToStringInternal(CharCode(Char(65535))));
Message(ValueToStringInternal(КодСимвола(Символ(65.9))));
Message(ValueToStringInternal(CharCode(Char(0.0001))));
Message(ValueToStringInternal(CharCode(Char(True))));
Message(StrLen(Char(-1))); Message(StrLen(Символ(65536)));
Message(StrLen(Char(Number("1e1000000"))));
Message(StrLen(Символ(Number("-1e1000000"))));
text = Char(0) + Символ(55357) + Char(56898) + Символ(55296);
restored = ЗначениеИзСтрокиВнутр(ValueToStringInternal(text));
Message(restored = text); Message(StrLen(restored)); Message(TypeOf(restored));
For position = 1 To 4 Do
    Message(ValueToStringInternal(кОдСиМвОлА(restored, position)));
EndDo;
Message(ValueToStringInternal(CharCode(Left(restored, 2), 2)));
Message(ValueToStringInternal(CharCode("🙂", 2)));
Message(ValueToStringInternal(cHaRcOdE("AB")));
Message(ValueToStringInternal(CharCode("AB", 1.9)));
Message(ValueToStringInternal(КодСимвола("AB", "2")));
Message(ValueToStringInternal(CharCode(123)));
Message(ValueToStringInternal(CharCode("")));
Message(ValueToStringInternal(КодСимвола("AB", 0)));
Message(ValueToStringInternal(CharCode("AB", -1)));
Message(ValueToStringInternal(CharCode("AB", 3)));
Message(ValueToStringInternal(CharCode("AB", Number("1e1000000"))));
Message(TypeOf(CharCode("A")));
saved = Символ(65);
'''
CHARACTER_OUTPUT = ('A\nЖ\n{"N",65535}\n{"N",65}\n{"N",0}\n{"N",1}\n'
                    '0\n0\n0\n0\nДа\n4\nСтрока\n'
                    '{"N",0}\n{"N",55357}\n{"N",56898}\n{"N",55296}\n'
                    '{"N",55357}\n{"N",56898}\n{"N",65}\n{"N",65}\n'
                    '{"N",66}\n{"N",49}\n{"N",-1}\n{"N",-1}\n'
                    '{"N",-1}\n{"N",-1}\n{"N",-1}\nЧисло\n')
CHARACTER_FAILURES = (
    ('Char(Undefined)', 'Невозможно преобразовать значение в число'),
    ('Символ(Undefined)', 'Невозможно преобразовать значение в число'),
    ('CharCode("A", Undefined)', 'Невозможно преобразовать значение в число'),
    ('КодСимвола("A", Undefined)', 'Невозможно преобразовать значение в число'),
)
for _expression, _message in CHARACTER_FAILURES:
    CHARACTER_PROGRAM += (f'Try saved = {_expression}; Except\n'
                          f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                          'EndTry;\nMessage(saved);\n')
    CHARACTER_OUTPUT += 'Да\nA\n'
CHARACTER_PROGRAM += 'Message(Char(КодСимвола("Ж")));\n'
CHARACTER_OUTPUT += 'Ж\n'


EVAL_PROGRAM = '''
Var shared;
Function EvalBump(value)
    value = value + 1;
    Return value;
EndFunction
Function EvalRead(parameter)
    local = 14;
    Return Eval("local + shared + parameter");
EndFunction
shared = 23;
Message(Вычислить("500 + 500*20/100"));
Message(EvalRead(3));
x = 10; Message(eVaL("EvalBump(x)")); Message(x);
Message(Eval("1 + 2 // комментарий"));
Message(Eval(12));
Message(Eval("СтрДлина(""Я😀"")"));
Message(ValueFromStringInternal(ValueToStringInternal(Eval("True"))));
saved = 42;
Try saved = Eval("1 +"); Except Message("eval-syntax-caught"); EndTry;
Message(saved);
Try Eval("1", EvalBump(x)); Except Message("eval-arity-caught"); EndTry;
Message(x);
loop = "Eval(loop)";
Try Eval(loop); Except Message("eval-depth-caught"); EndTry;
Message(Eval("?(True, 7, 1/0)"));
'''
EVAL_OUTPUT = ('600\n40\n11\n11\n3\n12\n3\nДа\neval-syntax-caught\n42\n'
               'eval-arity-caught\n11\neval-depth-caught\n7\n')


def check_eval(executable: str, *, directory: Path, env: dict) -> None:
    """Dynamic BSL expressions across every binary input mode."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'ВычислениеВыражения.bsl'
    source.write_text(EVAL_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, EVAL_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], EVAL_PROGRAM),
              ([], EVAL_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, EVAL_OUTPUT, ''):
            raise AssertionError(f'Failed Eval {arguments!r}: {result!r}')
    print('Binary Eval passed: context, reference, parse/arity/depth errors, '
          'BOM file, command flags, stdin and console recovery')


STRING_PARITY_PROGRAM = """
Message(СтрЧислоВхождений("aaaa", "aa"));
Message(StrOccurrenceCount("abc", ""));
Message(StrOccurrenceCount("", ""));
Message(StrOccurrenceCount("AaA", "a"));
Message(сТрЧиСлОвХоЖдЕнИй("Я😀Я😀", "😀"));
Message(StrOccurrenceCount(12121, "1"));
Message(ValueToStringInternal(StrTemplate("%2", "x")));
Message(StrTemplate("[%1]|[%2]", "Я"));
Message(StrTemplate("%%"));
Message(ValueFromStringInternal(ValueToStringInternal(StrOccurrenceCount("aaaa", "aa"))));
Try StrOccurrenceCount("a"); Except Message("occurrence-caught"); EndTry;
Message(StrOccurrenceCount("ababa", "aba"));
"""
STRING_PARITY_OUTPUT = '2\n0\n0\n1\n2\n3\n{"S",""}\n[Я]|[]\n%\n2\noccurrence-caught\n1\n'
# StrFind's documented two-argument form shares the UTF-16 Find primitive.
STRING_PARITY_PROGRAM += '''
Message(СтрНайти("Я😀ёж", "ёж"));
Message(sTrFiNd("abc", ""));
Message(StrFind("", ""));
Message(StrFind("ABC", "b"));
Message(ValueFromStringInternal(ValueToStringInternal(StrFind("ababa", "ba"))));
Try StrFind("abc", "b", Undefined); Except Message("strfind-caught"); EndTry;
Message(StrFind("abc", "c"));
'''
STRING_PARITY_OUTPUT += '4\n1\n1\n0\n2\nstrfind-caught\n3\n'



ARRAY_GAP_PROGRAM = """
a = New Array; alias = a; a.Вставить(3, "Я😀");
Message(a.Count()); Message(a.UBound()); Message(a[0] = Undefined);
Message(a.Find(Undefined)); Message(alias[3]);
f = New FixedArray(a); a.Insert(6); a[1] = "changed";
Message(f.Count()); Message(f[1] = Undefined); Message(a.Count());
b = ValueFromStringInternal(ValueToStringInternal(a));
Message(b[5] = Undefined); Message(b[1]);
Try a.Insert(100000000000000000000); Except Message("array-gap-caught"); EndTry;
Message(a.Count()); a.Insert(0, "head"); Message(a[0]); Message(a[4]);
"""
ARRAY_GAP_OUTPUT = '4\n3\nДа\n0\nЯ😀\n4\nДа\n7\nДа\nchanged\narray-gap-caught\n7\nhead\nЯ😀\n'

# Documented nested-array construction, exercised by the existing array routes.
ARRAY_GAP_PROGRAM += """
m = Новый мАсСиВ(2, 3, 4);
Message(m.Count()); Message(m[1].Count()); Message(m[1][2].Count());
m[0][1][2] = "Я😀";
Message(m[0][1][2]); Message(m[1][1][2] = Undefined);
f = New FixedArray(m); copy = New Array(f);
m[0][1][2] = "changed"; Message(copy[0][1][2]);
copy = ValueFromStringInternal(ValueToStringInternal(copy));
Message(copy[0][1][2]); Message(copy[1][1][2] = Undefined);
Try New Array(2, 0, 9); Except Message("array-zero-caught"); EndTry;
Try m = New Array(1000, 1000); Except Message("array-shape-caught"); EndTry;
Message(m[0][1][2]);
"""
ARRAY_GAP_OUTPUT += '2\n3\n4\nЯ😀\nДа\nЯ😀\nЯ😀\nДа\narray-zero-caught\narray-shape-caught\nchanged\n'


ARRAY_DEFAULT_PROGRAM = """
a = New Array;
a.дОбАвИтЬ();
a.iNsErT(0);
Message(a.Count());
Message(a[0] = Undefined);
Message(a.Get(1) = Undefined);
a[0] = "Я😀";
a.Set(1, "B");
Message(a.Get(0));
Message(a[1]);
f = New FixedArray(a);
a.Add();
Message(f.Count());
Message(a.Count());
b = ValueFromStringInternal(ValueToStringInternal(a));
Message(b.Get(2) = Undefined);
Try a.Insert(); Except Message("array-default-caught"); EndTry;
Message(a.Count());
a.Insert(a.Count());
Message(a.Get(3) = Undefined);
"""
ARRAY_DEFAULT_OUTPUT = '2\nДа\nДа\nЯ😀\nB\n2\n3\nДа\narray-default-caught\n3\nДа\n'


VALUE_FILLED_PROGRAM = """
Message(зНаЧеНиЕзАпОлНеНо(False));
Message(vAlUeIsFiLlEd(Undefined));
Message(ValueIsFilled(0));
Message(ValueIsFilled(-0.01));
Message(ValueIsFilled(" " + Char(9) + Char(10)));
Message(ValueIsFilled("😀"));
a = New Array;
Message(ValueIsFilled(a));
a.Add(Undefined);
Message(ValueIsFilled(a));
Message(ValueIsFilled(New FixedArray(a)));
s = New Structure;
Message(ValueIsFilled(s));
s.Insert("x", Undefined);
Message(ValueIsFilled(New FixedStructure(s)));
m = New Map;
Message(ValueIsFilled(m));
m.Insert("x", Undefined);
Message(ValueIsFilled(New FixedMap(m)));
Message(TypeOf(ValueIsFilled(False)));
Message(ValueToStringInternal(ValueIsFilled(0)));
Message(ValueFromStringInternal(ValueToStringInternal(ValueIsFilled(False))));
saved = "old";
"""
VALUE_FILLED_OUTPUT = ('Да\nНет\nНет\nДа\nНет\nДа\nНет\nДа\nДа\nНет\nДа\nНет\nДа\n'
                       'Булево\n{"B",0}\nДа\n')
VALUE_FILLED_FAILURES = (
    ('ValueIsFilled(Type("Number"))',
     'ЗначениеЗаполнено для этого типа пока не поддерживается в Yadinassi'),
)
for _expression, _message in VALUE_FILLED_FAILURES:
    VALUE_FILLED_PROGRAM += (f'Try saved = {_expression}; Except\n'
                            f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                            'EndTry;\nMessage(saved);\n')
    VALUE_FILLED_OUTPUT += 'Да\nold\n'
VALUE_FILLED_PROGRAM += 'Message(ValueIsFilled(False));\n'
VALUE_FILLED_OUTPUT += 'Да\n'


STRING_LINES_PROGRAM = """
Message(сТрЧиСлОсТрОк(""));
Message(sTrLiNeCoUnT("A" + Char(13) + Char(10) + "B" + Char(13)));
Message(StrLineCount(Char(10) + Char(10)));
Message(СтрПолучитьСтроку("A" + Char(13) + "Я😀", 2));
Message(sTrGeTlInE("A" + Char(10) + "B", 1.9));
Message("[" + StrGetLine("A", 0) + "]");
Message(CharCode(StrGetLine("A" + Char(10) + Char(0), 2)));
Message(TypeOf(StrLineCount("")));
Message(TypeOf(StrGetLine("", 1)));
Message(ValueFromStringInternal(ValueToStringInternal(StrGetLine("😀", 1))));
saved = "old";
"""
STRING_LINES_OUTPUT = '1\n2\n2\nЯ😀\nA\n[]\n0\nЧисло\nСтрока\n😀\n'
STRING_LINES_FAILURES = (('StrGetLine("A", Undefined)', 'Невозможно преобразовать значение в число'),)
for _expression, _message in STRING_LINES_FAILURES:
    STRING_LINES_PROGRAM += (f'Try saved = {_expression}; Except\n'
                            f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                            'EndTry;\nMessage(saved);\n')
    STRING_LINES_OUTPUT += 'Да\nold\n'
STRING_LINES_PROGRAM += 'Message(StrGetLine("new", 1));\n'
STRING_LINES_OUTPUT += 'new\n'


STRING_TEMPLATE_PROGRAM = """
Message(сТрШаБлОн("Привет, %1!", "мир"));
Message(sTrTeMpLaTe("%2/%1/%2", "один", "два"));
Message(StrTemplate("%10/%(1)0", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10));
Message(СтрШаблон("%%1/%%%1", "%2"));
Message(StrTemplate("[%1]", Undefined));
Message(StrTemplate("%1/%2", True, 1234.5));
Message(StrTemplate(Char(55357) + "%1", Char(56832)));
Message(TypeOf(StrTemplate("")));
Message(ValueFromStringInternal(ValueToStringInternal(StrTemplate("[%1]", "😀"))));
saved = "old";
"""
STRING_TEMPLATE_OUTPUT = ('Привет, мир!\nдва/один/два\n10/10\n%1/%%2\n[]\n'
                          'Да/1\u00a0234,5\n😀\nСтрока\n[😀]\n')
STRING_TEMPLATE_FAILURES = (
    ('StrTemplate("%0")', 'недопустимый формат маркера подстановки'),
    ('СтрШаблон("%1", 1, 2)', 'очень много параметров'),
    ('StrTemplate("%11", 1)', 'недопустимый формат маркера подстановки'),
    ('СтрШаблон("%(1", 1)', 'недопустимый формат маркера подстановки'),
)
for _expression, _message in STRING_TEMPLATE_FAILURES:
    STRING_TEMPLATE_PROGRAM += (f'Try saved = {_expression}; Except\n'
                               f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                               'EndTry;\nMessage(saved);\n')
    STRING_TEMPLATE_OUTPUT += 'Да\nold\n'
STRING_TEMPLATE_PROGRAM += 'Message(StrTemplate("%1", "new"));\n'
STRING_TEMPLATE_OUTPUT += 'new\n'


STRING_BOUNDARY_PROGRAM = """
Message(ValueToStringInternal(сТрНаЧиНаЕтСяС("Абв", "Аб")));
Message(ValueToStringInternal(sTrStArTsWiTh("Абв", "аб")));
Message(ValueToStringInternal(СтрЗаканчиваетсяНа("Абв", "бв")));
Message(ValueToStringInternal(sTrEnDsWiTh("Абв", "БВ")));
Message(ValueToStringInternal(StrStartsWith("", "a")));
Message(ValueToStringInternal(StrEndsWith("a", "aa")));
Message(ValueToStringInternal(StrStartsWith("😀X", Char(55357))));
Message(ValueToStringInternal(StrEndsWith("X😀", Char(56832))));
Message(ValueToStringInternal(StrStartsWith(Char(0) + "x", Char(0))));
Message(ValueToStringInternal(StrEndsWith("x" + Char(0), Char(0))));
Message(TypeOf(StrStartsWith("a", "a")));
Message(ValueFromStringInternal(ValueToStringInternal(StrEndsWith("abc", "bc"))));
saved = True;
"""
STRING_BOUNDARY_OUTPUT = ('{"B",1}\n{"B",0}\n{"B",1}\n{"B",0}\n{"B",0}\n{"B",0}\n'
                          '{"B",1}\n{"B",1}\n{"B",1}\n{"B",1}\nБулево\nДа\n')
STRING_BOUNDARY_FAILURES = tuple(
    (f'{name}({source}, "")', 'строка поиска не должна быть пустой')
    for name in ('StrStartsWith', 'СтрНачинаетсяС', 'StrEndsWith', 'СтрЗаканчиваетсяНа')
    for source in ('"abc"', '""'))
for _expression, _message in STRING_BOUNDARY_FAILURES:
    STRING_BOUNDARY_PROGRAM += (f'Try saved = {_expression}; Except\n'
                               f'Message(Find(ErrorDescription(), "{_message}") > 0);\n'
                               'EndTry;\nMessage(saved);\n')
    STRING_BOUNDARY_OUTPUT += 'Да\nДа\n'
STRING_BOUNDARY_PROGRAM += 'Message(StrEndsWith("recovered", "covered"));\n'
STRING_BOUNDARY_OUTPUT += 'Да\n'


# Lexical String/Boolean XML conversion; no document parsing is involved.
STRING_PARITY_PROGRAM += '''
Message(XMLСтрока(True)); Message(XMLString(False));
Message(XMLString("Я😀<&amp;"));
Message(XMLValue(Type("String"), " <x>&amp;</x> "));
Message(XMLЗначение(Тип("Булево"), "1"));
Message(XMLValue(Type("Boolean"), "0"));
Message(XMLValue(Type("Boolean"), "TRUE"));
Message(ValueToStringInternal(XMLValue(TypeOf(True), "false")));
Message(ValueFromStringInternal(ValueToStringInternal(XMLString(True))));
xmlSaved = "old";
Try xmlSaved = XMLValue(Type("Boolean"), " true "); Except Message("xml-caught"); EndTry;
Message(xmlSaved); Message(XMLValue(Type("Boolean"), XMLString(True)));
'''
STRING_PARITY_OUTPUT += 'true\nfalse\nЯ😀<&amp;\n <x>&amp;</x> \nДа\nНет\nДа\n{"B",0}\ntrue\nxml-caught\nold\nДа\n'


# Native-backed secondary-strength comparison, including recovery on strict types.
STRING_PARITY_PROGRAM += '''
Message(СтрСравнить("ЁЖ", "ёж")); Message(StrCompare("ß", "SS"));
Message(StrCompare("İ", "i")); Message(StrCompare("é", "é"));
Message(StrCompare("a-b", "ab")); Message(StrCompare("a", "а"));
Message(ValueFromStringInternal(ValueToStringInternal(StrCompare("b", "a"))));
compareSaved = "old";
Try compareSaved = StrCompare("a", 1); Except Message("compare-caught"); EndTry;
Message(compareSaved); Message(StrCompare("A", "a"));
'''
STRING_PARITY_OUTPUT += '0\n1\n1\n0\n-1\n-1\n1\ncompare-caught\nold\n0\n'


STRING_PARITY_PROGRAM += r'''
fillTarget = New Structure("Имя,Оставить", "old", 9);
fillSource = New Structure("иМя,Лишнее", "Я😀", 42);
ЗаполнитьЗначенияСвойств(fillTarget, New FixedStructure(fillSource));
Message(fillTarget.Имя); Message(fillTarget.Оставить); Message(fillTarget.Count());
Message(fillTarget.Property("Лишнее"));
fillCopy = ValueFromStringInternal(ValueToStringInternal(fillTarget));
fillSource.Имя = Undefined; FillPropertyValues(fillTarget, fillSource);
Message(fillTarget.Имя = Undefined); Message(fillCopy.Имя);
Try FillPropertyValues(fillTarget, 1); Except Message("fill-caught"); EndTry;
FillPropertyValues(fillTarget, fillCopy); Message(fillTarget.Имя);
'''
STRING_PARITY_OUTPUT += 'Я😀\n9\n2\nНет\nДа\nЯ😀\nfill-caught\nЯ😀\n'


STRING_PARITY_PROGRAM += r'''
executeValue = "old";
Выполнить("executeValue = ""Я😀""; localOnly = 7;");
Message(executeValue);
Try Execute("executeValue = ""bad""; executeValue = ;"); Except Message("execute-caught"); EndTry;
Message(executeValue);
Try Eval("localOnly"); Except Message("execute-local-gone"); EndTry;
Execute(Undefined); Execute("executeValue = ""ok"";"); Message(executeValue);
fillTarget = New Structure("Имя,Оставить", "old", 5);
fillSource = New Structure("имя,Оставить", "Я", 9);
FillPropertyValues(fillTarget, fillSource, "Имя"); Message(fillTarget.Имя); Message(fillTarget.Оставить);
FillPropertyValues(fillTarget, fillSource, , "Имя"); Message(fillTarget.Оставить);
FillPropertyValues(New FixedStructure(fillTarget), fillSource);
'''
STRING_PARITY_OUTPUT += 'Я😀\nexecute-caught\nЯ😀\nexecute-local-gone\nok\nЯ\n5\n9\n'


STRING_PARITY_PROGRAM += r'''
constructorArgs = New("Array"); constructorArgs.Add("Имя"); constructorArgs.Add("Я😀");
dynamicValue = Новый(Тип("Структура"), constructorArgs); Message(dynamicValue.Имя);
fixedArgs = New Array; fixedArgs.Add(dynamicValue);
dynamicCopy = ValueFromStringInternal(ValueToStringInternal(New("FixedStructure", fixedArgs)));
Message(dynamicCopy.Имя); Message(TypeOf(dynamicCopy) = Type("FixedStructure"));
Message(New("Array", False).Count());
Try dynamicValue = New("Missing"); Except Message("new-caught"); EndTry;
Message(dynamicValue.Имя); Message(Eval("New(""Array"").Count()"));
'''
STRING_PARITY_OUTPUT += 'Я😀\nЯ😀\nДа\n0\nnew-caught\nЯ😀\n0\n'


STRING_PARITY_PROGRAM += r'''
Procedure ChangeReference(slot) slot = "Я😀"; EndProcedure
Procedure ObserveReference(slot, Val owner)
    slot = 11; Message(owner[0]); owner[0] = 12; Message(slot);
EndProcedure
referenceArray = New Array(1); referenceArray[0] = 10;
ObserveReference(referenceArray[0], referenceArray);
ChangeReference((referenceArray[0])); Message(referenceArray[0]);
referenceHolder = New Structure("Value", 10);
ChangeReference(referenceHolder.Value); Message(referenceHolder.Value);
referenceMap = New Map; ChangeReference(referenceMap["missing"]); Message(referenceMap["missing"]);
referenceFixed = New FixedArray(referenceArray);
Try ChangeReference(referenceFixed[0]); Except Message("reference-readonly"); EndTry;
Message(referenceFixed[0]);
referenceHolder.Property("Value", referenceArray[0]); Message(referenceArray[0]);
Execute("ChangeReference(referenceArray[0]);"); Message(Eval("referenceArray[0]"));
'''
STRING_PARITY_OUTPUT += '11\n12\nЯ😀\nЯ😀\nЯ😀\nreference-readonly\nЯ😀\nЯ😀\nЯ😀\n'


# Documented bit operations; these explicit expectations are not native goldens.
STRING_PARITY_PROGRAM += '''
Message(ПобитовоеИ(10, 12)); Message(BitwiseOr(10, 12));
Message(BitwiseXor(10, 12)); Message(BitwiseNot(0) = 4294967295);
Message(ПобитовоеИНе(10, 12)); Message(CheckBit(2147483648, 31));
Message(ПроверитьПоБитовойМаске(26, 24));
Message(SetBit(0, 31, True) = 2147483648);
Message(SetBit(4294967295, 31, False) = 2147483647);
bitSaved = 42;
Try bitSaved = BitwiseAnd(1.5, 2); Except Message("bits-caught"); EndTry;
Message(bitSaved); Message(Eval("BitwiseOr(1, 2)"));
'''
STRING_PARITY_OUTPUT += '8\n14\n6\nДа\n2\nДа\nДа\nДа\nДа\nbits-caught\n42\n3\n'


# Documented unsigned right shift, independent of native saved outputs.
STRING_PARITY_PROGRAM += '''
Message(ПобитовыйСдвигВправо(4294967295, 31));
Message(BitwiseShiftRight(2147483648, 1) = 1073741824);
shiftSaved = 17;
Try shiftSaved = BitwiseShiftRight(1, 32); Except Message("shift-caught"); EndTry;
Message(shiftSaved); Message(Eval("BitwiseShiftRight(26, 3)"));
'''
STRING_PARITY_OUTPUT += '1\nДа\nshift-caught\n17\n3\n'


# Native controls reject empty/above-bound deletion and preserve state.
STRING_PARITY_PROGRAM += '''
deleteArray = New Array;
Try deleteArray.Удалить(0); Except Message("delete-empty-caught"); EndTry;
deleteArray.Add("Я😀");
Try deleteArray.Delete(1); Except Message("delete-bound-caught"); EndTry;
Try deleteArray.Delete(Number("1e1000000")); Except Message("delete-huge-caught"); EndTry;
Message(deleteArray[0]); Message(deleteArray.Count());
Try deleteArray.Delete(-1); Except Message("delete-caught"); EndTry;
deleteArray.Delete(0); Message(deleteArray.Count());
deleteArray.Add("recovered"); Message(deleteArray[0]);
'''
STRING_PARITY_OUTPUT += 'delete-empty-caught\ndelete-bound-caught\ndelete-huge-caught\nЯ😀\n1\ndelete-caught\n0\nrecovered\n'


# Owner PR52 numeric grammar, exact uint128, wrapping left shift and recovery.
STRING_PARITY_PROGRAM += '''
radixN = NumberFromHexString("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF");
Message(ValueToStringInternal(radixN));
Message(ЧислоИзДвоичнойСтроки("0b0011001"));
Message(BitwiseShiftLeft(4294967295, 1) = 4294967294);
Message(ПобитовыйСдвигВлево(2, 31));
radixSaved = 17;
Try radixSaved = NumberFromBinaryString("0B1"); Except Message("radix-caught"); EndTry;
Message(radixSaved); Message(ЧислоИзШестнадцатеричнойСтроки("0x1a"));
Message(ValueFromStringInternal(ValueToStringInternal(radixN)) = radixN);
Try BitwiseShiftLeft(1, 32); Except Message("left-caught"); EndTry;
Message(BitwiseShiftLeft(1, 31) = 2147483648);
'''
STRING_PARITY_OUTPUT += ('{"N",340282366920938463463374607431768211455}\n'
                         '25\nДа\n0\nradix-caught\n17\n26\nДа\nleft-caught\nДа\n')



# Native PR53: optional search, enum/namespace codec and error recovery.
STRING_PARITY_PROGRAM += '''
Message(СтрНайти("Я😀Я😀", "😀", НаправлениеПоиска.СКонца));
Message(StrFind("abcabcabc", "bc", SearchDirection.FromBegin, 3, 2));
Message(StrFind("aaaa", "aa", SearchDirection.FromEnd, , 2));
Message(StrFind("abcabc", "bc", , 3));
Message(ValueToStringInternal(SearchDirection.FromEnd));
Message(ValueFromStringInternal(ValueToStringInternal(SearchDirection.FromBegin)) = SearchDirection.FromBegin);
Message(ValueToStringInternal(ValueFromStringInternal(ValueToStringInternal(SearchDirection))));
Try Type("EnumSearchDirection"); Except Message("search-type-caught"); EndTry;
For Each direction In SearchDirection Do Message(direction); EndDo;
searchSaved = 7;
Try searchSaved = StrFind("abc", "b", SearchDirection.FromEnd, 4); Except Message("search-range-caught"); EndTry;
Message(searchSaved); Message(StrFind("abcabc", "b", SearchDirection.FromEnd, , 2));
Message(StrFind("abc", "", SearchDirection.FromEnd, 3, 1));
Message(StrFind("abc", "", SearchDirection.FromBegin, 3, 2));
Message(StrFind("", "", SearchDirection.FromEnd, 1, 2));
'''
STRING_PARITY_OUTPUT += ('5\n8\n1\n5\n'
                         '{"#",bee8fa9f-59d0-4e71-9f6e-599d83cb1960,1}\n'
                         'Да\n{"U"}\nsearch-type-caught\nС начала\nС конца\n'
                         'search-range-caught\n7\n2\n1\n3\n1\n')


def check_string_parity(executable: str, *, directory: Path, env: dict) -> None:
    """Native-backed strings and documented string/XML conversions across inputs."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'ВхожденияШаблона.bsl'
    source.write_text(STRING_PARITY_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, STRING_PARITY_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], STRING_PARITY_PROGRAM),
              ([], STRING_PARITY_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, STRING_PARITY_OUTPUT, ''):
            raise AssertionError(f'Failed native string parity {arguments!r}: {result!r}')
    print('Binary string checks passed: native parity, extended StrFind/SearchDirection, lexical XML conversion, '
          'BOM file, command flags, stdin and console recovery')


def check_array_gap(executable: str, *, directory: Path, env: dict) -> None:
    """Array gap insertion across all binary input modes."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'ПромежуткиМассива.bsl'
    source.write_text(ARRAY_GAP_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, ARRAY_GAP_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], ARRAY_GAP_PROGRAM),
              ([], ARRAY_GAP_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, ARRAY_GAP_OUTPUT, ''):
            raise AssertionError(f'Failed array gap insertion {arguments!r}: {result!r}')
    code = 'a = New Array; a.Add("old");\na.Insert(100000000000000000000);\n'
    source.write_text(code, encoding='utf-8-sig')
    cases = [([flag, code], None, '', '<команда>:2:') for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None, '', str(source) + ':2:'),
              (['-'], code, '', '<stdin>:2:'),
              ([], code + 'a.Count()\na[0]\n/exit\n', '1\nold\n', '<консоль>:1:')]
    for arguments, stdin, stdout, location in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                or 'предел роста массива Yadinassi' not in result.stderr or 'Traceback' in result.stderr):
            raise AssertionError(f'Failed array gap diagnostic {arguments!r}: {result!r}')
    print('Binary array constructors and gap insertion passed: dimensions, aliases, fixed snapshot, serialization, '
          'BOM file, command flags, stdin and console recovery')


def check_array_defaults(executable: str, *, directory: Path, env: dict) -> None:
    """Optional array values across all binary input modes."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'ПустыеЭлементы.bsl'
    source.write_text(ARRAY_DEFAULT_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, ARRAY_DEFAULT_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], ARRAY_DEFAULT_PROGRAM),
              ([], ARRAY_DEFAULT_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, ARRAY_DEFAULT_OUTPUT, ''):
            raise AssertionError(f'Failed array defaults {arguments!r}: {result!r}')
    print('Binary array defaults passed: aliases, mutation, fixed snapshot, serialization, '
          'BOM file, command flags, stdin and console recovery')


def check_value_filled(executable: str, *, directory: Path, env: dict) -> None:
    """Filled-value checks, failures and recovery in the binary."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'Заполненность.bsl'
    source.write_text(VALUE_FILLED_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, VALUE_FILLED_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], VALUE_FILLED_PROGRAM),
              ([], VALUE_FILLED_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, VALUE_FILLED_OUTPUT, ''):
            raise AssertionError(f'Failed value filled {arguments!r}: {result!r}')
    for expression, message in VALUE_FILLED_FAILURES:
        code = f'saved = "old";\nsaved = {expression};\n'
        source.write_text(code, encoding='utf-8-sig')
        cases = [([flag, code], None, '', '<команда>:2:')
                 for flag in ('-c', '-с', '--command')]
        cases += [([str(source)], None, '', str(source) + ':2:'),
                  (['-'], code, '', '<stdin>:2:'),
                  ([], code + 'saved\nValueIsFilled(False)\n/exit\n',
                   'old\nДа\n', '<консоль>:1:')]
        for arguments, stdin, stdout, location in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed value filled recovery {arguments!r}: {result!r}')
    print('Binary value filled passed: aliases, scalars, collections, '
          'serialization, BOM file, command flags, stdin and console recovery')


def check_string_lines(executable: str, *, directory: Path, env: dict) -> None:
    """Multiline string operations, failures and recovery in the binary."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'МногострочныйТекст.bsl'
    source.write_text(STRING_LINES_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, STRING_LINES_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], STRING_LINES_PROGRAM),
              ([], STRING_LINES_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, STRING_LINES_OUTPUT, ''):
            raise AssertionError(f'Failed string lines {arguments!r}: {result!r}')
    for expression, message in STRING_LINES_FAILURES:
        code = f'saved = "old";\nsaved = {expression};\n'
        source.write_text(code, encoding='utf-8-sig')
        cases = [([flag, code], None, '', '<команда>:2:')
                 for flag in ('-c', '-с', '--command')]
        cases += [([str(source)], None, '', str(source) + ':2:'),
                  (['-'], code, '', '<stdin>:2:'),
                  ([], code + 'saved\nStrGetLine("new", 1)\n/exit\n',
                   'old\nnew\n', '<консоль>:1:')]
        for arguments, stdin, stdout, location in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed string line recovery {arguments!r}: {result!r}')
    print('Binary string lines passed: aliases, CR/LF, indices, UTF-16, '
          'serialization, BOM file, command flags, stdin and console recovery')


def check_string_template(executable: str, *, directory: Path, env: dict) -> None:
    """Numbered string templates, failures and recovery in the binary."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'ШаблонСтроки.bsl'
    source.write_text(STRING_TEMPLATE_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, STRING_TEMPLATE_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], STRING_TEMPLATE_PROGRAM),
              ([], STRING_TEMPLATE_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, STRING_TEMPLATE_OUTPUT, ''):
            raise AssertionError(f'Failed string templates {arguments!r}: {result!r}')
    for expression, message in STRING_TEMPLATE_FAILURES:
        code = f'saved = "old";\nsaved = {expression};\n'
        source.write_text(code, encoding='utf-8-sig')
        cases = [([flag, code], None, '', '<команда>:2:')
                 for flag in ('-c', '-с', '--command')]
        cases += [([str(source)], None, '', str(source) + ':2:'),
                  (['-'], code, '', '<stdin>:2:'),
                  ([], code + 'saved\nStrTemplate("%1", "new")\n/exit\n',
                   'old\nnew\n', '<консоль>:1:')]
        for arguments, stdin, stdout, location in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed string template recovery {arguments!r}: {result!r}')
    print('Binary string templates passed: aliases, markers, arity, UTF-16, '
          'serialization, BOM file, command flags, stdin and console recovery')


def check_string_boundaries(executable: str, *, directory: Path, env: dict) -> None:
    """Exact string boundaries, empty-search failures and recovery in the binary."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'ГраницыСтрок.bsl'
    source.write_text(STRING_BOUNDARY_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, STRING_BOUNDARY_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], STRING_BOUNDARY_PROGRAM),
              ([], STRING_BOUNDARY_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, STRING_BOUNDARY_OUTPUT, ''):
            raise AssertionError(f'Failed string boundaries {arguments!r}: {result!r}')
    for expression, message in STRING_BOUNDARY_FAILURES:
        code = f'saved = True;\nsaved = {expression};\n'
        source.write_text(code, encoding='utf-8-sig')
        cases = [([flag, code], None, '', '<команда>:2:')
                 for flag in ('-c', '-с', '--command')]
        cases += [([str(source)], None, '', str(source) + ':2:'),
                  (['-'], code, '', '<stdin>:2:'),
                  ([], code + 'saved\nStrStartsWith("A", "A")\n/exit\n',
                   'Да\nДа\n', '<консоль>:1:')]
        for arguments, stdin, stdout, location in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed string boundary recovery {arguments!r}: {result!r}')
    print('Binary string boundaries passed: aliases, exact case, empty-search errors, UTF-16, '
          'serialization, BOM file, command flags, stdin and console recovery')


def check_characters(executable: str, *, directory: Path, env: dict) -> None:
    """UTF-16 character construction, lookup and serialization in the binary."""
    directory = directory.resolve()
    directory.mkdir()
    source = directory / 'Символы.bsl'
    source.write_text(CHARACTER_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, CHARACTER_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], CHARACTER_PROGRAM),
              ([], CHARACTER_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, CHARACTER_OUTPUT, ''):
            raise AssertionError(f'Failed character functions {arguments!r}: {result!r}')
    for expression, message in CHARACTER_FAILURES:
        code = f'saved = Символ(65);\nsaved = {expression};\n'
        source.write_text(code, encoding='utf-8-sig')
        cases = [([flag, code], None, '', '<команда>:2:')
                 for flag in ('-c', '-с', '--command')]
        cases += [([str(source)], None, '', str(source) + ':2:'),
                  (['-'], code, '', '<stdin>:2:'),
                  ([], code + 'saved\nКодСимвола(saved)\n/exit\n',
                   'A\n65\n', '<консоль>:1:')]
        for arguments, stdin, stdout, location in cases:
            result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                    encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
            if (result.returncode != 1 or result.stdout != stdout or location not in result.stderr
                    or message not in result.stderr or 'Traceback' in result.stderr):
                raise AssertionError(f'Failed character recovery {arguments!r}: {result!r}')
    print('Binary character functions passed: aliases, coercion, UTF-16 units, NUL/surrogate '
          'serialization, ranges, BOM file, command flags, stdin and console recovery')


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


GOTO_PROGRAM = r'''
#Region JumpProgram
Function Count(Val n)
    result = 0;
    ~again:
    result = result + 1;
    If result < n Then Goto ~AGAIN; EndIf;
    Return result;
EndFunction
Перейти ~Начало;
Message("skipped");
~начало:
Message(Count(3));
For i = 1 To 5 Do
    While True Do
        Try
            Goto ~outside;
        Except
            Message("caught-jump");
        EndTry;
    EndDo;
EndDo;
~outside:
Message(i);
Try
    Raise "expected";
Except
    Goto ~done;
EndTry;
~done:
Message(ErrorDescription() = "");
Message("goto-complete");
#EndRegion
'''
GOTO_OUTPUT = '3\n1\nДа\ngoto-complete\n'
GOTO_ERRORS = [
    ('Message("early"); Goto ~missing;', 'Метка не определена'),
    ('Message("early"); ~a: ~A:', 'Повторное объявление метки'),
    ('Goto ~inside; If False Then ~inside: EndIf;',
     'Переход внутрь другого блока пока не поддерживается'),
]


def check_goto(executable: str, *, directory: Path, env: dict) -> None:
    directory.mkdir()
    source = directory / 'Переходы.bsl'
    source.write_text(GOTO_PROGRAM, encoding='utf-8-sig')
    cases = [([flag, GOTO_PROGRAM], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], GOTO_PROGRAM),
              ([], GOTO_PROGRAM + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, GOTO_OUTPUT, ''):
            raise AssertionError(f'Failed Goto {arguments!r}: {result!r}')
    for program, message in GOTO_ERRORS:
        result = subprocess.run([executable, '-c', program], capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode != 1 or result.stdout or message not in result.stderr
                or '<команда>:1:' not in result.stderr or 'Traceback' in result.stderr):
            raise AssertionError(f'Failed Goto diagnostic: {result!r}')
    print('Binary Goto passed: aliases, loops, routines, try exits, CLI inputs and static diagnostics')


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
    untouched owner-provided sample fixture, including its arithmetic precision.
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



def check_clocks(executable: str, *, directory: Path, env: dict) -> None:
    """Check live wall clocks without saving nondeterministic native goldens."""
    directory.mkdir()
    code = '\n'.join([
        'localClock = ТекущаяДата(); utcClock = CurrentUniversalDate();',
        'milliseconds = ТекущаяУниверсальнаяДатаВМиллисекундах();',
        'Message(TypeOf(localClock) = Type("Date"));',
        'Message(TypeOf(utcClock) = Type("Дата"));',
        'Message(TypeOf(milliseconds) = Type("Число"));',
        'Message(TypeOf(cUrReNtDaTe()) = Type("Date"));',
        'Message(TypeOf(тЕкУщАяУнИвЕрСаЛьНаЯдАтА()) = Type("Date"));',
        'Message(TypeOf(CurrentUniversalDateInMilliseconds()) = Type("Number"));',
        'Message(ValueFromStringInternal(ValueToStringInternal(localClock)) = localClock);',
        'Message(ValueFromStringInternal(ValueToStringInternal(utcClock)) = utcClock);',
        'Message(ValueFromStringInternal(ValueToStringInternal(milliseconds)) = milliseconds);',
        'Message(Int(milliseconds) = milliseconds);',
        'snapshot = New Structure("Local,UTC,MS", localClock, utcClock, milliseconds);',
        'restored = ValueFromStringInternal(ValueToStringInternal(snapshot));',
        'Message(restored.Local = localClock And restored.UTC = utcClock And restored.MS = milliseconds);',
        'saved = utcClock;',
        'Try saved = CurrentDate(1); Except Message("clock-arity-caught"); EndTry;',
        'Message(saved = utcClock);',
        'Message(ValueToStringInternal(utcClock));',
        'Message(ValueToStringInternal(milliseconds));',
    ]) + '\n'
    source = directory / 'СистемныеЧасы.bsl'
    source.write_text(code, encoding='utf-8-sig')
    cases = [([flag, code], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], code), ([], code + '/exit\n')]
    for arguments, stdin in cases:
        before = time.time_ns()
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        after = time.time_ns()
        lines = result.stdout.splitlines()
        if (result.returncode != 0 or result.stderr or len(lines) != 15
                or lines[:13] != ['Да'] * 11 + ['clock-arity-caught', 'Да']):
            raise AssertionError(f'Failed wall clock checks {arguments!r}: {result!r}')
        utc = re.fullmatch(r'\{"D",([0-9]{14})\}', lines[13])
        ms = re.fullmatch(r'\{"N",([0-9]+)\}', lines[14])
        if utc is None or ms is None:
            raise AssertionError(f'Invalid clock codec records: {lines[-2:]!r}')
        # UTC milliseconds use year 1, not Unix time. No binary float conversion.
        epoch_ms = 62135596800000
        low, high = sorted((before, after))
        if not low // 1000000 + epoch_ms <= int(ms[1]) <= high // 1000000 + epoch_ms:
            raise AssertionError('Frozen millisecond clock is outside the invocation interval')
        actual = datetime.strptime(utc[1], '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
        lo_date = datetime.fromtimestamp(low // 1000000000, timezone.utc)
        hi_date = datetime.fromtimestamp(high // 1000000000, timezone.utc)
        if not lo_date <= actual <= hi_date:
            raise AssertionError('Frozen UTC Date is outside the invocation interval')
    module = directory / 'Часы.bsl'
    module.write_text('Function Snapshot() Export\n'
                      'Return New Structure("Local,UTC,MS", CurrentDate(), '
                      'ТекущаяУниверсальнаяДата(), CurrentUniversalDateInMilliseconds());\n'
                      'EndFunction\n', encoding='utf-8-sig')
    importer = directory / 'ИмпортЧасов.bsl'
    importer.write_text('// #Импорт Часы.bsl\nvalue = Часы.Snapshot();\n'
                        'Message(TypeOf(value.Local) = Type("Date"));\n'
                        'Message(TypeOf(value.UTC) = Type("Date"));\n'
                        'Message(TypeOf(value.MS) = Type("Number"));\n', encoding='utf-8-sig')
    for path in (importer, importer.relative_to(directory.parent)):
        result = subprocess.run([executable, str(path)], capture_output=True, encoding='utf-8',
                                cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, 'Да\n' * 3, ''):
            raise AssertionError(f'Failed imported clocks: {result!r}')
    print('Binary clocks passed: live UTC interval, year-1 milliseconds, aliases, codecs, '
          'BOM, imports, command flags, stdin, console, and error recovery')


def null_checkpoint_source(program: str) -> str:
    """Select the owner-confirmed Null helpers/body from the growing values suite."""
    body_start = '// Значение, тип и настоящий прямой/обратный кодек.'
    xml_helpers_start = '// Нативный checkpoint скалярного XML.'
    final = 'Сообщить("null.checkpoint.complete: [ok]");'
    if program.count(body_start) != 1 or program.count(final) != 1:
        raise AssertionError('Expected unique Null checkpoint body and completion marker')
    helpers, _, body = program.partition(body_start)
    if final not in body:
        raise AssertionError('Null completion marker must follow its body')
    # Later thematic helpers belong before the common executable body, but must
    # not participate in replaying the original native-confirmed observations.
    if helpers.count(xml_helpers_start) > 1:
        raise AssertionError('Expected at most one scalar XML helper boundary')
    helpers = helpers.partition(xml_helpers_start)[0]
    body = body.partition(final)[0]
    return helpers + body_start + body + final + '\n'


def null_checkpoint_output(output: str) -> str:
    """Keep the complete original native Null output when later themes are appended."""
    markers = list(re.finditer(r'^null\.checkpoint\.complete: \[ok\](?:\n|\Z)',
                              output, re.MULTILINE))
    if len(markers) != 1:
        raise AssertionError('Expected one native Null completion marker')
    return output[:markers[0].end()]


def check_null(executable: str, *, directory: Path, env: dict) -> None:
    """Replay owner Null output through each frozen input, then recovery/imports."""
    directory.mkdir()
    program = null_checkpoint_source(
        (ROOT / "integrational_tests/tests/values.bsl").read_text(encoding="utf-8-sig"))
    expected = null_checkpoint_output(
        (ROOT / "tests/fixtures/native_windows/values.out").read_text(encoding="utf-8-sig"))
    source = directory / 'СпециальныеЗначения.bsl'
    source.write_text(program, encoding='utf-8-sig')
    cases = [([flag, program], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], program), ([], program + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Failed native Null checkpoint {arguments!r}: {result!r}')
    module = directory / 'Особые.bsl'
    module.write_text('Function DefaultNull(value = Null) Export\nReturn value;\nEndFunction\n',
                      encoding='utf-8-sig')
    recovery = '\n'.join([
        '// #Импорт Особые.bsl',
        'saved = Особые.DefaultNull(); Message(ValueToStringInternal(saved));',
        'Try saved = Number(Null); Except Message("null-number-caught"); EndTry;',
        'Message(ValueToStringInternal(saved));',
        'Message(ValueToStringInternal(TypeOf(saved)));',
        'Message(ValueToStringInternal(False And Null));',
        'Message(ValueToStringInternal(True Or Null));',
        'a = New Array; a.Add(Undefined); a.Add(saved);',
        'fixed = New FixedArray(a);',
        'Message(ValueToStringInternal(fixed.Find(Null)));',
        'readback = ValueFromStringInternal(ValueToStringInternal(fixed));',
        'Message(ValueToStringInternal(readback[1]));',
    ]) + '\n'
    source.write_text(recovery, encoding='utf-8-sig')
    result = subprocess.run([executable, str(source)], capture_output=True,
                            encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
    wanted = ('{"L"}\nnull-number-caught\n{"L"}\n'
              '{"T",af40a278-63bc-478e-91a8-19e0d16b10b5}\n'
              '{"B",0}\n{"B",1}\n{"N",1}\n{"L"}\n')
    if (result.returncode, result.stdout, result.stderr) != (0, wanted, ''):
        raise AssertionError(f'Failed Null import/recovery: {result!r}')
    print('Binary Null passed: all 40 native observations, true inverse codec, BOM, '
          'command aliases, stdin, console, imported defaults and recovery')


def xml_checkpoint_labels(program: str) -> list[str]:
    """Read ordered packaging labels without inventing native XML results."""
    body_start = '// Скалярный XML: наблюдения без заранее заданных ответов.'
    final = 'Сообщить("xml.checkpoint.complete: [ok]");'
    if program.count(body_start) != 1 or program.count(final) != 1:
        raise AssertionError('Expected unique scalar XML body and completion marker')
    body = program.partition(body_start)[2]
    if final not in body:
        raise AssertionError('Scalar XML completion marker must follow its body')
    labels = re.findall(r'^НаблюдатьXML\("([a-z0-9.-]+)", ',
                        body.partition(final)[0], re.MULTILINE)
    if len(labels) != 62 or len(set(labels)) != 62:
        raise AssertionError('Expected 62 unique scalar XML observation labels')
    return ['xml.' + label for label in labels]


def validate_xml_checkpoint_output(output: str, expected_null: str, labels: list[str]) -> None:
    """Validate ordered observation frames while allowing multiline codec payloads."""
    expected_null = null_checkpoint_output(expected_null)
    if not output.startswith(expected_null):
        raise AssertionError('Scalar XML checkpoint changed the original native Null output')
    body = output[len(expected_null):]
    frames = list(re.finditer(r'^(xml\.[a-z0-9.-]+): \[', body, re.MULTILINE))
    if (len(set(labels)) != len(labels) or not frames or frames[0].start() != 0
            or [frame[1] for frame in frames] != labels + ['xml.checkpoint.complete']):
        raise AssertionError('Scalar XML observation frames are missing, duplicated or out of order')
    for frame, following in zip(frames, frames[1:]):
        # Do not inspect payload values: array/structure codecs contain newlines,
        # and payload correctness is checked separately against the owner output.
        if not body[frame.start():following.start()].endswith(']\n'):
            raise AssertionError(f'Unclosed scalar XML observation frame: {frame[1]}')
    if body[frames[-1].start():] != 'xml.checkpoint.complete: [ok]\n':
        raise AssertionError('Scalar XML checkpoint must end at its completion marker')



# Compact-source boundaries are review-guarded; the legacy Null/XML prefix
# stays immutable. Fresh owner output is required after source compaction.
VALUES_CONFIRMED_SHA256 = '8c6670294114773f6daabb847567390ab82bd2aba5105fe773b54482b065be44'
TYPES_HELPERS_SHA256 = '9ef8a920cd7f557a490ae8003a0460d61d5141602ea5316546f09faa29d4e5d4'
TYPES_BODY_SHA256 = 'a0f362ced62489c3b7e2b837ed6f9850258c2cbdca082d90ae50ad75c3f35bbf'
TYPES_HELPERS_START = '// Нативный checkpoint описаний типов.'
TYPES_BODY_START = '// Описания типов: наблюдения без заранее заданных ответов.'
TYPES_FINAL = 'types.checkpoint.complete: [ok]'


TYPES_ORIGINAL_SOURCE_SHA256 = '819d8b8e4cc68782692281b46446c9eca58552162a9cad762a7f967b5162dec6'
TYPES_SUPPLEMENT_HELPERS_SHA256 = '1765b1520cf6fc59c7380c8a767e28dc12759616f6440ab019153f5e5a92eb66'
TYPES_SUPPLEMENT_BODY_SHA256 = '21f310a6c5f85a7481b3666606685ab4099eec9ea6f6cf85bad9bb5e422fef25'
TYPES_SUPPLEMENT_HELPERS_START = '// Дополнение нативной проверки: вызов через переменную.'
TYPES_SUPPLEMENT_BODY_START = '// Дополнение описаний типов: вызов через переменную.'
TYPES_SUPPLEMENT_FINAL = 'types-extra.checkpoint.complete: [ok]'


def split_type_supplement(program: str) -> tuple[str, str]:
    """Split the reviewed main source and self-contained receiver supplement."""
    markers = (TYPES_SUPPLEMENT_HELPERS_START, TYPES_SUPPLEMENT_BODY_START)
    if not any(marker in program for marker in markers):
        return program, ''
    if any(program.count(marker) != 1 for marker in (*markers, TYPES_HELPERS_START)):
        raise AssertionError('Expected unique supplemental TypeDescription boundaries')
    prefix, rest = program.split(TYPES_SUPPLEMENT_HELPERS_START)
    helpers, rest = rest.split(TYPES_HELPERS_START)
    body_boundary = '\n\n' + TYPES_SUPPLEMENT_BODY_START
    if rest.count(body_boundary) != 1:
        raise AssertionError('Expected exact supplemental TypeDescription body separator')
    original_tail, body = rest.split(body_boundary)
    original = prefix + TYPES_HELPERS_START + original_tail
    helpers = TYPES_SUPPLEMENT_HELPERS_START + helpers
    body = body_boundary + body
    for text, expected in ((original, TYPES_ORIGINAL_SOURCE_SHA256),
                           (helpers, TYPES_SUPPLEMENT_HELPERS_SHA256),
                           (body, TYPES_SUPPLEMENT_BODY_SHA256)):
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != expected:
            raise AssertionError('TypeDescription supplement source changed; review boundaries and hashes')
    return original, helpers + body


def pending_types_checkpoint(program: str) -> tuple[str, list[str]]:
    """Historical XML source extraction for its focused tests, not a parity gate.

    Keep the legacy name for test_xml_checkpoint; frozen checks never strip types.
    """
    program, _ = split_type_supplement(program)
    null_body = '// Значение, тип и настоящий прямой/обратный кодек.'
    xml_final = 'Сообщить("xml.checkpoint.complete: [ok]");\n'
    for marker in (TYPES_HELPERS_START, TYPES_BODY_START, null_body, xml_final):
        if program.count(marker) != 1:
            raise AssertionError('Expected unique TypeDescription checkpoint boundaries')
    prefix, helpers_and_rest = program.split(TYPES_HELPERS_START)
    helpers, body = helpers_and_rest.split(null_body)
    original_body, types_body = body.split(xml_final)
    confirmed = prefix + null_body + original_body + xml_final
    if types_body.lstrip()[:len(TYPES_BODY_START)] != TYPES_BODY_START:
        raise AssertionError('Historical types body must immediately follow native XML')
    for text, expected in ((confirmed, VALUES_CONFIRMED_SHA256),
                           (TYPES_HELPERS_START + helpers, TYPES_HELPERS_SHA256),
                           (types_body, TYPES_BODY_SHA256)):
        if hashlib.sha256(text.encode('utf-8')).hexdigest() != expected:
            raise AssertionError('Checkpoint source changed; review historical source boundaries and hashes')
    labels = re.findall(r'^НаблюдатьТипы\("([a-z0-9.-]+)", ', types_body, re.MULTILINE)
    if not labels or len(set(labels)) != len(labels):
        raise AssertionError('Expected unique historical TypeDescription observations')
    if not types_body.rstrip().endswith('Сообщить("' + TYPES_FINAL + '");'):
        raise AssertionError('Missing historical TypeDescription completion marker')
    return confirmed, ['types.' + label for label in labels]


def check_saved_native_outputs(executable: str, *, directory: Path, env: dict) -> None:
    """Full frozen parity with every committed owner output, not selected lines."""
    directory.mkdir()
    environment = dict(env, YADINASSI_TIMEZONE='Europe/Warsaw', PYTHONTZPATH='', TZ='UTC0')
    for name in ('functions', 'strings', 'collections', 'numbers', 'dates', 'values'):
        output = ROOT / 'tests/fixtures/native_windows' / (name + '.out')
        if output.with_suffix('.err').exists():
            raise AssertionError(f'Native error file exists: {name}')
        expected = output.read_bytes().decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
        script = ROOT / 'integrational_tests/tests' / (name + '.bsl')
        if name == 'collections':
            replay = directory / 'collections-historical.bsl'
            replay.write_bytes(historical_collections_source(script.read_bytes(), output.read_bytes()))
            script = replay
        if name == 'values':
            replay = directory / 'values-historical.bsl'
            replay.write_bytes(historical_values_source(script.read_bytes(), output.read_bytes()))
            script = replay
        result = subprocess.run([executable, str(script)],
                                cwd=directory, env=environment, capture_output=True,
                                encoding='utf-8', timeout=30)
        if result.returncode or result.stderr or result.stdout != expected:
            raise AssertionError(f'Frozen native output mismatch: {name}: {result!r}')
    print('Binary native parity passed: all six complete owner outputs')


def check_timezone_configuration(executable: str, *, directory: Path, env: dict) -> None:
    """Standalone timezone configuration tests, not extra native observations."""
    cases = [
        ('Europe/Warsaw', '2024-07-01T12:34:56Z', '20240701143456'),
        ('Europe/Warsaw', '2024-03-31T00:59:59Z', '20240331015959'),
        ('Europe/Warsaw', '2024-03-31T01:00:00Z', '20240331030000'),
        ('Europe/Warsaw', '2024-10-27T00:30:00Z', '20241027023000'),
        ('Europe/Warsaw', '2024-10-27T01:30:00Z', '20241027023000'),
        ('Asia/Kathmandu', '2024-02-29T12:34:56Z', '20240229181956'),
        ('UTC', '2024-02-29T12:34:56Z', '20240229123456'),
    ]
    for zone, lexical, expected in cases:
        code = f'Message(ValueToStringInternal(XMLValue(Type("Date"), "{lexical}")));'
        result = subprocess.run([executable, '-c', code], cwd=directory,
                                env=dict(env, YADINASSI_TIMEZONE=zone),
                                capture_output=True, encoding='utf-8', timeout=30)
        if result.returncode or result.stderr or result.stdout != '{"D",' + expected + '}\n':
            raise AssertionError(f'Frozen timezone configuration failed: {zone}: {result!r}')
    # Explicit UTC also applies to the local wall clock, but not UTC clocks.
    code = ('delta = CurrentDate() - CurrentUniversalDate(); '
            'Message(delta >= -2 And delta <= 2);')
    result = subprocess.run([executable, '-c', code], cwd=directory,
                            env=dict(env, YADINASSI_TIMEZONE='UTC'),
                            capture_output=True, encoding='utf-8', timeout=30)
    if result.returncode or result.stderr or result.stdout != 'Да\n':
        raise AssertionError(f'Frozen configured local clock failed: {result!r}')
    code = ('Try value = XMLValue(Type("Date"), "2024-02-29T12:34:56Z"); '
            'Except Message("invalid-zone"); EndTry; '
            'Message(XMLString(XMLValue(Type("Date"), "2024-02-29T12:34:56")));')
    result = subprocess.run([executable, '-c', code], cwd=directory,
                            env=dict(env, YADINASSI_TIMEZONE='../UTC'),
                            capture_output=True, encoding='utf-8', timeout=30)
    if (result.returncode or result.stderr
            or result.stdout != 'invalid-zone\n2024-02-29T12:34:56\n'):
        raise AssertionError(f'Frozen invalid timezone/recovery failed: {result!r}')
    print('Binary timezone configuration passed: pinned data, seasonal DST, folds, '
          'nonwhole-hour zone, UTC clock, invalid configuration and naive-date independence')


def check_xml_checkpoint(executable: str, *, directory: Path, env: dict) -> None:
    """Full native values via file/stdin/console; bounded native command sample."""
    directory.mkdir()
    program = (ROOT / 'integrational_tests/tests/values.bsl').read_text(encoding='utf-8-sig')
    output = ROOT / 'tests/fixtures/native_windows/values.out'
    program = historical_values_source(program.encode('utf-8'), output.read_bytes()).decode('utf-8')
    _, command_program = split_type_supplement(program)
    if output.with_suffix('.err').exists():
        raise AssertionError('Native error file exists: values')
    expected = output.read_bytes().decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    env = dict(env, YADINASSI_TIMEZONE='Europe/Warsaw', PYTHONTZPATH='', TZ='UTC0')
    source = directory / 'НативныеЗначения.bsl'
    source.write_text(program, encoding='utf-8-sig')
    for arguments, stdin in [([str(source)], None), (['-'], program),
                             ([], program + '/exit\n')]:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Full native values checkpoint mismatch {arguments[0:1]!r}: {result!r}')
    print('Binary native values parity passed: complete committed owner output, including main '
          'and 23 supplemental type observations; BOM file, stdin and console')
    # Windows CreateProcess limits argv to 32767 UTF-16 code units. The full
    # source exceeds that bound; exercise command aliases with the self-contained
    # native supplement on every platform instead, never skip native file parity.
    marker = TYPES_FINAL + '\n'
    if not command_program or expected.count(marker) != 1:
        raise AssertionError('Expected native type supplement source and owner-output boundary')
    command_expected = expected.split(marker, 1)[1]
    for flag in ('-c', '-с', '--command'):
        arguments = [executable, flag, command_program]
        if len(subprocess.list2cmdline(arguments).encode('utf-16-le')) // 2 + 1 >= 32767:
            raise AssertionError('Native command sample exceeds Windows UTF-16 argv limit')
        result = subprocess.run(arguments, capture_output=True, encoding='utf-8',
                                cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, command_expected, ''):
            raise AssertionError(f'Native type command sample mismatch {flag}: {result!r}')
    print('Binary command aliases passed: exact 23-probe owner TypeDescription/qualifier/codec '
          'supplement; bounded sample for Windows argv limit, not full values command coverage')
    check_timezone_configuration(executable, directory=directory, env=env)


TABLE_COMMAND_LABELS = (
    'codec.table', 'codec.column', 'read.column-property', 'mutate.column-add',
    'mutate.copy-selected', 'typed.fixed-string', 'links.nested-sharing',
    'links.codec-object-graph',
)


def table_command_checkpoint(program: str, expected: str) -> tuple[str, str]:
    """Select unchanged native observations for the Windows command-size budget."""
    start = '// Нативный checkpoint ТаблицыЗначений: без придуманных ответов.'
    end = '// Конец помощников checkpoint ТаблицыЗначений.'
    if program.count(start) != 1 or program.count(end) != 1:
        raise AssertionError('Expected immutable table helper boundaries')
    helpers = start + program.split(start, 1)[1].split(end, 1)[0]
    lines = []
    records = []
    boundaries = list(re.finditer(r'^(table\.[a-z0-9.-]+): \[', expected, re.MULTILINE))
    for label in TABLE_COMMAND_LABELS:
        source_lines = [line for line in program.splitlines()
                        if line.startswith('НаблюдатьТаблицы("' + label + '", ')]
        matches = [index for index, match in enumerate(boundaries)
                   if match.group(1) == 'table.' + label]
        if len(source_lines) != 1 or len(matches) != 1:
            raise AssertionError('Missing/duplicate bounded table observation: ' + label)
        lines.append(source_lines[0])
        index = matches[0]
        last = boundaries[index + 1].start() if index + 1 < len(boundaries) else len(expected)
        records.append(expected[boundaries[index].start():last])
    return helpers + '\n'.join(lines) + '\n', ''.join(records)


def check_table_checkpoint(executable: str, *, directory: Path, env: dict) -> None:
    """Every owner collections byte in full modes; bounded exact command sample."""
    directory.mkdir()
    source_path = ROOT / 'integrational_tests/tests/collections.bsl'
    output_path = ROOT / 'tests/fixtures/native_windows/collections.out'
    if output_path.with_suffix('.err').exists():
        raise AssertionError('Native error file exists: collections')
    program = source_path.read_text(encoding='utf-8-sig')
    expected = output_path.read_bytes().decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    if not expected.endswith('table.checkpoint.complete: [ok]\n'):
        raise AssertionError('Missing native table completion marker')
    program = historical_collections_source(source_path.read_bytes(), output_path.read_bytes()).decode('utf-8-sig')
    env = dict(env, YADINASSI_TIMEZONE='Europe/Warsaw', PYTHONTZPATH='', TZ='UTC0')
    source = directory / 'Таблицы с пробелами.bsl'
    source.write_text(program, encoding='utf-8-sig')
    for arguments, stdin in [([str(source)], None), (['-'], program), ([], program + '/exit\n')]:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Full native collections checkpoint mismatch {arguments[0:1]!r}: {result!r}')
    command_program, command_expected = table_command_checkpoint(program, expected)
    for flag in ('-c', '-с', '--command'):
        arguments = [executable, flag, command_program]
        if len(subprocess.list2cmdline(arguments).encode('utf-16-le')) // 2 + 1 >= 32767:
            raise AssertionError('Native table command sample exceeds Windows UTF-16 argv limit')
        result = subprocess.run(arguments, capture_output=True, encoding='utf-8',
                                cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, command_expected, ''):
            raise AssertionError(f'Native table command sample mismatch {flag}: {result!r}')
    print('Binary native collections parity passed: complete owner output including 142 table '
          'observations via BOM file/stdin/console; eight exact native observations via command aliases')


def check_fixed_offset_conversions(executable: str, *, directory: Path, env: dict) -> None:
    """Documented whole-second GMT subset, not owner-generated native output."""
    directory.mkdir()
    program = (
        'base = Date(2024, 2, 29, 23, 59, 59);\n'
        'local = МестноеВремя(base, "GMT+00:01");\n'
        'Message(ValueToStringInternal(local));\n'
        'Message(УниверсальноеВремя(local, "GMT+0:01") = base);\n'
        'Message(ToLocalTime(base, "GMT-00:00") = base);\n'
        'Message(ValueToStringInternal(ToUniversalTime(base, "GMT-23:59")));\n'
        'Message(Eval("ToLocalTime(base, ""GMT+0"")") = base);\n'
        'a = New Array; a.Add(local);\n'
        'Message(ValueFromStringInternal(ValueToStringInternal(a))[0] = local);\n')
    expected = '{"D",20240301000059}\nДа\nДа\n{"D",20240301235859}\nДа\nДа\n'
    # Each unsupported call must be catchable without assigning over saved data.
    for expression in ('ToLocalTime(base)', 'ToUniversalTime(base, Undefined)',
                       'ToLocalTime(base, "Europe/Warsaw")',
                       'ToLocalTime(base + 0.0001, "GMT+0")',
                       'ToUniversalTime(Date(1,1,1), "GMT+0:01")',
                       'ToLocalTime(base, "GMT+24")'):
        program += (f'saved = base; Try saved = {expression}; '
                    'Except Message("caught"); EndTry; Message(saved = base);\n')
        expected += 'caught\nДа\n'
    source = directory / 'Смещения.bsl'
    source.write_text(program, encoding='utf-8-sig')
    # Explicit GMT conversion must not consult either ambient timezone setting.
    env = dict(env, YADINASSI_TIMEZONE='invalid/zone', TZ='UTC0')
    cases = [([flag, program], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], program), ([], program + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Failed fixed-GMT conversion {arguments!r}: {result!r}')
    module = directory / 'Пояс.bsl'
    module.write_text('Function Convert(d) Export Return ToLocalTime(d, "GMT+5:30"); '
                      'EndFunction\n', encoding='utf-8-sig')
    importer = directory / 'Импорт.bsl'
    importer.write_text('// #Импорт Пояс.bsl\n'
                        'Message(ValueToStringInternal(Пояс.Convert(Date(2024,12,31,22,0,0))));\n',
                        encoding='utf-8-sig')
    for path in (importer, importer.relative_to(directory.parent)):
        result = subprocess.run([executable, str(path)], capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, '{"D",20250101033000}\n', ''):
            raise AssertionError(f'Failed imported fixed-GMT conversion {path!r}: {result!r}')


def check_value_list_references(executable, *, directory, env):
    """Native PR74 field behavior across entry modes; client routing is local QA."""
    directory.mkdir()
    code = '\n'.join([
        'Procedure SetRef(field, Val value) field = value; EndProcedure',
        'Procedure SetVal(Val field) field = 99; EndProcedure',
        '&AtClient',
        'Function Live(field, Val item)',
        'field = 21; Message(item.Value); item.Value = 22; Return field;',
        'EndFunction',
        'Procedure Two(first, second) first = 31; Message(second); SetRef(second, 32); Message(first); EndProcedure',
        'Procedure Fail(field) field = 41; Raise "probe"; EndProcedure',
        'owner = New ValueList; item = owner.Add(10, "old", False);',
        'SetVal(item.Значение); Message(item.Value);',
        'Message(Live(item.Value, item));',
        'Two(item.Значение, item.Value);',
        'Try Fail(item.Value); Except Message(item.Value); EndTry;',
        'SetRef(item.Представление, 123); Message(item.Presentation);',
        'SetRef(item.Пометка, 1); Message(item.Check);',
        'Try SetRef(item.Check, New Array); Except Message(item.Check); EndTry;',
        'owner.Delete(item); SetRef(item.Value, 62); Message(item.Value); Message(item.GetID());',
    ]) + '\n'
    expected = '10\n21\n22\n31\n32\n41\n123\nДа\nДа\n62\n-1\n'
    source = directory / 'СсылкиПолейСписка.bsl'
    source.write_text(code, encoding='utf-8-sig')
    cases = [([flag, code], None) for flag in ('-c', '-с', '--command')]
    cases += [([str(source)], None), (['-'], code), ([], code + '/exit\n')]
    for arguments, stdin in cases:
        result = subprocess.run([executable, *arguments], input=stdin, capture_output=True,
                                encoding='utf-8', cwd=directory.parent, env=env, timeout=30)
        if (result.returncode, result.stdout, result.stderr) != (0, expected, ''):
            raise AssertionError(f'Failed ValueList references {arguments!r}: {result!r}')
    print('Binary ValueList field references passed: live aliases, Val, duplicate/nested '
          'forwarding, partial writes, conversion, detached fields, client routing, '
          'BOM file, command flags, stdin and console')


def main() -> None:
    # Redirected Windows output can default to cp1252, which cannot encode BSL text.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    executable = str(Path(sys.argv[1]).resolve())
    expected = (ROOT / "tests" / "fixtures" / "basic.out").read_text(encoding="utf-8")
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "YADINASSI_TIMEZONE")}
    env["PYTHONIOENCODING"] = "utf-8"
    # The bundled interpreter must work without finding Python on PATH.
    env["PATH"] = os.environ.get("SystemRoot", r"C:\Windows") + r"\System32" if os.name == "nt" else "/usr/bin:/bin"
    with tempfile.TemporaryDirectory(prefix="yadinassi-smoke-") as temporary:
        # Imports use resolved paths in diagnostics. Keep direct-file paths and
        # the subprocess cwd canonical too (e.g. macOS /var, Windows aliases,
        # and a symlink or a noncanonical path supplied through TMPDIR).
        temporary = str(Path(temporary).resolve())
        check_dates(executable, directory=Path(temporary) / "dates", env=env)
        check_clocks(executable, directory=Path(temporary) / "clocks", env=env)
        check_fixed_offset_conversions(executable, directory=Path(temporary) / "fixed-gmt", env=env)
        check_saved_native_outputs(executable, directory=Path(temporary) / "native-full", env=env)
        check_null(executable, directory=Path(temporary) / "null", env=env)
        check_xml_checkpoint(executable, directory=Path(temporary) / "xml-checkpoint", env=env)
        check_table_checkpoint(executable, directory=Path(temporary) / "table-checkpoint", env=env)
        check_value_list_references(executable, directory=Path(temporary) / "list-references", env=env)
        check_numeric_presentation(executable, directory=Path(temporary) / "numeric", env=env)
        check_division(executable, directory=Path(temporary) / "division", env=env)
        check_numeric_helpers(executable, directory=Path(temporary) / "integer-part", env=env)
        check_eval(executable, directory=Path(temporary) / "eval", env=env)
        check_string_parity(executable, directory=Path(temporary) / "string-parity", env=env)
        check_array_gap(executable, directory=Path(temporary) / "array-gap", env=env)
        check_array_defaults(executable, directory=Path(temporary) / "array-defaults", env=env)
        check_value_filled(executable, directory=Path(temporary) / "filled", env=env)
        check_string_lines(executable, directory=Path(temporary) / "lines", env=env)
        check_string_template(executable, directory=Path(temporary) / "templates", env=env)
        check_string_boundaries(executable, directory=Path(temporary) / "boundaries", env=env)
        check_characters(executable, directory=Path(temporary) / "characters", env=env)
        check_rounding(executable, directory=Path(temporary) / "rounding", env=env)
        check_numeric_boolean_comparisons(executable, directory=Path(temporary) / "comparisons", env=env)
        check_goto(executable, directory=Path(temporary) / "goto", env=env)
        check_internal_serialization(executable, directory=Path(temporary) / "serialization", env=env)
        sample = Path(temporary) / "пример.bsl"
        sample.write_bytes((ROOT / "basic.bsl").read_bytes())
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
            'Процедура ВыдатьОшибку() Экспорт\n'
            'Попытка\nВызватьИсключение "из модуля";\n'
            'Исключение\nВызватьИсключение;\nКонецПопытки;\nКонецПроцедуры',
            encoding="utf-8-sig")
        exception_main = Path(temporary) / "Обработка.bsl"
        exception_main.write_text(
            '// #Импорт Ошибки.bsl\nПопытка\nОшибки.ВыдатьОшибку();\n'
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
    Type("ValueTree");
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
            'Function Failure() Export\nReturn Type("ValueTree");\nEndFunction\n'
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
             f'Строка\nТип\n{type_module.resolve()}:2:12: Тип не поддерживается: ValueTree\nДа\n', 0),
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
            (['-c', 'Type("ValueTree");'], None, '', '<команда>:1:', 'Тип не поддерживается: ValueTree'),
            (['-c', 'Тип(1);'], None, '', '<команда>:1:', 'Имя типа должно быть строкой'),
            (['-c', 'TypeOf(Message);'], None, '', '<команда>:1:',
             'ТипЗнч для этого значения пока не поддерживается'),
            (['-'], 'Тип("ДеревоЗначений");\n', '', '<stdin>:1:', 'Тип не поддерживается: ДеревоЗначений'),
            ([str(type_error_file)], None, '', str(type_error_file) + ':2:',
             'ТипЗнч для этого значения пока не поддерживается'),
            ([str(type_error_importer)], None, '', str(type_module.resolve()) + ':2:',
             'Тип не поддерживается: ValueTree'),
            ([], 'kind = Type("Number");\nkind = Type("ValueTree");\n'
             'kind\nTypeOf(kind)\n/exit\n', 'Число\nТип\n', '<консоль>:1:',
             'Тип не поддерживается: ValueTree'),
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
            print("Binary terminal tests passed: cursor editing, history, multiline input, Date literals/ticks, region continuation, type values, fixed collections, numeric presentation, rounding, division and error recovery")
    print("Binary smoke tests passed: dates, rounding, division, numeric presentation, fixed collections, type values, maps, structures, strings/UTF-16, file, sibling/nested/directory imports, exceptions, client compilation, regions, -c, -с, console, stdin, errors")


if __name__ == "__main__":
    main()
