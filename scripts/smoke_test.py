"""Test the distributed executable outside the source tree and without PYTHONPATH."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


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
        type_output = ('Неопределено\nБулево\nЧисло\nСтрока\nМассив\nСтруктура\n'
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
            print("Binary terminal tests passed: cursor editing, history, multiline input, region continuation, type values, fixed collections and error recovery")
    print("Binary smoke tests passed: fixed collections, type values, maps, structures, strings/UTF-16, file, sibling/nested/directory imports, exceptions, client compilation, regions, -c, -с, console, stdin, errors")


if __name__ == "__main__":
    main()
