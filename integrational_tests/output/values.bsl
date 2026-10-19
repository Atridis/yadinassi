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
