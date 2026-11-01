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
F = Undefined; Try F = InformationRegisters.I67960de5.Select(New Structure("Product",Catalogs.C148d54b4.GetRef(New UUID("d2c35e5b-fe67-4dd3-860f-d08924062e20")))); Except EndTry;
FM = Undefined; Try FM = InformationRegisters.I67960de5.Select(New Structure("Product",Catalogs.C148d54b4.GetRef(New UUID("dfc24f9c-91d9-47be-a2f1-e43347c8c52c")))); Except EndTry;
D = Undefined; Try D = InformationRegisters.I67960de5.Select(New Structure("Product",Catalogs.C148d54b4.GetRef(New UUID("d2c35e5b-fe67-4dd3-860f-d08924062e20"))),"Desc"); Except EndTry;
Try CREmit("01", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-01: [action-error]"); EndTry;
// control.register
Try CREmit("02", Catalogs.C148d54b4.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", String(TypeOf(F))); Except Message("CR-03: [action-error]"); EndTry;
// type
Try CREmit("04", F.Variant); Except Message("CR-04: [action-error]"); EndTry;
// before
Try CREmit("05", F.Next()); Except Message("CR-05: [action-error]"); EndTry;
// 0.next
Try CREmit("06", XMLString(F.Variant)); Except Message("CR-06: [action-error]"); EndTry;
// 0.variant
Try CREmit("07", XMLString(F.Price)); Except Message("CR-07: [action-error]"); EndTry;
// 0.price
Try CREmit("08", F.Product.Description); Except Message("CR-08: [action-error]"); EndTry;
// 0.target
Try CREmit("09", F.Next()); Except Message("CR-09: [action-error]"); EndTry;
// 1.next
Try CREmit("10", XMLString(F.Variant)); Except Message("CR-10: [action-error]"); EndTry;
// 1.variant
Try CREmit("11", XMLString(F.Price)); Except Message("CR-11: [action-error]"); EndTry;
// 1.price
Try CREmit("12", F.Product.Description); Except Message("CR-12: [action-error]"); EndTry;
// 1.target
Try CREmit("13", F.Next()); Except Message("CR-13: [action-error]"); EndTry;
// exhaust
Try CREmit("14", F.Variant); Except Message("CR-14: [action-error]"); EndTry;
// retained
Try CREmit("15", F.Next()); Except Message("CR-15: [action-error]"); EndTry;
// restart
Try CREmit("16", FM.Next()); Except Message("CR-16: [action-error]"); EndTry;
// missing
Try CREmit("17", D.Next()); Except Message("CR-17: [action-error]"); EndTry;
// desc1
Try CREmit("18", XMLString(D.Variant)); Except Message("CR-18: [action-error]"); EndTry;
// desc1.variant
Try CREmit("19", D.Next()); Except Message("CR-19: [action-error]"); EndTry;
// desc2
Try CREmit("20", XMLString(D.Variant)); Except Message("CR-20: [action-error]"); EndTry;
// desc2.variant
Try CREmit("21", D.Next()); Except Message("CR-21: [action-error]"); EndTry;
// desc.end
Try CREmit("22", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-22: [action-error]"); EndTry;
// pad21
Try CREmit("23", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-23: [action-error]"); EndTry;
// pad22
Try CREmit("24", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-24: [action-error]"); EndTry;
// pad23
