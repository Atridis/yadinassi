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
Failed = Ложь;
S = Undefined;
Try S = Catalogs.Cc4e0bd7a.Select(); Except EndTry;
Try CREmit("01", Catalogs.Cc4e0bd7a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.product
Try CREmit("02", Catalogs.C3ee974be.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.category
Try CREmit("03", S.Next()); Except Message("CR-03: [action-error]"); EndTry;
// 0.next
Try CREmit("04", S.Code); Except Message("CR-04: [action-error]"); EndTry;
// 0.code
Try CREmit("05", S.A80493488); Except Message("CR-05: [action-error]"); EndTry;
// 0.boolean
Try CREmit("06", XMLString(S.Aba998999)); Except Message("CR-06: [action-error]"); EndTry;
// 0.date
Try CREmit("07", S.Ae089a1a5.Description); Except Message("CR-07: [action-error]"); EndTry;
// 0.category
Try CREmit("08", S.Next()); Except Message("CR-08: [action-error]"); EndTry;
// 1.next
Try CREmit("09", S.Code); Except Message("CR-09: [action-error]"); EndTry;
// 1.code
Try CREmit("10", S.A80493488); Except Message("CR-10: [action-error]"); EndTry;
// 1.boolean
Try CREmit("11", XMLString(S.Aba998999)); Except Message("CR-11: [action-error]"); EndTry;
// 1.date
Try CREmit("12", S.Ae089a1a5.Description); Except Message("CR-12: [action-error]"); EndTry;
// 1.category
Try CREmit("13", S.Next()); Except Message("CR-13: [action-error]"); EndTry;
// 2.next
Try CREmit("14", S.Code); Except Message("CR-14: [action-error]"); EndTry;
// 2.code
Try CREmit("15", S.A80493488); Except Message("CR-15: [action-error]"); EndTry;
// 2.boolean
Try CREmit("16", XMLString(S.Aba998999)); Except Message("CR-16: [action-error]"); EndTry;
// 2.date
Try CREmit("17", S.Ae089a1a5.Description); Except Message("CR-17: [action-error]"); EndTry;
// 2.category
Try CREmit("18", S.Next()); Except Message("CR-18: [action-error]"); EndTry;
// exhaust
Try CREmit("19", S.Next()); Except Message("CR-19: [action-error]"); EndTry;
// restart
Try CREmit("20", S.Code); Except Message("CR-20: [action-error]"); EndTry;
// restart.code
Try CREmit("21", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
// control.pad18
Try CREmit("22", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad19
Try CREmit("23", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad20
Try CREmit("24", Catalogs.Cc4e0bd7a.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad21
