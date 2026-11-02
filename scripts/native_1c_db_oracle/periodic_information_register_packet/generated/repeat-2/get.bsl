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
G0 = Undefined; Try G0 = InformationRegisters.I641d343f.GetFirst(Date(2024,2,29,12,0,0),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
G1 = Undefined; Try G1 = InformationRegisters.I641d343f.GetFirst(Date(2024,2,29,12,0,1),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
G2 = Undefined; Try G2 = InformationRegisters.I641d343f.GetFirst(Date(2024,2,29,12,0,1) + 1,New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
L0 = Undefined; Try L0 = InformationRegisters.I641d343f.GetLast(Date(2024,2,29,12,0,0),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
L1 = Undefined; Try L1 = InformationRegisters.I641d343f.GetLast(Date(2024,2,29,12,0,1),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
L2 = Undefined; Try L2 = InformationRegisters.I641d343f.GetLast(Date(2024,2,29,12,0,1) - 1,New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
GM = Undefined; Try GM = InformationRegisters.I641d343f.GetLast(Date(2024,2,29,12,0,1),New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("6aa4500d-9d13-4735-ad61-788c60808642")),1)); Except EndTry;
GN = Undefined; Try GN = InformationRegisters.I641d343f.GetFirst(Date(2024,2,29,12,0,2) + 1,New Structure("Product,Variant",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")),1)); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I641d343f.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C6b515170.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", XMLString(G0.Price)); Except Message("CR-03: [action-error]"); EndTry;
// G0.price
Try CREmit("04", XMLString(G1.Price)); Except Message("CR-04: [action-error]"); EndTry;
// G1.price
Try CREmit("05", XMLString(G2.Price)); Except Message("CR-05: [action-error]"); EndTry;
// G2.price
Try CREmit("06", XMLString(L0.Price)); Except Message("CR-06: [action-error]"); EndTry;
// L0.price
Try CREmit("07", XMLString(L1.Price)); Except Message("CR-07: [action-error]"); EndTry;
// L1.price
Try CREmit("08", XMLString(L2.Price)); Except Message("CR-08: [action-error]"); EndTry;
// L2.price
Try CREmit("09", XMLString(GM.Price)); Except Message("CR-09: [action-error]"); EndTry;
// GM.price
Try CREmit("10", XMLString(GN.Price)); Except Message("CR-10: [action-error]"); EndTry;
// GN.price
Try CREmit("11", String(TypeOf(G1))); Except Message("CR-11: [action-error]"); EndTry;
// type
Try CREmit("12", G1.Count()); Except Message("CR-12: [action-error]"); EndTry;
// count
Try CREmit("13", G1.Property("Period")); Except Message("CR-13: [action-error]"); EndTry;
// has.period
Try CREmit("14", G1.Property("Product")); Except Message("CR-14: [action-error]"); EndTry;
// has.product
Try CREmit("15", G1.Property("Note")); Except Message("CR-15: [action-error]"); EndTry;
// has.note
Try CREmit("16", G1.Available); Except Message("CR-16: [action-error]"); EndTry;
// boolean
Try CREmit("17", XMLString(G1.ValidUntil)); Except Message("CR-17: [action-error]"); EndTry;
// date
Try CREmit("18", GM.Count()); Except Message("CR-18: [action-error]"); EndTry;
// missing.count
Try CREmit("19", GM.Available); Except Message("CR-19: [action-error]"); EndTry;
// missing.boolean
Try CREmit("20", XMLString(GM.ValidUntil)); Except Message("CR-20: [action-error]"); EndTry;
// missing.date
Try CREmit("21", GN.Count()); Except Message("CR-21: [action-error]"); EndTry;
// future.count
Try CREmit("22", GN.Available); Except Message("CR-22: [action-error]"); EndTry;
// future.boolean
Try CREmit("23", XMLString(GN.ValidUntil)); Except Message("CR-23: [action-error]"); EndTry;
// future.date
Try CREmit("24", String(TypeOf(InformationRegisters.I641d343f))); Except Message("CR-24: [action-error]"); EndTry;
// manager.type
