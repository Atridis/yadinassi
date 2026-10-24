// Historical v3 helper from PR #102 commit 68716d6c4cc6689928deb92775f35b0725148336.
// Offline regression fixture only; never staged or executed by the native oracle.
// Shape-only diagnostic: exactly one officially documented filtered invocation.
// No second argument, scalar cell rendering, metadata values, or fallback calls.
Функция NativeФормаХранения(Контекст)
    Отбор = Новый Массив;
    Отбор.Добавить("Справочник.NativeOracleItems");
    Контекст.phase = "contract_call";
    Таблица = ПолучитьСтруктуруХраненияБазыДанных(Отбор);
    Контекст.phase = "contract_scan";
    Форма = Новый Структура("schema,target,nesting,tables", 1, "Справочник.NativeOracleItems", "observed_value_tables_only", Новый Массив);
    Бюджет = Новый Структура("columns,types,units,rows,cells", 0, 0, 0, 0, 0);
    NativeФормаТаблицы(Таблица, Неопределено, Неопределено, 0, Форма, Бюджет, Контекст);
    Возврат Форма;
КонецФункции

Процедура NativeФормаЛимит(Условие, Контекст)
    Контекст.phase = "contract_limit";
    Если Не Условие Тогда
        ВызватьИсключение "artifact_limit";
    КонецЕсли;
    Контекст.phase = "contract_scan";
КонецПроцедуры

Процедура NativeФормаСтроки(Значение, Бюджет, Контекст)
    Если ТипЗнч(Значение) <> Тип("Строка") Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
    Длина = СтрДлина(Значение);
    NativeФормаЛимит(Длина > 0 И Длина <= 64 И Бюджет.units + Длина <= 768, Контекст);
    // Match Python's BMP-only units, including worst-case JSON escapes.
    Для Индекс = 1 По Длина Цикл
        Код = КодСимвола(Значение, Индекс);
        Если Код < 32 Или Код > 65535 Или (Код >= 55296 И Код <= 57343) Тогда
            ВызватьИсключение "invalid_marker";
        КонецЕсли;
    КонецЦикла;
    Бюджет.units = Бюджет.units + Длина;
КонецПроцедуры

Процедура NativeФормаТаблицы(Таблица, Родитель, ЧерезКолонку, Глубина, Форма, Бюджет, Контекст)
    Если ТипЗнч(Таблица) <> Тип("ТаблицаЗначений") Тогда
        ВызватьИсключение "invalid_marker";
    КонецЕсли;
    // Count before iteration/allocation; repeated objects count again. Cycles
    // cannot bypass occurrence/depth/work budgets or imply exhaustive nesting.
    NativeФормаЛимит(Глубина <= 3 И Форма.tables.Количество() < 16, Контекст);
    ЧислоКолонок = Таблица.Колонки.Количество();
    ЧислоСтрок = Таблица.Количество();
    NativeФормаЛимит(ЧислоКолонок <= 32 И Бюджет.columns + ЧислоКолонок <= 64, Контекст);
    NativeФормаЛимит(Бюджет.rows + ЧислоСтрок <= 256 И Бюджет.cells + ЧислоСтрок * ЧислоКолонок <= 4096, Контекст);
    Бюджет.columns = Бюджет.columns + ЧислоКолонок;
    Бюджет.rows = Бюджет.rows + ЧислоСтрок;
    Бюджет.cells = Бюджет.cells + ЧислоСтрок * ЧислоКолонок;
    НомерТаблицы = Форма.tables.Количество();
    Сигнатура = Новый Структура("parent,via_column,columns", Родитель, ЧерезКолонку, Новый Массив);
    Форма.tables.Добавить(Сигнатура);
    Для Каждого Колонка Из Таблица.Колонки Цикл
        NativeФормаСтроки(Колонка.Имя, Бюджет, Контекст);
        Типы = Колонка.ТипЗначения.Типы();
        NativeФормаЛимит(Типы.Количество() <= 8 И Бюджет.types + Типы.Количество() <= 128, Контекст);
        Бюджет.types = Бюджет.types + Типы.Количество();
        Описание = Новый Структура("name,types", Колонка.Имя, Новый Массив);
        Для Каждого ОбъявленныйТип Из Типы Цикл
            // Only declared Type values may be rendered, never cell contents.
            Если ТипЗнч(ОбъявленныйТип) <> Тип("Тип") Тогда
                ВызватьИсключение "invalid_marker";
            КонецЕсли;
            ИмяТипа = Строка(ОбъявленныйТип);
            NativeФормаСтроки(ИмяТипа, Бюджет, Контекст);
            Описание.types.Добавить(ИмяТипа);
        КонецЦикла;
        Сигнатура.columns.Добавить(Описание);
    КонецЦикла;
    // Discover nested ValueTables from runtime types, not guessed column names.
    // Scalar/composite values and all row data stay private and are not copied.
    Для Каждого СтрокаТаблицы Из Таблица Цикл
        Для НомерКолонки = 0 По ЧислоКолонок - 1 Цикл
            Если ТипЗнч(СтрокаТаблицы[НомерКолонки]) = Тип("ТаблицаЗначений") Тогда
                NativeФормаТаблицы(СтрокаТаблицы[НомерКолонки], НомерТаблицы, НомерКолонки, Глубина + 1, Форма, Бюджет, Контекст);
            КонецЕсли;
        КонецЦикла;
    КонецЦикла;
КонецПроцедуры

