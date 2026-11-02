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
E = Undefined; Try E = InformationRegisters.I641d343f.Select(Date(2024,2,29,12,0,1),Date(2024,2,29,12,0,1),New Structure("Product",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f")))); Except EndTry;
D = Undefined; Try D = InformationRegisters.I641d343f.Select(Date(2024,2,29,12,0,0),Date(2024,2,29,12,0,2),New Structure("Product",Catalogs.C6b515170.GetRef(New UUID("50e5aaee-280d-4b17-9bff-b087dbd38b4f"))),"Desc"); Except EndTry;
M = Undefined; Try M = InformationRegisters.I641d343f.Select(Date(2024,2,29,12,0,0),Date(2024,2,29,12,0,2),New Structure("Product",Catalogs.C6b515170.GetRef(New UUID("6aa4500d-9d13-4735-ad61-788c60808642")))); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I641d343f.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C6b515170.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", String(TypeOf(E))); Except Message("CR-03: [action-error]"); EndTry;
// type
Try CREmit("04", XMLString(E.Period)); Except Message("CR-04: [action-error]"); EndTry;
// before
Try CREmit("05", E.Next()); Except Message("CR-05: [action-error]"); EndTry;
// exact.0.next
Try CREmit("06", XMLString(E.Variant)); Except Message("CR-06: [action-error]"); EndTry;
// exact.0.variant
Try CREmit("07", XMLString(E.Period)); Except Message("CR-07: [action-error]"); EndTry;
// exact.0.period
Try CREmit("08", E.Next()); Except Message("CR-08: [action-error]"); EndTry;
// exact.1.next
Try CREmit("09", XMLString(E.Variant)); Except Message("CR-09: [action-error]"); EndTry;
// exact.1.variant
Try CREmit("10", XMLString(E.Period)); Except Message("CR-10: [action-error]"); EndTry;
// exact.1.period
Try CREmit("11", E.Next()); Except Message("CR-11: [action-error]"); EndTry;
// exact.end
Try CREmit("12", E.Next()); Except Message("CR-12: [action-error]"); EndTry;
// exact.again
Try CREmit("13", D.Next()); Except Message("CR-13: [action-error]"); EndTry;
// desc.0.next
Try CREmit("14", XMLString(D.Price)); Except Message("CR-14: [action-error]"); EndTry;
// desc.0.price
Try CREmit("15", D.Next()); Except Message("CR-15: [action-error]"); EndTry;
// desc.1.next
Try CREmit("16", XMLString(D.Price)); Except Message("CR-16: [action-error]"); EndTry;
// desc.1.price
Try CREmit("17", D.Next()); Except Message("CR-17: [action-error]"); EndTry;
// desc.2.next
Try CREmit("18", XMLString(D.Price)); Except Message("CR-18: [action-error]"); EndTry;
// desc.2.price
Try CREmit("19", D.Next()); Except Message("CR-19: [action-error]"); EndTry;
// desc.3.next
Try CREmit("20", XMLString(D.Price)); Except Message("CR-20: [action-error]"); EndTry;
// desc.3.price
Try CREmit("21", D.Next()); Except Message("CR-21: [action-error]"); EndTry;
// desc.end
Try CREmit("22", M.Next()); Except Message("CR-22: [action-error]"); EndTry;
// missing
Try CREmit("23", XMLString(M.Period)); Except Message("CR-23: [action-error]"); EndTry;
// missing.period
Try CREmit("24", String(TypeOf(E.Period))); Except Message("CR-24: [action-error]"); EndTry;
// period.type
