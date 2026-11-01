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
Try CREmit("03", Documents.D83c067c6.FindByNumber("30").Items.Count()); Except Message("CR-03: [action-error]"); EndTry;
// zero
Try CREmit("04", Documents.D83c067c6.FindByNumber("10").Items.Count()); Except Message("CR-04: [action-error]"); EndTry;
// one
Try CREmit("05", Documents.D83c067c6.FindByNumber("20").Items.Count()); Except Message("CR-05: [action-error]"); EndTry;
// three
Try CREmit("06", String(TypeOf(Documents.D83c067c6.FindByNumber("20").Items))); Except Message("CR-06: [action-error]"); EndTry;
// section.type
Try CREmit("07", String(TypeOf(Documents.D83c067c6.FindByNumber("20").Items.Get(0)))); Except Message("CR-07: [action-error]"); EndTry;
// row.type
Try CREmit("08", TypeOf(Documents.D83c067c6.FindByNumber("20").Items) = Type("DocumentTabularSection.D83c067c6.Items")); Except Message("CR-08: [action-error]"); EndTry;
// section.type.identity
Try CREmit("09", TypeOf(Documents.D83c067c6.FindByNumber("20").Items.Get(0)) = Type("DocumentTabularSectionRow.D83c067c6.Items")); Except Message("CR-09: [action-error]"); EndTry;
// row.type.identity
Try CREmit("10", Documents.D83c067c6.FindByNumber("20").Items.Get(0).LineNumber); Except Message("CR-10: [action-error]"); EndTry;
// first.line
Try CREmit("11", Documents.D83c067c6.FindByNumber("10").Items.Get(0).LineNumber); Except Message("CR-11: [action-error]"); EndTry;
// other.owner.line
Try CREmit("12", Documents.D83c067c6.FindByNumber("20").Items[0] = Documents.D83c067c6.FindByNumber("20").Items.Get(0)); Except Message("CR-12: [action-error]"); EndTry;
// index.get
Try CREmit("13", Documents.D83c067c6.FindByNumber("20").Items.Get(0) = Documents.D83c067c6.FindByNumber("10").Items.Get(0)); Except Message("CR-13: [action-error]"); EndTry;
// cross.owner.row
Try CREmit("14", TypeOf(Documents.D83c067c6.FindByNumber("20").Items.Get(0).Product) = Type("CatalogRef.C1bb732a4")); Except Message("CR-14: [action-error]"); EndTry;
// product.type
Try CREmit("15", Documents.D83c067c6.FindByNumber("20").Items.Get(0).Product.Description); Except Message("CR-15: [action-error]"); EndTry;
// product.description
Try CREmit("16", Documents.D83c067c6.FindByNumber("10").Items.Get(0).Product.Description); Except Message("CR-16: [action-error]"); EndTry;
// second.product.description
Try CREmit("17", Documents.D83c067c6.FindByNumber("20").Items = Documents.D83c067c6.FindByNumber("20").Items); Except Message("CR-17: [action-error]"); EndTry;
// repeat.section.identity
Try CREmit("18", Documents.D83c067c6.FindByNumber("20").Items.Get(0) = Documents.D83c067c6.FindByNumber("20").Items.Get(0)); Except Message("CR-18: [action-error]"); EndTry;
// repeat.row.identity
Try CREmit("19", Documents.D83c067c6.EmptyRef().Items.Count()); Except Message("CR-19: [action-error]"); EndTry;
// empty.ref.count
Try CREmit("20", Documents.D83c067c6.GetRef(New UUID("df869c3e-008d-4910-85d8-951a17332e97")).Items.Count()); Except Message("CR-20: [action-error]"); EndTry;
// missing.ref.count
Try CREmit("21", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-21: [action-error]"); EndTry;
// control.pad20
Try CREmit("22", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-22: [action-error]"); EndTry;
// control.pad21
Try CREmit("23", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-23: [action-error]"); EndTry;
// control.pad22
Try CREmit("24", Documents.D83c067c6.EmptyRef().IsEmpty()); Except Message("CR-24: [action-error]"); EndTry;
// control.pad23
