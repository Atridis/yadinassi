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
S = Undefined; Try S = InformationRegisters.I641d343f.Select(); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I641d343f.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C6b515170.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", S.Next()); Except Message("CR-03: [action-error]"); EndTry;
// 0.next
Try CREmit("04", XMLString(S.Period)); Except Message("CR-04: [action-error]"); EndTry;
// 0.period
Try CREmit("05", String(S.Product.UUID())); Except Message("CR-05: [action-error]"); EndTry;
// 0.product
Try CREmit("06", XMLString(S.Variant)); Except Message("CR-06: [action-error]"); EndTry;
// 0.variant
Try CREmit("07", S.Next()); Except Message("CR-07: [action-error]"); EndTry;
// 1.next
Try CREmit("08", XMLString(S.Period)); Except Message("CR-08: [action-error]"); EndTry;
// 1.period
Try CREmit("09", String(S.Product.UUID())); Except Message("CR-09: [action-error]"); EndTry;
// 1.product
Try CREmit("10", XMLString(S.Variant)); Except Message("CR-10: [action-error]"); EndTry;
// 1.variant
Try CREmit("11", S.Next()); Except Message("CR-11: [action-error]"); EndTry;
// 2.next
Try CREmit("12", XMLString(S.Period)); Except Message("CR-12: [action-error]"); EndTry;
// 2.period
Try CREmit("13", String(S.Product.UUID())); Except Message("CR-13: [action-error]"); EndTry;
// 2.product
Try CREmit("14", XMLString(S.Variant)); Except Message("CR-14: [action-error]"); EndTry;
// 2.variant
Try CREmit("15", S.Next()); Except Message("CR-15: [action-error]"); EndTry;
// 3.next
Try CREmit("16", XMLString(S.Period)); Except Message("CR-16: [action-error]"); EndTry;
// 3.period
Try CREmit("17", String(S.Product.UUID())); Except Message("CR-17: [action-error]"); EndTry;
// 3.product
Try CREmit("18", XMLString(S.Variant)); Except Message("CR-18: [action-error]"); EndTry;
// 3.variant
Try CREmit("19", S.Next()); Except Message("CR-19: [action-error]"); EndTry;
// 4.next
Try CREmit("20", XMLString(S.Period)); Except Message("CR-20: [action-error]"); EndTry;
// 4.period
Try CREmit("21", String(S.Product.UUID())); Except Message("CR-21: [action-error]"); EndTry;
// 4.product
Try CREmit("22", XMLString(S.Variant)); Except Message("CR-22: [action-error]"); EndTry;
// 4.variant
Try CREmit("23", S.Next()); Except Message("CR-23: [action-error]"); EndTry;
// exhaust
Try CREmit("24", XMLString(S.Period)); Except Message("CR-24: [action-error]"); EndTry;
// retained
