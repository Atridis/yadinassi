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
Try CREmit("01", Documents.Dad0328ac.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.document
Try CREmit("02", Catalogs.C95217507.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", Documents.Dad0328ac.FindByNumber("30").A7d6294c3); Except Message("CR-03: [action-error]"); EndTry;
// 30.text
Try CREmit("04", XMLString(Documents.Dad0328ac.FindByNumber("30").Aeea091ef)); Except Message("CR-04: [action-error]"); EndTry;
// 30.number
Try CREmit("05", Documents.Dad0328ac.FindByNumber("30").Ac27bdff6); Except Message("CR-05: [action-error]"); EndTry;
// 30.boolean
Try CREmit("06", XMLString(Documents.Dad0328ac.FindByNumber("30").A4f92e66d)); Except Message("CR-06: [action-error]"); EndTry;
// 30.datetime
Try CREmit("07", String(Documents.Dad0328ac.FindByNumber("30").A5449af58.UUID())); Except Message("CR-07: [action-error]"); EndTry;
// 30.target.uuid
Try CREmit("08", Documents.Dad0328ac.FindByNumber("30").A5449af58.Description); Except Message("CR-08: [action-error]"); EndTry;
// 30.target.description
Try CREmit("09", Documents.Dad0328ac.FindByNumber("10").A7d6294c3); Except Message("CR-09: [action-error]"); EndTry;
// 10.text
Try CREmit("10", XMLString(Documents.Dad0328ac.FindByNumber("10").Aeea091ef)); Except Message("CR-10: [action-error]"); EndTry;
// 10.number
Try CREmit("11", Documents.Dad0328ac.FindByNumber("10").Ac27bdff6); Except Message("CR-11: [action-error]"); EndTry;
// 10.boolean
Try CREmit("12", XMLString(Documents.Dad0328ac.FindByNumber("10").A4f92e66d)); Except Message("CR-12: [action-error]"); EndTry;
// 10.datetime
Try CREmit("13", String(Documents.Dad0328ac.FindByNumber("10").A5449af58.UUID())); Except Message("CR-13: [action-error]"); EndTry;
// 10.target.uuid
Try CREmit("14", Documents.Dad0328ac.FindByNumber("10").A5449af58.Description); Except Message("CR-14: [action-error]"); EndTry;
// 10.target.description
Try CREmit("15", Documents.Dad0328ac.FindByNumber("20").A7d6294c3); Except Message("CR-15: [action-error]"); EndTry;
// 20.text
Try CREmit("16", XMLString(Documents.Dad0328ac.FindByNumber("20").Aeea091ef)); Except Message("CR-16: [action-error]"); EndTry;
// 20.number
Try CREmit("17", Documents.Dad0328ac.FindByNumber("20").Ac27bdff6); Except Message("CR-17: [action-error]"); EndTry;
// 20.boolean
Try CREmit("18", XMLString(Documents.Dad0328ac.FindByNumber("20").A4f92e66d)); Except Message("CR-18: [action-error]"); EndTry;
// 20.datetime
Try CREmit("19", String(Documents.Dad0328ac.FindByNumber("20").A5449af58.UUID())); Except Message("CR-19: [action-error]"); EndTry;
// 20.target.uuid
Try CREmit("20", Documents.Dad0328ac.FindByNumber("20").A5449af58.Description); Except Message("CR-20: [action-error]"); EndTry;
// 20.target.description
Try CREmit("21", TypeOf(Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611")).A5449af58) = Type("CatalogRef.C95217507")); Except Message("CR-21: [action-error]"); EndTry;
// target.type
Try CREmit("22", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad21
Try CREmit("23", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad22
Try CREmit("24", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
