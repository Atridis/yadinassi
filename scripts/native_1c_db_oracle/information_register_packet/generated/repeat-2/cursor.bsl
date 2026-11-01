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
S = Undefined; Try S = InformationRegisters.I67960de5.Select(); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C148d54b4.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", S.Next()); Except Message("CR-03: [action-error]"); EndTry;
// 0.next
Try CREmit("04", String(S.Product.UUID())); Except Message("CR-04: [action-error]"); EndTry;
// 0.product
Try CREmit("05", XMLString(S.Variant)); Except Message("CR-05: [action-error]"); EndTry;
// 0.variant
Try CREmit("06", XMLString(S.Price)); Except Message("CR-06: [action-error]"); EndTry;
// 0.price
Try CREmit("07", S.Available); Except Message("CR-07: [action-error]"); EndTry;
// 0.available
Try CREmit("08", XMLString(S.ValidUntil)); Except Message("CR-08: [action-error]"); EndTry;
// 0.date
Try CREmit("09", S.Note); Except Message("CR-09: [action-error]"); EndTry;
// 0.note
Try CREmit("10", S.Next()); Except Message("CR-10: [action-error]"); EndTry;
// 1.next
Try CREmit("11", String(S.Product.UUID())); Except Message("CR-11: [action-error]"); EndTry;
// 1.product
Try CREmit("12", XMLString(S.Variant)); Except Message("CR-12: [action-error]"); EndTry;
// 1.variant
Try CREmit("13", XMLString(S.Price)); Except Message("CR-13: [action-error]"); EndTry;
// 1.price
Try CREmit("14", S.Available); Except Message("CR-14: [action-error]"); EndTry;
// 1.available
Try CREmit("15", XMLString(S.ValidUntil)); Except Message("CR-15: [action-error]"); EndTry;
// 1.date
Try CREmit("16", S.Note); Except Message("CR-16: [action-error]"); EndTry;
// 1.note
Try CREmit("17", S.Next()); Except Message("CR-17: [action-error]"); EndTry;
// 2.next
Try CREmit("18", String(S.Product.UUID())); Except Message("CR-18: [action-error]"); EndTry;
// 2.product
Try CREmit("19", XMLString(S.Variant)); Except Message("CR-19: [action-error]"); EndTry;
// 2.variant
Try CREmit("20", XMLString(S.Price)); Except Message("CR-20: [action-error]"); EndTry;
// 2.price
Try CREmit("21", S.Available); Except Message("CR-21: [action-error]"); EndTry;
// 2.available
Try CREmit("22", XMLString(S.ValidUntil)); Except Message("CR-22: [action-error]"); EndTry;
// 2.date
Try CREmit("23", S.Note); Except Message("CR-23: [action-error]"); EndTry;
// 2.note
Try CREmit("24", S.Next()); Except Message("CR-24: [action-error]"); EndTry;
// exhaust
