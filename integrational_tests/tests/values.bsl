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
    // Доступность API проверяется при исполнении, а не при компиляции модуля.
    Очищено = Вычислить("ОбработкаСтрокиXML.УдалитьНедопустимыеСимволыXML(Текст, Версия)");
    Возврат Новый Структура("Input,Output,Alias,Codec",
        КодыXML(Текст), КодыXML(Очищено),
        Вычислить("XMLStringProcessing.DeleteDisallowedXMLCharacters(Текст, Версия)") = Очищено,
        КодыXML(ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Очищено))));
КонецФункции

// Дополнение нативной проверки: вызов через переменную.
// Компактная запись только type-checkpoint: пути полей и скалярные потоки.
// Сначала экранируется обратная косая черта, затем CR/LF: границы записи
// однозначны даже для текста с разделителями и настоящих многострочных потоков.
Функция ПолеКомпактногоДополнения(Знач Значение)
    Запись = ЗначениеВСтрокуВнутр(Значение);
    Запись = СтрЗаменить(Запись, "\", "\\");
    Запись = СтрЗаменить(Запись, Символ(13), "\r");
    Возврат СтрЗаменить(Запись, Символ(10), "\n");
КонецФункции

Функция ПоляКомпактногоДополнения(Знач Значение, Знач Путь)
    Результат = "";
    Если ТипЗнч(Значение) = Тип("Структура") Тогда
        Результат = Путь + "=structure(" + Строка(Значение.Количество()) + ")";
        Для Каждого Поле Из Значение Цикл
            Результат = Результат + ";";
            Результат = Результат + ПоляКомпактногоДополнения(Поле.Значение, Путь + "." + Поле.Ключ);
        КонецЦикла;
    ИначеЕсли ТипЗнч(Значение) = Тип("Массив") Тогда
        Результат = Путь + "=array(" + Строка(Значение.Количество()) + ")";
        Для Индекс = 0 По Значение.Количество() - 1 Цикл
            Результат = Результат + ";" + ПоляКомпактногоДополнения(Значение[Индекс], Путь + "." + Строка(Индекс));
        КонецЦикла;
    Иначе
        Результат = Путь + "=" + ПолеКомпактногоДополнения(Значение);
    КонецЕсли;
    Возврат Результат;
КонецФункции

// Прежние ошибки New ... .Method могли возникать до вызова метода.
// Конструкторы остаются в фиксированных строках Вычислить внутри защиты.
Процедура НаблюдатьДополнениеТипов(Знач Метка, Знач Выражение)
    Попытка
        Результат = Вычислить(Выражение);
    Исключение
        Сообщить("types-extra." + Метка + ": [error]");
        Возврат;
    КонецПопытки;
    Попытка
        Запись = ПоляКомпактногоДополнения(Результат, "value");
        Сообщить("types-extra." + Метка + ": [" + Запись + "]");
    Исключение
        Сообщить("types-extra." + Метка + ": [serialize-error]");
    КонецПопытки;
КонецПроцедуры

Функция СодержитТипДополнения(Знач Описание, Знач ПроверяемыйТип)
    Возврат Новый Структура("RU,EN", Описание.СодержитТип(ПроверяемыйТип),
        Описание.ContainsType(ПроверяемыйТип));
КонецФункции

Функция УмолчаниеТипаДополнения(Знач Описание)
    Результат = Описание.AdjustValue();
    Возврат Новый Структура("Value,Type,Russian", Результат, ТипЗнч(Результат),
        Описание.ПривестиЗначение());
КонецФункции

Функция СвойстваТипаДополнения(Знач Описание)
    Возврат Новый Структура("RU,EN", Описание.КвалификаторыСтроки.Length,
        Описание.StringQualifiers.Длина);
КонецФункции

Функция КоличествоМассиваДополнения(Знач Массив)
    Возврат Массив.Count();
КонецФункции

Функция КвалификаторыОписанияДополнения(Знач Описание)
    Итог = Новый Структура("Write,ReadWriteEqual,ReadType,NumberDigits,NumberFractionDigits,NumberSign,StringLength,StringAllowedLength,DateFractions,BinaryLength,BinaryAllowedLength",
        Неопределено, Неопределено, Неопределено,
        Описание.NumberQualifiers.Digits, Описание.NumberQualifiers.FractionDigits,
        Описание.NumberQualifiers.AllowedSign, Описание.StringQualifiers.Length,
        Описание.StringQualifiers.AllowedLength, Описание.DateQualifiers.DateFractions,
        Описание.BinaryDataQualifiers.Length, Описание.BinaryDataQualifiers.AllowedLength);
    Попытка Итог.Write = ЗначениеВСтрокуВнутр(Описание);
    Исключение Итог.Write = "[error]"; КонецПопытки;
    Попытка
        Копия = ЗначениеИзСтрокиВнутр(Итог.Write);
        Попытка Итог.ReadType = ТипЗнч(Копия); Исключение Итог.ReadType = "[error]"; КонецПопытки;
        Попытка
            ОбратныйПоток = ЗначениеВСтрокуВнутр(Копия);
            Итог.ReadWriteEqual = ОбратныйПоток = Итог.Write;
            Если Не Итог.ReadWriteEqual Тогда Итог.Вставить("ReadWrite", ОбратныйПоток); КонецЕсли;
        Исключение Итог.ReadWriteEqual = "[error]"; КонецПопытки;
    Исключение Итог.ReadType = "[error]"; КонецПопытки;
    Возврат Итог;
КонецФункции

Функция УмолчанияКвалификаторовДополнения(Знач Пустое, Знач Скалярное)
    Возврат Новый Структура("Empty,Scalars", КвалификаторыОписанияДополнения(Пустое),
        КвалификаторыОписанияДополнения(Скалярное));
КонецФункции

// Нативный checkpoint описаний типов. Никакие ответы не заданы заранее.
// Компактная запись только type-checkpoint: пути полей и скалярные потоки.
// Сначала экранируется обратная косая черта, затем CR/LF: границы записи
// однозначны даже для текста с разделителями и настоящих многострочных потоков.
Функция ПолеКомпактныхТипов(Знач Значение)
    Запись = ЗначениеВСтрокуВнутр(Значение);
    Запись = СтрЗаменить(Запись, "\", "\\");
    Запись = СтрЗаменить(Запись, Символ(13), "\r");
    Возврат СтрЗаменить(Запись, Символ(10), "\n");
КонецФункции

Функция ПоляКомпактныхТипов(Знач Значение, Знач Путь)
    Результат = "";
    Если ТипЗнч(Значение) = Тип("Структура") Тогда
        Результат = Путь + "=structure(" + Строка(Значение.Количество()) + ")";
        Для Каждого Поле Из Значение Цикл
            Результат = Результат + ";";
            Результат = Результат + ПоляКомпактныхТипов(Поле.Значение, Путь + "." + Поле.Ключ);
        КонецЦикла;
    ИначеЕсли ТипЗнч(Значение) = Тип("Массив") Тогда
        Результат = Путь + "=array(" + Строка(Значение.Количество()) + ")";
        Для Индекс = 0 По Значение.Количество() - 1 Цикл
            Результат = Результат + ";" + ПоляКомпактныхТипов(Значение[Индекс], Путь + "." + Строка(Индекс));
        КонецЦикла;
    Иначе
        Результат = Путь + "=" + ПолеКомпактныхТипов(Значение);
    КонецЕсли;
    Возврат Результат;
КонецФункции

// Новые конструкторы и пространства перечислений находятся только в строках
// Вычислить внутри защиты. Все подпрограммы предшествуют основному коду.
Процедура НаблюдатьТипы(Знач Метка, Знач Выражение)
    Попытка
        Результат = Вычислить(Выражение);
    Исключение
        Сообщить("types." + Метка + ": [error]");
        Возврат;
    КонецПопытки;
    Попытка
        Запись = ПоляКомпактныхТипов(Результат, "value");
        Сообщить("types." + Метка + ": [" + Запись + "]");
    Исключение
        Сообщить("types." + Метка + ": [serialize-error]");
    КонецПопытки;
КонецПроцедуры

// Каждая стадия независима: ошибка записи не скрывает имя и тип объекта;
// ошибка обратного чтения не скрывает настоящий прямой поток.
Функция СнимокТипов(Знач Значение)
    Итог = Новый Структура("Type,TypeWrite,TypeReadEqual,Text,Write,ReadType,ReadWriteEqual,Equal,Nested");
    Попытка Итог.Type = ТипЗнч(Значение); Исключение Итог.Type = "[error]"; КонецПопытки;
    Попытка
        Итог.TypeWrite = ЗначениеВСтрокуВнутр(ТипЗнч(Значение));
        ОбратныйПотокТипа = ЗначениеВСтрокуВнутр(ЗначениеИзСтрокиВнутр(Итог.TypeWrite));
        Итог.TypeReadEqual = ОбратныйПотокТипа = Итог.TypeWrite;
        Если Не Итог.TypeReadEqual Тогда Итог.Вставить("TypeRead", ОбратныйПотокТипа); КонецЕсли;
    Исключение
        Итог.TypeReadEqual = "[error]";
    КонецПопытки;
    Попытка Итог.Text = Строка(Значение); Исключение Итог.Text = "[error]"; КонецПопытки;
    Попытка Итог.Write = ЗначениеВСтрокуВнутр(Значение); Исключение Итог.Write = "[error]"; КонецПопытки;
    Попытка
        Копия = ЗначениеИзСтрокиВнутр(Итог.Write);
        Попытка Итог.ReadType = ТипЗнч(Копия); Исключение Итог.ReadType = "[error]"; КонецПопытки;
        Попытка
            ОбратныйПоток = ЗначениеВСтрокуВнутр(Копия);
            Итог.ReadWriteEqual = ОбратныйПоток = Итог.Write;
            Если Не Итог.ReadWriteEqual Тогда Итог.Вставить("ReadWrite", ОбратныйПоток); КонецЕсли;
        Исключение Итог.ReadWriteEqual = "[error]"; КонецПопытки;
        Попытка Итог.Equal = Копия = Значение; Исключение Итог.Equal = "[error]"; КонецПопытки;
    Исключение
        Итог.ReadType = "[error]";
    КонецПопытки;
    Попытка
        Контейнер = Новый Массив;
        Контейнер.Добавить(Значение);
        Итог.Nested = ЗначениеВСтрокуВнутр(ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Контейнер)));
    Исключение
        Итог.Nested = "[error]";
    КонецПопытки;
    Возврат Итог;
КонецФункции

Функция СвойстваЧислаТипов(Знач Значение)
    Возврат Новый Структура("Digits,FractionDigits,AllowedSign,Aliases",
        Значение.Digits, Значение.FractionDigits, Значение.AllowedSign,
        Значение.Разрядность = Значение.Digits И Значение.РазрядностьДробнойЧасти = Значение.FractionDigits
        И Значение.ДопустимыйЗнак = Значение.AllowedSign);
КонецФункции

Функция СвойстваДлиныТипов(Знач Значение)
    Возврат Новый Структура("Length,AllowedLength,Aliases", Значение.Length, Значение.AllowedLength,
        Значение.Длина = Значение.Length И Значение.ДопустимаяДлина = Значение.AllowedLength);
КонецФункции

Функция СвойстваДатыТипов(Знач Значение)
    Возврат Новый Структура("DateFractions,Aliases", Значение.DateFractions,
        Значение.ЧастиДаты = Значение.DateFractions);
КонецФункции

Функция СвойстваОписанияТипов(Знач Значение)
    Возврат Новый Структура("Types,Number,String,Date,Binary",
        Значение.Types(), СвойстваЧислаТипов(Значение.NumberQualifiers), СвойстваДлиныТипов(Значение.StringQualifiers),
        СвойстваДатыТипов(Значение.DateQualifiers), СвойстваДлиныТипов(Значение.BinaryDataQualifiers));
КонецФункции

Функция МассивТиповПробы()
    Результат = Новый Массив;
    Результат.Добавить(Тип("Строка"));
    Результат.Добавить(Тип("Число"));
    Результат.Добавить(Тип("Строка"));
    Возврат Результат;
КонецФункции

Функция НезависимостьТипов(Знач Значение)
    Список = Значение.Types();
    До = ЗначениеВСтрокуВнутр(Список);
    Список.Очистить();
    Список.Добавить(Тип("Дата"));
    Возврат Новый Структура("Before,After,Russian", До, Значение.Types(), Значение.Типы());
КонецФункции

Функция ПриведениеТипов(Знач Описание, Знач Значение)
    Результат = Описание.AdjustValue(Значение);
    Итог = Новый Структура("Value,Type,Russian,DateDelta", Результат, ТипЗнч(Результат),
        Описание.ПривестиЗначение(Значение), Неопределено);
    Если ТипЗнч(Результат) = Тип("Дата") Тогда
        Итог.DateDelta = Результат - Дата(2024,2,29,12,34,56);
    КонецЕсли;
    Возврат Итог;
КонецФункции

Функция ПоляОбъектаТипов(Знач Значение)
    Если ТипЗнч(Значение) = Тип("КвалификаторыЧисла") Тогда
        Возврат СвойстваЧислаТипов(Значение);
    ИначеЕсли ТипЗнч(Значение) = Тип("КвалификаторыСтроки") Или ТипЗнч(Значение) = Тип("КвалификаторыДвоичныхДанных") Тогда
        Возврат СвойстваДлиныТипов(Значение);
    ИначеЕсли ТипЗнч(Значение) = Тип("КвалификаторыДаты") Тогда
        Возврат СвойстваДатыТипов(Значение);
    КонецЕсли;
    Возврат СвойстваОписанияТипов(Значение);
КонецФункции

// Действие — только фиксированная строка из списка ниже, без файлов и внешних вызовов.
Функция ЗаписьСвойстваТипов(Знач Значение, Знач Действие)
    До = ПоляОбъектаТипов(Значение);
    Статус = "ok";
    Попытка Выполнить(Действие); Исключение Статус = "error"; КонецПопытки;
    Возврат Новый Структура("Status,Before,After", Статус, До, ПоляОбъектаТипов(Значение));
КонецФункции

// Begin Chars namespace helpers.
// Native-first hypotheses only. Never emit raw control characters.
Процедура НаблюдатьСимволы(Знач Метка, Знач Выражение)
    Попытка
        Результат = Вычислить(Выражение);
        Запись = ПоляКомпактныхТипов(Результат, "value");
        Сообщить("chars." + Метка + ": [" + Запись + "]");
    Исключение
        Сообщить("chars." + Метка + ": [error]");
    КонецПопытки;
КонецПроцедуры

Функция ПроекцияСимвола(Знач Значение)
    Итог = Новый Массив;
    Итог.Добавить(СтрДлина(Значение));
    Итог.Добавить(КодСимвола(Значение));
    Итог.Добавить(ТипЗнч(Значение) = Тип("Строка"));
    Возврат Итог;
КонецФункции

Функция КругСимвола(Знач Значение, Знач ЧерезXML)
    Если ЧерезXML Тогда
        Восстановлено = XMLЗначение(Тип("Строка"), XMLСтрока(Значение));
    Иначе
        Восстановлено = ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Значение));
    КонецЕсли;
    Итог = ПроекцияСимвола(Восстановлено);
    Итог.Добавить(Восстановлено = Значение);
    Возврат Итог;
КонецФункции

Функция ЗаписьСимвола(Знач Пространство, Знач Поле)
    До = Вычислить(Пространство + "." + Поле);
    Отклонено = Ложь;
    Попытка
        Выполнить(Пространство + "." + Поле + " = ""changed"";");
    Исключение
        Отклонено = Истина;
    КонецПопытки;
    После = Вычислить(Пространство + "." + Поле);
    Итог = Новый Массив;
    Итог.Добавить(Отклонено);
    Итог.Добавить(До = После);
    Итог.Добавить(ПроекцияСимвола(После));
    Возврат Итог;
КонецФункции

Функция ПолучательСимволов(Знач Пространство)
    Возврат ПроекцияСимвола(Пространство.LF);
КонецФункции
// End Chars namespace helpers.

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

// Менеджер: наблюдаем настоящий тип и кодек до возможной реализации.
НаблюдатьXML("manager.types", "New Structure(""RU,EN"", TypeOf(ОбработкаСтрокиXML), TypeOf(XMLStringProcessing))");
НаблюдатьXML("manager.write", "ValueToStringInternal(XMLStringProcessing)");
НаблюдатьXML("manager.inverse", "ValueFromStringInternal(ValueToStringInternal(ОбработкаСтрокиXML))");

// Очистка XML: контролы, границы Unicode, кодек и ошибки.
НаблюдатьXML("clean.default", "КодыXML(XMLStringProcessing.DeleteDisallowedXMLCharacters(УправляющиеXML()))");
НаблюдатьXML("clean.controls.1.0", "ОчисткаXML(УправляющиеXML(), ""1.0"")");
НаблюдатьXML("clean.controls.1.1", "ОчисткаXML(УправляющиеXML(), ""1.1"")");
НаблюдатьXML("clean.unicode.1.0", "ОчисткаXML(ГраницыXML(), ""1.0"")");
НаблюдатьXML("clean.unicode.1.1", "ОчисткаXML(ГраницыXML(), ""1.1"")");
НаблюдатьXML("clean.separated-surrogates", "ОчисткаXML(Символ(55296) + Символ(0) + Символ(56320), ""1.0"")");
НаблюдатьXML("clean.literal-markup", "ОчисткаXML(""<x>&amp;&#0;</x>"", ""1.0"")");
НаблюдатьXML("clean.bad-version", "XMLStringProcessing.DeleteDisallowedXMLCharacters(""text"", ""2.0"")");
НаблюдатьXML("clean.nonstring", "XMLStringProcessing.DeleteDisallowedXMLCharacters(123, ""1.0"")");
НаблюдатьXML("clean.undefined-version", "XMLStringProcessing.DeleteDisallowedXMLCharacters(""text"", Undefined)");

// Уточнение округления XML-даты: ответы первого прогона не различают алгоритмы.
НаблюдатьXML("date.fraction.below-half", "ПрочитатьДатуXML(""2024-02-29T12:34:56.4999"")");
НаблюдатьXML("date.fraction.half", "ПрочитатьДатуXML(""2024-02-29T12:34:56.5"")");
НаблюдатьXML("date.fraction.above-half", "ПрочитатьДатуXML(""2024-02-29T12:34:56.5001"")");
НаблюдатьXML("date.fraction.below-millisecond-carry", "ПрочитатьДатуXML(""2024-02-29T12:34:56.9994"")");
НаблюдатьXML("date.fraction.millisecond-carry-tie", "ПрочитатьДатуXML(""2024-02-29T12:34:56.9995"")");
НаблюдатьXML("date.fraction.four-digit-carry", "ПрочитатьДатуXML(""2024-02-29T12:34:56.9999"")");
НаблюдатьXML("date.fraction.below-tick-carry", "ПрочитатьДатуXML(""2024-02-29T12:34:56.99994"")");
НаблюдатьXML("date.fraction.above-tick-carry", "ПрочитатьДатуXML(""2024-02-29T12:34:56.99996"")");
НаблюдатьXML("date.fraction.odd-second-half", "ПрочитатьДатуXML(""2024-02-29T12:34:57.5"")");
НаблюдатьXML("date.fraction.day-carry", "ПрочитатьДатуXML(""2024-02-29T23:59:59.99995"")");
НаблюдатьXML("date.write.half", "XMLString(Date(2024,2,29,12,34,56) + 0.5)");
НаблюдатьXML("date.write.near-carry", "XMLString(Date(2024,2,29,12,34,56) + 0.9999)");
Сообщить("xml.checkpoint.complete: [ok]");


// Описания типов: наблюдения без заранее заданных ответов.
// Двоичные квалификаторы наблюдаются без создания ДвоичныхДанных.
НаблюдатьТипы("description.default.en", "СнимокТипов(New TypeDescription())");
НаблюдатьТипы("description.default.ru", "СнимокТипов(Новый ОписаниеТипов())");
НаблюдатьТипы("description.configured", "СнимокТипов(New TypeDescription(""String,Number,Date,Boolean""))");
НаблюдатьТипы("description.type.names", "Type(""TypeDescription"") = Тип(""ОписаниеТипов"")");
НаблюдатьТипы("number.default.en", "СнимокТипов(New NumberQualifiers())");
НаблюдатьТипы("number.default.ru", "СнимокТипов(Новый КвалификаторыЧисла())");
НаблюдатьТипы("number.configured", "СнимокТипов(New NumberQualifiers(5, 2, AllowedSign.Nonnegative))");
НаблюдатьТипы("number.type.names", "Type(""NumberQualifiers"") = Тип(""КвалификаторыЧисла"")");
НаблюдатьТипы("string.default.en", "СнимокТипов(New StringQualifiers())");
НаблюдатьТипы("string.default.ru", "СнимокТипов(Новый КвалификаторыСтроки())");
НаблюдатьТипы("string.configured", "СнимокТипов(New StringQualifiers(4, AllowedLength.Fixed))");
НаблюдатьТипы("string.type.names", "Type(""StringQualifiers"") = Тип(""КвалификаторыСтроки"")");
НаблюдатьТипы("date.default.en", "СнимокТипов(New DateQualifiers())");
НаблюдатьТипы("date.default.ru", "СнимокТипов(Новый КвалификаторыДаты())");
НаблюдатьТипы("date.configured", "СнимокТипов(New DateQualifiers(DateFractions.Date))");
НаблюдатьТипы("date.type.names", "Type(""DateQualifiers"") = Тип(""КвалификаторыДаты"")");
НаблюдатьТипы("binary.default.en", "СнимокТипов(New BinaryDataQualifiers())");
НаблюдатьТипы("binary.default.ru", "СнимокТипов(Новый КвалификаторыДвоичныхДанных())");
НаблюдатьТипы("binary.configured", "СнимокТипов(New BinaryDataQualifiers(4, AllowedLength.Fixed))");
НаблюдатьТипы("binary.type.names", "Type(""BinaryDataQualifiers"") = Тип(""КвалификаторыДвоичныхДанных"")");
НаблюдатьТипы("allowedsign.namespace", "СнимокТипов(AllowedSign)");
НаблюдатьТипы("allowedsign.namespace-alias", "TypeOf(AllowedSign) = ТипЗнч(ДопустимыйЗнак)");
НаблюдатьТипы("allowedsign.type-name", "Type(""AllowedSign"") = Тип(""ДопустимыйЗнак"")");
НаблюдатьТипы("allowedsign.any", "СнимокТипов(AllowedSign.Any)");
НаблюдатьТипы("allowedsign.any.alias", "AllowedSign.Any = ДопустимыйЗнак.Любой");
НаблюдатьТипы("allowedsign.nonnegative", "СнимокТипов(AllowedSign.Nonnegative)");
НаблюдатьТипы("allowedsign.nonnegative.alias", "AllowedSign.Nonnegative = ДопустимыйЗнак.Неотрицательный");
НаблюдатьТипы("allowedlength.namespace", "СнимокТипов(AllowedLength)");
НаблюдатьТипы("allowedlength.namespace-alias", "TypeOf(AllowedLength) = ТипЗнч(ДопустимаяДлина)");
НаблюдатьТипы("allowedlength.type-name", "Type(""AllowedLength"") = Тип(""ДопустимаяДлина"")");
НаблюдатьТипы("allowedlength.variable", "СнимокТипов(AllowedLength.Variable)");
НаблюдатьТипы("allowedlength.variable.alias", "AllowedLength.Variable = ДопустимаяДлина.Переменная");
НаблюдатьТипы("allowedlength.fixed", "СнимокТипов(AllowedLength.Fixed)");
НаблюдатьТипы("allowedlength.fixed.alias", "AllowedLength.Fixed = ДопустимаяДлина.Фиксированная");
НаблюдатьТипы("datefractions.namespace", "СнимокТипов(DateFractions)");
НаблюдатьТипы("datefractions.namespace-alias", "TypeOf(DateFractions) = ТипЗнч(ЧастиДаты)");
НаблюдатьТипы("datefractions.type-name", "Type(""DateFractions"") = Тип(""ЧастиДаты"")");
НаблюдатьТипы("datefractions.datetime", "СнимокТипов(DateFractions.DateTime)");
НаблюдатьТипы("datefractions.datetime.alias", "DateFractions.DateTime = ЧастиДаты.ДатаВремя");
НаблюдатьТипы("datefractions.date", "СнимокТипов(DateFractions.Date)");
НаблюдатьТипы("datefractions.date.alias", "DateFractions.Date = ЧастиДаты.Дата");
НаблюдатьТипы("datefractions.time", "СнимокТипов(DateFractions.Time)");
НаблюдатьТипы("datefractions.time.alias", "DateFractions.Time = ЧастиДаты.Время");
НаблюдатьТипы("properties.number.default", "СвойстваЧислаТипов(New NumberQualifiers())");
НаблюдатьТипы("properties.number.configured", "СвойстваЧислаТипов(New NumberQualifiers(5,2,AllowedSign.Nonnegative))");
НаблюдатьТипы("properties.string.default", "СвойстваДлиныТипов(New StringQualifiers())");
НаблюдатьТипы("properties.string.configured", "СвойстваДлиныТипов(New StringQualifiers(4,AllowedLength.Fixed))");
НаблюдатьТипы("properties.date.default", "СвойстваДатыТипов(New DateQualifiers())");
НаблюдатьТипы("properties.date.time", "СвойстваДатыТипов(New DateQualifiers(DateFractions.Time))");
НаблюдатьТипы("properties.binary.default", "СвойстваДлиныТипов(New BinaryDataQualifiers())");
НаблюдатьТипы("properties.binary.configured", "СвойстваДлиныТипов(New BinaryDataQualifiers(4,AllowedLength.Fixed))");
НаблюдатьТипы("properties.description.default", "СвойстваОписанияТипов(New TypeDescription())");
НаблюдатьТипы("properties.description.scalars", "СвойстваОписанияТипов(New TypeDescription(""Number,String,Date,Boolean""))");
НаблюдатьТипы("number.ctor.negative", "СвойстваЧислаТипов(New NumberQualifiers(-1))");
НаблюдатьТипы("number.ctor.fraction", "СвойстваЧислаТипов(New NumberQualifiers(5.9, 2.9))");
НаблюдатьТипы("number.ctor.fraction-exceeds", "СвойстваЧислаТипов(New NumberQualifiers(2, 3))");
НаблюдатьТипы("number.ctor.zero-digits", "СвойстваЧислаТипов(New NumberQualifiers(0, 2))");
НаблюдатьТипы("number.ctor.max38", "СвойстваЧислаТипов(New NumberQualifiers(38, 10))");
НаблюдатьТипы("number.ctor.above38", "СвойстваЧислаТипов(New NumberQualifiers(39))");
НаблюдатьТипы("number.ctor.text", "СвойстваЧислаТипов(New NumberQualifiers(""5"", ""2""))");
НаблюдатьТипы("number.ctor.undefined", "СвойстваЧислаТипов(New NumberQualifiers(Undefined))");
НаблюдатьТипы("number.ctor.wrong-sign", "СвойстваЧислаТипов(New NumberQualifiers(5, 2, 0))");
НаблюдатьТипы("string.ctor.negative", "СвойстваДлиныТипов(New StringQualifiers(-1))");
НаблюдатьТипы("string.ctor.fraction", "СвойстваДлиныТипов(New StringQualifiers(3.9))");
НаблюдатьТипы("string.ctor.text", "СвойстваДлиныТипов(New StringQualifiers(""3""))");
НаблюдатьТипы("string.ctor.wrong-length", "СвойстваДлиныТипов(New StringQualifiers(3, 0))");
НаблюдатьТипы("string.ctor.zero-fixed", "СвойстваДлиныТипов(New StringQualifiers(0, AllowedLength.Fixed))");
НаблюдатьТипы("binary.ctor.negative", "СвойстваДлиныТипов(New BinaryDataQualifiers(-1))");
НаблюдатьТипы("binary.ctor.fraction", "СвойстваДлиныТипов(New BinaryDataQualifiers(3.9))");
НаблюдатьТипы("binary.ctor.text", "СвойстваДлиныТипов(New BinaryDataQualifiers(""3""))");
НаблюдатьТипы("binary.ctor.wrong-length", "СвойстваДлиныТипов(New BinaryDataQualifiers(3, 0))");
НаблюдатьТипы("binary.ctor.zero-fixed", "СвойстваДлиныТипов(New BinaryDataQualifiers(0, AllowedLength.Fixed))");
НаблюдатьТипы("date.ctor.wrong-fraction", "New DateQualifiers(0)");
НаблюдатьТипы("description.ctor.empty", "СнимокТипов(New TypeDescription(""""))");
НаблюдатьТипы("description.ctor.spaces", "СнимокТипов(New TypeDescription("" Строка , Число ""))");
НаблюдатьТипы("description.ctor.duplicates", "СнимокТипов(New TypeDescription(""String,Number,String""))");
НаблюдатьТипы("description.ctor.array", "СнимокТипов(New TypeDescription(МассивТиповПробы()))");
НаблюдатьТипы("description.ctor.unknown", "СнимокТипов(New TypeDescription(""NoSuchType""))");
НаблюдатьТипы("description.ctor.undefined", "СнимокТипов(New TypeDescription(Undefined))");
НаблюдатьТипы("description.ctor.null", "СнимокТипов(New TypeDescription(""Null""))");
НаблюдатьТипы("description.ctor.undefined-type", "СнимокТипов(New TypeDescription(""Undefined""))");
НаблюдатьТипы("description.types-copy", "НезависимостьТипов(New TypeDescription(""String,Number""))");
НаблюдатьТипы("description.copy.add-remove", "СнимокТипов(New TypeDescription(New TypeDescription(""String,Number""), ""Date"", ""String""))");
НаблюдатьТипы("description.copy.qualifiers", "СвойстваОписанияТипов(New TypeDescription(New TypeDescription(""Number"", New NumberQualifiers(5,2))))");
НаблюдатьТипы("description.copy.override", "СвойстваОписанияТипов(New TypeDescription(New TypeDescription(""Number"", New NumberQualifiers(5,2)), , , New NumberQualifiers(3,1)))");
НаблюдатьТипы("description.all-qualifiers", "СвойстваОписанияТипов(New TypeDescription(""Number,String,Date"", New NumberQualifiers(5,2), New StringQualifiers(4), New DateQualifiers(DateFractions.Time), New BinaryDataQualifiers(8)))");
НаблюдатьТипы("adjust.number.text", "ПриведениеТипов(New TypeDescription(""Number""), ""12.5"")");
НаблюдатьТипы("adjust.number.invalid", "ПриведениеТипов(New TypeDescription(""Number""), ""abc"")");
НаблюдатьТипы("adjust.number.boolean", "ПриведениеТипов(New TypeDescription(""Number""), True)");
НаблюдатьТипы("adjust.number.undefined", "ПриведениеТипов(New TypeDescription(""Number""), Undefined)");
НаблюдатьТипы("adjust.string.number", "ПриведениеТипов(New TypeDescription(""String""), 12.5)");
НаблюдатьТипы("adjust.string.boolean", "ПриведениеТипов(New TypeDescription(""String""), False)");
НаблюдатьТипы("adjust.string.undefined", "ПриведениеТипов(New TypeDescription(""String""), Undefined)");
НаблюдатьТипы("adjust.date.text", "ПриведениеТипов(New TypeDescription(""Date""), ""20240229123456"")");
НаблюдатьТипы("adjust.date.number", "ПриведениеТипов(New TypeDescription(""Date""), 1)");
НаблюдатьТипы("adjust.boolean.text", "ПриведениеТипов(New TypeDescription(""Boolean""), ""True"")");
НаблюдатьТипы("adjust.boolean.zero", "ПриведениеТипов(New TypeDescription(""Boolean""), 0)");
НаблюдатьТипы("adjust.boolean.number", "ПриведениеТипов(New TypeDescription(""Boolean""), 2)");
НаблюдатьТипы("adjust.boolean.undefined", "ПриведениеТипов(New TypeDescription(""Boolean""), Undefined)");
НаблюдатьТипы("adjust.empty.number", "ПриведениеТипов(New TypeDescription(""""), 12)");
НаблюдатьТипы("adjust.null.number", "ПриведениеТипов(New TypeDescription(""Null""), 12)");
НаблюдатьТипы("adjust.union-number-string.text", "ПриведениеТипов(New TypeDescription(""Number,String""), ""12"")");
НаблюдатьТипы("adjust.union-string-number.number", "ПриведениеТипов(New TypeDescription(""String,Number""), 12)");
НаблюдатьТипы("adjust.union-number-date.text", "ПриведениеТипов(New TypeDescription(""Number,Date""), ""20240229"")");
НаблюдатьТипы("adjust.union-date-number.text", "ПриведениеТипов(New TypeDescription(""Date,Number""), ""20240229"")");
НаблюдатьТипы("adjust.union-number-string.boolean", "ПриведениеТипов(New TypeDescription(""Number,String""), True)");
НаблюдатьТипы("adjust.union-string-number.boolean", "ПриведениеТипов(New TypeDescription(""String,Number""), True)");
НаблюдатьТипы("adjust.union-undefined-number.text", "ПриведениеТипов(New TypeDescription(""Undefined,Number""), ""12"")");
НаблюдатьТипы("adjust.qualified-number.below-half", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), 1.234)");
НаблюдатьТипы("adjust.qualified-number.half", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), 1.235)");
НаблюдатьТипы("adjust.qualified-number.even-half", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), 1.245)");
НаблюдатьТипы("adjust.qualified-number.negative-even-half", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), -1.245)");
НаблюдатьТипы("adjust.qualified-number.negative-half", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), -1.235)");
НаблюдатьТипы("adjust.qualified-number.max", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), 999.99)");
НаблюдатьТипы("adjust.qualified-number.overflow", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), 1000)");
НаблюдатьТипы("adjust.qualified-number.round-overflow", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), 999.995)");
НаблюдатьТипы("adjust.qualified-number.negative-overflow", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2)), -1000)");
НаблюдатьТипы("adjust.nonnegative", "ПриведениеТипов(New TypeDescription(""Number"", New NumberQualifiers(5,2,AllowedSign.Nonnegative)), -1.235)");
НаблюдатьТипы("adjust.string.variable-short", "ПриведениеТипов(New TypeDescription(""String"", , New StringQualifiers(4)), ""ab"")");
НаблюдатьТипы("adjust.string.fixed-short", "ПриведениеТипов(New TypeDescription(""String"", , New StringQualifiers(4,AllowedLength.Fixed)), ""ab"")");
НаблюдатьТипы("adjust.string.fixed-long", "ПриведениеТипов(New TypeDescription(""String"", , New StringQualifiers(4,AllowedLength.Fixed)), ""abcdef"")");
НаблюдатьТипы("adjust.string.utf16-cut", "ПриведениеТипов(New TypeDescription(""String"", , New StringQualifiers(2)), ""Я😀Z"")");
НаблюдатьТипы("adjust.string.unicode-exact", "ПриведениеТипов(New TypeDescription(""String"", , New StringQualifiers(3)), ""Я😀Z"")");
НаблюдатьТипы("adjust.string.trim-spaces", "ПриведениеТипов(New TypeDescription(""String"", , New StringQualifiers(3)), ""a  b"")");
НаблюдатьТипы("adjust.date.date", "ПриведениеТипов(New TypeDescription(""Date"", , , New DateQualifiers(DateFractions.Date)), Date(2024,2,29,12,34,56) + 0.1234)");
НаблюдатьТипы("adjust.date.time", "ПриведениеТипов(New TypeDescription(""Date"", , , New DateQualifiers(DateFractions.Time)), Date(2024,2,29,12,34,56) + 0.1234)");
НаблюдатьТипы("adjust.date.datetime", "ПриведениеТипов(New TypeDescription(""Date"", , , New DateQualifiers(DateFractions.DateTime)), Date(2024,2,29,12,34,56) + 0.1234)");
НаблюдатьТипы("readonly.number", "ЗаписьСвойстваТипов(New NumberQualifiers(5,2), ""Значение.Разрядность = 9;"")");
НаблюдатьТипы("readonly.string", "ЗаписьСвойстваТипов(New StringQualifiers(4), ""Значение.Length = 9;"")");
НаблюдатьТипы("readonly.date", "ЗаписьСвойстваТипов(New DateQualifiers(), ""Значение.DateFractions = Значение.DateFractions;"")");
НаблюдатьТипы("readonly.binary", "ЗаписьСвойстваТипов(New BinaryDataQualifiers(4), ""Значение.Длина = 9;"")");
НаблюдатьТипы("readonly.description", "ЗаписьСвойстваТипов(New TypeDescription(""String""), ""Значение.StringQualifiers = Значение.StringQualifiers;"")");
Сообщить("types.checkpoint.complete: [ok]");


// Дополнение описаний типов: вызов через переменную.
// Отдельные синтаксические контроли намеренно проверяют цепочку конструктора.
НаблюдатьДополнениеТипов("contains.present", "СодержитТипДополнения(New TypeDescription(""String,Number""), Type(""String""))");
НаблюдатьДополнениеТипов("contains.absent", "СодержитТипДополнения(New TypeDescription(""String,Number""), Type(""Date""))");
НаблюдатьДополнениеТипов("contains.wrong", "СодержитТипДополнения(New TypeDescription(""String""), ""String"")");
НаблюдатьДополнениеТипов("default.number", "УмолчаниеТипаДополнения(New TypeDescription(""Number""))");
НаблюдатьДополнениеТипов("default.string", "УмолчаниеТипаДополнения(New TypeDescription(""String""))");
НаблюдатьДополнениеТипов("default.date", "УмолчаниеТипаДополнения(New TypeDescription(""Date""))");
НаблюдатьДополнениеТипов("default.boolean", "УмолчаниеТипаДополнения(New TypeDescription(""Boolean""))");
НаблюдатьДополнениеТипов("default.number-string", "УмолчаниеТипаДополнения(New TypeDescription(""Number,String""))");
НаблюдатьДополнениеТипов("default.string-number", "УмолчаниеТипаДополнения(New TypeDescription(""String,Number""))");
НаблюдатьДополнениеТипов("default.number-date", "УмолчаниеТипаДополнения(New TypeDescription(""Number,Date""))");
НаблюдатьДополнениеТипов("default.undefined-number", "УмолчаниеТипаДополнения(New TypeDescription(""Undefined,Number""))");
НаблюдатьДополнениеТипов("default.null", "УмолчаниеТипаДополнения(New TypeDescription(""Null""))");
НаблюдатьДополнениеТипов("default.empty", "УмолчаниеТипаДополнения(New TypeDescription(""""))");
НаблюдатьДополнениеТипов("properties.aliases", "СвойстваТипаДополнения(New TypeDescription(""String""))");
НаблюдатьДополнениеТипов("syntax.array-direct", "New Array().Count()");
НаблюдатьДополнениеТипов("syntax.array-parentheses", "(New Array()).Count()");
НаблюдатьДополнениеТипов("syntax.array-receiver", "КоличествоМассиваДополнения(New Array())");
НаблюдатьДополнениеТипов("syntax.description-parentheses", "(New TypeDescription(""String"")).ContainsType(Type(""String""))");
НаблюдатьДополнениеТипов("qualifiers.default", "УмолчанияКвалификаторовДополнения(New TypeDescription(), New TypeDescription(""Number,String,Date,Boolean""))");
НаблюдатьДополнениеТипов("qualifiers.full", "КвалификаторыОписанияДополнения(New TypeDescription(""Number,String,Date"", New NumberQualifiers(5,2,AllowedSign.Nonnegative), New StringQualifiers(4,AllowedLength.Fixed), New DateQualifiers(DateFractions.Time), New BinaryDataQualifiers(8,AllowedLength.Fixed)))");
НаблюдатьДополнениеТипов("qualifiers.copy", "КвалификаторыОписанияДополнения(New TypeDescription(New TypeDescription(""Number"", New NumberQualifiers(5,2))))");
НаблюдатьДополнениеТипов("qualifiers.override", "КвалификаторыОписанияДополнения(New TypeDescription(New TypeDescription(""Number"", New NumberQualifiers(5,2)), , , New NumberQualifiers(3,1)))");
НаблюдатьДополнениеТипов("qualifiers.date-only", "КвалификаторыОписанияДополнения(New TypeDescription(""Date"", , , New DateQualifiers(DateFractions.Date)))");
Сообщить("types-extra.checkpoint.complete: [ok]");
// Begin Chars namespace observations.
НаблюдатьСимволы("member.cr.ru", "ПроекцияСимвола(Символы.ВК)");
НаблюдатьСимволы("write.cr.ru", "ЗаписьСимвола(""Символы"", ""ВК"")");
НаблюдатьСимволы("member.cr.en", "ПроекцияСимвола(Chars.CR)");
НаблюдатьСимволы("write.cr.en", "ЗаписьСимвола(""Chars"", ""CR"")");
НаблюдатьСимволы("alias.cr", "Символы.ВК = Chars.CR");
НаблюдатьСимволы("case.cr", "ПроекцияСимвола(cHaRs.cr)");
НаблюдатьСимволы("codec.cr", "КругСимвола(Chars.CR, Ложь)");
НаблюдатьСимволы("xml.cr", "КругСимвола(Символы.ВК, Истина)");
НаблюдатьСимволы("member.vtab.ru", "ПроекцияСимвола(Символы.ВТаб)");
НаблюдатьСимволы("write.vtab.ru", "ЗаписьСимвола(""Символы"", ""ВТаб"")");
НаблюдатьСимволы("member.vtab.en", "ПроекцияСимвола(Chars.VTab)");
НаблюдатьСимволы("write.vtab.en", "ЗаписьСимвола(""Chars"", ""VTab"")");
НаблюдатьСимволы("alias.vtab", "Символы.ВТаб = Chars.VTab");
НаблюдатьСимволы("case.vtab", "ПроекцияСимвола(cHaRs.vtAB)");
НаблюдатьСимволы("codec.vtab", "КругСимвола(Chars.VTab, Ложь)");
НаблюдатьСимволы("xml.vtab", "КругСимвола(Символы.ВТаб, Истина)");
НаблюдатьСимволы("member.nbsp.ru", "ПроекцияСимвола(Символы.НПП)");
НаблюдатьСимволы("write.nbsp.ru", "ЗаписьСимвола(""Символы"", ""НПП"")");
НаблюдатьСимволы("member.nbsp.en", "ПроекцияСимвола(Chars.NBSp)");
НаблюдатьСимволы("write.nbsp.en", "ЗаписьСимвола(""Chars"", ""NBSp"")");
НаблюдатьСимволы("alias.nbsp", "Символы.НПП = Chars.NBSp");
НаблюдатьСимволы("case.nbsp", "ПроекцияСимвола(cHaRs.nbsP)");
НаблюдатьСимволы("codec.nbsp", "КругСимвола(Chars.NBSp, Ложь)");
НаблюдатьСимволы("xml.nbsp", "КругСимвола(Символы.НПП, Истина)");
НаблюдатьСимволы("member.lf.ru", "ПроекцияСимвола(Символы.ПС)");
НаблюдатьСимволы("write.lf.ru", "ЗаписьСимвола(""Символы"", ""ПС"")");
НаблюдатьСимволы("member.lf.en", "ПроекцияСимвола(Chars.LF)");
НаблюдатьСимволы("write.lf.en", "ЗаписьСимвола(""Chars"", ""LF"")");
НаблюдатьСимволы("alias.lf", "Символы.ПС = Chars.LF");
НаблюдатьСимволы("case.lf", "ПроекцияСимвола(cHaRs.lf)");
НаблюдатьСимволы("codec.lf", "КругСимвола(Chars.LF, Ложь)");
НаблюдатьСимволы("xml.lf", "КругСимвола(Символы.ПС, Истина)");
НаблюдатьСимволы("member.ff.ru", "ПроекцияСимвола(Символы.ПФ)");
НаблюдатьСимволы("write.ff.ru", "ЗаписьСимвола(""Символы"", ""ПФ"")");
НаблюдатьСимволы("member.ff.en", "ПроекцияСимвола(Chars.FF)");
НаблюдатьСимволы("write.ff.en", "ЗаписьСимвола(""Chars"", ""FF"")");
НаблюдатьСимволы("alias.ff", "Символы.ПФ = Chars.FF");
НаблюдатьСимволы("case.ff", "ПроекцияСимвола(cHaRs.ff)");
НаблюдатьСимволы("codec.ff", "КругСимвола(Chars.FF, Ложь)");
НаблюдатьСимволы("xml.ff", "КругСимвола(Символы.ПФ, Истина)");
НаблюдатьСимволы("member.tab.ru", "ПроекцияСимвола(Символы.Таб)");
НаблюдатьСимволы("write.tab.ru", "ЗаписьСимвола(""Символы"", ""Таб"")");
НаблюдатьСимволы("member.tab.en", "ПроекцияСимвола(Chars.Tab)");
НаблюдатьСимволы("write.tab.en", "ЗаписьСимвола(""Chars"", ""Tab"")");
НаблюдатьСимволы("alias.tab", "Символы.Таб = Chars.Tab");
НаблюдатьСимволы("case.tab", "ПроекцияСимвола(cHaRs.tAB)");
НаблюдатьСимволы("codec.tab", "КругСимвола(Chars.Tab, Ложь)");
НаблюдатьСимволы("xml.tab", "КругСимвола(Символы.Таб, Истина)");
НаблюдатьСимволы("case.namespace-ru", "ПроекцияСимвола(сИмВоЛы.пС)");
НаблюдатьСимволы("missing", "ПроекцияСимвола(Chars.NotACharacter)");
НаблюдатьСимволы("call.member", "ПроекцияСимвола(Chars.LF())");
НаблюдатьСимволы("call.namespace", "ПроекцияСимвола(Chars())");
НаблюдатьСимволы("index.string", "ПроекцияСимвола(Chars[""LF""])");
НаблюдатьСимволы("index.number", "ПроекцияСимвола(Символы[0])");
НаблюдатьСимволы("eval.ru", "ПроекцияСимвола(Вычислить(""Символы.ПС""))");
НаблюдатьСимволы("eval.en", "ПроекцияСимвола(Eval(""Chars.LF""))");
НаблюдатьСимволы("receiver.ru", "ПолучательСимволов(Символы)");
НаблюдатьСимволы("receiver.en", "ПолучательСимволов(Chars)");
Сообщить("chars.checkpoint.complete: [ok]");
// End Chars namespace observations.
