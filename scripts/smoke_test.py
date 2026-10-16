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
        cases = [
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
            print("Binary terminal tests passed: cursor editing, history, multiline input, region continuation, type values and error recovery")
    print("Binary smoke tests passed: type values, maps, structures, strings/UTF-16, file, sibling/nested/directory imports, exceptions, client compilation, regions, -c, -с, console, stdin, errors")


if __name__ == "__main__":
    main()
