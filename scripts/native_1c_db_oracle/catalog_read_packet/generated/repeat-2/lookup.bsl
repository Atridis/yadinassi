// LOCAL preparation: generated owned-config probe. No native answers predicted.
Функция CRText(Знач Text)
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
Функция CRScalar(Знач Value)
    Если ТипЗнч(Value) = Тип("Строка") Тогда Возврат CRText(Value); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Булево") Тогда Возврат ?(Value, "B1", "B0"); КонецЕсли;
    Если ТипЗнч(Value) = Тип("Неопределено") Тогда Возврат "U"; КонецЕсли;
    Если ТипЗнч(Value) = Тип("Число") Тогда
        Если Value < 0 Или Value > 64 Или Value <> Цел(Value) Тогда ВызватьИсключение "metadata-observer-number"; КонецЕсли;
        Возврат "N" + Строка(Value);
    КонецЕсли;
    ВызватьИсключение "metadata-observer-type";
КонецФункции
Процедура CREmit(Знач Label, Знач Value)
    Попытка
        Encoded = CRScalar(Value);
    Исключение
        Сообщить("CR-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("CR-" + Label + ": [ok|" + Encoded + "]");
КонецПроцедуры
Процедура CRObserve(Знач Label, Знач Expression)
    Попытка
        Value = Вычислить(Expression);
    Исключение
        Сообщить("CR-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    CREmit(Label, Value);
КонецПроцедуры
Сообщить("CR-C1: [" + CRText("") + "]");
Сообщить("CR-C2: [" + CRText("A ;""😀") + "]");
Failed = Ложь; S = Неопределено;
Попытка
    Result = Catalogs.Cb0f3538b.EmptyRef().Metadata().Name;
Исключение
    Сообщить("CR-01: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("01", Result); КонецЕсли; Failed = Ложь;
// control.name
Попытка
    Result = String(Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).UUID());
Исключение
    Сообщить("CR-02: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("02", Result); КонецЕсли; Failed = Ложь;
// control.uuid
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByCode("10").UUID());
Исключение
    Сообщить("CR-03: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("03", Result); КонецЕсли; Failed = Ложь;
// code.10
Попытка
    Result = ValueIsFilled(Catalogs.Cb0f3538b.FindByCode("10"));
Исключение
    Сообщить("CR-04: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("04", Result); КонецЕсли; Failed = Ложь;
// filled.10
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByCode("20").UUID());
Исключение
    Сообщить("CR-05: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("05", Result); КонецЕсли; Failed = Ложь;
// code.20
Попытка
    Result = ValueIsFilled(Catalogs.Cb0f3538b.FindByCode("20"));
Исключение
    Сообщить("CR-06: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("06", Result); КонецЕсли; Failed = Ложь;
// filled.20
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByCode("30").UUID());
Исключение
    Сообщить("CR-07: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("07", Result); КонецЕсли; Failed = Ложь;
// code.30
Попытка
    Result = ValueIsFilled(Catalogs.Cb0f3538b.FindByCode("30"));
Исключение
    Сообщить("CR-08: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("08", Result); КонецЕсли; Failed = Ложь;
// filled.30
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByCode("40").UUID());
Исключение
    Сообщить("CR-09: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("09", Result); КонецЕсли; Failed = Ложь;
// code.40
Попытка
    Result = ValueIsFilled(Catalogs.Cb0f3538b.FindByCode("40"));
Исключение
    Сообщить("CR-10: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("10", Result); КонецЕсли; Failed = Ложь;
// filled.40
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByCode("99").UUID());
Исключение
    Сообщить("CR-11: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("11", Result); КонецЕсли; Failed = Ложь;
// code.99
Попытка
    Result = ValueIsFilled(Catalogs.Cb0f3538b.FindByCode("99"));
Исключение
    Сообщить("CR-12: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("12", Result); КонецЕсли; Failed = Ложь;
// filled.99
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByDescription("Alpha", True).UUID());
Исключение
    Сообщить("CR-13: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("13", Result); КонецЕсли; Failed = Ложь;
// desc.Alpha
Попытка
    Result = Catalogs.Cb0f3538b.FindByDescription("Alpha", True).IsEmpty();
Исключение
    Сообщить("CR-14: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("14", Result); КонецЕсли; Failed = Ложь;
// empty.Alpha
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByDescription("Zulu", True).UUID());
Исключение
    Сообщить("CR-15: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("15", Result); КонецЕсли; Failed = Ложь;
// desc.Zulu
Попытка
    Result = Catalogs.Cb0f3538b.FindByDescription("Zulu", True).IsEmpty();
Исключение
    Сообщить("CR-16: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("16", Result); КонецЕсли; Failed = Ложь;
// empty.Zulu
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByDescription("Mike", True).UUID());
Исключение
    Сообщить("CR-17: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("17", Result); КонецЕсли; Failed = Ложь;
// desc.Mike
Попытка
    Result = Catalogs.Cb0f3538b.FindByDescription("Mike", True).IsEmpty();
Исключение
    Сообщить("CR-18: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("18", Result); КонецЕсли; Failed = Ложь;
// empty.Mike
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByDescription("Gone", True).UUID());
Исключение
    Сообщить("CR-19: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("19", Result); КонецЕсли; Failed = Ложь;
// desc.Gone
Попытка
    Result = Catalogs.Cb0f3538b.FindByDescription("Gone", True).IsEmpty();
Исключение
    Сообщить("CR-20: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("20", Result); КонецЕсли; Failed = Ложь;
// empty.Gone
Попытка
    Result = String(Catalogs.Cb0f3538b.FindByDescription("Absent", True).UUID());
Исключение
    Сообщить("CR-21: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("21", Result); КонецЕсли; Failed = Ложь;
// desc.Absent
Попытка
    Result = Catalogs.Cb0f3538b.FindByDescription("Absent", True).IsEmpty();
Исключение
    Сообщить("CR-22: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("22", Result); КонецЕсли; Failed = Ложь;
// empty.Absent
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")) = Catalogs.Cf5758dc3.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71"));
Исключение
    Сообщить("CR-23: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("23", Result); КонецЕсли; Failed = Ложь;
// sameuuid
Попытка
    Result = TypeOf(Catalogs.Cb0f3538b.EmptyRef()) = TypeOf(Catalogs.Cf5758dc3.EmptyRef());
Исключение
    Сообщить("CR-24: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("24", Result); КонецЕсли; Failed = Ложь;
// sametype
