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
FreshA = Неопределено;
Попытка
    FreshA = Catalogs.C01a9a4ac.GetRef();
Исключение
КонецПопытки;
FreshB = Неопределено;
Попытка
    FreshB = Catalogs.C01a9a4ac.GetRef();
Исключение
КонецПопытки;
Observed = Истина;
Попытка
    Result = Catalogs.C01a9a4ac.Metadata().Name;
Исключение
    Сообщить("CR-01: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("01", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = String(Catalogs.C01a9a4ac.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846")).UUID());
Исключение
    Сообщить("CR-02: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("02", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = String(FreshA.UUID());
Исключение
    Сообщить("CR-03: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("03", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = String(FreshB.UUID());
Исключение
    Сообщить("CR-04: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("04", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = FreshA.IsEmpty();
Исключение
    Сообщить("CR-05: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("05", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = FreshB.IsEmpty();
Исключение
    Сообщить("CR-06: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("06", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = ValueIsFilled(FreshA);
Исключение
    Сообщить("CR-07: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("07", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = ValueIsFilled(FreshB);
Исключение
    Сообщить("CR-08: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("08", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = FreshA <> FreshB;
Исключение
    Сообщить("CR-09: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("09", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = FreshA <> Catalogs.C01a9a4ac.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846"));
Исключение
    Сообщить("CR-10: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("10", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = FreshB <> Catalogs.C01a9a4ac.GetRef(New UUID("895e6e79-e0c6-474d-bad2-7aeee4aa3846"));
Исключение
    Сообщить("CR-11: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("11", Result); КонецЕсли;
Observed = Истина;
Попытка
    Result = FreshA.Metadata() = FreshB.Metadata() And FreshA.Metadata() = Metadata.Catalogs.C01a9a4ac;
Исключение
    Сообщить("CR-12: [action-error]");
    Observed = Ложь;
КонецПопытки;
Если Observed Тогда CREmit("12", Result); КонецЕсли;
