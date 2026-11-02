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
G1 = Undefined; Try G1 = InformationRegisters.I27c9f847.Get(New Structure("Product,Variant",Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18")),1)); Except EndTry;
G2 = Undefined; Try G2 = InformationRegisters.I27c9f847.Get(New Structure("Product,Variant",Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18")),2)); Except EndTry;
G3 = Undefined; Try G3 = InformationRegisters.I27c9f847.Get(New Structure("Product,Variant",Catalogs.C50827504.GetRef(New UUID("7b2f71d1-55b1-4812-9c0f-291a91b89f73")),1)); Except EndTry;
GM = Undefined; Try GM = InformationRegisters.I27c9f847.Get(New Structure("Product,Variant",Catalogs.C50827504.GetRef(New UUID("da1a3f46-b75f-42e6-9e85-2dde635430a9")),1)); Except EndTry;
GV = Undefined; Try GV = InformationRegisters.I27c9f847.Get(New Structure("Product,Variant",Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18")),99)); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I27c9f847.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C50827504.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", XMLString(G1.Price)); Except Message("CR-03: [action-error]"); EndTry;
// a1.price
Try CREmit("04", G1.Available); Except Message("CR-04: [action-error]"); EndTry;
// a1.available
Try CREmit("05", XMLString(G1.ValidUntil)); Except Message("CR-05: [action-error]"); EndTry;
// a1.date
Try CREmit("06", XMLString(G2.Price)); Except Message("CR-06: [action-error]"); EndTry;
// a2.price
Try CREmit("07", G2.Available); Except Message("CR-07: [action-error]"); EndTry;
// a2.available
Try CREmit("08", XMLString(G2.ValidUntil)); Except Message("CR-08: [action-error]"); EndTry;
// a2.date
Try CREmit("09", XMLString(G3.Price)); Except Message("CR-09: [action-error]"); EndTry;
// b1.price
Try CREmit("10", G3.Available); Except Message("CR-10: [action-error]"); EndTry;
// b1.available
Try CREmit("11", XMLString(G3.ValidUntil)); Except Message("CR-11: [action-error]"); EndTry;
// b1.date
Try CREmit("12", XMLString(GM.Price)); Except Message("CR-12: [action-error]"); EndTry;
// missing.price
Try CREmit("13", GM.Available); Except Message("CR-13: [action-error]"); EndTry;
// missing.available
Try CREmit("14", XMLString(GM.ValidUntil)); Except Message("CR-14: [action-error]"); EndTry;
// missing.date
Try CREmit("15", String(TypeOf(G1))); Except Message("CR-15: [action-error]"); EndTry;
// type
Try CREmit("16", G1.Count()); Except Message("CR-16: [action-error]"); EndTry;
// count
Try CREmit("17", G1.Property("Price")); Except Message("CR-17: [action-error]"); EndTry;
// has.price
Try CREmit("18", G1.Property("Product")); Except Message("CR-18: [action-error]"); EndTry;
// has.product
Try CREmit("19", G1.Property("Variant")); Except Message("CR-19: [action-error]"); EndTry;
// has.variant
Try CREmit("20", G1.Property("Note")); Except Message("CR-20: [action-error]"); EndTry;
// has.note
Try CREmit("21", InformationRegisters.I27c9f847.Get(New Structure("Variant,Product",1,Catalogs.C50827504.GetRef(New UUID("b1605ed5-bcdf-4193-911b-004a8bd3af18")))).Price = G1.Price); Except Message("CR-21: [action-error]"); EndTry;
// key.order
Try CREmit("22", XMLString(GV.Price)); Except Message("CR-22: [action-error]"); EndTry;
// missing.variant
Try CREmit("23", String(TypeOf(GM))); Except Message("CR-23: [action-error]"); EndTry;
// missing.type
Try CREmit("24", GM.Count()); Except Message("CR-24: [action-error]"); EndTry;
// missing.count
