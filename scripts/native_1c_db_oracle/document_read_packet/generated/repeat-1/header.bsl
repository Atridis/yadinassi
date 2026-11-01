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
Try CREmit("03", Documents.Dad0328ac.FindByNumber("30").Number); Except Message("CR-03: [action-error]"); EndTry;
// 30.number
Try CREmit("04", XMLString(Documents.Dad0328ac.FindByNumber("30").Date)); Except Message("CR-04: [action-error]"); EndTry;
// 30.date
Try CREmit("05", Documents.Dad0328ac.FindByNumber("30").Posted); Except Message("CR-05: [action-error]"); EndTry;
// 30.posted
Try CREmit("06", Documents.Dad0328ac.FindByNumber("30").DeletionMark); Except Message("CR-06: [action-error]"); EndTry;
// 30.deleted
Try CREmit("07", String(Documents.Dad0328ac.FindByNumber("30").UUID())); Except Message("CR-07: [action-error]"); EndTry;
// 30.uuid
Try CREmit("08", Documents.Dad0328ac.FindByNumber("10").Number); Except Message("CR-08: [action-error]"); EndTry;
// 10.number
Try CREmit("09", XMLString(Documents.Dad0328ac.FindByNumber("10").Date)); Except Message("CR-09: [action-error]"); EndTry;
// 10.date
Try CREmit("10", Documents.Dad0328ac.FindByNumber("10").Posted); Except Message("CR-10: [action-error]"); EndTry;
// 10.posted
Try CREmit("11", Documents.Dad0328ac.FindByNumber("10").DeletionMark); Except Message("CR-11: [action-error]"); EndTry;
// 10.deleted
Try CREmit("12", String(Documents.Dad0328ac.FindByNumber("10").UUID())); Except Message("CR-12: [action-error]"); EndTry;
// 10.uuid
Try CREmit("13", Documents.Dad0328ac.FindByNumber("20").Number); Except Message("CR-13: [action-error]"); EndTry;
// 20.number
Try CREmit("14", XMLString(Documents.Dad0328ac.FindByNumber("20").Date)); Except Message("CR-14: [action-error]"); EndTry;
// 20.date
Try CREmit("15", Documents.Dad0328ac.FindByNumber("20").Posted); Except Message("CR-15: [action-error]"); EndTry;
// 20.posted
Try CREmit("16", Documents.Dad0328ac.FindByNumber("20").DeletionMark); Except Message("CR-16: [action-error]"); EndTry;
// 20.deleted
Try CREmit("17", String(Documents.Dad0328ac.FindByNumber("20").UUID())); Except Message("CR-17: [action-error]"); EndTry;
// 20.uuid
Try CREmit("18", Documents.Dad0328ac.FindByNumber("30") = Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))); Except Message("CR-18: [action-error]"); EndTry;
// present
Try CREmit("19", Documents.Dad0328ac.FindByNumber("30", Date(2024,2,29)) = Documents.Dad0328ac.GetRef(New UUID("91153f8f-bd35-430b-bf69-9172632d2611"))); Except Message("CR-19: [action-error]"); EndTry;
// dated.lookup
Try CREmit("20", Documents.Dad0328ac.GetRef(New UUID("3247a168-60b7-4bbb-901d-1601b198cfb6")).Number); Except Message("CR-20: [action-error]"); EndTry;
// absent.number
Try CREmit("21", XMLString(Documents.Dad0328ac.GetRef(New UUID("3247a168-60b7-4bbb-901d-1601b198cfb6")).Date)); Except Message("CR-21: [action-error]"); EndTry;
// absent.date
Try CREmit("22", Documents.Dad0328ac.GetRef(New UUID("3247a168-60b7-4bbb-901d-1601b198cfb6")).Posted); Except Message("CR-22: [action-error]"); EndTry;
// absent.posted
Try CREmit("23", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad22
Try CREmit("24", Documents.Dad0328ac.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
