// LOCAL preparation: fixed owned-config probe. No native answers predicted.
Функция MCText(Знач Text)
    Если СтрДлина(Text) > 64 Тогда ВызватьИсключение "metadata-observer-bound"; КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "metadata-observer-unit"; КонецЕсли;
        Digits = "";
        Для D = 1 По 4 Цикл
            Q = Цел(Code / 16);
            Digits = Сред("0123456789abcdef", Code - Q * 16 + 1, 1) + Digits;
            Code = Q;
        КонецЦикла;
        Record = Record + Digits;
    КонецЦикла;
    Возврат Record;
КонецФункции
Функция MCScalar(Знач Value)
    Если ТипЗнч(Value) = Тип("Строка") Тогда Возврат MCText(Value); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Булево") Тогда Возврат ?(Value, "B1", "B0"); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Неопределено") Тогда Возврат "U"; КонецЕсли;
    Если ТипЗнч(Value) = Тип("Число") Тогда
        Если Value < 0 Или Value > 64 Или Value <> Цел(Value) Тогда ВызватьИсключение "metadata-observer-number"; КонецЕсли;
        Возврат "N" + Строка(Value);
    КонецЕсли;
    ВызватьИсключение "metadata-observer-type";
КонецФункции
Процедура MCEmit(Знач Label, Знач Value)
    Попытка
        Encoded = MCScalar(Value);
    Исключение
        Сообщить("MC-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("MC-" + Label + ": [ok|" + Encoded + "]");
КонецПроцедуры
Процедура MCObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("MC-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    MCEmit(Label, Value);
КонецПроцедуры
Сообщить("MC-C1: [" + MCText("") + "]");
Сообщить("MC-C2: [" + MCText("A ;""😀") + "]");
MCObserve("01", "Метаданные.Справочники.Количество()"); // count.ru
MCObserve("02", "Metadata.Catalogs.Count()"); // count.en
MCObserve("03", "Метаданные.Справочники.NativeOracleItems.Имя"); // name.ru
MCObserve("04", "Metadata.Catalogs.NativeOracleItems.Name"); // name.en
MCObserve("05", "Метаданные.Справочники.NativeOracleItems.ПолноеИмя()"); // fullname.ru
MCObserve("06", "Metadata.Catalogs.NativeOracleItems.FullName()"); // fullname.en
MCObserve("07", "Метаданные.Справочники.NativeOracleItems.Реквизиты.Payload.Тип.КвалификаторыСтроки.Длина"); // payload.ru
MCObserve("08", "Metadata.Catalogs.NativeOracleItems.Attributes.Payload.Type.StringQualifiers.Length"); // payload.en
MCObserve("09", "Метаданные.Справочники.Найти(""NativeOracleItems"").Имя"); // find.ru
MCObserve("10", "Metadata.Catalogs.Find(""NativeOracleItems"").Name"); // find.en
MCObserve("11", "Metadata.Catalogs.Find(""nativeoracleitems"").Name"); // find.lower
MCObserve("12", "Метаданные.Справочники.Найти(""NATIVEORACLEITEMS"").Имя"); // find.upper
MCObserve("13", "Metadata.Catalogs.Find(""AbsentNativeOracleCatalog"") = Undefined"); // find.missing
MCObserve("14", "Metadata.Catalogs[""NativeOracleItems""].Name"); // index.name
MCObserve("15", "Metadata.Catalogs[0].Name"); // index.zero
MCObserve("16", "Metadata.Catalogs[-1].Name"); // index.negative
MCObserve("17", "Metadata.Catalogs[1].Name"); // index.past
MCObserve("18", "Metadata.Catalogs.Find()"); // find.noarg
MCObserve("19", "Metadata.Catalogs.Find(""NativeOracleItems"", 1).Name"); // find.extra
MCObserve("20", "Metadata.Catalogs.Find(1) = Undefined"); // find.number
MCObserve("21", "Metadata.Catalogs.Count(1)"); // count.extra
MCObserve("22", "Metadata.Catalogs.AbsentNativeOracleCatalog.Name"); // property.missing
MCObserve("23", "Метаданные.Справочники.NativeOracleItems = Metadata.Catalogs.NativeOracleItems"); // global.identity
MCObserve("24", "Metadata.Catalogs.Find(""NativeOracleItems"") = Metadata.Catalogs.NativeOracleItems"); // find.identity
// A surprising successful write must remain visible, not be rolled back or normalized.
Попытка
    Выполнить("Метаданные.Справочники.NativeOracleItems.Имя = ""ChangedNativeOracleItems"";");
    MCEmit("25", Истина);
Исключение
    Сообщить("MC-25: [action-error]");
КонецПопытки;
MCObserve("26", "Metadata.Catalogs[0].Name"); // post-write independent observation
