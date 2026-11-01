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
Try CREmit("01", Documents.D83c067c6.EmptyRef().Metadata().Name); Except Message("CR-01: [action-error]"); EndTry;
// control.document
Try CREmit("02", Catalogs.C1bb732a4.EmptyRef().Metadata().Name); Except Message("CR-02: [action-error]"); EndTry;
// control.catalog
Try CREmit("03", Documents.D83c067c6.FindByNumber("20").Items.Get(0).LineNumber); Except Message("CR-03: [action-error]"); EndTry;
// 0.line
Try CREmit("04", String(Documents.D83c067c6.FindByNumber("20").Items.Get(0).Product.UUID())); Except Message("CR-04: [action-error]"); EndTry;
// 0.product
Try CREmit("05", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(0).Quantity)); Except Message("CR-05: [action-error]"); EndTry;
// 0.quantity
Try CREmit("06", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(0).Price)); Except Message("CR-06: [action-error]"); EndTry;
// 0.price
Try CREmit("07", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(0).Amount)); Except Message("CR-07: [action-error]"); EndTry;
// 0.amount
Try CREmit("08", Documents.D83c067c6.FindByNumber("20").Items.Get(0).Note); Except Message("CR-08: [action-error]"); EndTry;
// 0.note
Try CREmit("09", Documents.D83c067c6.FindByNumber("20").Items.Get(1).LineNumber); Except Message("CR-09: [action-error]"); EndTry;
// 1.line
Try CREmit("10", String(Documents.D83c067c6.FindByNumber("20").Items.Get(1).Product.UUID())); Except Message("CR-10: [action-error]"); EndTry;
// 1.product
Try CREmit("11", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(1).Quantity)); Except Message("CR-11: [action-error]"); EndTry;
// 1.quantity
Try CREmit("12", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(1).Price)); Except Message("CR-12: [action-error]"); EndTry;
// 1.price
Try CREmit("13", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(1).Amount)); Except Message("CR-13: [action-error]"); EndTry;
// 1.amount
Try CREmit("14", Documents.D83c067c6.FindByNumber("20").Items.Get(1).Note); Except Message("CR-14: [action-error]"); EndTry;
// 1.note
Try CREmit("15", Documents.D83c067c6.FindByNumber("20").Items.Get(2).LineNumber); Except Message("CR-15: [action-error]"); EndTry;
// 2.line
Try CREmit("16", String(Documents.D83c067c6.FindByNumber("20").Items.Get(2).Product.UUID())); Except Message("CR-16: [action-error]"); EndTry;
// 2.product
Try CREmit("17", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(2).Quantity)); Except Message("CR-17: [action-error]"); EndTry;
// 2.quantity
Try CREmit("18", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(2).Price)); Except Message("CR-18: [action-error]"); EndTry;
// 2.price
Try CREmit("19", XMLString(Documents.D83c067c6.FindByNumber("20").Items.Get(2).Amount)); Except Message("CR-19: [action-error]"); EndTry;
// 2.amount
Try CREmit("20", Documents.D83c067c6.FindByNumber("20").Items.Get(2).Note); Except Message("CR-20: [action-error]"); EndTry;
// 2.note
Try CREmit("21", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
// control.pad20
Try CREmit("22", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad21
Try CREmit("23", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad22
Try CREmit("24", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
