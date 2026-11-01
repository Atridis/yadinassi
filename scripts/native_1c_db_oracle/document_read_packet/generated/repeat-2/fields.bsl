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
Try CREmit("01", Documents.D8e1d8e38.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.document
Try CREmit("02", Catalogs.C8730e849.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", Documents.D8e1d8e38.FindByNumber("30").A1bd27738); Except Message("CR-03: [action-error]"); EndTry;
// 30.text
Try CREmit("04", XMLString(Documents.D8e1d8e38.FindByNumber("30").Ac0e7cd57)); Except Message("CR-04: [action-error]"); EndTry;
// 30.number
Try CREmit("05", Documents.D8e1d8e38.FindByNumber("30").Acf18520d); Except Message("CR-05: [action-error]"); EndTry;
// 30.boolean
Try CREmit("06", XMLString(Documents.D8e1d8e38.FindByNumber("30").A47fccf59)); Except Message("CR-06: [action-error]"); EndTry;
// 30.datetime
Try CREmit("07", String(Documents.D8e1d8e38.FindByNumber("30").Aa02f337c.UUID())); Except Message("CR-07: [action-error]"); EndTry;
// 30.target.uuid
Try CREmit("08", Documents.D8e1d8e38.FindByNumber("30").Aa02f337c.Description); Except Message("CR-08: [action-error]"); EndTry;
// 30.target.description
Try CREmit("09", Documents.D8e1d8e38.FindByNumber("10").A1bd27738); Except Message("CR-09: [action-error]"); EndTry;
// 10.text
Try CREmit("10", XMLString(Documents.D8e1d8e38.FindByNumber("10").Ac0e7cd57)); Except Message("CR-10: [action-error]"); EndTry;
// 10.number
Try CREmit("11", Documents.D8e1d8e38.FindByNumber("10").Acf18520d); Except Message("CR-11: [action-error]"); EndTry;
// 10.boolean
Try CREmit("12", XMLString(Documents.D8e1d8e38.FindByNumber("10").A47fccf59)); Except Message("CR-12: [action-error]"); EndTry;
// 10.datetime
Try CREmit("13", String(Documents.D8e1d8e38.FindByNumber("10").Aa02f337c.UUID())); Except Message("CR-13: [action-error]"); EndTry;
// 10.target.uuid
Try CREmit("14", Documents.D8e1d8e38.FindByNumber("10").Aa02f337c.Description); Except Message("CR-14: [action-error]"); EndTry;
// 10.target.description
Try CREmit("15", Documents.D8e1d8e38.FindByNumber("20").A1bd27738); Except Message("CR-15: [action-error]"); EndTry;
// 20.text
Try CREmit("16", XMLString(Documents.D8e1d8e38.FindByNumber("20").Ac0e7cd57)); Except Message("CR-16: [action-error]"); EndTry;
// 20.number
Try CREmit("17", Documents.D8e1d8e38.FindByNumber("20").Acf18520d); Except Message("CR-17: [action-error]"); EndTry;
// 20.boolean
Try CREmit("18", XMLString(Documents.D8e1d8e38.FindByNumber("20").A47fccf59)); Except Message("CR-18: [action-error]"); EndTry;
// 20.datetime
Try CREmit("19", String(Documents.D8e1d8e38.FindByNumber("20").Aa02f337c.UUID())); Except Message("CR-19: [action-error]"); EndTry;
// 20.target.uuid
Try CREmit("20", Documents.D8e1d8e38.FindByNumber("20").Aa02f337c.Description); Except Message("CR-20: [action-error]"); EndTry;
// 20.target.description
Try CREmit("21", TypeOf(Documents.D8e1d8e38.GetRef(New UUID("0c19a161-2292-4047-b890-d087eeef341e")).Aa02f337c) = Type("CatalogRef.C8730e849")); Except Message("CR-21: [action-error]"); EndTry;
// target.type
Try CREmit("22", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad21
Try CREmit("23", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad22
Try CREmit("24", Documents.D8e1d8e38.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
