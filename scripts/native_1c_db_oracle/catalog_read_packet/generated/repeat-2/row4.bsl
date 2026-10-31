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
Попытка S = Catalogs.Cb0f3538b.Select(); Исключение КонецПопытки;
Попытка
    Result = Catalogs.Cb0f3538b.Metadata().Name;
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
    Result = S.Next();
Исключение
    Сообщить("CR-03: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("03", Result); КонецЕсли; Failed = Ложь;
// next1
Попытка
    Result = S.Next();
Исключение
    Сообщить("CR-04: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("04", Result); КонецЕсли; Failed = Ложь;
// next2
Попытка
    Result = S.Next();
Исключение
    Сообщить("CR-05: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("05", Result); КонецЕсли; Failed = Ложь;
// next3
Попытка
    Result = S.Next();
Исключение
    Сообщить("CR-06: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("06", Result); КонецЕсли; Failed = Ложь;
// next4
Попытка
    Result = S.Code;
Исключение
    Сообщить("CR-07: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("07", Result); КонецЕсли; Failed = Ложь;
// fourth.Code
Попытка
    Result = S.Description;
Исключение
    Сообщить("CR-08: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("08", Result); КонецЕсли; Failed = Ложь;
// fourth.Description
Попытка
    Result = S.Payload;
Исключение
    Сообщить("CR-09: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("09", Result); КонецЕсли; Failed = Ложь;
// fourth.Payload
Попытка
    Result = S.Amount;
Исключение
    Сообщить("CR-10: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("10", Result); КонецЕсли; Failed = Ложь;
// fourth.Amount
Попытка
    Result = S.DeletionMark;
Исключение
    Сообщить("CR-11: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("11", Result); КонецЕсли; Failed = Ложь;
// fourth.DeletionMark
Попытка
    Result = String(S.Ref.UUID());
Исключение
    Сообщить("CR-12: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("12", Result); КонецЕсли; Failed = Ложь;
// fourth.uuid
Попытка
    Result = S.Next();
Исключение
    Сообщить("CR-13: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("13", Result); КонецЕсли; Failed = Ложь;
// exhaust
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).Code;
Исключение
    Сообщить("CR-14: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("14", Result); КонецЕсли; Failed = Ложь;
// ref.Code
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).Description;
Исключение
    Сообщить("CR-15: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("15", Result); КонецЕсли; Failed = Ложь;
// ref.Description
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).Payload;
Исключение
    Сообщить("CR-16: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("16", Result); КонецЕсли; Failed = Ложь;
// ref.Payload
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).Amount;
Исключение
    Сообщить("CR-17: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("17", Result); КонецЕсли; Failed = Ложь;
// ref.Amount
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).DeletionMark;
Исключение
    Сообщить("CR-18: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("18", Result); КонецЕсли; Failed = Ложь;
// ref.DeletionMark
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).Ref = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71"));
Исключение
    Сообщить("CR-19: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("19", Result); КонецЕсли; Failed = Ложь;
// ref.ref
Попытка
    Result = TypeOf(Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71"))) = Type("CatalogRef.Cb0f3538b");
Исключение
    Сообщить("CR-20: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("20", Result); КонецЕсли; Failed = Ложь;
// ref.type
Попытка
    Result = ValueIsFilled(Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")));
Исключение
    Сообщить("CR-21: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("21", Result); КонецЕсли; Failed = Ложь;
// ref.filled
Попытка
    Result = Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).Metadata() = Metadata.Catalogs.Cb0f3538b;
Исключение
    Сообщить("CR-22: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("22", Result); КонецЕсли; Failed = Ложь;
// ref.metadata
Попытка
    Result = String(Catalogs.Cb0f3538b.GetRef(New UUID("700628db-fab5-4377-bce2-7e47b690ce71")).UUID());
Исключение
    Сообщить("CR-23: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("23", Result); КонецЕсли; Failed = Ложь;
// ref.uuid
Попытка
    Result = Catalogs.Cb0f3538b.EmptyRef().IsEmpty();
Исключение
    Сообщить("CR-24: [action-error]");
    Result = Неопределено; Failed = Истина;
КонецПопытки;
Если Не Failed Тогда CREmit("24", Result); КонецЕсли; Failed = Ложь;
// empty.isempty
