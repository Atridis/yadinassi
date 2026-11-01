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
IterCount = Undefined; IterAmount = Undefined; IterLines = Undefined; Try IterCount = 0; IterAmount = 0; IterLines = ""; For Each R In Documents.De777997a.FindByNumber("20").Items Do IterCount = IterCount + 1; IterAmount = IterAmount + R.Amount; IterLines = IterLines + String(R.LineNumber) + ";"; EndDo; Except IterCount = Undefined; IterAmount = Undefined; IterLines = Undefined; EndTry;
Try CREmit("01", Documents.De777997a.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.document
Try CREmit("02", Catalogs.Cb27de61e.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", Documents.De777997a.FindByNumber("20").Items.Find(Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360")),"Product").LineNumber); Except Message("CR-03: [action-error]"); EndTry;
// find.first
Try CREmit("04", XMLString(Documents.De777997a.FindByNumber("20").Items.IndexOf(Documents.De777997a.FindByNumber("20").Items.Find(Catalogs.Cb27de61e.GetRef(New UUID("07de414c-becc-4dd0-ae38-6095e6769360")),"Product")))); Except Message("CR-04: [action-error]"); EndTry;
// find.index
Try CREmit("05", Documents.De777997a.FindByNumber("20").Items.Find(Catalogs.Cb27de61e.GetRef(New UUID("c98e2ffe-2a0e-4004-847d-d66047e28034")),"Product") = Undefined); Except Message("CR-05: [action-error]"); EndTry;
// find.missing
Try CREmit("06", XMLString(Documents.De777997a.FindByNumber("20").Items.IndexOf(Documents.De777997a.FindByNumber("20").Items.Get(2)))); Except Message("CR-06: [action-error]"); EndTry;
// row.index
Try CREmit("07", XMLString(Documents.De777997a.FindByNumber("20").Items.IndexOf(Documents.De777997a.FindByNumber("10").Items.Get(0)))); Except Message("CR-07: [action-error]"); EndTry;
// foreign.index
Try CREmit("08", XMLString(Documents.De777997a.FindByNumber("20").Items.Total("Amount"))); Except Message("CR-08: [action-error]"); EndTry;
// total
Try CREmit("09", XMLString(Documents.De777997a.FindByNumber("30").Items.Total("Amount"))); Except Message("CR-09: [action-error]"); EndTry;
// empty.total
Try CREmit("10", XMLString(Documents.De777997a.FindByNumber("10").Items.Total("Amount"))); Except Message("CR-10: [action-error]"); EndTry;
// one.total
Try CREmit("11", IterCount); Except Message("CR-11: [action-error]"); EndTry;
// foreach.count
Try CREmit("12", XMLString(IterAmount)); Except Message("CR-12: [action-error]"); EndTry;
// foreach.amount
Try CREmit("13", IterLines); Except Message("CR-13: [action-error]"); EndTry;
// foreach.lines
Try CREmit("14", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-14: [action-error]"); EndTry;
// control.pad13
Try CREmit("15", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-15: [action-error]"); EndTry;
// control.pad14
Try CREmit("16", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-16: [action-error]"); EndTry;
// control.pad15
Try CREmit("17", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-17: [action-error]"); EndTry;
// control.pad16
Try CREmit("18", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-18: [action-error]"); EndTry;
// control.pad17
Try CREmit("19", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-19: [action-error]"); EndTry;
// control.pad18
Try CREmit("20", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-20: [action-error]"); EndTry;
// control.pad19
Try CREmit("21", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
// control.pad20
Try CREmit("22", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad21
Try CREmit("23", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad22
Try CREmit("24", Documents.De777997a.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
