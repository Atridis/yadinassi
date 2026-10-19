// Нативный checkpoint основы Date. Результаты определяет реальная 1С.
// Все выражения изолированы: ошибка не мешает следующей пробе и маркеру.
Процедура НаблюдатьДату(Знач Метка, Знач Выражение)
    Попытка
        Результат = Вычислить(Выражение);
    Исключение
        Сообщить("date." + Метка + ": [error]");
        Возврат;
    КонецПопытки;
    Попытка
        Запись = ЗначениеВСтрокуВнутр(Результат);
        Сообщить("date." + Метка + ": [" + Запись + "]");
    Исключение
        Сообщить("date." + Метка + ": [serialize-error]");
    КонецПопытки;
КонецПроцедуры

// Равные независимо созданные даты должны наблюдаться и как ключи коллекции.
// Функция вызывается только внутри защищенного Вычислить; циклов и внешних I/O нет.
Функция ПроверитьКлючиДат()
    Ключ = Дата(2024, 2, 29, 12, 34, 56);
    Таблица = Новый Соответствие;
    Таблица.Вставить(Ключ, "first");
    Таблица.Вставить(Дата(2024, 2, 29, 12, 34, 56), "second");
    Восстановлено = ЗначениеИзСтрокиВнутр(ЗначениеВСтрокуВнутр(Таблица));
    Возврат Новый Структура("Count,Value,RestoredCount,RestoredValue",
        Таблица.Количество(), Таблица.Получить(Дата(2024, 2, 29, 12, 34, 56)),
        Восстановлено.Количество(), Восстановлено.Получить(Ключ));
КонецФункции

НаблюдатьДату("construct.parts", "Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("construct.ymd", "Дата(2024, 2, 29)");
НаблюдатьДату("construct.ymdh", "Date(2024, 2, 29, 12)");
НаблюдатьДату("construct.ymdhm", "Date(2024, 2, 29, 12, 34)");
НаблюдатьДату("construct.omitted", "Date(2024, 2, 29, , , 56)");
НаблюдатьДату("construct.canonical", "Date(""20240229123456"")");
НаблюдатьДату("construct.short", "Date(""20240229"")");
НаблюдатьДату("construct.fraction", "Date(2024, 2, 29, 12, 34, 56.9) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("construct.nonleap", "Date(2023, 2, 29)");
НаблюдатьДату("construct.min", "Date(1, 1, 1)");
НаблюдатьДату("construct.max", "Date(9999, 12, 31, 23, 59, 59)");
НаблюдатьДату("construct.zero-year", "Date(0, 1, 1)");
НаблюдатьДату("construct.excess-year", "Date(10000, 1, 1)");
НаблюдатьДату("literal.full", "'20240229123456'");
НаблюдатьДату("literal.short", "'20240229'");
НаблюдатьДату("literal.partial-time", "'202402291234'");
НаблюдатьДату("literal.short-time", "'2024022912'");
НаблюдатьДату("literal.punctuation", "'2024-02-29 12:34:56'");
НаблюдатьДату("literal.invalid", "'20230229'");
НаблюдатьДату("codec.type-ru", "Тип(""Дата"")");
НаблюдатьДату("codec.type-en", "Type(""Date"")");
НаблюдатьДату("codec.typeof", "TypeOf(Date(2024, 2, 29))");
НаблюдатьДату("codec.roundtrip", "ValueFromStringInternal(ValueToStringInternal(Date(2024, 2, 29, 12, 34, 56)))");
НаблюдатьДату("codec.type-roundtrip", "ValueFromStringInternal(ValueToStringInternal(Type(""Date"")))");
НаблюдатьДату("codec.map-value-keys", "ПроверитьКлючиДат()");
НаблюдатьДату("string.full", "String(Date(2024, 2, 29, 12, 34, 56))");
НаблюдатьДату("string.empty", "String(Date(1, 1, 1))");
НаблюдатьДату("filled.empty", "ValueIsFilled(Date(1, 1, 1))");
НаблюдатьДату("filled.time", "ValueIsFilled(Date(1, 1, 1, 0, 0, 1))");
НаблюдатьДату("arithmetic.add", "Date(2024, 2, 29, 23, 59, 59) + 1");
НаблюдатьДату("arithmetic.reversed", "1 + Date(2024, 2, 29, 23, 59, 59)");
НаблюдатьДату("arithmetic.subtract", "Date(2024, 3, 1) - 1");
НаблюдатьДату("arithmetic.difference", "Date(2024, 3, 1) - Date(2024, 2, 28)");
НаблюдатьДату("arithmetic.min-underflow", "Date(1, 1, 1) - 1");
НаблюдатьДату("arithmetic.max-overflow", "Date(9999, 12, 31, 23, 59, 59) + 1");
НаблюдатьДату("compare.equal", "Date(2024, 2, 29) = Date(""20240229"")");
НаблюдатьДату("compare.order", "Date(2024, 2, 29) < Date(2024, 3, 1)");
НаблюдатьДату("compare.number-equal", "Date(1, 1, 1) = 0");
НаблюдатьДату("precision.delta-0-0001", "(Date(2024, 2, 29, 12, 34, 56) + 0.0001) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.delta-0-00005", "(Date(2024, 2, 29, 12, 34, 56) + 0.00005) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.delta-0-00015", "(Date(2024, 2, 29, 12, 34, 56) + 0.00015) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.delta-neg0-0001", "(Date(2024, 2, 29, 12, 34, 56) + -0.0001) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.delta-neg0-00005", "(Date(2024, 2, 29, 12, 34, 56) + -0.00005) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.delta-neg0-00015", "(Date(2024, 2, 29, 12, 34, 56) + -0.00015) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.roundtrip", "ValueFromStringInternal(ValueToStringInternal(Date(2024, 2, 29, 12, 34, 56) + 0.1234)) - Date(2024, 2, 29, 12, 34, 56)");
НаблюдатьДату("precision.codec", "Date(2024, 2, 29, 12, 34, 56) + 0.1234");
НаблюдатьДату("precision.half-second", "New Structure(""Low,Tie,High"", (Date(2024, 2, 29, 12, 34, 56) + 0.4) - Date(2024, 2, 29, 12, 34, 56), (Date(2024, 2, 29, 12, 34, 56) + 0.5) - Date(2024, 2, 29, 12, 34, 56), (Date(2024, 2, 29, 12, 34, 56) + 0.6) - Date(2024, 2, 29, 12, 34, 56))");
НаблюдатьДату("precision.second-component", "Second(Date(2024, 2, 29, 12, 34, 56) + 0.5)");
НаблюдатьДату("components.all", "New Structure(""Y,M,D,H,N,S"", Year(Date(2024, 2, 29, 12, 34, 56)), Month(Date(2024, 2, 29, 12, 34, 56)), Day(Date(2024, 2, 29, 12, 34, 56)), Hour(Date(2024, 2, 29, 12, 34, 56)), Minute(Date(2024, 2, 29, 12, 34, 56)), Second(Date(2024, 2, 29, 12, 34, 56)))");
НаблюдатьДату("precision.negative-half-second", "New Structure(""Low,Tie,High"", (Date(2024, 2, 29, 12, 34, 56) - 0.4) - Date(2024, 2, 29, 12, 34, 56), (Date(2024, 2, 29, 12, 34, 56) - 0.5) - Date(2024, 2, 29, 12, 34, 56), (Date(2024, 2, 29, 12, 34, 56) - 0.6) - Date(2024, 2, 29, 12, 34, 56))");
Сообщить("date.checkpoint.complete: [ok]");

// Календарный checkpoint: результаты и скрытые доли секунды определяет реальная 1С.
НаблюдатьДату("calendar.period.begin-minute", "New Structure(""Value,Delta"", BegOfMinute((Date(2024,2,29,12,34,56) + 0.1234)), BegOfMinute((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29,12,34,0))");
НаблюдатьДату("calendar.period.end-minute", "New Structure(""Value,Delta"", КонецМинуты((Date(2024,2,29,12,34,56) + 0.1234)), КонецМинуты((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29,12,34,59))");
НаблюдатьДату("calendar.period.begin-hour", "New Structure(""Value,Delta"", BegOfHour((Date(2024,2,29,12,34,56) + 0.1234)), BegOfHour((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29,12,0,0))");
НаблюдатьДату("calendar.period.end-hour", "New Structure(""Value,Delta"", КонецЧаса((Date(2024,2,29,12,34,56) + 0.1234)), КонецЧаса((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29,12,59,59))");
НаблюдатьДату("calendar.period.begin-day", "New Structure(""Value,Delta"", BegOfDay((Date(2024,2,29,12,34,56) + 0.1234)), BegOfDay((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29))");
НаблюдатьДату("calendar.period.end-day", "New Structure(""Value,Delta"", КонецДня((Date(2024,2,29,12,34,56) + 0.1234)), КонецДня((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29,23,59,59))");
НаблюдатьДату("calendar.period.begin-week", "New Structure(""Value,Delta"", BegOfWeek((Date(2024,2,29,12,34,56) + 0.1234)), BegOfWeek((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,26))");
НаблюдатьДату("calendar.period.end-week", "New Structure(""Value,Delta"", КонецНедели((Date(2024,2,29,12,34,56) + 0.1234)), КонецНедели((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,3,3,23,59,59))");
НаблюдатьДату("calendar.period.begin-month", "New Structure(""Value,Delta"", BegOfMonth((Date(2024,2,29,12,34,56) + 0.1234)), BegOfMonth((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,1))");
НаблюдатьДату("calendar.period.end-month", "New Structure(""Value,Delta"", КонецМесяца((Date(2024,2,29,12,34,56) + 0.1234)), КонецМесяца((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,2,29,23,59,59))");
НаблюдатьДату("calendar.period.begin-quarter", "New Structure(""Value,Delta"", BegOfQuarter((Date(2024,2,29,12,34,56) + 0.1234)), BegOfQuarter((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,1,1))");
НаблюдатьДату("calendar.period.end-quarter", "New Structure(""Value,Delta"", КонецКвартала((Date(2024,2,29,12,34,56) + 0.1234)), КонецКвартала((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,3,31,23,59,59))");
НаблюдатьДату("calendar.period.begin-year", "New Structure(""Value,Delta"", BegOfYear((Date(2024,2,29,12,34,56) + 0.1234)), BegOfYear((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,1,1))");
НаблюдатьДату("calendar.period.end-year", "New Structure(""Value,Delta"", КонецГода((Date(2024,2,29,12,34,56) + 0.1234)), КонецГода((Date(2024,2,29,12,34,56) + 0.1234)) - Date(2024,12,31,23,59,59))");
НаблюдатьДату("calendar.month.forward-year", "New Structure(""Value,Delta"", AddMonth(Date(2023,12,15,12,34,56) + 0.1234,2), AddMonth(Date(2023,12,15,12,34,56) + 0.1234,2) - Date(2024,2,15,12,34,56))");
НаблюдатьДату("calendar.month.backward-year", "New Structure(""Value,Delta"", ДобавитьМесяц(Date(2024,1,15,12,34,56) + 0.1234,-2), ДобавитьМесяц(Date(2024,1,15,12,34,56) + 0.1234,-2) - Date(2023,11,15,12,34,56))");
НаблюдатьДату("calendar.month.leap-january", "New Structure(""Value,Delta"", AddMonth(Date(2024,1,31,12,34,56) + 0.1234,1), AddMonth(Date(2024,1,31,12,34,56) + 0.1234,1) - Date(2024,2,29,12,34,56))");
НаблюдатьДату("calendar.month.common-january", "AddMonth(Date(2023,1,31),1)");
НаблюдатьДату("calendar.month.leap-year", "AddMonth(Date(2024,2,29),12)");
НаблюдатьДату("calendar.month.reverse-end", "AddMonth(Date(2024,3,31),-1)");
НаблюдатьДату("calendar.month.chain", "AddMonth(AddMonth(Date(2024,1,31),1),1) - AddMonth(Date(2024,1,31),2)");
НаблюдатьДату("calendar.month.zero-fraction", "AddMonth(Date(2024,2,29,12,34,56) + 0.1234,0) - Date(2024,2,29,12,34,56)");
НаблюдатьДату("calendar.month.count-pos-half", "AddMonth(Date(2024,5,15),0.5)");
НаблюдатьДату("calendar.month.count-neg-half", "AddMonth(Date(2024,5,15),-0.5)");
НаблюдатьДату("calendar.month.count-pos-one-half", "AddMonth(Date(2024,5,15),1.5)");
НаблюдатьДату("calendar.month.count-neg-one-half", "AddMonth(Date(2024,5,15),-1.5)");
НаблюдатьДату("calendar.month.min-underflow", "AddMonth(Date(1,1,1),-1)");
НаблюдатьДату("calendar.month.max-overflow", "AddMonth(Date(9999,12,31,23,59,59),1)");
НаблюдатьДату("calendar.number.january-2018", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2018,1,1)), WeekDay(Date(2018,1,1)), DayOfYear(Date(2018,1,1)))");
НаблюдатьДату("calendar.number.january-2019", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2019,1,1)), WeekDay(Date(2019,1,1)), DayOfYear(Date(2019,1,1)))");
НаблюдатьДату("calendar.number.january-2020", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2020,1,1)), WeekDay(Date(2020,1,1)), DayOfYear(Date(2020,1,1)))");
НаблюдатьДату("calendar.number.january-2021", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2021,1,1)), WeekDay(Date(2021,1,1)), DayOfYear(Date(2021,1,1)))");
НаблюдатьДату("calendar.number.january-2022", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2022,1,1)), WeekDay(Date(2022,1,1)), DayOfYear(Date(2022,1,1)))");
НаблюдатьДату("calendar.number.january-2023", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2023,1,1)), WeekDay(Date(2023,1,1)), DayOfYear(Date(2023,1,1)))");
НаблюдатьДату("calendar.number.january-2015", "New Structure(""Week,Day,Ordinal"", WeekOfYear(Date(2015,1,1)), WeekDay(Date(2015,1,1)), DayOfYear(Date(2015,1,1)))");
НаблюдатьДату("calendar.number.year-end", "New Structure(""Week,Day,Ordinal"", НеделяГода(Date(2015,12,31)), ДеньНедели(Date(2015,12,31)), ДеньГода(Date(2015,12,31)))");
НаблюдатьДату("calendar.number.first-monday", "New Structure(""Week,Day,Ordinal"", НеделяГода(Date(2016,1,4)), ДеньНедели(Date(2016,1,4)), ДеньГода(Date(2016,1,4)))");
НаблюдатьДату("calendar.number.february", "New Structure(""Week,Day,Ordinal"", НеделяГода(Date(2021,2,1)), ДеньНедели(Date(2021,2,1)), ДеньГода(Date(2021,2,1)))");
НаблюдатьДату("calendar.number.leap-ordinals", "New Structure(""Before,Leap,After,Last"", DayOfYear(Date(2024,2,28)), DayOfYear(Date(2024,2,29)), DayOfYear(Date(2024,3,1)), DayOfYear(Date(2024,12,31)))");
НаблюдатьДату("calendar.number.common-and-weekdays", "New Structure(""March,Last,Sunday,Monday,WeekSunday,WeekMonday"", DayOfYear(Date(2023,3,1)), DayOfYear(Date(2023,12,31)), WeekDay(Date(2024,3,3)), WeekDay(Date(2024,3,4)), WeekOfYear(Date(2024,3,3)), WeekOfYear(Date(2024,3,4)))");
НаблюдатьДату("calendar.edge.begin-min", "BegOfWeek(Date(1,1,1))");
НаблюдатьДату("calendar.edge.end-max-week", "EndOfWeek(Date(9999,12,31,23,59,59))");
НаблюдатьДату("calendar.edge.begin-max-year", "НачалоГода(Date(9999,12,31,23,59,59))");
НаблюдатьДату("calendar.edge.end-max-year", "EndOfYear(Date(9999,12,31,23,59,59)) - Date(9999,12,31,23,59,59)");
НаблюдатьДату("calendar.edge.wrong-date", "BegOfDay(0)");
НаблюдатьДату("calendar.edge.wrong-count", "AddMonth(Date(2024,2,29),Undefined)");
НаблюдатьДату("calendar.edge.missing-argument", "AddMonth(Date(2024,2,29))");
НаблюдатьДату("calendar.edge.excess-argument", "WeekOfYear(Date(2024,2,29),1)");
Сообщить("date.calendar.checkpoint.complete: [ok]");
