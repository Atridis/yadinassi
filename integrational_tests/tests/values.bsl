// Нативный checkpoint специальных значений: Null. Ответы определяет реальная 1С.
// Это отдельная тема: basic.bsl остается неизменным примером релизного архива.
// Выражения вычисляются внутри защиты; ошибки не прерывают следующие наблюдения.
Процедура НаблюдатьNull(Знач Метка, Знач Выражение)
    Попытка
        Результат = Вычислить(Выражение);
    Исключение
        Сообщить("null." + Метка + ": [error]");
        Возврат;
    КонецПопытки;
    Попытка
        Запись = ЗначениеВСтрокуВнутр(Результат);
        Сообщить("null." + Метка + ": [" + Запись + "]");
    Исключение
        Сообщить("null." + Метка + ": [serialize-error]");
    КонецПопытки;
КонецПроцедуры

// Null передается из защищенного выражения, не вычисляется вне него.
Функция ВложенныйNull(Знач Значение)
    МассивЗначений = Новый Массив;
    МассивЗначений.Добавить(Значение);
    МассивЗначений.Добавить(Неопределено);
    Вложено = Новый Структура("Value,Items", Значение, МассивЗначений);
    Возврат ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Вложено));
КонецФункции

Функция ПоискNull(Знач Значение)
    МассивЗначений = Новый Массив;
    МассивЗначений.Добавить(Неопределено);
    МассивЗначений.Добавить(Значение);
    Возврат Новый Структура("NullIndex,UndefinedIndex",
        МассивЗначений.Найти(Значение), МассивЗначений.Найти(Неопределено));
КонецФункции

Функция КлючNull(Знач Значение)
    Карта = Новый Соответствие;
    Карта.Вставить(Неопределено, "undefined");
    Карта.Вставить(Значение, "first");
    Карта.Вставить(Значение, "second");
    Восстановлено = ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Карта));
    Возврат Новый Структура("Count,Value,UndefinedValue,Restored",
        Карта.Количество(), Карта.Получить(Значение),
        Карта.Получить(Неопределено), Восстановлено);
КонецФункции

// Нативный checkpoint скалярного XML. Ответы определяет реальная 1С.
// Новые вызовы выполняются только внутри защиты; диагностический текст локали
// не становится эталоном. Непарные суррогаты и управляющие символы не выводятся.
Процедура НаблюдатьXML(Знач Метка, Знач Выражение)
    Попытка
        Результат = Вычислить(Выражение);
    Исключение
        Сообщить("xml." + Метка + ": [error]");
        Возврат;
    КонецПопытки;
    Попытка
        Запись = ЗначениеВСтрокуВнутр(Результат);
        Сообщить("xml." + Метка + ": [" + Запись + "]");
    Исключение
        Сообщить("xml." + Метка + ": [serialize-error]");
    КонецПопытки;
КонецПроцедуры

Функция ПрочитатьДатуXML(Знач Текст)
    Результат = XMLЗначение(Тип("Дата"), Текст);
    // Внутренняя запись Date сама по себе не доказывает сохранение долей секунды.
    Возврат Новый Структура("Value,Delta", Результат,
        Результат - Дата(2024, 2, 29, 12, 34, 56));
КонецФункции

Функция КругXML(Знач Значение)
    Текст = XMLСтрока(Значение);
    Прочитано = XMLЗначение(ТипЗнч(Значение), Текст);
    Вложено = Новый Структура("Text,Value", Текст, Прочитано);
    Возврат Новый Структура("XML,Value,Equal,Type,Restored",
        Текст, Прочитано, Прочитано = Значение, ТипЗнч(Прочитано),
        ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Вложено)));
КонецФункции

Функция КодыXML(Знач Текст)
    Результат = Новый Массив;
    // Единственный цикл ограничен короткой входной строкой этой пробы.
    Для Позиция = 1 По СтрДлина(Текст) Цикл
        Результат.Добавить(КодСимвола(Текст, Позиция));
    КонецЦикла;
    Возврат Результат;
КонецФункции

Функция УправляющиеXML()
    Возврат Символ(0) + Символ(1) + Символ(8) + Символ(9) + Символ(10)
        + Символ(11) + Символ(12) + Символ(13) + Символ(14) + Символ(31)
        + Символ(32) + Символ(127) + Символ(132) + Символ(133)
        + Символ(134) + Символ(159) + Символ(160);
КонецФункции

Функция ГраницыXML()
    Возврат Символ(55295) + "😀" + Символ(57344) + Символ(64976)
        + Символ(65533) + Символ(65534) + Символ(65535)
        + Символ(55296) + "A" + Символ(56320);
КонецФункции

Функция ОчисткаXML(Знач Текст, Знач Версия)
    Очищено = УдалитьНедопустимыеСимволыXML(Текст, Версия);
    Возврат Новый Структура("Input,Output,Alias,Codec",
        КодыXML(Текст), КодыXML(Очищено),
        DeleteDisallowedXMLCharacters(Текст, Версия) = Очищено,
        КодыXML(ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Очищено))));
КонецФункции

// Значение, тип и настоящий прямой/обратный кодек.
НаблюдатьNull("literal.upper", "NULL");
НаблюдатьNull("literal.mixed", "nUlL");
НаблюдатьNull("type.ru", "ТипЗнч(Null)");
НаблюдатьNull("type.en", "TypeOf(Null)");
НаблюдатьNull("type.name", "Type(""Null"")");
НаблюдатьNull("codec.value-roundtrip", "ValueFromStringInternal(ValueToStringInternal(Null))");
НаблюдатьNull("codec.type-roundtrip", "ValueFromStringInternal(ValueToStringInternal(Type(""Null"")))");
НаблюдатьNull("convert.string", "String(Null)");
НаблюдатьNull("convert.filled", "ValueIsFilled(Null)");
НаблюдатьNull("convert.number", "Number(Null)");
НаблюдатьNull("convert.boolean", "Boolean(Null)");

// Сравнение: не переносим SQL-семантику в язык сценариев.
НаблюдатьNull("compare.self-equal", "Null = Null");
НаблюдатьNull("compare.self-not-equal", "Null <> Null");
НаблюдатьNull("compare.undefined", "Null = Undefined");
НаблюдатьNull("compare.undefined-reversed", "Undefined = Null");
НаблюдатьNull("compare.zero", "Null = 0");
НаблюдатьNull("compare.empty-string", "Null = """"");
НаблюдатьNull("compare.less", "Null < 0");
НаблюдатьNull("compare.greater", "0 > Null");

// Логика: обе позиции операнда и условие; результаты не заданы.
НаблюдатьNull("logic.not", "Not Null");
НаблюдатьNull("logic.and-false", "Null And False");
НаблюдатьNull("logic.false-and", "False And Null");
НаблюдатьNull("logic.and-true", "Null And True");
НаблюдатьNull("logic.true-and", "True And Null");
НаблюдатьNull("logic.or-false", "Null Or False");
НаблюдатьNull("logic.false-or", "False Or Null");
НаблюдатьNull("logic.or-true", "Null Or True");
НаблюдатьNull("logic.true-or", "True Or Null");
НаблюдатьNull("conditional", "?(Null, ""then"", ""else"")");

// Арифметика ограничена простыми различающими случаями.
НаблюдатьNull("arithmetic.negative", "-Null");
НаблюдатьNull("arithmetic.plus", "Null + 1");
НаблюдатьNull("arithmetic.plus-reversed", "1 + Null");
НаблюдатьNull("arithmetic.minus", "Null - 1");
НаблюдатьNull("arithmetic.minus-reversed", "1 - Null");
НаблюдатьNull("arithmetic.times-zero", "Null * 0");
НаблюдатьNull("arithmetic.divide", "Null / 1");
НаблюдатьNull("arithmetic.divide-reversed", "1 / Null");

// Вложенные значения, поиск и ключи: только существующие автономные коллекции.
НаблюдатьNull("collection.nested-roundtrip", "ВложенныйNull(Null)");
НаблюдатьNull("collection.find", "ПоискNull(Null)");
НаблюдатьNull("collection.map-roundtrip", "КлючNull(Null)");

Сообщить("null.checkpoint.complete: [ok]");

// Скалярный XML: наблюдения без заранее заданных ответов.

// Число: запись, допустимые лексические формы и обратное чтение.
НаблюдатьXML("number.write.zero", "XMLString(0)");
НаблюдатьXML("number.write.negative-zero", "XMLString(-0.0000)");
НаблюдатьXML("number.write.decimal", "XMLString(12345.6700)");
НаблюдатьXML("number.write.negative-small", "XMLString(-0.000001)");
НаблюдатьXML("number.write.precision", "XMLString(123456789012345678901234567890.123456789)");
НаблюдатьXML("number.write.tiny", "XMLString(0.000000000000000000000000001)");
НаблюдатьXML("number.read.plus-leading", "XMLValue(Type(""Number""), ""+001.2300"")");
НаблюдатьXML("number.read.minus-zero", "XMLValue(Type(""Number""), ""-0"")");
НаблюдатьXML("number.read.leading-point", "XMLValue(Type(""Number""), "".5"")");
НаблюдатьXML("number.read.trailing-point", "XMLValue(Type(""Number""), ""5."")");
НаблюдатьXML("number.read.exponent", "XMLValue(Type(""Number""), ""1e3"")");
НаблюдатьXML("number.read.exponent-upper", "XMLValue(Type(""Number""), ""1E-3"")");
НаблюдатьXML("number.read.space", "XMLValue(Type(""Number""), "" 1.5 "")");
НаблюдатьXML("number.read.comma", "XMLValue(Type(""Number""), ""1,5"")");
НаблюдатьXML("number.read.empty", "XMLValue(Type(""Number""), """")");
НаблюдатьXML("number.read.nan", "XMLValue(Type(""Number""), ""NaN"")");
НаблюдатьXML("number.read.tab", "XMLЗначение(Тип(""Число""), Символ(9) + ""1.5"" + Символ(10))");
НаблюдатьXML("number.roundtrip", "КругXML(12345678901234567890.123456789)");

// Дата: календарь, доли секунды и явные смещения часового пояса.
НаблюдатьXML("date.write.minimum", "XMLСтрока(Date(1,1,1))");
НаблюдатьXML("date.write.leap", "XMLСтрока(Date(2024,2,29,12,34,56))");
НаблюдатьXML("date.write.fraction", "XMLСтрока(Date(2024,2,29,12,34,56) + 0.1234)");
НаблюдатьXML("date.write.maximum", "XMLСтрока(Date(9999,12,31,23,59,59))");
НаблюдатьXML("date.read.plain", "ПрочитатьДатуXML(""2024-02-29T12:34:56"")");
НаблюдатьXML("date.read.date-only", "ПрочитатьДатуXML(""2024-02-29"")");
НаблюдатьXML("date.read.utc", "ПрочитатьДатуXML(""2024-02-29T12:34:56Z"")");
НаблюдатьXML("date.read.offset-east", "ПрочитатьДатуXML(""2024-02-29T12:34:56+03:00"")");
НаблюдатьXML("date.read.offset-west", "ПрочитатьДатуXML(""2024-02-29T12:34:56-05:30"")");
НаблюдатьXML("date.read.fraction", "ПрочитатьДатуXML(""2024-02-29T12:34:56.1234"")");
НаблюдатьXML("date.read.fraction-tie", "ПрочитатьДатуXML(""2024-02-29T12:34:56.12345"")");
НаблюдатьXML("date.read.fraction-carry", "ПрочитатьДатуXML(""2024-02-29T12:34:56.99995"")");
НаблюдатьXML("date.read.midnight24", "ПрочитатьДатуXML(""2024-02-29T24:00:00"")");
НаблюдатьXML("date.read.invalid-day", "ПрочитатьДатуXML(""2023-02-29T12:34:56"")");
НаблюдатьXML("date.roundtrip", "КругXML(Date(2024,2,29,12,34,56) + 0.1234)");

// Специальные значения: документированные типы, неизвестная лексика.
НаблюдатьXML("null.write", "XMLString(Null)");
НаблюдатьXML("null.read-empty", "XMLValue(Type(""Null""), """")");

// Неопределено проверяется отдельно от Null.
НаблюдатьXML("undefined.write", "XMLString(Undefined)");
НаблюдатьXML("undefined.read-empty", "XMLValue(Type(""Undefined""), """")");

// Очистка XML: контролы, границы Unicode, кодек и ошибки.
НаблюдатьXML("clean.default", "КодыXML(DeleteDisallowedXMLCharacters(УправляющиеXML()))");
НаблюдатьXML("clean.controls.1.0", "ОчисткаXML(УправляющиеXML(), ""1.0"")");
НаблюдатьXML("clean.controls.1.1", "ОчисткаXML(УправляющиеXML(), ""1.1"")");
НаблюдатьXML("clean.unicode.1.0", "ОчисткаXML(ГраницыXML(), ""1.0"")");
НаблюдатьXML("clean.unicode.1.1", "ОчисткаXML(ГраницыXML(), ""1.1"")");
НаблюдатьXML("clean.separated-surrogates", "ОчисткаXML(Символ(55296) + Символ(0) + Символ(56320), ""1.0"")");
НаблюдатьXML("clean.literal-markup", "ОчисткаXML(""<x>&amp;&#0;</x>"", ""1.0"")");
НаблюдатьXML("clean.bad-version", "DeleteDisallowedXMLCharacters(""text"", ""2.0"")");
НаблюдатьXML("clean.nonstring", "DeleteDisallowedXMLCharacters(123, ""1.0"")");
НаблюдатьXML("clean.undefined-version", "DeleteDisallowedXMLCharacters(""text"", Undefined)");

Сообщить("xml.checkpoint.complete: [ok]");
