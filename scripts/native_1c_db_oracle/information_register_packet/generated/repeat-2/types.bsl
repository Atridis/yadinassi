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
Try CREmit("03", String(TypeOf(InformationRegisters))); Except Message("CR-03: [action-error]"); EndTry;
// global
Try CREmit("04", String(TypeOf(InformationRegisters.I67960de5))); Except Message("CR-04: [action-error]"); EndTry;
// manager
Try CREmit("05", String(TypeOf(S))); Except Message("CR-05: [action-error]"); EndTry;
// selection
Try CREmit("06", XMLString(S.Price)); Except Message("CR-06: [action-error]"); EndTry;
// before
Try CREmit("07", S.Next()); Except Message("CR-07: [action-error]"); EndTry;
// next
Try CREmit("08", String(TypeOf(S.Product))); Except Message("CR-08: [action-error]"); EndTry;
// Product.type
Try CREmit("09", String(TypeOf(S.Variant))); Except Message("CR-09: [action-error]"); EndTry;
// Variant.type
Try CREmit("10", String(TypeOf(S.Price))); Except Message("CR-10: [action-error]"); EndTry;
// Price.type
Try CREmit("11", String(TypeOf(S.Available))); Except Message("CR-11: [action-error]"); EndTry;
// Available.type
Try CREmit("12", String(TypeOf(S.ValidUntil))); Except Message("CR-12: [action-error]"); EndTry;
// ValidUntil.type
Try CREmit("13", String(TypeOf(S.Note))); Except Message("CR-13: [action-error]"); EndTry;
// Note.type
Try CREmit("14", TypeOf(S.Product) = Type("CatalogRef.C148d54b4")); Except Message("CR-14: [action-error]"); EndTry;
// target.type
Try CREmit("15", S.Product.Description); Except Message("CR-15: [action-error]"); EndTry;
// target.description
Try CREmit("16", TypeOf(S) = Type("InformationRegisterSelection.I67960de5")); Except Message("CR-16: [action-error]"); EndTry;
// selection.identity
Try CREmit("17", InformationRegisters.I67960de5.Get(New Structure("Product",Catalogs.C148d54b4.GetRef(New UUID("d2c35e5b-fe67-4dd3-860f-d08924062e20")))) = Undefined); Except Message("CR-17: [action-error]"); EndTry;
// partial.key
Try CREmit("18", S.Next()); Except Message("CR-18: [action-error]"); EndTry;
// next2
Try CREmit("19", S.Next()); Except Message("CR-19: [action-error]"); EndTry;
// next3
Try CREmit("20", S.Next()); Except Message("CR-20: [action-error]"); EndTry;
// exhaust
Try CREmit("21", XMLString(S.Price)); Except Message("CR-21: [action-error]"); EndTry;
// retained
Try CREmit("22", S.Next()); Except Message("CR-22: [action-error]"); EndTry;
// restart
Try CREmit("23", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-23: [action-error]"); EndTry;
// pad22
Try CREmit("24", Metadata.InformationRegisters.I67960de5.Name); Except Message("CR-24: [action-error]"); EndTry;
// pad23
